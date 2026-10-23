"""Free annual financial statements from FinDataEngine's SEC filing feed."""
import math
import os
import threading
import time
from urllib.parse import quote

import requests


class FinancialDataError(RuntimeError):
    """Safe, user-facing provider error (never contains credentials or URLs)."""
    def __init__(self, message, *, global_failure=True):
        super().__init__(message)
        self.global_failure = global_failure


_cache = {}
_lock = threading.Lock()
_slots = threading.Semaphore(2)
_TTL = 86400
_FIELDS = {
    "income_statement": {
        "revenues": "revenue", "net_income_loss": "net_income",
        "gross_profit": "gross_profit", "operating_income_loss": "operating_income",
        "basic_earnings_per_share": "eps_basic",
        "diluted_earnings_per_share": "eps_diluted",
    },
    "balance_sheet": {
        "equity": "total_stockholders_equity", "assets": "total_assets",
        "long_term_debt": "long_term_debt",
        "current_assets": "total_current_assets", "current_liabilities": "total_current_liabilities",
        "cash_and_cash_equivalents": "cash_and_equivalents",
    },
    "cash_flow_statement": {
        "net_cash_flow_from_operating_activities": "net_cash_operating",
        "capital_expenditure": "capital_expenditures",
        "depreciation_and_amortization": "depreciation_amortization",
    },
}


def _number(value):
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    return None


def normalize_statements(statements):
    """Join by period end, never by array position or fiscal-year label."""
    by_statement = {}
    for name, rows in statements.items():
        by_date = {}
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("period_end"), str):
                raise FinancialDataError("FinDataEngine returned an invalid financial reporting period.")
            end = row["period_end"]
            if end not in by_date or str(row.get("as_reported_filed", "")) > str(by_date[end].get("as_reported_filed", "")):
                by_date[end] = row
        by_statement[name] = by_date
    dates = sorted(by_statement["income_statement"], reverse=True)[:5]
    if not dates:
        raise FinancialDataError("FinDataEngine has no annual income statements for this stock. Analysis cannot run without financial data.", global_failure=False)
    if any(dates[0] not in by_statement[name] for name in _FIELDS):
        raise FinancialDataError("FinDataEngine is missing matching balance-sheet or cash-flow data for the latest annual report. Analysis cannot run on incomplete statements.", global_failure=False)
    results = []
    for end in dates:
        financials = {}
        for name, mapping in _FIELDS.items():
            row = by_statement[name].get(end, {})
            values = {}
            for target, source in mapping.items():
                value = _number(row.get(source))
                if value is not None:
                    # SEC reports expenditure as a positive outflow; the scorer
                    # expects signed capex for operating cash flow + capex.
                    if target == "capital_expenditure":
                        value = -abs(value)
                    values[target] = {"value": value}
            financials[name] = values
        results.append({"end_date": end, "financials": financials})
    if not results[0]["financials"]["income_statement"]:
        raise FinancialDataError("FinDataEngine returned an empty income statement. Analysis cannot run without financial data.", global_failure=False)
    return results


def _statement(symbol, statement, key):
    url = f"https://asreported.io/v1/companies/{quote(symbol, safe='')}/fundamentals"
    for attempt in range(2):
        try:
            with _slots:
                response = requests.get(url, headers={"X-API-Key": key},
                                        params={"statement": statement, "period": "annual"}, timeout=25)
        except requests.Timeout:
            raise FinancialDataError("FinDataEngine timed out while loading financial statements. Please retry.") from None
        except requests.RequestException:
            raise FinancialDataError("Could not connect to FinDataEngine for financial statements. Please retry.") from None
        status = response.status_code
        if status == 401:
            raise FinancialDataError("FinDataEngine rejected the API key. Update the FinDataEngine-API secret.")
        if status in (402, 403):
            raise FinancialDataError("FinDataEngine denied financial-data access. Check the account's API permissions and quota.")
        if status == 404:
            raise FinancialDataError("FinDataEngine does not have financial statements for this stock.", global_failure=False)
        if status == 429:
            raise FinancialDataError("FinDataEngine's request limit has been reached. Wait for the quota to reset before retrying.")
        if status >= 500 and attempt == 0:
            time.sleep(1)
            continue
        if status != 200:
            raise FinancialDataError(f"FinDataEngine financial statements are unavailable (HTTP {status}).")
        try:
            payload = response.json()
        except ValueError:
            raise FinancialDataError("FinDataEngine returned an invalid financial-data response.") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise FinancialDataError("FinDataEngine returned an unexpected financial-data format.")
        return payload["data"]


def fetch_financials(symbol):
    key = os.getenv("FINDATAENGINE_API_KEY", "").strip()
    if not key:
        raise FinancialDataError("Financial data is not configured. Connect the FinDataEngine-API secret to the backend.")
    symbol = symbol.upper().strip()
    with _lock:
        cached = _cache.get(symbol)
        if cached and time.monotonic() - cached[0] < _TTL:
            return cached[1]
    statements = {
        name: _statement(symbol, "cash_flow" if name == "cash_flow_statement" else name, key)
        for name in _FIELDS
    }
    result = normalize_statements(statements)
    with _lock:
        # Bound memory in long-lived service instances.
        if len(_cache) >= 500:
            _cache.pop(next(iter(_cache)))
        _cache[symbol] = (time.monotonic(), result)
    return result
