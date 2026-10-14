"""筛选漏斗：从全市场到候选池的五层过滤 + 排雷引擎。

漏斗设计（每层都有明确的淘汰理由，结果可审计）
-----------------------------------------------
    ① 硬性初筛     ST / 上市年限 / 市值        （"不碰什么"的底线）
    ② 盈利质量筛   ROE 最新 + 5 年均值          （持续赚钱的能力）
    ③ 排雷筛       红旗规则 → 红灯剔除、黄灯标注 （"不亏大钱"的保障）
    ④ 估值筛       PE / 股息率                  （价格合理性）
    ⑤ 打分排序     五维评分 → 评级 A/B/C/D      （优中选优）

排雷规则（红旗）逐条对应 docs/METRICS.md「排雷清单」，
每条规则输出【触发值 vs 阈值】，让剔除决定可解释、可复核。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import AppConfig
from . import metrics as metrics_mod


# ---------------------------------------------------------------- 结构
@dataclass
class Flag:
    level: str      # "red" | "yellow"
    rule: str       # 规则短名
    detail: str     # 触发值 vs 阈值

    def __str__(self) -> str:
        icon = "🔴" if self.level == "red" else "🟡"
        return f"{icon} [{self.rule}] {self.detail}"


@dataclass
class ScreenResult:
    passed: pd.DataFrame             # 候选池（含指标/打分/红旗）
    rejected: pd.DataFrame           # 被剔除（含剔除层级与原因）
    funnel: dict = field(default_factory=dict)  # 各层剩余数量
    data_notes: list = field(default_factory=list)  # 数据覆盖说明（缺失字段与跳过的规则）

    def summary(self) -> str:
        lines = ["筛选漏斗:"]
        for k, v in self.funnel.items():
            lines.append(f"  {k}: {v}")
        lines.append(f"  最终候选池: {len(self.passed)} 家")
        if self.data_notes:
            lines.append("数据覆盖说明（以下字段本数据源不包含，相关规则已跳过）:")
            for n in self.data_notes:
                lines.append(f"  · {n}")
        return "\n".join(lines)


# ---------------------------------------------------------------- 数据覆盖检查
def _data_notes(metrics_df: pd.DataFrame) -> list[str]:
    """检查指标表中"整列全缺失"的字段，生成跳过规则的透明说明。"""
    checks = [
        ("debt_ratio", "资产负债率 → 「高杠杆」规则跳过"),
        ("monetary_ratio", "货币资金 → 「存贷双高」规则跳过"),
        ("goodwill_ratio", "商誉 → 「商誉占净资产」规则跳过"),
        ("receivable_ratio", "应收账款 → 「应收占比/应收增速」规则跳过"),
        ("inventory_ratio", "存货 → 「存货占比」规则跳过"),
        ("dividend_yield", "分红数据 → 「股息率」条件与股东回报评分按中性处理"),
    ]
    notes = []
    for col, label in checks:
        if col in metrics_df.columns and metrics_df[col].isna().all():
            notes.append(label)
    return notes


# ---------------------------------------------------------------- 排雷
def vet_company(m: dict, cfg: AppConfig) -> list[Flag]:
    """对一家公司的指标做红旗检测，返回全部触发的 Flag。"""
    v = cfg.vetting
    flags: list[Flag] = []

    # —— 现金流（第一优先级）——
    if m.get("ocf_neg_years", 0) >= v.ocf_neg_years_limit_red:
        flags.append(Flag(
            "red", "经营现金流连续为负",
            f"连续 {m['ocf_neg_years']} 年为负（阈值 ≥{v.ocf_neg_years_limit_red}）",
        ))

    ocf_ratio = m.get("ocf_profit_ratio", 1.0)
    if ocf_ratio < v.ocf_profit_ratio_red:
        flags.append(Flag(
            "red", "利润含金量严重不足",
            f"5年累计经营现金流/净利润 = {ocf_ratio:.2f}（阈值 <{v.ocf_profit_ratio_red}）",
        ))
    elif ocf_ratio < v.ocf_profit_ratio_warn:
        flags.append(Flag(
            "yellow", "利润含金量偏低",
            f"5年累计经营现金流/净利润 = {ocf_ratio:.2f}（阈值 <{v.ocf_profit_ratio_warn}）",
        ))

    # —— 存贷双高 ——
    if v.cash_debt_double_high_red and m.get("cash_debt_double"):
        flags.append(Flag(
            "red", "存贷双高",
            f"货币资金/总资产 {m.get('monetary_ratio', 0):.0%} 与有息负债/总资产 "
            f"{m.get('int_debt_ratio', 0):.0%} 同时超线（各 >{v.cash_ratio_high:.0%}）",
        ))

    # —— 应收 / 存货 ——
    if m.get("receivable_ratio", 0) > v.receivable_ratio_warn:
        flags.append(Flag(
            "yellow", "应收账款占比过高",
            f"应收/营收 = {m['receivable_ratio']:.0%}（阈值 >{v.receivable_ratio_warn:.0%}）",
        ))
    if m.get("receivable_gap", 0) > v.receivable_growth_gap_warn:
        flags.append(Flag(
            "yellow", "应收增速远超营收",
            f"应收增速 − 营收增速 = {m['receivable_gap']:+.0%}（阈值 >{v.receivable_growth_gap_warn:.0%}）",
        ))
    if m.get("inventory_ratio", 0) > v.inventory_ratio_warn:
        flags.append(Flag(
            "yellow", "存货占比偏高",
            f"存货/营收 = {m['inventory_ratio']:.0%}（阈值 >{v.inventory_ratio_warn:.0%}）",
        ))

    # —— 商誉 / 杠杆 ——
    if m.get("goodwill_ratio", 0) > v.goodwill_ratio_warn:
        flags.append(Flag(
            "yellow", "商誉占净资产过高",
            f"商誉/净资产 = {m['goodwill_ratio']:.0%}（阈值 >{v.goodwill_ratio_warn:.0%}）",
        ))
    if m.get("debt_ratio", 0) > v.debt_ratio_warn:
        flags.append(Flag(
            "yellow", "资产负债率偏高",
            f"资产负债率 = {m['debt_ratio']:.0%}（阈值 >{v.debt_ratio_warn:.0%}）",
        ))

    # —— 利润质量 / 趋势 ——
    if m.get("deducted_ratio", 1.0) < v.deducted_ratio_warn:
        flags.append(Flag(
            "yellow", "扣非占比偏低",
            f"扣非净利/净利 = {m['deducted_ratio']:.0%}（阈值 <{v.deducted_ratio_warn:.0%}）",
        ))
    if m.get("roe_decline", 0) >= v.roe_decline_years_warn:
        flags.append(Flag(
            "yellow", "ROE 连续下滑",
            f"连续 {m['roe_decline']} 年下滑（阈值 ≥{v.roe_decline_years_warn}）",
        ))
    return flags


# ---------------------------------------------------------------- 漏斗
def _reject_record(m: dict, layer: str, reason: str) -> dict:
    return {
        "symbol": m.get("symbol"), "name": m.get("name"),
        "industry": m.get("industry", ""),
        "layer": layer, "reason": reason,
        "roe_latest": m.get("roe_latest"), "roe_5y_avg": m.get("roe_5y_avg"),
        "pe": m.get("pe"), "ocf_profit_ratio": m.get("ocf_profit_ratio"),
        "_type": m.get("_type", ""),
    }


def screen(financials: pd.DataFrame, cfg: AppConfig,
           enrich_fn=None) -> ScreenResult:
    """执行完整筛选漏斗。

    enrich_fn: 可选钩子 —— 在「③排雷筛后、④估值筛前」调用，
    接收剩余公司的指标宽表并返回补充后的表（如实时模式补拉估值）。
    """
    from . import scoring  # 延迟导入避免循环

    funnel: dict[str, int] = {}
    rejected: list[dict] = []

    # ---- 原始公司级指标 ----
    all_metrics = metrics_mod.metrics_for_all(financials, years=cfg.data.years)
    funnel["全市场"] = len(all_metrics)

    # ---- ① 硬性初筛 ----
    keep = all_metrics.copy()
    for _, m in keep.iterrows():
        md = m.to_dict()
        if cfg.screen.exclude_st and md.get("st_flag"):
            rejected.append(_reject_record(md, "①硬性初筛", "ST/风险警示股"))
        elif md.get("listed_years", 0) < cfg.screen.min_listed_years:
            rejected.append(_reject_record(
                md, "①硬性初筛",
                f"上市 {md.get('listed_years')} 年 < {cfg.screen.min_listed_years} 年"))
        elif md.get("market_cap", 0) < cfg.screen.min_market_cap:
            rejected.append(_reject_record(
                md, "①硬性初筛",
                f"市值 {md.get('market_cap', 0)/1e8:.0f} 亿 < "
                f"{cfg.screen.min_market_cap/1e8:.0f} 亿"))
    rej_syms = {r["symbol"] for r in rejected}
    keep = keep[~keep["symbol"].isin(rej_syms)]
    funnel["①硬性初筛后"] = len(keep)

    # ---- ② 盈利质量筛 ----
    layer2_rej = []
    for _, m in keep.iterrows():
        md = m.to_dict()
        if md["roe_latest"] < cfg.screen.min_roe_latest:
            layer2_rej.append((md["symbol"], _reject_record(
                md, "②盈利质量筛",
                f"最新 ROE {md['roe_latest']:.1%} < {cfg.screen.min_roe_latest:.0%}")))
        elif md["roe_5y_avg"] < cfg.screen.min_roe_5y_avg:
            layer2_rej.append((md["symbol"], _reject_record(
                md, "②盈利质量筛",
                f"5年平均 ROE {md['roe_5y_avg']:.1%} < {cfg.screen.min_roe_5y_avg:.0%}")))
    rejected += [r for _, r in layer2_rej]
    keep = keep[~keep["symbol"].isin([s for s, _ in layer2_rej])]
    funnel["②盈利质量筛后"] = len(keep)

    # ---- ③ 排雷筛 ----
    vet_results: dict[str, list[Flag]] = {}
    layer3_rej = []
    for _, m in keep.iterrows():
        md = m.to_dict()
        flags = vet_company(md, cfg)
        vet_results[md["symbol"]] = flags
        reds = [f for f in flags if f.level == "red"]
        if reds:
            reason = "；".join(f.detail for f in reds)
            layer3_rej.append((md["symbol"], _reject_record(md, "③排雷筛", reason)))
    rejected += [r for _, r in layer3_rej]
    keep = keep[~keep["symbol"].isin([s for s, _ in layer3_rej])]
    funnel["③排雷筛后"] = len(keep)

    # ---- ③.5 数据补全（可选钩子：实时模式在此补拉估值等）----
    if enrich_fn is not None and not keep.empty:
        try:
            keep = enrich_fn(keep)
            funnel["③.5数据补全后"] = len(keep)
        except Exception as e:  # noqa: BLE001
            print(f"[screening] 数据补全失败（继续执行）：{e}")

    # ---- ④ 估值筛（字段缺失时自动跳过对应条件）----
    layer4_rej = []
    for _, m in keep.iterrows():
        md = m.to_dict()
        if md["pe"] <= 0 or md["pe"] > cfg.screen.max_pe:
            layer4_rej.append((md["symbol"], _reject_record(
                md, "④估值筛",
                f"PE {md['pe']:.1f} 不在 (0, {cfg.screen.max_pe:.0f}] 区间")))
        elif md["dividend_yield"] < cfg.screen.min_dividend_yield:
            layer4_rej.append((md["symbol"], _reject_record(
                md, "④估值筛",
                f"股息率 {md['dividend_yield']:.1%} < {cfg.screen.min_dividend_yield:.1%}")))
    rejected += [r for _, r in layer4_rej]
    keep = keep[~keep["symbol"].isin([s for s, _ in layer4_rej])]
    funnel["④估值筛后"] = len(keep)

    # ---- ⑤ 打分排序 ----
    scored_rows = []
    for _, m in keep.iterrows():
        md = m.to_dict()
        sc = scoring.score_company(md, cfg)
        md.update(sc)
        flags = vet_results.get(md["symbol"], [])
        md["flags_yellow"] = sum(1 for f in flags if f.level == "yellow")
        md["vet_notes"] = "；".join(str(f) for f in flags) if flags else ""
        scored_rows.append(md)

    passed = pd.DataFrame(scored_rows)
    if not passed.empty:
        passed = passed.sort_values("score_total", ascending=False).reset_index(drop=True)
        passed.insert(0, "rank", range(1, len(passed) + 1))

    rejected_df = pd.DataFrame(rejected)
    return ScreenResult(
        passed=passed, rejected=rejected_df, funnel=funnel,
        data_notes=_data_notes(keep) if not keep.empty else [],
    )
