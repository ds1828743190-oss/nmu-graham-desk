"""报告呈现：筛选报告 / 个股分析报告（Markdown）。

呈现原则
--------
- 每个数字都可对照：不写"财务健康"，写"资产负债率 28%（<40% 属于干净区间）"；
- 每个决定都可追溯：被剔除的公司一定注明【哪一层、什么规则、触发值】；
- 每个疑点都可行动：财务报表疑点全部映射到年报的具体核查章节。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import AppConfig
from .analysis import CompanyAnalysis, dupont_note
from .screening import ScreenResult


def _pct(x, digits=1) -> str:
    try:
        v = float(x)
        if v != v:
            return "—"
        return f"{v:.{digits}%}"
    except Exception:
        return "—"


def _num(x, digits=1) -> str:
    try:
        v = float(x)
        if v != v:
            return "—"
        return f"{v:.{digits}f}"
    except Exception:
        return "—"


def _yi(x) -> str:
    """元 → 亿元（NaN/异常显示为 —）。"""
    try:
        v = float(x)
        if v != v:
            return "—"
        return f"{v/1e8:,.1f}"
    except Exception:
        return "—"


# ================================================================== 筛选报告
def screen_report_md(result: ScreenResult, cfg: AppConfig,
                     out_dir: str | Path = "reports",
                     date_tag: str = "") -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = date_tag or pd.Timestamp.now().strftime("%Y%m%d")
    path = out_dir / f"screen_{tag}.md"

    # ---- 候选池表 ----
    pool_rows = []
    top_n = cfg.report.top_n
    for _, r in result.passed.head(top_n).iterrows():
        pool_rows.append(
            f"| {int(r['rank'])} | {r['symbol']} | {r['name']} | {r['industry']} | "
            f"{r['score_total']:.0f} | **{r['grade']}** | {_pct(r['roe_5y_avg'])} | "
            f"{_num(r['ocf_profit_ratio'], 2)} | {_pct(r['dividend_yield'])} | "
            f"{_num(r['pe'], 1)} | {int(r['flags_yellow'])} |"
        )
    pool_table = "\n".join([
        "| 排名 | 代码 | 名称 | 行业 | 综合分 | 评级 | 5年ROE | 含金量 | 股息率 | PE | 黄旗 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ] + pool_rows) if pool_rows else "（候选池为空）"

    # ---- 漏斗 ----
    funnel_lines = [f"- {k}：**{v}** 家" for k, v in result.funnel.items()]

    # ---- 剔除统计（按层）----
    rej_summary = ""
    if not result.rejected.empty:
        by_layer = result.rejected.groupby("layer").size()
        by_layer_lines = [f"| {k} | {v} 家 |" for k, v in by_layer.items()]
        rej_summary = "\n".join([
            "| 剔除层级 | 数量 |", "|---|---|",
        ] + by_layer_lines)

    # ---- 剔除明细 ----
    rej_detail = ""
    if not result.rejected.empty:
        rows = []
        for _, r in result.rejected.iterrows():
            rows.append(f"| {r['symbol']} | {r['name']} | {r['layer']} | {str(r['reason'])[:72]} |")
        rej_detail = "\n".join([
            "| 代码 | 名称 | 层级 | 原因 |", "|---|---|---|---|",
        ] + rows[:60])
        if len(result.rejected) > 60:
            rej_detail += f"\n\n*（另有 {len(result.rejected) - 60} 家未展示）*"

    md = f"""# 标的筛选报告 · {tag}

> 北民大格雷厄姆的 ValueDesk 自动生成 · 数据源：{cfg.data.source} · 分析年数：{cfg.data.years} 年
> ⚠️ 筛选结果只是研究的起点，不是买入清单；每一家进入候选池的公司仍须人工阅读年报核实。

## 一、筛选漏斗

{chr(10).join(funnel_lines)}

## 二、候选池（前 {min(top_n, len(result.passed))} 名）

{pool_table}

**评级**：A ≥{cfg.scoring.grade_a:.0f} 分 · B ≥{cfg.scoring.grade_b:.0f} · C ≥{cfg.scoring.grade_c:.0f} · D 以下
**含金量** = 5年累计经营现金流/净利润（>0.8 健康）· **黄旗** = 标注风险但未剔除的疑点数

## 三、剔除统计

{rej_summary}

## 四、剔除明细（可审计）

{rej_detail}

---
*筛选阈值见 config/default.yaml；每条排雷规则的数值依据见 docs/METRICS.md*
"""
    path.write_text(md, encoding="utf-8")
    return path


# ================================================================== 个股报告
def company_report_md(an: CompanyAnalysis, financials: pd.DataFrame,
                      cfg: AppConfig, out_dir: str | Path = "reports") -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"company_{an.symbol}.md"

    m = an.metrics
    company = financials[financials["symbol"] == an.symbol].sort_values("year")

    # —— 速览 ——
    overview = "\n".join([
        "| 项目 | 数值 |", "|---|---|",
        f"| 行业 | {an.industry or '—'} |",
        f"| 上市年限 | {m.get('listed_years', 0)} 年 |",
        f"| 总市值 | {_yi(m.get('market_cap', 0))} 亿元 |",
        f"| 最新财年 | {m.get('year_latest', '—')} |",
        f"| 结论 | **{an.verdict}** —— {an.verdict_reason} |",
    ])

    # —— 五年核心表 ——
    fin_rows = []
    for _, r in company.iterrows():
        fin_rows.append(
            f"| {int(r['year'])} | {_yi(r['revenue'])} | {_yi(r['net_profit'])} | "
            f"{_pct(r['roe'])} | {_pct(r['gross_margin'])} | {_pct(r['net_margin'])} | "
            f"{_yi(r['ocf'])} | {_pct(r['debt_ratio'])} |"
        )
    fin_table = "\n".join([
        "| 年份 | 营收(亿) | 净利(亿) | ROE | 毛利率 | 净利率 | 经营现金流(亿) | 负债率 |",
        "|---|---|---|---|---|---|---|---|",
    ] + fin_rows)

    # —— 亮点 / 疑点 ——
    hl = "\n".join(f"- {x}" for x in an.highlights)
    cc = "\n".join(f"- {x}" for x in an.concerns)

    # —— 评分 ——
    from .scoring import explain_scores
    score_lines = "\n".join(explain_scores(m, cfg))

    # —— 排雷 ——
    if an.flags:
        flag_lines = "\n".join(f"- {f}" for f in an.flags)
    else:
        flag_lines = "- ✅ 未触发任何红旗"

    # —— 年报核查清单（通用 + 定向）——
    base_items = [c for c in an.checklist if c.based_on.startswith("通用核查")]
    targeted = [c for c in an.checklist if not c.based_on.startswith("通用核查")]

    base_md = "\n\n".join(
        f"**{i}. {c.item}**\n   - 📍 去哪查：{c.where}\n   - 🔍 查什么：{c.how}"
        for i, c in enumerate(base_items, 1)
    ) or "（无）"
    if targeted:
        target_md = "\n\n".join(
            f"**D{i}. {c.item}**（依据：{c.based_on}）\n"
            f"   - 📍 去哪查：{c.where}\n   - 🔍 查什么：{c.how}"
            for i, c in enumerate(targeted, 1)
        )
    else:
        target_md = "（本次财务数据未触发特定核查项——这本身是好信号，但通用核查仍须完成）"

    md = f"""# {an.name}（{an.symbol}）· 价值分析报告

> 生成时间：{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')} · 数据源：{cfg.data.source}
> ⚠️ 本报告由规则引擎生成，是研究的起点而非结论；最终判断（以及买不买）由你完成。

## 结论：{an.verdict}

{an.verdict_reason}

## 一、公司速览

{overview}

## 二、核心财务数据（近 {len(company)} 年）

{fin_table}

## 三、盈利质量

**杜邦拆解**：{dupont_note(m)}

- 5 年平均 ROE：{_pct(m.get('roe_5y_avg'))}｜最新 {_pct(m.get('roe_latest'))}｜连续下滑 {m.get('roe_decline', 0)} 年
- 扣非净利/净利：{_pct(m.get('deducted_ratio'))}（<60% 说明利润依赖非经常性项目）
- 毛利率：{_pct(m.get('gross_margin'))}（5年波动标准差 {_pct(m.get('gross_margin_std'))}）

## 四、资产安全

- 资产负债率：{_pct(m.get('debt_ratio'))}
- 货币资金/总资产：{_pct(m.get('monetary_ratio'))}｜有息负债/总资产：{_pct(m.get('int_debt_ratio'))}｜存贷双高：{'⚠️ 是' if m.get('cash_debt_double') else '否'}
- 应收账款/营收：{_pct(m.get('receivable_ratio'))}｜应收与营收增速差：{_pct(m.get('receivable_gap'))}
- 商誉/净资产：{_pct(m.get('goodwill_ratio'))}｜存货/营收：{_pct(m.get('inventory_ratio'))}

## 五、现金流质量

- 5 年累计经营现金流/净利润（含金量）：**{_num(m.get('ocf_profit_ratio'), 2)}**（>0.8 健康，<0.5 警戒）
- 经营现金流连续为负：{m.get('ocf_neg_years', 0)} 年
- 最新自由现金流（经营现金流−资本开支）：{_yi(m.get('fcf_latest', 0))} 亿元

## 六、股东回报

- 股息率：{_pct(m.get('dividend_yield'), 2)}｜连续分红：{m.get('dividend_years', 0)} 年｜分红率：{_pct(m.get('payout_ratio'))}

## 七、估值

- PE：{_num(m.get('pe'))}｜PB：{_num(m.get('pb'), 2)}（需与历史分位、同业对照后使用）

## 八、五维评分

{score_lines}

**综合分：{an.scores.get('score_total', 0):.1f} → 评级 {an.scores.get('grade', '—')}**

## 九、排雷清单

{flag_lines}

## 十、年报核查清单 ⭐

> 财报数据是体温计，真正的病因在年报原文里。核查分两组：
> **通用核查**（每家公司都做的固定动作）+ **定向核查**（基于本次财务数据异常生成的专项任务）。

### 10.1 通用核查（每次都做）

{base_md}

### 10.2 定向核查（数据触发）

{target_md}

---

## 分析亮点

{hl}

## 分析疑点

{cc}

---
*规则与阈值：config/default.yaml ｜ 指标释义：docs/METRICS.md*
"""
    path.write_text(md, encoding="utf-8")
    return path
