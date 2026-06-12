from dotenv import load_dotenv
load_dotenv(override=True)

import asyncio
import json
import os

import httpx

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

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
from analysis.summarizer import generate_debate
from analysis.congress_trades import fetch_congressional_purchases

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

    det = data["details"]
    price = get_price(data)
    prev_close = get_prev_close(data)
    change = round(price - prev_close, 2) if price and prev_close else None
    change_pct = round(change / prev_close * 100, 2) if change and prev_close else None

    company_name = det.get("name") or symbol
    _exchange_map = {"XNAS": "NASDAQ", "XNYS": "NYSE", "XASE": "AMEX", "BATS": "BATS"}
    raw_exchange = det.get("primary_exchange", "")
    exchange = _exchange_map.get(raw_exchange, raw_exchange)
    sector = det.get("sic_description", "")

    kpis = get_kpis(data)
    fundamentals = get_fundamentals(data)

    debate = generate_debate(
        symbol=symbol,
        company_name=company_name,
        verdict=score_data["verdict"],
        confidence=score_data["confidence"],
        factors=score_data["factors"],
        rule_results=score_data["rule_results"],
        kpis=kpis,
        fundamentals=fundamentals,
    )

    # Judge's verdict and confidence override the rule engine when available
    verdict    = debate["verdict"]    if debate else score_data["verdict"]
    confidence = debate["confidence"] if debate else score_data["confidence"]

    return {
        "symbol": symbol,
        "company_name": company_name,
        "exchange": exchange,
        "sector": sector,
        "industry": sector,
        "price": price,
        "prev_close": prev_close,
        "change": change,
        "change_pct": change_pct,
        "kpis": kpis,
        "fundamentals": fundamentals,
        "technicals": get_technicals(data),
        "history": get_history(data),
        "news": get_news(data),
        "debate": debate,
        **score_data,
        "verdict": verdict,
        "confidence": confidence,
    }


@app.get("/debug-trades")
async def debug_trades():
    import httpx
    from datetime import datetime, timedelta

    api_key = os.getenv("FMP_API_KEY", "")
    if not api_key:
        return {"error": "FMP_API_KEY not set in backend/.env"}

    api_key = os.getenv("FMP_API_KEY", "")
    params = {"page": 0, "limit": 25, "apikey": api_key}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            sr = await client.get("https://financialmodelingprep.com/stable/senate-latest", params=params)
            hr = await client.get("https://financialmodelingprep.com/stable/house-latest", params=params)
        return {
            "senate_status": sr.status_code,
            "senate_records": len(sr.json()) if sr.status_code == 200 else 0,
            "senate_sample": sr.text[:300],
            "house_status": hr.status_code,
            "house_records": len(hr.json()) if hr.status_code == 200 else 0,
            "house_sample": hr.text[:300],
            "api_key_set": bool(api_key),
            "api_key_prefix": api_key[:6] if api_key else "none",
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/stock-selector")
async def stock_selector():
    """
    Stream SSE events while scanning recent congressional purchases.
    Runs each ticker through the full analysis pipeline and returns
    the first 5 where both the Value and Growth investors say BUY.
    """
    polygon_key = os.getenv("POLYGON_API_KEY", "")

    async def event_stream():
        def sse(obj: dict) -> str:
            return f"data: {json.dumps(obj)}\n\n"

        yield sse({"type": "status", "message": "Fetching congressional trades…"})

        try:
            tickers = await fetch_congressional_purchases(days=30)
        except Exception as e:
            yield sse({"type": "error", "message": f"Capitol Trades API error: {e}"})
            return

        if not tickers:
            yield sse({"type": "error", "message": "No congressional purchases found in the last 10 days."})
            return

        yield sse({"type": "status", "message": f"Found {len(tickers)} unique tickers. Screening…"})

        results: list[dict] = []
        checked = 0

        for ticker in tickers:
            if len(results) >= 5:
                break

            checked += 1
            yield sse({"type": "analyzing", "ticker": ticker, "found": len(results), "checked": checked})

            try:
                data = await asyncio.to_thread(fetch_all, ticker)
                score_data = await asyncio.to_thread(run_rules, data)

                det = data["details"]
                company_name = det.get("name") or ticker
                kpis = await asyncio.to_thread(get_kpis, data)
                fundamentals = await asyncio.to_thread(get_fundamentals, data)

                debate = await asyncio.to_thread(
                    lambda: generate_debate(
                        symbol=ticker,
                        company_name=company_name,
                        verdict=score_data["verdict"],
                        confidence=score_data["confidence"],
                        factors=score_data["factors"],
                        rule_results=score_data["rule_results"],
                        kpis=kpis,
                        fundamentals=fundamentals,
                    )
                )

                if not debate:
                    continue

                value_ok = (debate.get("value") or {}).get("decision", "").upper() == "BUY"
                growth_ok = (debate.get("growth") or {}).get("decision", "").upper() == "BUY"

                if value_ok and growth_ok:
                    branding = det.get("branding") or {}
                    icon_url = branding.get("icon_url")
                    if icon_url and polygon_key:
                        icon_url = f"{icon_url}?apiKey={polygon_key}"

                    stock = {
                        "symbol": ticker,
                        "company_name": company_name,
                        "icon_url": icon_url,
                        "verdict": debate.get("verdict"),
                        "confidence": debate.get("confidence"),
                    }
                    results.append(stock)
                    yield sse({"type": "found", "stock": stock, "total": len(results)})

            except Exception:
                continue  # skip tickers that error out

        yield sse({"type": "complete", "stocks": results})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
