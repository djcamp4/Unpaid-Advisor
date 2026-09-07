import asyncio
import os
import json
import httpx
from datetime import datetime, timedelta

FMP_BASE = "https://financialmodelingprep.com/stable"
OSP_BASE = "https://api.opensourceforall.com/api/v1"

_AMOUNT_MAP = {
    "$1,001 - $15,000":           8_000,
    "$15,001 - $50,000":          32_500,
    "$50,001 - $100,000":         75_000,
    "$100,001 - $250,000":        175_000,
    "$250,001 - $500,000":        375_000,
    "$500,001 - $1,000,000":      750_000,
    "$1,000,001 - $5,000,000":    3_000_000,
    "$5,000,001 - $25,000,000":   15_000_000,
    "$25,000,001 - $50,000,000":  37_500_000,
    "Over $50,000,000":           75_000_000,
}


def _parse_amount(s: str) -> int:
    return _AMOUNT_MAP.get((s or "").strip(), 0)


def _parse_date(s: str):
    s = (s or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _is_purchase(tx: dict) -> bool:
    t = (tx.get("type") or "").lower().strip()
    return "purchase" in t or t in ("buy", "p")


def _ticker(tx: dict) -> str | None:
    t = (tx.get("ticker") or tx.get("symbol") or "").strip().upper()
    if not t or t in ("--", "N/A", "NONE", ""):
        return None
    # Skip funds, bonds, options
    if len(t) > 5 or " " in t or "/" in t or "$" in t:
        return None
    return t


PAGE_SIZE = 25
MAX_PAGES = 100
CHAMBERS = (("senate-latest", "Senate"), ("house-latest", "House"))


def _read_page(response, chamber):
    # Never include the request URL (which contains the API key) in errors.
    if response.status_code == 402:
        raise RuntimeError(f"FMP {chamber} disclosures returned HTTP 402 (payment/access required). Check that your FMP subscription includes congressional disclosures.")
    if response.status_code != 200:
        raise RuntimeError(f"FMP {chamber} disclosures returned HTTP {response.status_code}. Check API access and rate limits.")
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(f"FMP {chamber} disclosures returned invalid JSON.") from None
    if not isinstance(data, list) or any(not isinstance(tx, dict) for tx in data):
        raise RuntimeError(f"FMP {chamber} disclosures returned an unexpected response. Check API access.")
    return data


def _past_cutoff(data, cutoff):
    # Latest feeds are ordered by disclosure, not transaction date. An old
    # transaction disclosed recently must not stop pagination prematurely.
    dates = [_parse_date(tx.get("disclosureDate")) for tx in data]
    return bool(dates) and all(d is not None and d < cutoff for d in dates)


def _check_page(data, seen, chamber):
    fingerprint = json.dumps(data, sort_keys=True)
    if fingerprint in seen:
        raise RuntimeError(f"FMP {chamber} repeated a page; congressional history is incomplete.")
    seen.add(fingerprint)


async def _fetch_chamber(client, endpoint, chamber, api_key, cutoff):
    transactions = []
    seen = set()
    for page in range(MAX_PAGES):
        try:
            response = await client.get(f"{FMP_BASE}/{endpoint}", params={
                "page": page, "limit": PAGE_SIZE, "apikey": api_key,
            })
        except httpx.RequestError:
            raise RuntimeError(f"Unable to reach FMP {chamber} disclosures. Please retry.") from None
        data = _read_page(response, chamber)
        if not data:
            return transactions
        _check_page(data, seen, chamber)
        transactions.extend({**tx, "_chamber": chamber} for tx in data)
        if _past_cutoff(data, cutoff):
            return transactions
        # Continue even after short pages: providers may cap the requested limit.
    raise RuntimeError(f"FMP {chamber} history exceeded the pagination limit; scan is incomplete.")


async def fetch_congressional_purchase_details(days: int = 30) -> dict[str, dict]:
    """Collect purchases disclosed within the window across both paginated feeds."""
    api_key = os.getenv("OSP_API_KEY", "")
    if not api_key:
        raise RuntimeError("OSP_API_KEY is not set. Add the OSP-API secret to the backend environment.")
    cutoff = datetime.now().date() - timedelta(days=days)
    async with httpx.AsyncClient(timeout=30) as client:
        transactions = []
        for page in range(1, MAX_PAGES + 1):
            response = await client.get(f"{OSP_BASE}/trades", headers={"X-API-Key": api_key}, params={"page": page, "per_page": PAGE_SIZE})
            if response.status_code != 200:
                raise RuntimeError(f"OSP congressional trades returned HTTP {response.status_code}.")
            payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(data, list):
                raise RuntimeError("OSP congressional trades returned an unexpected response.")
            transactions.extend(data)
            if not data or len(data) < PAGE_SIZE or _past_cutoff([{"disclosureDate": tx.get("disclosure_date")} for tx in data], cutoff):
                break
    normalized = [{"ticker": tx.get("ticker"), "type": tx.get("transaction_type"), "amount": tx.get("amount_range"), "disclosureDate": tx.get("disclosure_date"), "transactionDate": tx.get("transaction_date"), "senator": tx.get("member_name") or tx.get("politician"), "representative": tx.get("member_name") or tx.get("politician"), "_chamber": tx.get("chamber", "Congress").title()} for tx in transactions]
    return _purchase_details(normalized, cutoff)


def _purchase_details(transactions, cutoff):
    details: dict[str, dict] = {}
    for tx in transactions:
        if not _is_purchase(tx):
            continue
        tx_date = _parse_date(tx.get("disclosureDate") or tx.get("transactionDate") or "")
        if tx_date is None or tx_date < cutoff:
            continue
        ticker = _ticker(tx)
        if not ticker:
            continue
        amount = _parse_amount(tx.get("amount", ""))
        name = (tx.get("senator") or tx.get("representative") or f"{tx.get('firstName', '')} {tx.get('lastName', '')}".strip() or "Unknown")
        chamber = tx.get("_chamber", "Congress")

        if ticker not in details:
            details[ticker] = {"max_amount": 0, "buyers": []}

        if amount > details[ticker]["max_amount"]:
            details[ticker]["max_amount"] = amount

        details[ticker]["buyers"].append({
            "name": name,
            "chamber": chamber,
            "amount": tx.get("amount", "undisclosed"),
            "date": str(tx_date),
        })

    return details


async def fetch_congressional_purchases(days: int = 30) -> list[str]:
    """Return deduplicated ticker symbols sorted by largest single purchase."""
    details = await fetch_congressional_purchase_details(days)
    return [t for t, d in sorted(details.items(), key=lambda x: x[1]["max_amount"], reverse=True)]


async def get_ticker_congressional_context(ticker: str, days: int = 60) -> dict | None:
    """Return congressional purchase context for a specific ticker, or None."""
    try:
        details = await fetch_congressional_purchase_details(days)
        return details.get(ticker.upper())
    except Exception:
        return None


def get_ticker_congressional_context_sync(ticker: str, days: int = 60) -> dict | None:
    """Synchronous version using requests — safe to call from sync or async endpoints."""
    import requests as req
    api_key = os.getenv("OSP_API_KEY", "")
    if not api_key:
        return None
    cutoff = datetime.now().date() - timedelta(days=days)
    try:
        transactions = []
        with req.Session() as client:
            for page in range(1, MAX_PAGES + 1):
                response = client.get(f"{OSP_BASE}/trades", headers={"X-API-Key": api_key}, params={"page": page, "per_page": PAGE_SIZE}, timeout=30)
                if response.status_code != 200:
                    return None
                payload = response.json()
                data = payload.get("data") if isinstance(payload, dict) else None
                if not isinstance(data, list):
                    return None
                transactions.extend({"ticker": tx.get("ticker"), "type": tx.get("transaction_type"), "amount": tx.get("amount_range"), "disclosureDate": tx.get("disclosure_date"), "transactionDate": tx.get("transaction_date"), "senator": tx.get("member_name") or tx.get("politician"), "representative": tx.get("member_name") or tx.get("politician"), "_chamber": tx.get("chamber", "Congress").title()} for tx in data)
                if not data or len(data) < PAGE_SIZE or _past_cutoff([{"disclosureDate": tx.get("disclosure_date")} for tx in data], cutoff):
                    break
        return _purchase_details(transactions, cutoff).get(ticker.upper())
    except (req.RequestException, RuntimeError):
        return None


def format_congress_context(context: dict | None) -> str | None:
    """Format congressional context into a readable string for agent prompts."""
    if not context:
        return None
    buyers = context.get("buyers", [])
    if not buyers:
        return None
    lines = []
    seen = set()
    for b in buyers:
        key = b["name"]
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"{b['name']} ({b['chamber']}) purchased {b['amount']} on {b['date']}")
    return "; ".join(lines[:3])  # cap at 3 buyers to keep prompt concise
