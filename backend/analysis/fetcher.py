import os
import time
import requests as _requests
import pandas as pd
import numpy as np

_FMP_KEY = os.environ.get("FMP_API_KEY", "S50WQYCaOtXcM5m9Kt9b3aRZWcJ5aoxz")
_FMP_BASE = "https://financialmodelingprep.com/stable"

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


def _get(endpoint: str, params: dict = None) -> dict | list | None:
    p = {"apikey": _FMP_KEY}
    if params:
        p.update(params)
    try:
        r = _session.get(f"{_FMP_BASE}/{endpoint}", params=p, timeout=15)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict) and "Error Message" in data:
            return None
        return data
    except Exception:
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


def fetch_all(symbol: str) -> dict:
    symbol = symbol.upper().strip()

    def _fetch():
        quote = _get("quote", {"symbol": symbol})
        if not quote or not isinstance(quote, list) or not quote[0].get("price"):
            raise ValueError(f"Ticker '{symbol}' not found or has no price data.")
        q = quote[0]

        profile = _get("profile", {"symbol": symbol})
        p = profile[0] if profile and isinstance(profile, list) else {}

        metrics = _get("key-metrics-ttm", {"symbol": symbol})
        m = metrics[0] if metrics and isinstance(metrics, list) else {}

        ratios = _get("ratios-ttm", {"symbol": symbol})
        r = ratios[0] if ratios and isinstance(ratios, list) else {}

        income = _get("income-statement", {"symbol": symbol, "limit": 5})
        balance = _get("balance-sheet-statement", {"symbol": symbol, "limit": 5})
        cashflow = _get("cash-flow-statement", {"symbol": symbol, "limit": 5})

        hist_daily = _get("historical-price-eod/full", {"symbol": symbol, "timeseries": 365})
        hist_weekly = _get("historical-price-eod/full", {"symbol": symbol, "timeseries": 1825})

        news = _get("news/stock", {"symbols": symbol, "limit": 8})

        return {
            "symbol": symbol,
            "quote": q,
            "profile": p,
            "metrics": m,
            "ratios": r,
            "income": income or [],
            "balance": balance or [],
            "cashflow": cashflow or [],
            "hist_daily": hist_daily,
            "hist_weekly": hist_weekly,
            "news_raw": news or [],
        }

    return _cached(symbol, _fetch)


# ── Public helpers ─────────────────────────────────────────────────────────────

def get_price(data: dict) -> float | None:
    return _to_float(data["quote"].get("price"))


def get_prev_close(data: dict) -> float | None:
    return _to_float(data["quote"].get("previousClose"))


def get_market_cap(data: dict) -> float | None:
    return _to_float(data["quote"].get("marketCap"))


def get_kpis(data: dict) -> dict:
    q = data["quote"]
    m = data["metrics"]
    mc = get_market_cap(data)
    return {
        "market_cap": mc,
        "market_cap_fmt": _fmt_large(mc),
        "pe_ratio": _to_float(m.get("peRatioTTM")),
        "forward_pe": _to_float(m.get("forwardPETTM")),
        "peg_ratio": _to_float(m.get("pegRatioTTM")),
        "price_to_book": _to_float(m.get("pbRatioTTM")),
        "week_52_high": _to_float(q.get("yearHigh")),
        "week_52_low": _to_float(q.get("yearLow")),
        "volume": _to_float(q.get("volume")),
        "avg_volume": _to_float(q.get("avgVolume")),
        "dividend_yield": _to_float(m.get("dividendYieldTTM")),
        "beta": _to_float(m.get("betaTTM")),
        "eps_ttm": _to_float(m.get("epsTTM")),
        "shares_outstanding": _to_float(m.get("weightedAverageSharesDilutedTTM")),
    }


def get_fundamentals(data: dict) -> dict:
    m = data["metrics"]
    r = data["ratios"]
    inc = data["income"][0] if data["income"] else {}
    rev = _to_float(inc.get("revenue"))
    fcf = _to_float(m.get("freeCashFlowPerShareTTM"))
    return {
        "eps_ttm": _to_float(m.get("epsTTM")),
        "revenue_ttm": rev,
        "revenue_ttm_fmt": _fmt_large(rev),
        "revenue_growth_yoy": _to_float(r.get("revenueGrowthTTM")),
        "gross_margin": _to_float(r.get("grossProfitMarginTTM")),
        "operating_margin": _to_float(r.get("operatingProfitMarginTTM")),
        "net_margin": _to_float(r.get("netProfitMarginTTM")),
        "profit_margin": _to_float(r.get("netProfitMarginTTM")),
        "free_cash_flow": fcf,
        "free_cash_flow_fmt": _fmt_large(fcf),
        "debt_to_equity": _to_float(r.get("debtEquityRatioTTM")),
        "roe": _to_float(r.get("returnOnEquityTTM")),
        "roa": _to_float(r.get("returnOnAssetsTTM")),
        "earnings_growth": _to_float(r.get("epsGrowthTTM")),
        "dividend_yield": _to_float(m.get("dividendYieldTTM")),
        "shares_outstanding": _to_float(m.get("weightedAverageSharesDilutedTTM")),
        "book_value": _to_float(m.get("bookValuePerShareTTM")),
    }


def get_balance_sheet_metrics(data: dict) -> dict:
    bal = data["balance"]
    inc = data["income"]
    cf = data["cashflow"]
    m = data["metrics"]
    r = data["ratios"]

    def _col(rows, key):
        return [_to_float(row.get(key)) for row in rows if row.get(key) is not None]

    return {
        "current_assets": _col(bal, "totalCurrentAssets"),
        "current_liabilities": _col(bal, "totalCurrentLiabilities"),
        "long_term_debt": _col(bal, "longTermDebt"),
        "equity": _col(bal, "totalStockholdersEquity"),
        "net_income": _col(inc, "netIncome"),
        "da": _col(cf, "depreciationAndAmortization"),
        "capex": _col(cf, "capitalExpenditure"),
        "op_income": _col(inc, "operatingIncome"),
        "total_debt": _col(bal, "totalDebt"),
        "cash": _col(bal, "cashAndCashEquivalents"),
        "tax_rate": _to_float(r.get("effectiveTaxRateTTM")) or 0.21,
        "_info_proxy": {
            "earningsGrowth": r.get("epsGrowthTTM"),
            "revenueGrowth": r.get("revenueGrowthTTM"),
            "sharesOutstanding": m.get("weightedAverageSharesDilutedTTM"),
        },
    }


# ── Technical indicators ───────────────────────────────────────────────────────

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


def _parse_hist(raw) -> pd.DataFrame | None:
    if not raw or "historical" not in raw:
        return None
    rows = raw["historical"]
    if not rows:
        return None
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)
    df.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume",
    }, inplace=True)
    return df


def get_technicals(data: dict) -> dict:
    hist = _parse_hist(data.get("hist_daily"))
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
    def _serialize(raw, weekly: bool = False) -> list[dict]:
        df = _parse_hist(raw)
        if df is None or df.empty:
            return []
        if weekly:
            df = df[df["date"].dt.dayofweek == 0].copy()
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
        "weekly": _serialize(data.get("hist_weekly"), weekly=True),
    }


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
            publisher = item.get("site", "") or item.get("publisher", "")
            pub_date = (item.get("publishedDate", "") or "")[:10]
            url = item.get("url", "")
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
