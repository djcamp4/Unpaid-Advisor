import asyncio
import os
import httpx
from datetime import datetime, timedelta

FMP_BASE = "https://financialmodelingprep.com/stable"

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
    # FMP stable API uses "ticker"; legacy endpoints may use "symbol"
    t = (tx.get("ticker") or tx.get("symbol") or "").strip().upper()
    if not t or t in ("--", "N/A", "NONE", ""):
        return None
    # Skip funds, bonds, options
    if len(t) > 5 or " " in t or "/" in t or "$" in t:
        return None
    return t


def _member_name(tx: dict) -> str:
    # FMP stable API returns full name as "senator" or "representative"
    return (
        tx.get("senator")
        or tx.get("representative")
        or f"{tx.get('firstName', '')} {tx.get('lastName', '')}".strip()
        or "Unknown"
    )


async def fetch_congressional_purchase_details(days: int = 30) -> dict[str, dict]:
    """
    Return {ticker: {max_amount, buyers: [{name, chamber, amount, date}]}}
    sorted by max_amount descending.
    """
    api_key = os.getenv("FMP_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "FMP_API_KEY is not set. Add it to backend/.env as FMP_API_KEY=your_key"
        )

    cutoff = datetime.now().date() - timedelta(days=days)
    params = {"page": 0, "limit": 25, "apikey": api_key}

    async with httpx.AsyncClient(timeout=30) as client:
        sr = await client.get(f"{FMP_BASE}/senate-latest", params=params)
        hr = await client.get(f"{FMP_BASE}/house-latest", params=params)

    transactions: list[dict] = []
    for resp, chamber, label in [(sr, "Senate", "senate"), (hr, "House", "house")]:
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                print(f"[congress] {label}: {len(data)} records", flush=True)
                for tx in data:
                    tx["_chamber"] = chamber
                transactions.extend(data)
            else:
                print(f"[congress] {label}: unexpected response type {type(data).__name__}: {str(data)[:200]}", flush=True)
        else:
            print(f"[congress] {label}: HTTP {resp.status_code} — {resp.text[:200]}", flush=True)

    print(f"[congress] {len(transactions)} total transactions before filtering (cutoff={cutoff})", flush=True)

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
        name = _member_name(tx)
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

    print(f"[congress] {len(details)} unique tickers after filtering: {list(details.keys())[:10]}", flush=True)
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
    api_key = os.getenv("FMP_API_KEY", "")
    if not api_key:
        return None
    cutoff = datetime.now().date() - timedelta(days=days)
    params = {"page": 0, "limit": 25, "apikey": api_key}
    try:
        transactions: list[dict] = []
        for url, chamber in [
            (f"{FMP_BASE}/senate-latest", "Senate"),
            (f"{FMP_BASE}/house-latest", "House"),
        ]:
            r = req.get(url, params=params, timeout=30)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    for tx in data:
                        tx["_chamber"] = chamber
                    transactions.extend(data)

        details: dict[str, dict] = {}
        for tx in transactions:
            if not _is_purchase(tx):
                continue
            tx_date = _parse_date(tx.get("disclosureDate") or tx.get("transactionDate") or "")
            if tx_date is None or tx_date < cutoff:
                continue
            t = _ticker(tx)
            if not t:
                continue
            amount = _parse_amount(tx.get("amount", ""))
            name = _member_name(tx)
            if t not in details:
                details[t] = {"max_amount": 0, "buyers": []}
            if amount > details[t]["max_amount"]:
                details[t]["max_amount"] = amount
            details[t]["buyers"].append({
                "name": name,
                "chamber": tx.get("_chamber", "Congress"),
                "amount": tx.get("amount", "undisclosed"),
                "date": str(tx_date),
            })
        return details.get(ticker.upper())
    except Exception:
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
