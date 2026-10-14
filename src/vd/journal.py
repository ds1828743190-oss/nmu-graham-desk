"""跟踪器：持续跟踪候选池的变化（新增 / 退出 / 评分变动）。

价值投资是"持续寻找"而不是"一锤子买卖"——
每次筛选的候选池快照都留档，下次筛选自动对比：
新进入的是什么（为什么以前没进来）、退出的又为什么（评分降了还是被雷劈了）。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from .screening import ScreenResult


class Tracker:
    def __init__(self, root: str | Path = "reports"):
        self.dir = Path(root) / "tracker"
        self.dir.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------- 快照
    def save_snapshot(self, result: ScreenResult, date_tag: str) -> Path:
        cols = [c for c in ["symbol", "name", "industry", "score_total", "grade",
                            "roe_5y_avg", "ocf_profit_ratio", "pe", "dividend_yield"]
                if c in result.passed.columns]
        path = self.dir / f"pool_{date_tag.replace('-', '')}.csv"
        result.passed[cols].to_csv(path, index=False, encoding="utf-8-sig")
        return path

    # ---------------------------------------------------------- 对比
    def diff_with_previous(self) -> dict:
        """与上一次快照对比，返回 {'new': [...], 'dropped': [...], 'upgraded': [...]}。"""
        snaps = sorted(self.dir.glob("pool_*.csv"))
        if len(snaps) < 2:
            return {"new": [], "dropped": [], "changed": []}
        prev = pd.read_csv(snaps[-2])
        curr = pd.read_csv(snaps[-1])
        prev_set = set(prev["symbol"].astype(str))
        curr_set = set(curr["symbol"].astype(str))

        new = curr[curr["symbol"].astype(str).isin(curr_set - prev_set)]
        dropped = prev[prev["symbol"].astype(str).isin(prev_set - curr_set)]

        # 评分明显变动（±5 分以上）
        merged = curr.merge(prev, on="symbol", suffixes=("_now", "_prev"))
        changed = merged[
            (merged["score_total_now"] - merged["score_total_prev"]).abs() >= 5
        ][["symbol", "name_now", "score_total_prev", "score_total_now"]]

        return {
            "new": new[["symbol", "name", "score_total", "grade"]].to_dict("records"),
            "dropped": dropped[["symbol", "name", "score_total", "grade"]].to_dict("records"),
            "changed": changed.to_dict("records"),
        }

    def diff_text(self) -> str:
        d = self.diff_with_previous()
        if not any(d.values()):
            return "（暂无历史快照可供对比，这是第一次跟踪）"
        lines = []
        if d["new"]:
            lines.append("**新进入候选池**：")
            for r in d["new"]:
                lines.append(f"- {r['symbol']} {r['name']}（{r['score_total']:.0f} 分 / {r['grade']}）")
        if d["dropped"]:
            lines.append("**退出候选池**（需要复盘原因）：")
            for r in d["dropped"]:
                lines.append(f"- {r['symbol']} {r['name']}（原 {r['score_total']:.0f} 分 / {r['grade']}）")
        if d["changed"]:
            lines.append("**评分明显变动**：")
            for r in d["changed"]:
                delta = r["score_total_now"] - r["score_total_prev"]
                lines.append(f"- {r['symbol']} {r['name_now']}："
                             f"{r['score_total_prev']:.0f} → {r['score_total_now']:.0f}（{delta:+.0f}）")
        return "\n".join(lines)
