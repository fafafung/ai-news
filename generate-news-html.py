#!/usr/bin/env python3
"""
AI News Archive — Static HTML Generator (v2 — modern editorial redesign)
========================================================================
Generates daily, weekly, and index HTML pages for the AI news archive system.

Usage:
    python3 generate-news-html.py daily  /path/to/daily-news.json
    python3 generate-news-html.py weekly [/path/to/week-summaries.json]
    python3 generate-news-html.py index

Daily mode:
    Reads a JSON file (schema below), writes YYYY-MM-DD.html, updates
    index_data.json (incl. category counts + headlines for the homepage hero),
    and regenerates index.html.

Weekly mode:
    Groups index_data.json entries by ISO week, writes weekly-YYYY-WWW.html
    with a per-week summary + day-by-day timeline, regenerates index.html.
    Optional 2nd arg: a JSON file of week summaries to merge & persist, e.g.
        { "2026-W25": "本週主軸係 open-source 模型大爆發 …" }

Index mode:
    Regenerates index.html from index_data.json.

All paths are relative so the site works locally and on Vercel.

Input JSON schema (daily mode):
{
  "date": "2026-06-24",
  "dow": "三",                         // optional; weekday is also derived from date
  "items": [
    {
      "title": "openai/codex",
      "link": "https://github.com/openai/codex",
      "category": "github",            // github | tech | general | research
      "why": "短摘要（meta 用，會以斜體顯示）",
      "description": "長描述，2-3 句中文，係用戶主力閱讀嘅內容。",
      "stars": 44700,                   // optional
      "signal": "big",                  // optional: new|big|hot|pain|para
      "source_domain": "github.com",    // optional, auto-extracted from link
      "image": "https://…/preview.png"  // optional thumbnail URL (news/research)
    }
  ],
  "summary": "全日總括（會以「編輯導讀」顯示喺頂部）",
  "hero_image": "https://…/og.png"      // optional homepage hero highlight image
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

CATEGORY_LABELS = {
    "github": "GitHub 開源",
    "tech": "科技新聞",
    "general": "業界動態",
    "research": "研究論文",
}

CATEGORY_SHORT = {
    "github": "GitHub",
    "tech": "科技",
    "general": "業界",
    "research": "論文",
}

CATEGORY_ORDER = ["github", "tech", "general", "research"]

# Each category maps to a CSS custom property (defined per-theme in the stylesheet)
CATEGORY_VAR = {
    "github": "var(--c-oss)",
    "tech": "var(--c-tech)",
    "general": "var(--c-biz)",
    "research": "var(--c-paper)",
}

# Signal -> (label, css-colour-var)
SIGNAL_LABELS = {
    "new": ("新項目", "var(--c-paper)"),
    "big": ("官方", "var(--c-biz)"),
    "hot": ("熱門", "var(--accent)"),
    "pain": ("實用", "var(--c-paper)"),
    "para": ("觀點", "var(--c-tech)"),
}

WEEKDAY_CHARS = "一二三四五六日"          # Mon..Sun (isoweekday 1..7)
WEEKDAY_FULL = ["星期一", "星期二", "星期三", "星期四",
                "星期五", "星期六", "星期日"]


# ---------------------------------------------------------------------------
# Inline SVG icons (no braces -> safe inside f-strings)
# ---------------------------------------------------------------------------

ICON_LOGO = ('<svg width="17" height="17" viewBox="0 0 24 24" fill="none" '
             'stroke="#fff" stroke-width="2.4" stroke-linecap="round">'
             '<path d="M5 19V5l7 7-7 7Z"/><path d="M14 12h5"/></svg>')

ICON_GITHUB = ('<svg width="18" height="18" viewBox="0 0 24 24" '
               'fill="currentColor"><path d="M12 2C6.48 2 2 6.58 2 12.25c0 '
               '4.53 2.87 8.37 6.84 9.73.5.1.68-.22.68-.49l-.01-1.72c-2.78.62'
               '-3.37-1.37-3.37-1.37-.45-1.18-1.11-1.5-1.11-1.5-.91-.64.07-.62'
               '.07-.62 1 .07 1.53 1.06 1.53 1.06.89 1.57 2.34 1.12 2.91.85.09'
               '-.66.35-1.12.63-1.38-2.22-.26-4.56-1.14-4.56-5.07 0-1.12.39'
               '-2.03 1.03-2.75-.1-.26-.45-1.3.1-2.71 0 0 .84-.28 2.75 1.05a9.3'
               ' 9.3 0 0 1 5 0c1.91-1.33 2.75-1.05 2.75-1.05.55 1.41.2 2.45.1 '
               '2.71.64.72 1.03 1.63 1.03 2.75 0 3.94-2.34 4.81-4.57 5.06.36.32'
               '.68.94.68 1.9l-.01 2.82c0 .27.18.59.69.49A10.26 10.26 0 0 0 22 '
               '12.25C22 6.58 17.52 2 12 2Z"/></svg>')

ICON_THEME = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" '
              'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
              'stroke-linejoin="round"><path d="M12 3a9 9 0 1 0 9 9c-.5 0-1 0'
              '-1.5-.1A6.5 6.5 0 0 1 12 3z"/></svg>')

ICON_ARROW = ('<svg width="15" height="15" viewBox="0 0 24 24" fill="none" '
              'stroke="currentColor" stroke-width="2.4" stroke-linecap="round" '
              'stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"/></svg>')

ICON_EXTERNAL = ('<svg width="13" height="13" viewBox="0 0 24 24" fill="none" '
                 'stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
                 'stroke-linejoin="round" style="opacity:.45;flex-shrink:0"><path '
                 'd="M7 17 17 7M9 7h8v8"/></svg>')

ICON_BACK = ('<svg width="14" height="14" viewBox="0 0 24 24" fill="none" '
             'stroke="currentColor" stroke-width="2.4" stroke-linecap="round" '
             'stroke-linejoin="round"><path d="M19 12H5M11 18l-6-6 6-6"/></svg>')

ICON_STAR = ('<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor">'
             '<path d="M12 2l2.9 6.26 6.85.6-5.18 4.52 1.55 6.7L12 16.9 5.88 '
             '20.6l1.55-6.7L2.25 9.4l6.85-.6L12 2Z"/></svg>')

ICON_IMAGE = ('<svg width="22" height="22" viewBox="0 0 24 24" fill="none" '
              'stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" '
              'width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/>'
              '<path d="M21 15l-5-5L5 21"/></svg>')


# ---------------------------------------------------------------------------
# CSS — self-contained, no external deps  (braces are literal: never .format()ed)
# ---------------------------------------------------------------------------

CSS = r"""
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}

:root{
  --bg:#0b0c0f;--bg-elev:#15161c;--bg-elev2:#1c1e26;--line:#262833;--line-soft:#1d1f27;
  --text:#ECEDF0;--text-dim:#b7bbc7;--text-faint:#878b98;
  --accent:#5B6CFF;--accent-soft:rgba(91,108,255,.16);--accent-line:rgba(91,108,255,.34);
  --c-oss:#E8B23A;--c-tech:#5BA3F7;--c-biz:#B488FF;--c-paper:#52CC81;
  --glow:radial-gradient(ellipse at center,rgba(91,108,255,.16),transparent 70%);
  --font-cjk:"Noto Sans HK","PingFang HK","Microsoft JhengHei",-apple-system,sans-serif;
  --font-disp:"Space Grotesk","Noto Sans HK","PingFang HK",sans-serif;
  --font-mono:"JetBrains Mono","SFMono-Regular","Menlo",monospace;
}
:root[data-theme="light"]{
  --bg:#FAF8F4;--bg-elev:#fff;--bg-elev2:#F3F1EA;--line:#E5E2D9;--line-soft:#EDEAE2;
  --text:#17181C;--text-dim:#54565E;--text-faint:#82848c;
  --accent:#5B6CFF;--accent-soft:rgba(91,108,255,.10);--accent-line:rgba(91,108,255,.26);
  --c-oss:#B07F15;--c-tech:#1F6FD6;--c-biz:#7C4CD4;--c-paper:#1E9B52;
  --glow:radial-gradient(ellipse at center,rgba(91,108,255,.10),transparent 70%);
}
@media (prefers-color-scheme:light){
  :root:not([data-theme="dark"]):not([data-theme="light"]){
    --bg:#FAF8F4;--bg-elev:#fff;--bg-elev2:#F3F1EA;--line:#E5E2D9;--line-soft:#EDEAE2;
    --text:#17181C;--text-dim:#54565E;--text-faint:#82848c;
    --accent-soft:rgba(91,108,255,.10);--accent-line:rgba(91,108,255,.26);
    --c-oss:#B07F15;--c-tech:#1F6FD6;--c-biz:#7C4CD4;--c-paper:#1E9B52;
    --glow:radial-gradient(ellipse at center,rgba(91,108,255,.10),transparent 70%);
  }
}

html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--font-cjk);
  -webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;
  position:relative;overflow-x:hidden;min-height:100vh}
a{color:inherit;text-decoration:none}
::selection{background:var(--accent);color:#fff}
::-webkit-scrollbar{width:11px;height:11px}
::-webkit-scrollbar-thumb{background:var(--line);border-radius:6px;border:3px solid var(--bg)}
::-webkit-scrollbar-track{background:var(--bg)}
@keyframes rise{from{transform:translateY(14px);opacity:.6}to{transform:translateY(0);opacity:1}}
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.35;transform:scale(.8)}}

.glow{position:fixed;top:-260px;left:50%;transform:translateX(-50%);width:1000px;
  height:560px;background:var(--glow);pointer-events:none;z-index:0}

/* ── Masthead ── */
.nav{position:sticky;top:0;z-index:50;backdrop-filter:blur(14px);
  background:color-mix(in srgb,var(--bg) 78%,transparent);border-bottom:1px solid var(--line)}
.nav-in{max-width:1120px;margin:0 auto;padding:14px 28px;display:flex;align-items:center;gap:24px}
.brand{display:flex;align-items:center;gap:12px;flex-shrink:0}
.brand-mark{width:34px;height:34px;border-radius:9px;background:var(--accent);display:flex;
  align-items:center;justify-content:center;box-shadow:0 4px 14px var(--accent-soft)}
.brand-name{font-family:var(--font-disp);font-weight:700;font-size:17px;letter-spacing:-.01em;line-height:1.05}
.brand-name b{color:var(--accent);font-family:var(--font-mono);font-weight:700;margin-right:3px}
.brand-tag{font-family:var(--font-mono);font-size:9.5px;letter-spacing:.22em;color:var(--text-faint);margin-top:2px}
.nav-links{display:flex;align-items:center;gap:4px;margin-left:8px}
.nav-link{position:relative;font-size:14px;font-weight:500;color:var(--text);padding:8px 12px;transition:color .15s}
.nav-link:hover{color:var(--accent)}
.nav-link.active::after{content:"";position:absolute;left:12px;right:12px;bottom:2px;height:2px;
  background:var(--accent);border-radius:2px}
.nav-right{margin-left:auto;display:flex;align-items:center;gap:18px}
.live{display:flex;align-items:center;gap:8px}
.live-dot{width:7px;height:7px;border-radius:50%;background:var(--accent);animation:pulse 2s ease-in-out infinite}
.live span{font-family:var(--font-mono);font-size:11px;color:var(--text-dim)}
.icon-link{display:flex;color:var(--text-dim);transition:color .15s}
.icon-link:hover{color:var(--text)}
.icon-btn{display:flex;align-items:center;justify-content:center;width:34px;height:34px;border-radius:9px;
  border:1px solid var(--line);background:var(--bg-elev);color:var(--text-dim);cursor:pointer;transition:all .15s}
.icon-btn:hover{color:var(--accent);border-color:var(--accent-line)}

.main{position:relative;z-index:1;max-width:1120px;margin:0 auto;padding:0 28px 90px;animation:rise .5s ease}
.narrow{max-width:780px;margin:0 auto}
.wide{max-width:820px;margin:0 auto}

/* ── Hero (index) ── */
.hero{padding:56px 0 44px;display:grid;grid-template-columns:1.55fr 1fr;gap:48px;
  align-items:start;border-bottom:1px solid var(--line)}
.kicker{display:flex;align-items:center;gap:10px;margin-bottom:20px}
.kicker .k{font-family:var(--font-mono);font-size:11px;letter-spacing:.26em;color:var(--accent);font-weight:600}
.kicker .ln{height:1px;width:36px;background:var(--accent-line)}
.kicker .en{font-family:var(--font-mono);font-size:11px;letter-spacing:.2em;color:var(--text-faint)}
.bigdate{font-family:var(--font-disp);font-weight:700;font-size:62px;line-height:.98;letter-spacing:-.03em}
.dmeta{margin-top:10px;display:flex;align-items:center;gap:14px;font-family:var(--font-mono);font-size:13px;color:var(--text-dim)}
.dmeta .sep{color:var(--line)}
.dmeta b{color:var(--accent);font-weight:600}
.lede{margin-top:24px;font-size:16.5px;line-height:1.85;color:var(--text-dim);max-width:560px;font-weight:400}
.btn{display:inline-flex;align-items:center;gap:8px;margin-top:28px;background:var(--accent);color:#fff;border:none;
  cursor:pointer;font-family:var(--font-cjk);font-weight:600;font-size:14px;padding:12px 20px;border-radius:10px;transition:all .15s}
.btn:hover{opacity:.9;transform:translateY(-1px)}
.panel{background:var(--bg-elev);border:1px solid var(--line);border-radius:16px;padding:18px}
.panel-hl{position:relative;aspect-ratio:16/10;border-radius:12px;overflow:hidden;margin-bottom:16px;
  background:linear-gradient(135deg,var(--bg-elev2),color-mix(in srgb,var(--accent) 30%,var(--bg-elev2)))}
.panel-hl img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.panel-hl .ph{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--text-faint);opacity:.5}
.panel-hl .cap{position:absolute;left:0;right:0;bottom:0;padding:14px 16px;background:linear-gradient(to top,rgba(0,0,0,.62),transparent)}
.panel-hl .cap .k{font-family:var(--font-mono);font-size:9.5px;letter-spacing:.2em;color:#fff;opacity:.82;margin-bottom:3px}
.panel-hl .cap .t{font-size:13.5px;font-weight:600;color:#fff;line-height:1.4}
.panel-lbl{font-family:var(--font-mono);font-size:10.5px;letter-spacing:.2em;color:var(--text-faint);margin-bottom:6px}
.hl-row{display:flex;gap:12px;padding:11px 0;border-top:1px solid var(--line-soft);cursor:pointer;transition:opacity .15s}
.hl-row:hover{opacity:.7}
.hl-row .dot{margin-top:7px;width:7px;height:7px;border-radius:50%;flex-shrink:0;background:var(--c)}
.hl-row .t{font-size:14px;line-height:1.5;color:var(--text);font-weight:500}
.catstats{margin-top:16px;padding-top:14px;border-top:1px solid var(--line-soft);display:flex;gap:16px}
.catstat{display:flex;flex-direction:column;gap:3px}
.catstat .n{font-family:var(--font-mono);font-size:20px;font-weight:700;color:var(--c);line-height:1}
.catstat .l{font-size:10px;color:var(--text-faint)}

/* ── Section titles ── */
.block{padding:48px 0 12px}
.block.tl{padding:44px 0 0}
.sec-title{display:flex;align-items:baseline;gap:14px;margin-bottom:24px}
.sec-title h2{font-family:var(--font-disp);font-weight:700;font-size:24px;letter-spacing:-.02em}
.sec-title .en{font-family:var(--font-mono);font-size:11px;letter-spacing:.2em;color:var(--text-faint)}
.sec-title .stat{margin-left:auto;font-family:var(--font-mono);font-size:12px;color:var(--text-dim)}

/* ── Weekly grid (index) ── */
.week-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.week-card{background:var(--bg-elev);border:1px solid var(--line);border-radius:14px;padding:20px 18px;
  cursor:pointer;display:flex;flex-direction:column;gap:14px;transition:all .15s}
.week-card:hover{border-color:var(--accent-line);transform:translateY(-2px)}
.week-card .top{display:flex;align-items:baseline;justify-content:space-between}
.week-card .wk{font-family:var(--font-mono);font-size:10px;letter-spacing:.18em;color:var(--text-faint)}
.week-card .num{font-family:var(--font-disp);font-size:34px;font-weight:700;line-height:.9}
.week-card .rng{font-family:var(--font-mono);font-size:12px;color:var(--text-dim)}
.week-card .bar{height:4px;border-radius:3px;background:var(--bg-elev2);overflow:hidden}
.week-card .bar i{display:block;height:100%;border-radius:3px;background:var(--accent)}
.week-card .st{display:flex;gap:16px;font-family:var(--font-mono);font-size:12px;color:var(--text-dim)}
.week-card .st b{color:var(--text);font-weight:600}

/* ── Archive timeline (index) ── */
.timeline{position:relative;padding-left:26px}
.timeline .rail{position:absolute;left:5px;top:14px;bottom:14px;width:1px;background:var(--line)}
.arch-week{position:relative;margin:22px 0 10px;cursor:pointer;display:flex;align-items:center;gap:10px;transition:opacity .15s}
.arch-week:hover{opacity:.75}
.arch-week .pt{position:absolute;left:-25px;width:11px;height:11px;border-radius:50%;background:var(--accent);border:3px solid var(--bg)}
.arch-week .lbl{font-family:var(--font-mono);font-size:12px;font-weight:700;letter-spacing:.06em;color:var(--accent)}
.arch-week .meta{font-family:var(--font-mono);font-size:11px;color:var(--text-faint)}
.arch-week .fill{height:1px;flex:1;background:var(--line-soft)}
.arch-day{position:relative;display:flex;gap:18px;align-items:baseline;padding:11px 16px;margin:4px 0;border-radius:11px;
  cursor:pointer;transition:background .15s}
.arch-day:hover{background:var(--bg-elev)}
.arch-day .pt{position:absolute;left:-23px;top:18px;width:7px;height:7px;border-radius:50%;background:var(--line);border:2px solid var(--bg)}
.arch-day .d{flex-shrink:0;width:62px}
.arch-day .d .dt{font-family:var(--font-mono);font-size:15px;font-weight:600;letter-spacing:.01em}
.arch-day .d .dw{font-size:11px;color:var(--text-faint);margin-top:1px}
.arch-day .cnt{flex-shrink:0;font-family:var(--font-mono);font-size:11px;color:var(--text-dim);
  background:var(--bg-elev2);padding:2px 9px;border-radius:20px;align-self:center}
.arch-day .sn{flex:1;font-size:13.5px;line-height:1.6;color:var(--text-dim);
  display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}

/* ── Day / Weekly page headers ── */
.back{margin-top:32px;display:inline-flex;align-items:center;gap:7px;background:none;border:none;cursor:pointer;
  font-family:var(--font-mono);font-size:12px;color:var(--text-dim);letter-spacing:.04em;transition:color .15s}
.back:hover{color:var(--accent)}
.phead{padding:24px 0 28px;border-bottom:1px solid var(--line)}
.phead .k{font-family:var(--font-mono);font-size:11px;letter-spacing:.24em;color:var(--accent);margin-bottom:16px}
.phead h1{font-family:var(--font-disp);font-weight:700;font-size:52px;line-height:1;letter-spacing:-.03em}
.phead .row{margin-top:14px;display:flex;align-items:center;gap:14px;font-family:var(--font-mono);font-size:13px;color:var(--text-dim)}
.phead .row b{color:var(--accent);font-weight:600}
.phead .row .t{color:var(--text);font-weight:600}
.phead .row .sep{color:var(--line)}
.wkh1{display:flex;align-items:flex-end;gap:18px}
.wkh1 .yr{font-family:var(--font-mono);font-size:13px;color:var(--text-dim);padding-bottom:8px}

/* ── Lede / summary box ── */
.ledebox{margin:28px 0 6px;padding:22px 24px;background:var(--bg-elev);border:1px solid var(--line);
  border-left:3px solid var(--accent);border-radius:0 12px 12px 0}
.ledebox.wk{margin:0 0 32px;padding:24px 26px;border-radius:0 14px 14px 0}
.ledebox .k{font-family:var(--font-mono);font-size:10.5px;letter-spacing:.2em;color:var(--accent);margin-bottom:9px}
.ledebox p{font-size:15.5px;line-height:1.88;color:var(--text)}

/* ── Category pills (daily) ── */
.pills{display:flex;gap:8px;flex-wrap:wrap;margin:26px 0 8px}
.pill{display:inline-flex;align-items:center;gap:8px;background:var(--bg-elev);border:1px solid var(--line);
  border-radius:30px;padding:7px 14px;font-size:13px;color:var(--text-dim);transition:all .15s}
.pill:hover{border-color:var(--c);color:var(--text)}
.pill .dot{width:8px;height:8px;border-radius:2px;background:var(--c)}
.pill .n{font-family:var(--font-mono);font-size:11px;color:var(--text-faint)}

/* ── Switch (weekly) ── */
.switch{display:flex;gap:8px;flex-wrap:wrap;margin:24px 0 26px}
.switch a{font-family:var(--font-mono);font-size:13px;padding:7px 15px;border-radius:30px;background:var(--bg-elev);
  border:1px solid var(--line);color:var(--text-dim);transition:all .15s}
.switch a:hover{color:var(--text)}
.switch a.active{border-color:var(--accent-line);color:var(--accent)}

/* ── Section + cards (daily) ── */
.section{margin-top:40px;scroll-margin-top:90px}
.sec-head{display:flex;align-items:center;gap:11px;margin-bottom:18px;padding-bottom:11px;border-bottom:1px solid var(--line)}
.sec-head .dot{width:10px;height:10px;border-radius:3px;background:var(--c)}
.sec-head h2{font-family:var(--font-cjk);font-weight:700;font-size:17px;color:var(--c)}
.sec-head .cnt{margin-left:auto;font-family:var(--font-mono);font-size:12px;color:var(--text-faint)}
.cards{display:flex;flex-direction:column;gap:12px}
.card{position:relative;background:var(--bg-elev);border:1px solid var(--line);border-radius:14px;
  padding:18px 20px 16px 22px;overflow:hidden;transition:border-color .15s}
.card:hover{border-color:var(--c)}
.card .rule{position:absolute;left:0;top:0;bottom:0;width:3px;background:var(--c)}
.card .crow{display:flex;gap:16px;align-items:flex-start}
.card .cmain{flex:1;min-width:0}
.card .chead{display:flex;align-items:flex-start;gap:12px}
.card .title{flex:1;min-width:0;display:inline-flex;align-items:center;gap:7px;font-family:var(--font-cjk);
  font-weight:700;font-size:16px;line-height:1.4;color:var(--text);transition:color .15s}
.card .title.mono{font-family:var(--font-mono)}
.card .title:hover{color:var(--c)}
.badges{display:flex;gap:6px;flex-shrink:0;align-items:center}
.badge-star{display:inline-flex;align-items:center;gap:4px;font-family:var(--font-mono);font-size:11px;font-weight:600;
  color:var(--c-oss);background:color-mix(in srgb,var(--c-oss) 14%,transparent);
  border:1px solid color-mix(in srgb,var(--c-oss) 26%,transparent);padding:2px 9px;border-radius:20px}
.badge-sig{font-family:var(--font-mono);font-size:10px;font-weight:600;letter-spacing:.04em;padding:3px 9px;
  border-radius:20px;color:var(--sc);background:color-mix(in srgb,var(--sc) 15%,transparent)}
.desc{margin-top:9px;font-size:14px;line-height:1.78;color:var(--text);opacity:.88}
.meta{margin-top:11px;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.meta .src{font-family:var(--font-mono);font-size:11px;color:var(--text-faint);background:var(--bg-elev2);padding:2px 9px;border-radius:6px}
.meta .why{font-size:12.5px;color:var(--text-dim);font-style:italic}
.thumb{flex-shrink:0;width:120px;height:90px;border-radius:10px;overflow:hidden;position:relative;
  background:linear-gradient(135deg,var(--bg-elev2),color-mix(in srgb,var(--c) 24%,var(--bg-elev2)))}
.thumb img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.thumb .ph{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--text-faint);opacity:.55}
.endmark{margin-top:48px;text-align:center;font-family:var(--font-mono);font-size:12px;color:var(--text-faint);letter-spacing:.2em}

/* ── Weekly day timeline ── */
.subhead{display:flex;align-items:baseline;gap:12px;margin-bottom:18px}
.subhead h2{font-family:var(--font-cjk);font-weight:700;font-size:16px}
.subhead .en{font-family:var(--font-mono);font-size:11px;letter-spacing:.18em;color:var(--text-faint)}
.daytl{position:relative;padding-left:28px}
.daytl .rail{position:absolute;left:5px;top:12px;bottom:12px;width:1px;background:var(--line)}
.day-row{position:relative;display:flex;gap:20px;padding:16px 18px;margin-bottom:10px;background:var(--bg-elev);
  border:1px solid var(--line);border-radius:14px;cursor:pointer;align-items:flex-start;transition:all .15s}
.day-row:hover{border-color:var(--accent-line);transform:translateX(2px)}
.day-row .pt{position:absolute;left:-25px;top:24px;width:11px;height:11px;border-radius:50%;background:var(--accent);border:3px solid var(--bg)}
.day-row .d{flex-shrink:0;width:66px}
.day-row .d .dt{font-family:var(--font-mono);font-size:17px;font-weight:600;color:var(--text)}
.day-row .d .dw{font-size:11px;color:var(--text-faint);margin-top:2px}
.day-row .d .cn{margin-top:8px;font-family:var(--font-mono);font-size:10.5px;color:var(--accent)}
.day-row .sn{flex:1;font-size:14px;line-height:1.75;color:var(--text-dim);padding-top:1px}

/* ── Footer ── */
.footer{position:relative;z-index:1;border-top:1px solid var(--line);margin-top:40px}
.footer-in{max-width:1120px;margin:0 auto;padding:28px;display:flex;align-items:center;justify-content:space-between;
  flex-wrap:wrap;gap:14px;font-family:var(--font-mono);font-size:12px;color:var(--text-faint)}
.footer-in a{color:var(--text-dim);transition:color .15s}
.footer-in a:hover{color:var(--accent)}
.footer-in .r{display:flex;align-items:center;gap:18px}

/* ── Responsive ── */
@media (max-width:860px){
  .hero{grid-template-columns:1fr;gap:32px}
  .week-grid{grid-template-columns:repeat(2,1fr)}
}
@media (max-width:620px){
  .nav-in,.main,.footer-in{padding-left:18px;padding-right:18px}
  .nav-links{gap:0}.nav-link{padding:8px 8px;font-size:13px}
  .live{display:none}
  .bigdate{font-size:44px}.phead h1{font-size:38px}
  .week-grid{grid-template-columns:1fr 1fr}
  .card .crow{flex-direction:column}.thumb{width:100%;height:150px}
}
"""


# ---------------------------------------------------------------------------
# Theme scripts (plain strings — braces are literal, never .format()ed)
# ---------------------------------------------------------------------------

THEME_INIT = (
    "<script>(function(){try{var t=localStorage.getItem('ainews_theme');"
    "if(t==='light'||t==='dark'){document.documentElement.setAttribute('data-theme',t);}}"
    "catch(e){}})();</script>"
)

THEME_TOGGLE = (
    "<script>(function(){var b=document.getElementById('themeToggle');if(!b)return;"
    "function cur(){var d=document.documentElement.getAttribute('data-theme');"
    "if(d)return d;return (window.matchMedia&&window.matchMedia('(prefers-color-scheme: light)').matches)?'light':'dark';}"
    "b.addEventListener('click',function(){var t=cur()==='dark'?'light':'dark';"
    "document.documentElement.setAttribute('data-theme',t);try{localStorage.setItem('ainews_theme',t);}catch(e){}});})();</script>"
)

FONTS_LINK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?'
    'family=Space+Grotesk:wght@400;500;600;700&'
    'family=JetBrains+Mono:wght@400;500;700&'
    'family=Noto+Sans+HK:wght@300;400;500;700;900&display=swap" rel="stylesheet">'
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_domain(url):
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        return re.sub(r"^www\.", "", domain)
    except Exception:
        return ""


def format_stars(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def weekday_index(date_str):
    """Return isoweekday-1 (0=Mon .. 6=Sun) from YYYY-MM-DD."""
    return datetime.strptime(date_str, "%Y-%m-%d").isoweekday() - 1


def weekday_full(date_str):
    return WEEKDAY_FULL[weekday_index(date_str)]


def date_short(date_str):
    return date_str[5:].replace("-", ".")


def week_key(iso_year, iso_week):
    return f"{iso_year}-W{iso_week:02d}"


def weekly_filename(iso_year, iso_week):
    return f"weekly-{iso_year}-W{iso_week:02d}.html"


def render_masthead(active, latest_date, latest_week_file):
    """active in {home, daily, weekly}."""
    latest_href = f"{latest_date}.html" if latest_date else "index.html"
    week_href = latest_week_file if latest_week_file else "index.html"
    a_home = " active" if active == "home" else ""
    a_daily = " active" if active == "daily" else ""
    a_weekly = " active" if active == "weekly" else ""
    return (
        '<header class="nav"><div class="nav-in">'
        '<a class="brand" href="index.html">'
        f'<span class="brand-mark">{ICON_LOGO}</span>'
        '<span><span class="brand-name"><b>AI</b>新聞檔案</span>'
        '<span class="brand-tag" style="display:block">DAILY&nbsp;AI&nbsp;INTELLIGENCE</span></span></a>'
        '<nav class="nav-links">'
        f'<a class="nav-link{a_home}" href="index.html">主頁</a>'
        f'<a class="nav-link{a_daily}" href="{latest_href}">最新一日</a>'
        f'<a class="nav-link{a_weekly}" href="{week_href}">週報</a>'
        '</nav>'
        '<div class="nav-right">'
        f'<span class="live"><span class="live-dot"></span><span>每日更新 · {latest_date}</span></span>'
        '<a class="icon-link" href="https://github.com/fafafung/ai-news" target="_blank" '
        f'rel="noopener" title="GitHub">{ICON_GITHUB}</a>'
        f'<button class="icon-btn" id="themeToggle" title="切換主題" type="button">{ICON_THEME}</button>'
        '</div></div></header>'
    )


def page_shell(title, body_html, active, latest_date, latest_week_file):
    """Assemble a full HTML document (no str.format on script/CSS)."""
    head = (
        '<!DOCTYPE html>\n<html lang="zh-HK">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f'<title>{title}</title>\n'
        f'{FONTS_LINK}\n'
        '<style>' + CSS + '</style>\n'
        + THEME_INIT +
        '\n</head>\n<body>\n'
    )
    masthead = render_masthead(active, latest_date, latest_week_file)
    footer = (
        '<footer class="footer"><div class="footer-in">'
        '<span>AI 新聞檔案 · 每日由 AI 自動生成</span>'
        '<span class="r"><span>curated by Fafa</span>'
        '<a href="https://github.com/fafafung/ai-news" target="_blank" rel="noopener">GitHub ↗</a>'
        '</span></div></footer>\n'
    )
    return (
        head
        + '<div class="glow"></div>\n'
        + masthead + '\n'
        + body_html + '\n'
        + footer
        + THEME_TOGGLE
        + '\n</body>\n</html>\n'
    )


def load_index_data():
    if os.path.exists(INDEX_DATA):
        with open(INDEX_DATA, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"entries": []}


def save_index_data(data):
    with open(INDEX_DATA, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def latest_week_file_from(entries):
    """Newest weekly page filename from entries (for nav)."""
    best = None
    for e in entries:
        iy, iw = e.get("iso_year"), e.get("iso_week")
        if iy and iw:
            if best is None or (iy, iw) > best:
                best = (iy, iw)
    return weekly_filename(*best) if best else ""


# ---------------------------------------------------------------------------
# Card / item rendering (daily)
# ---------------------------------------------------------------------------

def render_item(item):
    category = item.get("category", "general")
    title = item.get("title", "Untitled")
    description = item.get("description", "") or item.get("why", "")
    why = item.get("why", "")
    link = item.get("link", "")
    stars = item.get("stars", 0) or 0
    signal = item.get("signal", "")
    image = item.get("image", "")
    source_domain = item.get("source_domain", "") or extract_domain(link)

    color = CATEGORY_VAR.get(category, "var(--c-tech)")
    is_mono = category == "github"

    badges = []
    if stars:
        badges.append(
            f'<span class="badge-star">{ICON_STAR}{format_stars(stars)}</span>'
        )
    if signal in SIGNAL_LABELS:
        slabel, scolor = SIGNAL_LABELS[signal]
        badges.append(
            f'<span class="badge-sig" style="--sc:{scolor}">{slabel}</span>'
        )
    badges_html = f'<div class="badges">{"".join(badges)}</div>' if badges else ""

    meta = []
    if source_domain:
        meta.append(f'<span class="src">{source_domain}</span>')
    if why and item.get("description"):
        meta.append(f'<span class="why">{why}</span>')
    meta_html = f'<div class="meta">{"".join(meta)}</div>' if meta else ""

    # Thumbnail: news/research always get a slot; github only if an image exists.
    thumb_html = ""
    if image or category != "github":
        img = f'<img src="{image}" alt="">' if image else ""
        thumb_html = (
            f'<div class="thumb" style="--c:{color}">{img}'
            f'<span class="ph">{ICON_IMAGE}</span></div>'
        )

    title_cls = "title mono" if is_mono else "title"
    return (
        f'<article class="card" style="--c:{color}">'
        '<span class="rule"></span>'
        '<div class="crow"><div class="cmain">'
        '<div class="chead">'
        f'<a class="{title_cls}" href="{link}" target="_blank" rel="noopener">'
        f'{title}{ICON_EXTERNAL}</a>{badges_html}</div>'
        f'<p class="desc">{description}</p>{meta_html}'
        f'</div>{thumb_html}</div></article>'
    )


def render_section(category, items):
    if not items:
        return ""
    label = CATEGORY_LABELS.get(category, category.capitalize())
    color = CATEGORY_VAR.get(category, "var(--c-tech)")
    cards = "".join(render_item(it) for it in items)
    return (
        f'<section class="section" id="cat-{category}" style="--c:{color}">'
        '<div class="sec-head"><span class="dot"></span>'
        f'<h2>{label}</h2><span class="cnt">{len(items)} 條</span></div>'
        f'<div class="cards">{cards}</div></section>'
    )


# ---------------------------------------------------------------------------
# Daily page generation
# ---------------------------------------------------------------------------

def generate_daily(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    date_str = data["date"]
    dow = data.get("dow", "")
    items = data.get("items", [])
    summary = data.get("summary", "")
    hero_image = data.get("hero_image", "")

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    iso_year, iso_week, _ = dt.isocalendar()
    wd_full = weekday_full(date_str)

    for item in items:
        if not item.get("source_domain"):
            item["source_domain"] = extract_domain(item.get("link", ""))

    grouped = OrderedDict((cat, []) for cat in CATEGORY_ORDER)
    for item in items:
        cat = item.get("category", "general")
        grouped.setdefault(cat, []).append(item)

    title = f"AI 新聞 · {date_str}"
    total = len(items)

    # ── Body ──
    parts = ['<main class="main narrow">']
    parts.append(f'<a class="back" href="index.html">{ICON_BACK}返回主頁</a>')
    parts.append(
        '<header class="phead">'
        f'<div class="k">每日簡報 · {wd_full}</div>'
        f'<h1>{date_str}</h1>'
        '<div class="row">'
        f'<span><b>{total}</b> 條新聞</span><span class="sep">/</span>'
        f'<span><span class="t">{sum(1 for c in grouped.values() if c)}</span> 個分類</span>'
        '</div></header>'
    )
    if summary:
        parts.append(
            '<div class="ledebox"><div class="k">編輯導讀</div>'
            f'<p>{summary}</p></div>'
        )

    # Category jump pills
    pill_html = ['<div class="pills">']
    for cat in CATEGORY_ORDER:
        n = len(grouped.get(cat, []))
        if not n:
            continue
        color = CATEGORY_VAR[cat]
        pill_html.append(
            f'<a class="pill" href="#cat-{cat}" style="--c:{color}">'
            f'<span class="dot"></span>{CATEGORY_LABELS[cat]}'
            f'<span class="n">{n}</span></a>'
        )
    pill_html.append('</div>')
    parts.append("".join(pill_html))

    for cat in CATEGORY_ORDER:
        parts.append(render_section(cat, grouped.get(cat, [])))
    for cat, cat_items in grouped.items():
        if cat not in CATEGORY_ORDER and cat_items:
            parts.append(render_section(cat, cat_items))

    parts.append('<div class="endmark">— 完 —</div>')
    parts.append('</main>')
    body = "\n".join(parts)

    # ── Persist index_data first (so nav "latest" is correct) ──
    index_data = load_index_data()
    truncated_summary = summary[:140] + "…" if len(summary) > 140 else summary

    first_item_snippet = ""
    if items:
        ft = items[0].get("title", "")
        fd = items[0].get("description", "") or items[0].get("why", "")
        if fd:
            s = f"{ft}: {fd}"
            first_item_snippet = s[:110] + "…" if len(s) > 110 else s

    cat_counts = {cat: len(grouped.get(cat, [])) for cat in CATEGORY_ORDER
                  if grouped.get(cat)}
    headlines = [{"title": it.get("title", ""),
                  "category": it.get("category", "general")}
                 for it in items[:4]]

    entry = {
        "date": date_str, "dow": dow, "title": title, "item_count": total,
        "iso_year": iso_year, "iso_week": iso_week,
        "summary": truncated_summary, "first_item_snippet": first_item_snippet,
        "cat_counts": cat_counts, "headlines": headlines,
    }
    if hero_image:
        entry["hero_image"] = hero_image

    found = False
    for i, e in enumerate(index_data["entries"]):
        if e.get("date") == date_str:
            e.update(entry)
            found = True
            break
    if not found:
        index_data["entries"].append(entry)
    index_data["entries"].sort(key=lambda e: e.get("date", ""), reverse=True)
    save_index_data(index_data)

    latest_date = index_data["entries"][0]["date"] if index_data["entries"] else date_str
    lwf = latest_week_file_from(index_data["entries"])

    full_html = page_shell(title, body, "daily", latest_date, lwf)
    daily_path = os.path.join(BASE_DIR, f"{date_str}.html")
    with open(daily_path, "w", encoding="utf-8") as f:
        f.write(full_html)

    print(f"✅ Generated daily page: {daily_path}")
    print(f"📝 Updated {INDEX_DATA}")
    generate_index()
    print(f"📋 Regenerated {INDEX_HTML}")
    return daily_path


# ---------------------------------------------------------------------------
# Index page generation
# ---------------------------------------------------------------------------

def generate_index():
    index_data = load_index_data()
    entries = index_data.get("entries", [])
    week_summaries = index_data.get("week_summaries", {})

    # Group weeks
    weeks = {}
    for e in entries:
        key = (e.get("iso_year", 0), e.get("iso_week", 0))
        if key != (0, 0):
            weeks.setdefault(key, {"entries": [], "total": 0})
            weeks[key]["entries"].append(e)
            weeks[key]["total"] += e.get("item_count", 0)
    sorted_weeks = sorted(weeks.keys(), reverse=True)
    max_news = max((w["total"] for w in weeks.values()), default=1) or 1

    title = "AI 新聞檔案"
    total_days = len(entries)
    total_items = sum(e.get("item_count", 0) for e in entries)
    latest_date = entries[0]["date"] if entries else ""
    lwf = latest_week_file_from(entries)

    parts = ['<main class="main">']

    # ── Hero ──
    if entries:
        f0 = entries[0]
        fdate = f0.get("date", "")
        fcount = f0.get("item_count", 0)
        fsummary = f0.get("summary", "") or f0.get("first_item_snippet", "")
        fwd = weekday_full(fdate) if fdate else ""
        headlines = f0.get("headlines", [])
        cat_counts = f0.get("cat_counts", {})
        hero_image = f0.get("hero_image", "")
        hl_title = headlines[0]["title"] if headlines else "今日精選"

        hl_rows = ""
        for h in headlines:
            color = CATEGORY_VAR.get(h.get("category", "general"), "var(--c-tech)")
            hl_rows += (
                f'<a class="hl-row" href="{fdate}.html" style="--c:{color}">'
                f'<span class="dot"></span><span class="t">{h.get("title","")}</span></a>'
            )

        cat_stat_html = ""
        if cat_counts:
            cells = ""
            for cat in CATEGORY_ORDER:
                if cat in cat_counts:
                    color = CATEGORY_VAR[cat]
                    cells += (
                        f'<div class="catstat" style="--c:{color}">'
                        f'<span class="n">{cat_counts[cat]}</span>'
                        f'<span class="l">{CATEGORY_SHORT[cat]}</span></div>'
                    )
            cat_stat_html = f'<div class="catstats">{cells}</div>'

        hero_img_html = f'<img src="{hero_image}" alt="">' if hero_image else ""

        parts.append(
            '<section class="hero"><div>'
            '<div class="kicker"><span class="k">今日精選</span>'
            '<span class="ln"></span><span class="en">TODAY\'S BRIEFING</span></div>'
            f'<h1 class="bigdate">{fdate}</h1>'
            f'<div class="dmeta"><span>{fwd}</span><span class="sep">/</span>'
            f'<span><b>{fcount}</b> 條新聞</span></div>'
            f'<p class="lede">{fsummary}</p>'
            f'<a class="btn" href="{fdate}.html">閱讀今日全文{ICON_ARROW}</a>'
            '</div>'
            '<div class="panel">'
            '<div class="panel-hl">'
            f'{hero_img_html}<span class="ph">{ICON_IMAGE}</span>'
            f'<span class="cap"><span class="k">今日焦點</span>'
            f'<span class="t">{hl_title}</span></span></div>'
            '<div class="panel-lbl">今日頭條 · HEADLINES</div>'
            f'{hl_rows}{cat_stat_html}'
            '</div></section>'
        )

    # ── Weekly grid ──
    if sorted_weeks:
        cards = ""
        for (iy, iw) in sorted_weeks:
            info = weeks[(iy, iw)]
            wdays = len(info["entries"])
            wtotal = info["total"]
            try:
                mon = date.fromisocalendar(iy, iw, 1)
                sun = mon + timedelta(days=6)
                rng = f"{mon.strftime('%m.%d')} — {sun.strftime('%m.%d')}"
            except (ValueError, TypeError):
                rng = ""
            pct = round(wtotal / max_news * 100)
            cards += (
                f'<a class="week-card" href="{weekly_filename(iy, iw)}">'
                '<div class="top"><span class="wk">WEEK</span>'
                f'<span class="num">{iw:02d}</span></div>'
                f'<div class="rng">{rng}</div>'
                f'<div class="bar"><i style="width:{pct}%"></i></div>'
                f'<div class="st"><span><b>{wdays}</b> 天</span>'
                f'<span><b>{wtotal}</b> 條</span></div></a>'
            )
        parts.append(
            '<section class="block"><div class="sec-title"><h2>週報</h2>'
            '<span class="en">WEEKLY DIGEST</span></div>'
            f'<div class="week-grid">{cards}</div></section>'
        )

    # ── Archive timeline ──
    if entries:
        rows = ""
        for (iy, iw) in sorted_weeks:
            try:
                mon = date.fromisocalendar(iy, iw, 1)
                sun = mon + timedelta(days=6)
                rng = f"{mon.strftime('%m.%d')} — {sun.strftime('%m.%d')}"
            except (ValueError, TypeError):
                rng = ""
            info = weeks[(iy, iw)]
            rows += (
                f'<a class="arch-week" href="{weekly_filename(iy, iw)}">'
                '<span class="pt"></span>'
                f'<span class="lbl">第{iw:02d}週</span>'
                f'<span class="meta">{rng} · {info["total"]} 條</span>'
                '<span class="fill"></span></a>'
            )
            for e in sorted(info["entries"], key=lambda x: x.get("date", ""), reverse=True):
                d = e.get("date", "")
                rows += (
                    f'<a class="arch-day" href="{d}.html"><span class="pt"></span>'
                    f'<div class="d"><div class="dt">{date_short(d)}</div>'
                    f'<div class="dw">{weekday_full(d)}</div></div>'
                    f'<span class="cnt">{e.get("item_count", 0)} 條</span>'
                    f'<p class="sn">{e.get("summary","") or e.get("first_item_snippet","")}</p></a>'
                )
        parts.append(
            '<section class="block tl"><div class="sec-title"><h2>歷史記錄</h2>'
            '<span class="en">ARCHIVE</span>'
            f'<span class="stat">{total_days} 天 · {total_items} 條 · {len(sorted_weeks)} 週</span></div>'
            f'<div class="timeline"><div class="rail"></div>{rows}</div></section>'
        )
    else:
        parts.append('<p style="padding:60px 0;color:var(--text-dim)">暫無記錄</p>')

    parts.append('</main>')
    body = "\n".join(parts)

    full_html = page_shell(title, body, "home", latest_date, lwf)
    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(full_html)
    return INDEX_HTML


# ---------------------------------------------------------------------------
# Weekly page generation
# ---------------------------------------------------------------------------

def generate_weekly(summaries_path=None):
    index_data = load_index_data()
    entries = index_data.get("entries", [])
    if not entries:
        print("⚠️  No entries in index_data.json. Nothing to do.")
        return

    # Merge & persist optional week summaries
    week_summaries = index_data.get("week_summaries", {})
    if summaries_path and os.path.exists(summaries_path):
        with open(summaries_path, "r", encoding="utf-8") as f:
            incoming = json.load(f)
        week_summaries.update(incoming)
        index_data["week_summaries"] = week_summaries
        save_index_data(index_data)
        print(f"📝 Merged {len(incoming)} week summary entrie(s) into {INDEX_DATA}")

    # Group by ISO week
    weeks = {}
    for e in entries:
        iy, iw = e.get("iso_year"), e.get("iso_week")
        if iy is None or iw is None:
            try:
                dt = datetime.strptime(e["date"], "%Y-%m-%d")
                iy, iw, _ = dt.isocalendar()
            except (ValueError, KeyError):
                continue
        weeks.setdefault((iy, iw), []).append(e)

    sorted_weeks = sorted(weeks.keys(), reverse=True)
    latest_date = entries[0]["date"]
    lwf = latest_week_file_from(entries)

    for (iy, iw) in sorted_weeks:
        wk_entries = sorted(weeks[(iy, iw)], key=lambda x: x.get("date", ""), reverse=True)
        try:
            mon = date.fromisocalendar(iy, iw, 1)
            sun = mon + timedelta(days=6)
            rng = f"{mon.strftime('%m.%d')} — {sun.strftime('%m.%d')}"
        except (ValueError, TypeError):
            rng = ""
        total_items = sum(e.get("item_count", 0) for e in wk_entries)
        total_days = len(wk_entries)
        title = f"AI 新聞 · 第{iw:02d}週 ({iy})"
        summary = week_summaries.get(week_key(iy, iw),
                                     "（本週總結將由新聞 agent 自動生成）")

        # Switcher with active highlight
        sw_links = ""
        for (jy, jw) in sorted_weeks:
            cls = "active" if (jy, jw) == (iy, iw) else ""
            sw_links += (f'<a class="{cls}" '
                         f'href="{weekly_filename(jy, jw)}">第{jw:02d}週</a>')
        sw_html = f'<div class="switch">{sw_links}</div>'

        day_rows = ""
        for e in wk_entries:
            d = e.get("date", "")
            snippet = e.get("summary", "") or e.get("first_item_snippet", "")
            day_rows += (
                f'<a class="day-row" href="{d}.html"><span class="pt"></span>'
                f'<div class="d"><div class="dt">{date_short(d)}</div>'
                f'<div class="dw">{weekday_full(d)}</div>'
                f'<div class="cn">{e.get("item_count", 0)} 條</div></div>'
                f'<p class="sn">{snippet}</p></a>'
            )

        body = (
            '<main class="main wide">'
            f'<a class="back" href="index.html">{ICON_BACK}返回主頁</a>'
            '<header class="phead"><div class="k">週報 · WEEKLY DIGEST</div>'
            f'<div class="wkh1"><h1>第{iw:02d}週</h1><span class="yr">{iy}</span></div>'
            '<div class="row">'
            f'<span>{rng}</span><span class="sep">/</span>'
            f'<span><span class="t">{total_days}</span> 天</span>'
            f'<span><b>{total_items}</b> 條</span></div></header>'
            f'{sw_html}'
            '<div class="ledebox wk"><div class="k">本週總結 · WEEKLY SUMMARY</div>'
            f'<p>{summary}</p></div>'
            '<div class="subhead"><h2>每日記錄</h2><span class="en">DAY BY DAY</span></div>'
            f'<div class="daytl"><div class="rail"></div>{day_rows}</div>'
            '</main>'
        )

        full_html = page_shell(title, body, "weekly", latest_date, lwf)
        path = os.path.join(BASE_DIR, weekly_filename(iy, iw))
        with open(path, "w", encoding="utf-8") as f:
            f.write(full_html)
        print(f"✅ Generated weekly page: {path}")

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
        summaries_path = sys.argv[2] if len(sys.argv) >= 3 else None
        generate_weekly(summaries_path)

    elif mode == "index":
        generate_index()
        print(f"📋 Regenerated {INDEX_HTML}")

    else:
        print(f"❌ Unknown mode: {mode}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
