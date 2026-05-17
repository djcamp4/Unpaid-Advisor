import time
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import numpy as np

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
        ticker = yf.Ticker(symbol)
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


def get_technicals(data: dict) -> dict:
    hist = data["hist_daily"]
    if hist is None or hist.empty:
        return {}

    close = hist["Close"]
    volume = hist["Volume"]

    hist.ta.rsi(length=14, append=True)
    hist.ta.macd(fast=12, slow=26, signal=9, append=True)
    hist.ta.bbands(length=20, std=2, append=True)
    hist.ta.sma(length=50, append=True)
    hist.ta.sma(length=200, append=True)

    price = float(close.iloc[-1])

    rsi_col = next((c for c in hist.columns if c.startswith("RSI_")), None)
    rsi = float(hist[rsi_col].iloc[-1]) if rsi_col and not pd.isna(hist[rsi_col].iloc[-1]) else None

    macd_col = next((c for c in hist.columns if c.startswith("MACD_") and "h" not in c.lower() and "s" not in c.lower()), None)
    macd_sig_col = next((c for c in hist.columns if c.startswith("MACDs_")), None)
    macd_bullish = None
    if macd_col and macd_sig_col:
        try:
            m = float(hist[macd_col].iloc[-1])
            s = float(hist[macd_sig_col].iloc[-1])
            macd_bullish = m > s
        except Exception:
            pass

    sma50_col = next((c for c in hist.columns if "SMA_50" in c), None)
    sma200_col = next((c for c in hist.columns if "SMA_200" in c), None)
    sma50 = float(hist[sma50_col].iloc[-1]) if sma50_col and not pd.isna(hist[sma50_col].iloc[-1]) else None
    sma200 = float(hist[sma200_col].iloc[-1]) if sma200_col and not pd.isna(hist[sma200_col].iloc[-1]) else None

    bb_upper_col = next((c for c in hist.columns if c.startswith("BBU_")), None)
    bb_lower_col = next((c for c in hist.columns if c.startswith("BBL_")), None)
    bb_position = None
    if bb_upper_col and bb_lower_col:
        try:
            bb_upper = float(hist[bb_upper_col].iloc[-1])
            bb_lower = float(hist[bb_lower_col].iloc[-1])
            pct = (price - bb_lower) / (bb_upper - bb_lower) if bb_upper != bb_lower else 0.5
            if pct > 0.8:
                bb_position = "upper"
            elif pct < 0.2:
                bb_position = "lower"
            else:
                bb_position = "mid"
        except Exception:
            pass

    avg_vol = float(volume.mean())
    cur_vol = float(volume.iloc[-1])
    vol_vs_avg = (cur_vol - avg_vol) / avg_vol if avg_vol else None

    # Simple support/resistance: recent 20-day low/high
    recent = close.tail(20)
    support = float(recent.min())
    resistance = float(recent.max())

    # Technical signal
    bullish_signals = sum([
        rsi is not None and 40 < rsi < 70,
        macd_bullish is True,
        sma50 is not None and price > sma50,
        sma200 is not None and price > sma200,
    ])
    if bullish_signals >= 3:
        signal = "BUY"
    elif bullish_signals <= 1:
        signal = "SELL"
    else:
        signal = "HOLD"

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
