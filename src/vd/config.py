"""配置体系：筛选阈值 / 排雷规则 / 评分权重，全部集中于此。

设计原则：所有判断阈值都放在配置里 —— 你能随时调整，
而且"调了什么、调前调后有什么差异"可以被清楚地记录和复盘。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import dataclasses

try:
    import yaml  # type: ignore
    _HAS_YAML = True
except ImportError:  # pragma: no cover
    _HAS_YAML = False


# ------------------------------------------------------------------ 数据层
@dataclass
class DataConfig:
    source: str = "mock"          # mock = 离线演示；akshare = 联网实时
    years: int = 5                # 分析年数（含最新一期）
    max_symbols: int = 200        # 实时模式下估值补拉的标的数上限
    cache_dir: str = "data_cache"
    exclude_bse: bool = True      # 实时模式排除北交所（4/8/9 开头）
    mock_seed: int = 42
    mock_n_companies: int = 30    # 模拟公司数量


# ------------------------------------------------------------------ 筛选漏斗
@dataclass
class ScreenConfig:
    # 第 1 层：硬性初筛
    min_listed_years: int = 5     # 上市年限（排除次新股）
    exclude_st: bool = True       # 排除 ST/*ST
    min_market_cap: float = 30e8  # 市值下限（元），30 亿小盘线

    # 第 2 层：盈利质量筛
    min_roe_latest: float = 0.08      # 最近一年 ROE 下限
    min_roe_5y_avg: float = 0.10      # 近 5 年平均 ROE 下限

    # 第 3 层：估值筛（可选；0 表示不启用该条件）
    max_pe: float = 60.0
    min_dividend_yield: float = 0.0   # 股息率下限（0 = 不做硬筛选）


# ------------------------------------------------------------------ 排雷规则
@dataclass
class VettingConfig:
    """红旗检测阈值。red = 剔除；yellow = 标注风险保留。

    每条规则的出处与含义见 docs/METRICS.md 「排雷清单」。
    """
    # 现金流
    ocf_neg_years_limit_red: int = 2        # 经营现金流连续为负 >= 2 年 → 红
    ocf_profit_ratio_red: float = 0.5       # 5年累计 OCF/净利润 < 0.5 → 红
    ocf_profit_ratio_warn: float = 0.8      # < 0.8 → 黄

    # 存贷双高（康美式特征：账上存款多、外面借款也多）
    cash_ratio_high: float = 0.20           # 货币资金/总资产 > 20%
    debt_fund_ratio_high: float = 0.20      # 有息负债/总资产 > 20%
    cash_debt_double_high_red: bool = True

    # 应收 / 存货
    receivable_ratio_warn: float = 0.50     # 应收账款/营收 > 50% → 黄
    receivable_growth_gap_warn: float = 0.30  # 应收增速 − 营收增速 > 30pct → 黄
    inventory_ratio_warn: float = 0.60      # 存货/营收 > 60% → 黄

    # 商誉 / 负债
    goodwill_ratio_warn: float = 0.30       # 商誉/净资产 > 30% → 黄
    debt_ratio_warn: float = 0.70           # 资产负债率 > 70% → 黄

    # 利润质量 / 趋势
    deducted_ratio_warn: float = 0.60       # 扣非净利/净利 < 60% → 黄
    roe_decline_years_warn: int = 2         # ROE 连续下滑 >= 2 年 → 黄


# ------------------------------------------------------------------ 评分
@dataclass
class ScoringConfig:
    """五维评分权重（总和 = 1.0）。各维度的打分规则见 scoring.py。"""
    weights: dict = field(default_factory=lambda: {
        "quality": 0.30,      # 盈利质量：ROE 水平与稳定性、毛利率
        "safety": 0.20,       # 资产安全：负债、应收、商誉、存货
        "cashflow": 0.20,     # 现金流：利润含金量与自由现金流
        "growth": 0.15,       # 成长：营收/净利增速与稳定性
        "valuation": 0.15,    # 估值：PE/PB/股息率
    })
    # 评级分界（综合分 0-100）
    grade_a: float = 80.0
    grade_b: float = 65.0
    grade_c: float = 50.0


# ------------------------------------------------------------------ 报告
@dataclass
class ReportConfig:
    out_dir: str = "reports"
    top_n: int = 20               # 筛选报告展示条数


# ------------------------------------------------------------------ 总配置
@dataclass
class AppConfig:
    data: DataConfig = field(default_factory=DataConfig)
    screen: ScreenConfig = field(default_factory=ScreenConfig)
    vetting: VettingConfig = field(default_factory=VettingConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    report: ReportConfig = field(default_factory=ReportConfig)


# ---------------------------------------------------------------- 工具
def _apply(obj: Any, overrides: dict) -> None:
    valid = {f.name: f for f in dataclasses.fields(obj)}
    for k, v in overrides.items():
        if k not in valid:
            print(f"[config] 忽略未知配置项: {k}")
            continue
        cur = getattr(obj, k)
        if dataclasses.is_dataclass(cur) and isinstance(v, dict):
            _apply(cur, v)
        elif isinstance(cur, dict) and isinstance(v, dict):
            merged = dict(cur)
            merged.update(v)
            setattr(obj, k, merged)
        else:
            setattr(obj, k, v)


def load_config(path: str | Path | None = None) -> AppConfig:
    cfg = AppConfig()
    if path is None:
        return cfg
    p = Path(path)
    if not p.exists():
        print(f"[config] 未找到 {p}，使用内置默认配置")
        return cfg
    if not _HAS_YAML:
        print("[config] 未安装 pyyaml，使用默认配置")
        return cfg
    with open(p, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    _apply(cfg, raw)
    return cfg
