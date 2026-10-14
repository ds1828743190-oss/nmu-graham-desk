#!/bin/bash
# ============================================================
#  北民大格雷厄姆的 ValueDesk · 桌面启动器
#  用法：双击本文件（或在终端执行 ./启动ValueDesk.command）
#  功能：自动检查环境 → 启动本地服务 → 打开浏览器界面
#  停止：在启动窗口按 Ctrl+C，或直接关闭窗口
# ============================================================

cd "$(dirname "$0")" || { echo "❌ 无法进入项目目录"; exit 1; }

echo "============================================================"
echo "  北民大格雷厄姆的 ValueDesk · 价值投资分析工作台"
echo "  正在检查运行环境 ..."
echo "============================================================"

# ---------- 1) 查找可用的 Python ----------
PY=""
for candidate in \
    "$HOME/.workbuddy/binaries/python/envs/default/bin/python" \
    "./.venv/bin/python" \
    "$(command -v python3)" \
    "/usr/local/bin/python3" \
    "/opt/homebrew/bin/python3" \
    "/usr/bin/python3"; do
    if [ -n "$candidate" ] && [ -x "$candidate" ]; then
        PY="$candidate"
        break
    fi
done

if [ -z "$PY" ]; then
    echo "❌ 未找到 Python 环境。"
    echo "   请先安装 Python 3.10 及以上版本（python.org 或 Homebrew）后重试。"
    read -n 1 -s -r -p "按任意键退出 ..."
    exit 1
fi
echo "✓ Python: $PY"

# ---------- 2) 依赖自检（缺则自动安装，清华镜像） ----------
if ! "$PY" -c "import pandas, numpy, yaml" >/dev/null 2>&1; then
    echo "⚙️  检测到缺少依赖，正在自动安装（清华镜像）..."
    if ! "$PY" -m pip install pandas numpy pyyaml \
        -i https://pypi.tuna.tsinghua.edu.cn/simple; then
        echo "❌ 依赖安装失败。请检查网络后重试，或手动执行："
        echo "   $PY -m pip install pandas numpy pyyaml -i https://pypi.tuna.tsinghua.edu.cn/simple"
        read -n 1 -s -r -p "按任意键退出 ..."
        exit 1
    fi
fi
echo "✓ 依赖就绪（pandas / numpy / pyyaml）"

# ---------- 3) 无需任何额外配置，直接启动 ----------
echo "✓ 配置：config/default.yaml（默认 mock 离线数据，开箱即用）"
echo "------------------------------------------------------------"
exec "$PY" app/server.py --open-browser
