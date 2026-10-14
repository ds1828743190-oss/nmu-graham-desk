# 架构说明 · 北民大格雷厄姆的 ValueDesk

> 本文档回答：**系统由哪些部分组成、各部分如何接口、依赖方向是什么、如何启动与扩展。**

---

## 一、系统全景

```
┌───────────────────────────────────────────────────────────────┐
│  桌面启动层                                                     │
│  启动ValueDesk.command（项目内/桌面快捷方式）                     │
│    └─ 环境自检 → 启动 app/server.py → 自动打开浏览器              │
├───────────────────────────────────────────────────────────────┤
│  界面层  app/                                                   │
│  ┌─────────────┐   ┌──────────────┐   ┌────────────────┐      │
│  │ ui.py       │──▶│ server.py    │──▶│ render.py      │      │
│  │ 单页界面     │◀──│ 统一 API     │   │ MD→HTML 渲染    │      │
│  │ (CSS/JS内嵌) │   │ (标准库HTTP) │   │                │      │
│  └─────────────┘   └──────┬───────┘   └────────────────┘      │
├───────────────────────────┼───────────────────────────────────┤
│  核心逻辑层  src/vd/       ▼                                     │
│  ┌────────┐  ┌─────────┐  ┌──────────┐  ┌─────────┐          │
│  │ data   │─▶│ metrics │─▶│ screening│─▶│ scoring │          │
│  │ 数据层  │  │ 指标    │  │ 漏斗+排雷 │  │ 五维评分 │          │
│  └────────┘  └─────────┘  └────┬─────┘  └─────────┘          │
│  ┌──────────────┐  ┌───────────┴──┐  ┌─────────────┐          │
│  │ analysis     │  │ report       │  │ journal     │          │
│  │ 个股分析     │─▶│ 报告生成      │  │ 候选池跟踪   │          │
│  │ +年报核查清单 │  │ (Markdown)   │  │ (快照对比)   │          │
│  └──────────────┘  └──────────────┘  └─────────────┘          │
├───────────────────────────────────────────────────────────────┤
│  命令行入口（保留）  scripts/                                    │
│  screen.py（筛选） / analyze.py（分析）                          │
└───────────────────────────────────────────────────────────────┘
          ▲
          │ 配置：config/default.yaml（全部阈值/权重，唯一参数入口）
```

---

## 二、模块接口一览（统一契约）

每个模块都是**纯函数式接口**（输入 → 输出，不维护全局状态）：

| 模块 | 关键接口 | 输入 | 输出 | 依赖 |
|---|---|---|---|---|
| `config` | `load_config(path?)` | YAML 路径（可选） | `AppConfig` | 无 |
| `data` | `load_financials(cfg)` | AppConfig | `DataFrame`（公司×年 长表） | config |
| `metrics` | `compute_company_metrics(df, years)` | 单公司数据 | `dict`（全部派生指标） | 无 |
| `metrics` | `metrics_for_all(financials)` | 全量数据 | 宽表（一行一公司） | 无 |
| `screening` | `screen(financials, cfg)` | 数据+配置 | `ScreenResult{passed, rejected, funnel}` | metrics |
| `screening` | `vet_company(m, cfg)` | 单公司指标 | `list[Flag]`（红旗列表） | config |
| `scoring` | `score_company(m, cfg)` | 单公司指标 | `dict`（五维分+综合分+评级） | config |
| `analysis` | `analyze_company(symbol, df, cfg)` | 代码+数据 | `CompanyAnalysis`（结论/亮点/疑点/核查清单） | metrics, screening, scoring |
| `report` | `screen_report_md(...)` / `company_report_md(...)` | 结果对象 | Markdown 文件路径 | — |
| `journal` | `Tracker().save_snapshot()` / `diff_with_previous()` | ScreenResult | 快照文件 / 差异 dict | — |
| `app/render` | `md_to_html(md)` | Markdown 文本 | HTML 片段 | 无 |
| `app/ui` | `index_html()` | 无 | 完整页面 HTML | 无 |
| `app/server` | HTTP 服务（见下） | HTTP 请求 | JSON/HTML | 以上全部 |

**依赖方向是单向的**，不允许反向引用：
```
data → metrics → screening → scoring → analysis → report
                                        │
                               app/server ──▶ 调用以上全部
```
（`app/` 层只调用核心层，核心层永远不知道界面层的存在。）

---

## 三、统一 API（server.py 暴露）

| 方法 | 路径 | 输入 | 输出 |
|---|---|---|---|
| GET | `/` | — | 单页界面 |
| GET | `/api/status` | — | 数据源 / 公司数 / 候选池 / 跟踪变化 / 漏斗摘要 |
| POST | `/api/screen` | — | 漏斗数组 + 候选池数组 + 剔除数 + 报告名 |
| POST | `/api/analyze` | `{"symbol": "600006"}` | 结论 + 评级 + 分数 + 报告 HTML |
| GET | `/api/reports` | — | 报告列表（名称/类型/时间/大小） |
| GET | `/api/report?name=...` | 文件名 | 渲染后的 HTML（防路径穿越） |
| POST | `/api/refresh` | — | 重新加载数据 |

约定：
- 全部返回 JSON（`{ok: true/false, ...}`），错误带 `error` 字段；
- 只监听 `127.0.0.1`，不对外网暴露；
- 数据在服务内存中缓存（首次访问预热），`/api/refresh` 强制重载。

---

## 四、桌面启动链路

```
用户双击「启动ValueDesk.command」
  │
  ├─ ① 定位项目目录（脚本自身所在目录，随项目移动）
  ├─ ② 查找 Python（优先托管 venv → python3 → 常见路径）
  ├─ ③ 依赖自检（pandas/numpy/pyyaml，缺失则自动用清华镜像安装）
  ├─ ④ 启动 app/server.py --open-browser
  │      ├─ 预热数据（mock 秒级）
  │      ├─ 端口探测（8787 起，被占用自动 +1）
  │      └─ 自动打开浏览器
  └─ ⑤ 用户关闭终端窗口 / Ctrl+C 即停止
```

**零配置保证**：
- 默认 `mock` 数据源 —— 不联网、不装 akshare 也能完整使用全部功能；
- 阈值全部有出厂默认值（`src/vd/config.py`），`config/default.yaml` 是可选覆盖；
- 桌面快捷方式已创建：`~/Desktop/启动ValueDesk.command`（项目移动时改其中 `PROJECT_DIR` 一行即可）。

---

## 五、数据流转（一次典型使用的完整链路）

```
① 用户点击「开始筛选」
② POST /api/screen
③ server.AppState.run_screen()
     ├─ ensure_data()        # 首次加载并缓存财务数据集
     ├─ screening.screen()
     │    ├─ metrics_for_all()            # 30 家 × 5 年 → 指标宽表
     │    ├─ ①硬性初筛 → ②盈利质量筛 → ③排雷(vet_company) → ④估值筛
     │    └─ ⑤score_company() 打分排序
     ├─ report.screen_report_md()          # 落盘 reports/screen_*.md
     └─ journal.Tracker.save_snapshot()    # 落盘候选池快照（供下次对比）
④ 返回 JSON（漏斗 + 候选池）→ 界面渲染
⑤ 用户点击候选池某一行
⑥ POST /api/analyze {symbol}
     ├─ analysis.analyze_company()         # 结论/亮点/疑点/年报核查清单
     ├─ report.company_report_md()         # 落盘 reports/company_*.md
     └─ render.md_to_html()                # Markdown → HTML
⑦ 界面展示结论卡 + 完整报告
```

---

## 六、扩展点（保持架构约束的前提下）

| 想做什么 | 只改哪里 | 约束 |
|---|---|---|
| 调整筛选阈值 / 权重 | `config/default.yaml` | 无需改代码 |
| 新增排雷规则 | `screening.vet_company` + config | 必须输出可读的 Flag（触发值 vs 阈值） |
| 新增年报核查规则 | `analysis._CHECKLIST_RULES` | 必须包含【去哪查 + 查什么】 |
| 换数据源（akshare/其他） | `data.load_financials` | 输出必须符合统一长表结构 |
| 新增界面功能 | `app/ui.py` + `app/server.py` | 只能调用核心层接口，不得反向依赖 |
| 新增 CLI 工具 | `scripts/` | 与 server 平级，共享核心层 |

---

## 七、文件清单与职责

```
value-desk/
├── 启动ValueDesk.command     桌面启动器（双击运行）
├── config/default.yaml       唯一参数入口
├── app/                      界面层（ui / server / render）
├── src/vd/                   核心逻辑层（7 个模块，见接口表）
├── scripts/                  命令行入口（screen / analyze）
├── tests/test_core.py        回归测试（7 项，含埋雷样本守护）
├── docs/                     METRICS.md（指标手册）· ARCHITECTURE.md（本文）
└── reports/                  全部输出：报告 / 快照 /（journal 跟踪）
```

依赖铁律（写在代码注释里，扩展时请遵守）：
1. 核心层不依赖界面层；
2. `data` 的输出结构（长表字段名）是系统内唯一的"数据契约"；
3. 所有阈值必须来自 config，不允许散落硬编码；
4. 界面只展示核心层的产出，不做任何业务计算。
