"""单页界面（零外部资源：CSS/JS 全内嵌，离线可用）。

五个视图：仪表盘 / 标的筛选 / 个股分析 / 报告库 / 说明与配置。
"""

_INDEX = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>北民大格雷厄姆的 ValueDesk · 价值投资分析工作台</title>
<style>
:root{
  --bg:#f5f6f8; --card:#fff; --border:#e6e8ec; --text:#15171c; --muted:#6f7480;
  --primary:#2f5bea; --primary-weak:#edf2fe; --primary-dark:#2246bb;
  --red:#cf3434; --red-weak:#fdeeee; --amber:#b5791a; --amber-weak:#fdf5e7;
  --green:#2c7a52; --green-weak:#ebf5ef; --gray:#6f7480; --gray-weak:#f0f1f4;
  --shadow:0 1px 2px rgba(16,24,40,.05),0 1px 3px rgba(16,24,40,.05);
  --radius:10px;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  background:var(--bg);color:var(--text);font-size:14px;line-height:1.55;
  -webkit-font-smoothing:antialiased;
}
.shell{display:flex;min-height:100vh}
/* ---------------- 侧边栏 ---------------- */
.sidebar{
  width:216px;flex-shrink:0;background:var(--card);border-right:1px solid var(--border);
  display:flex;flex-direction:column;position:sticky;top:0;height:100vh;
}
.brand{padding:20px 18px 14px;border-bottom:1px solid var(--border)}
.brand b{font-size:15px;letter-spacing:.2px;line-height:1.45;display:block}
.brand b::first-letter{color:var(--primary)}
.brand span{display:block;font-size:12px;color:var(--muted);margin-top:2px}
nav{padding:12px 10px;flex:1}
nav a{
  display:block;padding:9px 12px;border-radius:8px;color:var(--text);text-decoration:none;
  font-size:13.5px;margin-bottom:2px;cursor:pointer;user-select:none;
}
nav a:hover{background:var(--gray-weak)}
nav a.active{background:var(--primary-weak);color:var(--primary-dark);font-weight:600}
.sidebar-foot{
  padding:14px 20px;border-top:1px solid var(--border);font-size:12px;color:var(--muted);
}
#src-badge{
  display:inline-block;padding:1px 8px;border-radius:20px;background:var(--gray-weak);
  font-weight:600;color:var(--text);
}
/* ---------------- 主区 ---------------- */
main{flex:1;padding:28px 34px;max-width:1200px}
.page{display:none}
.page.active{display:block;animation:fade .18s ease}
@keyframes fade{from{opacity:0;transform:translateY(3px)}to{opacity:1;transform:none}}
h1.page-title{font-size:20px;margin-bottom:4px}
.page-sub{color:var(--muted);font-size:13px;margin-bottom:22px}
.card{
  background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:18px 20px;box-shadow:var(--shadow);margin-bottom:16px;
}
.card h3{font-size:14.5px;margin-bottom:10px}
.grid{display:grid;gap:14px}
.grid-4{grid-template-columns:repeat(4,1fr)}
.grid-2{grid-template-columns:1fr 1fr}
.stat{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:14px 16px;box-shadow:var(--shadow)}
.stat .k{font-size:12px;color:var(--muted)}
.stat .v{font-size:22px;font-weight:700;margin-top:2px;font-variant-numeric:tabular-nums}
.stat .s{font-size:12px;color:var(--muted);margin-top:2px}
/* ---------------- 控件 ---------------- */
.btn{
  display:inline-flex;align-items:center;gap:6px;border:1px solid var(--primary);
  background:var(--primary);color:#fff;border-radius:8px;padding:9px 18px;font-size:14px;
  cursor:pointer;font-weight:600;transition:background .12s;
}
.btn:hover{background:var(--primary-dark)}
.btn:disabled{opacity:.55;cursor:default}
.btn.sec{background:#fff;color:var(--text);border-color:var(--border)}
.btn.sec:hover{background:var(--gray-weak)}
.btn.sm{padding:5px 12px;font-size:12.5px;font-weight:500}
input[type=text]{
  border:1px solid var(--border);border-radius:8px;padding:9px 12px;font-size:14px;
  width:200px;outline:none;background:#fff;font-family:inherit;
}
input[type=text]:focus{border-color:var(--primary);box-shadow:0 0 0 3px var(--primary-weak)}
.chip{
  display:inline-block;padding:3px 10px;border-radius:20px;background:var(--gray-weak);
  font-size:12.5px;cursor:pointer;margin:2px 4px 2px 0;border:1px solid transparent;
}
.chip:hover{border-color:var(--primary);color:var(--primary-dark)}
.muted{color:var(--muted)} .small{font-size:12.5px}
.mt{margin-top:12px} .mb{margin-bottom:12px} .ml{margin-left:10px}
.hidden{display:none!important}
/* ---------------- 徽章 ---------------- */
.badge{display:inline-block;padding:1.5px 9px;border-radius:6px;font-size:12px;font-weight:700}
.badge.verdict-watch{background:var(--red-weak);color:var(--red)}
.badge.verdict-observe{background:var(--amber-weak);color:var(--amber)}
.badge.verdict-avoid{background:var(--gray-weak);color:var(--gray)}
.badge.grade-A{background:var(--red-weak);color:var(--red)}
.badge.grade-B{background:var(--primary-weak);color:var(--primary-dark)}
.badge.grade-C{background:var(--amber-weak);color:var(--amber)}
.badge.grade-D{background:var(--gray-weak);color:var(--gray)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:4px;vertical-align:1px}
.dot-red{background:#e05252}.dot-yellow{background:#e0a52e}.dot-green{background:#3f9c68}
/* ---------------- 漏斗 ---------------- */
.funnel .row{display:flex;align-items:center;gap:12px;margin-bottom:7px}
.funnel .label{width:150px;flex-shrink:0;font-size:13px;color:var(--muted);text-align:right}
.funnel .bar{height:22px;border-radius:6px;background:linear-gradient(90deg,var(--primary),#6c8df2);
  min-width:2px;transition:width .5s ease;display:flex;align-items:center;justify-content:flex-end;
  padding-right:8px;color:#fff;font-size:12px;font-weight:600}
/* ---------------- 表格 ---------------- */
.table-wrap{overflow-x:auto;border:1px solid var(--border);border-radius:var(--radius)}
table{border-collapse:collapse;width:100%;font-size:13px}
th{background:#fafbfc;text-align:left;padding:9px 12px;color:var(--muted);font-weight:600;
  border-bottom:1px solid var(--border);white-space:nowrap;font-size:12.5px}
td{padding:8px 12px;border-bottom:1px solid #f0f1f4;font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:none}
tbody tr:hover{background:#f9fafb}
tbody tr{cursor:pointer}
tbody tr.no-click{cursor:default}
/* ---------------- 报告渲染区 ---------------- */
.report-html{font-size:13.5px;line-height:1.7}
.report-html h1{font-size:19px;margin:14px 0 8px}
.report-html h2{font-size:16px;margin:20px 0 8px;padding-top:12px;border-top:1px solid var(--border)}
.report-html h3{font-size:14px;margin:14px 0 6px}
.report-html p{margin:6px 0}
.report-html ul,.report-html ol{margin:6px 0 6px 22px}
.report-html li{margin:3px 0}
.report-html blockquote{
  border-left:3px solid var(--primary);background:var(--primary-weak);
  padding:8px 14px;border-radius:0 8px 8px 0;margin:8px 0;color:#37415c;font-size:13px;
}
.report-html hr{border:none;border-top:1px solid var(--border);margin:16px 0}
.report-html code{background:var(--gray-weak);padding:1px 5px;border-radius:4px;font-size:12.5px}
.report-html pre.code-block{background:#1c2130;color:#e8ecf5;padding:12px 14px;border-radius:8px;
  overflow-x:auto;font-size:12.5px;margin:8px 0}
.report-html pre.code-block code{background:none;color:inherit;padding:0}
.report-html a{color:var(--primary)}
.report-html table{border-collapse:collapse;width:100%;font-size:12.5px;margin:8px 0}
.report-html th{background:#fafbfc;padding:7px 10px;border:1px solid var(--border)}
.report-html td{padding:6px 10px;border:1px solid var(--border);font-variant-numeric:tabular-nums}
/* ---------------- 结论卡 ---------------- */
.verdict-card{display:flex;align-items:center;gap:18px;padding:18px 20px;
  border-radius:var(--radius);border:1px solid var(--border);background:var(--card);
  box-shadow:var(--shadow);margin-bottom:16px}
.verdict-card .big{font-size:26px;font-weight:800;flex-shrink:0}
.verdict-card .why{font-size:13px;color:var(--muted)}
.vc-watch{border-left:5px solid var(--red)} .vc-watch .big{color:var(--red)}
.vc-observe{border-left:5px solid var(--amber)} .vc-observe .big{color:var(--amber)}
.vc-avoid{border-left:5px solid var(--gray)} .vc-avoid .big{color:var(--gray)}
/* ---------------- 报告列表 ---------------- */
.report-item{display:flex;align-items:center;gap:12px;padding:11px 14px;border:1px solid var(--border);
  border-radius:8px;margin-bottom:8px;background:#fff;cursor:pointer}
.report-item:hover{border-color:var(--primary)}
.report-item .tag{flex-shrink:0;font-size:11px;font-weight:700;padding:2px 8px;border-radius:5px;
  background:var(--primary-weak);color:var(--primary-dark)}
.report-item .tag.screen{background:var(--amber-weak);color:var(--amber)}
.report-item .name{flex:1;font-size:13.5px}
.report-item .meta{font-size:12px;color:var(--muted)}
/* ---------------- loading / toast ---------------- */
.spinner{display:inline-block;width:15px;height:15px;border:2px solid rgba(255,255,255,.4);
  border-top-color:#fff;border-radius:50%;animation:spin .7s linear infinite;vertical-align:-3px}
@keyframes spin{to{transform:rotate(360deg)}}
#toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%) translateY(80px);
  background:#22262f;color:#fff;padding:10px 18px;border-radius:9px;font-size:13px;
  opacity:0;transition:all .25s ease;z-index:99;max-width:70vw}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
#toast.err{background:#8f2d2d}
.footer-note{color:var(--muted);font-size:12px;margin-top:26px;line-height:1.7}
</style>
</head>
<body>
<div class="shell">
  <aside class="sidebar">
    <div class="brand">
      <b>北民大格雷厄姆的 ValueDesk</b>
      <span>价值投资分析工作台</span>
    </div>
    <nav id="nav">
      <a data-view="dashboard" class="active">仪表盘</a>
      <a data-view="screen">标的筛选</a>
      <a data-view="analyze">个股分析</a>
      <a data-view="reports">报告库</a>
      <a data-view="about">说明与配置</a>
    </nav>
    <div class="sidebar-foot">数据源 <span id="src-badge">…</span><br>
      <span id="run-hint" class="small"></span>
    </div>
  </aside>

  <main>
    <!-- ================= 仪表盘 ================= -->
    <section class="page active" id="view-dashboard">
      <h1 class="page-title">仪表盘</h1>
      <div class="page-sub">持续寻找标的 · 财报与年报综合判断</div>
      <div class="grid grid-4 mb">
        <div class="stat"><div class="k">数据模式</div><div class="v" id="d-source">—</div>
          <div class="s" id="d-source-sub">—</div>
          <div style="margin-top:6px">
            <span class="chip" onclick="switchSource('mock')">离线演示</span>
            <span class="chip" onclick="switchSource('akshare')">实时联网</span>
          </div></div>
        <div class="stat"><div class="k">公司池</div><div class="v" id="d-firms">—</div>
          <div class="s">可分析的公司数量</div></div>
        <div class="stat"><div class="k">候选池</div><div class="v" id="d-pool">—</div>
          <div class="s" id="d-pool-sub">尚未运行筛选</div></div>
        <div class="stat"><div class="k">跟踪变化</div><div class="v" id="d-diff">—</div>
          <div class="s" id="d-diff-sub">与上次快照对比</div></div>
      </div>
      <div class="card">
        <h3>快捷操作</h3>
        <div class="mt">
          <button class="btn" onclick="go('screen', true)">运行全市场筛选</button>
          <button class="btn sec ml" onclick="go('analyze')">个股深度分析</button>
          <button class="btn sec ml" onclick="refreshData()">刷新数据</button>
        </div>
      </div>
      <div class="card">
        <h3>最近筛选摘要</h3>
        <div id="d-last-screen" class="muted small">运行一次筛选后，这里会显示漏斗与候选池概况。</div>
      </div>
    </section>

    <!-- ================= 筛选 ================= -->
    <section class="page" id="view-screen">
      <h1 class="page-title">标的筛选</h1>
      <div class="page-sub">五层漏斗：硬性初筛 → 盈利质量 → 排雷 → 估值 → 五维评分</div>
      <div class="card">
        <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
          <button class="btn" id="btn-screen" onclick="runScreen()">开始筛选</button>
          <span class="muted small" id="screen-status">点击运行（离线模式约 1–2 秒；实时联网模式约 1–2 分钟）</span>
        </div>
      </div>
      <div id="funnel-box" class="card hidden">
        <h3>筛选漏斗</h3>
        <div class="funnel" id="funnel"></div>
      </div>
      <div id="pool-box" class="card hidden">
        <h3>候选池 <span class="muted small" id="pool-count"></span></h3>
        <div class="muted small mb">点击任意一行 → 直接生成该公司的深度分析报告</div>
        <div class="table-wrap" id="pool-table"></div>
        <div class="muted small" id="pool-notes" style="margin-top:8px"></div>
      </div>
    </section>

    <!-- ================= 分析 ================= -->
    <section class="page" id="view-analyze">
      <h1 class="page-title">个股深度分析</h1>
      <div class="page-sub">杜邦拆解 · 亮点疑点 · 排雷清单 · 年报核查任务</div>
      <div class="card">
        <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
          <input type="text" id="analyze-symbol" placeholder="输入股票代码，如 600006"
                 onkeydown="if(event.key==='Enter')runAnalyze()">
          <button class="btn" id="btn-analyze" onclick="runAnalyze()">分析</button>
          <span class="muted small">提示：先运行筛选，可从候选池快捷选择</span>
        </div>
        <div class="mt" id="quick-chips"></div>
      </div>
      <div id="analyze-result"></div>
    </section>

    <!-- ================= 报告库 ================= -->
    <section class="page" id="view-reports">
      <h1 class="page-title">报告库</h1>
      <div class="page-sub">所有生成的筛选报告与个股分析报告（Markdown 原件保存在 reports/）</div>
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <h3 id="reports-title" style="margin:0">全部报告</h3>
          <button class="btn sec sm" onclick="loadReports()">刷新列表</button>
        </div>
        <div class="mt" id="report-list"></div>
      </div>
      <div class="card hidden" id="report-viewer-box">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <h3 id="report-viewer-title" style="margin:0">—</h3>
          <button class="btn sec sm" onclick="closeReport()">关闭</button>
        </div>
        <div class="report-html mt" id="report-viewer"></div>
      </div>
    </section>

    <!-- ================= 说明 ================= -->
    <section class="page" id="view-about">
      <h1 class="page-title">说明与配置</h1>
      <div class="page-sub">系统结构 · 模块接口 · 参数说明</div>
      <div class="card">
        <h3>数据模式（两种，随时切换）</h3>
        <p class="small mt">· <b>离线演示</b>：内置 30 家演示公司（含五类埋雷样本），秒级可用，用于熟悉系统与测试排雷逻辑；</p>
        <p class="small">· <b>实时联网</b>：筛选时联网拉取全市场年报数据（约 1–2 分钟/次）；个股分析实时拉取该股最新财务与估值（约 3 秒）——数据始终为最新披露口径，<b>无需维护本地数据库</b>；</p>
        <p class="small">· 在仪表盘「数据模式」卡片点选切换，选择自动保存，重启后保持。</p>
      </div>
      <div class="card">
        <h3>启动方式</h3>
        <p class="small mt">· 桌面双击 <b>启动ValueDesk.command</b>：自动启动本地服务并打开本页面；</p>
        <p class="small">· 命令行：<code>python app/server.py</code>（可选 <code>--port 8787</code>、<code>--source akshare</code>）；</p>
        <p class="small">· 传统命令行入口仍然可用：<code>python scripts/screen.py</code>、<code>python scripts/analyze.py 600006</code>。</p>
      </div>
      <div class="card">
        <h3>模块接口与依赖关系</h3>
        <pre class="code-block" style="font-size:12px">data(数据层)
  └─→ metrics(指标) ──→ screening(漏斗+排雷) ──→ scoring(评分)
                                  │
  analysis(分析) ←───────┬────────┘
    └─ report(报告)      │
         └─ journal(跟踪) │
                          ▼
        app/server.py(本地服务) ──→ app/ui.py(界面)
依赖方向单向：data → metrics → screening → scoring；analysis 复用以上全部；
server/ui 只调用既有模块，不反向依赖。</pre>
      </div>
      <div class="card">
        <h3>关键配置（config/default.yaml 可改）</h3>
        <div class="table-wrap"><table id="cfg-table">
          <thead><tr><th>参数</th><th>默认</th><th>含义</th></tr></thead>
          <tbody>
            <tr class="no-click"><td>screen.min_roe_latest</td><td>8%</td><td>最新一年 ROE 下限</td></tr>
            <tr class="no-click"><td>screen.min_roe_5y_avg</td><td>10%</td><td>近 5 年平均 ROE 下限</td></tr>
            <tr class="no-click"><td>vetting.ocf_profit_ratio_red</td><td>0.5</td><td>利润含金量红灯线（5年累计现金流/净利）</td></tr>
            <tr class="no-click"><td>vetting.debt_ratio_warn</td><td>70%</td><td>资产负债率黄旗线</td></tr>
            <tr class="no-click"><td>vetting.goodwill_ratio_warn</td><td>30%</td><td>商誉/净资产黄旗线</td></tr>
            <tr class="no-click"><td>scoring.weights</td><td>30/20/20/15/15</td><td>五维评分权重（质量/安全/现金流/成长/估值）</td></tr>
            <tr class="no-click"><td>data.source</td><td>mock</td><td>mock 离线演示 / akshare 真实数据</td></tr>
          </tbody>
        </table></div>
      </div>
      <div class="footer-note">
        ⚠️ 本系统输出为研究辅助，不构成投资建议。mock 数据仅用于演示流程；
        真实数据模式下请以交易所公告与年报原文为准。
      </div>
    </section>
  </main>
</div>
<div id="toast"></div>

<script>
/* ================= 工具 ================= */
const $ = (s) => document.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

let toastTimer = null;
function toast(msg, isErr) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = isErr ? "show err" : "show";
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.className = "", 2600);
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error("HTTP " + res.status);
  return res.json();
}

/* ================= 导航 ================= */
function go(view, runNow) {
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  $("#view-" + view).classList.add("active");
  document.querySelectorAll("#nav a").forEach(a =>
    a.classList.toggle("active", a.dataset.view === view));
  if (view === "reports") loadReports();
  if (view === "screen" && runNow) runScreen();
  window.scrollTo({top: 0});
}
document.querySelectorAll("#nav a").forEach(a =>
  a.addEventListener("click", () => go(a.dataset.view)));

/* ================= 状态 ================= */
async function refreshStatus() {
  try {
    const s = await api("/api/status");
    $("#src-badge").textContent = s.source === "akshare" ? "实时联网" : "离线";
    $("#d-source").textContent = s.source === "akshare" ? "实时联网" : "离线演示";
    $("#d-source-sub").textContent = s.source === "akshare"
      ? "akshare 免费通道 · 最新披露口径"
      : "内置数据（含埋雷样本）";
    $("#d-firms").textContent = s.n_companies ? s.n_companies + " 家" : "待加载";
    $("#d-pool").textContent = s.pool_size ?? "—";
    $("#d-pool-sub").textContent = s.screen_time
      ? "最近筛选 " + s.screen_time : "尚未运行筛选";
    if (s.diff_summary) {
      $("#d-diff").textContent = s.diff_summary;
      $("#d-diff-sub").textContent = "与上次快照对比";
    } else {
      $("#d-diff").textContent = "—";
      $("#d-diff-sub").textContent = "暂无历史快照";
    }
    if (s.last_funnel) {
      const f = s.last_funnel.map(x =>
        `${esc(x.label)} <b>${x.count}</b>`).join(" → ");
      $("#d-last-screen").innerHTML = f;
    }
    if (s.pool_top5 && s.pool_top5.length) {
      $("#quick-chips").innerHTML = "候选池快捷分析： " + s.pool_top5.map(r =>
        `<span class="chip" onclick="quickAnalyze('${esc(r.symbol)}')">${esc(r.symbol)} ${esc(r.name)}</span>`
      ).join("");
    }
  } catch (e) {
    $("#src-badge").textContent = "离线";
  }
}

async function switchSource(source) {
  try {
    toast("正在切换数据模式…");
    const r = await api("/api/source", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({source})
    });
    toast(r.message || "已切换");
    refreshStatus();
  } catch (e) { toast("切换失败：" + e.message, true); }
}

async function refreshData() {
  try {
    toast("正在刷新数据…");
    const s = await api("/api/refresh", {method: "POST"});
    toast(s.message || "数据已刷新");
    refreshStatus();
  } catch (e) { toast("刷新失败：" + e.message, true); }
}

/* ================= 筛选 ================= */
async function runScreen() {
  const btn = $("#btn-screen");
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span> 筛选中…';
  $("#screen-status").textContent = "正在执行五层漏斗…";
  try {
    const r = await api("/api/screen", {method: "POST"});
    if (!r.ok) throw new Error(r.error || "筛选失败");
    renderFunnel(r.funnel);
    renderPool(r);
    $("#screen-status").textContent =
      `完成：候选池 ${r.pool_total ?? r.pool.length} 家，剔除 ${r.n_rejected} 家（报告：${r.report_name}）`;
    toast("筛选完成");
    refreshStatus();
  } catch (e) {
    $("#screen-status").textContent = "失败：" + e.message;
    toast("筛选失败：" + e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "重新筛选";
  }
}

function renderFunnel(funnel) {
  const box = $("#funnel-box"), el = $("#funnel");
  box.classList.remove("hidden");
  const max = Math.max(...funnel.map(x => x.count), 1);
  el.innerHTML = funnel.map(x => `
    <div class="row">
      <div class="label">${esc(x.label)}</div>
      <div class="bar" style="width:${Math.max(x.count / max * 100, 2)}%">${x.count}</div>
    </div>`).join("");
}

function renderPool(r) {
  const box = $("#pool-box");
  box.classList.remove("hidden");
  const total = r.pool_total ?? r.pool.length;
  $("#pool-count").textContent = total > r.pool.length
    ? `共 ${total} 家（展示前 ${r.pool.length} 名）` : `共 ${total} 家`;
  const head = `<thead><tr>
    <th>排名</th><th>代码</th><th>名称</th><th>行业</th><th>综合分</th><th>评级</th>
    <th>5年ROE</th><th>含金量</th><th>股息率</th><th>PE</th><th>黄旗</th></tr></thead>`;
  const rows = r.pool.map(v => `<tr onclick="quickAnalyze('${esc(v.symbol)}')">
    <td>${v.rank}</td><td>${esc(v.symbol)}</td><td>${esc(v.name)}</td>
    <td>${esc(v.industry)}</td>
    <td><b>${Number(v.score).toFixed(0)}</b></td>
    <td><span class="badge grade-${esc(v.grade)}">${esc(v.grade)}</span></td>
    <td>${fmtPct(v.roe)}</td><td>${Number(v.ocf).toFixed(2)}</td>
    <td>${fmtPct(v.dy, 2)}</td><td>${v.pe != null && !isNaN(v.pe) ? Number(v.pe).toFixed(1) : "—"}</td>
    <td>${v.yellow ? '<span class="dot dot-yellow"></span>' + v.yellow : "0"}</td></tr>`).join("");
  $("#pool-table").innerHTML = `<table>${head}<tbody>${rows}</tbody></table>`;
  const notesEl = $("#pool-notes");
  if (r.data_notes && r.data_notes.length) {
    notesEl.innerHTML = "数据覆盖说明（以下规则因数据源限制已跳过）：<br>" +
      r.data_notes.map(n => "· " + esc(n)).join("<br>");
  } else {
    notesEl.innerHTML = "";
  }
}

const fmtPct = (v, d = 1) => (v == null || isNaN(v)) ? "—" : (v * 100).toFixed(d) + "%";

/* ================= 分析 ================= */
function quickAnalyze(symbol) {
  go("analyze");
  $("#analyze-symbol").value = symbol;
  runAnalyze();
}

async function runAnalyze() {
  const symbol = $("#analyze-symbol").value.trim();
  if (!symbol) { toast("请输入股票代码", true); return; }
  const btn = $("#btn-analyze");
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span> 分析中…';
  $("#analyze-result").innerHTML =
    '<div class="card"><span class="spinner" style="border-color:#ccd;border-top-color:#2f5bea"></span> 正在生成深度分析报告…</div>';
  try {
    const r = await api("/api/analyze", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({symbol})
    });
    if (!r.ok) throw new Error(r.error || "分析失败");
    const vc = r.verdict === "关注" ? "vc-watch" :
               r.verdict === "观察" ? "vc-observe" : "vc-avoid";
    const vBadge = r.verdict === "关注" ? "verdict-watch" :
                   r.verdict === "观察" ? "verdict-observe" : "verdict-avoid";
    $("#analyze-result").innerHTML = `
      <div class="verdict-card ${vc}">
        <div class="big">${esc(r.verdict)}</div>
        <div>
          <div style="font-weight:700">
            ${esc(r.symbol)} ${esc(r.name)}
            <span class="badge ${vBadge} ml">${esc(r.verdict)}</span>
            <span class="badge grade-${esc(r.grade)} ml">${esc(r.grade)} 级 · ${Number(r.score).toFixed(0)} 分</span>
          </div>
          <div class="why">${esc(r.reason)}</div>
        </div>
      </div>
      <div class="card"><div class="report-html">${r.html}</div></div>`;
    toast("分析完成：" + r.symbol);
  } catch (e) {
    $("#analyze-result").innerHTML =
      `<div class="card" style="color:#b03030">分析失败：${esc(e.message)}</div>`;
    toast("分析失败：" + e.message, true);
  } finally {
    btn.disabled = false; btn.textContent = "分析";
  }
}

/* ================= 报告库 ================= */
async function loadReports() {
  try {
    const r = await api("/api/reports");
    if (!r.reports.length) {
      $("#report-list").innerHTML = '<div class="muted small">暂无报告。先运行一次筛选或个股分析。</div>';
      return;
    }
    $("#report-list").innerHTML = r.reports.map(f => `
      <div class="report-item" onclick="openReport('${esc(f.name)}')">
        <span class="tag ${f.type === 'screen' ? 'screen' : ''}">${f.type === 'screen' ? "筛选" : "个股"}</span>
        <span class="name">${esc(f.title)}</span>
        <span class="meta">${esc(f.mtime)} · ${f.size_kb} KB</span>
      </div>`).join("");
  } catch (e) { toast("读取报告列表失败", true); }
}

async function openReport(name) {
  try {
    const r = await api("/api/report?name=" + encodeURIComponent(name));
    $("#report-viewer-box").classList.remove("hidden");
    $("#report-viewer-title").textContent = r.title;
    $("#report-viewer").innerHTML = r.html;
    $("#report-viewer-box").scrollIntoView({behavior: "smooth", block: "start"});
  } catch (e) { toast("打开报告失败", true); }
}
function closeReport() { $("#report-viewer-box").classList.add("hidden"); }

/* ================= 启动 ================= */
refreshStatus();
</script>
</body>
</html>
"""


def index_html() -> str:
    return _INDEX
