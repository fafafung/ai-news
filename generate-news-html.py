#!/usr/bin/env python3
"""
AI News Archive — Static HTML Generator
========================================
Generates daily and weekly HTML pages for the AI news archive system.

Usage:
    python3 generate-news-html.py daily /path/to/daily-news.json
    python3 generate-news-html.py weekly

Daily mode:
    Reads a JSON file (see README for schema), generates a dark-theme HTML page
    at /opt/data/ai-news/YYYY-MM-DD.html, updates index_data.json, and
    regenerates index.html.

Weekly mode:
    Scans index_data.json, groups entries by ISO week, generates
    weekly-YYYY-WWW.html with aggregate stats, and regenerates index.html.

All paths are relative so the site works both locally and on Vercel.
"""

import json
import os
import sys
from datetime import datetime, date, timedelta
from collections import OrderedDict
import calendar

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
    "github": "GitHub",
    "tech": "Tech",
    "general": "General",
    "research": "Research",
}

CATEGORY_ORDER = ["github", "tech", "general", "research"]

SIGNAL_BADGES = {
    "new": ("🆕", "#e74c3c"),       # red-ish — new paradigm
    "big": ("#", "#8e44ad"),         # purple-ish — big company (icon won't render, use 🏢)
    "hot": ("🔥", "#e67e22"),        # orange-ish — viral
    "pain": ("💊", "#27ae60"),       # green-ish — solves problem
    "para": ("💡", "#2980b9"),       # blue-ish — new category
}

# Override 'big' to use the building emoji
SIGNAL_BADGES["big"] = ("🏢", "#8e44ad")


# ---------------------------------------------------------------------------
# HTML skeleton
# ---------------------------------------------------------------------------

HTML_HEAD = """\
<!DOCTYPE html>
<html lang="zh-HK">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI News Archive — {title}</title>
<style>
:root {{
  --bg: #0d1117;
  --bg2: #161b22;
  --bg3: #1c2333;
  --text: #e6edf3;
  --text2: #8b949e;
  --text3: #58a6ff;
  --border: #30363d;
  --accent: #58a6ff;
  --card-hover: #1c2333;
  --link: #58a6ff;
  --stat-bg: #0d1117;
}}
@media (prefers-color-scheme: light) {{
  :root {{
    --bg: #ffffff;
    --bg2: #f6f8fa;
    --bg3: #eef1f5;
    --text: #1f2328;
    --text2: #656d76;
    --text3: #0969da;
    --border: #d0d7de;
    --accent: #0969da;
    --card-hover: #f3f4f6;
    --link: #0969da;
    --stat-bg: #ffffff;
  }}
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans",
    "Noto Sans CJK SC", "PingFang SC", "Microsoft YaHei", Helvetica, Arial,
    sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.6;
  padding: 0;
  -webkit-font-smoothing: antialiased;
}}
a {{ color: var(--link); text-decoration: none; }}
a:hover {{ text-decoration: underline; }}
.container {{ max-width: 880px; margin: 0 auto; padding: 24px 16px; }}

/* Header */
.header {{
  border-bottom: 1px solid var(--border);
  padding-bottom: 20px;
  margin-bottom: 24px;
}}
.header h1 {{
  font-size: 1.6rem;
  font-weight: 700;
  margin-bottom: 4px;
  letter-spacing: -0.01em;
}}
.header .sub {{
  color: var(--text2);
  font-size: 0.9rem;
}}
.header .nav {{
  margin-top: 12px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 0.9rem;
}}
.header .nav a {{
  color: var(--text2);
  padding: 4px 10px;
  border-radius: 6px;
  background: var(--bg2);
  transition: background 0.15s;
}}
.header .nav a:hover {{
  background: var(--bg3);
  text-decoration: none;
}}

/* Stats bar */
.stats {{
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  margin-bottom: 24px;
  font-size: 0.85rem;
}}
.stat-box {{
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 70px;
}}
.stat-box .num {{
  font-size: 1.3rem;
  font-weight: 700;
  color: var(--accent);
}}
.stat-box .label {{
  color: var(--text2);
  font-size: 0.75rem;
  margin-top: 2px;
}}

/* Category sections */
.section {{
  margin-bottom: 28px;
}}
.section-title {{
  font-size: 1.2rem;
  font-weight: 600;
  margin-bottom: 12px;
  padding-bottom: 6px;
  border-bottom: 2px solid var(--accent);
  display: flex;
  align-items: center;
  gap: 6px;
}}

/* Cards */
.card {{
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 10px;
  transition: background 0.15s, border-color 0.15s;
}}
.card:hover {{
  background: var(--card-hover);
  border-color: var(--accent);
}}
.card-title {{
  font-size: 1rem;
  font-weight: 600;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}}
.card-title a {{
  color: var(--text);
}}
.card-title a:hover {{
  color: var(--link);
}}
.card-why {{
  color: var(--text2);
  font-size: 0.88rem;
  margin-top: 2px;
}}

/* Badges */
.badge {{
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 0.7rem;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 12px;
  white-space: nowrap;
  letter-spacing: 0.02em;
}}
.badge-signal {{
  color: #fff;
}}

/* Stars */
.stars {{
  color: #e3b341;
  font-size: 0.8rem;
  font-weight: 500;
  white-space: nowrap;
}}

/* Summary block */
.summary-box {{
  background: linear-gradient(135deg, var(--bg2), var(--bg3));
  border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  border-radius: 8px;
  padding: 16px 20px;
  margin-top: 28px;
  margin-bottom: 28px;
  font-size: 0.95rem;
  line-height: 1.7;
}}
.summary-box .label {{
  font-weight: 700;
  color: var(--accent);
  margin-bottom: 4px;
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}

/* Footer */
.footer {{
  border-top: 1px solid var(--border);
  padding-top: 16px;
  margin-top: 40px;
  text-align: center;
  color: var(--text2);
  font-size: 0.82rem;
}}
.footer a {{ color: var(--text2); }}

/* Weekly-specific */
.week-entry {{
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 18px 20px;
  margin-bottom: 14px;
  transition: background 0.15s;
}}
.week-entry:hover {{
  background: var(--card-hover);
}}
.week-entry .week-title {{
  font-size: 1.15rem;
  font-weight: 700;
  margin-bottom: 4px;
}}
.week-entry .week-meta {{
  color: var(--text2);
  font-size: 0.85rem;
  margin-bottom: 8px;
}}
.week-entry .week-stats {{
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 0.82rem;
}}

/* Daily item in weekly view */
.daily-mini {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--bg3);
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 0.82rem;
  margin: 2px 4px 2px 0;
}}

/* Responsive */
@media (max-width: 600px) {{
  .container {{ padding: 16px 12px; }}
  .header h1 {{ font-size: 1.3rem; }}
  .stats {{ gap: 8px; }}
  .stat-box {{ min-width: 60px; padding: 8px 12px; }}
  .stat-box .num {{ font-size: 1.1rem; }}
  .card {{ padding: 12px 14px; }}
}}
</style>
</head>
<body>
<div class="container">

<header class="header">
  <h1>{title}</h1>
  <div class="sub">{subtitle}</div>
  <nav class="nav">
    <a href="index.html">🏠 主頁</a>
    {nav_links}
  </nav>
</header>
"""

HTML_FOOTER = """\
<footer class="footer">
  <p>🤖 由 AI 自動生成 · <a href="https://github.com/fafafung/ai-news">GitHub</a></p>
</footer>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        f'{emoji}</span>'
    )


def render_stars(n):
    """Render a stars span if n > 0."""
    if n > 0:
        return f'<span class="stars">⭐ {format_stars(n)}</span>'
    return ""


def render_item(item):
    """Render a single news item card."""
    category = item.get("category", "general")
    icon = CATEGORY_ICONS.get(category, "📌")
    title = item.get("title", "Untitled")
    why = item.get("why", "")
    link = item.get("link", "")
    stars = item.get("stars", 0)
    signal = item.get("signal", "")

    parts = [
        f'<div class="card-title">',
        f'<a href="{link}" target="_blank" rel="noopener">{icon} {title}</a>',
    ]
    if signal:
        parts.append(render_badge(signal))
    if stars:
        parts.append(render_stars(stars))
    parts.append("</div>")

    if why:
        parts.append(f'<div class="card-why">{why}</div>')

    return f'<div class="card">{"".join(parts)}</div>'


def render_section(category, items):
    """Render a category section."""
    if not items:
        return ""
    icon = CATEGORY_ICONS.get(category, "📌")
    label = CATEGORY_LABELS.get(category, category.capitalize())
    parts = [f'<div class="section">',
             f'<div class="section-title">{icon} {label}</div>']
    for item in items:
        parts.append(render_item(item))
    parts.append("</div>")
    return "\n".join(parts)


def render_stats(items):
    """Render the stats bar."""
    total = len(items)
    cat_counts = {}
    for item in items:
        cat = item.get("category", "general")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    parts = ['<div class="stats">']
    # Total
    parts.append(
        f'<div class="stat-box"><span class="num">{total}</span>'
        f'<span class="label">總計</span></div>'
    )
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

    # Build nav link back
    nav_links = f'<a href="index.html">📋 目錄</a>'

    title = f"AI 新聞 · {date_str}"
    if dow:
        subtitle = f"星期{dow} · {date_str}"
    else:
        subtitle = date_str

    # Stats
    stats_html = render_stats(items)

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
        summary_html = f'<div class="summary-box"><div class="label">📝 總結</div>{summary}</div>'

    body = stats_html + sections_html + summary_html

    full_html = HTML_HEAD.format(
        title=title,
        subtitle=subtitle,
        nav_links=nav_links,
    ) + body + HTML_FOOTER

    # Write daily HTML
    daily_path = os.path.join(BASE_DIR, f"{date_str}.html")
    with open(daily_path, "w", encoding="utf-8") as f:
        f.write(full_html)

    print(f"✅ Generated daily page: {daily_path}")

    # Update index_data.json
    index_data = load_index_data()

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
                "summary": summary[:120] + "…" if len(summary) > 120 else summary,
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
            "summary": summary[:120] + "…" if len(summary) > 120 else summary,
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
    """Generate index.html from index_data.json."""
    index_data = load_index_data()
    entries = index_data.get("entries", [])

    title = "AI 新聞檔案"
    subtitle = (
        f"一共 {len(entries)} 天的新聞記錄"
    )

    nav_links = ""

    # Build the daily list HTML
    daily_rows = []
    for entry in entries:
        date_str = entry.get("date", "")
        dow = entry.get("dow", "")
        item_count = entry.get("item_count", 0)
        summary = entry.get("summary", "")

        row_parts = [
            '<div class="week-entry">',
            f'<div class="week-title">'
            f'<a href="{date_str}.html">📅 {date_str}'
        ]
        if dow:
            row_parts.append(f' 星期{dow}')
        row_parts.append(f'</a></div>')

        row_parts.append(
            f'<div class="week-stats">'
            f'<span>📰 {item_count} 條新聞</span>'
            f'</div>'
        )

        if summary:
            row_parts.append(
                f'<div class="card-why" style="margin-top:6px;">{summary}</div>'
            )

        row_parts.append('</div>')
        daily_rows.append("\n".join(row_parts))

    body = "\n".join(daily_rows) if daily_rows else "<p>暫無記錄</p>"

    full_html = HTML_HEAD.format(
        title=title,
        subtitle=subtitle,
        nav_links=nav_links,
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
        # Using ISO week: Jan 4 is always in week 1
        monday = date.fromisocalendar(iso_year, iso_week, 1)
        sunday = monday + timedelta(days=6)

        total_items = sum(e.get("item_count", 0) for e in week_entries)
        total_days = len(week_entries)

        title = f"AI 新聞 · 第{iso_week:02d}週 ({iso_year})"
        subtitle = (
            f"{monday.strftime('%Y-%m-%d')} — {sunday.strftime('%Y-%m-%d')} · "
            f"{total_days} 天 · {total_items} 條新聞"
        )

        nav_links = '<a href="index.html">📋 目錄</a>'

        # Stats
        stats_parts = [
            '<div class="stats">',
            f'<div class="stat-box"><span class="num">{total_days}</span>'
            f'<span class="label">天數</span></div>',
            f'<div class="stat-box"><span class="num">{total_items}</span>'
            f'<span class="label">新聞總數</span></div>',
            '</div>',
        ]

        # Daily entries for this week
        daily_blocks = []
        # Sort entries by date descending
        sorted_entries = sorted(week_entries, key=lambda e: e.get("date", ""), reverse=True)
        for entry in sorted_entries:
            date_str = entry.get("date", "")
            dow = entry.get("dow", "")
            item_count = entry.get("item_count", 0)
            summary = entry.get("summary", "")

            block = [
                f'<div class="daily-mini">'
                f'<a href="{date_str}.html">📅 {date_str}</a>'
            ]
            if dow:
                block.append(f' 星期{dow}')
            block.append(f' · {item_count} 項')
            block.append('</div>')

            daily_blocks.extend(block)

        daily_links = "\n".join(daily_blocks)

        # Day-by-day breakdown
        days_html = ""
        for entry in sorted_entries:
            date_str = entry.get("date", "")
            dow = entry.get("dow", "")
            item_count = entry.get("item_count", 0)
            summary = entry.get("summary", "")

            days_html += (
                f'<div class="week-entry" style="padding:12px 16px;">'
                f'<div class="week-title" style="font-size:1rem;">'
                f'<a href="{date_str}.html">📅 {date_str}'
            )
            if dow:
                days_html += f' 星期{dow}'
            days_html += f'</a>'
            days_html += f' <span style="color:var(--text2);font-size:0.8rem;">({item_count} 條)</span>'
            days_html += '</div>'
            if summary:
                days_html += f'<div class="card-why" style="margin-top:4px;">{summary}</div>'
            days_html += '</div>'

        body = "\n".join(stats_parts) + "\n" + days_html

        full_html = HTML_HEAD.format(
            title=title,
            subtitle=subtitle,
            nav_links=nav_links,
        ) + body + HTML_FOOTER

        # Write weekly page
        weekly_filename = f"weekly-{iso_year}-W{iso_week:02d}.html"
        weekly_path = os.path.join(BASE_DIR, weekly_filename)
        with open(weekly_path, "w", encoding="utf-8") as f:
            f.write(full_html)

        print(f"✅ Generated weekly page: {weekly_path}")

    # Update index.html with links to weekly pages
    generate_index_with_weekly(sorted_weeks)


def generate_index_with_weekly(sorted_weeks):
    """Generate index.html that includes both daily entries and weekly links."""
    index_data = load_index_data()
    entries = index_data.get("entries", [])

    title = "AI 新聞檔案"
    subtitle = (
        f"一共 {len(entries)} 天的新聞記錄 · "
        f"{len(sorted_weeks)} 個星期"
    )

    nav_links = ""

    # Weekly summary section
    weekly_links_html = ""
    if sorted_weeks:
        weekly_links_html = '<div class="section"><div class="section-title">📊 週報</div>'
        for iso_year, iso_week in sorted_weeks:
            weekly_links_html += (
                f'<div class="week-entry" style="padding:12px 16px;">'
                f'<div class="week-title" style="font-size:1rem;">'
                f'<a href="weekly-{iso_year}-W{iso_week:02d}.html">'
                f'📊 第{iso_week:02d}週 ({iso_year})</a></div>'
                f'</div>'
            )
        weekly_links_html += '</div>'

    # Daily list section
    daily_html = '<div class="section"><div class="section-title">📅 每日新聞</div>'
    for entry in entries:
        date_str = entry.get("date", "")
        dow = entry.get("dow", "")
        item_count = entry.get("item_count", 0)
        summary = entry.get("summary", "")

        daily_html += (
            '<div class="week-entry" style="padding:12px 16px;">'
            f'<div class="week-title" style="font-size:1rem;">'
            f'<a href="{date_str}.html">📅 {date_str}'
        )
        if dow:
            daily_html += f' 星期{dow}'
        daily_html += '</a>'
        daily_html += (
            f' <span style="color:var(--text2);font-size:0.8rem;">'
            f'({item_count} 條)</span>'
        )
        daily_html += '</div>'
        if summary:
            daily_html += (
                f'<div class="card-why" style="margin-top:4px;'
                f'padding:0 16px 12px;">{summary}</div>'
            )
        daily_html += '</div>'

    daily_html += '</div>'

    body = weekly_links_html + daily_html

    full_html = HTML_HEAD.format(
        title=title,
        subtitle=subtitle,
        nav_links=nav_links,
    ) + body + HTML_FOOTER

    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(full_html)

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
        # Also allow regenerating index alone
        generate_index()
        print(f"📋 Regenerated {INDEX_HTML}")

    else:
        print(f"❌ Unknown mode: {mode}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
