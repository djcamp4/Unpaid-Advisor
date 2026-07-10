"""
Three-agent investment analysis via OpenRouter:
  1. Value agent  — Buffett/Graham/Lynch perspective + decision
  2. Growth agent — Aggressive growth perspective + decision (reads value case)
  3. Judge        — Weighs both, produces final verdict, confidence %, and summary
Returns None gracefully if API key is missing or any call fails.
"""

import os
import re
import time
import anthropic

_MODEL = "claude-opus-4-8"

# Cache debate results for 2 hours so repeated runs of the same symbol
# (e.g. stock selector + manual analysis) return consistent verdicts.
_debate_cache: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 7200  # seconds

_MAX_RETRIES = 3
_RETRY_CAP = 20  # seconds


def _call(messages: list, api_key: str, max_tokens: int = 500) -> str | None:
    system = next((m["content"] for m in messages if m["role"] == "system"), "")
    user_messages = [m for m in messages if m["role"] != "system"]
    client = anthropic.Anthropic(api_key=api_key)

    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.messages.create(
                model=_MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=user_messages,
            )
            return resp.content[0].text.strip() or None
        except anthropic.RateLimitError:
            wait = min(5 * (attempt + 1), _RETRY_CAP)
            print(f"[summarizer] Rate limited, waiting {wait}s (attempt {attempt + 1}/{_MAX_RETRIES})", flush=True)
            if attempt < _MAX_RETRIES - 1:
                time.sleep(wait)
                continue
            print("[summarizer] Exhausted retries on rate limit", flush=True)
            return None
        except Exception as e:
            print(f"[summarizer] Anthropic call failed: {e}", flush=True)
            return None
    return None


def _extract_decision(text: str, tag: str) -> str:
    for line in text.upper().splitlines():
        if tag in line:
            if "DON'T BUY" in line or "DONT BUY" in line:
                return "DON'T BUY"
            if "BUY" in line:
                return "BUY"
            if "HOLD" in line:
                return "HOLD"
    return "HOLD"


def _extract_confidence(text: str) -> float:
    for line in text.upper().splitlines():
        if "CONFIDENCE:" in line:
            m = re.search(r'(\d+)', line)
            if m:
                return min(float(m.group(1)), 100.0)
    return 50.0


def _clean(text: str, *tags) -> str:
    for tag in tags:
        text = re.sub(rf"{tag}.*$", "", text, flags=re.IGNORECASE | re.MULTILINE)
    return text.strip()


def _data_block(symbol, company_name, verdict, confidence, factors,
                rule_results, kpis, fundamentals, congress_context=None) -> str:
    passed = [r for r in rule_results if r["status"] == "PASS"  and r["rule_type"] == "quantitative"]
    failed = [r for r in rule_results if r["status"] == "FAIL"  and r["rule_type"] == "quantitative"]
    warned = [r for r in rule_results if r["status"] == "WARN"  and r["rule_type"] == "quantitative"]

    def pct(v): return f"{v*100:.1f}%" if v is not None else "N/A"
    def num(v, p=""): return f"{p}{v:,.2f}" if v is not None else "N/A"

    return "\n".join([
        f"Stock: {symbol} ({company_name})",
        f"Quantitative rule score: {verdict} at {min(100, round(confidence + (15 if congress_context else 0)))}% confidence",
        f"Factor scores — Fundamentals: {factors['fundamentals']['score']}%  "
        f"Growth: {factors['growth']['score']}%  "
        f"Valuation: {factors['valuation']['score']}%  "
        f"Technical: {factors['technical']['score']}%",
        "",
        "Key metrics:",
        f"  P/E: {num(kpis.get('pe_ratio'))}  |  P/B: {num(kpis.get('price_to_book'))}  |  PEG: {num(kpis.get('peg_ratio'))}",
        f"  EPS: {num(kpis.get('eps_ttm'), '$')}  |  Market Cap: {kpis.get('market_cap_fmt', 'N/A')}",
        f"  Revenue growth: {pct(fundamentals.get('revenue_growth_yoy'))}  |  Earnings growth: {pct(fundamentals.get('earnings_growth'))}",
        f"  Gross margin: {pct(fundamentals.get('gross_margin'))}  |  Net margin: {pct(fundamentals.get('net_margin'))}",
        f"  ROE: {pct(fundamentals.get('roe'))}  |  Debt/Equity: {num(fundamentals.get('debt_to_equity'))}",
        f"  FCF/share: {num(fundamentals.get('free_cash_flow'), '$')}",
        "",
        f"Rules passed ({len(passed)}): " + (", ".join(r["name"] for r in passed[:6]) or "none"),
        f"Rules failed ({len(failed)}): " + (", ".join(r["name"] for r in failed[:6]) or "none"),
        f"Rules warned ({len(warned)}): " + (", ".join(r["name"] for r in warned[:4]) or "none"),
        *(
            [f"\nCongressional signal: {congress_context}",
             "Note: Members of Congress sometimes act on asymmetric or early-access information."]
            if congress_context else []
        ),
    ])


def generate_debate(
    symbol: str,
    company_name: str,
    verdict: str,
    confidence: float,
    factors: dict,
    rule_results: list,
    kpis: dict,
    fundamentals: dict,
    congress_context: str | None = None,
) -> dict | None:
    cached = _debate_cache.get(symbol)
    if cached and time.time() - cached[0] < _CACHE_TTL:
        return cached[1]
    result = _generate_debate_uncached(
        symbol, company_name, verdict, confidence, factors, rule_results, kpis, fundamentals,
        congress_context=congress_context,
    )
    if result:
        _debate_cache[symbol] = (time.time(), result)
    return result


# ── Stock selector: pitch + ranking flow ─────────────────────────────────────

_pitches_cache: dict[str, tuple[float, dict]] = {}


def generate_stock_pitches(
    symbol: str,
    company_name: str,
    verdict: str,
    confidence: float,
    factors: dict,
    rule_results: list,
    kpis: dict,
    fundamentals: dict,
    congress_context: str | None = None,
) -> dict | None:
    """
    Have value and growth investors argue FOR this stock.
    Returns {value_case, growth_case} or None on failure.
    Used by the stock selector ranking flow.
    """
    cached = _pitches_cache.get(symbol)
    if cached and time.time() - cached[0] < _CACHE_TTL:
        return cached[1]

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    data = _data_block(symbol, company_name, verdict, confidence, factors,
                       rule_results, kpis, fundamentals, congress_context)

    congress_note = (
        "A member of Congress recently purchased this stock. "
        "Treat this as a meaningful bullish signal — congressional members sometimes "
        "act on early or asymmetric information. Give this genuine weight. "
        if congress_context else ""
    )

    value_raw = _call([
        {
            "role": "system",
            "content": (
                "You are a disciplined value investor in the tradition of Warren Buffett, "
                "Benjamin Graham, and Peter Lynch. You focus on margin of safety, durable "
                "competitive advantages, consistent earnings, low debt, and reasonable valuations. "
                "Some metrics may show N/A — ignore missing fields and evaluate on what is available. "
                + congress_note +
                "Make the strongest investment case FOR this stock from a value perspective. "
                "Write exactly 2 paragraphs, under 120 words total. Be direct and specific. "
                "Always end with a complete sentence."
            ),
        },
        {"role": "user", "content": f"Make the value investing case for this stock:\n\n{data}"},
    ], api_key, max_tokens=350)

    if not value_raw:
        return None

    growth_raw = _call([
        {
            "role": "system",
            "content": (
                "You are an aggressive growth investor focused on revenue trajectory, "
                "total addressable market, competitive moat, and future earnings power. "
                "Some metrics may show N/A — ignore missing fields and evaluate on what is available. "
                + congress_note +
                "Make the strongest investment case FOR this stock from a growth perspective. "
                "Write exactly 2 paragraphs, under 120 words total. Be direct and specific. "
                "Always end with a complete sentence."
            ),
        },
        {"role": "user", "content": f"Make the growth investing case for this stock:\n\n{data}"},
    ], api_key, max_tokens=350)

    if not growth_raw:
        return None

    result = {"value_case": value_raw, "growth_case": growth_raw}
    _pitches_cache[symbol] = (time.time(), result)
    return result


def rank_stocks(candidates: list[dict]) -> list[dict]:
    """
    Judge selects the top 5 stocks from candidates.
    Each candidate needs: ticker, company_name, rule_score, score_data (with factors),
    value_case, growth_case, and optionally congress_context.
    Returns [{symbol, rank, confidence, rationale}] sorted rank 1–5.
    Falls back to rule score order if the API call fails.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    def fallback():
        return [
            {"symbol": c["ticker"], "rank": i + 1, "confidence": round(c.get("rule_score", 50)), "rationale": ""}
            for i, c in enumerate(candidates[:5])
        ]

    if not api_key or not candidates:
        return fallback()

    entries = []
    for i, c in enumerate(candidates, 1):
        ticker = c["ticker"]
        company = c.get("company_name", ticker)
        factors = c.get("score_data", {}).get("factors", {})
        rule_score = round(c.get("rule_score", 0))
        ctx = c.get("congress_context") or ""

        entry = (
            f"Stock {i}: {ticker} ({company})\n"
            f"Rule score: {rule_score}% | "
            f"Fundamentals: {factors.get('fundamentals', {}).get('score', '?')}% | "
            f"Growth: {factors.get('growth', {}).get('score', '?')}% | "
            f"Valuation: {factors.get('valuation', {}).get('score', '?')}% | "
            f"Technical: {factors.get('technical', {}).get('score', '?')}%"
            + (f"\nCongressional purchase: {ctx}" if ctx else "") + "\n"
            f"Value case: {c.get('value_case', 'N/A')}\n"
            f"Growth case: {c.get('growth_case', 'N/A')}"
        )
        entries.append(entry)

    n = len(candidates)
    judge_raw = _call([
        {
            "role": "system",
            "content": (
                "You are a senior investment analyst making final stock picks from a pre-screened list. "
                "Value and growth investors have argued the case FOR each stock. "
                "Select the 5 BEST stocks and rank them 1 (best) through 5. "
                "Favor strong rule scores, compelling investment cases, and congressional purchase signals. "
                "\n\n"
                "Use EXACTLY this format — 5 entries, no other text:\n\n"
                "#1 TICKER | XX%\n"
                "2-3 sentence rationale.\n\n"
                "#2 TICKER | XX%\n"
                "2-3 sentence rationale.\n\n"
                "#3 TICKER | XX%\n"
                "2-3 sentence rationale.\n\n"
                "#4 TICKER | XX%\n"
                "2-3 sentence rationale.\n\n"
                "#5 TICKER | XX%\n"
                "2-3 sentence rationale."
            ),
        },
        {
            "role": "user",
            "content": f"From these {n} candidate stocks, select your top 5:\n\n" + "\n\n".join(entries),
        },
    ], api_key, max_tokens=700)

    if not judge_raw:
        print("[summarizer] rank_stocks: judge call failed, using rule score fallback", flush=True)
        return fallback()

    pattern = re.compile(r'#(\d)\s+([A-Z]{1,5})\s*\|\s*(\d+)%[^\n]*\n(.*?)(?=\n#\d|\Z)', re.DOTALL)
    matches = pattern.findall(judge_raw)

    ticker_set = {c["ticker"] for c in candidates}
    results: list[dict] = []
    seen: set[str] = set()

    for rank_str, ticker, conf_str, rationale in matches:
        ticker = ticker.strip().upper()
        if ticker not in ticker_set or ticker in seen:
            continue
        seen.add(ticker)
        results.append({
            "symbol": ticker,
            "rank": int(rank_str),
            "confidence": min(float(conf_str), 100.0),
            "rationale": rationale.strip(),
        })

    for c in candidates:
        if len(results) >= 5:
            break
        if c["ticker"] not in seen:
            seen.add(c["ticker"])
            results.append({
                "symbol": c["ticker"],
                "rank": len(results) + 1,
                "confidence": round(c.get("rule_score", 50)),
                "rationale": "",
            })

    return results[:5]


def _generate_debate_uncached(
    symbol: str,
    company_name: str,
    verdict: str,
    confidence: float,
    factors: dict,
    rule_results: list,
    kpis: dict,
    fundamentals: dict,
    congress_context: str | None = None,
) -> dict | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    print(f"[summarizer] api_key present: {bool(api_key)}, length: {len(api_key) if api_key else 0}", flush=True)
    if not api_key:
        print("[summarizer] ANTHROPIC_API_KEY not set — skipping debate", flush=True)
        return None

    data = _data_block(symbol, company_name, verdict, confidence, factors,
                       rule_results, kpis, fundamentals, congress_context)

    # ── Agent 1: Value investor ───────────────────────────────────────────────
    value_raw = _call([
        {
            "role": "system",
            "content": (
                "You are a disciplined value investor in the tradition of Warren Buffett, "
                "Benjamin Graham, and Peter Lynch. You prioritize margin of safety, durable "
                "competitive advantages, consistent earnings, low debt, and reasonable valuations. "
                "You are skeptical of hype and growth-at-any-price thinking. "
                "Some metrics may show N/A — ignore missing fields and evaluate based on what is available. "
                "Never cite missing data as a reason to oppose a stock. "
                + (
                    "A member of Congress recently purchased this stock. Even as a value investor, "
                    "treat this as a meaningful signal — congressional members sometimes act on "
                    "early or asymmetric information not yet reflected in public metrics. "
                    "Give this signal genuine weight alongside the fundamentals. "
                    if congress_context else ""
                ) +
                "Write exactly 2 paragraphs. Stay under 120 words total — always end your last "
                "paragraph with a complete sentence before the decision tag. "
                "End with exactly: DECISION: BUY  or  DECISION: HOLD  or  DECISION: DON'T BUY"
            ),
        },
        {"role": "user", "content": f"Analyze this stock from a value investing perspective:\n\n{data}"},
    ], api_key, max_tokens=400)

    if not value_raw:
        return None
    value_decision = _extract_decision(value_raw, "DECISION:")
    value_case = _clean(value_raw, "DECISION:")

    # ── Agent 2: Growth investor (independent view, then challenges value case) ─
    growth_raw = _call([
        {
            "role": "system",
            "content": (
                "You are an aggressive growth investor focused exclusively on total addressable market, "
                "revenue trajectory, competitive moat, and future earnings power. "
                "Your framework: revenue growth rate, market share trajectory, and category leadership matter "
                "far more than current P/E or book value. You believe the biggest risk is missing a "
                "transformational company. Value metrics are largely irrelevant to your thesis. "
                "Some metrics may show N/A — ignore missing fields and evaluate based on what is available. "
                "Never cite missing data as a reason to oppose a stock. "
                + (
                    "A member of Congress recently purchased this stock. Treat this as a meaningful "
                    "bullish signal — congressional members often act on early or asymmetric information. "
                    "Give this signal genuine weight in your thesis. "
                    if congress_context else ""
                ) +
                "Evaluate the stock FIRST on growth fundamentals, THEN briefly note where you disagree "
                "with the value investor's framing if they were too conservative. "
                "Write exactly 2 paragraphs. Stay under 120 words total — always end your last "
                "paragraph with a complete sentence before the decision tag. "
                "Be direct, opinionated, and specific. "
                "Your DECISION must match your analysis: if your paragraphs are bullish, you MUST say BUY. "
                "Only say HOLD if you identified a specific concern that gives you genuine pause. "
                "A growth investor who writes a positive case and then says HOLD is contradicting themselves. "
                "End with exactly: DECISION: BUY  or  DECISION: HOLD  or  DECISION: DON'T BUY"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Stock data:\n\n{data}\n\n"
                f"The value investor's take (which you may push back on):\n{value_case}\n\n"
                "Give your independent growth investing verdict. Lead with growth metrics, not value metrics."
            ),
        },
    ], api_key, max_tokens=400)

    if not growth_raw:
        return None
    growth_decision = _extract_decision(growth_raw, "DECISION:")
    growth_case = _clean(growth_raw, "DECISION:")

    # ── Agent 3: Judge — produces the final verdict and confidence ────────────
    judge_raw = _call([
        {
            "role": "system",
            "content": (
                "You are a senior investment analyst and the final decision-maker. "
                "A value investor and a growth investor have both made their cases. "
                "Weigh their arguments carefully — neither perspective automatically wins. "
                + (
                    "IMPORTANT: The stock data shows a recent congressional purchase. "
                    "Members of Congress sometimes act on early or asymmetric information. "
                    "Treat this as a genuine bullish signal — add approximately 15 points "
                    "to your confidence score and lean toward BUY when cases are close. "
                    if congress_context else ""
                ) +
                "Produce a plain-English summary of 3-5 sentences (under 150 words). "
                "Do not open with clichés or framing phrases like 'this is a classic', "
                "'this stock presents', 'the debate here', or any similar setup line. "
                "Start directly with the most important observation about the stock. "
                "Always end your summary with a complete sentence. "
                "Then append exactly these two lines (no other text after them):\n"
                "CONFIDENCE: XX%\n"
                "FINAL VERDICT: BUY  or  FINAL VERDICT: HOLD  or  FINAL VERDICT: DON'T BUY"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Stock: {symbol} ({company_name})\n\n"
                f"VALUE INVESTOR ({value_decision}):\n{value_case}\n\n"
                f"GROWTH INVESTOR ({growth_decision}):\n{growth_case}\n\n"
                "Weigh both cases and deliver your verdict."
            ),
        },
    ], api_key, max_tokens=700)

    if not judge_raw:
        return None

    final_verdict = _extract_decision(judge_raw, "FINAL VERDICT:")
    final_confidence = _extract_confidence(judge_raw)
    summary = _clean(judge_raw, "CONFIDENCE:", "FINAL VERDICT:")

    return {
        "verdict":    final_verdict,
        "confidence": final_confidence,
        "summary":    summary,
        "value":  {"case": value_case,  "decision": value_decision},
        "growth": {"case": growth_case, "decision": growth_decision},
    }
