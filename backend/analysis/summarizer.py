"""
Three-step AI analysis via OpenRouter:
  1. Value agent  — Buffett/Graham/Lynch perspective + decision
  2. Growth agent — Aggressive growth perspective + decision (reads value case)
  3. Summary      — 3-5 sentence plain-English synthesis informed by both
Returns None gracefully if API key is missing or any call fails.
"""

import os
import requests

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = "anthropic/claude-opus-4"


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


def _clean(text: str, tag: str) -> str:
    """Remove the trailing decision line from agent output."""
    import re
    return re.sub(rf"{tag}.*$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()


def _data_block(symbol, company_name, verdict, confidence, factors,
                rule_results, kpis, fundamentals) -> str:
    passed = [r for r in rule_results if r["status"] == "PASS"  and r["rule_type"] == "quantitative"]
    failed = [r for r in rule_results if r["status"] == "FAIL"  and r["rule_type"] == "quantitative"]
    warned = [r for r in rule_results if r["status"] == "WARN"  and r["rule_type"] == "quantitative"]

    def pct(v): return f"{v*100:.1f}%" if v is not None else "N/A"
    def num(v, p=""): return f"{p}{v:,.2f}" if v is not None else "N/A"

    return "\n".join([
        f"Stock: {symbol} ({company_name})",
        f"Quantitative verdict: {verdict} at {confidence}% confidence",
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
                "Write 2-3 focused paragraphs analyzing this stock, referencing specific numbers "
                "from the rule results and metrics provided. "
                "End your response with exactly one line in this format: DECISION: BUY or DECISION: HOLD or DECISION: DON'T BUY"
            ),
        },
        {"role": "user", "content": f"Analyze this stock from a value investing perspective:\n\n{data}"},
    ], api_key, max_tokens=480)

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
                "Write 2-3 focused paragraphs referencing specific numbers. "
                "End your response with exactly one line in this format: DECISION: BUY or DECISION: HOLD or DECISION: DON'T BUY"
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
    ], api_key, max_tokens=480)

    if not growth_raw:
        return None
    growth_decision = _extract_decision(growth_raw, "DECISION:")
    growth_case = _clean(growth_raw, "DECISION:")

    # ── Agent 3: Plain-English summary informed by both ───────────────────────
    summary_raw = _call([
        {
            "role": "system",
            "content": (
                "You are a financial writer summarizing an investment analysis. "
                "Write 3-5 plain-English sentences that capture the most important takeaways "
                "about this stock, informed by both a value investor's perspective and a "
                "growth investor's perspective. Be direct, specific, and reference key numbers. "
                "Do not use bullet points. Do not recommend buying or selling. "
                "Just give an honest, balanced summary an investor can use."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Stock: {symbol} ({company_name})\n\n"
                f"Value investor's analysis:\n{value_case}\n\n"
                f"Growth investor's analysis:\n{growth_case}\n\n"
                "Write a 3-5 sentence plain-English summary of the key points."
            ),
        },
    ], api_key, max_tokens=300)

    return {
        "summary": summary_raw,
        "value":  {"case": value_case,  "decision": value_decision},
        "growth": {"case": growth_case, "decision": growth_decision},
    }
