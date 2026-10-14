"""评分层：五维打分（0–100）→ 加权综合分 → 评级 A/B/C/D。

打分规则全部显式、阶梯化，任何一分都能回溯到具体指标数值 —— 
这是"判断逻辑"的完全透明化：你可以不认同某条规则，但你必须能看见它。
（改规则：修改下面的阶梯，或调整 config 里的权重。）
"""
from __future__ import annotations

from .config import AppConfig


def _ladder(value: float, steps: list[tuple[float, float]], default: float = 20.0) -> float:
    """阶梯打分：steps = [(阈值, 分数), ...] 从高到低，value >= 阈值取该分。"""
    if value != value:  # NaN
        return default
    for threshold, score in steps:
        if value >= threshold:
            return score
    return default


def _ladder_rev(value: float, steps: list[tuple[float, float]], default: float = 20.0) -> float:
    """反向阶梯：value <= 阈值取该分（用于"越低越好"的指标）。"""
    if value != value:
        return default
    for threshold, score in steps:
        if value <= threshold:
            return score
    return default


# ---------------------------------------------------------------- 分维度
def score_quality(m: dict) -> float:
    """盈利质量（ROE 水平 50% + ROE 稳定性 25% + 毛利率 25%）。

    关键修正：ROE 要按【杜邦来源】打折——高杠杆推起来的 ROE 质量低于
    高净利率/高周转驱动的 ROE（权益乘数 >3 打 8 折，>4 打 6 折）。
    """
    roe_level = _ladder(m.get("roe_5y_avg", 0), [
        (0.20, 100), (0.15, 85), (0.12, 70), (0.10, 55), (0.08, 40),
    ])
    lev = m.get("dupont_leverage", 2.0)
    if lev == lev and lev > 4.0:          # 负债率约 >75%
        roe_level *= 0.6
    elif lev == lev and lev > 3.0:        # 负债率约 >67%
        roe_level *= 0.8
    roe_stability = _ladder_rev(m.get("roe_decline", 0), [
        (0, 100), (1, 80), (2, 55), (3, 30),
    ])
    gross = _ladder(m.get("gross_margin", 0), [
        (0.50, 100), (0.35, 80), (0.25, 60), (0.15, 40),
    ])
    return 0.5 * roe_level + 0.25 * roe_stability + 0.25 * gross


def score_safety(m: dict) -> float:
    """资产安全：从 100 起扣分制（高杠杆为最重点扣分项）。"""
    s = 100.0
    if m.get("cash_debt_double"):
        s -= 35
    dr = m.get("debt_ratio", 0)
    if dr > 0.70:
        s -= 20 + (dr - 0.70) * 150     # 70% 以上：基础扣 20，每多 1pct 再扣 1.5
    ar = m.get("receivable_ratio", 0)
    if ar > 0.50:
        s -= (ar - 0.50) * 60           # 超线部分按比例扣
    gap = m.get("receivable_gap", 0)
    if gap > 0.30:
        s -= (gap - 0.30) * 50
    gw = m.get("goodwill_ratio", 0)
    if gw > 0.30:
        s -= (gw - 0.30) * 180          # 商誉减值可击穿净资产，重罚
    inv = m.get("inventory_ratio", 0)
    if inv > 0.60:
        s -= (inv - 0.60) * 40
    return max(s, 0.0)


def score_cashflow(m: dict) -> float:
    """现金流：利润含金量为主（70%）+ 自由现金流（30%）。

    数据缺失（NaN）取中性分 60 —— 不因"看不到"而惩罚公司。
    """
    ratio = m.get("ocf_profit_ratio", float("nan"))
    if ratio != ratio:
        base = 60.0
    else:
        base = _ladder(ratio, [
            (1.00, 100), (0.80, 80), (0.65, 60), (0.50, 40), (0.30, 20),
        ])
    if m.get("ocf_neg_years", 0) >= 2:
        base = min(base, 10)
    fcf_val = m.get("fcf_latest", float("nan"))
    if fcf_val != fcf_val:
        fcf_score = 60.0
    else:
        fcf_score = 100 if fcf_val > 0 else 30
    return 0.7 * base + 0.3 * fcf_score


def score_growth(m: dict) -> float:
    """成长（营收 CAGR 60% + 净利 CAGR 40%，叠加上下限保护）。"""
    rev = _ladder(m.get("revenue_cagr", float("nan")), [
        (0.25, 100), (0.15, 85), (0.10, 70), (0.05, 55), (0.0, 40),
    ], default=25)
    prof = _ladder(m.get("profit_cagr", float("nan")), [
        (0.25, 100), (0.15, 85), (0.10, 70), (0.05, 55), (0.0, 40),
    ], default=25)
    return 0.6 * rev + 0.4 * prof


def score_valuation(m: dict) -> float:
    """估值（PE 55% + 股息率 45%）。

    数据语义区分：
    - 字段缺失（NaN，如免费数据源无估值）→ 取中性分 60（不奖不罚）；
    - 亏损（PE ≤ 0）→ 30 分（估值维度给低分）；
    - 有值 → 阶梯打分。
    """
    pe = m.get("pe", float("nan"))
    if pe != pe:                               # NaN：数据缺失
        pe_score = 60.0
    elif pe <= 0:                              # 亏损
        pe_score = 30.0
    else:
        pe_score = _ladder_rev(pe, [
            (15, 100), (25, 80), (35, 60), (50, 40),
        ])
    dy = m.get("dividend_yield", float("nan"))
    if dy != dy:                               # 缺失 → 中性
        dy_score = 60.0
    else:
        dy_score = _ladder(dy, [
            (0.04, 100), (0.03, 85), (0.02, 65), (0.01, 45),
        ])
    return 0.55 * pe_score + 0.45 * dy_score


# ---------------------------------------------------------------- 综合
def score_company(m: dict, cfg: AppConfig) -> dict:
    """五维打分 → 综合分与评级。"""
    q = score_quality(m)
    s = score_safety(m)
    c = score_cashflow(m)
    g = score_growth(m)
    v = score_valuation(m)

    w = cfg.scoring.weights
    total = (
        w.get("quality", 0.30) * q
        + w.get("safety", 0.20) * s
        + w.get("cashflow", 0.20) * c
        + w.get("growth", 0.15) * g
        + w.get("valuation", 0.15) * v
    )
    sc = cfg.scoring
    grade = ("A" if total >= sc.grade_a else
             "B" if total >= sc.grade_b else
             "C" if total >= sc.grade_c else "D")
    return {
        "score_total": round(total, 1),
        "score_quality": round(q, 1),
        "score_safety": round(s, 1),
        "score_cashflow": round(c, 1),
        "score_growth": round(g, 1),
        "score_valuation": round(v, 1),
        "grade": grade,
    }


def explain_scores(m: dict, cfg: AppConfig) -> list[str]:
    """生成逐维度打分的解释行（报告用）。"""
    sc = score_company(m, cfg)
    lines = []
    lines.append(f"  盈利质量 {sc['score_quality']:5.1f} / 100 —— "
                 f"5年平均ROE {m.get('roe_5y_avg', 0):.1%}，毛利率 {m.get('gross_margin', 0):.1%}")
    lines.append(f"  资产安全 {sc['score_safety']:5.1f} / 100 —— "
                 f"负债率 {m.get('debt_ratio', 0):.1%}，应收/营收 {m.get('receivable_ratio', 0):.1%}，商誉/净资产 {m.get('goodwill_ratio', 0):.1%}")
    lines.append(f"  现金流   {sc['score_cashflow']:5.1f} / 100 —— "
                 f"5年累计含金量 {m.get('ocf_profit_ratio', 0):.2f}，自由现金流 {'正' if m.get('fcf_latest', 0) > 0 else '负'}")
    lines.append(f"  成长性   {sc['score_growth']:5.1f} / 100 —— "
                 f"营收CAGR {m.get('revenue_cagr', 0):.1%}，净利CAGR {m.get('profit_cagr', 0):.1%}")
    lines.append(f"  估值     {sc['score_valuation']:5.1f} / 100 —— "
                 f"PE {m.get('pe', 0):.1f}，股息率 {m.get('dividend_yield', 0):.2%}")
    return lines
