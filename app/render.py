"""Markdown → HTML 渲染器（报告展示专用，零依赖）。

支持的语法（覆盖系统生成的全部报告）：
标题 #~####、表格、无序/有序列表、粗体/斜体、行内代码、代码块、
引用、分隔线、链接。所有文本先做 HTML 转义（防注入）。
"""
from __future__ import annotations

import html
import re


def _inline(text: str) -> str:
    """行内格式：转义 → 粗体/斜体/行内代码/链接。"""
    t = html.escape(text, quote=False)
    # 行内代码（先处理，避免其中内容被其他规则影响）
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    # 粗体 / 斜体
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)
    # 链接 [text](url)
    t = re.sub(
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        r'<a href="\2" target="_blank" rel="noopener">\1</a>', t,
    )
    # 状态符号渲染为彩色标签
    t = t.replace("🔴", '<span class="dot dot-red"></span>')
    t = t.replace("🟡", '<span class="dot dot-yellow"></span>')
    t = t.replace("✅", '<span class="dot dot-green"></span>')
    return t


def _is_table_sep(line: str) -> bool:
    s = line.strip()
    return bool(s) and set(s.replace("|", "").replace("-", "").replace(":", "").strip()) == set()


def _split_row(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def md_to_html(md: str) -> str:
    """把 Markdown 文本渲染为 HTML 片段。"""
    lines = md.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    in_list = False       # 当前是否在列表中（ul/ol）
    list_tag = ""

    def close_list():
        nonlocal in_list, list_tag
        if in_list:
            out.append(f"</{list_tag}>")
            in_list = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # ---- 代码块 ----
        if stripped.startswith("```"):
            close_list()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            i += 1  # 跳过结尾 ```
            body = html.escape("\n".join(code_lines))
            out.append(f'<pre class="code-block"><code>{body}</code></pre>')
            continue

        # ---- 表格 ----
        if "|" in line and i + 1 < len(lines) and _is_table_sep(lines[i + 1]):
            close_list()
            header = _split_row(line)
            rows = []
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append(_split_row(lines[i]))
                i += 1
            th = "".join(f"<th>{_inline(c)}</th>" for c in header)
            body_rows = "".join(
                "<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>"
                for r in rows
            )
            out.append(
                f'<div class="table-wrap"><table><thead><tr>{th}</tr></thead>'
                f"<tbody>{body_rows}</tbody></table></div>"
            )
            continue

        # ---- 标题 ----
        m = re.match(r"^(#{1,4})\s+(.*)$", stripped)
        if m:
            close_list()
            level = len(m.group(1))
            out.append(f"<h{level}>{_inline(m.group(2))}</h{level}>")
            i += 1
            continue

        # ---- 分隔线 ----
        if re.match(r"^-{3,}$", stripped) or re.match(r"^\*{3,}$", stripped):
            close_list()
            out.append("<hr>")
            i += 1
            continue

        # ---- 引用 ----
        if stripped.startswith(">"):
            close_list()
            quote_lines = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote_lines.append(lines[i].strip().lstrip(">").strip())
                i += 1
            body = "<br>".join(_inline(q) for q in quote_lines if q)
            out.append(f'<blockquote>{body}</blockquote>')
            continue

        # ---- 列表 ----
        m_ul = re.match(r"^[-*]\s+(.*)$", stripped)
        m_ol = re.match(r"^(\d+)[.、]\s+(.*)$", stripped)
        if m_ul or m_ol:
            want = "ul" if m_ul else "ol"
            if not in_list or list_tag != want:
                close_list()
                in_list, list_tag = True, want
                out.append(f"<{want}>")
            content = m_ul.group(1) if m_ul else m_ol.group(2)
            # 续行（缩进的后续行）合并
            out.append(f"<li>{_inline(content)}</li>")
            i += 1
            continue

        # ---- 空行 / 段落 ----
        if not stripped:
            close_list()
            i += 1
            continue

        close_list()
        out.append(f"<p>{_inline(stripped)}</p>")
        i += 1

    close_list()
    return "\n".join(out)
