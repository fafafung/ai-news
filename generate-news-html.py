#!/usr/bin/env python3
"""
AI News Archive — Static HTML Generator
========================================
Generates daily, weekly, and index HTML pages for the AI news archive system.

Usage:
    python3 generate-news-html.py daily /path/to/daily-news.json
    python3 generate-news-html.py weekly
    python3 generate-news-html.py index

Daily mode:
    Reads a JSON file (see README for schema), generates a responsive HTML page
    at /opt/data/ai-news/YYYY-MM-DD.html, updates index_data.json, and
    regenerates index.html.

Weekly mode:
    Scans index_data.json, groups entries by ISO week, generates
    weekly-YYYY-WWW.html with aggregate stats, and regenerates index.html.

Index mode:
    Regenerates index.html from index_data.json.

All paths are relative so the site works both locally and on Vercel.

Input JSON schema (daily mode):
{
  "date": "2026-06-23",
  "dow": "二",
  "items": [
    {
      "title": "baidu/Unlimited-OCR",
      "link": "https://github.com/baidu/Unlimited-OCR",
      "category": "github",
      "why": "短摘要（metadata 用）",
      "description": "長描述，2-3 句中文，係用戶主力閱讀嘅內容，代替 click link。",
      "stars": 83,
      "signal": "big",
      "source_domain": "github.com"          // optional, auto-extracted from link
    }
  ],
  "summary": "全日期總括（optional）"
}
"""

import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime, date, timedelta
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_DATA = os.path.join(BASE_DIR, "index_data.json")
INDEX_HTML = os.path.join(BASE_DIR, "index.html")


# ---------------------------------------------------------------------------
# Visual constants
# ---------------------------------------------------------------------------

CATEGORY_ICONS = {
    "github": "⚡",
    "tech": "🔬",
    "general": "📰",
    "research": "📄",
}

CATEGORY_LABELS = {
    "github": "GitHub 開源",
    "tech": "科技新聞",
    "general": "業界動態",
    "research": "研究論文",
}

CATEGORY_ORDER = ["github", "tech", "general", "research"]

# Accent colours per category (for left-border on sections)
CATEGORY_ACCENT = {
    "github": "#e3b341",
    "tech": "#58a6ff",
    "general": "#bc8cff",
    "research": "#3fb950",
}

SIGNAL_BADGES = {
    "new": ("🆕", "#e74c3c"),
    "big": ("🏢", "#8e44ad"),
    "hot": ("🔥", "#e67e22"),
    "pain": ("💊", "#27ae60"),
    "para": ("💡", "#2980b9"),
}

# Map category to a suitable emoji prefix for each item title
TITLE_EMOJI = {
    "github": "📦",
    "tech": "⚙️",
    "general": "🌐",
    "research": "📖",
}

WEEKDAY_NAMES = {
    "一": "星期一", "二": "星期二", "三": "星期三",
    "四": "星期四", "五": "星期五", "六": "星期六", "日": "星期日",
}


# ---------------------------------------------------------------------------
# CSS — self-contained, no external deps
# ---------------------------------------------------------------------------

CSS = r"""/* ── Reset & Base ── */
*, *::before, *::after { margin:0; padding:0; box-sizing:border-box; }

:root {
  --bg: #0d1117;
  --bg2: #161b22;
  --bg3: #1c2333;
  --bg4: #21262d;
  --text: #e6edf3;
  --text2: #8b949e;
  --text3: #58a6ff;
  --border: #30363d;
  --border2: #3d444d;
  --accent: #58a6ff;
  --card-hover: #1c2333;
  --link: #58a6ff;
  --badge-text: #ffffff;
  --shadow: rgba(0,0,0,0.3);
  --featured-bg: linear-gradient(135deg, #161b22 0%, #1c2333 100%);
  --featured-border: #58a6ff;
}

@media (prefers-color-scheme: light) {
  :root {
    --bg: #ffffff;
    --bg2: #f6f8fa;
    --bg3: #eef1f5;
    --bg4: #e8ecf0;
    --text: #1f2328;
    --text2: #656d76;
    --text3: #0969da;
    --border: #d0d7de;
    --border2: #d8dee4;
    --accent: #0969da;
    --card-hover: #f3f4f6;
    --link: #0969da;
    --badge-text: #ffffff;
    --shadow: rgba(0,0,0,0.08);
    --featured-border: #0969da;
  }
}

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans",
    "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", Helvetica, Arial,
    sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.7;
  padding: 0;
  -webkit-font-smoothing: antialiased;
  font-size: 16px;
}

a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }

/* ── Layout ── */
.container { max-width: 920px; margin: 0 auto; padding: 32px 20px; }

/* ── Header ── */
.header {
  border-bottom: 1px solid var(--border);
  padding-bottom: 24px;
  margin-bottom: 32px;
}
.header h1 {
  font-size: 1.75rem;
  font-weight: 800;
  margin-bottom: 6px;
  letter-spacing: -0.02em;
  line-height: 1.3;
}
.header h1 .date-weekday {
  font-weight: 400;
  color: var(--text2);
  font-size: 0.9em;
}
.header .sub {
  color: var(--text2);
  font-size: 0.92rem;
  margin-top: 2px;
}
.header .nav {
  margin-top: 16px;
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  font-size: 0.88rem;
}
.header .nav a {
  color: var(--text2);
  padding: 5px 12px;
  border-radius: 8px;
  background: var(--bg2);
  border: 1px solid var(--border);
  transition: all 0.15s;
}
.header .nav a:hover {
  background: var(--bg3);
  border-color: var(--text3);
  text-decoration: none;
  color: var(--text);
}

/* ── Stats Bar ── */
.stats {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 28px;
}
.stat-box {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 18px;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 76px;
}
.stat-box .num {
  font-size: 1.4rem;
  font-weight: 800;
  color: var(--accent);
  line-height: 1.2;
}
.stat-box .label {
  color: var(--text2);
  font-size: 0.72rem;
  margin-top: 3px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

/* ── Day-of-week stat box ── */
.stat-box.dow-box .num {
  font-size: 1.1rem;
}

/* ── Section (Category Group) ── */
.section {
  margin-bottom: 36px;
}
.section-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--border);
}
.section-header .section-icon {
  font-size: 1.3rem;
}
.section-header .section-label {
  font-size: 1.15rem;
  font-weight: 700;
  letter-spacing: -0.01em;
}
.section-header .section-count {
  font-size: 0.78rem;
  color: var(--text2);
  background: var(--bg3);
  padding: 2px 10px;
  border-radius: 10px;
  margin-left: auto;
}

/* ── News Card ── */
.card {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
  margin-bottom: 12px;
  transition: all 0.2s;
  position: relative;
}
.card:hover {
  background: var(--card-hover);
  border-color: var(--accent);
  box-shadow: 0 4px 12px var(--shadow);
}
.card-accent-border {
  position: absolute;
  top: 8px;
  left: 0;
  width: 4px;
  height: calc(100% - 16px);
  border-radius: 0 3px 3px 0;
}

/* Title row */
.card-title-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.card-title-link {
  font-size: 1.05rem;
  font-weight: 700;
  color: var(--text);
  line-height: 1.4;
  flex: 1;
  min-width: 0;
}
.card-title-link:hover {
  color: var(--link);
}
.card-title-link .emoji-prefix {
  margin-right: 4px;
}

/* Badges */
.badge-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 0.68rem;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 20px;
  white-space: nowrap;
  letter-spacing: 0.02em;
  line-height: 1.3;
}
.badge-signal {
  color: var(--badge-text);
}
.badge-source {
  background: var(--bg3);
  color: var(--text2);
  border: 1px solid var(--border);
}
.badge-stars {
  background: rgba(227, 179, 65, 0.15);
  color: #e3b341;
  border: 1px solid rgba(227, 179, 65, 0.3);
}

/* Description — the main readable content */
.card-description {
  font-size: 0.95rem;
  line-height: 1.75;
  color: var(--text);
  margin-bottom: 8px;
}

/* Why (short one-liner) — metadata fallback */
.card-why {
  font-size: 0.82rem;
  color: var(--text2);
  line-height: 1.5;
}

/* Metadata bar */
.card-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  margin-top: 4px;
}
.card-meta .meta-item {
  font-size: 0.75rem;
  color: var(--text2);
}

/* ── Summary Box ── */
.summary-box {
  background: linear-gradient(135deg, var(--bg2), var(--bg3));
  border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  border-radius: 12px;
  padding: 20px 24px;
  margin-top: 32px;
  margin-bottom: 32px;
  font-size: 0.95rem;
  line-height: 1.8;
}
.summary-box .summary-label {
  font-weight: 700;
  color: var(--accent);
  margin-bottom: 6px;
  font-size: 0.82rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

/* ── Featured Section (Index) ── */
.featured-section {
  margin-bottom: 36px;
}
.featured-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  font-weight: 700;
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 16px;
}
.featured-card {
  background: var(--featured-bg);
  border: 1px solid var(--featured-border);
  border-radius: 14px;
  padding: 24px 28px;
  transition: all 0.2s;
}
.featured-card:hover {
  box-shadow: 0 4px 16px var(--shadow);
}
.featured-card .fc-date {
  font-size: 1.35rem;
  font-weight: 800;
  margin-bottom: 4px;
}
.featured-card .fc-date a {
  color: var(--text);
}
.featured-card .fc-date a:hover {
  color: var(--link);
}
.featured-card .fc-meta {
  color: var(--text2);
  font-size: 0.85rem;
  margin-bottom: 8px;
}
.featured-card .fc-summary {
  font-size: 0.92rem;
  line-height: 1.7;
  color: var(--text);
}

/* ── History Entry (Index) ── */
.history-entry {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px 20px;
  margin-bottom: 10px;
  transition: all 0.15s;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
}
.history-entry:hover {
  background: var(--card-hover);
  border-color: var(--accent);
}
.history-entry .he-date {
  font-size: 1rem;
  font-weight: 700;
}
.history-entry .he-date a {
  color: var(--text);
}
.history-entry .he-date a:hover {
  color: var(--link);
}
.history-entry .he-badge {
  font-size: 0.72rem;
  background: var(--bg3);
  color: var(--text2);
  padding: 2px 10px;
  border-radius: 10px;
}
.history-entry .he-snippet {
  font-size: 0.85rem;
  color: var(--text2);
  flex-basis: 100%;
  margin-top: 4px;
  line-height: 1.5;
}

/* ── Week Entry (Index & Weekly page) ── */
.week-entry {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 22px;
  margin-bottom: 12px;
  transition: all 0.15s;
}
.week-entry:hover {
  background: var(--card-hover);
  border-color: var(--accent);
}
.week-entry .we-title {
  font-size: 1.1rem;
  font-weight: 700;
  margin-bottom: 4px;
}
.week-entry .we-title a { color: var(--text); }
.week-entry .we-title a:hover { color: var(--link); }
.week-entry .we-meta {
  color: var(--text2);
  font-size: 0.85rem;
  margin-bottom: 8px;
}
.week-entry .we-stats {
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
  font-size: 0.82rem;
}
.week-entry .we-stats span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* ── Daily Mini (for weekly page day list) ── */
.daily-mini {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--bg3);
  border-radius: 8px;
  padding: 4px 12px;
  font-size: 0.82rem;
  margin: 3px 5px 3px 0;
}

/* ── Footer ── */
.footer {
  border-top: 1px solid var(--border);
  padding-top: 20px;
  margin-top: 48px;
  text-align: center;
  color: var(--text2);
  font-size: 0.8rem;
  line-height: 1.8;
}
.footer a { color: var(--text2); }
.footer a:hover { color: var(--link); }

/* ── Responsive ── */
@media (max-width: 640px) {
  .container { padding: 20px 14px; }
  .header h1 { font-size: 1.35rem; }
  .stats { gap: 8px; }
  .stat-box { min-width: 60px; padding: 8px 14px; }
  .stat-box .num { font-size: 1.15rem; }
  .card { padding: 14px 16px; }
  .card-title-link { font-size: 0.95rem; }
  .card-description { font-size: 0.88rem; }
  .featured-card { padding: 18px 20px; }
  .featured-card .fc-date { font-size: 1.15rem; }
}

@media (max-width: 400px) {
  .container { padding: 14px 10px; }
  .header h1 { font-size: 1.15rem; }
  .stat-box { min-width: 50px; padding: 6px 10px; }
  .stat-box .num { font-size: 1rem; }
  .section-header { flex-wrap: wrap; }
}
"""


# ---------------------------------------------------------------------------
# HTML skeleton
# ---------------------------------------------------------------------------

HTML_HEAD = """<!DOCTYPE html>
<html lang="zh-HK">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
{css}
</style>
</head>
<body>
<div class="container">

<header class="header">
  <h1>{title_html}</h1>
  <div class="sub">{subtitle}</div>
  <nav class="nav">
    <a href="index.html">🏠 主頁</a>
    {nav_links}
  </nav>
</header>
"""

HTML_FOOTER = """<footer class="footer">
  <p>🤖 由 AI 自動生成 · <a href="https://github.com/fafafung/ai-news">GitHub</a></p>
  <p style="margin-top:4px;font-size:0.75rem;opacity:0.7;">AI 新聞檔案 · 每日更新</p>
</footer>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def extract_domain(url):
    """Extract readable domain from a URL (e.g. github.com, huggingface.co)."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        # Remove www. prefix
        domain = re.sub(r"^www\.", "", domain)
        return domain
    except Exception:
        return ""


def format_stars(n):
    """Format star count: 1.2k, 4.2k, 1.2M, etc."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def render_badge(signal):
    """Render a signal badge HTML snippet."""
    emoji, color = SIGNAL_BADGES.get(signal, ("❓", "#666"))
    return (
        f'<span class="badge badge-signal" '
        f'style="background:{color}">'
        f"{emoji}</span>"
    )


def render_stars_badge(n):
    """Render a star count badge if n > 0."""
    if n > 0:
        return f'<span class="badge badge-stars">⭐ {format_stars(n)}</span>'
    return ""


def render_source_badge(domain):
    """Render a source domain badge."""
    if not domain:
        return ""
    return f'<span class="badge badge-source">{domain}</span>'


def render_item(item):
    """Render a single news item as a rich card."""
    category = item.get("category", "general")
    title = item.get("title", "Untitled")
    description = item.get("description", "")
    why = item.get("why", "")
    link = item.get("link", "")
    stars = item.get("stars", 0)
    signal = item.get("signal", "")
    source_domain = item.get("source_domain", "") or extract_domain(link)

    # Accent colour for this category
    accent = CATEGORY_ACCENT.get(category, "#58a6ff")
    # Emoji prefix for the title
    emoji_prefix = TITLE_EMOJI.get(category, "📌")

    parts = ['<div class="card">']

    # Accent border
    parts.append(
        f'<div class="card-accent-border" '
        f'style="background:{accent};opacity:0.6;"></div>'
    )

    # Title row
    parts.append('<div class="card-title-row">')
    parts.append(
        f'<a href="{link}" target="_blank" rel="noopener" '
        f'class="card-title-link">'
        f'<span class="emoji-prefix">{emoji_prefix}</span>{title}</a>'
    )

    # Badges in title row
    badges = []
    if signal:
        badges.append(render_badge(signal))
    if stars:
        badges.append(render_stars_badge(stars))
    if badges:
        parts.append(f'<div class="badge-row">{"".join(badges)}</div>')

    parts.append("</div>")  # card-title-row

    # Description (main readable content, 2-3 sentences Chinese)
    if description:
        parts.append(
            f'<div class="card-description">{description}</div>'
        )
    elif why:
        # Fallback: if no description, use why as the readable content
        parts.append(
            f'<div class="card-description">{why}</div>'
        )

    # Metadata bar
    meta_items = []
    if source_domain:
        meta_items.append(render_source_badge(source_domain))
    if not description and why:
        # If description is set, that's the main content; why is metadata
        pass  # why was already shown above as fallback
    elif why and description:
        # Both present: show why as a "quick summary" in meta
        meta_items.append(
            f'<span class="meta-item">💬 {why}</span>'
        )

    if meta_items:
        parts.append(f'<div class="card-meta">{"".join(meta_items)}</div>')

    parts.append("</div>")
    return "\n".join(parts)


def render_section(category, items):
    """Render a category section with cards."""
    if not items:
        return ""
    icon = CATEGORY_ICONS.get(category, "📌")
    label = CATEGORY_LABELS.get(category, category.capitalize())
    accent = CATEGORY_ACCENT.get(category, "#58a6ff")

    parts = [
        '<div class="section">',
        f'<div class="section-header" style="border-bottom-color:{accent}40;">',
        f'<span class="section-icon">{icon}</span>',
        f'<span class="section-label" style="color:{accent};">{label}</span>',
        f'<span class="section-count">{len(items)} 條</span>',
        "</div>",
    ]
    for item in items:
        parts.append(render_item(item))
    parts.append("</div>")
    return "\n".join(parts)


def render_stats(items, date_str=None, dow=None):
    """Render the stats bar with day info if provided."""
    total = len(items)
    cat_counts = {}
    for item in items:
        cat = item.get("category", "general")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    parts = ['<div class="stats">']

    # Total stat
    parts.append(
        f'<div class="stat-box"><span class="num">{total}</span>'
        f'<span class="label">新聞總數</span></div>'
    )

    # Day of week (if provided)
    if dow:
        weekday_full = WEEKDAY_NAMES.get(dow, f"星期{dow}")
        parts.append(
            f'<div class="stat-box dow-box"><span class="num">'
            f"{weekday_full}</span>"
            f'<span class="label">星期</span></div>'
        )

    # Category counts
    for cat in CATEGORY_ORDER:
        cnt = cat_counts.get(cat, 0)
        if cnt:
            icon = CATEGORY_ICONS.get(cat, "📌")
            label = CATEGORY_LABELS.get(cat, cat.capitalize())
            parts.append(
                f'<div class="stat-box"><span class="num">{cnt}</span>'
                f'<span class="label">{icon} {label}</span></div>'
            )

    parts.append("</div>")
    return "\n".join(parts)


def load_index_data():
    """Load index_data.json, return dict or empty default."""
    if os.path.exists(INDEX_DATA):
        with open(INDEX_DATA, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"entries": []}


def save_index_data(data):
    """Write index_data.json."""
    with open(INDEX_DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Daily page generation
# ---------------------------------------------------------------------------

def generate_daily(json_path):
    """Generate a daily HTML page from a JSON data file."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    date_str = data["date"]          # e.g. "2026-06-22"
    dow = data.get("dow", "")        # e.g. "一"
    items = data.get("items", [])
    summary = data.get("summary", "")

    # Parse date
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    iso_year, iso_week, iso_dow = dt.isocalendar()

    # Auto-extract source_domain for items that don't have it
    for item in items:
        if not item.get("source_domain"):
            item["source_domain"] = extract_domain(item.get("link", ""))

    # Group items by category, preserving specified order
    grouped = OrderedDict()
    for cat in CATEGORY_ORDER:
        grouped[cat] = []
    for item in items:
        cat = item.get("category", "general")
        if cat in grouped:
            grouped[cat].append(item)
        else:
            grouped[cat] = [item]

    # Build nav links
    nav_links = f'<a href="index.html">📋 目錄</a>'
    nav_links += (
        f'<a href="weekly-{iso_year}-W{iso_week:02d}.html">'
        f"📊 第{iso_week:02d}週</a>"
    )

    # Title
    title = f"AI 新聞 · {date_str}"
    if dow:
        title_html = f"AI 新聞 · {date_str} <span class=\"date-weekday\">星期{dow}</span>"
        subtitle = f"星期{dow} · {date_str}"
    else:
        title_html = f"AI 新聞 · {date_str}"
        subtitle = date_str

    # Stats
    stats_html = render_stats(items, date_str, dow)

    # Sections
    sections_html = ""
    for cat in CATEGORY_ORDER:
        sections_html += render_section(cat, grouped.get(cat, []))
    # Also render any categories not in the standard order
    for cat, cat_items in grouped.items():
        if cat not in CATEGORY_ORDER and cat_items:
            sections_html += render_section(cat, cat_items)

    # Summary
    summary_html = ""
    if summary:
        summary_html = (
            f'<div class="summary-box">'
            f'<div class="summary-label">📝 總結</div>'
            f"{summary}</div>"
        )

    body = stats_html + sections_html + summary_html

    full_html = HTML_HEAD.format(
        title=title,
        title_html=title_html,
        subtitle=subtitle,
        nav_links=nav_links,
        css=CSS,
    ) + body + HTML_FOOTER

    # Write daily HTML
    daily_path = os.path.join(BASE_DIR, f"{date_str}.html")
    with open(daily_path, "w", encoding="utf-8") as f:
        f.write(full_html)

    print(f"✅ Generated daily page: {daily_path}")

    # Update index_data.json
    index_data = load_index_data()

    # Truncate summary for index_data
    truncated_summary = (
        summary[:120] + "…" if len(summary) > 120 else summary
    )

    # Build a short snippet from first item
    first_item_snippet = ""
    if items:
        first_title = items[0].get("title", "")
        first_desc = items[0].get("description", "") or items[0].get("why", "")
        if first_desc:
            snippet_text = f"{first_title}: {first_desc}"
            first_item_snippet = (
                snippet_text[:100] + "…" if len(snippet_text) > 100
                else snippet_text
            )

    # Update or append this entry
    found = False
    for entry in index_data["entries"]:
        if entry.get("date") == date_str:
            entry.update({
                "date": date_str,
                "dow": dow,
                "title": title,
                "item_count": len(items),
                "iso_year": iso_year,
                "iso_week": iso_week,
                "summary": truncated_summary,
                "first_item_snippet": first_item_snippet,
            })
            found = True
            break
    if not found:
        index_data["entries"].append({
            "date": date_str,
            "dow": dow,
            "title": title,
            "item_count": len(items),
            "iso_year": iso_year,
            "iso_week": iso_week,
            "summary": truncated_summary,
            "first_item_snippet": first_item_snippet,
        })

    # Sort entries by date descending (newest first)
    index_data["entries"].sort(key=lambda e: e.get("date", ""), reverse=True)
    save_index_data(index_data)
    print(f"📝 Updated {INDEX_DATA}")

    # Regenerate index.html
    generate_index()
    print(f"📋 Regenerated {INDEX_HTML}")

    return daily_path


# ---------------------------------------------------------------------------
# Index page generation
# ---------------------------------------------------------------------------

def generate_index():
    """Generate index.html from index_data.json.

    Layout:
      - Featured: most recent day as "today's highlights"
      - History: list of past days with date, item count, first 100 chars of first item
      - Weekly section: cards for each week with total item count and date range
    """
    index_data = load_index_data()
    entries = index_data.get("entries", [])

    # Compute unique weeks from entries
    seen_weeks = {}
    for entry in entries:
        key = (entry.get("iso_year", 0), entry.get("iso_week", 0))
        if key != (0, 0):
            if key not in seen_weeks:
                seen_weeks[key] = {"entries": [], "total_items": 0}
            seen_weeks[key]["entries"].append(entry)
            seen_weeks[key]["total_items"] += entry.get("item_count", 0)

    sorted_weeks = sorted(seen_weeks.keys(), reverse=True)

    title = "AI 新聞檔案"
    total_days = len(entries)
    total_items = sum(e.get("item_count", 0) for e in entries)
    subtitle = (
        f"一共 {total_days} 天 · {total_items} 條新聞記錄"
    )
    if sorted_weeks:
        subtitle += f" · {len(sorted_weeks)} 個星期"

    nav_links = ""

    body_parts = []

    # ── Featured: most recent day ──
    if entries:
        featured = entries[0]  # newest first
        fc_date = featured.get("date", "")
        fc_dow = featured.get("dow", "")
        fc_count = featured.get("item_count", 0)
        fc_summary = featured.get("summary", "")
        fc_first = featured.get("first_item_snippet", "")

        featured_html = [
            '<div class="featured-section">',
            '<div class="featured-label">⭐ 今日精選</div>',
            '<div class="featured-card">',
            f'<div class="fc-date"><a href="{fc_date}.html">📅 {fc_date}',
        ]
        if fc_dow:
            featured_html.append(f' 星期{fc_dow}')
        featured_html.append(f'</a></div>')
        featured_html.append(
            f'<div class="fc-meta">📰 {fc_count} 條新聞</div>'
        )
        if fc_summary:
            featured_html.append(
                f'<div class="fc-summary">{fc_summary}</div>'
            )
        elif fc_first:
            featured_html.append(
                f'<div class="fc-summary">{fc_first}</div>'
            )
        featured_html.append("</div></div>")
        body_parts.append("\n".join(featured_html))

    # ── Weekly section ──
    if sorted_weeks:
        weekly_parts = [
            '<div class="section">',
            '<div class="section-header" style="border-bottom-color:var(--accent);">',
            '<span class="section-icon">📊</span>',
            '<span class="section-label">週報</span>',
            f'<span class="section-count">{len(sorted_weeks)} 個星期</span>',
            "</div>",
        ]
        for iso_year, iso_week in sorted_weeks:
            week_info = seen_weeks[(iso_year, iso_week)]
            week_entries = week_info["entries"]
            week_total = week_info["total_items"]
            week_days = len(week_entries)

            # Compute date range
            try:
                monday = date.fromisocalendar(iso_year, iso_week, 1)
                sunday = monday + timedelta(days=6)
                date_range = (
                    f"{monday.strftime('%Y-%m-%d')} — "
                    f"{sunday.strftime('%Y-%m-%d')}"
                )
            except (ValueError, TypeError):
                date_range = ""

            weekly_parts.extend([
                '<div class="week-entry">',
                '<div class="we-title">',
                f'<a href="weekly-{iso_year}-W{iso_week:02d}.html">',
                f"📊 第{iso_week:02d}週 ({iso_year})</a></div>",
                f'<div class="we-meta">{date_range}</div>',
                '<div class="we-stats">',
                f"<span>📅 {week_days} 天</span>",
                f"<span>📰 {week_total} 條新聞</span>",
                "</div></div>",
            ])
        weekly_parts.append("</div>")
        body_parts.append("\n".join(weekly_parts))

    # ── History: daily list (skip the featured first entry) ──
    history_entries = entries[1:] if entries else []
    if history_entries:
        history_parts = [
            '<div class="section">',
            '<div class="section-header" style="border-bottom-color:var(--border);">',
            '<span class="section-icon">📅</span>',
            '<span class="section-label">歷史記錄</span>',
            f'<span class="section-count">{len(history_entries)} 天</span>',
            "</div>",
        ]
        for entry in history_entries:
            date_str = entry.get("date", "")
            dow = entry.get("dow", "")
            item_count = entry.get("item_count", 0)
            snippet = entry.get("first_item_snippet", "")

            history_parts.append('<div class="history-entry">')
            history_parts.append(
                f'<div class="he-date">'
                f'<a href="{date_str}.html">📅 {date_str}'
            )
            if dow:
                history_parts.append(f' 星期{dow}')
            history_parts.append("</a></div>")
            history_parts.append(
                f'<span class="he-badge">📰 {item_count} 條</span>'
            )
            if snippet:
                history_parts.append(
                    f'<div class="he-snippet">{snippet}</div>'
                )
            history_parts.append("</div>")

        history_parts.append("</div>")
        body_parts.append("\n".join(history_parts))
    else:
        body_parts.append("<p>暫無記錄</p>")

    body = "\n".join(body_parts)

    full_html = HTML_HEAD.format(
        title=title,
        title_html=title,
        subtitle=subtitle,
        nav_links=nav_links,
        css=CSS,
    ) + body + HTML_FOOTER

    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(full_html)

    return INDEX_HTML


# ---------------------------------------------------------------------------
# Weekly page generation
# ---------------------------------------------------------------------------

def generate_weekly():
    """Scan index_data.json, group entries by ISO week, generate weekly pages."""
    index_data = load_index_data()
    entries = index_data.get("entries", [])

    if not entries:
        print("⚠️  No entries in index_data.json. Nothing to do.")
        return

    # Group by ISO year + week
    weeks = {}
    for entry in entries:
        iso_year = entry.get("iso_year")
        iso_week = entry.get("iso_week")
        if iso_year is None or iso_week is None:
            # Try to parse from date
            try:
                dt = datetime.strptime(entry["date"], "%Y-%m-%d")
                iso_year, iso_week, _ = dt.isocalendar()
            except (ValueError, KeyError):
                continue
        key = (iso_year, iso_week)
        if key not in weeks:
            weeks[key] = []
        weeks[key].append(entry)

    # Sort weeks: newest first
    sorted_weeks = sorted(weeks.keys(), reverse=True)

    for iso_year, iso_week in sorted_weeks:
        week_entries = weeks[(iso_year, iso_week)]

        # Calculate week date range (Monday to Sunday)
        monday = date.fromisocalendar(iso_year, iso_week, 1)
        sunday = monday + timedelta(days=6)

        total_items = sum(e.get("item_count", 0) for e in week_entries)
        total_days = len(week_entries)

        title = f"AI 新聞 · 第{iso_week:02d}週 ({iso_year})"
        date_range = (
            f"{monday.strftime('%Y-%m-%d')} — {sunday.strftime('%Y-%m-%d')}"
        )
        subtitle = (
            f"{date_range} · "
            f"{total_days} 天 · {total_items} 條新聞"
        )

        nav_links = (
            f'<a href="index.html">📋 目錄</a>'
        )

        # Stats
        stats_parts = [
            '<div class="stats">',
            f'<div class="stat-box"><span class="num">{total_days}</span>'
            f'<span class="label">天數</span></div>',
            f'<div class="stat-box"><span class="num">{total_items}</span>'
            f'<span class="label">新聞總數</span></div>',
            '</div>',
        ]

        # Sort entries by date descending
        sorted_entries = sorted(
            week_entries, key=lambda e: e.get("date", ""), reverse=True
        )

        # Day-by-day breakdown with richer cards
        days_html = ""
        for entry in sorted_entries:
            date_str = entry.get("date", "")
            dow = entry.get("dow", "")
            item_count = entry.get("item_count", 0)
            summary = entry.get("summary", "")
            snippet = entry.get("first_item_snippet", "")

            days_html += (
                '<div class="week-entry">'
                f'<div class="we-title">'
                f'<a href="{date_str}.html">📅 {date_str}'
            )
            if dow:
                days_html += f' 星期{dow}'
            days_html += "</a></div>"
            days_html += (
                '<div class="we-stats">'
                f"<span>📰 {item_count} 條新聞</span>"
                "</div>"
            )
            if summary:
                days_html += (
                    f'<div style="margin-top:6px;font-size:0.88rem;'
                    f'color:var(--text2);line-height:1.6;">'
                    f"{summary}</div>"
                )
            elif snippet:
                days_html += (
                    f'<div style="margin-top:6px;font-size:0.85rem;'
                    f'color:var(--text2);line-height:1.5;">'
                    f"{snippet}</div>"
                )
            days_html += "</div>"

        body = "\n".join(stats_parts) + "\n" + days_html

        full_html = HTML_HEAD.format(
            title=title,
            title_html=title,
            subtitle=subtitle,
            nav_links=nav_links,
            css=CSS,
        ) + body + HTML_FOOTER

        # Write weekly page
        weekly_filename = f"weekly-{iso_year}-W{iso_week:02d}.html"
        weekly_path = os.path.join(BASE_DIR, weekly_filename)
        with open(weekly_path, "w", encoding="utf-8") as f:
            f.write(full_html)

        print(f"✅ Generated weekly page: {weekly_path}")

    # Regenerate index.html with weekly links
    generate_index()
    print(f"📋 Regenerated {INDEX_HTML} with weekly links")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "daily":
        if len(sys.argv) < 3:
            print("Usage: python3 generate-news-html.py daily <json-path>")
            sys.exit(1)
        json_path = sys.argv[2]
        if not os.path.exists(json_path):
            print(f"❌ File not found: {json_path}")
            sys.exit(1)
        generate_daily(json_path)

    elif mode == "weekly":
        generate_weekly()

    elif mode == "index":
        generate_index()
        print(f"📋 Regenerated {INDEX_HTML}")

    else:
        print(f"❌ Unknown mode: {mode}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
