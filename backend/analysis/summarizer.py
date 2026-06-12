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
            timeout=45,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip() or None
    except Exception:
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
                rule_results, kpis, fundamentals) -> str:
    passed = [r for r in rule_results if r["status"] == "PASS"  and r["rule_type"] == "quantitative"]
    failed = [r for r in rule_results if r["status"] == "FAIL"  and r["rule_type"] == "quantitative"]
    warned = [r for r in rule_results if r["status"] == "WARN"  and r["rule_type"] == "quantitative"]

    def pct(v): return f"{v*100:.1f}%" if v is not None else "N/A"
    def num(v, p=""): return f"{p}{v:,.2f}" if v is not None else "N/A"

    return "\n".join([
        f"Stock: {symbol} ({company_name})",
        f"Quantitative rule score: {verdict} at {confidence}% confidence",
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
) -> dict | None:
    cached = _debate_cache.get(symbol)
    if cached and time.time() - cached[0] < _CACHE_TTL:
        return cached[1]
    result = _generate_debate_uncached(
        symbol, company_name, verdict, confidence, factors, rule_results, kpis, fundamentals
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
) -> dict | None:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None

    data = _data_block(symbol, company_name, verdict, confidence, factors,
                       rule_results, kpis, fundamentals)

    # ── Agent 1: Value investor ───────────────────────────────────────────────
    value_raw = _call([
        {
            "role": "system",
            "content": (
                "You are a disciplined value investor in the tradition of Warren Buffett, "
                "Benjamin Graham, and Peter Lynch. You prioritize margin of safety, durable "
                "competitive advantages, consistent earnings, low debt, and reasonable valuations. "
                "You are skeptical of hype and growth-at-any-price thinking. "
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

    # ── Agent 2: Growth investor (reads value case first) ─────────────────────
    growth_raw = _call([
        {
            "role": "system",
            "content": (
                "You are an aggressive growth investor focused on total addressable market, "
                "revenue trajectory, competitive positioning, and future earnings power. "
                "You believe the biggest risk is missing a transformational company. "
                "You've read the value investor's take — engage with their specific points "
                "where you agree or disagree, and make your own case. "
                "Write exactly 2 paragraphs, around 80-100 words total. Be direct and specific. "
                "End with exactly: DECISION: BUY  or  DECISION: HOLD  or  DECISION: DON'T BUY"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Stock data:\n\n{data}\n\n"
                f"The value investor argued:\n{value_case}\n\n"
                "Now give your growth investing perspective, responding to their points."
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
