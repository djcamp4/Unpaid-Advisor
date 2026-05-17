"""
Generates a natural language explanation of the stock verdict via OpenRouter.
Returns None gracefully if OPENROUTER_API_KEY is not set or the request fails.
"""

import os
import requests

_API_URL = "https://openrouter.ai/api/v1/chat/completions"
_MODEL = "anthropic/claude-opus-4"

_SYSTEM_PROMPT = (
    "You are a stock analysis assistant trained in the investment philosophies of "
    "Warren Buffett, Benjamin Graham, and Peter Lynch. "
    "Explain in 3–5 plain-English sentences why a stock received its BUY or DON'T BUY verdict. "
    "Be direct and specific — reference the actual numbers provided. "
    "Focus on the most important passing and failing rules. "
    "Speak to an intelligent investor who wants the honest rationale, not reassurance."
)


def generate_summary(
    symbol: str,
    company_name: str,
    verdict: str,
    confidence: float,
    factors: dict,
    rule_results: list[dict],
    kpis: dict,
    fundamentals: dict,
) -> str | None:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None

    passed = [r for r in rule_results if r["status"] == "PASS" and r["rule_type"] == "quantitative"]
    failed = [r for r in rule_results if r["status"] == "FAIL" and r["rule_type"] == "quantitative"]
    warned  = [r for r in rule_results if r["status"] == "WARN" and r["rule_type"] == "quantitative"]

    def fmt(rules: list[dict], limit: int = 5) -> str:
        return ", ".join(f"{r['name']} ({r['actual']})" for r in rules[:limit])

    rules_lines = []
    if passed:
        rules_lines.append(f"PASSING: {fmt(passed)}")
    if failed:
        rules_lines.append(f"FAILING: {fmt(failed)}")
    if warned:
        rules_lines.append(f"BORDERLINE: {fmt(warned, 3)}")

    metrics = []
    if kpis.get("pe_ratio"):
        metrics.append(f"P/E {kpis['pe_ratio']:.1f}×")
    if kpis.get("peg_ratio"):
        metrics.append(f"PEG {kpis['peg_ratio']:.2f}")
    if kpis.get("price_to_book"):
        metrics.append(f"P/B {kpis['price_to_book']:.2f}×")
    if fundamentals.get("roe"):
        metrics.append(f"ROE {fundamentals['roe']:.1%}")
    if fundamentals.get("profit_margin"):
        metrics.append(f"margin {fundamentals['profit_margin']:.1%}")

    user_content = (
        f"Stock: {company_name} ({symbol})\n"
        f"Verdict: {verdict} — Confidence: {confidence}%\n\n"
        f"Factor scores:\n"
        f"- Fundamentals: {factors['fundamentals']['score']}% ({factors['fundamentals']['label']})\n"
        f"- Growth:       {factors['growth']['score']}% ({factors['growth']['label']})\n"
        f"- Valuation:    {factors['valuation']['score']}% ({factors['valuation']['label']})\n"
        f"- Technical:    {factors['technical']['score']}% ({factors['technical']['label']})\n\n"
        f"Key metrics: {', '.join(metrics) if metrics else 'N/A'}\n\n"
        f"Rule results:\n" + "\n".join(rules_lines) + "\n\n"
        f"Explain in 3–5 sentences why this stock received a {verdict} verdict at {confidence}% confidence."
    )

    try:
        resp = requests.post(
            _API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": _MODEL,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user",   "content": user_content},
                ],
                "max_tokens": 400,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip() or None
    except Exception:
        return None
