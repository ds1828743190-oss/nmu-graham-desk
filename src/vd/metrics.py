"""指标计算层：从财务长表提炼「判断用」的派生指标。

系统关注的指标体系（五组，对应价值分析的判断逻辑）：

    ① 盈利质量    ROE（杜邦拆解）、毛利率/净利率、扣非占比、ROE 趋势
    ② 资产安全    资产负债率、应收/营收、存货/营收、商誉/净资产、存贷双高
    ③ 现金流      利润含金量（5年累计 OCF/净利）、连续为负年数、自由现金流
    ④ 成长        营收/净利 CAGR、增长稳定性
    ⑤ 股东回报    股息率、分红连续性、分红率（payout）

每个指标的"为什么关注 + 健康阈值"见 METRIC_NOTES（报告会引用）。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------- 指标释义
METRIC_NOTES: dict[str, str] = {
    "roe_latest": "净资产收益率（最新一年）= 净利润/净资产。衡量股东每投入 1 元赚回多少；长期稳定 >15% 是优质公司的第一特征。",
    "roe_5y_avg": "近 5 年平均 ROE。单年数据易受扰动，长期均值才代表真实盈利能力。",
    "roe_decline": "ROE 连续下滑年数。趋势比绝对值更早发出信号。",
    "gross_margin": "毛利率 = 毛利/营收。反映产品定价权与商业模式优劣；关注其【稳定性】——长期稳在 30%+ 通常意味着某种护城河。",
    "net_margin": "净利率 = 净利/营收。与毛利率对照可看出费用管控能力。",
    "deducted_ratio": "扣非净利/净利。剔除非经常性损益（卖资产、补贴等）；<60% 说明利润含金量存疑。",
    "ocf_profit_ratio": "5年累计经营现金流/净利润 = 利润含金量。>0.8 健康；<0.5 警戒——利润可能只是纸面数字（康得新、康美案发前该比值长期恶化）。",
    "ocf_neg_years": "经营现金流连续为负年数。真实赚钱的生意不会长年收不回现金。",
    "fcf_latest": "自由现金流 = 经营现金流 − 资本开支。股东能真正拿到的钱。",
    "debt_ratio": "资产负债率。非金融行业 >70% 警戒；更要看有息负债（无息经营占款是良性负债）。",
    "cash_debt_double": "存贷双高：账上货币资金充裕却持续大额借款。正常经营不会一边存钱一边借高息债——该特征常见于财务造假案例（康美药业案发前：货币资金 341 亿 vs 有息负债约百亿）。",
    "receivable_ratio": "应收账款/营收。赊销比例，过高说明对下游议价弱 or 激进确认收入。",
    "receivable_gap": "应收增速 − 营收增速（百分点）。缺口持续扩大 = 靠赊销堆收入，回款质量恶化，是暴雷前置信号。",
    "goodwill_ratio": "商誉/净资产。并购溢价形成的资产，减值直接吞噬净资产；>30% 高度警惕（2018 商誉减值潮）。",
    "inventory_ratio": "存货/营收。积压风险与行业特性相关（白酒存货≠服装存货），重点看趋势突变。",
    "revenue_cagr": "营收复合增速（近 3 年）。成长性的第一指标，重点看质量（是否伴随现金流）。",
    "profit_cagr": "净利复合增速（近 3 年）。与营收增速对照：利润增速持续高于营收增速要么是提价能力、要么是费用粉饰。",
    "dividend_yield": "股息率 = 每股分红/股价。现金回报的最直接指标，与无风险利率对照。",
    "dividend_years": "连续分红年数。分红连续性比单年高低更能说明股东回报意愿。",
    "payout_ratio": "分红率 = 分红/净利润。合理区间通常 30%–70%；过高可能不可持续，过低要问为什么。",
    "pe": "市盈率 = 市值/净利。要与增速（PEG）、历史分位、同行对比才有意义。",
    "pb": "市净率。适合重资产/金融行业；与 ROE 联用（PB ≈ PE × ROE）。",
}


# ---------------------------------------------------------------- 工具
def _cagr(first: float, last: float, years: int) -> float:
    if years <= 0 or first <= 0 or last <= 0:
        return float("nan")
    return (last / first) ** (1 / years) - 1


def _consecutive_negative(series: pd.Series) -> int:
    """序列末尾连续为负的个数。"""
    cnt = 0
    for v in reversed(list(series)):
        if pd.notna(v) and v < 0:
            cnt += 1
        else:
            break
    return cnt


def _decline_years(series: pd.Series) -> int:
    """序列末尾连续下滑的个数（严格递减才算）。"""
    vals = [v for v in series if pd.notna(v)]
    cnt = 0
    for i in range(len(vals) - 1, 0, -1):
        if vals[i] < vals[i - 1]:
            cnt += 1
        else:
            break
    return cnt


# ---------------------------------------------------------------- 主函数
def compute_company_metrics(company: pd.DataFrame, years: int = 5) -> dict:
    """对一家公司（按年排序好的 DataFrame）计算全部派生指标。"""
    df = company.sort_values("year").tail(years).reset_index(drop=True)
    latest = df.iloc[-1]
    m: dict = {
        "symbol": latest["symbol"], "name": latest["name"],
        "industry": latest.get("industry", ""),
        "year_latest": int(latest["year"]),
        "n_years": len(df),
    }

    # ---- ① 盈利质量 ----
    m["roe_latest"] = float(latest["roe"])
    m["roe_5y_avg"] = float(df["roe"].mean())
    m["roe_decline"] = _decline_years(df["roe"])
    m["gross_margin"] = float(latest["gross_margin"])
    m["gross_margin_std"] = float(df["gross_margin"].std())  # 毛利率波动（护城河代理）
    m["net_margin"] = float(latest["net_margin"])
    m["deducted_ratio"] = (
        float(latest["deducted_net_profit"] / latest["net_profit"])
        if latest["net_profit"] else float("nan")
    )
    # 杜邦拆解（三因子）
    if latest["net_assets"] and latest["total_assets"]:
        m["dupont_margin"] = float(latest["net_profit"] / latest["revenue"]) \
            if latest["revenue"] else float("nan")
        m["dupont_turnover"] = float(latest["revenue"] / latest["total_assets"]) \
            if latest["total_assets"] else float("nan")
        m["dupont_leverage"] = float(latest["total_assets"] / latest["net_assets"]) \
            if latest["net_assets"] else float("nan")

    # ---- ② 资产安全 ----
    m["debt_ratio"] = float(latest["debt_ratio"])
    m["monetary_ratio"] = (
        float(latest["monetary_funds"] / latest["total_assets"])
        if latest["total_assets"] else float("nan")
    )
    m["int_debt_ratio"] = (
        float(latest["interest_bearing_debt"] / latest["total_assets"])
        if latest["total_assets"] else float("nan")
    )
    m["cash_debt_double"] = bool(
        m.get("monetary_ratio", 0) > 0.20 and m.get("int_debt_ratio", 0) > 0.20
    )
    m["receivable_ratio"] = (
        float(latest["accounts_receivable"] / latest["revenue"])
        if latest["revenue"] else float("nan")
    )
    if len(df) >= 2 and df.iloc[0]["revenue"] > 0 and df.iloc[0]["accounts_receivable"] > 0:
        ar_g = latest["accounts_receivable"] / df.iloc[0]["accounts_receivable"]
        rev_g = latest["revenue"] / df.iloc[0]["revenue"]
        n = len(df) - 1
        ar_cagr = ar_g ** (1 / n) - 1
        rev_cagr_full = rev_g ** (1 / n) - 1
        m["receivable_gap"] = float(ar_cagr - rev_cagr_full)
    else:
        m["receivable_gap"] = 0.0
    m["goodwill_ratio"] = (
        float(latest["goodwill"] / latest["net_assets"])
        if latest["net_assets"] else 0.0
    )
    m["inventory_ratio"] = (
        float(latest["inventory"] / latest["revenue"])
        if latest["revenue"] else float("nan")
    )

    # ---- ③ 现金流 ----
    # 注意：pandas 对全 NaN 列求和的返回值是 0.0（陷阱）——
    # 数据缺失必须显式识别为 NaN，绝不能当作"金额为零"参与判断。
    has_ocf = bool(df["ocf"].notna().any())
    has_profit = bool(df["net_profit"].notna().any())
    ocf_sum = float(df["ocf"].sum()) if has_ocf else float("nan")
    profit_sum = float(df["net_profit"].sum()) if has_profit else float("nan")
    m["ocf_sum"] = ocf_sum
    m["profit_sum"] = profit_sum
    if has_ocf and has_profit and abs(profit_sum) > 1e-9:
        m["ocf_profit_ratio"] = ocf_sum / profit_sum
    else:
        m["ocf_profit_ratio"] = float("nan")   # 数据不足 → 上层按"未知"处理
    m["ocf_neg_years"] = _consecutive_negative(df["ocf"])
    m["fcf_latest"] = float(latest["ocf"] - latest["capex"]) \
        if pd.notna(latest["ocf"]) and pd.notna(latest["capex"]) \
        else float("nan")
    m["ocf_latest"] = float(latest["ocf"])

    # ---- ④ 成长 ----
    n = min(3, len(df) - 1)
    if n >= 1:
        m["revenue_cagr"] = _cagr(float(df.iloc[-1 - n]["revenue"]),
                                  float(latest["revenue"]), n)
        m["profit_cagr"] = _cagr(float(df.iloc[-1 - n]["net_profit"]),
                                 float(latest["net_profit"]), n)
    else:
        m["revenue_cagr"] = m["profit_cagr"] = float("nan")
    growth_rates = df["revenue"].pct_change().dropna()
    m["growth_std"] = float(growth_rates.std()) if len(growth_rates) > 1 else 0.0

    # ---- ⑤ 股东回报 ----
    m["dividend_yield"] = float(latest["dividend_yield"])
    m["dividend_years"] = int(latest["dividend_years"])
    m["payout_ratio"] = (
        float(latest["dividend"] / latest["net_profit"])
        if latest["net_profit"] else 0.0
    )

    # ---- 估值 ----
    m["pe"] = float(latest["pe"])
    m["pb"] = float(latest["pb"])
    m["market_cap"] = float(latest["market_cap"])

    # ---- 其他 ----
    m["listed_years"] = int(latest["listed_years"])
    m["st_flag"] = bool(latest.get("st_flag", False))
    m["_type"] = latest.get("type", "")   # 仅演示对照用，不参与任何判断
    return m


def metrics_for_all(financials: pd.DataFrame, years: int = 5) -> pd.DataFrame:
    """对全部公司批量计算指标，返回一家一行的宽表。"""
    rows = []
    for symbol, g in financials.groupby("symbol"):
        rows.append(compute_company_metrics(g, years=years))
    return pd.DataFrame(rows)
