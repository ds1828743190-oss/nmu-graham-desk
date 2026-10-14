#!/usr/bin/env python
"""北民大格雷厄姆的 ValueDesk 本地服务：桌面系统的统一运行入口。

启动::

    python app/server.py                  # 默认端口 8787，自动打开浏览器
    python app/server.py --port 9000      # 指定端口
    python app/server.py --source akshare # 真实数据
    python app/server.py --no-browser     # 不自动开浏览器

统一 API（前端 app/ui.py 与任何本地脚本均可调用）::

    GET  /                    单页界面
    GET  /api/status          系统状态（数据源/公司数/候选池/跟踪变化）
    POST /api/screen          运行五层筛选 → 漏斗 + 候选池
    POST /api/analyze         个股深度分析 {symbol} → 结论 + 报告 HTML
    GET  /api/reports         报告列表
    GET  /api/report?name=... 单个报告（HTML）
    POST /api/refresh         重新加载数据

设计约束
--------
- 只监听 127.0.0.1（本机），不对外暴露；
- 全部使用 Python 标准库（零新增依赖）；
- 服务只调用 vd 包既有模块，不反向依赖任何 CLI 脚本。
"""
from __future__ import annotations

import argparse
import json
import threading
import sys
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from vd.config import load_config  # noqa: E402
from vd.data import load_financials  # noqa: E402
from vd import screening, analysis, report as report_mod  # noqa: E402
from vd.journal import Tracker  # noqa: E402
from app import render, ui  # noqa: E402


# ================================================================== 状态
class AppState:
    """进程内存态：数据与最近一次筛选结果（线程安全）。"""

    def __init__(self, source_override: str | None = None):
        self.cfg = load_config(ROOT / "config" / "default.yaml")
        if source_override:
            self.cfg.data.source = source_override
        self.financials: pd.DataFrame | None = None
        self.screen_result = None
        self.screen_time: str = ""
        self.lock = threading.Lock()

    # -------------------------------------------------- 数据
    def ensure_data(self) -> None:
        if self.financials is None:
            print(f"[vd] 加载数据（source={self.cfg.data.source}）...")
            self.financials = load_financials(self.cfg)
            n = self.financials["symbol"].nunique()
            print(f"[vd] 数据就绪：{n} 家公司 × {self.cfg.data.years} 年")

    def reload_data(self) -> None:
        with self.lock:
            self.financials = None
            self.screen_result = None
            self.screen_time = ""
        self.ensure_data()

    # -------------------------------------------------- 数据模式切换
    def switch_source(self, source: str) -> None:
        """切换数据源（mock 离线演示 / akshare 联网实时）并持久化到配置。"""
        import re
        if source not in ("mock", "akshare"):
            raise ValueError(f"不支持的数据源: {source}")
        with self.lock:
            self.cfg.data.source = source
            self.financials = None
            self.screen_result = None
            self.screen_time = ""
        # 持久化到 config/default.yaml（只替换 data.source 的值，保留注释）
        cfg_path = ROOT / "config" / "default.yaml"
        try:
            text = cfg_path.read_text(encoding="utf-8")
            new_text = re.sub(r'(?m)^(\s*source:\s*)"[^"]*"',
                              lambda m: f'{m.group(1)}"{source}"', text, count=1)
            if new_text != text:
                cfg_path.write_text(new_text, encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            print(f"[vd] 配置持久化失败（仅内存生效）：{e}")
        print(f"[vd] 数据源已切换为 {source}")

    # -------------------------------------------------- 筛选
    def run_screen(self):
        with self.lock:
            self.ensure_data()
            t0 = time.time()

            # 实时模式：为「排雷后」的标的并发补拉估值（PE/PB/总市值）
            enrich = None
            if self.cfg.data.source == "akshare":
                from vd.data import RealtimeSource
                rts = RealtimeSource(self.cfg)

                def enrich(df_keep):
                    syms = df_keep["symbol"].astype(str).tolist()
                    vals = rts.enrich_valuations(
                        syms, limit=max(self.cfg.data.max_symbols * 2, 200))
                    print(f"[实时] 已补拉 {len(vals)} 家估值")
                    out = df_keep.copy()
                    out["pe"] = out["symbol"].astype(str).map(
                        lambda s: vals.get(s, {}).get("pe", float("nan")))
                    out["pb"] = out["symbol"].astype(str).map(
                        lambda s: vals.get(s, {}).get("pb", float("nan")))
                    out["market_cap"] = out["symbol"].astype(str).map(
                        lambda s: vals.get(s, {}).get("market_cap", float("nan")))
                    return out

            self.screen_result = screening.screen(self.financials, self.cfg,
                                                  enrich_fn=enrich)
            self.screen_time = time.strftime("%m-%d %H:%M")
            dt = time.time() - t0
        print(f"[vd] 筛选完成（{dt:.1f}s）：候选池 "
              f"{len(self.screen_result.passed)} 家")
        # 落盘：报告 + 跟踪快照
        date_tag = time.strftime("%Y%m%d")
        report_mod.screen_report_md(self.screen_result, self.cfg,
                                    ROOT / "reports", date_tag)
        Tracker(ROOT / "reports").save_snapshot(self.screen_result, date_tag)
        return self.screen_result

    # -------------------------------------------------- 分析
    def analyze(self, symbol: str) -> dict:
        """个股分析。

        实时模式（akshare）：直接联网拉取该股最新财务 + 估值（约 3-5 秒），
        实现"输入代码即分析的实时体验"，无需等待全市场数据加载。
        """
        sym = str(symbol).strip().zfill(6)
        if self.cfg.data.source == "akshare":
            from vd.data import load_single_stock
            data = load_single_stock(sym, self.cfg)
            # 若内存已加载全市场数据，顺带补上名称与行业（更可读）
            if self.financials is not None:
                row = self.financials[self.financials["symbol"] == sym]
                if len(row):
                    data["name"] = row.iloc[0]["name"]
                    data["industry"] = row.iloc[0].get("industry", "")
            an = analysis.analyze_company(sym, data, self.cfg)
            fin_for_report = data
        else:
            self.ensure_data()
            an = analysis.analyze_company(symbol, self.financials, self.cfg)
            fin_for_report = self.financials

        md_path = report_mod.company_report_md(an, fin_for_report, self.cfg,
                                               ROOT / "reports")
        md_text = md_path.read_text(encoding="utf-8")
        return {
            "symbol": an.symbol, "name": an.name,
            "verdict": an.verdict, "reason": an.verdict_reason,
            "score": an.scores["score_total"], "grade": an.scores["grade"],
            "html": render.md_to_html(md_text),
        }

    # -------------------------------------------------- 状态快照
    def status(self) -> dict:
        pool = self.screen_result.passed if self.screen_result is not None else None
        s = {
            "source": self.cfg.data.source,
            "n_companies": int(self.financials["symbol"].nunique())
            if self.financials is not None else 0,
            "pool_size": len(pool) if pool is not None else None,
            "screen_time": self.screen_time,
            "last_funnel": None, "pool_top5": None, "diff_summary": "",
        }
        if self.screen_result is not None:
            s["last_funnel"] = [
                {"label": k, "count": v} for k, v in self.screen_result.funnel.items()
            ]
            top = pool.head(5)
            s["pool_top5"] = [
                {"symbol": r["symbol"], "name": r["name"]}
                for _, r in top.iterrows()
            ]
            # 跟踪对比（简短摘要）
            try:
                d = Tracker(ROOT / "reports").diff_with_previous()
                n_new, n_drop = len(d["new"]), len(d["dropped"])
                if n_new == 0 and n_drop == 0:
                    s["diff_summary"] = "与上次无变化"
                else:
                    s["diff_summary"] = f"+{n_new} / -{n_drop}"
            except Exception:
                s["diff_summary"] = ""
        return s


STATE: AppState | None = None


# ================================================================== HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "graham-desk/0.1"

    # ------------------------------------------------ 输出工具
    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", code)

    def _html(self, text: str, code: int = 200) -> None:
        self._send(text.encode("utf-8"), "text/html; charset=utf-8", code)

    def _error(self, msg: str, code: int = 400) -> None:
        self._json({"ok": False, "error": msg}, code)

    def log_message(self, fmt, *args):  # 安静一点：只打 API 访问
        try:
            msg = fmt % args if args else str(fmt)
        except Exception:
            msg = str(fmt)
        if "/api/" in msg:
            print(f"[vd] {msg}")

    def do_HEAD(self):
        """可达性探测（工具/浏览器预检的 HEAD 请求）：直接 200 响应。"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    # ------------------------------------------------ GET
    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path == "/":
                return self._html(ui.index_html())
            if url.path == "/api/status":
                return self._json(STATE.status())
            if url.path == "/api/reports":
                return self._json({"ok": True,
                                   "reports": self._list_reports()})
            if url.path == "/api/report":
                qs = parse_qs(url.query)
                name = (qs.get("name") or [""])[0]
                return self._serve_report(name)
            return self._error("未知路径", 404)
        except Exception as e:  # noqa: BLE001
            return self._error(f"服务异常：{type(e).__name__}: {e}", 500)

    # ------------------------------------------------ POST
    def do_POST(self):
        url = urlparse(self.path)
        try:
            if url.path == "/api/screen":
                return self._do_screen()
            if url.path == "/api/analyze":
                return self._do_analyze()
            if url.path == "/api/refresh":
                STATE.reload_data()
                return self._json({"ok": True, "message": "数据已重新加载"})
            if url.path == "/api/source":
                payload = json.loads(self.rfile.read(
                    int(self.headers.get("Content-Length", 0))) or b"{}")
                source = str(payload.get("source", "")).strip()
                STATE.switch_source(source)
                hint = ("已切换为实时联网模式：筛选将联网拉取全市场（约 1-2 分钟），"
                        "个股分析实时拉取（约 3 秒）"
                        if source == "akshare" else "已切换为离线演示模式（数据即时可用）")
                return self._json({"ok": True, "source": source, "message": hint})
            return self._error("未知路径", 404)
        except Exception as e:  # noqa: BLE001
            return self._error(f"服务异常：{type(e).__name__}: {e}", 500)

    # ------------------------------------------------ 业务
    def _do_screen(self):
        result = STATE.run_screen()
        pool_rows = []
        # 前端表格只展示前 100 家（全量在报告文件中，防止页面卡顿）
        for _, r in result.passed.head(100).iterrows():
            pool_rows.append({
                "rank": int(r["rank"]), "symbol": r["symbol"], "name": r["name"],
                "industry": r["industry"], "score": float(r["score_total"]),
                "grade": r["grade"], "roe": float(r["roe_5y_avg"]),
                "ocf": float(r["ocf_profit_ratio"]), "dy": float(r["dividend_yield"]),
                "pe": float(r["pe"]), "yellow": int(r["flags_yellow"]),
            })
        return self._json({
            "ok": True,
            "funnel": [{"label": k, "count": v} for k, v in result.funnel.items()],
            "pool": pool_rows,
            "pool_total": int(len(result.passed)),
            "n_rejected": int(len(result.rejected)),
            "report_name": f"screen_{time.strftime('%Y%m%d')}.md",
            "data_notes": result.data_notes,
        })

    def _do_analyze(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")
        symbol = str(payload.get("symbol", "")).strip()
        if not symbol:
            return self._error("缺少 symbol")
        out = STATE.analyze(symbol)
        out["ok"] = True
        return self._json(out)

    def _list_reports(self) -> list[dict]:
        rep_dir = ROOT / "reports"
        if not rep_dir.exists():
            try:
                rep_dir.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
        items = []
        for p in sorted(rep_dir.glob("*.md"),
                        key=lambda x: x.stat().st_mtime, reverse=True):
            is_screen = p.name.startswith("screen_")
            items.append({
                "name": p.name,
                "title": ("筛选报告 · " + p.stem.replace("screen_", ""))
                if is_screen else ("个股报告 · " + p.stem.replace("company_", "")),
                "type": "screen" if is_screen else "company",
                "mtime": time.strftime("%m-%d %H:%M",
                                       time.localtime(p.stat().st_mtime)),
                "size_kb": round(p.stat().st_size / 1024, 1),
            })
        return items

    def _serve_report(self, name: str):
        # 安全：只允许 reports/ 目录下的 .md 文件（防路径穿越）
        if not name or "/" in name or "\\" in name or not name.endswith(".md"):
            return self._error("非法文件名", 400)
        path = (ROOT / "reports" / name).resolve()
        if not str(path).startswith(str((ROOT / "reports").resolve())):
            return self._error("非法路径", 400)
        if not path.exists():
            return self._error("报告不存在", 404)
        md = path.read_text(encoding="utf-8")
        title = path.stem.replace("company_", "").replace("screen_", "")
        return self._json({"ok": True, "title": title,
                           "html": render.md_to_html(md)})


# ================================================================== 启动
def _pick_port(preferred: int) -> int:
    import socket
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("找不到空闲端口")


def main() -> None:
    global STATE
    ap = argparse.ArgumentParser(description="北民大格雷厄姆的 ValueDesk 本地服务")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--source", default=None, choices=["mock", "akshare"],
                    help="覆盖数据源")
    ap.add_argument("--open-browser", action="store_true", default=True)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    STATE = AppState(source_override=args.source)
    port = _pick_port(args.port)
    url = f"http://127.0.0.1:{port}"

    # 预热：先加载数据，网页一打开就能用
    try:
        STATE.ensure_data()
    except Exception as e:  # noqa: BLE001
        print(f"[vd] ⚠️ 数据加载失败（界面仍会启动，可在页面上重试）：{e}")

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("=" * 56)
    print("  北民大格雷厄姆的 ValueDesk · 价值投资分析工作台")
    print(f"  服务地址: {url}")
    print(f"  数据源:   {STATE.cfg.data.source}")
    print("  停止服务: 在本窗口按 Ctrl+C（或直接关闭窗口）")
    print("=" * 56)

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[vd] 服务已停止")


if __name__ == "__main__":
    main()
