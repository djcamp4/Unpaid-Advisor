import time
import requests as _requests
import yfinance as yf
import pandas as pd
import numpy as np

_session = _requests.Session()
_session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
})

_cache: dict = {}
CACHE_TTL = 3600  # 1 hour


def _cached(key: str, fn):
    entry = _cache.get(key)
    if entry and time.time() - entry["ts"] < CACHE_TTL:
        return entry["data"]
    result = fn()
    _cache[key] = {"ts": time.time(), "data": result}
    return result


def _safe_row(df: pd.DataFrame, candidates: list[str]) -> pd.Series | None:
    if df is None or df.empty:
        return None
    for name in candidates:
        if name in df.index:
            return df.loc[name]
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
        ticker = yf.Ticker(symbol, session=_session)
        info = ticker.info or {}

        if not info.get("regularMarketPrice") and not info.get("currentPrice"):
            raise ValueError(f"Ticker '{symbol}' not found or has no price data.")

        income = _get_df(ticker, ["income_stmt", "financials"])
        balance = _get_df(ticker, ["balance_sheet"])
        cashflow = _get_df(ticker, ["cash_flow", "cashflow"])

        hist_daily = ticker.history(period="1y")
        hist_weekly = ticker.history(period="5y", interval="1wk")
        news_raw = ticker.news or []

        return {
            "symbol": symbol,
            "info": info,
            "income": income,
            "balance": balance,
            "cashflow": cashflow,
            "hist_daily": hist_daily,
            "hist_weekly": hist_weekly,
            "news_raw": news_raw,
        }

    return _cached(symbol, _fetch)


def _get_df(ticker, attrs: list[str]) -> pd.DataFrame | None:
    for attr in attrs:
        try:
            df = getattr(ticker, attr, None)
            if df is not None and not df.empty:
                return df
        except Exception:
            pass
    return None


# ── Public helpers used by scorer ─────────────────────────────────────────────

def get_price(data: dict) -> float | None:
    info = data["info"]
    return _to_float(info.get("currentPrice") or info.get("regularMarketPrice"))


def get_prev_close(data: dict) -> float | None:
    return _to_float(data["info"].get("previousClose"))


def get_market_cap(data: dict) -> float | None:
    return _to_float(data["info"].get("marketCap"))


def get_kpis(data: dict) -> dict:
    info = data["info"]
    mc = get_market_cap(data)
    return {
        "market_cap": mc,
        "market_cap_fmt": _fmt_large(mc),
        "pe_ratio": _to_float(info.get("trailingPE")),
        "forward_pe": _to_float(info.get("forwardPE")),
        "peg_ratio": _to_float(info.get("pegRatio")),
        "price_to_book": _to_float(info.get("priceToBook")),
        "week_52_high": _to_float(info.get("fiftyTwoWeekHigh")),
        "week_52_low": _to_float(info.get("fiftyTwoWeekLow")),
        "volume": _to_float(info.get("volume")),
        "avg_volume": _to_float(info.get("averageVolume")),
        "dividend_yield": _to_float(info.get("dividendYield")),
        "beta": _to_float(info.get("beta")),
        "eps_ttm": _to_float(info.get("trailingEps")),
        "forward_eps": _to_float(info.get("forwardEps")),
    }


def get_fundamentals(data: dict) -> dict:
    info = data["info"]
    income = data["income"]
    cashflow = data["cashflow"]

    rev = _to_float(info.get("totalRevenue"))
    fcf = _to_float(info.get("freeCashflow"))

    rev_growth = _to_float(info.get("revenueGrowth"))
    earnings_growth = _to_float(info.get("earningsGrowth"))

    return {
        "eps_ttm": _to_float(info.get("trailingEps")),
        "revenue_ttm": rev,
        "revenue_ttm_fmt": _fmt_large(rev),
        "revenue_growth_yoy": rev_growth,
        "gross_margin": _to_float(info.get("grossMargins")),
        "operating_margin": _to_float(info.get("operatingMargins")),
        "net_margin": _to_float(info.get("profitMargins")),
        "free_cash_flow": fcf,
        "free_cash_flow_fmt": _fmt_large(fcf),
        "debt_to_equity": _to_float(info.get("debtToEquity")),
        "roe": _to_float(info.get("returnOnEquity")),
        "roa": _to_float(info.get("returnOnAssets")),
        "earnings_growth": earnings_growth,
        "dividend_yield": _to_float(info.get("dividendYield")),
        "shares_outstanding": _to_float(info.get("sharesOutstanding")),
        "book_value": _to_float(info.get("bookValue")),
    }


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
    if pd.isna(m) or pd.isna(s):
        return None
    return bool(m > s)


def _bbands(close: pd.Series, length: int = 20, std: float = 2.0):
    sma = close.rolling(length).mean()
    dev = close.rolling(length).std()
    upper = (sma + std * dev).iloc[-1]
    lower = (sma - std * dev).iloc[-1]
    return (None, None) if pd.isna(upper) or pd.isna(lower) else (float(upper), float(lower))


def _sma(close: pd.Series, length: int) -> float | None:
    val = close.rolling(length).mean().iloc[-1]
    return None if pd.isna(val) else float(val)


def get_technicals(data: dict) -> dict:
    hist = data["hist_daily"]
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
    def _serialize(hist: pd.DataFrame) -> list[dict]:
        if hist is None or hist.empty:
            return []
        out = []
        for ts, row in hist.iterrows():
            try:
                out.append({
                    "date": ts.strftime("%Y-%m-%d"),
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
        "daily": _serialize(data["hist_daily"]),
        "weekly": _serialize(data["hist_weekly"]),
    }


POSITIVE_WORDS = {"surge", "soar", "beat", "record", "growth", "profit", "raise", "upgrade",
                  "strong", "bullish", "gain", "rally", "boost", "outperform", "exceed"}
NEGATIVE_WORDS = {"fall", "drop", "miss", "loss", "decline", "cut", "downgrade", "risk",
                  "warning", "concern", "weak", "bearish", "lawsuit", "probe", "fine", "restrict"}


def _sentiment(title: str) -> str:
    words = set(title.lower().split())
    pos = len(words & POSITIVE_WORDS)
    neg = len(words & NEGATIVE_WORDS)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def get_news(data: dict) -> list[dict]:
    out = []
    for item in (data["news_raw"] or [])[:8]:
        try:
            content = item.get("content", {})
            title = content.get("title", "") or item.get("title", "")
            publisher = content.get("provider", {}).get("displayName", "") or item.get("publisher", "")
            pub_date = content.get("pubDate", "") or ""
            url = content.get("canonicalUrl", {}).get("url", "") or item.get("link", "")
            if title:
                out.append({
                    "title": title,
                    "publisher": publisher,
                    "published_at": pub_date[:10] if pub_date else "",
                    "url": url,
                    "sentiment": _sentiment(title),
                })
        except Exception:
            pass
    return out


def get_balance_sheet_metrics(data: dict) -> dict:
    balance = data["balance"]
    income = data["income"]
    cashflow = data["cashflow"]
    info = data["info"]

    ca = _safe_row(balance, ["Current Assets", "TotalCurrentAssets"])
    cl = _safe_row(balance, ["Current Liabilities", "TotalCurrentLiabilities"])
    ltd = _safe_row(balance, ["Long Term Debt", "LongTermDebt", "Long-Term Debt"])
    equity = _safe_row(balance, ["Stockholders Equity", "Total Stockholder Equity",
                                  "StockholdersEquity", "CommonStockEquity"])
    net_income = _safe_row(income, ["Net Income", "NetIncome"])
    da = _safe_row(cashflow, ["Depreciation And Amortization", "DepreciationAndAmortization",
                               "Reconciled Depreciation", "Depreciation"])
    capex = _safe_row(cashflow, ["Capital Expenditure", "CapitalExpenditure",
                                  "Capital Expenditures", "CapEx"])
    op_income = _safe_row(income, ["Operating Income", "OperatingIncome", "EBIT"])
    total_debt = _safe_row(balance, ["Total Debt", "TotalDebt"])
    cash = _safe_row(balance, ["Cash And Cash Equivalents", "Cash", "CashAndCashEquivalents"])

    def _series_to_list(s) -> list[float | None]:
        if s is None:
            return []
        return [_to_float(v) for v in s.values]

    return {
        "current_assets": _series_to_list(ca),
        "current_liabilities": _series_to_list(cl),
        "long_term_debt": _series_to_list(ltd),
        "equity": _series_to_list(equity),
        "net_income": _series_to_list(net_income),
        "da": _series_to_list(da),
        "capex": _series_to_list(capex),
        "op_income": _series_to_list(op_income),
        "total_debt": _series_to_list(total_debt),
        "cash": _series_to_list(cash),
        "tax_rate": _to_float(info.get("effectiveTaxRate")) or 0.21,
    }
