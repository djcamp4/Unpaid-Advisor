import os
import time
from datetime import date, timedelta
import requests as _requests
import pandas as pd
import numpy as np

_POLY_KEY = os.environ.get("POLYGON_API_KEY", "")
_POLY_BASE = "https://api.polygon.io"

_cache: dict = {}
CACHE_TTL = 3600  # 1 hour

_session = _requests.Session()
_session.headers.update({"User-Agent": "UnpaidAdvisor/1.0"})


def _cached(key: str, fn):
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < CACHE_TTL:
        return entry["data"]
    result = fn()
    _cache[key] = {"ts": time.time(), "data": result}
    return result


def _get(path: str, params: dict = None) -> dict | None:
    p = {"apiKey": _POLY_KEY}
    if params:
        p.update(params)
    for attempt in range(3):
        try:
            r = _session.get(f"{_POLY_BASE}{path}", params=p, timeout=15)
            if r.status_code == 429:
                time.sleep(12 * (attempt + 1))
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict) and data.get("status") in ("ERROR", "NOT_FOUND"):
                return None
            return data
        except Exception:
            time.sleep(2)
    return None


def _to_float(val) -> float | None:
    try:
        v = float(val)
        return None if (np.isnan(v) or np.isinf(v)) else v
    except (TypeError, ValueError):
        return None


def _fmt_large(val: float | None) -> str:
    if val is None:
        return "N/A"
    if abs(val) >= 1e12:
        return f"${val/1e12:.2f}T"
    if abs(val) >= 1e9:
        return f"${val/1e9:.2f}B"
    if abs(val) >= 1e6:
        return f"${val/1e6:.2f}M"
    return f"${val:,.0f}"


def _fv(stmt: dict, *keys) -> float | None:
    """Extract value from a Polygon financial statement field, trying multiple key names."""
    for key in keys:
        item = stmt.get(key)
        if item is None:
            continue
        if isinstance(item, dict):
            v = _to_float(item.get("value"))
        else:
            v = _to_float(item)
        if v is not None:
            return v
    return None


def fetch_all(symbol: str) -> dict:
    symbol = symbol.upper().strip()

    def _fetch():
        today = date.today()
        one_year_ago = today - timedelta(days=365)
        five_years_ago = today - timedelta(days=365 * 5)

        # Current quote snapshot
        snap_raw = _get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{symbol}")
        snap = snap_raw.get("ticker", {}) if snap_raw else {}

        # Previous close (fallback price source)
        prev_raw = _get(f"/v2/aggs/ticker/{symbol}/prev")
        prev = prev_raw.get("results", [{}])[0] if prev_raw and prev_raw.get("results") else {}

        # Validate we have price data
        price = (
            _to_float(snap.get("day", {}).get("c"))
            or _to_float(snap.get("prevDay", {}).get("c"))
            or _to_float(prev.get("c"))
        )
        if not price:
            raise ValueError(f"Ticker '{symbol}' not found or has no price data.")

        # Ticker details (name, exchange, sector, market cap, shares)
        details_raw = _get(f"/v3/reference/tickers/{symbol}")
        details = details_raw.get("results", {}) if details_raw else {}

        # Annual financial statements (last 5 years)
        fins_raw = _get("/vX/reference/financials", {
            "ticker": symbol, "timeframe": "annual", "limit": 5, "order": "desc",
        })
        fins = fins_raw.get("results", []) if fins_raw else []

        # Daily history (1 year)
        hist_daily = _get(
            f"/v2/aggs/ticker/{symbol}/range/1/day/{one_year_ago}/{today}",
            {"adjusted": "true", "sort": "asc", "limit": 365},
        )

        # Weekly history (5 years)
        hist_weekly = _get(
            f"/v2/aggs/ticker/{symbol}/range/1/week/{five_years_ago}/{today}",
            {"adjusted": "true", "sort": "asc", "limit": 260},
        )

        # News
        news_raw = _get("/v2/reference/news", {
            "ticker": symbol, "limit": 8, "sort": "published_utc", "order": "desc",
        })
        news = news_raw.get("results", []) if news_raw else []

        return {
            "symbol": symbol,
            "snap": snap,
            "prev": prev,
            "details": details,
            "fins": fins,
            "hist_daily": hist_daily,
            "hist_weekly": hist_weekly,
            "news_raw": news,
        }

    return _cached(symbol, _fetch)


# ── Price / market helpers ────────────────────────────────────────────────────

def get_price(data: dict) -> float | None:
    snap = data["snap"]
    prev = data["prev"]
    return (
        _to_float(snap.get("day", {}).get("c"))
        or _to_float(snap.get("prevDay", {}).get("c"))
        or _to_float(prev.get("c"))
    )


def get_prev_close(data: dict) -> float | None:
    snap = data["snap"]
    prev = data["prev"]
    return (
        _to_float(snap.get("prevDay", {}).get("c"))
        or _to_float(prev.get("c"))
    )


def get_market_cap(data: dict) -> float | None:
    return (
        _to_float(data["details"].get("market_cap"))
        or _to_float(data["snap"].get("day", {}).get("c"))
        and _to_float(data["details"].get("weighted_shares_outstanding"))
        and _to_float(data["details"].get("market_cap"))
    )


def _shares(data: dict) -> float | None:
    return (
        _to_float(data["details"].get("weighted_shares_outstanding"))
        or _to_float(data["details"].get("share_class_shares_outstanding"))
    )


def _latest_fin(fins: list, stmt: str, *keys) -> float | None:
    for period in fins:
        v = _fv(period.get("financials", {}).get(stmt, {}), *keys)
        if v is not None:
            return v
    return None


def _fin_series(fins: list, stmt: str, *keys) -> list[float | None]:
    return [
        _fv(period.get("financials", {}).get(stmt, {}), *keys)
        for period in fins
    ]


# ── KPIs and fundamentals ─────────────────────────────────────────────────────

def get_kpis(data: dict) -> dict:
    fins = data["fins"]
    det = data["details"]
    snap = data["snap"]
    prev = data["prev"]

    price = get_price(data)
    mc = _to_float(det.get("market_cap"))
    shares = _shares(data)

    # EPS from most recent annual income statement
    eps = _latest_fin(fins, "income_statement",
                      "basic_earnings_per_share", "diluted_earnings_per_share")

    # Book value per share
    equity = _latest_fin(fins, "balance_sheet",
                         "equity", "equity_attributable_to_parent",
                         "stockholders_equity")
    bvps = (equity / shares) if equity and shares else None

    # PE, P/B, PEG
    pe = (price / eps) if price and eps and eps > 0 else None
    pb = (price / bvps) if price and bvps and bvps > 0 else None

    # PEG: PE / (earnings growth % yoy)
    ni_series = _fin_series(fins, "income_statement", "net_income_loss", "net_income")
    ni_vals = [v for v in ni_series if v is not None]
    eps_growth_pct = None
    if len(ni_vals) >= 2 and ni_vals[1] and ni_vals[1] != 0:
        eps_growth_pct = (ni_vals[0] - ni_vals[1]) / abs(ni_vals[1]) * 100
    peg = (pe / eps_growth_pct) if pe and eps_growth_pct and eps_growth_pct > 0 else None

    # Volume
    volume = _to_float(snap.get("day", {}).get("v")) or _to_float(prev.get("v"))

    # 52-week high/low from snapshot
    w52_high = _to_float(det.get("week_52_high"))
    w52_low = _to_float(det.get("week_52_low"))

    # Dividend yield
    div_yield = _latest_fin(fins, "income_statement",
                             "dividends_per_common_share")
    div_yield_pct = (div_yield / price) if div_yield and price else None

    return {
        "market_cap": mc,
        "market_cap_fmt": _fmt_large(mc),
        "pe_ratio": pe,
        "forward_pe": None,
        "peg_ratio": peg,
        "price_to_book": pb,
        "week_52_high": w52_high,
        "week_52_low": w52_low,
        "volume": volume,
        "avg_volume": None,
        "dividend_yield": div_yield_pct,
        "beta": _to_float(det.get("beta")),
        "eps_ttm": eps,
        "shares_outstanding": shares,
    }


def get_fundamentals(data: dict) -> dict:
    fins = data["fins"]
    price = get_price(data)
    shares = _shares(data)

    rev_series = _fin_series(fins, "income_statement", "revenues", "revenue")
    ni_series = _fin_series(fins, "income_statement", "net_income_loss", "net_income")
    rev_vals = [v for v in rev_series if v is not None]
    ni_vals = [v for v in ni_series if v is not None]

    rev = rev_vals[0] if rev_vals else None
    rev_growth = ((rev_vals[0] - rev_vals[1]) / abs(rev_vals[1])
                  if len(rev_vals) >= 2 and rev_vals[1] else None)
    eps_growth = ((ni_vals[0] - ni_vals[1]) / abs(ni_vals[1])
                  if len(ni_vals) >= 2 and ni_vals[1] else None)

    gross_profit = _latest_fin(fins, "income_statement", "gross_profit")
    op_income = _latest_fin(fins, "income_statement",
                            "operating_income_loss", "operating_income")
    net_income = _latest_fin(fins, "income_statement", "net_income_loss", "net_income")
    equity = _latest_fin(fins, "balance_sheet",
                         "equity", "equity_attributable_to_parent")
    total_assets = _latest_fin(fins, "balance_sheet", "assets")
    op_cf = _latest_fin(fins, "cash_flow_statement",
                        "net_cash_flow_from_operating_activities")
    capex = _latest_fin(fins, "cash_flow_statement", "capital_expenditure")
    fcf = (op_cf + capex) if op_cf and capex else op_cf

    gross_margin = (gross_profit / rev) if gross_profit and rev else None
    op_margin = (op_income / rev) if op_income and rev else None
    net_margin = (net_income / rev) if net_income and rev else None
    roe = (net_income / equity) if net_income and equity and equity > 0 else None
    roa = (net_income / total_assets) if net_income and total_assets else None
    bvps = (equity / shares) if equity and shares else None
    fcf_ps = (fcf / shares) if fcf and shares else None

    div = _latest_fin(fins, "income_statement", "dividends_per_common_share")
    div_yield = (div / price) if div and price else None

    eps = _latest_fin(fins, "income_statement",
                      "basic_earnings_per_share", "diluted_earnings_per_share")
    ltd = _latest_fin(fins, "balance_sheet", "long_term_debt", "noncurrent_debt")
    debt_to_eq = (ltd / equity) if ltd and equity and equity > 0 else None

    return {
        "eps_ttm": eps,
        "revenue_ttm": rev,
        "revenue_ttm_fmt": _fmt_large(rev),
        "revenue_growth_yoy": rev_growth,
        "gross_margin": gross_margin,
        "operating_margin": op_margin,
        "net_margin": net_margin,
        "profit_margin": net_margin,
        "free_cash_flow": fcf_ps,
        "free_cash_flow_fmt": _fmt_large(fcf),
        "debt_to_equity": debt_to_eq,
        "roe": roe,
        "roa": roa,
        "earnings_growth": eps_growth,
        "dividend_yield": div_yield,
        "shares_outstanding": shares,
        "book_value": bvps,
    }


def get_balance_sheet_metrics(data: dict) -> dict:
    fins = data["fins"]
    shares = _shares(data)

    def _series(*keys) -> list[float | None]:
        result = []
        for period in fins:
            for stmt_key in ("balance_sheet", "income_statement", "cash_flow_statement"):
                stmt = period.get("financials", {}).get(stmt_key, {})
                v = _fv(stmt, *keys)
                if v is not None:
                    result.append(v)
                    break
            else:
                result.append(None)
        return [v for v in result if v is not None]

    def _bs(*keys):
        return _series_from(fins, "balance_sheet", *keys)

    def _is(*keys):
        return _series_from(fins, "income_statement", *keys)

    def _cf(*keys):
        return _series_from(fins, "cash_flow_statement", *keys)

    ni_series = _is("net_income_loss", "net_income")
    rev_series = _is("revenues", "revenue")
    ni_vals = [v for v in ni_series if v is not None]
    rev_vals = [v for v in rev_series if v is not None]

    eps_growth = ((ni_vals[0] - ni_vals[1]) / abs(ni_vals[1])
                  if len(ni_vals) >= 2 and ni_vals[1] else None)
    rev_growth = ((rev_vals[0] - rev_vals[1]) / abs(rev_vals[1])
                  if len(rev_vals) >= 2 and rev_vals[1] else None)

    return {
        "current_assets": _bs("current_assets"),
        "current_liabilities": _bs("current_liabilities"),
        "long_term_debt": _bs("long_term_debt", "noncurrent_debt"),
        "equity": _bs("equity", "equity_attributable_to_parent", "stockholders_equity"),
        "net_income": ni_series,
        "da": _cf("depreciation_and_amortization", "depreciation_depletion_and_amortization"),
        "capex": _cf("capital_expenditure"),
        "op_income": _is("operating_income_loss", "operating_income"),
        "total_debt": _bs("long_term_debt", "noncurrent_debt"),
        "cash": _bs("cash_and_cash_equivalents", "cash"),
        "tax_rate": 0.21,
        "_info_proxy": {
            "earningsGrowth": eps_growth,
            "revenueGrowth": rev_growth,
            "sharesOutstanding": shares,
        },
    }


def _series_from(fins: list, stmt_key: str, *keys) -> list[float | None]:
    result = []
    for period in fins:
        stmt = period.get("financials", {}).get(stmt_key, {})
        v = _fv(stmt, *keys)
        if v is not None:
            result.append(v)
    return result


# ── Technical indicators (no external library) ────────────────────────────────

def _rsi(close: pd.Series, length: int = 14) -> float | None:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=length - 1, adjust=False).mean()
    avg_loss = loss.ewm(com=length - 1, adjust=False).mean()
    rs = avg_gain / avg_loss
    val = (100 - (100 / (1 + rs))).iloc[-1]
    return None if pd.isna(val) else float(val)


def _macd(close: pd.Series):
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    m = macd_line.iloc[-1]
    s = signal_line.iloc[-1]
    return None if pd.isna(m) or pd.isna(s) else bool(m > s)


def _bbands(close: pd.Series, length: int = 20, std: float = 2.0):
    sma = close.rolling(length).mean()
    dev = close.rolling(length).std()
    upper = (sma + std * dev).iloc[-1]
    lower = (sma - std * dev).iloc[-1]
    return (None, None) if pd.isna(upper) or pd.isna(lower) else (float(upper), float(lower))


def _sma(close: pd.Series, length: int) -> float | None:
    val = close.rolling(length).mean().iloc[-1]
    return None if pd.isna(val) else float(val)


def _parse_poly_hist(raw) -> pd.DataFrame | None:
    """Parse Polygon aggregate response {results: [{o,h,l,c,v,t}]}."""
    if not raw:
        return None
    results = raw.get("results", [])
    if not results:
        return None
    df = pd.DataFrame(results)
    # t is Unix ms timestamp
    df["date"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_localize(None)
    df = df.sort_values("date").reset_index(drop=True)
    df.rename(columns={"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume"},
              inplace=True)
    return df


def get_technicals(data: dict) -> dict:
    hist = _parse_poly_hist(data.get("hist_daily"))
    if hist is None or hist.empty:
        return {}

    close = hist["Close"]
    volume = hist["Volume"]
    price = float(close.iloc[-1])

    rsi = _rsi(close)
    macd_bullish = _macd(close)
    sma50 = _sma(close, 50)
    sma200 = _sma(close, 200)
    bb_upper, bb_lower = _bbands(close)

    bb_position = None
    if bb_upper is not None and bb_lower is not None and bb_upper != bb_lower:
        pct = (price - bb_lower) / (bb_upper - bb_lower)
        bb_position = "upper" if pct > 0.8 else "lower" if pct < 0.2 else "mid"

    avg_vol = float(volume.mean())
    cur_vol = float(volume.iloc[-1])
    vol_vs_avg = (cur_vol - avg_vol) / avg_vol if avg_vol else None

    recent = close.tail(20)
    support = float(recent.min())
    resistance = float(recent.max())

    bullish_signals = sum([
        rsi is not None and 40 < rsi < 70,
        macd_bullish is True,
        sma50 is not None and price > sma50,
        sma200 is not None and price > sma200,
    ])
    signal = "BUY" if bullish_signals >= 3 else "SELL" if bullish_signals <= 1 else "HOLD"

    return {
        "rsi": rsi,
        "macd_bullish": macd_bullish,
        "sma_50": sma50,
        "sma_200": sma200,
        "above_sma_50": price > sma50 if sma50 else None,
        "above_sma_200": price > sma200 if sma200 else None,
        "bb_position": bb_position,
        "volume_vs_avg": vol_vs_avg,
        "support": support,
        "resistance": resistance,
        "signal": signal,
        "bullish_signals": bullish_signals,
    }


def get_history(data: dict) -> dict:
    def _serialize(raw) -> list[dict]:
        df = _parse_poly_hist(raw)
        if df is None or df.empty:
            return []
        out = []
        for _, row in df.iterrows():
            try:
                out.append({
                    "date": row["date"].strftime("%Y-%m-%d"),
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]),
                })
            except Exception:
                pass
        return out

    return {
        "daily": _serialize(data.get("hist_daily")),
        "weekly": _serialize(data.get("hist_weekly")),
    }


# ── News ──────────────────────────────────────────────────────────────────────

POSITIVE_WORDS = {"surge", "soar", "beat", "record", "growth", "profit", "raise", "upgrade",
                  "strong", "bullish", "gain", "rally", "boost", "outperform", "exceed"}
NEGATIVE_WORDS = {"fall", "drop", "miss", "loss", "decline", "cut", "downgrade", "risk",
                  "warning", "concern", "weak", "bearish", "lawsuit", "probe", "fine", "restrict"}


def _sentiment(title: str) -> str:
    words = set(title.lower().split())
    pos = len(words & POSITIVE_WORDS)
    neg = len(words & NEGATIVE_WORDS)
    return "positive" if pos > neg else "negative" if neg > pos else "neutral"


def get_news(data: dict) -> list[dict]:
    out = []
    for item in (data["news_raw"] or [])[:8]:
        try:
            title = item.get("title", "")
            publisher = item.get("publisher", {}).get("name", "") if isinstance(item.get("publisher"), dict) else item.get("publisher", "")
            pub_date = (item.get("published_utc", "") or "")[:10]
            url = item.get("article_url", "") or item.get("url", "")
            if title:
                out.append({
                    "title": title,
                    "publisher": publisher,
                    "published_at": pub_date,
                    "url": url,
                    "sentiment": _sentiment(title),
                })
        except Exception:
            pass
    return out
