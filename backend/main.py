from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from analysis.fetcher import (
    fetch_all,
    get_fundamentals,
    get_history,
    get_kpis,
    get_news,
    get_price,
    get_prev_close,
    get_technicals,
)
from analysis.scorer import run_rules

app = FastAPI(title="Unpaid Advisor API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/analyze/{symbol}")
def analyze(symbol: str):
    symbol = symbol.upper().strip()
    try:
        data = fetch_all(symbol)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {e}")

    try:
        score_data = run_rules(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scoring failed: {e}")

    info = data["info"]
    price = get_price(data)
    prev_close = get_prev_close(data)
    change = round(price - prev_close, 2) if price and prev_close else None
    change_pct = round(change / prev_close * 100, 2) if change and prev_close else None

    return {
        "symbol": symbol,
        "company_name": info.get("longName") or info.get("shortName", symbol),
        "exchange": info.get("exchange", ""),
        "sector": info.get("sector", ""),
        "industry": info.get("industry", ""),
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": change_pct,
        "kpis": get_kpis(data),
        "fundamentals": get_fundamentals(data),
        "technicals": get_technicals(data),
        "history": get_history(data),
        "news": get_news(data),
        **score_data,
    }
