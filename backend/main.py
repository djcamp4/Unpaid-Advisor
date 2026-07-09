from dotenv import load_dotenv
load_dotenv()  # Cloud Run env vars take precedence; .env used for local dev only

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
from analysis.congress_trades import (
    fetch_congressional_purchases,
    fetch_congressional_purchase_details,
    get_ticker_congressional_context_sync,
    format_congress_context,
)

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
async def analyze(symbol: str):
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

    congress_ctx = get_ticker_congressional_context_sync(symbol)
    congress_str = format_congress_context(congress_ctx)

    debate = generate_debate(
        symbol=symbol,
        company_name=company_name,
        verdict=score_data["verdict"],
        confidence=score_data["confidence"],
        factors=score_data["factors"],
        rule_results=score_data["rule_results"],
        kpis=kpis,
        fundamentals=fundamentals,
        congress_context=congress_str,
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
    api_key = os.getenv("FMP_API_KEY", "")
    if not api_key:
        return {"error": "FMP_API_KEY not set in backend/.env"}

    params = {"page": 0, "limit": 10, "apikey": api_key}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            sr = await client.get("https://financialmodelingprep.com/stable/senate-latest", params=params)
            hr = await client.get("https://financialmodelingprep.com/stable/house-latest", params=params)

        senate_data = sr.json() if sr.status_code == 200 else []
        house_data  = hr.json() if hr.status_code == 200 else []

        return {
            "api_key_set": True,
            "api_key_prefix": api_key[:6],
            "senate_status": sr.status_code,
            "senate_records": len(senate_data) if isinstance(senate_data, list) else "not-a-list",
            "senate_first_record": senate_data[0] if isinstance(senate_data, list) and senate_data else None,
            "senate_first_record_keys": list(senate_data[0].keys()) if isinstance(senate_data, list) and senate_data else [],
            "house_status": hr.status_code,
            "house_records": len(house_data) if isinstance(house_data, list) else "not-a-list",
            "house_first_record": house_data[0] if isinstance(house_data, list) and house_data else None,
            "house_first_record_keys": list(house_data[0].keys()) if isinstance(house_data, list) and house_data else [],
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
            trade_details = await fetch_congressional_purchase_details(days=60)
        except Exception as e:
            yield sse({"type": "error", "message": f"Capitol Trades API error: {e}"})
            return

        if not trade_details:
            yield sse({"type": "error", "message": "No congressional purchases found in the last 30 days."})
            return

        tickers = [t for t, d in sorted(trade_details.items(), key=lambda x: x[1]["max_amount"], reverse=True)]
        yield sse({"type": "status", "message": f"Found {len(tickers)} unique tickers. Screening…"})

        results: list[dict] = []
        checked = 0

        for ticker in tickers:
            if len(results) >= 5:
                break

            checked += 1
            yield sse({"type": "analyzing", "ticker": ticker, "found": len(results), "checked": checked})

            try:
                fetch_task = asyncio.create_task(asyncio.to_thread(fetch_all, ticker))
                while not fetch_task.done():
                    try:
                        await asyncio.wait_for(asyncio.shield(fetch_task), timeout=10)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                data = fetch_task.result()

                score_data = await asyncio.to_thread(run_rules, data)

                det = data["details"]
                company_name = det.get("name") or ticker
                kpis = await asyncio.to_thread(get_kpis, data)
                fundamentals = await asyncio.to_thread(get_fundamentals, data)

                # Run debate in background thread, sending keepalives every 10s
                # so the SSE connection doesn't drop during long OpenRouter calls
                congress_str = format_congress_context(trade_details.get(ticker))
                debate_task = asyncio.create_task(asyncio.to_thread(
                    lambda: generate_debate(
                        symbol=ticker,
                        company_name=company_name,
                        verdict=score_data["verdict"],
                        confidence=score_data["confidence"],
                        factors=score_data["factors"],
                        rule_results=score_data["rule_results"],
                        kpis=kpis,
                        fundamentals=fundamentals,
                        congress_context=congress_str,
                    )
                ))
                while not debate_task.done():
                    try:
                        await asyncio.wait_for(asyncio.shield(debate_task), timeout=10)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                debate = debate_task.result()

                if not debate:
                    continue

                judge_confidence = debate.get("confidence") or 0
                judge_verdict = (debate.get("verdict") or "").upper()
                value_decision = (debate.get("value") or {}).get("decision", "").upper()
                growth_decision = (debate.get("growth") or {}).get("decision", "").upper()
                agent_agrees = value_decision in ("BUY", "HOLD") or growth_decision in ("BUY", "HOLD")
                if judge_verdict == "BUY" and agent_agrees:
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
