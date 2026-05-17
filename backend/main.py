from dotenv import load_dotenv
load_dotenv()

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
from analysis.summarizer import generate_summary

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

    q = data["quote"]
    p = data["profile"]
    price = get_price(data)
    prev_close = get_prev_close(data)
    change = round(price - prev_close, 2) if price and prev_close else None
    change_pct = round(change / prev_close * 100, 2) if change and prev_close else None

    company_name = p.get("companyName") or q.get("name") or symbol
    kpis = get_kpis(data)
    fundamentals = get_fundamentals(data)

    summary = generate_summary(
        symbol=symbol,
        company_name=company_name,
        verdict=score_data["verdict"],
        confidence=score_data["confidence"],
        factors=score_data["factors"],
        rule_results=score_data["rule_results"],
        kpis=kpis,
        fundamentals=fundamentals,
    )

    return {
        "symbol": symbol,
        "company_name": company_name,
        "exchange": p.get("exchangeShortName", ""),
        "sector": p.get("sector", ""),
        "industry": p.get("industry", ""),
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": change_pct,
        "kpis": kpis,
        "fundamentals": fundamentals,
        "technicals": get_technicals(data),
        "history": get_history(data),
        "news": get_news(data),
        "summary": summary,
        **score_data,
    }
