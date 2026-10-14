#!/usr/bin/env python
"""个股深度分析入口：生成完整价值分析报告（含年报核查清单）。

用法::

    cd value-desk
    python scripts/analyze.py 600001            # 分析单只
    python scripts/analyze.py --top 5           # 分析候选池前 5 名
    python scripts/analyze.py --all-rejected    # 分析全部被剔除样本（复盘"为什么被剔除"）

产出：reports/company_<代码>.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vd.config import load_config  # noqa: E402
from vd.data import load_financials  # noqa: E402
from vd import analysis, screening, report  # noqa: E402


def _analyze_and_save(symbol: str, financials, cfg, out_dir: Path) -> str:
    an = analysis.analyze_company(symbol, financials, cfg)
    path = report.company_report_md(an, financials, cfg, out_dir)
    n_target = sum(1 for c in an.checklist
                   if not c.based_on.startswith("通用核查"))
    print(f"  [{an.verdict}] {an.symbol} {an.name} —— "
          f"{an.scores['score_total']:.0f} 分 / {an.scores['grade']} 级 / "
          f"{n_target} 项定向核查 → {path.name}")
    return an.verdict


def main() -> None:
    ap = argparse.ArgumentParser(description="北民大格雷厄姆的 ValueDesk · 个股分析")
    ap.add_argument("symbol", nargs="?", default=None, help="股票代码")
    ap.add_argument("--top", type=int, default=0, help="分析候选池前 N 名")
    ap.add_argument("--config", default=str(ROOT / "config" / "default.yaml"))
    ap.add_argument("--source", default=None)
    args = ap.parse_args()

    if not args.symbol and not args.top:
        ap.error("请指定股票代码，或使用 --top N")

    cfg = load_config(args.config)
    if args.source:
        cfg.data.source = args.source

    financials = load_financials(cfg)
    out_dir = ROOT / "reports"

    if args.symbol:
        _analyze_and_save(args.symbol, financials, cfg, out_dir)
        return

    # --top：先筛选再分析
    result = screening.screen(financials, cfg)
    top = result.passed.head(args.top)
    if top.empty:
        print("候选池为空，无可分析标的")
        return
    print(f"分析候选池前 {len(top)} 名：\n")
    counts: dict[str, int] = {}
    for _, r in top.iterrows():
        v = _analyze_and_save(r["symbol"], financials, cfg, out_dir)
        counts[v] = counts.get(v, 0) + 1
    print(f"\n结论分布: " + " / ".join(f"{k} {v}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
