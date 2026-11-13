# -*- coding: utf-8 -*-
"""把 docs/ 下的两份 Markdown 文档生成一份自包含、离线可读的 HTML 阅读版。

用法（在项目根目录或任意目录均可）：
    python docs/build_reader.py

改完 technical-doc.md / blog-post.md 后重跑一次即可同步阅读版。
不依赖任何第三方库，只用标准库。
"""
import html
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent
TECH_MD = BASE / "technical-doc.md"
BLOG_MD = BASE / "blog-post.md"
OUT_HTML = BASE / "reader.html"


def inline(text: str) -> str:
    """行内语法：行内代码、粗体、链接、斜体。代码先占位，避免二次解析。"""
    text = html.escape(text, quote=False)
    slots = []

    def hold_code(m):
        slots.append("<code>" + m.group(1) + "</code>")
        return "\x00%d\x00" % (len(slots) - 1)

    text = re.sub(r"`([^`]+)`", hold_code, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: slots[int(m.group(1))], text)


def is_table_separator(line: str) -> bool:
    """匹配 |---|---| / | :--- | ---: | 这类分隔行，不用含反斜杠的正则。"""
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return False
    body = s.strip("|").replace("|", "").replace(" ", "").replace(":", "")
    return bool(body) and set(body) <= {"-"}


LIST_RE = re.compile(r"^\s*(?:[-*]|\d+[.])\s+")
ORDERED_RE = re.compile(r"^\s*\d+[.]\s+")
HEAD_RE = re.compile(r"^(#{1,6})\s+(.*)$")
HR_RE = re.compile(r"^\s*-{3,}\s*$")


def render(md: str):
    lines = md.splitlines()
    out, toc = [], []
    i, n, sec = 0, len(lines), 0

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # 围栏代码块
        if stripped.startswith("```"):
            i += 1
            buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(buf)) + "</code></pre>")
            continue

        # 分隔线
        if HR_RE.match(line):
            out.append("<hr>")
            i += 1
            continue

        # 标题
        m = HEAD_RE.match(line)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            if level == 2:
                sec += 1
                anchor = "sec-%d" % sec
                plain = re.sub(r"[*`]", "", text)
                # 同时生成一个 GitHub 风格的锚点，让正文里的章节目录链接也能跳转
                slug = re.sub(r"[^\w-]", "", plain.lower().replace(" ", "-"))
                if plain != "目录":
                    toc.append((anchor, plain))
                out.append('<span class="anchor" id="%s"></span>' % slug)
                out.append('<h2 id="%s">%s</h2>' % (anchor, inline(text)))
            else:
                out.append("<h%d>%s</h%d>" % (level, inline(text), level))
            i += 1
            continue

        # 表格
        if stripped.startswith("|") and i + 1 < n and is_table_separator(lines[i + 1]):
            header = [c.strip() for c in stripped.strip("|").split("|")]
            i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            t = ['<div class="table-wrap"><table><thead><tr>']
            t += ["<th>%s</th>" % inline(c) for c in header]
            t.append("</tr></thead><tbody>")
            for r in rows:
                t.append("<tr>")
                t += ["<td>%s</td>" % inline(c) for c in r]
                t.append("</tr>")
            t.append("</tbody></table></div>")
            out.append("".join(t))
            continue

        # 引用（连续 > 行合并成一段）
        if stripped.startswith(">"):
            parts = []
            while i < n and lines[i].strip().startswith(">"):
                parts.append(inline(lines[i].strip().lstrip(">").strip()))
                i += 1
            out.append("<blockquote>%s</blockquote>" % "<br>".join(parts))
            continue

        # 列表
        if LIST_RE.match(line):
            items, ordered = [], bool(ORDERED_RE.match(line))
            while i < n and LIST_RE.match(lines[i]):
                items.append(LIST_RE.sub("", lines[i], count=1))
                i += 1
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % inline(x) for x in items), tag))
            continue

        # 普通段落：连续非空行合并，遇到块级语法就停
        buf = [stripped]
        i += 1
        while i < n:
            nxt = lines[i].strip()
            if (not nxt or nxt.startswith(("#", ">", "|", "```"))
                    or HR_RE.match(lines[i]) or LIST_RE.match(lines[i])):
                break
            buf.append(nxt)
            i += 1
        out.append("<p>%s</p>" % inline(" ".join(buf)))

    return "\n".join(out), toc


def toc_html(items):
    return "\n".join(
        '<a class="toc-link" href="#%s" data-target="%s">%s</a>' % (a, a, html.escape(t))
        for a, t in items
    )


TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>闲小集 · 技术文档与博客</title>
<style>
  :root {
    --bg: #f7f9fc; --surface: #ffffff; --ink: #172b4d; --muted: #5c6f8c;
    --line: #e3ebf5; --brand: #1677ff; --brand-soft: #e8f3ff; --code-bg: #f4f7fb;
    --radius: 14px; --sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
      "Microsoft YaHei", "Hiragino Sans GB", "Source Han Sans SC", sans-serif;
    --mono: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #12161d; --surface: #1a2029; --ink: #e6edf6; --muted: #9fb0c6;
      --line: #2c3542; --brand: #6aa8ff; --brand-soft: #1c2c42; --code-bg: #141a22;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--ink); font-family: var(--sans);
    font-size: 15px; line-height: 1.85; }
  a { color: var(--brand); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .topbar { position: sticky; top: 0; z-index: 20; background: var(--surface);
    border-bottom: 1px solid var(--line); padding: 14px 26px; display: flex;
    align-items: center; gap: 22px; flex-wrap: wrap; }
  .brand { font-size: 17px; font-weight: 700; letter-spacing: .3px; white-space: nowrap; }
  .brand span { color: var(--brand); }
  .tabs { display: flex; gap: 8px; }
  .tab { border: 1px solid var(--line); background: transparent; color: var(--muted);
    padding: 6px 16px; border-radius: 999px; cursor: pointer; font-size: 13.5px;
    font-family: inherit; transition: .18s ease; }
  .tab:hover { border-color: var(--brand); color: var(--brand); }
  .tab.active { background: var(--brand); border-color: var(--brand); color: #fff; }
  .meta { margin-left: auto; color: var(--muted); font-size: 12.5px; white-space: nowrap; }
  .layout { display: flex; gap: 28px; max-width: 1240px; margin: 0 auto; padding: 28px 26px 80px; }
  .toc { width: 236px; flex: none; position: sticky; top: 78px; align-self: flex-start;
    max-height: calc(100vh - 110px); overflow-y: auto; padding-right: 8px; }
  .toc-title { font-size: 12px; color: var(--muted); letter-spacing: 1.2px;
    text-transform: uppercase; margin: 0 0 10px 10px; font-weight: 700; }
  .toc-link { display: block; padding: 5px 10px; border-radius: 8px; color: var(--muted);
    font-size: 13px; line-height: 1.5; border-left: 2px solid transparent; }
  .toc-link:hover { background: var(--brand-soft); color: var(--brand); text-decoration: none; }
  .toc-link.active { color: var(--brand); border-left-color: var(--brand);
    background: var(--brand-soft); font-weight: 600; }
  .toc-group { display: none; }
  .toc-group.active { display: block; }
  main { flex: 1; min-width: 0; background: var(--surface); border: 1px solid var(--line);
    border-radius: var(--radius); padding: 40px 48px 64px; }
  article { display: none; }
  article.active { display: block; }
  h1 { font-size: 27px; line-height: 1.4; margin: 0 0 18px; letter-spacing: -.3px; }
  h2 { font-size: 21px; margin: 46px 0 16px; padding-bottom: 10px;
    border-bottom: 1px solid var(--line); scroll-margin-top: 90px; }
  .anchor { display: block; height: 0; scroll-margin-top: 90px; }
  h3 { font-size: 17px; margin: 30px 0 12px; }
  h4 { font-size: 15px; margin: 22px 0 10px; color: var(--muted); }
  p { margin: 12px 0; }
  strong { color: var(--ink); font-weight: 700; }
  ul, ol { padding-left: 24px; margin: 12px 0; }
  li { margin: 5px 0; }
  hr { border: none; border-top: 1px solid var(--line); margin: 34px 0; }
  blockquote { margin: 18px 0; padding: 12px 18px; background: var(--brand-soft);
    border-left: 3px solid var(--brand); border-radius: 0 10px 10px 0; color: var(--ink); }
  blockquote p { margin: 0; }
  code { font-family: var(--mono); font-size: .9em; background: var(--code-bg);
    padding: 2px 6px; border-radius: 5px; border: 1px solid var(--line); }
  pre { background: var(--code-bg); border: 1px solid var(--line); border-radius: 10px;
    padding: 16px 20px; overflow-x: auto; margin: 18px 0; line-height: 1.7; }
  pre code { background: none; border: none; padding: 0; font-size: 12.5px; }
  .table-wrap { overflow-x: auto; margin: 18px 0; }
  table { border-collapse: collapse; width: 100%; font-size: 13.5px; }
  th, td { border: 1px solid var(--line); padding: 9px 13px; text-align: left;
    vertical-align: top; line-height: 1.65; }
  th { background: var(--brand-soft); font-weight: 700; white-space: nowrap; }
  tbody tr:nth-child(even) { background: rgba(22, 119, 255, .035); }
  .foot { text-align: center; color: var(--muted); font-size: 12.5px; padding: 0 26px 40px; }
  @media (max-width: 900px) {
    .layout { flex-direction: column; padding: 18px 14px 60px; gap: 14px; }
    .toc { position: static; width: 100%; max-height: 190px; border: 1px solid var(--line);
      border-radius: 10px; background: var(--surface); padding: 12px; }
    main { padding: 24px 20px 44px; }
    h1 { font-size: 22px; } h2 { font-size: 19px; }
    .meta { display: none; }
  }
</style>
</head>
<body>
<div class="topbar">
  <div class="brand">闲小集 <span>·</span> 项目文档</div>
  <div class="tabs">
    <button class="tab active" data-doc="tech">技术文档</button>
    <button class="tab" data-doc="blog">博客文章</button>
  </div>
  <div class="meta">v1.0 · 2026-11-13 · commit 2103953</div>
</div>
<div class="layout">
  <aside class="toc">
    <div class="toc-title">目录</div>
    <div class="toc-group active" data-group="tech">__TOC_TECH__</div>
    <div class="toc-group" data-group="blog">__TOC_BLOG__</div>
  </aside>
  <main>
    <article id="doc-tech" class="active">__TECH__</article>
    <article id="doc-blog">__BLOG__</article>
  </main>
</div>
<div class="foot">闲小集 · 校园二手交易平台　|　文档随代码存于 docs/ 目录，离线可读</div>
<script>
(function () {
  var tabs = document.querySelectorAll('.tab');
  var articles = document.querySelectorAll('article');
  var groups = document.querySelectorAll('.toc-group');
  function switchTo(name) {
    tabs.forEach(function (t) { t.classList.toggle('active', t.dataset.doc === name); });
    articles.forEach(function (a) { a.classList.toggle('active', a.id === 'doc-' + name); });
    groups.forEach(function (g) { g.classList.toggle('active', g.dataset.group === name); });
    window.scrollTo({ top: 0, behavior: 'smooth' });
    try { localStorage.setItem('xj-doc-tab', name); } catch (e) {}
  }
  tabs.forEach(function (t) { t.addEventListener('click', function () { switchTo(t.dataset.doc); }); });
  document.addEventListener('click', function (e) {
    var link = e.target.closest('.toc-link');
    if (!link) return;
    e.preventDefault();
    var target = document.getElementById(link.dataset.target);
    if (!target) return;
    var y = target.getBoundingClientRect().top + window.pageYOffset - 84;
    window.scrollTo({ top: y, behavior: 'smooth' });
    groups.forEach(function (g) {
      g.querySelectorAll('.toc-link').forEach(function (l) { l.classList.remove('active'); });
    });
    link.classList.add('active');
  });
  try {
    var saved = localStorage.getItem('xj-doc-tab');
    if (saved === 'blog') { switchTo('blog'); }
  } catch (e) {}
})();
</script>
</body>
</html>
"""


def main():
    tech_html, tech_toc = render(TECH_MD.read_text(encoding="utf-8"))
    blog_html, blog_toc = render(BLOG_MD.read_text(encoding="utf-8"))
    out = (TEMPLATE.replace("__TOC_TECH__", toc_html(tech_toc))
                   .replace("__TOC_BLOG__", toc_html(blog_toc))
                   .replace("__TECH__", tech_html)
                   .replace("__BLOG__", blog_html))
    OUT_HTML.write_text(out, encoding="utf-8")
    print("生成完成:", OUT_HTML, len(out), "字符")
    print("技术文档", len(tech_toc), "节 | 博客", len(blog_toc), "节")
    print("表格", out.count("<table>"), "| 代码块", out.count("<pre>"),
          "| 列表", out.count("<ul>") + out.count("<ol>"), "| 引用", out.count("<blockquote>"))


if __name__ == "__main__":
    main()
