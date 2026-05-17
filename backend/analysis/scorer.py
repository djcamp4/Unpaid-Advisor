"""
Applies the Buffett/Graham/Lynch rules to fetched stock data and produces
a BUY / DON'T BUY verdict with a confidence percentage.

Quantitative rules are auto-evaluated.
Qualitative rules are flagged as MANUAL (require human review).
"""

import json
import math
import os
from dataclasses import dataclass, field, asdict
from typing import Optional

from .fetcher import (
    get_balance_sheet_metrics,
    get_fundamentals,
    get_kpis,
    get_market_cap,
    get_price,
    get_technicals,
)

RULES_PATH = os.path.join(os.path.dirname(__file__), "..", "rules.json")

with open(RULES_PATH) as f:
    RULES_DATA = json.load(f)


@dataclass
class RuleResult:
    rule_id: str
    name: str
    source: str
    phase_id: int
    phase_name: str
    rule_type: str          # quantitative | qualitative
    status: str             # PASS | WARN | FAIL | MANUAL
    actual: str             # human-readable actual value
    threshold: str          # human-readable threshold
    detail: str             # one-line explanation
    weight: float = 1.0     # relative weight in confidence calc
    score: float = 0.0      # 0.0 / 0.5 / 1.0


def _r(rule_id: str, name: str, source: str, phase_id: int, phase_name: str,
       status: str, actual: str, threshold: str, detail: str,
       weight: float = 1.0) -> RuleResult:
    score_map = {"PASS": 1.0, "WARN": 0.5, "FAIL": 0.0, "MANUAL": 0.0}
    score = score_map.get(status, 0.0)
    return RuleResult(rule_id, name, source, phase_id, phase_name,
                      "quantitative", status, actual, threshold, detail, weight, score)


def _manual(rule_id: str, name: str, source: str, phase_id: int, phase_name: str,
            question: str) -> RuleResult:
    return RuleResult(rule_id, name, source, phase_id, phase_name,
                      "qualitative", "MANUAL", "—", "Human review required",
                      question, weight=0.0, score=0.0)


def _pct(v: Optional[float]) -> str:
    return f"{v*100:.1f}%" if v is not None else "N/A"


def _fmt(v: Optional[float], decimals: int = 2, prefix: str = "") -> str:
    if v is None:
        return "N/A"
    return f"{prefix}{v:,.{decimals}f}"


# ── DCF helpers ────────────────────────────────────────────────────────────────

def _dcf_intrinsic_value(owner_earnings: float, growth_rate: float,
                          discount_rate: float = 0.10,
                          terminal_growth: float = 0.03,
                          years: int = 10) -> float:
    growth_rate = min(max(growth_rate, 0.0), 0.25)  # cap 0-25%
    pv = 0.0
    for yr in range(1, years + 1):
        oe = owner_earnings * (1 + growth_rate) ** yr
        pv += oe / (1 + discount_rate) ** yr
    terminal_oe = owner_earnings * (1 + growth_rate) ** years
    terminal_value = terminal_oe * (1 + terminal_growth) / (discount_rate - terminal_growth)
    pv += terminal_value / (1 + discount_rate) ** years
    return pv


# ── Per-rule evaluators ────────────────────────────────────────────────────────

def _eval_fhs01(bm: dict, ph_name: str) -> RuleResult:
    """Current ratio >= 2.0"""
    ca_list = bm["current_assets"]
    cl_list = bm["current_liabilities"]
    if not ca_list or not cl_list or ca_list[0] is None or cl_list[0] is None or cl_list[0] == 0:
        return _r("FHS-01", "Current ratio minimum", "Benjamin Graham", 2, ph_name,
                  "FAIL", "N/A", ">= 2.0", "Could not retrieve current assets / liabilities")
    ratio = ca_list[0] / cl_list[0]
    if ratio >= 2.0:
        status = "PASS"
    elif ratio >= 1.5:
        status = "WARN"
    else:
        status = "FAIL"
    return _r("FHS-01", "Current ratio minimum", "Benjamin Graham", 2, ph_name,
              status, f"{ratio:.2f}×", ">= 2.0",
              f"Current ratio of {ratio:.2f} {'meets' if status=='PASS' else 'is below'} Graham's 2.0 floor",
              weight=1.2)


def _eval_fhs02(bm: dict, ph_name: str) -> RuleResult:
    """LT debt <= 2× working capital"""
    ca = bm["current_assets"][0] if bm["current_assets"] else None
    cl = bm["current_liabilities"][0] if bm["current_liabilities"] else None
    ltd = bm["long_term_debt"][0] if bm["long_term_debt"] else None
    if ca is None or cl is None:
        return _r("FHS-02", "Long-term debt ceiling", "Benjamin Graham", 2, ph_name,
                  "FAIL", "N/A", "<= 2× working capital", "Could not retrieve balance sheet data")
    wc = ca - cl
    if wc <= 0 or ltd is None:
        status = "FAIL" if ltd and ltd > 0 else "WARN"
        return _r("FHS-02", "Long-term debt ceiling", "Benjamin Graham", 2, ph_name,
                  status, f"WC: {wc:,.0f}", "<= 2× working capital",
                  "Working capital is non-positive — debt load is concerning", weight=1.2)
    ratio = ltd / wc
    status = "PASS" if ratio <= 2.0 else "FAIL"
    return _r("FHS-02", "Long-term debt ceiling", "Benjamin Graham", 2, ph_name,
              status, f"{ratio:.2f}× WC", "<= 2.0×",
              f"LT debt is {ratio:.2f}× working capital", weight=1.2)


def _eval_fhs03(bm: dict, ph_name: str) -> RuleResult:
    """Unbroken positive earnings"""
    ni_list = [v for v in bm["net_income"] if v is not None]
    if len(ni_list) < 2:
        return _r("FHS-03", "Unbroken earnings record", "Benjamin Graham", 2, ph_name,
                  "FAIL", "N/A", "Positive every year (10yr)", "Insufficient earnings history")
    all_positive = all(v > 0 for v in ni_list)
    years = len(ni_list)
    status = "PASS" if all_positive else "FAIL"
    detail = (f"All {years} available years show positive earnings"
              if all_positive else "One or more years had negative earnings")
    note = "" if years >= 5 else f" (only {years} years of data available)"
    return _r("FHS-03", "Unbroken earnings record", "Benjamin Graham", 2, ph_name,
              status, f"{years} yrs checked", "Positive every year (10yr)", detail + note)


def _eval_fhs04(bm: dict, ph_name: str) -> RuleResult:
    """ROE >= 15% for each of past 5 years"""
    ni = bm["net_income"]
    eq = bm["equity"]
    pairs = [(n, e) for n, e in zip(ni, eq) if n is not None and e is not None and e != 0]
    if not pairs:
        return _r("FHS-04", "ROE — sustained", "Warren Buffett", 2, ph_name,
                  "FAIL", "N/A", ">= 15% each year (5yr)", "Could not compute ROE")
    roes = [n / e for n, e in pairs]
    all_pass = all(r >= 0.15 for r in roes)
    worst = min(roes)
    status = "PASS" if all_pass else ("WARN" if worst >= 0.10 else "FAIL")
    return _r("FHS-04", "ROE — sustained", "Warren Buffett", 2, ph_name,
              status, f"Min ROE {_pct(worst)}", ">= 15% each year",
              f"ROEs: {', '.join(_pct(r) for r in roes[:4])}", weight=1.5)


def _eval_fhs05(bm: dict, ph_name: str) -> RuleResult:
    """Owner earnings positive and growing"""
    ni = bm["net_income"]
    da = bm["da"]
    capex = bm["capex"]
    years = min(len(ni), len(da), len(capex))
    if years < 2:
        return _r("FHS-05", "Owner earnings positive & growing", "Warren Buffett", 2, ph_name,
                  "FAIL", "N/A", "Positive & growing", "Insufficient cash flow data")
    oe_list = []
    for i in range(years):
        n = ni[i]; d = da[i] if da[i] else 0; c = capex[i] if capex[i] else 0
        if n is None:
            continue
        oe_list.append(n + abs(d) - abs(c))
    if not oe_list:
        return _r("FHS-05", "Owner earnings positive & growing", "Warren Buffett", 2, ph_name,
                  "FAIL", "N/A", "Positive & growing", "Could not compute owner earnings")
    positive = all(v > 0 for v in oe_list)
    growing = len(oe_list) >= 2 and oe_list[0] > oe_list[-1]
    if positive and growing:
        status = "PASS"
    elif positive:
        status = "WARN"
    else:
        status = "FAIL"
    from .fetcher import _fmt_large
    return _r("FHS-05", "Owner earnings positive & growing", "Warren Buffett", 2, ph_name,
              status, _fmt_large(oe_list[0]), "Positive & growing",
              f"Latest owner earnings: {_fmt_large(oe_list[0])}", weight=1.3)


def _eval_gsc01(kpis: dict, ph_name: str) -> RuleResult:
    """PEG ratio <= 1.0"""
    peg = kpis.get("peg_ratio")
    if peg is None:
        return _r("GSC-01", "PEG ratio target", "Peter Lynch", 3, ph_name,
                  "FAIL", "N/A", "<= 1.0 ideal", "PEG not available", weight=1.3)
    if peg <= 1.0:
        status = "PASS"
    elif peg <= 1.5:
        status = "WARN"
    elif peg <= 2.0:
        status = "WARN"
    else:
        status = "FAIL"
    return _r("GSC-01", "PEG ratio target", "Peter Lynch", 3, ph_name,
              status, f"{peg:.2f}", "<= 1.0 (ideal) / <= 1.5 (ok)",
              f"PEG of {peg:.2f} {'is cheap' if peg<1 else 'is elevated' if peg>1.5 else 'is acceptable'}",
              weight=1.3)


def _eval_gsc04(bm: dict, kpis: dict, ph_name: str) -> RuleResult:
    """ROIC >= 15%"""
    ni = bm["net_income"][0] if bm["net_income"] else None
    op = bm["op_income"][0] if bm["op_income"] else None
    eq = bm["equity"][0] if bm["equity"] else None
    td = bm["total_debt"][0] if bm["total_debt"] else 0
    cash = bm["cash"][0] if bm["cash"] else 0
    tax_rate = bm.get("tax_rate", 0.21)

    if op is None or eq is None:
        return _r("GSC-04", "High-return reinvestment (ROIC)", "Warren Buffett", 3, ph_name,
                  "FAIL", "N/A", ">= 15%", "Could not compute ROIC")
    nopat = op * (1 - tax_rate)
    invested_capital = eq + (td or 0) - (cash or 0)
    if invested_capital <= 0:
        return _r("GSC-04", "High-return reinvestment (ROIC)", "Warren Buffett", 3, ph_name,
                  "PASS", "N/A (neg debt)", ">= 15%", "Invested capital near zero — asset-light business", weight=1.2)
    roic = nopat / invested_capital
    if roic >= 0.15:
        status = "PASS"
    elif roic >= 0.10:
        status = "WARN"
    else:
        status = "FAIL"
    return _r("GSC-04", "High-return reinvestment (ROIC)", "Warren Buffett", 3, ph_name,
              status, _pct(roic), ">= 15%",
              f"ROIC of {_pct(roic)} {'exceeds' if roic>=0.15 else 'is below'} 15% threshold", weight=1.2)


def _eval_vms01(kpis: dict, ph_name: str) -> RuleResult:
    """P/E <= 15"""
    pe = kpis.get("pe_ratio")
    if pe is None or pe <= 0:
        return _r("VMS-01", "P/E ratio anchor", "Benjamin Graham", 4, ph_name,
                  "FAIL", "N/A", "<= 15", "P/E not available or negative", weight=1.5)
    if pe <= 15:
        status = "PASS"
    elif pe <= 20:
        status = "WARN"
    else:
        status = "FAIL"
    return _r("VMS-01", "P/E ratio anchor", "Benjamin Graham", 4, ph_name,
              status, f"{pe:.1f}×", "<= 15 (Graham ceiling)",
              f"P/E of {pe:.1f} {'is attractive' if pe<=15 else 'is elevated' if pe>25 else 'is above ceiling'}",
              weight=1.5)


def _eval_vms02(kpis: dict, ph_name: str) -> RuleResult:
    """P/B <= 1.5"""
    pb = kpis.get("price_to_book")
    if pb is None or pb <= 0:
        return _r("VMS-02", "Price-to-book check", "Benjamin Graham", 4, ph_name,
                  "FAIL", "N/A", "<= 1.5", "P/B not available")
    if pb <= 1.5:
        status = "PASS"
    elif pb <= 3.0:
        status = "WARN"
    else:
        status = "FAIL"
    return _r("VMS-02", "Price-to-book check", "Benjamin Graham", 4, ph_name,
              status, f"{pb:.2f}×", "<= 1.5 (Graham ceiling)",
              f"P/B of {pb:.2f} {'is below' if pb<=1.5 else 'exceeds'} Graham's ceiling")


def _eval_vms03_04_05(bm: dict, kpis: dict, data: dict, ph_name: str) -> tuple[RuleResult, RuleResult, RuleResult]:
    """DCF intrinsic value, margin of safety, expected return"""
    ni = bm["net_income"][0] if bm["net_income"] else None
    da_val = bm["da"][0] if bm["da"] else 0
    capex_val = bm["capex"][0] if bm["capex"] else 0
    mc = get_market_cap(data)
    price = get_price(data)
    shares = kpis.get("shares_outstanding")

    fail_dcf = _r("VMS-03", "DCF intrinsic value", "Warren Buffett", 4, ph_name,
                  "FAIL", "N/A", "Mkt cap < intrinsic value", "Could not compute DCF", weight=2.0)
    fail_mos = _r("VMS-04", "Margin of safety", "Benjamin Graham", 4, ph_name,
                  "FAIL", "N/A", ">= 25% discount", "Could not compute margin of safety", weight=2.0)
    fail_ret = _r("VMS-05", "Projected annual return", "Warren Buffett", 4, ph_name,
                  "FAIL", "N/A", ">= 10% annualized", "Could not compute expected return", weight=1.5)

    if ni is None or mc is None or mc <= 0:
        return fail_dcf, fail_mos, fail_ret

    owner_earnings = ni + abs(da_val or 0) - abs(capex_val or 0)
    if owner_earnings <= 0:
        return (
            _r("VMS-03", "DCF intrinsic value", "Warren Buffett", 4, ph_name,
               "FAIL", "Negative OE", "Mkt cap < intrinsic value",
               "Owner earnings are negative — DCF not meaningful", weight=2.0),
            fail_mos, fail_ret
        )

    # Growth rate: use earnings growth or revenue growth, fallback 5%
    info = bm.get("_info_proxy", {})
    eg = float(info.get("earningsGrowth") or 0)
    rg = float(info.get("revenueGrowth") or 0)
    growth_rate = max(min((eg + rg) / 2 if eg and rg else (eg or rg or 0.05), 0.25), 0.0)

    intrinsic_value = _dcf_intrinsic_value(owner_earnings, growth_rate)
    mos = (intrinsic_value - mc) / intrinsic_value if intrinsic_value > 0 else -99

    # VMS-03
    dcf_status = "PASS" if intrinsic_value > mc else "FAIL"
    from .fetcher import _fmt_large
    dcf = _r("VMS-03", "DCF intrinsic value", "Warren Buffett", 4, ph_name,
             dcf_status,
             f"IV: {_fmt_large(intrinsic_value)} / Mkt: {_fmt_large(mc)}",
             "Mkt cap < intrinsic value",
             f"DCF intrinsic value {_fmt_large(intrinsic_value)} vs market cap {_fmt_large(mc)}"
             f" (growth rate used: {growth_rate*100:.1f}%)", weight=2.0)

    # VMS-04
    if mos >= 0.33:
        mos_status = "PASS"
    elif mos >= 0.25:
        mos_status = "WARN"
    else:
        mos_status = "FAIL"
    mos_result = _r("VMS-04", "Margin of safety", "Benjamin Graham", 4, ph_name,
                    mos_status, f"{mos*100:.1f}%", ">= 25% (min) / >= 33% (preferred)",
                    f"Stock {'has a {:.0f}% margin of safety'.format(mos*100) if mos>0 else 'is overvalued by {:.0f}%'.format(abs(mos)*100)}",
                    weight=2.0)

    # VMS-05: projected 10-yr return
    intrinsic_10yr = _dcf_intrinsic_value(owner_earnings, growth_rate, years=10)
    if price and price > 0:
        per_share_iv = intrinsic_value / (shares or 1)
        expected_return = (per_share_iv / price) ** (1 / 10) - 1 if per_share_iv > 0 else -0.99
    else:
        expected_return = (intrinsic_value / mc) ** (1 / 10) - 1

    if expected_return >= 0.10:
        ret_status = "PASS"
    elif expected_return >= 0.08:
        ret_status = "WARN"
    else:
        ret_status = "FAIL"
    ret_result = _r("VMS-05", "Projected annual return", "Warren Buffett", 4, ph_name,
                    ret_status, f"{expected_return*100:.1f}%/yr", ">= 10% annualized",
                    f"Expected 10-yr annualized return of {expected_return*100:.1f}%", weight=1.5)

    return dcf, mos_result, ret_result


# ── Main scorer entry point ────────────────────────────────────────────────────

def run_rules(data: dict) -> dict:
    """Return verdict, confidence, all rule results, and factor scores."""
    kpis = get_kpis(data)
    bm = get_balance_sheet_metrics(data)
    technicals = get_technicals(data)

    results: list[RuleResult] = []

    # Helper to find phase name from rules JSON
    def ph_name(ph_id: int) -> str:
        for p in RULES_DATA["phases"]:
            if p["id"] == ph_id:
                return p["name"]
        return ""

    # ── Phase 1: qualitative (manual) ─────────────────────────────────────────
    p1 = ph_name(1)
    for rule in RULES_DATA["phases"][0]["rules"]:
        results.append(_manual(rule["id"], rule["name"], rule["source"], 1, p1, rule["question"]))

    # ── Phase 2: financial health ──────────────────────────────────────────────
    p2 = ph_name(2)
    results.append(_eval_fhs01(bm, p2))
    results.append(_eval_fhs02(bm, p2))
    results.append(_eval_fhs03(bm, p2))
    results.append(_eval_fhs04(bm, p2))
    results.append(_eval_fhs05(bm, p2))

    # ── Phase 3: growth ────────────────────────────────────────────────────────
    p3 = ph_name(3)
    results.append(_eval_gsc01(kpis, p3))
    # GSC-02, GSC-03 are qualitative
    for rule in [r for r in RULES_DATA["phases"][2]["rules"] if r["type"] == "qualitative"]:
        results.append(_manual(rule["id"], rule["name"], rule["source"], 3, p3, rule["question"]))
    results.append(_eval_gsc04(bm, kpis, p3))

    # ── Phase 4: valuation ─────────────────────────────────────────────────────
    p4 = ph_name(4)
    results.append(_eval_vms01(kpis, p4))
    results.append(_eval_vms02(kpis, p4))
    dcf, mos, ret = _eval_vms03_04_05(bm, kpis, data, p4)
    results.append(dcf)
    results.append(mos)
    results.append(ret)

    # ── Phase 5: qualitative ───────────────────────────────────────────────────
    p5 = ph_name(5)
    for rule in RULES_DATA["phases"][4]["rules"]:
        results.append(_manual(rule["id"], rule["name"], rule["source"], 5, p5,
                                rule.get("question", rule["name"])))

    # ── Confidence score (quantitative rules only) ─────────────────────────────
    quant = [r for r in results if r.rule_type == "quantitative"]
    total_weight = sum(r.weight for r in quant)
    earned_weight = sum(r.score * r.weight for r in quant)
    confidence = round((earned_weight / total_weight * 100) if total_weight else 0, 1)

    # Critical gates: if VMS-04 (margin of safety) or FHS-04 (ROE) hard-fail, cap confidence
    mos_result = next((r for r in results if r.rule_id == "VMS-04"), None)
    roe_result = next((r for r in results if r.rule_id == "FHS-04"), None)
    if mos_result and mos_result.status == "FAIL":
        confidence = min(confidence, 45.0)
    if roe_result and roe_result.status == "FAIL":
        confidence = min(confidence, 55.0)

    verdict = "BUY" if confidence >= 60.0 else "DON'T BUY"

    # ── Per-phase factor scores ────────────────────────────────────────────────
    def phase_score(ph_ids: list[int]) -> float:
        subset = [r for r in quant if r.phase_id in ph_ids]
        if not subset:
            return 0.0
        tw = sum(r.weight for r in subset)
        ew = sum(r.score * r.weight for r in subset)
        return round(ew / tw * 100, 1) if tw else 0.0

    # Technical score (independent of rules JSON — from indicators)
    tech_score = round(technicals.get("bullish_signals", 0) / 4 * 100, 1) if technicals else 0.0

    factors = {
        "fundamentals": {"score": phase_score([2]), "label": _score_label(phase_score([2]))},
        "growth":        {"score": phase_score([3]), "label": _score_label(phase_score([3]))},
        "valuation":     {"score": phase_score([4]), "label": _score_label(phase_score([4]))},
        "technical":     {"score": tech_score,       "label": _score_label(tech_score)},
    }

    return {
        "verdict": verdict,
        "confidence": confidence,
        "factors": factors,
        "rule_results": [asdict(r) for r in results],
    }


def _score_label(score: float) -> str:
    if score >= 80:
        return "Strong"
    if score >= 60:
        return "Good"
    if score >= 40:
        return "Mixed"
    if score >= 20:
        return "Weak"
    return "Poor"
