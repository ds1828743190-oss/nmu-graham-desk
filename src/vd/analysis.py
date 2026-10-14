"""个股深度分析：把"指标 + 打分 + 排雷"转化为人类可读的判断。

三个核心产出
------------
1. **亮点 / 疑点**：自动生成，每条都附着具体数值（不说空话）；
2. **结论**：关注 / 观察 / 回避（规则透明，可推翻——但必须给出理由）；
3. **年报核查清单**：本模块最有价值的部分 ——
   财报数据只是"体温计"，真正的病因要去年报原文里找。
   每个财报异常点都会映射到【年报的具体章节 + 具体核查动作】，
   让"读年报"从漫无目的变成带着问题的定向核查。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import AppConfig
from . import metrics as metrics_mod
from . import scoring
from .screening import Flag, vet_company


@dataclass
class CheckItem:
    item: str          # 核查主题
    where: str         # 年报中的位置（章节/附注）
    how: str           # 具体核查动作
    based_on: str      # 触发该核查的财报依据


@dataclass
class CompanyAnalysis:
    symbol: str
    name: str
    industry: str
    verdict: str = "观察"                # 关注 / 观察 / 回避
    verdict_reason: str = ""
    highlights: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)
    checklist: list[CheckItem] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    scores: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)


# ---------------------------------------------------------------- 核查清单规则
# 每条规则：(触发条件, 核查主题, 年报位置, 核查动作, 依据模板)
_CHECKLIST_RULES: list[tuple] = [
    (lambda m: m.get("receivable_gap", 0) > 0.30,
     "应收账款增速远超营收",
     "年报「财务报表附注 → 应收账款」",
     "查看账龄结构：1 年以内占比是否明显下降、前五大欠款方集中度是否上升；"
     "同时核对「营业收入」附注中信用政策是否放宽（如延长账期）",
     "应收增速 − 营收增速 = {receivable_gap:+.0%}"),

    (lambda m: m.get("cash_debt_double"),
     "存贷双高异常",
     "年报「货币资金」附注 + 有息负债明细",
     "核查货币资金受限情况（质押/冻结/共管）；将利息收入与货币资金规模对照"
     "（大额存款却只有极低的利息收入，存款真实性存疑）",
     "货币资金/总资产 {monetary_ratio:.0%} 与有息负债/总资产 {int_debt_ratio:.0%} 同时超线"),

    (lambda m: m.get("goodwill_ratio", 0) > 0.30,
     "商誉减值风险",
     "年报「商誉」附注 + 商誉减值测试",
     "核查被并购标的的业绩承诺完成情况；关注减值测试关键假设"
     "（收入增长率、折现率）是否明显激进于收购时的预测",
     "商誉/净资产 = {goodwill_ratio:.0%}"),

    (lambda m: m.get("ocf_profit_ratio", 1) < 0.80,
     "利润含金量不足",
     "年报「现金流量表补充资料」（净利润→经营现金流的调节表）",
     "逐项检查调节项：是存货/应收/其他应收增加吃掉了现金，还是存在"
     "大额非付现收益（公允价值变动、投资收益）在支撑利润",
     "5年累计经营现金流/净利润 = {ocf_profit_ratio:.2f}"),

    (lambda m: m.get("inventory_ratio", 0) > 0.60,
     "存货积压风险",
     "年报「存货」附注",
     "核查存货构成与库龄/保质期；对比同行存货跌价准备计提比例"
     "（计提显著偏低可能是在藏风险）",
     "存货/营收 = {inventory_ratio:.0%}"),

    (lambda m: m.get("deducted_ratio", 1) < 0.70,
     "扣非利润占比偏低",
     "年报「非经常性损益明细表」",
     "盘点非经常性收益来源（卖资产/政府补助/金融资产收益）；"
     "评估各项的可持续性——靠一次性收益撑起来的利润不配估值溢价",
     "扣非净利/净利 = {deducted_ratio:.0%}"),

    (lambda m: m.get("debt_ratio", 0) > 0.70,
     "高杠杆偿债风险",
     "年报「有息负债」明细 + 偿债能力章节",
     "核查债务到期结构（一年内到期占比）、利息保障倍数；"
     "穿透表外负债与明股实债（少数股东权益异常高的间接信号）",
     "资产负债率 = {debt_ratio:.0%}"),

    (lambda m: m.get("roe_decline", 0) >= 2,
     "ROE 连续下滑",
     "年报「管理层讨论与分析（MD&A）」",
     "看管理层如何拆解盈利下滑：是行业周期性回落（可接受）还是核心竞争力削弱（危险）；"
     "用杜邦三因子（净利率×周转×杠杆）定位下滑来源",
     "ROE 连续 {roe_decline} 年下滑，5年平均 {roe_5y_avg:.1%}"),

    (lambda m: m.get("payout_ratio", 0) > 0.80,
     "分红率过高",
     "年报「利润分配方案」+ 资金计划",
     "判断是否可持续：对照资本开支计划与融资计划——"
     "一边大额分红一边大额融资的组合需要警惕（可能服务大股东而非公司）", 
     "分红/净利润 = {payout_ratio:.0%}"),

    (lambda m: m.get("dividend_years", 5) < 3,
     "分红连续性不足",
     "年报「利润分配」历史",
     "结合发展阶段解释：成长期留存利润再投资是合理的，"
     "但需核实留存资金是否真的投向了高回报项目（对照历年 ROE 变化）",
     "连续分红 {dividend_years} 年"),
]


# ---------------------------------------------------------------- 通用核查清单
# 与财务数据无关的"流程性"核查 —— 所有公司都应做的固定动作。
_BASE_CHECKLIST: list[tuple[str, str, str]] = [
    ("审计意见检查",
     "年报「审计报告」首页",
     "确认是否为【标准无保留意见】；出现'保留意见/无法表示意见/否定意见'直接一票否决；"
     "关注是否更换过会计师事务所（频繁换所是危险信号）"),
    ("关键审计事项（KAM）",
     "年报「审计报告 → 关键审计事项」",
     "会计师列出的 KAM 就是他们最不放心的科目（通常是收入确认、应收、存货、商誉等），"
     "逐条阅读审计师执行的程序与结论"),
    ("管理层讨论与分析（MD&A）",
     "年报「第三节 管理层讨论与分析」",
     "看管理层对行业趋势的判断与公司战略是否符合常识；对照财务数据是否互相印证"
     "（如声称'销售强劲'但应收暴增，就是自相矛盾）"),
    ("股东与质押情况",
     "年报「股东情况」章节 + 最新公告",
     "核查第一大股东质押比例（高质押 = 潜在平仓风险）；近一年是否存在大股东减持；"
     "董监高是否增持（内部人行为是最诚实的信号）"),
]


# ---------------------------------------------------------------- 亮点 / 疑点
def _find_highlights(m: dict) -> list[str]:
    h: list[str] = []

    if m.get("roe_5y_avg", 0) >= 0.15:
        h.append(f"长期盈利能力优秀：5 年平均 ROE {m['roe_5y_avg']:.1%}（>15% 线）")
    if m.get("ocf_profit_ratio", 0) >= 1.0:
        h.append(f"利润含金量高：5 年累计经营现金流是净利润的 "
                 f"{m['ocf_profit_ratio']:.2f} 倍，利润有真金白银背书")
    if m.get("gross_margin", 0) >= 0.35 and m.get("gross_margin_std", 1) < 0.03:
        h.append(f"毛利率 {m['gross_margin']:.1%} 且波动极小（标准差 {m['gross_margin_std']:.1%}），"
                 f"具备一定的定价权/护城河特征")
    if m.get("debt_ratio", 1) <= 0.40:
        h.append(f"资产负债表干净：资产负债率仅 {m['debt_ratio']:.1%}")
    if m.get("monetary_ratio", 0) > m.get("int_debt_ratio", 0) + 0.05:
        h.append("账上现金充裕且显著高于有息负债（财务弹性充足）")
    if m.get("dividend_yield", 0) >= 0.03:
        h.append(f"股息回报可观：股息率 {m['dividend_yield']:.1%}，超过无风险利率")
    if m.get("dividend_years", 0) >= 5:
        h.append("连续 5 年以上分红，股东回报意愿稳定")
    if m.get("revenue_cagr", 0) == m.get("revenue_cagr", 0) and m.get("revenue_cagr", 0) >= 0.15:
        h.append(f"成长性好：近 3 年营收 CAGR {m['revenue_cagr']:.1%}")
    if m.get("deducted_ratio", 0) >= 0.90:
        h.append(f"利润纯度高：扣非占比 {m['deducted_ratio']:.0%}，几乎全部来自主业")
    if not h:
        h.append("单项指标均未达到显著优秀水平（无突出亮点）")
    return h


def _find_concerns(m: dict, flags: list[Flag]) -> list[str]:
    c: list[str] = []
    for f in flags:
        c.append(str(f))
    # 补充非红旗但值得注意的点
    if m.get("roe_decline", 0) == 1:
        c.append("🟡 ROE 最近一年出现下滑，需观察是否延续")
    if m.get("growth_std", 0) > 0.15:
        c.append(f"🟡 营收增速波动较大（标准差 {m['growth_std']:.0%}），成长稳定性一般")
    if not c:
        c.append("未检测到显著风险信号（仍需人工阅读年报核实）")
    return c


def _dupont_read(m: dict) -> str:
    """杜邦拆解的一句话解读。"""
    margin = m.get("dupont_margin", float("nan"))
    turnover = m.get("dupont_turnover", float("nan"))
    leverage = m.get("dupont_leverage", float("nan"))
    if margin != margin or turnover != turnover or leverage != leverage:
        return "（数据不足，无法拆解）"
    if leverage > 3:
        driver = "杠杆驱动（ROE 质量需打折）"
    elif margin > 0.15:
        driver = "高净利率（定价权型）"
    elif turnover > 1.0:
        driver = "高周转（效率型）"
    else:
        driver = "均衡型（三项均不突出）"
    return (f"净利率 {margin:.1%} × 总资产周转 {turnover:.2f} × 权益乘数 {leverage:.2f}"
            f" → ROE {m.get('roe_latest', 0):.1%}。主要驱动：{driver}。")


# ---------------------------------------------------------------- 主函数
def analyze_company(symbol: str, financials: pd.DataFrame,
                    cfg: AppConfig) -> CompanyAnalysis:
    """对单家公司做完整分析。"""
    company = financials[financials["symbol"] == symbol]
    if company.empty:
        raise ValueError(f"数据集中没有 {symbol}")

    m = metrics_mod.compute_company_metrics(company, years=cfg.data.years)
    flags = vet_company(m, cfg)
    scores = scoring.score_company(m, cfg)

    reds = [f for f in flags if f.level == "red"]

    # 重大黄旗（单独出现也足以把"关注"降为"观察"——这些科目一旦出问题都不小）
    MATERIAL_RULES = {
        "资产负债率偏高", "商誉占净资产过高",
        "利润含金量偏低", "经营现金流连续为负",
    }
    has_material = any(f.rule in MATERIAL_RULES for f in flags)

    # ---- 结论 ----
    if reds:
        verdict = "回避"
        verdict_reason = "触发红线：" + "；".join(f.detail for f in reds)
    elif scores["grade"] in ("A", "B") and not has_material and len(flags) <= 1:
        verdict = "关注"
        verdict_reason = (f"综合评分 {scores['score_total']:.0f}（{scores['grade']} 级），"
                          f"无红线且无重大疑点（{len(flags)} 项一般性提示）")
    else:
        verdict = "观察"
        parts = []
        if scores["grade"] in ("C", "D"):
            parts.append(f"评分不足（{scores['score_total']:.0f}，{scores['grade']} 级）")
        if has_material:
            parts.append("存在重大疑点：" + "、".join(
                f.rule for f in flags if f.rule in MATERIAL_RULES))
        if len(flags) >= 2:
            parts.append(f"黄色疑点较多（{len(flags)} 项）")
        verdict_reason = "；".join(parts) or "处于可接受但不突出的中间地带"

    # ---- 年报核查清单（通用 + 定向）----
    checklist: list[CheckItem] = []
    for item, where, how in _BASE_CHECKLIST:
        checklist.append(CheckItem(
            item=item, where=where, how=how, based_on="通用核查（每家公司都做）",
        ))
    for cond, item, where, how, template in _CHECKLIST_RULES:
        try:
            if cond(m):
                checklist.append(CheckItem(
                    item=item, where=where, how=how,
                    based_on=template.format(**{
                        k: (v if v == v else 0) for k, v in m.items()
                    }),
                ))
        except (KeyError, ValueError):
            continue

    return CompanyAnalysis(
        symbol=symbol, name=m["name"], industry=m.get("industry", ""),
        verdict=verdict, verdict_reason=verdict_reason,
        highlights=_find_highlights(m),
        concerns=_find_concerns(m, flags),
        checklist=checklist,
        flags=flags, scores=scores, metrics=m,
    )


def dupont_note(m: dict) -> str:
    return _dupont_read(m)
