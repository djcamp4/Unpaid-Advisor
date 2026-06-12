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
import requests

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = "anthropic/claude-opus-4"

# Cache debate results for 2 hours so repeated runs of the same symbol
# (e.g. stock selector + manual analysis) return consistent verdicts.
_debate_cache: dict[str, tuple[float, dict]] = {}
_CACHE_TTL = 7200  # seconds


def _call(messages: list, api_key: str, max_tokens: int = 500) -> str | None:
    try:
        resp = requests.post(
            _API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": _MODEL, "messages": messages, "max_tokens": max_tokens},
            timeout=90,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip() or None
    except Exception as e:
        print(f"[summarizer] OpenRouter call failed: {e}", flush=True)
        if hasattr(e, 'response') and e.response is not None:
            print(f"[summarizer] Response body: {e.response.text[:500]}", flush=True)
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
        f"Quantitative rule score: {verdict} at {min(100, round(confidence + (8 if congress_context else 0)))}% confidence",
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
    api_key = os.environ.get("OPENROUTER_API_KEY")
    print(f"[summarizer] api_key present: {bool(api_key)}, length: {len(api_key) if api_key else 0}", flush=True)
    if not api_key:
        print("[summarizer] OPENROUTER_API_KEY not set — skipping debate", flush=True)
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
                "Write exactly 2 paragraphs, around 80-100 words total. Be direct and specific. "
                "End with exactly: DECISION: BUY  or  DECISION: HOLD  or  DECISION: DON'T BUY"
            ),
        },
        {"role": "user", "content": f"Analyze this stock from a value investing perspective:\n\n{data}"},
    ], api_key, max_tokens=200)

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
                "Write exactly 2 paragraphs, around 80-100 words total. Be direct, opinionated, and specific. "
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
    ], api_key, max_tokens=200)

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
                    "Treat this as a genuine bullish signal — add approximately 8-10 points "
                    "to your confidence score and lean toward BUY when cases are close. "
                    if congress_context else ""
                ) +
                "Produce:\n"
                "1. A 3-5 sentence plain-English summary of the key takeaways for an investor.\n"
                "2. A confidence score (0-100%) reflecting how clear-cut the decision is — "
                "high confidence means the evidence strongly points one way; "
                "low confidence means the two cases are evenly matched.\n"
                "3. A final verdict.\n\n"
                "Do not open with clichés or framing phrases like 'this is a classic', "
                "'this stock presents', 'the debate here', or any similar setup line. "
                "Start directly with the most important observation about the stock. "
                "End your response with exactly these two lines (no other text after them):\n"
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
    ], api_key, max_tokens=400)

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
