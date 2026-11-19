import html
import json
import os
import re
import shutil
import sys

import markdown
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

from vamp_lexer import VampDataLexer, VampLexer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PAGES = os.path.join(HERE, "pages")
OUTPUT = os.path.join(HERE, "_site")
REPOSITORY = "https://github.com/Clxtus/Vamp"
SITE_NAME = "Vamp"

GROUPS = [
    ("Language", ["source-files-and-comments", "types-variables-and-constants", "expressions-and-assignment",
                  "functions-and-returns", "control-flow", "strings", "enums"]),
    ("Collections", ["arrays-and-dictionaries", "lists-and-maps"]),
    ("Classes and types", ["classes", "optional-values-and-none"]),
    ("Program structure", ["error-handling", "tests", "console-output-and-program-exit", "imports"]),
    ("Memory and performance", ["memory", "limits"]),
    ("Standard libraries", ["standard-libraries"]),
    ("Windows and interfaces", ["the-os-library", "interface-styles", "native-interface-controls",
                                "changing-querying-and-removing-interfaces", "interface-groups", "events",
                                "drawing-on-a-canvas"]),
    ("Tools", ["the-vamp-command", "editor-support-and-debugging"]),
]
CHILD_ORDER = {
    "standard-libraries": ["math", "random", "time", "file", "console", "json", "thread", "net", "regex", "memory",
                           "input", "audio"],
}
LEXERS = {"vamp": VampLexer(), "vp": VampLexer(), "vpdata": VampDataLexer()}
FENCE = re.compile(r"^```(\w*)\s*$")


def slugify(text):
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def plain(text):
    return re.sub(r"[`*_]", "", text).strip()


class Page:
    def __init__(self, title, slug, group, body, parent=None):
        self.title = title
        self.slug = slug
        self.group = group
        self.body = body
        self.parent = parent
        self.children = []
        self.html = ""
        self.headings = []

    @property
    def url(self):
        return "index.html" if self.slug == "index" else f"{self.slug}.html"


def read_page(path, slug, group, parent=None):
    with open(path, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    title = slug
    if lines and lines[0].startswith("# "):
        title, lines = lines[0][2:].strip(), lines[1:]
    return Page(title, slug, group, "\n".join(lines).strip("\n"), parent)


def ordered(names, preferred):
    return [name for name in preferred if name in names] + sorted(name for name in names if name not in preferred)


# pages live in docs/pages (local only, gitignored), order comes from GROUPS
def load_pages():
    if not os.path.isdir(PAGES):
        sys.exit(f"No pages found: put the documentation pages in {PAGES}")
    home = read_page(os.path.join(PAGES, "index.md"), "index", "Getting started")
    home.title = "Vamp documentation"
    slugs = [name[:-3] for name in os.listdir(PAGES) if name.endswith(".md") and name != "index.md"]
    placement = {slug: group for group, listed in GROUPS for slug in listed}
    pages = []
    for slug in ordered(slugs, [slug for _, listed in GROUPS for slug in listed]):
        page = read_page(os.path.join(PAGES, slug + ".md"), slug, placement.get(slug, "More"))
        folder = os.path.join(PAGES, slug)
        if os.path.isdir(folder):
            names = [name[:-3] for name in os.listdir(folder) if name.endswith(".md")]
            for name in ordered(names, CHILD_ORDER.get(slug, [])):
                page.children.append(read_page(os.path.join(folder, name + ".md"), f"{slug}-{name}", page.group, page))
        pages.append(page)
    return home, pages


def highlight_code(language, code):
    if language in LEXERS:
        lexer = LEXERS[language]
    else:
        try:
            lexer = get_lexer_by_name(language) if language else TextLexer()
        except ClassNotFound:
            lexer = TextLexer()
    rendered = highlight(code, lexer, HtmlFormatter(nowrap=True))
    label = {"vamp": "Vamp", "vp": "Vamp", "vpdata": "Vamp data", "": "Text"}.get(language, language)
    return (f'<div class="code" data-language="{html.escape(label)}"><button class="copy" type="button" '
            f'aria-label="Copy code">Copy</button><pre><code>{rendered}</code></pre></div>')


def render(page, anchors):
    stash, lines, block, language = [], [], None, ""
    for line in page.body.splitlines():
        match = FENCE.match(line)
        if block is None and match:
            block, language = [], match.group(1).lower()
        elif block is not None and line.strip() == "```":
            stash.append(highlight_code(language, "\n".join(block)))
            lines += ["", f"VAMPCODEBLOCK{len(stash) - 1}", ""]
            block = None
        elif block is not None:
            block.append(line)
        else:
            lines.append(line)
    converter = markdown.Markdown(extensions=["tables", "toc", "sane_lists"],
                                  extension_configs={"toc": {"slugify": lambda text, _: slugify(text)}})
    body = converter.convert("\n".join(lines))
    for idx, code in enumerate(stash):
        body = body.replace(f"<p>VAMPCODEBLOCK{idx}</p>", code)
    body = re.sub(r'<table>', '<div class="table"><table>', body).replace("</table>", "</table></div>")

    def relink(match):
        target = match.group(1)
        if target.startswith("#"):
            owner = anchors.get(target[1:])
            if owner and owner is not page:
                return f'href="{owner.url}{target}"'
        if target.startswith(("./", "../")) or (not re.match(r"^[a-z]+:", target) and target.endswith(".md")):
            return f'href="{REPOSITORY}/blob/main/{target.lstrip("./")}"'
        return match.group(0)

    body = re.sub(r'href="([^"]+)"', relink, body)
    page.headings = [(token["level"], token["id"], token["name"]) for token in flatten(converter.toc_tokens)]
    page.html = body


def flatten(tokens):
    for token in tokens:
        yield token
        yield from flatten(token["children"])


def collect_anchors(pages):
    anchors = {}
    for page in sorted(pages, key=lambda page: page.parent is not None):
        anchors.setdefault(slugify(plain(page.title)), page)
    for page in pages:
        for line in page.body.splitlines():
            if line.startswith("#"):
                anchors.setdefault(slugify(markdown.markdown(line.lstrip("#").strip())), page)
    return anchors


def nav_html(home, pages, current):
    def link(page):
        classes = "current" if page is current or current in page.children else ""
        inner = f'<a class="{classes}" href="{page.url}">{inline(page.title)}</a>'
        subs = ""
        if page is current and page.headings:
            items = "".join(f'<li><a href="#{anchor}">{name}</a></li>'
                            for level, anchor, name in page.headings if level == 2)
            subs = f'<ul class="local">{items}</ul>' if items else ""
        if page.children and (page is current or current in page.children or current is None):
            items = "".join(f'<li>{link(child)}</li>' for child in page.children)
            subs += f'<ul>{items}</ul>'
        return inner + subs

    parts = [f'<p class="caption">Getting started</p><ul><li>{link(home)}</li></ul>']
    groups = []
    for page in pages:
        if page.group not in groups:
            groups.append(page.group)
    for group in groups:
        items = "".join(f"<li>{link(page)}</li>" for page in pages if page.group == group)
        parts.append(f'<p class="caption">{html.escape(group)}</p><ul>{items}</ul>')
    return "".join(parts)


def inline(text):
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", html.escape(text))


def layout(title, content, nav, extra_head="", toc="", crumbs=""):
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(plain(title)) if "documentation" in title else html.escape(plain(title)) + " — " + SITE_NAME + " documentation"}</title>
<link rel="icon" href="_static/icon.png">
<link rel="stylesheet" href="_static/style.css">
<script>try{{var t=localStorage.getItem("vamp-theme");if(t)document.documentElement.dataset.theme=t;}}catch(e){{}}</script>
{extra_head}
</head>
<body>
<header class="mobile-bar">
  <button class="menu" type="button" aria-label="Open the menu">&#9776;</button>
  <a class="brand" href="index.html"><img src="_static/icon.png" alt="">Vamp</a>
</header>
<nav class="sidebar" aria-label="Documentation">
  <div class="sidebar-top">
    <a class="brand" href="index.html"><img src="_static/icon.png" alt=""><span>Vamp</span></a>
    <div class="version">latest</div>
    <form class="search" action="search.html" role="search">
      <input type="search" name="q" placeholder="Search docs" aria-label="Search the documentation" autocomplete="off">
      <div class="search-results" hidden></div>
    </form>
  </div>
  <div class="sidebar-nav">{nav}</div>
</nav>
<div class="page">
  <div class="topbar">
    <div class="crumbs">{crumbs}</div>
    <div class="actions">
      <a href="{REPOSITORY}" class="edit">GitHub</a>
      <button class="theme" type="button" aria-label="Switch between light and dark">&#9681;</button>
    </div>
  </div>
  <div class="columns">
    <main class="content">
{content}
    </main>
    {toc}
  </div>
  <footer>
    &copy; 2026 Clxtus &middot; Vamp is released under the <a href="{REPOSITORY}/blob/main/LICENSE">MIT License</a>
    &middot; <a href="{REPOSITORY}">Source on GitHub</a>
  </footer>
</div>
<script src="_static/search-index.js"></script>
<script src="_static/docs.js"></script>
</body>
</html>
"""


def page_html(page, home, pages, sequence):
    pos = sequence.index(page)
    prev = sequence[pos - 1] if pos > 0 else None
    following = sequence[pos + 1] if pos + 1 < len(sequence) else None
    buttons = '<div class="pager">'
    if prev:
        buttons += f'<a class="previous" href="{prev.url}"><span>Previous</span>{inline(prev.title)}</a>'
    if following:
        buttons += f'<a class="next" href="{following.url}"><span>Next</span>{inline(following.title)}</a>'
    buttons += "</div>"
    title = f'<h1 id="{slugify(plain(page.title))}">{inline(page.title)}</h1>' if page.slug != "index" else ""
    if page.children:
        items = "".join(f'<li><a href="{child.url}">{inline(child.title)}</a></li>' for child in page.children)
        page.html += f'<ul class="child-pages">{items}</ul>'
    crumbs = '<a href="index.html">Docs</a>'
    if page.slug != "index":
        if not page.parent or page.parent.title != page.group:
            crumbs += f' <span>&rsaquo;</span> {html.escape(page.group)}'
        if page.parent:
            crumbs += f' <span>&rsaquo;</span> <a href="{page.parent.url}">{inline(page.parent.title)}</a>'
        crumbs += f' <span>&rsaquo;</span> {inline(page.title)}'
    toc = ""
    entries = [(level, anchor, name) for level, anchor, name in page.headings if level in (2, 3)]
    if entries and page.slug != "index":
        items = "".join(f'<li class="level-{level}"><a href="#{anchor}">{name}</a></li>'
                        for level, anchor, name in entries)
        toc = f'<aside class="toc"><p>On this page</p><ul>{items}</ul></aside>'
    article = f'<article class="{"home" if page.slug == "index" else "doc"}">{title}{page.html}{buttons}</article>'
    return layout(page.title, article, nav_html(home, pages, page), toc=toc, crumbs=crumbs)


def search_entries(pages):
    entries = []
    for page in pages:
        sections = re.split(r'(<h[23] id="[^"]+">.*?</h[23]>)', page.html)
        current_title, current_anchor = plain(page.title), ""
        texts = [sections[0]]
        for part in sections[1:] + [None]:
            if part is None or part.startswith("<h"):
                text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", " ".join(texts)))).strip()
                if text or current_anchor:
                    entries.append({"page": plain(page.title), "title": current_title,
                                    "url": page.url + (f"#{current_anchor}" if current_anchor else ""),
                                    "text": text[:2000]})
                if part is None:
                    break
                match = re.match(r'<h[23] id="([^"]+)">(.*?)</h[23]>', part)
                current_anchor = match.group(1)
                current_title = html.unescape(re.sub(r"<[^>]+>", "", match.group(2)))
                texts = []
            else:
                texts.append(part)
    return entries


def build():
    home, pages = load_pages()
    every = [home]
    for page in pages:
        every.append(page)
        every.extend(page.children)
    anchors = collect_anchors(every)
    for page in every:
        render(page, anchors)
    shutil.rmtree(OUTPUT, ignore_errors=True)
    static = os.path.join(OUTPUT, "_static")
    shutil.copytree(os.path.join(HERE, "theme"), static)
    shutil.copy2(os.path.join(ROOT, "vamp-vscode", "icons", "icon.png"), os.path.join(static, "icon.png"))
    with open(os.path.join(static, "search-index.js"), "w", encoding="utf-8") as fh:
        fh.write("window.VAMP_SEARCH = " + json.dumps(search_entries(every), ensure_ascii=False) + ";\n")
    for page in every:
        with open(os.path.join(OUTPUT, page.url), "w", encoding="utf-8") as fh:
            fh.write(page_html(page, home, pages, every))
    search = ('<article class="doc"><h1>Search</h1><p class="search-summary"></p>'
              '<ol class="search-page-results"></ol></article>')
    with open(os.path.join(OUTPUT, "search.html"), "w", encoding="utf-8") as fh:
        fh.write(layout("Search", search, nav_html(home, pages, None), crumbs='<a href="index.html">Docs</a>'))
    missing = ('<article class="doc"><h1>Page not found</h1><p>This page does not exist. Try the search box, or '
               'go back to the <a href="index.html">start of the documentation</a>.</p></article>')
    with open(os.path.join(OUTPUT, "404.html"), "w", encoding="utf-8") as fh:
        fh.write(layout("Page not found", missing, nav_html(home, pages, None)))
    open(os.path.join(OUTPUT, ".nojekyll"), "w").close()
    print(f"Built {len(every) + 2} pages in {OUTPUT}")


if __name__ == "__main__":
    sys.exit(build())
