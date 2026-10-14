"""数据层：财务数据集（年度长表）。

统一结构（Financials，pandas DataFrame 长表）
---------------------------------------------
每家公司 × 每年一行，字段：

    基础:     symbol, name, industry, listed_years, year, st_flag
    利润表:   revenue, net_profit, deducted_net_profit
    比率:     gross_margin, net_margin, roe
    资产表:   total_assets, net_assets, debt_ratio,
              monetary_funds, interest_bearing_debt, goodwill,
              accounts_receivable, inventory
    现金流:   ocf（经营现金流净额）, capex（资本开支）
    股东回报: dividend（现金分红总额）, dividend_years（连续分红年数）
    估值:     pe, pb, market_cap, dividend_yield

数据源
------
- MockSource：确定性模拟 30 家公司 × 5 年，**内置健康样本与五类埋雷样本**
  （存贷双高 / 应收暴增 / 商誉高企 / 高杠杆 / 现金流背离），
  用来演示筛选漏斗与排雷规则的真实触发。
- AkshareSource：真实 A股数据（尽力容错；接口字段随 akshare 版本可能变动，
  失败时给出明确提示而不是静默出错）。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import AppConfig


# ================================================================== Mock
_INDUSTRIES = ["白酒", "医药", "家电", "银行", "电子", "化工"]

# 公司档案模板：type 决定财务特征轨迹
# (type, 每行业家数, 参数)
_PROFILES = [
    # —— 健康公司 ——
    dict(type="excellent", per_industry=1, roe0=0.22, growth=0.15,
         gross=0.55, ocf_ratio=1.15, debt=0.30, div_yield=0.030, pe0=22, goodwill=0.01),
    dict(type="steady", per_industry=1, roe0=0.13, growth=0.07,
         gross=0.38, ocf_ratio=1.05, debt=0.42, div_yield=0.028, pe0=14, goodwill=0.02),
    # —— 成长型（高估值）——
    dict(type="growth", per_industry=1, roe0=0.16, growth=0.32,
         gross=0.45, ocf_ratio=0.85, debt=0.35, div_yield=0.004, pe0=48, goodwill=0.05),
    # —— 平庸型（将被 ROE 筛剔除）——
    dict(type="mediocre", per_industry=1, roe0=0.075, growth=0.03,
         gross=0.20, ocf_ratio=1.0, debt=0.50, div_yield=0.012, pe0=12, goodwill=0.02),
    # —— 埋雷样本（各抽 1-2 个行业放置；ROE 校准为可通过质量筛，确保走到排雷环节）——
    dict(type="cash_debt_double", per_industry=0, roe0=0.175, growth=0.10,
         gross=0.40, ocf_ratio=0.30, debt=0.45, div_yield=0.010, pe0=18, goodwill=0.02),
    dict(type="receivable_boom", per_industry=0, roe0=0.175, growth=0.12,
         gross=0.35, ocf_ratio=-0.20, debt=0.48, div_yield=0.0, pe0=25, goodwill=0.03),
    dict(type="goodwill_bomb", per_industry=0, roe0=0.17, growth=0.08,
         gross=0.36, ocf_ratio=0.90, debt=0.44, div_yield=0.010, pe0=20, goodwill=0.45),
    dict(type="high_leverage", per_industry=0, roe0=0.14, growth=0.05,
         gross=0.25, ocf_ratio=0.95, debt=0.78, div_yield=0.015, pe0=10, goodwill=0.02),
]

_PROFILE_LABELS = {
    "excellent": "卓越型", "steady": "稳健型", "growth": "成长型",
    "mediocre": "平庸型", "cash_debt_double": "埋雷·存贷双高",
    "receivable_boom": "埋雷·应收暴增", "goodwill_bomb": "埋雷·商誉高企",
    "high_leverage": "埋雷·高杠杆",
}


def _grow(base: float, growth: float, t: int, rng: np.random.Generator,
          noise: float = 0.03) -> float:
    return base * (1 + growth) ** t * (1 + rng.normal(0, noise))


def generate_mock_financials(cfg: AppConfig) -> pd.DataFrame:
    """确定性生成模拟财务数据集（含五类埋雷样本）。"""
    d = cfg.data
    rng = np.random.default_rng(d.mock_seed)
    years = list(range(2021, 2021 + d.years))   # 2021–2025

    rows = []
    code_idx = 0
    # 前 4 类按行业铺开；埋雷样本按固定位置插入
    special_queue = ["cash_debt_double", "receivable_boom", "cash_debt_double",
                     "goodwill_bomb", "receivable_boom", "high_leverage"]

    companies: list[dict] = []
    for prof in _PROFILES:
        if prof["per_industry"] > 0:
            for ind in _INDUSTRIES:
                companies.append({**prof, "industry": ind})
    # 插入埋雷（每个埋雷占用一个行业，避免与健康公司同名行业混淆观感）
    for i, t in enumerate(special_queue):
        base = next(p for p in _PROFILES if p["type"] == t)
        companies.append({**base, "industry": _INDUSTRIES[i % len(_INDUSTRIES)]})

    # 控制总数
    companies = companies[: d.mock_n_companies]

    for comp in companies:
        code_idx += 1
        prefix = ["600", "601", "603", "000", "002", "300"][code_idx % 6]
        symbol = f"{prefix}{code_idx:03d}"
        ctype = comp["type"]
        name = f"{comp['industry']}{_PROFILE_LABELS[ctype][:2]}{code_idx:02d}"
        listed_years = 8 + int(rng.integers(0, 10))

        # —— 规模基准（公司级固定，保证营收轨迹连续稳定）——
        revenue_base = 20e8 * (1 + rng.random() * 3)

        for t, year in enumerate(years):
            # —— 规模轨迹 ——
            revenue = _grow(revenue_base, comp["growth"], t, rng)
            net_margin = comp["roe0"] * 0.55          # 粗略换算：ROE≈净利率×1.8
            net_profit = revenue * net_margin * (1 + rng.normal(0, 0.05))

            # —— 埋雷特化调整 ——
            if ctype == "receivable_boom" and t >= 2:
                net_profit *= 1.1                      # 利润仍"好看"
                ocf_ratio = -0.4 - 0.2 * (t - 2)       # 现金流越来越差
            elif ctype == "cash_debt_double":
                ocf_ratio = 0.25 + rng.normal(0, 0.05)  # 含金量持续极低
            else:
                ocf_ratio = comp["ocf_ratio"] * (1 + rng.normal(0, 0.08))

            deducted_ratio = {
                "cash_debt_double": 0.55, "receivable_boom": 0.60,
                "goodwill_bomb": 0.72, "excellent": 0.95, "steady": 0.92,
                "growth": 0.88, "mediocre": 0.80, "high_leverage": 0.85,
            }[ctype]
            deducted = net_profit * deducted_ratio * (1 + rng.normal(0, 0.03))

            total_assets = revenue / (0.6 + rng.random() * 0.5)   # 近似的资产周转
            net_assets = total_assets * (1 - comp["debt"])
            roe = net_profit / net_assets

            # 现金流与资本开支
            ocf = net_profit * ocf_ratio
            capex = revenue * (0.05 + rng.random() * 0.05)

            # —— 资产负债表细项 ——
            monetary = total_assets * (
                0.28 if ctype == "cash_debt_double" else 0.10 + rng.random() * 0.08)
            int_debt = total_assets * (
                0.32 if ctype == "cash_debt_double"
                else (0.28 if ctype == "high_leverage" else comp["debt"] * 0.5))
            goodwill = net_assets * comp["goodwill"] * (1 + rng.normal(0, 0.05))
            if ctype == "receivable_boom":
                # 应收占营收比例快速攀升
                ar = revenue * (0.20 + 0.22 * max(0, t - 1))
            else:
                ar = revenue * (0.12 + rng.random() * 0.10)
            inventory = revenue * (0.15 + rng.random() * 0.15)

            # 分红 / 估值
            div_yield = comp["div_yield"] * (1 + rng.normal(0, 0.06))
            dividend = net_profit * (div_yield / max(net_margin, 0.03)) * 0.3
            pe = comp["pe0"] * (1 + rng.normal(0, 0.10))
            pb = pe * roe * (1 + rng.normal(0, 0.05))

            rows.append({
                "symbol": symbol, "name": name, "industry": comp["industry"],
                "type": ctype, "listed_years": listed_years,
                "year": year, "st_flag": False,
                "revenue": round(revenue, 0),
                "net_profit": round(net_profit, 0),
                "deducted_net_profit": round(deducted, 0),
                "gross_margin": comp["gross"] * (1 + rng.normal(0, 0.03)),
                "net_margin": net_margin * (1 + rng.normal(0, 0.04)),
                "roe": roe,
                "total_assets": round(total_assets, 0),
                "net_assets": round(net_assets, 0),
                "debt_ratio": comp["debt"] * (1 + rng.normal(0, 0.03)),
                "monetary_funds": round(monetary, 0),
                "interest_bearing_debt": round(int_debt, 0),
                "goodwill": round(goodwill, 0),
                "accounts_receivable": round(ar, 0),
                "inventory": round(inventory, 0),
                "ocf": round(ocf, 0),
                "capex": round(capex, 0),
                "dividend": round(dividend, 0),
                "dividend_years": 5 - (code_idx % 3),   # 3–5 年连续分红
                "pe": round(pe, 1), "pb": round(pb, 2),
                "market_cap": round(net_profit * pe, 0),
                "dividend_yield": div_yield,
            })

    df = pd.DataFrame(rows)
    # 类型标签不进入分析逻辑，仅用于演示期的结果对照（正式流程会删除）
    return df


# =============================================================== 实时模式（AKShare 联网）
class RealtimeSource:
    """联网实时数据源（AKShare 免费通道，2026-10 实测可用接口）。

    接口组合
    --------
    - 批量（全市场筛选）：``stock_yjbb_em`` 业绩报表，约 10s/年报期，
      含 ROE / 毛利率 / 营收 / 净利 / 每股经营现金流 / 所处行业；
    - 单股（实时分析）：``stock_financial_analysis_indicator``，约 1s/票，
      含资产负债率 / 净利率 / 现金流等 80+ 字段；
    - 估值（百度股市通）：``stock_zh_valuation_baidu``，约 0.5s/指标，
      PE(TTM) / PB / 总市值 —— 取最新交易日快照。

    数据缺失声明（免费通道不含以下字段，统一置 NaN；
    上层规则自动跳过，并在报告与界面中如实标注）：
    商誉 / 货币资金 / 应收账款 / 存货 / 分红明细。

    口径说明：财务数据为各年年报期（12-31）累计值；股本为估算值
    （净利润 ÷ 每股收益的中位数），用于把"每股"指标换算为总额。
    """

    def __init__(self, cfg: AppConfig):
        try:
            import akshare as ak
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "未安装 akshare。请执行: pip install akshare "
                "-i https://pypi.tuna.tsinghua.edu.cn/simple"
            ) from e
        self.ak = ak
        self.cfg = cfg

    # -------------------------------------------------- 工具
    @staticmethod
    def _num(v) -> float:
        try:
            return float(str(v).replace("%", "").replace(",", "").strip())
        except Exception:
            return float("nan")

    @staticmethod
    def _col(df: pd.DataFrame, *aliases):
        for a in aliases:
            if a in df.columns:
                return a
        return None

    def _g(self, df: pd.DataFrame, row, *aliases) -> float:
        col = self._col(df, *aliases)
        if col is None:
            return float("nan")
        return self._num(row[col])

    # -------------------------------------------------- 估值（百度股市通）
    def fetch_valuation(self, symbol: str) -> dict:
        """最新 PE(TTM) / PB / 总市值（元）；任何一项失败即为 NaN。"""
        out = {"pe": float("nan"), "pb": float("nan"), "market_cap": float("nan")}
        for key, indicator in (("pe", "市盈率(TTM)"),
                               ("pb", "市净率"),
                               ("market_cap", "总市值")):
            try:
                df = self.ak.stock_zh_valuation_baidu(
                    symbol=symbol, indicator=indicator, period="近一年")
                if df is not None and len(df) and "value" in df.columns:
                    v = self._num(df["value"].iloc[-1])
                    if key == "market_cap" and v == v:
                        v = v * 1e8          # 百度返回"亿元" → 统一为"元"
                    out[key] = v
            except Exception:
                pass
        return out

    # -------------------------------------------------- 单股实时
    def fetch_single(self, symbol: str) -> pd.DataFrame:
        """单只股票：财务摘要（20 年历史，含总额字段）+ 最新估值 → 统一长表。

        主数据源：``stock_financial_abstract``（新浪财务摘要，约 0.4s），
        含 营业总收入 / 净利润 / 扣非净利润 / 净资产 / 商誉 / 经营现金流量净额 /
        ROE / 毛利率 / 资产负债率 / 权益乘数 等关键指标。
        """
        import re
        years_back = self.cfg.data.years

        ab = self.ak.stock_financial_abstract(symbol=str(symbol).zfill(6))
        if ab is None or ab.empty:
            raise RuntimeError(f"{symbol} 未取到财务摘要数据，请核对代码")

        id_col = self._col(ab, "指标")
        if id_col is None:
            raise RuntimeError(f"{symbol} 财务摘要缺少「指标」列（接口字段可能变化）")
        date_cols = [c for c in ab.columns if re.fullmatch(r"\d{8}", str(c))]
        if not date_cols:
            raise RuntimeError(f"{symbol} 财务摘要缺少日期列")

        # 指标去重（同名指标分属不同分组，取行首版本即可）
        ab = ab.drop_duplicates(subset=[id_col], keep="first").set_index(id_col)

        def get(indicator: str, date_col) -> float:
            if indicator in ab.index:
                return self._num(ab.at[indicator, date_col])
            return float("nan")

        # 取年报期（12-31）近 N 年
        annual = sorted([c for c in date_cols if str(c).endswith("1231")])
        picked = annual[-years_back:]
        if not picked:
            raise RuntimeError(f"{symbol} 财务摘要无年报期数据")

        val = self.fetch_valuation(symbol)

        rows = []
        for c in picked:
            revenue = get("营业总收入", c)
            net_profit = get("净利润", c)
            deduct = get("扣非净利润", c)
            if deduct != deduct:
                deduct = net_profit
            net_assets = get("股东权益合计(净资产)", c)
            equity_mult = get("权益乘数", c)
            total_assets = (net_assets * equity_mult
                            if net_assets == net_assets and equity_mult == equity_mult
                            else float("nan"))
            rows.append({
                "symbol": str(symbol).zfill(6), "name": str(symbol).zfill(6),
                "industry": "", "type": "akshare",
                "listed_years": 10, "year": int(str(c)[:4]), "st_flag": False,
                "revenue": revenue,
                "net_profit": net_profit,
                "deducted_net_profit": deduct,
                "gross_margin": get("毛利率", c) / 100,
                "net_margin": get("销售净利率", c) / 100,
                "roe": get("净资产收益率(ROE)", c) / 100,
                "total_assets": total_assets,
                "net_assets": net_assets,
                "debt_ratio": get("资产负债率", c) / 100,
                "monetary_funds": float("nan"),
                "interest_bearing_debt": float("nan"),
                "goodwill": get("商誉", c),
                "accounts_receivable": float("nan"),
                "inventory": float("nan"),
                "ocf": get("经营现金流量净额", c),
                "capex": float("nan"),
                "dividend": float("nan"), "dividend_years": 0,
                "pe": float("nan"), "pb": float("nan"),
                "market_cap": float("nan"),
                "dividend_yield": float("nan"),
            })

        # 最新估值挂到最后一行（上层取 latest 行）
        rows[-1]["pe"] = val["pe"]
        rows[-1]["pb"] = val["pb"]
        rows[-1]["market_cap"] = val["market_cap"]
        return pd.DataFrame(rows)

    # -------------------------------------------------- 批量（全市场筛选）
    def fetch_market(self) -> pd.DataFrame:
        """全市场：近 N 年年报期业绩报表 → 统一长表（含行业与股本估算）。"""
        years_back = self.cfg.data.years
        this_year = pd.Timestamp.today().year
        periods = [f"{y}1231" for y in range(this_year - years_back, this_year)]

        frames = []
        for period in periods:
            try:
                df = self.ak.stock_yjbb_em(date=period)
            except Exception as e:
                print(f"[实时] {period} 拉取失败：{e}")
                continue
            if df is None or df.empty:
                continue
            df = df.copy()
            df["year"] = int(period[:4])
            frames.append(df)
            print(f"[实时] {period} 已拉取：{len(df)} 家")

        if not frames:
            raise RuntimeError("业绩报表接口未取到数据，请检查网络后重试")

        raw = pd.concat(frames, ignore_index=True)

        # ---- 列名统一（多别名探测）----
        rename = {}
        for target, aliases in {
            "symbol": ("股票代码",), "name": ("股票简称",),
            "industry": ("所处行业",),
            "revenue": ("营业总收入-营业总收入", "营业收入"),
            "net_profit": ("净利润-净利润", "净利润"),
            "roe": ("净资产收益率",), "gross_margin": ("销售毛利率",),
            "eps": ("每股收益",),
            "ocf_ps": ("每股经营现金流量", "每股经营性现金流"),
            "bps": ("每股净资产",),
        }.items():
            col = self._col(raw, *aliases)
            if col is not None:
                rename[col] = target
        raw = raw.rename(columns=rename)

        for c in ("revenue", "net_profit", "roe", "gross_margin",
                  "eps", "ocf_ps", "bps"):
            if c not in raw.columns:
                raw[c] = float("nan")
            raw[c] = pd.to_numeric(raw[c], errors="coerce")
        raw["symbol"] = raw["symbol"].astype(str).str.zfill(6)
        if "name" not in raw.columns:
            raw["name"] = raw["symbol"]
        if "industry" not in raw.columns:
            raw["industry"] = ""

        # ---- 股本估算：eps>0 期的 净利润/每股收益 中位数 ----
        raw["shares_est"] = raw["net_profit"] / raw["eps"].where(raw["eps"] > 0)
        shares_map = raw.groupby("symbol")["shares_est"].median()
        raw["shares"] = raw["symbol"].map(shares_map)

        out = pd.DataFrame({
            "symbol": raw["symbol"],
            "name": raw["name"].astype(str),
            "industry": raw["industry"].astype(str).fillna(""),
            "type": "akshare",
            "listed_years": 10,
            "year": raw["year"],
            "st_flag": raw["name"].astype(str).str.contains("ST", na=False),
            "revenue": raw["revenue"],
            "net_profit": raw["net_profit"],
            # 免费批量通道无扣非数据：以净利替代（报告与界面中标注）
            "deducted_net_profit": raw["net_profit"],
            "gross_margin": raw["gross_margin"] / 100,
            "net_margin": (raw["net_profit"] /
                           raw["revenue"].where(raw["revenue"] > 0)),
            "roe": raw["roe"] / 100,
            "total_assets": float("nan"),
            "net_assets": raw["bps"] * raw["shares"],
            "debt_ratio": float("nan"),
            "monetary_funds": float("nan"),
            "interest_bearing_debt": float("nan"),
            "goodwill": float("nan"),
            "accounts_receivable": float("nan"),
            "inventory": float("nan"),
            "ocf": raw["ocf_ps"] * raw["shares"],
            "capex": float("nan"),
            "dividend": float("nan"),
            "dividend_years": 0,
            "pe": float("nan"), "pb": float("nan"),
            "market_cap": float("nan"),
            "dividend_yield": float("nan"),
        })
        out = out.dropna(subset=["symbol"])
        if getattr(self.cfg.data, "exclude_bse", True):
            # 默认排除北交所（4/8/9 开头）：流动性与披露质量差异大，个人研究优先沪深
            out = out[~out["symbol"].str.match(r"^(4|8|9)")]
        return out.reset_index(drop=True)

    # -------------------------------------------------- 估值批量补全
    def enrich_valuations(self, symbols: list[str], max_workers: int = 6,
                          limit: int = 200) -> dict[str, dict]:
        """对指定代码列表并发补拉估值（≤limit 家）。

        返回 {symbol: {"pe":..., "pb":..., "market_cap":...}}——
        供筛选流程在"排雷后、估值筛前"调用（只补可交易范围内的标的）。
        """
        from concurrent.futures import ThreadPoolExecutor

        picked = [s for s in symbols][:limit]
        result: dict[str, dict] = {}

        def work(sym):
            try:
                return sym, self.fetch_valuation(sym)
            except Exception:
                return sym, {"pe": float("nan"), "pb": float("nan"),
                             "market_cap": float("nan")}

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            for sym, val in ex.map(work, picked):
                result[sym] = val
        return result


# ------------------------------------------------------------------ 入口
def load_financials(cfg: AppConfig) -> pd.DataFrame:
    """统一数据入口（批量）。"""
    if cfg.data.source == "akshare":
        print("[实时] 联网拉取全市场业绩报表（近 %d 年年报期）..." % cfg.data.years)
        return RealtimeSource(cfg).fetch_market()
    print(f"[mock] 生成模拟财务数据集（{cfg.data.mock_n_companies} 家公司 × "
          f"{cfg.data.years} 年，seed={cfg.data.mock_seed}）")
    return generate_mock_financials(cfg)


def load_single_stock(symbol: str, cfg: AppConfig) -> pd.DataFrame:
    """统一数据入口（单股实时）：任何模式下都优先联网实时拉取。"""
    print(f"[实时] 单股实时拉取 {symbol}（财务指标 + 估值）...")
    return RealtimeSource(cfg).fetch_single(symbol)
