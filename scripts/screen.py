#!/usr/bin/env python
"""全市场筛选入口：五层漏斗 → 候选池 → 报告。

用法::

    cd value-desk
    python scripts/screen.py                # mock 演示数据
    python scripts/screen.py --source akshare   # 真实A股（需联网）

产出：
- reports/screen_YYYYMMDD.md     筛选报告（候选池 + 漏斗 + 剔除明细）
- reports/tracker/pool_*.csv     候选池快照（供下次对比）
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from vd.config import load_config  # noqa: E402
from vd.data import load_financials  # noqa: E402
from vd import screening, report  # noqa: E402
from vd.journal import Tracker  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="北民大格雷厄姆的 ValueDesk · 标的筛选")
    ap.add_argument("--config", default=str(ROOT / "config" / "default.yaml"))
    ap.add_argument("--source", default=None, help="覆盖数据源: mock / akshare")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.source:
        cfg.data.source = args.source

    financials = load_financials(cfg)
    print(f"数据集: {financials['symbol'].nunique()} 家公司 × "
          f"{cfg.data.years} 年（共 {len(financials)} 行）\n")

    result = screening.screen(financials, cfg)

    # ---------- 终端摘要 ----------
    print(result.summary())
    print()
    if not result.passed.empty:
        print("🏆 候选池（前 10 名）")
        print(f"{'排名':<4}{'代码':<8}{'名称':<14}{'评分':<6}{'评级':<4}"
              f"{'5年ROE':<8}{'含金量':<8}{'股息率':<8}{'PE':<6}黄旗")
        for _, r in result.passed.head(10).iterrows():
            print(f"{int(r['rank']):<4}{r['symbol']:<8}{r['name']:<14}"
                  f"{r['score_total']:<6.0f}{r['grade']:<4}"
                  f"{r['roe_5y_avg']:<8.1%}{r['ocf_profit_ratio']:<8.2f}"
                  f"{r['dividend_yield']:<8.1%}{r['pe']:<6.1f}{int(r['flags_yellow'])}")

    # 埋雷样本的落点（演示对照：mock 模式下显示埋雷公司被如何处理）
    if cfg.data.source == "mock" and "_type" in result.passed.columns:
        pass  # 埋雷不应出现在候选池

    # ---------- 报告与跟踪 ----------
    date_tag = pd.Timestamp.now().strftime("%Y%m%d")
    path = report.screen_report_md(result, cfg, ROOT / "reports", date_tag)
    tracker = Tracker(ROOT / "reports")
    tracker.save_snapshot(result, date_tag)

    print(f"\n📄 筛选报告: {path}")
    print(f"📄 候选池快照已更新（下次运行自动对比变化）")

    # 剔除侧演示：统计埋雷样本的处理结果（mock 模式）
    if not result.rejected.empty:
        n_rej = len(result.rejected)
        print(f"🚫 共剔除 {n_rej} 家（逐条原因见报告第四节）")


if __name__ == "__main__":
    main()
