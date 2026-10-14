#!/usr/bin/env python
"""核心测试：数据 / 指标 / 排雷 / 筛选漏斗 / 打分 / 分析。

直接运行:  python tests/test_core.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vd.config import load_config  # noqa: E402
from vd.data import generate_mock_financials  # noqa: E402
from vd import metrics as metrics_mod  # noqa: E402
from vd import screening, scoring, analysis  # noqa: E402


def test_config():
    cfg = load_config()
    assert cfg.screen.min_roe_5y_avg == 0.10
    ycfg = load_config(ROOT / "config" / "default.yaml")
    w = ycfg.scoring.weights
    assert abs(sum(w.values()) - 1.0) < 1e-9, "评分权重之和必须为 1"


def test_mock_data():
    cfg = load_config()
    df = generate_mock_financials(cfg)
    n_comp = df["symbol"].nunique()
    assert n_comp == cfg.data.mock_n_companies
    assert df["year"].nunique() == cfg.data.years
    # 确定性
    df2 = generate_mock_financials(cfg)
    assert df["roe"].round(6).equals(df2["roe"].round(6))
    # 埋雷样本存在
    types = set(df["type"].unique())
    for t in ["cash_debt_double", "receivable_boom", "goodwill_bomb", "high_leverage"]:
        assert t in types, f"缺少埋雷样本类型 {t}"


def test_metrics_calculation():
    cfg = load_config()
    df = generate_mock_financials(cfg)
    # 找一家卓越型公司
    ex_type = "excellent"
    sym = df[df["type"] == ex_type]["symbol"].iloc[0]
    m = metrics_mod.compute_company_metrics(df[df["symbol"] == sym], cfg.data.years)

    assert m["roe_5y_avg"] > 0.10
    assert m["ocf_profit_ratio"] > 0.8       # 卓越型含金量应健康
    assert not m["cash_debt_double"]
    assert "dupont_margin" in m              # 杜邦拆解存在

    # 存贷双高样本
    cdd_sym = df[df["type"] == "cash_debt_double"]["symbol"].iloc[0]
    m2 = metrics_mod.compute_company_metrics(df[df["symbol"] == cdd_sym], cfg.data.years)
    assert m2["cash_debt_double"], "存贷双高样本未被识别"
    assert m2["ocf_profit_ratio"] < 0.8, "存贷双高样本含金量应偏低"


def test_vet_rules():
    cfg = load_config()
    df = generate_mock_financials(cfg)

    # 应收暴增样本 → 应有相应黄旗；现金流恶化明显 → 应触发含金量相关旗
    ar_sym = df[df["type"] == "receivable_boom"]["symbol"].iloc[0]
    m = metrics_mod.compute_company_metrics(df[df["symbol"] == ar_sym], cfg.data.years)
    flags = screening.vet_company(m, cfg)
    rules = {f.rule for f in flags}
    assert any("应收" in r for r in rules) or any("含金量" in r for r in rules), \
        f"应收暴增样本未触发预期规则: {rules}"

    # 商誉样本
    gw_sym = df[df["type"] == "goodwill_bomb"]["symbol"].iloc[0]
    m2 = metrics_mod.compute_company_metrics(df[df["symbol"] == gw_sym], cfg.data.years)
    flags2 = screening.vet_company(m2, cfg)
    assert any("商誉" in f.rule for f in flags2), "商誉样本未触发商誉规则"

    # 高杠杆样本
    hl_sym = df[df["type"] == "high_leverage"]["symbol"].iloc[0]
    m3 = metrics_mod.compute_company_metrics(df[df["symbol"] == hl_sym], cfg.data.years)
    flags3 = screening.vet_company(m3, cfg)
    assert any("负债率" in f.rule for f in flags3), "高杠杆样本未触发负债率规则"


def test_screen_funnel():
    cfg = load_config()
    df = generate_mock_financials(cfg)
    result = screening.screen(df, cfg)

    # 漏斗逐层收敛
    vals = list(result.funnel.values())
    assert vals == sorted(vals, reverse=True), "漏斗数量应逐层递减"
    assert result.funnel["全市场"] == cfg.data.mock_n_companies

    # 候选池非空且评级合理
    assert not result.passed.empty, "候选池不应为空"
    assert set(result.passed["grade"]).issubset({"A", "B", "C", "D"})

    # 面试雷样本不应进入候选池（必须被剔除处理）
    passed_types = set(result.passed.get("_type", []))
    for bad in ["cash_debt_double", "receivable_boom"]:
        assert bad not in passed_types, f"{bad} 样本不应进入候选池"

    # 被剔除的记录都要有原因
    if not result.rejected.empty:
        assert result.rejected["reason"].notna().all()
        assert result.rejected["layer"].notna().all()


def test_scoring_ordering():
    cfg = load_config()
    df = generate_mock_financials(cfg)

    def score_of(t):
        sym = df[df["type"] == t]["symbol"].iloc[0]
        m = metrics_mod.compute_company_metrics(df[df["symbol"] == sym], cfg.data.years)
        return scoring.score_company(m, cfg)["score_total"]

    s_excellent = score_of("excellent")
    s_mediocre = score_of("mediocre")
    s_cdd = score_of("cash_debt_double")
    assert s_excellent > s_mediocre, "卓越型应得分高于平庸型"
    assert s_excellent > s_cdd, "卓越型应得分高于存贷双高型"
    # 分数在合理区间
    assert 0 <= s_excellent <= 100


def test_analysis_output():
    cfg = load_config()
    df = generate_mock_financials(cfg)

    # 卓越型 → 应为"关注"或"观察"
    ex_sym = df[df["type"] == "excellent"]["symbol"].iloc[0]
    an = analysis.analyze_company(ex_sym, df, cfg)
    assert an.verdict in ("关注", "观察")
    assert an.highlights and an.concerns
    assert an.scores["score_total"] > 0

    # 存贷双高样本 → 必须"回避"（红灯）
    cdd_sym = df[df["type"] == "cash_debt_double"]["symbol"].iloc[0]
    an2 = analysis.analyze_company(cdd_sym, df, cfg)
    assert an2.verdict == "回避", f"存贷双高样本应判回避，实际 {an2.verdict}"
    assert any("存贷双高" in c.item for c in an2.checklist), \
        "应生成存贷双高的年报核查任务"

    # 应收暴增样本 → 核查清单应包含应收账款项
    ar_sym = df[df["type"] == "receivable_boom"]["symbol"].iloc[0]
    an3 = analysis.analyze_company(ar_sym, df, cfg)
    items = " ".join(c.item for c in an3.checklist)
    assert ("应收" in items) or ("含金量" in items), "应收样本应触发对应核查项"


def _run_all():
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    passed, failed = 0, []
    for fn in fns:
        try:
            fn()
            print(f"  ✅ {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {fn.__name__}: {e}")
            failed.append(fn.__name__)
        except Exception as e:  # noqa: BLE001
            print(f"  💥 {fn.__name__}: {type(e).__name__}: {e}")
            failed.append(fn.__name__)
    print(f"\n{passed}/{len(fns)} 通过")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    _run_all()
