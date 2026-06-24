#!/usr/bin/env python3
"""
AI News Archive — Static HTML Generator (v3 — front-page + verticals)
=====================================================================
Generates the full multi-page site:
  - index.html ............ front page (lead + top stories + this-week + trending + recent)
  - YYYY-MM-DD.html ....... daily page (lede + category sections + cards)
  - weekly-YYYY-WWW.html .. weekly digest (summary + top picks + themes + repos + day list)
  - monthly-YYYY-MM.html .. monthly review (only when a monthly summary exists)
  - category-KEY.html ..... category stream (github/tech/general/research across all days)
  - archive.html .......... full timeline grouped by week

Usage:
  python3 generate-news-html.py daily   /path/to/daily.json
  python3 generate-news-html.py weekly  [/path/to/week-data.json]
  python3 generate-news-html.py monthly [/path/to/month-data.json]
  python3 generate-news-html.py index            # regenerate everything from index_data.json

Daily input JSON:
{
  "date": "2026-06-24",
  "dow": "三",                      # optional, weekday also derived from date
  "summary": "全日總括（編輯導讀）",
  "hero_image": "https://…/og.png", # optional homepage hero image
  "items": [
    { "title": "openai/codex", "link": "https://…", "category": "github",
      "why": "短摘要", "description": "長描述 2-3 句",
      "stars": 44700, "signal": "big",            # optional
      "source_domain": "github.com", "image": "https://…" }  # both optional
  ]
}

Agent-supplied curation (optional — auto-derived when omitted):
  weekly  week-data.json  : { "2026-W25": { "summary": "...", "themes": ["…"],
                              "highlights": [{"title","why","date":"2026-06-16","category"}],
                              "repos": [{"name","stars"}] } }
  monthly month-data.json : { "2026-06": { "summary": "...", "themes": ["…"],
                              "highlights": [{"title","why","category"}] } }
                            # a month page is generated ONLY when its summary exists
  trending (homepage)     : stored under index_data["trending"]:
                            { "topics": [{"label","days"}], "repos": [{"name","stars","url"}] }
                            # auto-derived from stars when absent
"""

import json
import os
import re
import sys
from collections import OrderedDict
from datetime import datetime, date, timedelta
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_DATA = os.path.join(BASE_DIR, "index_data.json")
INDEX_HTML = os.path.join(BASE_DIR, "index.html")

# ---------------------------------------------------------------------------
# Category + signal config
# ---------------------------------------------------------------------------
CAT = {
    "github":   {"label": "GitHub 開源", "short": "GitHub", "var": "var(--c-oss)"},
    "tech":     {"label": "科技新聞",     "short": "科技",   "var": "var(--c-tech)"},
    "general":  {"label": "業界動態",     "short": "業界",   "var": "var(--c-biz)"},
    "research": {"label": "研究論文",     "short": "論文",   "var": "var(--c-paper)"},
}
CAT_ORDER = ["github", "tech", "general", "research"]
NEWS_CATS = ["tech", "general", "research"]

SIGNAL = {
    "new":  ("新項目", "var(--c-paper)"),
    "big":  ("官方",   "var(--c-biz)"),
    "hot":  ("熱門",   "var(--accent)"),
    "pain": ("實用",   "var(--c-paper)"),
    "para": ("觀點",   "var(--c-tech)"),
}
SIGNAL_SCORE = {"hot": 4, "big": 4, "new": 3, "pain": 2, "para": 1, "": 0}
WEEKDAY_FULL = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

# ---------------------------------------------------------------------------
# Icons (no braces -> safe in f-strings)
# ---------------------------------------------------------------------------
I_LOGO = ('<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fff" '
          'stroke-width="2.4" stroke-linecap="round"><path d="M5 19V5l7 7-7 7Z"/>'
          '<path d="M14 12h5"/></svg>')
I_GH = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.48 '
        '2 2 6.58 2 12.25c0 4.53 2.87 8.37 6.84 9.73.5.1.68-.22.68-.49l-.01-1.72c-2.78.62-3.37-1.37'
        '-3.37-1.37-.45-1.18-1.11-1.5-1.11-1.5-.91-.64.07-.62.07-.62 1 .07 1.53 1.06 1.53 1.06.89 '
        '1.57 2.34 1.12 2.91.85.09-.66.35-1.12.63-1.38-2.22-.26-4.56-1.14-4.56-5.07 0-1.12.39-2.03 '
        '1.03-2.75-.1-.26-.45-1.3.1-2.71 0 0 .84-.28 2.75 1.05a9.3 9.3 0 0 1 5 0c1.91-1.33 2.75-1.05 '
        '2.75-1.05.55 1.41.2 2.45.1 2.71.64.72 1.03 1.63 1.03 2.75 0 3.94-2.34 4.81-4.57 5.06.36.32'
        '.68.94.68 1.9l-.01 2.82c0 .27.18.59.69.49A10.26 10.26 0 0 0 22 12.25C22 6.58 17.52 2 12 2Z"/></svg>')
I_MOON = ('<svg class="ic-moon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
          'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 '
          '11.2 3 7 7 0 0 0 21 12.8z"/></svg>')
I_SUN = ('<svg class="ic-sun" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
         'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/>'
         '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4'
         'M17.7 6.3l1.4-1.4"/></svg>')
I_ARR = ('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" '
         'stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>')
I_ARR_S = ('<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" '
           'stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>')
I_EXT = ('<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" '
         'stroke-linecap="round" stroke-linejoin="round" style="opacity:.45;flex-shrink:0"><path d="M7 17 17 7M9 7h8v8"/></svg>')
I_BACK = ('<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" '
          'stroke-linecap="round" stroke-linejoin="round"><path d="M19 12H5M11 18l-6-6 6-6"/></svg>')
I_IMG = ('<svg width="{s}" height="{s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">'
         '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/>'
         '<path d="M21 15l-5-5L5 21"/></svg>')

def img_icon(size=22):
    return I_IMG.replace("{s}", str(size))

# ---------------------------------------------------------------------------
# CSS (literal braces — never .format()ed)
# ---------------------------------------------------------------------------
CSS = r"""
:root{
  --bg:#0b0c0f;--bg-elev:#15161c;--bg-elev2:#1c1e26;--line:#262833;--line-soft:#1d1f27;
  --text:#ECEDF0;--text-dim:#b7bbc7;--text-faint:#878b98;
  --accent:#5B6CFF;--accent-soft:rgba(91,108,255,.16);--accent-line:rgba(91,108,255,.34);
  --c-oss:#E8B23A;--c-tech:#5BA3F7;--c-biz:#B488FF;--c-paper:#52CC81;
  --font-cjk:"Noto Sans HK","PingFang HK","Microsoft JhengHei",-apple-system,sans-serif;
  --font-disp:"Space Grotesk","Noto Sans HK","PingFang HK",sans-serif;
  --font-mono:"JetBrains Mono","SFMono-Regular","Menlo",monospace;
  --glow:radial-gradient(ellipse at center,rgba(91,108,255,.16),transparent 70%);
}
:root[data-theme="light"]{
  --bg:#FAF8F4;--bg-elev:#fff;--bg-elev2:#F3F1EA;--line:#E5E2D9;--line-soft:#EDEAE2;
  --text:#17181C;--text-dim:#54565E;--text-faint:#82848c;
  --accent:#5B6CFF;--accent-soft:rgba(91,108,255,.10);--accent-line:rgba(91,108,255,.26);
  --c-oss:#B07F15;--c-tech:#1F6FD6;--c-biz:#7C4CD4;--c-paper:#1E9B52;
  --glow:radial-gradient(ellipse at center,rgba(91,108,255,.10),transparent 70%);
}
@media (prefers-color-scheme:light){
  :root:not([data-theme="dark"]){
    --bg:#FAF8F4;--bg-elev:#fff;--bg-elev2:#F3F1EA;--line:#E5E2D9;--line-soft:#EDEAE2;
    --text:#17181C;--text-dim:#54565E;--text-faint:#82848c;
    --accent-soft:rgba(91,108,255,.10);--accent-line:rgba(91,108,255,.26);
    --c-oss:#B07F15;--c-tech:#1F6FD6;--c-biz:#7C4CD4;--c-paper:#1E9B52;
    --glow:radial-gradient(ellipse at center,rgba(91,108,255,.10),transparent 70%);
  }
}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--font-cjk);min-height:100vh;
  position:relative;overflow-x:hidden;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}
a{color:inherit;text-decoration:none}
::selection{background:var(--accent);color:#fff}
::-webkit-scrollbar{width:11px;height:11px}
::-webkit-scrollbar-thumb{background:var(--line);border-radius:6px;border:3px solid var(--bg)}
::-webkit-scrollbar-track{background:var(--bg)}
@keyframes rise{from{transform:translateY(14px);opacity:.5}to{transform:translateY(0);opacity:1}}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.8)}}
.glow{position:fixed;top:-260px;left:50%;transform:translateX(-50%);width:1000px;height:560px;
  background:var(--glow);pointer-events:none;z-index:0}
/* theme icon toggle */
.ic-sun{display:none}
:root[data-theme="light"] .ic-moon{display:none}
:root[data-theme="light"] .ic-sun{display:inline-flex}
/* hover utilities (inline styles cover the rest) */
a,button{transition:color .15s,opacity .15s,border-color .15s,transform .15s,background .15s}
.navlink:hover,.flink:hover,.swbtn:hover,.acc:hover{color:var(--accent)!important}
.ghlink:hover{color:var(--text)!important}
.tbtn:hover{color:var(--accent)!important;border-color:var(--accent-line)!important}
.hov:hover{opacity:.7}
.hov9:hover{opacity:.9;transform:translateY(-1px)}
.ncard:hover{border-color:var(--c,var(--accent-line))!important}
.tcol:hover{color:var(--c)!important}
.lift:hover{border-color:var(--accent-line)!important;transform:translateY(-2px)}
.lift2:hover{transform:translateY(-2px)}
.pillh:hover{border-color:var(--c)!important;color:var(--text)!important}
.dayrow:hover{border-color:var(--accent-line)!important;transform:translateX(2px)}
.toplink:hover{color:var(--text)!important}
@media (max-width:768px){
  [data-r="nav"]{gap:12px!important;padding-left:16px!important;padding-right:16px!important}
  [data-r="navlinks"]{flex-basis:100%!important;order:3;justify-content:center;gap:0!important;
    border-top:1px solid var(--line);margin-left:0!important;padding-top:6px}
  [data-r="hero"]{grid-template-columns:1fr!important;gap:24px!important}
  [data-r="cols2"]{grid-template-columns:1fr!important}
  [data-r="cols4"]{grid-template-columns:1fr 1fr!important}
  [data-r="big"]{font-size:34px!important}
  [data-r="cardrow"]{flex-direction:column!important}
  [data-r="thumb"]{width:100%!important;height:160px!important}
  main{padding-left:18px!important;padding-right:18px!important}
}
"""

THEME_INIT = ("<script>(function(){try{var t=localStorage.getItem('ainews_theme');"
              "if(t!=='light'&&t!=='dark'){t=(window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches)?'light':'dark';}"
              "document.documentElement.setAttribute('data-theme',t);}catch(e){}})();</script>")
THEME_TOGGLE = ("<script>(function(){var b=document.getElementById('themeToggle');if(!b)return;"
                "b.addEventListener('click',function(){var c=document.documentElement.getAttribute('data-theme')==='light'?'dark':'light';"
                "document.documentElement.setAttribute('data-theme',c);try{localStorage.setItem('ainews_theme',c);}catch(e){}});})();</script>")
FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
         '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&'
         'family=JetBrains+Mono:wght@400;500;700&family=Noto+Sans+HK:wght@300;400;500;700;900&display=swap" rel="stylesheet">')

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def extract_domain(url):
    if not url:
        return ""
    try:
        p = urlparse(url)
        d = p.netloc or p.path.split("/")[0]
        return re.sub(r"^www\.", "", d)
    except Exception:
        return ""

def fmt_stars(v):
    if v in (None, "", 0):
        return ""
    if isinstance(v, str):
        return v
    n = int(v)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)

def star_int(v):
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        m = re.match(r"([\d.]+)\s*([kKmM]?)", v.strip())
        if not m:
            return 0
        num = float(m.group(1)); suf = m.group(2).lower()
        return int(num * (1_000_000 if suf == "m" else 1_000 if suf == "k" else 1))
    return 0

def wd_full(date_str):
    return WEEKDAY_FULL[datetime.strptime(date_str, "%Y-%m-%d").isoweekday() - 1]

def dshort(date_str):
    return date_str[5:].replace("-", ".")

def md(date_str):
    return date_str[5:].replace("-", ".")

def week_key(iy, iw):
    return f"{iy}-W{iw:02d}"

def weekly_file(iy, iw):
    return f"weekly-{iy}-W{iw:02d}.html"

def monthly_file(mk):
    return f"monthly-{mk}.html"

def cat_var(cat):
    return CAT.get(cat, CAT["tech"])["var"]

def cat_label(cat):
    return CAT.get(cat, CAT["tech"])["label"]

def cat_short(cat):
    return CAT.get(cat, CAT["tech"])["short"]

def load_index():
    if os.path.exists(INDEX_DATA):
        with open(INDEX_DATA, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"entries": []}

def save_index(d):
    with open(INDEX_DATA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------------------------
# Shell (nav / footer / page)
# ---------------------------------------------------------------------------
def render_nav(active, ctx):
    latest_daily = ctx["latest_daily"]
    weekly_href = ctx["latest_weekly_file"] or "index.html"
    daily_href = f"{latest_daily}.html" if latest_daily else "index.html"
    def link(href, label, key):
        und = ('<span style="position:absolute;left:11px;right:11px;bottom:2px;height:2px;'
               'background:var(--accent);border-radius:2px;"></span>') if active == key else ""
        return (f'<a class="navlink" href="{href}" style="position:relative;font-family:var(--font-cjk);'
                f'font-size:14px;font-weight:500;color:var(--text);padding:8px 11px;">{label}{und}</a>')
    return (
        '<header style="position:sticky;top:0;z-index:50;backdrop-filter:blur(14px);'
        'background:color-mix(in srgb,var(--bg) 78%,transparent);border-bottom:1px solid var(--line);">'
        '<div data-r="nav" style="max-width:1120px;margin:0 auto;padding:14px 28px;display:flex;'
        'align-items:center;gap:22px;flex-wrap:wrap;">'
        '<a href="index.html" style="display:flex;align-items:center;gap:12px;flex-shrink:0;">'
        '<span style="width:34px;height:34px;border-radius:9px;background:var(--accent);display:flex;'
        f'align-items:center;justify-content:center;box-shadow:0 4px 14px var(--accent-soft);">{I_LOGO}</span>'
        '<span style="line-height:1.05;display:block;"><span style="display:block;font-family:var(--font-disp);'
        'font-weight:700;font-size:17px;letter-spacing:-0.01em;"><span style="color:var(--accent);'
        'font-family:var(--font-mono);font-weight:700;margin-right:3px;">AI</span>新聞檔案</span>'
        '<span style="display:block;font-family:var(--font-mono);font-size:9.5px;letter-spacing:0.22em;'
        'color:var(--text-faint);margin-top:2px;">DAILY&nbsp;AI&nbsp;INTELLIGENCE</span></span></a>'
        '<nav data-r="navlinks" style="display:flex;align-items:center;gap:2px;margin-left:6px;">'
        + link("index.html", "主頁", "home")
        + link(daily_href, "最新", "daily")
        + link(weekly_href, "週報", "weekly")
        + link("category-github.html", "分類", "category")
        + '</nav>'
        '<div style="margin-left:auto;display:flex;align-items:center;gap:16px;">'
        '<a class="ghlink" href="https://github.com/fafafung/ai-news" target="_blank" rel="noopener" '
        f'title="GitHub" style="display:flex;color:var(--text-dim);">{I_GH}</a>'
        '<button class="tbtn" id="themeToggle" title="切換主題" type="button" style="display:flex;'
        'align-items:center;justify-content:center;width:34px;height:34px;border-radius:9px;'
        'border:1px solid var(--line);background:var(--bg-elev);color:var(--text-dim);cursor:pointer;">'
        f'{I_MOON}{I_SUN}</button></div></div></header>'
    )

def render_footer(ctx):
    mk = ctx["latest_month_file"]
    def fl(href, label):
        return (f'<a class="flink" href="{href}" style="font-family:var(--font-mono);font-size:12px;'
                f'color:var(--text-dim);padding:4px 0;">{label}</a>')
    monthly_link = fl(mk, "月報") if (ctx["has_monthly"] and mk) else ""
    daily_href = f'{ctx["latest_daily"]}.html' if ctx["latest_daily"] else "index.html"
    weekly_href = ctx["latest_weekly_file"] or "index.html"
    return (
        '<footer style="position:relative;z-index:1;border-top:1px solid var(--line);margin-top:40px;">'
        '<div style="max-width:1120px;margin:0 auto;padding:22px 28px 6px;display:flex;gap:4px 18px;flex-wrap:wrap;">'
        + fl("index.html", "主頁") + fl(daily_href, "最新一日") + fl(weekly_href, "週報")
        + monthly_link + fl("archive.html", "檔案") + fl("category-github.html", "分類")
        + '</div>'
        '<div style="max-width:1120px;margin:0 auto;padding:14px 28px 26px;display:flex;align-items:center;'
        'justify-content:space-between;flex-wrap:wrap;gap:14px;font-family:var(--font-mono);font-size:12px;color:var(--text-faint);">'
        '<span>AI 新聞檔案 · 每日由 AI 自動生成</span>'
        '<span style="display:flex;align-items:center;gap:18px;"><span>curated by Fafa</span>'
        '<a class="flink" href="https://github.com/fafafung/ai-news" target="_blank" rel="noopener" '
        'style="color:var(--text-dim);">GitHub ↗</a></span></div></footer>'
    )

def page_shell(title, active, body, ctx):
    head = ('<!DOCTYPE html>\n<html lang="zh-HK">\n<head>\n<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f'<title>{title}</title>\n{FONTS}\n<style>' + CSS + '</style>\n' + THEME_INIT + '\n</head>\n<body>\n')
    return (head + '<div class="glow"></div>\n' + render_nav(active, ctx) + '\n'
            + '<main style="position:relative;z-index:1;max-width:1120px;margin:0 auto;padding:0 28px 90px;">\n'
            + body + '\n</main>\n' + render_footer(ctx) + '\n' + THEME_TOGGLE + '\n</body>\n</html>\n')

# ---------------------------------------------------------------------------
# Component renderers
# ---------------------------------------------------------------------------
def placeholder(color, size, icon_px):
    return (f'<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;'
            f'color:var(--text-faint);opacity:.5;">{img_icon(icon_px)}</div>')

def media_box(image, color, style, icon_px):
    img = (f'<img src="{image}" alt="" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;">'
           if image else "")
    return (f'<div style="{style}background:linear-gradient(135deg,var(--bg-elev2),'
            f'color-mix(in srgb,{color} 26%,var(--bg-elev2)));">{img}{placeholder(color,0,icon_px)}</div>')

def render_daily_card(it):
    cat = it.get("category", "general")
    color = cat_var(cat)
    title = it.get("title", "")
    desc = it.get("description", "") or it.get("why", "")
    why = it.get("why", "")
    link = it.get("link", "#")
    stars = it.get("stars", 0)
    signal = it.get("signal", "")
    image = it.get("image", "")
    src = it.get("source_domain", "") or extract_domain(link)
    is_mono = cat == "github"
    title_font = "var(--font-mono)" if is_mono else "var(--font-cjk)"

    badges = ""
    sf = fmt_stars(stars)
    if sf:
        badges += ('<span style="display:inline-flex;align-items:center;gap:4px;font-family:var(--font-mono);'
                   'font-size:11px;font-weight:600;color:var(--c-oss);background:color-mix(in srgb,var(--c-oss) 14%,transparent);'
                   'border:1px solid color-mix(in srgb,var(--c-oss) 26%,transparent);padding:2px 9px;border-radius:20px;">'
                   f'★ {sf}</span>')
    if signal in SIGNAL:
        slbl, scol = SIGNAL[signal]
        badges += (f'<span style="font-family:var(--font-mono);font-size:10px;font-weight:600;letter-spacing:0.04em;'
                   f'padding:3px 9px;border-radius:20px;color:{scol};background:color-mix(in srgb,{scol} 15%,transparent);">{slbl}</span>')
    badges_html = f'<div style="display:flex;gap:6px;flex-shrink:0;align-items:center;">{badges}</div>' if badges else ""

    meta = f'<span style="font-family:var(--font-mono);font-size:11px;color:var(--text-faint);background:var(--bg-elev2);padding:2px 9px;border-radius:6px;">{src}</span>'
    if why and it.get("description"):
        meta += f'<span style="font-size:12.5px;color:var(--text-dim);font-style:italic;">{why}</span>'

    thumb = ""
    if image or cat != "github":
        thumb = ('<div data-r="thumb" style="flex-shrink:0;width:120px;height:90px;border-radius:10px;overflow:hidden;position:relative;'
                 f'">{media_box(image, color, "position:absolute;inset:0;", 22)}</div>')
        # simpler: wrap media_box directly
        thumb = (f'<div data-r="thumb" style="flex-shrink:0;width:120px;height:90px;border-radius:10px;overflow:hidden;position:relative;'
                 f'background:linear-gradient(135deg,var(--bg-elev2),color-mix(in srgb,{color} 24%,var(--bg-elev2)));">'
                 + (f'<img src="{image}" alt="" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;">' if image else "")
                 + f'<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--text-faint);opacity:.55;">{img_icon(22)}</div></div>')

    return (
        f'<article class="ncard" style="--c:{color};position:relative;background:var(--bg-elev);border:1px solid var(--line);'
        'border-radius:14px;padding:18px 20px 16px 22px;overflow:hidden;">'
        f'<span style="position:absolute;left:0;top:0;bottom:0;width:3px;background:{color};"></span>'
        '<div data-r="cardrow" style="display:flex;gap:16px;align-items:flex-start;">'
        '<div style="flex:1;min-width:0;">'
        '<div style="display:flex;align-items:flex-start;gap:12px;">'
        f'<a class="tcol" href="{link}" target="_blank" rel="noopener" style="--c:{color};flex:1;min-width:0;display:inline-flex;'
        f'align-items:center;gap:7px;font-family:{title_font};font-weight:700;font-size:16px;line-height:1.4;color:var(--text);">{title}{I_EXT}</a>'
        f'{badges_html}</div>'
        f'<p style="margin-top:9px;font-size:14px;line-height:1.78;color:var(--text);opacity:.88;">{desc}</p>'
        f'<div style="margin-top:11px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;">{meta}</div>'
        f'</div>{thumb}</div></article>'
    )

def render_hl_dated(h):
    """Dated highlight card (home this-week / weekly picks)."""
    cat = h.get("category", h.get("cat", "tech"))
    color = cat_var(cat)
    d = h.get("date", "")
    dt = md(d) if (d and "-" in d) else d
    href = f"{d}.html" if (d and "-" in d) else "#"
    return (
        f'<a class="ncard" href="{href}" style="--c:{color};display:flex;gap:16px;padding:16px 18px;background:var(--bg-elev);'
        'border:1px solid var(--line);border-radius:12px;cursor:pointer;">'
        f'<span style="flex-shrink:0;font-family:var(--font-mono);font-size:11px;color:var(--accent);padding-top:2px;">{dt}</span>'
        '<div style="flex:1;min-width:0;">'
        f'<div style="display:flex;align-items:center;gap:7px;margin-bottom:5px;"><span style="width:7px;height:7px;border-radius:2px;background:{color};"></span>'
        f'<span style="font-family:var(--font-mono);font-size:10px;color:var(--text-faint);">{cat_label(cat)}</span></div>'
        f'<div style="font-size:15px;font-weight:600;line-height:1.45;color:var(--text);">{h.get("title","")}</div>'
        f'<div style="margin-top:5px;font-size:12.5px;color:var(--text-dim);font-style:italic;line-height:1.55;">{h.get("why","")}</div>'
        '</div></a>'
    )

def render_hl_plain(h):
    """Plain highlight card (monthly picks, no date)."""
    cat = h.get("category", h.get("cat", "tech"))
    color = cat_var(cat)
    return (
        '<div style="padding:16px 18px;background:var(--bg-elev);border:1px solid var(--line);border-radius:12px;">'
        f'<div style="display:flex;align-items:center;gap:7px;margin-bottom:6px;"><span style="width:7px;height:7px;border-radius:2px;background:{color};"></span>'
        f'<span style="font-family:var(--font-mono);font-size:10px;color:var(--text-faint);">{cat_label(cat)}</span></div>'
        f'<div style="font-size:15px;font-weight:600;line-height:1.45;">{h.get("title","")}</div>'
        f'<div style="margin-top:5px;font-size:12.5px;color:var(--text-dim);font-style:italic;line-height:1.55;">{h.get("why","")}</div></div>'
    )

def theme_chips(themes):
    return "".join(
        f'<span style="font-family:var(--font-cjk);font-size:12.5px;color:var(--text-dim);background:var(--bg-elev);'
        f'border:1px solid var(--line);padding:5px 12px;border-radius:30px;"># {t}</span>' for t in themes)

def section_title(zh, en, right=""):
    r = f'<span style="margin-left:auto;font-family:var(--font-mono);font-size:12px;color:var(--text-dim);">{right}</span>' if right else ""
    return ('<div style="display:flex;align-items:baseline;gap:14px;margin-bottom:20px;">'
            f'<h2 style="font-family:var(--font-disp);font-weight:700;font-size:24px;letter-spacing:-0.02em;">{zh}</h2>'
            f'<span style="font-family:var(--font-mono);font-size:11px;letter-spacing:0.2em;color:var(--text-faint);">{en}</span>{r}</div>')

def sub_title(zh, en, dim=False):
    col = 'color:var(--text-dim);' if dim else ''
    return ('<div style="display:flex;align-items:baseline;gap:12px;margin-bottom:14px;">'
            f'<h2 style="font-family:var(--font-cjk);font-weight:700;font-size:16px;{col}">{zh}</h2>'
            f'<span style="font-family:var(--font-mono);font-size:11px;letter-spacing:0.18em;color:var(--text-faint);">{en}</span></div>')

def back_btn():
    return ('<a class="acc" href="index.html" style="margin-top:32px;display:inline-flex;align-items:center;gap:7px;'
            'font-family:var(--font-mono);font-size:12px;color:var(--text-dim);letter-spacing:0.04em;">'
            f'{I_BACK}返回主頁</a>')

# ---------------------------------------------------------------------------
# Derivation (auto fallback for curation)
# ---------------------------------------------------------------------------
def collect_week_items(entries, iy, iw):
    out = []
    for e in entries:
        if e.get("iso_year") == iy and e.get("iso_week") == iw:
            for it in e.get("items", []):
                out.append({**it, "date": e.get("date", "")})
    return out

def derive_highlights(items, n=4):
    def score(it):
        return SIGNAL_SCORE.get(it.get("signal", ""), 0) * 1_000_000 + star_int(it.get("stars", 0))
    ordered = sorted(items, key=score, reverse=True)
    out = []
    for it in ordered[:n]:
        out.append({"title": it.get("title", ""), "why": it.get("why", ""),
                    "date": it.get("date", ""), "category": it.get("category", "general")})
    return out

def derive_repos(items, n=4):
    seen = {}
    for it in items:
        if it.get("category") == "github" or star_int(it.get("stars", 0)) > 0:
            nm = it.get("title", "")
            si = star_int(it.get("stars", 0))
            if nm and (nm not in seen or si > seen[nm]):
                seen[nm] = si
    ranked = sorted(seen.items(), key=lambda kv: kv[1], reverse=True)[:n]
    return [{"name": nm, "stars": fmt_stars(si)} for nm, si in ranked if si > 0]

def get_week_data(data, entries, iy, iw):
    wk = week_key(iy, iw)
    agent = (data.get("week_data") or {}).get(wk, {})
    items = collect_week_items(entries, iy, iw)
    return {
        "summary": agent.get("summary", "（本週總結將由新聞 agent 自動生成）"),
        "themes": agent.get("themes", []),
        "highlights": agent.get("highlights") or derive_highlights(items),
        "repos": [{"name": r["name"], "stars": fmt_stars(r.get("stars"))} for r in agent["repos"]] if agent.get("repos") else derive_repos(items),
    }

def get_trending(data, entries):
    agent = data.get("trending") or {}
    all_items = []
    for e in entries[:14]:
        for it in e.get("items", []):
            all_items.append(it)
    repos = agent.get("repos")
    if repos:
        repos = [{"name": r["name"], "stars": fmt_stars(r.get("stars")), "url": r.get("url", "#")} for r in repos]
    else:
        seen = {}
        for it in all_items:
            if it.get("category") == "github" or star_int(it.get("stars", 0)) > 0:
                nm = it.get("title", ""); si = star_int(it.get("stars", 0))
                if nm and (nm not in seen or si > seen[nm]["si"]):
                    seen[nm] = {"si": si, "url": it.get("link", "#")}
        ranked = sorted(seen.items(), key=lambda kv: kv[1]["si"], reverse=True)[:5]
        repos = [{"name": nm, "stars": fmt_stars(v["si"]), "url": v["url"]} for nm, v in ranked if v["si"] > 0]
    return {"topics": agent.get("topics", []), "repos": repos}

# ---------------------------------------------------------------------------
# Context (shared links)
# ---------------------------------------------------------------------------
def build_ctx(data):
    entries = data.get("entries", [])
    latest_daily = entries[0]["date"] if entries else ""
    # newest week
    best_w = None
    for e in entries:
        iy, iw = e.get("iso_year"), e.get("iso_week")
        if iy and iw and (best_w is None or (iy, iw) > best_w):
            best_w = (iy, iw)
    latest_weekly = weekly_file(*best_w) if best_w else ""
    # months with summaries
    month_data = data.get("month_data") or {}
    month_keys = sorted([mk for mk, v in month_data.items() if v.get("summary")], reverse=True)
    has_monthly = bool(month_keys)
    latest_month_file = monthly_file(month_keys[0]) if month_keys else ""
    return {"latest_daily": latest_daily, "latest_weekly_file": latest_weekly,
            "has_monthly": has_monthly, "latest_month_file": latest_month_file,
            "month_keys": month_keys}

# ---------------------------------------------------------------------------
# Page bodies
# ---------------------------------------------------------------------------
def build_daily_body(date_str, dow, items, summary):
    grouped = OrderedDict((c, []) for c in CAT_ORDER)
    for it in items:
        grouped.setdefault(it.get("category", "general"), []).append(it)
    total = len(items)
    ncats = sum(1 for v in grouped.values() if v)

    pills = ""
    for c in CAT_ORDER:
        n = len(grouped.get(c, []))
        if not n:
            continue
        col = cat_var(c)
        pills += (f'<a class="pillh" href="category-{c}.html" style="--c:{col};display:inline-flex;align-items:center;gap:8px;'
                  'background:var(--bg-elev);border:1px solid var(--line);border-radius:30px;padding:7px 14px;cursor:pointer;'
                  'font-family:var(--font-cjk);font-size:13px;color:var(--text-dim);">'
                  f'<span style="width:8px;height:8px;border-radius:2px;background:{col};"></span>{cat_label(c)}'
                  f'<span style="font-family:var(--font-mono);font-size:11px;color:var(--text-faint);">{n}</span></a>')

    sections = ""
    order = CAT_ORDER + [c for c in grouped if c not in CAT_ORDER]
    for c in order:
        arr = grouped.get(c, [])
        if not arr:
            continue
        col = cat_var(c)
        cards = "".join(render_daily_card(it) for it in arr)
        sections += (
            f'<section id="cat-{c}" style="margin-top:40px;scroll-margin-top:90px;">'
            '<div style="display:flex;align-items:center;gap:11px;margin-bottom:18px;padding-bottom:11px;border-bottom:1px solid var(--line);">'
            f'<span style="width:10px;height:10px;border-radius:3px;background:{col};"></span>'
            f'<h2 style="font-family:var(--font-cjk);font-weight:700;font-size:17px;color:{col};">{cat_label(c)}</h2>'
            f'<span style="margin-left:auto;font-family:var(--font-mono);font-size:12px;color:var(--text-faint);">{len(arr)} 條</span>'
            f'<a class="acc" href="category-{c}.html" style="font-family:var(--font-mono);font-size:11.5px;color:var(--accent);">全部 →</a></div>'
            f'<div style="display:flex;flex-direction:column;gap:12px;">{cards}</div></section>')

    lede = ""
    if summary:
        lede = ('<div style="margin:28px 0 6px;padding:22px 24px;background:var(--bg-elev);border:1px solid var(--line);'
                'border-left:3px solid var(--accent);border-radius:0 12px 12px 0;">'
                '<div style="font-family:var(--font-mono);font-size:10.5px;letter-spacing:0.2em;color:var(--accent);margin-bottom:9px;">編輯導讀</div>'
                f'<p style="font-size:15.5px;line-height:1.85;color:var(--text);">{summary}</p></div>')

    return (
        '<div style="animation:rise .5s ease;max-width:780px;margin:0 auto;">'
        + back_btn() +
        '<header style="padding:24px 0 28px;border-bottom:1px solid var(--line);">'
        f'<div style="font-family:var(--font-mono);font-size:11px;letter-spacing:0.24em;color:var(--accent);margin-bottom:16px;">每日簡報 · {wd_full(date_str)}</div>'
        f'<h1 data-r="big" style="font-family:var(--font-disp);font-weight:700;font-size:52px;line-height:1;letter-spacing:-0.03em;">{date_str}</h1>'
        '<div style="margin-top:14px;display:flex;align-items:center;gap:14px;font-family:var(--font-mono);font-size:13px;color:var(--text-dim);">'
        f'<span><span style="color:var(--accent);font-weight:600;">{total}</span> 條新聞</span>'
        f'<span style="color:var(--line);">/</span><span>{ncats} 個分類</span></div></header>'
        + lede +
        f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin:26px 0 8px;">{pills}</div>'
        + sections +
        '<div style="margin-top:48px;text-align:center;font-family:var(--font-mono);font-size:12px;color:var(--text-faint);letter-spacing:0.2em;">— 完 —</div>'
        '</div>'
    )

def build_index_body(data, ctx):
    entries = data.get("entries", [])
    if not entries:
        return '<p style="padding:60px 0;color:var(--text-dim);">暫無記錄</p>'
    f0 = entries[0]
    date_str = f0["date"]
    items = f0.get("items", [])
    summary = f0.get("summary", "")
    hero_image = f0.get("hero_image", "")
    total = f0.get("item_count", len(items))

    news = [it for it in items if it.get("category") in NEWS_CATS]
    repos = [it for it in items if it.get("category") == "github"]
    ordered = news + repos if news else items
    lead = ordered[0] if ordered else {}
    secondary = ordered[1:4]
    rest = ordered[4:10]

    lead_col = cat_var(lead.get("category", "tech"))
    lead_img = lead.get("image", "") or hero_image
    lead_block = (
        f'<a class="hov9" href="{date_str}.html" style="display:block;cursor:pointer;">'
        '<div style="position:relative;aspect-ratio:16/9;border-radius:14px;overflow:hidden;'
        f'background:linear-gradient(135deg,var(--bg-elev2),color-mix(in srgb,{lead_col} 30%,var(--bg-elev2)));">'
        + (f'<img src="{lead_img}" alt="" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;">' if lead_img else "")
        + f'<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--text-faint);opacity:.45;">{img_icon(34)}</div>'
        f'<span style="position:absolute;top:14px;left:14px;font-family:var(--font-mono);font-size:10.5px;font-weight:600;'
        f'letter-spacing:0.04em;padding:4px 10px;border-radius:20px;color:#fff;background:color-mix(in srgb,{lead_col} 80%,#000);">{cat_label(lead.get("category","tech"))}</span></div>'
        f'<h2 style="margin-top:16px;font-family:var(--font-disp);font-weight:700;font-size:27px;line-height:1.22;letter-spacing:-0.01em;color:var(--text);">{lead.get("title","")}</h2>'
        f'<p style="margin-top:10px;font-size:15px;line-height:1.8;color:var(--text-dim);">{lead.get("description","") or lead.get("why","")}</p>'
        '<div style="margin-top:12px;display:flex;align-items:center;gap:10px;">'
        f'<span style="font-family:var(--font-mono);font-size:11px;color:var(--text-faint);background:var(--bg-elev2);padding:2px 9px;border-radius:6px;">{lead.get("source_domain","") or extract_domain(lead.get("link",""))}</span>'
        '<span style="font-family:var(--font-mono);font-size:12px;color:var(--accent);">閱讀 →</span></div></a>')

    sec_rows = ""
    for s in secondary:
        col = cat_var(s.get("category", "tech"))
        sec_rows += (
            f'<a class="hov" href="{date_str}.html" style="display:flex;gap:14px;padding:15px 0;border-top:1px solid var(--line-soft);cursor:pointer;">'
            f'<div style="flex-shrink:0;width:74px;height:56px;border-radius:8px;overflow:hidden;position:relative;'
            f'background:linear-gradient(135deg,var(--bg-elev2),color-mix(in srgb,{col} 24%,var(--bg-elev2)));">'
            + (f'<img src="{s.get("image")}" alt="" style="position:absolute;inset:0;width:100%;height:100%;object-fit:cover;">' if s.get("image") else "")
            + f'<div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--text-faint);opacity:.5;">{img_icon(16)}</div></div>'
            '<div style="flex:1;min-width:0;">'
            f'<div style="display:flex;align-items:center;gap:7px;margin-bottom:4px;"><span style="width:6px;height:6px;border-radius:2px;background:{col};"></span>'
            f'<span style="font-family:var(--font-mono);font-size:10px;color:var(--text-faint);letter-spacing:0.04em;">{cat_label(s.get("category","tech"))}</span></div>'
            f'<div style="font-size:14.5px;font-weight:600;line-height:1.45;color:var(--text);">{s.get("title","")}</div></div></a>')

    rest_rows = ""
    for r in rest:
        col = cat_var(r.get("category", "tech"))
        fnt = "var(--font-mono)" if r.get("category") == "github" else "var(--font-cjk)"
        rest_rows += (
            f'<a class="hov" href="{date_str}.html" style="display:flex;align-items:center;gap:11px;padding:11px 0;border-bottom:1px solid var(--line-soft);cursor:pointer;">'
            f'<span style="width:7px;height:7px;border-radius:2px;flex-shrink:0;background:{col};"></span>'
            f'<span style="flex:1;min-width:0;font-family:{fnt};font-size:14px;font-weight:500;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{r.get("title","")}</span>'
            f'<span style="font-family:var(--font-mono);font-size:10px;color:var(--text-faint);">{cat_short(r.get("category","tech"))}</span></a>')

    # this week
    bw = (f0.get("iso_year"), f0.get("iso_week"))
    wkd = get_week_data(data, entries, bw[0], bw[1])
    hi_cards = "".join(render_hl_dated(h) for h in wkd["highlights"])
    chips = theme_chips(wkd["themes"])

    # trending
    tr = get_trending(data, entries)
    topics_rows = "".join(
        '<div style="display:flex;align-items:center;gap:12px;padding:11px 0;border-top:1px solid var(--line-soft);">'
        f'<span style="flex:1;min-width:0;font-size:14px;color:var(--text);font-weight:500;">{t.get("label","")}</span>'
        f'<span style="font-family:var(--font-mono);font-size:11px;color:var(--accent);flex-shrink:0;">連續 {t.get("days","")} 日</span></div>'
        for t in tr["topics"])
    repo_rows = ""
    for i, r in enumerate(tr["repos"]):
        repo_rows += (
            f'<a class="hov" href="{r.get("url","#")}" target="_blank" rel="noopener" style="display:flex;align-items:center;gap:12px;padding:11px 0;border-top:1px solid var(--line-soft);">'
            f'<span style="font-family:var(--font-mono);font-size:12px;color:var(--text-faint);width:16px;flex-shrink:0;">{str(i+1).zfill(2)}</span>'
            f'<span style="flex:1;min-width:0;font-family:var(--font-mono);font-size:13px;color:var(--text);font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{r.get("name","")}</span>'
            f'<span style="font-family:var(--font-mono);font-size:11px;font-weight:600;color:var(--c-oss);flex-shrink:0;">★ {r.get("stars","")}</span></a>')
    topics_col = ('<div style="background:var(--bg-elev);border:1px solid var(--line);border-radius:14px;padding:20px 22px;">'
                  '<div style="font-family:var(--font-mono);font-size:10.5px;letter-spacing:0.18em;color:var(--text-faint);margin-bottom:6px;">熱話 · TOPICS</div>'
                  f'{topics_rows}</div>') if tr["topics"] else ""
    repos_col = ('<div style="background:var(--bg-elev);border:1px solid var(--line);border-radius:14px;padding:20px 22px;">'
                 '<div style="font-family:var(--font-mono);font-size:10.5px;letter-spacing:0.18em;color:var(--text-faint);margin-bottom:6px;">熱門 Repo · STARS</div>'
                 f'{repo_rows}</div>')
    trending_grid_cols = "1fr 1fr" if tr["topics"] else "1fr"

    # this-week section
    week_block = (
        '<section style="padding:44px 0 0;">'
        '<div style="display:flex;align-items:baseline;gap:14px;margin-bottom:20px;">'
        '<h2 style="font-family:var(--font-disp);font-weight:700;font-size:24px;letter-spacing:-0.02em;">本週焦點</h2>'
        '<span style="font-family:var(--font-mono);font-size:11px;letter-spacing:0.2em;color:var(--text-faint);">THIS WEEK</span>'
        f'<a class="acc" href="{ctx["latest_weekly_file"] or "index.html"}" style="margin-left:auto;font-family:var(--font-mono);font-size:12px;color:var(--accent);">完整週報 →</a></div>'
        f'<div style="display:flex;gap:7px;flex-wrap:wrap;margin-bottom:16px;">{chips}</div>'
        f'<div data-r="cols2" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">{hi_cards}</div></section>')

    # monthly band
    band = ""
    if ctx["has_monthly"]:
        mk = ctx["month_keys"][0]
        m = (data.get("month_data") or {})[mk]
        lbl = m.get("label") or (mk[:4] + "年" + str(int(mk[5:7])) + "月")
        en = m.get("en") or datetime.strptime(mk + "-01", "%Y-%m-%d").strftime("%B %Y").upper()
        band = (
            f'<a class="lift2" href="{monthly_file(mk)}" style="margin-top:44px;display:flex;align-items:center;justify-content:space-between;'
            'gap:24px;flex-wrap:wrap;padding:24px 28px;border-radius:16px;cursor:pointer;'
            'background:linear-gradient(135deg,var(--bg-elev),color-mix(in srgb,var(--accent) 12%,var(--bg-elev)));border:1px solid var(--accent-line);">'
            '<div style="flex:1;min-width:240px;">'
            f'<div style="font-family:var(--font-mono);font-size:10.5px;letter-spacing:0.2em;color:var(--accent);margin-bottom:8px;">月報 · {en}</div>'
            f'<div style="font-family:var(--font-disp);font-weight:700;font-size:26px;letter-spacing:-0.02em;color:var(--text);">{lbl} 回顧</div>'
            f'<p style="margin-top:8px;font-size:13.5px;line-height:1.7;color:var(--text-dim);max-width:640px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">{m.get("summary","")}</p></div>'
            f'<span style="flex-shrink:0;display:inline-flex;align-items:center;gap:8px;font-family:var(--font-cjk);font-weight:600;font-size:14px;color:var(--accent);">本月回顧{I_ARR}</span></a>')

    # recent strip
    recent = ""
    for e in entries[:7]:
        d = e["date"]
        recent += (
            f'<a class="lift" href="{d}.html" style="flex-shrink:0;width:210px;background:var(--bg-elev);border:1px solid var(--line);border-radius:12px;padding:16px 18px;cursor:pointer;">'
            '<div style="display:flex;align-items:baseline;justify-content:space-between;margin-bottom:8px;">'
            f'<span style="font-family:var(--font-mono);font-size:15px;font-weight:600;color:var(--text);">{dshort(d)}</span>'
            f'<span style="font-family:var(--font-mono);font-size:10.5px;color:var(--accent);">{e.get("item_count",0)} 條</span></div>'
            f'<div style="font-size:11px;color:var(--text-faint);margin-bottom:8px;">{wd_full(d)}</div>'
            f'<p style="font-size:12.5px;line-height:1.6;color:var(--text-dim);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;">{e.get("summary","") or e.get("first_item_snippet","")}</p></a>')

    return (
        '<div style="animation:rise .5s ease;">'
        # masthead row
        '<div style="padding:40px 0 22px;display:flex;align-items:flex-end;justify-content:space-between;gap:20px;flex-wrap:wrap;border-bottom:1px solid var(--line);">'
        '<div><div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">'
        '<span style="font-family:var(--font-mono);font-size:11px;letter-spacing:0.26em;color:var(--accent);font-weight:600;">今日精選</span>'
        '<span style="height:1px;width:30px;background:var(--accent-line);"></span>'
        '<span style="font-family:var(--font-mono);font-size:11px;letter-spacing:0.18em;color:var(--text-faint);">TODAY\'S BRIEFING</span></div>'
        f'<h1 data-r="big" style="font-family:var(--font-disp);font-weight:700;font-size:46px;line-height:1;letter-spacing:-0.03em;">{date_str}'
        f'<span style="font-family:var(--font-cjk);font-weight:500;font-size:22px;color:var(--text-dim);margin-left:14px;">{wd_full(date_str)}</span></h1></div>'
        f'<a class="hov9" href="{date_str}.html" style="display:inline-flex;align-items:center;gap:7px;background:var(--accent);color:#fff;'
        'font-family:var(--font-cjk);font-weight:600;font-size:13.5px;padding:11px 18px;border-radius:10px;">'
        f'閱讀今日全部 {total} 條{I_ARR_S}</a></div>'
        # lead + secondary
        '<section data-r="hero" style="padding:32px 0 16px;display:grid;grid-template-columns:1.45fr 1fr;gap:40px;align-items:start;">'
        + lead_block +
        '<div><div style="font-family:var(--font-mono);font-size:10.5px;letter-spacing:0.2em;color:var(--text-faint);margin-bottom:6px;">頭條 · TOP STORIES</div>'
        + sec_rows + '</div></section>'
        # more today
        '<section style="padding:24px 0 8px;">'
        '<div style="font-family:var(--font-mono);font-size:10.5px;letter-spacing:0.2em;color:var(--text-faint);margin-bottom:14px;">今日其餘 · MORE TODAY</div>'
        f'<div data-r="cols2" style="display:grid;grid-template-columns:1fr 1fr;gap:6px 36px;">{rest_rows}</div></section>'
        + week_block + band +
        # trending
        '<section style="padding:44px 0 0;">'
        + section_title("趨勢", "TRENDING") +
        f'<div data-r="cols2" style="display:grid;grid-template-columns:{trending_grid_cols};gap:14px;">{topics_col}{repos_col}</div></section>'
        # recent
        '<section style="padding:44px 0 0;">'
        '<div style="display:flex;align-items:baseline;gap:14px;margin-bottom:20px;">'
        '<h2 style="font-family:var(--font-disp);font-weight:700;font-size:24px;letter-spacing:-0.02em;">最近</h2>'
        '<span style="font-family:var(--font-mono);font-size:11px;letter-spacing:0.2em;color:var(--text-faint);">LAST 7 DAYS</span>'
        '<a class="acc" href="archive.html" style="margin-left:auto;font-family:var(--font-mono);font-size:12px;color:var(--accent);">完整檔案 →</a></div>'
        f'<div style="display:flex;gap:12px;overflow-x:auto;padding-bottom:8px;">{recent}</div></section>'
        '</div>'
    )

def build_weekly_body(data, ctx, iy, iw):
    entries = data.get("entries", [])
    weeks = []
    for e in entries:
        k = (e.get("iso_year"), e.get("iso_week"))
        if k[0] and k[1] and k not in [w[0] for w in weeks]:
            weeks.append((k, ))
    # unique weeks sorted
    wk_keys = sorted({(e.get("iso_year"), e.get("iso_week")) for e in entries if e.get("iso_year") and e.get("iso_week")}, reverse=True)
    cur = (iy, iw)
    mon = date.fromisocalendar(iy, iw, 1); sun = mon + timedelta(days=6)
    rng = f"{mon.strftime('%m.%d')} — {sun.strftime('%m.%d')}"
    wk_entries = sorted([e for e in entries if e.get("iso_year") == iy and e.get("iso_week") == iw],
                        key=lambda e: e["date"], reverse=True)
    total_items = sum(e.get("item_count", 0) for e in wk_entries)
    wkd = get_week_data(data, entries, iy, iw)

    switch = ""
    for (jy, jw) in wk_keys:
        active = (jy, jw) == cur
        bc = "var(--accent-line)" if active else "var(--line)"
        tc = "var(--accent)" if active else "var(--text-dim)"
        switch += (f'<a class="swbtn" href="{weekly_file(jy,jw)}" style="font-family:var(--font-mono);font-size:13px;padding:7px 15px;'
                   f'border-radius:30px;background:var(--bg-elev);border:1px solid {bc};color:{tc};">第{jw:02d}週</a>')

    picks = ""
    if wkd["highlights"]:
        chips = theme_chips(wkd["themes"])
        cards = "".join(
            f'<div style="--c:{cat_var(h.get("category","tech"))};display:flex;gap:16px;padding:16px 20px;background:var(--bg-elev);border:1px solid var(--line);border-radius:12px;">'
            f'<span style="flex-shrink:0;font-family:var(--font-mono);font-size:11px;color:var(--accent);padding-top:3px;">{md(h["date"]) if h.get("date") and "-" in h.get("date","") else h.get("date","")}</span>'
            '<div style="flex:1;min-width:0;">'
            f'<div style="display:flex;align-items:center;gap:7px;margin-bottom:5px;"><span style="width:7px;height:7px;border-radius:2px;background:{cat_var(h.get("category","tech"))};"></span>'
            f'<span style="font-family:var(--font-mono);font-size:10px;color:var(--text-faint);">{cat_label(h.get("category","tech"))}</span></div>'
            f'<div style="font-size:15.5px;font-weight:600;line-height:1.45;">{h.get("title","")}</div>'
            f'<div style="margin-top:5px;font-size:13px;color:var(--text-dim);font-style:italic;line-height:1.6;">{h.get("why","")}</div></div></div>'
            for h in wkd["highlights"])
        repos = "".join(
            f'<span style="display:inline-flex;align-items:center;gap:9px;font-family:var(--font-mono);font-size:13px;color:var(--text);'
            f'background:var(--bg-elev);border:1px solid var(--line);padding:8px 14px;border-radius:10px;">{r["name"]}'
            f'<span style="font-size:11px;font-weight:600;color:var(--c-oss);">★ {r.get("stars","")}</span></span>'
            for r in wkd["repos"]) if wkd["repos"] else ""
        repos_block = (sub_title("本週熱門 Repo", "TRENDING") + f'<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:34px;">{repos}</div>') if repos else ""
        picks = (
            sub_title("本週焦點", "TOP PICKS")
            + f'<div style="display:flex;gap:7px;flex-wrap:wrap;margin:6px 0 16px;">{chips}</div>'
            + f'<div style="display:flex;flex-direction:column;gap:10px;margin-bottom:34px;">{cards}</div>'
            + repos_block)

    day_rows = ""
    for e in wk_entries:
        d = e["date"]
        day_rows += (
            f'<a class="dayrow" href="{d}.html" style="position:relative;display:flex;gap:18px;padding:13px 16px;margin-bottom:8px;'
            'background:var(--bg-elev);border:1px solid var(--line);border-radius:12px;cursor:pointer;align-items:flex-start;">'
            '<span style="position:absolute;left:-25px;top:20px;width:11px;height:11px;border-radius:50%;background:var(--accent);border:3px solid var(--bg);"></span>'
            f'<div style="flex-shrink:0;width:58px;"><div style="font-family:var(--font-mono);font-size:15px;font-weight:600;color:var(--text);">{dshort(d)}</div>'
            f'<div style="font-size:10.5px;color:var(--text-faint);margin-top:2px;">{wd_full(d)}</div></div>'
            f'<div style="flex-shrink:0;font-family:var(--font-mono);font-size:10.5px;color:var(--accent);align-self:center;">{e.get("item_count",0)} 條</div>'
            f'<p style="flex:1;font-size:13px;line-height:1.65;color:var(--text-dim);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">{e.get("summary","") or e.get("first_item_snippet","")}</p></a>')

    return (
        '<div style="animation:rise .5s ease;max-width:840px;margin:0 auto;">'
        + back_btn() +
        '<header style="padding:24px 0 26px;border-bottom:1px solid var(--line);">'
        '<div style="font-family:var(--font-mono);font-size:11px;letter-spacing:0.24em;color:var(--accent);margin-bottom:16px;">週報 · WEEKLY DIGEST</div>'
        '<div style="display:flex;align-items:flex-end;gap:18px;">'
        f'<h1 data-r="big" style="font-family:var(--font-disp);font-weight:700;font-size:54px;line-height:0.9;letter-spacing:-0.03em;">第{iw:02d}週</h1>'
        f'<span style="font-family:var(--font-mono);font-size:13px;color:var(--text-dim);padding-bottom:8px;">{iy}</span></div>'
        '<div style="margin-top:14px;display:flex;align-items:center;gap:14px;font-family:var(--font-mono);font-size:13px;color:var(--text-dim);">'
        f'<span>{rng}</span><span style="color:var(--line);">/</span>'
        f'<span><span style="color:var(--text);font-weight:600;">{len(wk_entries)}</span> 天</span>'
        f'<span><span style="color:var(--accent);font-weight:600;">{total_items}</span> 條</span></div></header>'
        f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin:24px 0 28px;">{switch}</div>'
        '<div style="margin:0 0 30px;padding:24px 26px;background:var(--bg-elev);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:0 14px 14px 0;">'
        '<div style="font-family:var(--font-mono);font-size:10.5px;letter-spacing:0.2em;color:var(--accent);margin-bottom:11px;">本週總結 · WEEKLY SUMMARY</div>'
        f'<p style="font-size:15.5px;line-height:1.9;color:var(--text);">{wkd["summary"]}</p></div>'
        + picks +
        sub_title("每日記錄", "DAY BY DAY", dim=True)
        + '<div style="position:relative;padding-left:28px;"><div style="position:absolute;left:5px;top:12px;bottom:12px;width:1px;background:var(--line);"></div>'
        + day_rows + '</div></div>'
    )

def build_monthly_body(data, ctx, mk):
    m = (data.get("month_data") or {})[mk]
    entries = data.get("entries", [])
    lbl = m.get("label") or (mk[:4] + "年" + str(int(mk[5:7])) + "月")
    en = m.get("en") or datetime.strptime(mk + "-01", "%Y-%m-%d").strftime("%B %Y").upper()
    # highlights: agent or derive from month's items
    if m.get("highlights"):
        hls = m["highlights"]
    else:
        mitems = []
        for e in entries:
            if e["date"][:7] == mk:
                for it in e.get("items", []):
                    mitems.append({**it, "date": e["date"]})
        hls = derive_highlights(mitems, 4)
    themes = m.get("themes", [])

    switch = ""
    for k in ctx["month_keys"]:
        active = k == mk
        bc = "var(--accent-line)" if active else "var(--line)"
        tc = "var(--accent)" if active else "var(--text-dim)"
        mv = (data.get("month_data") or {})[k]
        ml = mv.get("label") or (k[:4] + "年" + str(int(k[5:7])) + "月")
        switch += (f'<a class="swbtn" href="{monthly_file(k)}" style="font-family:var(--font-mono);font-size:13px;padding:7px 15px;'
                   f'border-radius:30px;background:var(--bg-elev);border:1px solid {bc};color:{tc};">{ml}</a>')

    chips = theme_chips(themes)
    hi = "".join(render_hl_plain(h) for h in hls)

    # weeks of this month
    wk_keys = sorted({(e.get("iso_year"), e.get("iso_week")) for e in entries if e["date"][:7] == mk and e.get("iso_year")}, reverse=True)
    wk_cards = ""
    for (jy, jw) in wk_keys:
        we = [e for e in entries if e.get("iso_year") == jy and e.get("iso_week") == jw]
        mon = date.fromisocalendar(jy, jw, 1); sun = mon + timedelta(days=6)
        rng = f"{mon.strftime('%m.%d')} — {sun.strftime('%m.%d')}"
        tot = sum(e.get("item_count", 0) for e in we)
        wk_cards += (
            f'<a class="lift" href="{weekly_file(jy,jw)}" style="background:var(--bg-elev);border:1px solid var(--line);border-radius:12px;padding:16px;cursor:pointer;display:flex;flex-direction:column;gap:8px;">'
            f'<div style="font-family:var(--font-disp);font-size:26px;font-weight:700;line-height:1;">第{jw:02d}週</div>'
            f'<div style="font-family:var(--font-mono);font-size:11px;color:var(--text-dim);">{rng}</div>'
            f'<div style="font-family:var(--font-mono);font-size:11px;color:var(--text-faint);">{len(we)} 天 · {tot} 條</div></a>')

    return (
        '<div style="animation:rise .5s ease;max-width:840px;margin:0 auto;">'
        + back_btn() +
        '<header style="padding:24px 0 26px;border-bottom:1px solid var(--line);">'
        '<div style="font-family:var(--font-mono);font-size:11px;letter-spacing:0.24em;color:var(--accent);margin-bottom:16px;">月報 · MONTHLY REVIEW</div>'
        '<div style="display:flex;align-items:flex-end;gap:18px;">'
        f'<h1 data-r="big" style="font-family:var(--font-disp);font-weight:700;font-size:50px;line-height:0.9;letter-spacing:-0.03em;">{lbl}</h1>'
        f'<span style="font-family:var(--font-mono);font-size:13px;color:var(--text-dim);padding-bottom:8px;">{en}</span></div></header>'
        f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin:24px 0 4px;">{switch}</div>'
        '<div style="margin:28px 0 30px;padding:24px 26px;background:var(--bg-elev);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:0 14px 14px 0;">'
        '<div style="font-family:var(--font-mono);font-size:10.5px;letter-spacing:0.2em;color:var(--accent);margin-bottom:11px;">本月總結 · MONTHLY SUMMARY</div>'
        f'<p style="font-size:15.5px;line-height:1.9;color:var(--text);">{m.get("summary","")}</p></div>'
        + sub_title("本月焦點", "TOP PICKS")
        + f'<div style="display:flex;gap:7px;flex-wrap:wrap;margin:6px 0 16px;">{chips}</div>'
        + f'<div data-r="cols2" style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:34px;">{hi}</div>'
        + sub_title("本月各週", "WEEKS")
        + f'<div data-r="cols4" style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;">{wk_cards}</div></div>'
    )

def build_category_body(data, cur):
    entries = data.get("entries", [])
    # aggregate items by category across days
    streams = {c: [] for c in CAT_ORDER}
    for e in entries:
        for it in e.get("items", []):
            c = it.get("category", "general")
            streams.setdefault(c, []).append({**it, "date": e["date"]})
    col = cat_var(cur)
    cur_stream = streams.get(cur, [])

    tabs = ""
    for k in CAT_ORDER:
        active = k == cur
        bc = "var(--accent-line)" if active else "var(--line)"
        tc = "var(--accent)" if active else "var(--text-dim)"
        tabs += (f'<a class="swbtn" href="category-{k}.html" style="display:inline-flex;align-items:center;gap:8px;background:var(--bg-elev);'
                 f'border:1px solid {bc};border-radius:30px;padding:8px 15px;font-family:var(--font-cjk);font-size:13.5px;color:{tc};">'
                 f'<span style="width:8px;height:8px;border-radius:2px;background:{cat_var(k)};"></span>{cat_label(k)}'
                 f'<span style="font-family:var(--font-mono);font-size:11px;color:var(--text-faint);">{len(streams.get(k,[]))}</span></a>')

    rows = ""
    fnt = "var(--font-mono)" if cur == "github" else "var(--font-cjk)"
    for it in cur_stream:
        url = it.get("link") or ("https://" + (it.get("source_domain") or extract_domain(it.get("link", ""))))
        src = it.get("source_domain", "") or extract_domain(it.get("link", ""))
        sf = fmt_stars(it.get("stars", 0))
        star = (f'<span style="flex-shrink:0;font-family:var(--font-mono);font-size:11px;font-weight:600;color:var(--c-oss);padding-top:2px;">★ {sf}</span>') if sf else ""
        rows += (
            f'<article class="ncard" style="--c:{col};position:relative;display:flex;gap:16px;background:var(--bg-elev);border:1px solid var(--line);'
            'border-radius:12px;padding:15px 18px 15px 20px;overflow:hidden;align-items:flex-start;">'
            f'<span style="position:absolute;left:0;top:0;bottom:0;width:3px;background:{col};"></span>'
            f'<span style="flex-shrink:0;font-family:var(--font-mono);font-size:12px;color:var(--accent);padding-top:3px;width:42px;">{md(it["date"])}</span>'
            '<div style="flex:1;min-width:0;">'
            '<div style="display:flex;align-items:flex-start;gap:10px;">'
            f'<a class="tcol" href="{url}" target="_blank" rel="noopener" style="--c:{col};flex:1;min-width:0;font-family:{fnt};font-weight:700;font-size:15.5px;line-height:1.42;color:var(--text);">{it.get("title","")}</a>{star}</div>'
            '<div style="margin-top:6px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;">'
            f'<span style="font-family:var(--font-mono);font-size:11px;color:var(--text-faint);background:var(--bg-elev2);padding:2px 8px;border-radius:6px;">{src}</span>'
            f'<span style="font-size:12.5px;color:var(--text-dim);font-style:italic;">{it.get("why","")}</span></div></div></article>')

    total_days = len({e["date"] for e in entries})
    return (
        '<div style="animation:rise .5s ease;max-width:840px;margin:0 auto;">'
        + back_btn() +
        '<header style="padding:24px 0 22px;">'
        '<div style="font-family:var(--font-mono);font-size:11px;letter-spacing:0.24em;color:var(--accent);margin-bottom:14px;">分類 · TOPICS</div>'
        f'<h1 data-r="big" style="font-family:var(--font-disp);font-weight:700;font-size:46px;line-height:1;letter-spacing:-0.03em;color:{col};">{cat_label(cur)}</h1>'
        f'<div style="margin-top:12px;font-family:var(--font-mono);font-size:13px;color:var(--text-dim);"><span style="color:var(--accent);font-weight:600;">{len(cur_stream)}</span> 條 · 跨 {total_days} 天</div></header>'
        f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:26px;border-bottom:1px solid var(--line);padding-bottom:18px;">{tabs}</div>'
        f'<div style="display:flex;flex-direction:column;gap:10px;">{rows}</div></div>'
    )

def build_archive_body(data):
    entries = data.get("entries", [])
    wk_keys = sorted({(e.get("iso_year"), e.get("iso_week")) for e in entries if e.get("iso_year") and e.get("iso_week")}, reverse=True)
    total_days = len(entries)
    total_items = sum(e.get("item_count", 0) for e in entries)
    rows = ""
    for (iy, iw) in wk_keys:
        we = sorted([e for e in entries if e.get("iso_year") == iy and e.get("iso_week") == iw], key=lambda e: e["date"], reverse=True)
        mon = date.fromisocalendar(iy, iw, 1); sun = mon + timedelta(days=6)
        rng = f"{mon.strftime('%m.%d')} — {sun.strftime('%m.%d')}"
        tot = sum(e.get("item_count", 0) for e in we)
        rows += (
            f'<a class="hov" href="{weekly_file(iy,iw)}" style="position:relative;margin:24px 0 10px;cursor:pointer;display:flex;align-items:center;gap:10px;">'
            '<span style="position:absolute;left:-25px;width:11px;height:11px;border-radius:50%;background:var(--accent);border:3px solid var(--bg);"></span>'
            f'<span style="font-family:var(--font-mono);font-size:12px;font-weight:700;letter-spacing:0.06em;color:var(--accent);">第{iw:02d}週</span>'
            f'<span style="font-family:var(--font-mono);font-size:11px;color:var(--text-faint);">{rng} · {tot} 條</span>'
            '<span style="height:1px;flex:1;background:var(--line-soft);"></span></a>')
        for e in we:
            d = e["date"]
            rows += (
                f'<a href="{d}.html" class="archday" style="position:relative;display:flex;gap:18px;align-items:baseline;padding:11px 16px;margin:4px 0;border-radius:11px;cursor:pointer;">'
                '<span style="position:absolute;left:-23px;top:18px;width:7px;height:7px;border-radius:50%;background:var(--line);border:2px solid var(--bg);"></span>'
                f'<div style="flex-shrink:0;width:62px;"><div style="font-family:var(--font-mono);font-size:15px;font-weight:600;color:var(--text);letter-spacing:0.01em;">{dshort(d)}</div>'
                f'<div style="font-size:11px;color:var(--text-faint);margin-top:1px;">{wd_full(d)}</div></div>'
                f'<div style="flex-shrink:0;font-family:var(--font-mono);font-size:11px;color:var(--text-dim);background:var(--bg-elev2);padding:2px 9px;border-radius:20px;align-self:center;">{e.get("item_count",0)} 條</div>'
                f'<p style="flex:1;font-size:13.5px;line-height:1.6;color:var(--text-dim);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;">{e.get("summary","") or e.get("first_item_snippet","")}</p></a>')

    return (
        '<div style="animation:rise .5s ease;">'
        '<style>.archday:hover{background:var(--bg-elev)}</style>'
        '<header style="padding:40px 0 26px;border-bottom:1px solid var(--line);">'
        '<div style="font-family:var(--font-mono);font-size:11px;letter-spacing:0.24em;color:var(--accent);margin-bottom:14px;">檔案 · ARCHIVE</div>'
        '<h1 data-r="big" style="font-family:var(--font-disp);font-weight:700;font-size:48px;line-height:1;letter-spacing:-0.03em;">歷史記錄</h1>'
        f'<div style="margin-top:14px;font-family:var(--font-mono);font-size:13px;color:var(--text-dim);">{total_days} 天 · {total_items} 條 · {len(wk_keys)} 週</div></header>'
        '<div style="position:relative;padding-left:26px;margin-top:30px;max-width:840px;">'
        '<div style="position:absolute;left:5px;top:14px;bottom:14px;width:1px;background:var(--line);"></div>'
        + rows + '</div></div>'
    )

# ---------------------------------------------------------------------------
# Regenerate all derived pages
# ---------------------------------------------------------------------------
def write_page(path, html):
    with open(os.path.join(BASE_DIR, path), "w", encoding="utf-8") as f:
        f.write(html)

def regenerate_all(data):
    ctx = build_ctx(data)
    entries = data.get("entries", [])

    # index
    write_page("index.html", page_shell("AI 新聞檔案", "home", build_index_body(data, ctx), ctx))
    print("📋 index.html")

    # weeklies
    wk_keys = sorted({(e.get("iso_year"), e.get("iso_week")) for e in entries if e.get("iso_year") and e.get("iso_week")}, reverse=True)
    for (iy, iw) in wk_keys:
        title = f"AI 新聞 · 第{iw:02d}週 ({iy})"
        write_page(weekly_file(iy, iw), page_shell(title, "weekly", build_weekly_body(data, ctx, iy, iw), ctx))
    print(f"📊 {len(wk_keys)} weekly page(s)")

    # monthlies (only with summary)
    for mk in ctx["month_keys"]:
        title = f"AI 新聞 · {mk[:4]}年{int(mk[5:7])}月"
        write_page(monthly_file(mk), page_shell(title, "monthly", build_monthly_body(data, ctx, mk), ctx))
    if ctx["month_keys"]:
        print(f"🗓  {len(ctx['month_keys'])} monthly page(s)")

    # category streams
    for c in CAT_ORDER:
        title = f"AI 新聞 · {cat_label(c)}"
        write_page(f"category-{c}.html", page_shell(title, "category", build_category_body(data, c), ctx))
    print("🏷  4 category page(s)")

    # archive
    write_page("archive.html", page_shell("AI 新聞 · 歷史記錄", "archive", build_archive_body(data), ctx))
    print("🗂  archive.html")

# ---------------------------------------------------------------------------
# Daily
# ---------------------------------------------------------------------------
def generate_daily(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        d = json.load(f)
    date_str = d["date"]
    dow = d.get("dow", "")
    items = d.get("items", [])
    summary = d.get("summary", "")
    hero_image = d.get("hero_image", "")
    for it in items:
        if not it.get("source_domain"):
            it["source_domain"] = extract_domain(it.get("link", ""))

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    iy, iw, _ = dt.isocalendar()

    data = load_index()
    ctx = build_ctx(data)  # provisional for nav while writing daily

    # write daily page
    body = build_daily_body(date_str, dow, items, summary)
    # ensure ctx reflects this date as latest if newest
    # (recompute after persisting)
    truncated = summary[:140] + "…" if len(summary) > 140 else summary
    snippet = ""
    if items:
        ft = items[0].get("title", ""); fd = items[0].get("description", "") or items[0].get("why", "")
        if fd:
            s = f"{ft}: {fd}"; snippet = s[:110] + "…" if len(s) > 110 else s
    cat_counts = {}
    for it in items:
        cat_counts[it.get("category", "general")] = cat_counts.get(it.get("category", "general"), 0) + 1
    # compact items for persistence (used by category streams / hero / trending)
    slim = [{"title": it.get("title", ""), "link": it.get("link", ""), "category": it.get("category", "general"),
             "stars": it.get("stars", 0), "signal": it.get("signal", ""), "source_domain": it.get("source_domain", ""),
             "why": it.get("why", ""), "description": it.get("description", ""), "image": it.get("image", "")}
            for it in items]

    entry = {"date": date_str, "dow": dow, "item_count": len(items), "iso_year": iy, "iso_week": iw,
             "summary": truncated, "first_item_snippet": snippet, "cat_counts": cat_counts, "items": slim}
    if hero_image:
        entry["hero_image"] = hero_image

    found = False
    for i, e in enumerate(data["entries"]):
        if e.get("date") == date_str:
            data["entries"][i] = {**e, **entry}; found = True; break
    if not found:
        data["entries"].append(entry)
    data["entries"].sort(key=lambda e: e.get("date", ""), reverse=True)
    save_index(data)

    ctx = build_ctx(data)
    write_page(f"{date_str}.html", page_shell(f"AI 新聞 · {date_str}", "daily", body, ctx))
    print(f"✅ {date_str}.html")
    regenerate_all(data)

def generate_weekly(path=None):
    data = load_index()
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            incoming = json.load(f)
        wd = data.get("week_data") or {}
        wd.update(incoming)
        data["week_data"] = wd
        save_index(data)
        print(f"📝 merged {len(incoming)} week-data entrie(s)")
    regenerate_all(data)

def generate_monthly(path=None):
    data = load_index()
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            incoming = json.load(f)
        md_ = data.get("month_data") or {}
        md_.update(incoming)
        data["month_data"] = md_
        save_index(data)
        print(f"📝 merged {len(incoming)} month-data entrie(s)")
    regenerate_all(data)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    mode = sys.argv[1]
    if mode == "daily":
        if len(sys.argv) < 3:
            print("Usage: python3 generate-news-html.py daily <json-path>"); sys.exit(1)
        if not os.path.exists(sys.argv[2]):
            print(f"❌ File not found: {sys.argv[2]}"); sys.exit(1)
        generate_daily(sys.argv[2])
    elif mode == "weekly":
        generate_weekly(sys.argv[2] if len(sys.argv) >= 3 else None)
    elif mode == "monthly":
        generate_monthly(sys.argv[2] if len(sys.argv) >= 3 else None)
    elif mode == "index":
        regenerate_all(load_index())
    else:
        print(f"❌ Unknown mode: {mode}"); print(__doc__); sys.exit(1)

if __name__ == "__main__":
    main()
