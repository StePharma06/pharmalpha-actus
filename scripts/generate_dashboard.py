#!/usr/bin/env python3
"""
Pharm'Actus - Dashboard analytics (hebdomadaire)
Fetch Brevo API stats → genere HTML dashboard (2 periodes) + envoie par email

Usage:
  BREVO_API_KEY=xkeysib-... python scripts/generate_dashboard.py

Output:
  dashboard.html (a la racine, publie sur https://actus.pharmalpha.fr/dashboard.html)
  Email envoye a stephen.pharmacien@gmail.com
"""

import json
import os
import re
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PARIS_TZ = ZoneInfo("Europe/Paris")

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
DASHBOARD_HTML = ROOT_DIR / "dashboard.html"
INDEX_HTML = ROOT_DIR / "index.html"

BREVO_LIST_ID = 5
BREVO_API_BASE = "https://api.brevo.com/v3"
WEEK_DAYS = 7
CUMUL_START_DATE = "2026-01-01"  # Avant le lancement de Pharm'Actus

DASHBOARD_URL = "https://actus.pharmalpha.fr/dashboard.html"
EMAIL_RECIPIENT = "stephen.pharmacien@gmail.com"
SENDER_EMAIL = "actus@pharmalpha.fr"
SENDER_NAME = "Pharm'Actus Dashboard"


def brevo_api(endpoint, api_key, method="GET", payload=None):
    """Call Brevo API."""
    url = f"{BREVO_API_BASE}{endpoint}"
    headers = {"api-key": api_key, "Accept": "application/json"}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, headers=headers, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        print(f"  [API-ERR] {endpoint}: {e.code} {e.reason}")
        try:
            print(f"    body: {e.read().decode()[:300]}")
        except Exception:
            pass
        return {}
    except Exception as e:
        print(f"  [API-ERR] {endpoint}: {e}")
        return {}


def get_subscribers_count(api_key):
    """Get current subscriber count from the list."""
    data = brevo_api(f"/contacts/lists/{BREVO_LIST_ID}", api_key)
    return data.get("totalSubscribers", 0)


def get_aggregated_report(api_key, start_date, end_date):
    """Get aggregated Brevo report for a period."""
    endpoint = f"/smtp/statistics/aggregatedReport?startDate={start_date}&endDate={end_date}"
    return brevo_api(endpoint, api_key)


def get_events(api_key, event_type, start_date, end_date, limit=2500):
    """Fetch all events of a given type over a period with pagination."""
    all_events = []
    offset = 0
    while True:
        endpoint = (
            f"/smtp/statistics/events"
            f"?event={event_type}"
            f"&startDate={start_date}"
            f"&endDate={end_date}"
            f"&limit={limit}"
            f"&offset={offset}"
        )
        data = brevo_api(endpoint, api_key)
        events = data.get("events", [])
        if not events:
            break
        all_events.extend(events)
        if len(events) < limit:
            break
        offset += limit
        if offset > 50000:  # safety
            break
    return all_events


def _iterate_chunks(start_date, end_date, chunk_days=89):
    """Yield (start, end) string pairs chunking a period by max N days (Brevo limit = 90)."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=chunk_days), end)
        yield cur.strftime("%Y-%m-%d"), chunk_end.strftime("%Y-%m-%d")
        cur = chunk_end + timedelta(days=1)


def get_stats_for_period(api_key, start_date, end_date):
    """Fetch all stats over period (chunks by 90j to respect Brevo API limit)."""
    delivered = opens = unique_opens = clicks = unique_clicks = 0
    article_clicks = defaultdict(int)
    article_unique_clickers = defaultdict(set)

    for chunk_start, chunk_end in _iterate_chunks(start_date, end_date):
        report = get_aggregated_report(api_key, chunk_start, chunk_end)
        delivered += report.get("delivered", 0)
        opens += report.get("opens", 0)
        unique_opens += report.get("uniqueOpens", 0)
        clicks += report.get("clicks", 0)
        unique_clicks += report.get("uniqueClicks", 0)

        # Per-article clicks for this chunk
        click_events = get_events(api_key, "clicks", chunk_start, chunk_end)
        for event in click_events:
            url = event.get("link", "") or event.get("url", "")
            email = event.get("email", "")
            aid = extract_article_id_from_url(url)
            if aid:
                article_clicks[aid] += 1
                if email:
                    article_unique_clickers[aid].add(email)

    top_articles = sorted(
        article_clicks.keys(),
        key=lambda k: (len(article_unique_clickers[k]), article_clicks[k]),
        reverse=True,
    )[:15]

    return {
        "delivered": delivered,
        "opens": opens,
        "unique_opens": unique_opens,
        "clicks": clicks,
        "unique_clicks": unique_clicks,
        "open_rate": (unique_opens / delivered * 100) if delivered else 0,
        "click_rate": (unique_clicks / delivered * 100) if delivered else 0,
        "ctor": (unique_clicks / unique_opens * 100) if unique_opens else 0,
        "article_clicks": article_clicks,
        "article_unique_clickers": article_unique_clickers,
        "top_articles": top_articles,
        "start_date": start_date,
        "end_date": end_date,
    }


def load_articles_map():
    """Load article metadata from index.html to map IDs → title/date/category."""
    articles = {}
    if not INDEX_HTML.exists():
        return articles
    html = INDEX_HTML.read_text(encoding="utf-8")
    pattern = re.compile(
        r'id:\s*"([^"]+)"[\s\S]*?date:\s*"([^"]+)"[\s\S]*?categorie:\s*"([^"]+)"[\s\S]*?titre:\s*"((?:[^"\\]|\\.)*)"'
    )
    for match in pattern.finditer(html):
        aid, date, cat, titre = match.groups()
        titre = titre.replace('\\"', '"').replace("\\n", " ")
        if aid not in articles:
            articles[aid] = {"titre": titre, "date": date, "categorie": cat}
    return articles


def extract_article_id_from_url(url):
    """Extract article ID from an email URL."""
    match = re.search(r'/articles/([a-z0-9_]+)\.html', url)
    if match:
        return match.group(1)
    match = re.search(r'[?&]a=([a-z0-9_]+)', url)
    if match:
        return match.group(1)
    return None


BADGE_COLORS = {
    "pharma_france": ("#fff7ed", "#f97316", "Pharma France"),
    "pharma_monde": ("#eff6ff", "#2563eb", "Pharma Monde"),
    "sante": ("#f0fdf4", "#16a34a", "Sante"),
    "bonne_nouvelle": ("#f0fdfa", "#0d9488", "Bonne nouvelle"),
    "avenir_pharma": ("#eef2ff", "#4f46e5", "Avenir pharma"),
    "lsv": ("#f5f3ff", "#7c3aed", "Le Saviez-Vous"),
}


def build_dashboard(api_key):
    """Main function: fetch stats for 2 periods + build/send dashboard."""
    today = datetime.now(PARIS_TZ)
    end_date = today.strftime("%Y-%m-%d")
    week_start = (today - timedelta(days=WEEK_DAYS)).strftime("%Y-%m-%d")

    print(f"=== Dashboard Pharm'Actus ===")
    print(f"  Semaine : {week_start} -> {end_date}")
    print(f"  Cumule  : {CUMUL_START_DATE} -> {end_date}")

    print("\n[1/5] Abonnes Brevo...")
    subscribers = get_subscribers_count(api_key)
    print(f"  {subscribers} abonnes dans la liste")

    print("\n[2/5] Stats semaine passee (7j)...")
    week_stats = get_stats_for_period(api_key, week_start, end_date)
    print(f"  {week_stats['delivered']} delivres, {week_stats['unique_opens']} ouvertures, {week_stats['unique_clicks']} clics")

    print("\n[3/5] Stats cumulees (depuis debut)...")
    cumul_stats = get_stats_for_period(api_key, CUMUL_START_DATE, end_date)
    print(f"  {cumul_stats['delivered']} delivres, {cumul_stats['unique_opens']} ouvertures, {cumul_stats['unique_clicks']} clics")

    print("\n[4/5] Mapping articles...")
    articles_map = load_articles_map()
    print(f"  {len(articles_map)} articles connus")

    print("\n[5/5] Generation HTML...")
    html = render_dashboard(
        subscribers=subscribers,
        week_stats=week_stats,
        cumul_stats=cumul_stats,
        articles_map=articles_map,
    )
    DASHBOARD_HTML.write_text(html, encoding="utf-8")
    print(f"  Fichier : {DASHBOARD_HTML}")

    # Envoi email
    print("\n[Email] Envoi du dashboard par email...")
    email_html = render_email_dashboard(
        subscribers=subscribers,
        week_stats=week_stats,
        cumul_stats=cumul_stats,
        articles_map=articles_map,
    )
    send_dashboard_email(api_key, email_html)

    print(f"\n=== Termine ===")
    print(f"URL en ligne : {DASHBOARD_URL}")


def format_article_row(i, aid, articles_map, article_clicks, article_unique_clickers):
    """Generate an HTML row for a top article."""
    meta = articles_map.get(aid, {})
    titre = meta.get("titre", aid)
    date = meta.get("date", "-")
    cat = meta.get("categorie", "")
    bg, fg, label = BADGE_COLORS.get(cat, ("#f0f0f0", "#666", cat or "-"))
    unique = len(article_unique_clickers[aid])
    total = article_clicks[aid]
    return f'''<tr>
      <td class="rank">{i}</td>
      <td class="date">{date}</td>
      <td><span class="badge" style="background:{bg};color:{fg};">{label}</span></td>
      <td class="title">{titre}</td>
      <td class="num"><strong>{unique}</strong></td>
      <td class="num">{total}</td>
    </tr>'''


def build_top_table_html(stats, articles_map):
    """Generate the top articles table rows."""
    top_articles = stats["top_articles"]
    if not top_articles:
        return '<tr><td colspan="6" style="text-align:center;color:#888;padding:24px;font-size:13px;">Aucun clic identifi&eacute; sur un article sp&eacute;cifique.<br><small>Les liens per-article ont &eacute;t&eacute; activ&eacute;s le 2026-04-11. Les donn&eacute;es commencent a s\'accumuler.</small></td></tr>'
    rows = ""
    for i, aid in enumerate(top_articles, 1):
        rows += format_article_row(i, aid, articles_map, stats["article_clicks"], stats["article_unique_clickers"])
    return rows


def render_dashboard(**ctx):
    """Render the full HTML dashboard."""
    subs = ctx["subscribers"]
    week = ctx["week_stats"]
    cumul = ctx["cumul_stats"]
    articles_map = ctx["articles_map"]

    week_top_rows = build_top_table_html(week, articles_map)
    cumul_top_rows = build_top_table_html(cumul, articles_map)

    updated_at = datetime.now(PARIS_TZ).strftime("%Y-%m-%d %H:%M")

    return f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>Dashboard Pharm'Actus</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: -apple-system, 'Segoe UI', system-ui, sans-serif;
  background: #f4f4f5;
  color: #1a1a1a;
  padding: 32px 24px;
  max-width: 1200px;
  margin: 0 auto;
  line-height: 1.5;
}}
header {{ margin-bottom: 32px; }}
h1 {{ font-size: 28px; margin-bottom: 6px; }}
h1 span {{ color: #f97316; }}
.subtitle {{ color: #888; font-size: 13px; }}

.stats-grid {{
  display: grid;
  grid-template-columns: 2fr 1fr 1fr;
  gap: 12px;
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  margin-bottom: 24px;
}}
.stats-grid h3 {{ font-size: 11px; text-transform: uppercase; color: #888; font-weight: 700; letter-spacing: 0.4px; padding-bottom: 12px; border-bottom: 2px solid #f0f0f0; }}
.stats-grid .head-label {{ grid-column: 1; }}
.stats-grid .head-week {{ text-align: right; color: #f97316; }}
.stats-grid .head-cumul {{ text-align: right; color: #0d9488; }}
.stats-row {{ display: contents; }}
.stats-row > div {{
  padding: 14px 0;
  border-bottom: 1px solid #f0f0f0;
}}
.stats-row:last-child > div {{ border-bottom: none; }}
.stats-row .label {{ font-weight: 500; color: #555; font-size: 14px; }}
.stats-row .label small {{ display: block; color: #aaa; font-size: 11px; margin-top: 2px; font-weight: 400; }}
.stats-row .value {{ text-align: right; font-size: 20px; font-weight: 700; font-variant-numeric: tabular-nums; }}
.stats-row .value.week {{ color: #f97316; }}
.stats-row .value.cumul {{ color: #0d9488; }}
.stats-row .value small {{ display: block; color: #aaa; font-size: 11px; font-weight: 400; margin-top: 2px; }}

.card {{
  background: #fff;
  padding: 24px 28px;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  margin-bottom: 24px;
}}
.card h2 {{ font-size: 18px; margin-bottom: 4px; }}
.card h2 .tag {{ font-size: 11px; background: #fff7ed; color: #f97316; padding: 3px 10px; border-radius: 100px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.3px; margin-left: 8px; vertical-align: middle; }}
.card h2 .tag.cumul {{ background: #f0fdfa; color: #0d9488; }}
.card .hint {{ color: #888; font-size: 12px; margin-bottom: 16px; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{
  text-align: left;
  padding: 10px 12px;
  border-bottom: 2px solid #f0f0f0;
  color: #666;
  font-weight: 600;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}}
td {{ padding: 12px; border-bottom: 1px solid #f0f0f0; font-size: 14px; vertical-align: middle; }}
td.rank {{ width: 36px; color: #aaa; font-weight: 700; }}
td.date {{ width: 100px; color: #888; font-size: 12px; font-family: monospace; }}
td.title {{ font-weight: 500; }}
td.num {{ width: 80px; text-align: right; font-variant-numeric: tabular-nums; }}
.badge {{
  display: inline-block;
  padding: 3px 10px;
  border-radius: 100px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  white-space: nowrap;
}}
tr:last-child td {{ border-bottom: none; }}
tr:hover td {{ background: #fafafa; }}
.footer {{ color: #aaa; font-size: 11px; text-align: center; margin-top: 40px; padding-top: 24px; border-top: 1px solid #e5e5e5; }}
@media (max-width: 700px) {{
  .stats-grid {{ grid-template-columns: 1.5fr 1fr 1fr; gap: 8px; padding: 16px; }}
  .stats-row .value {{ font-size: 16px; }}
  td.title {{ font-size: 13px; }}
}}
</style>
</head>
<body>
<header>
  <h1>Dashboard <span>Pharm'Actus</span></h1>
  <p class="subtitle">Semaine du {week["start_date"]} au {week["end_date"]} &mdash; Cumul depuis le {cumul["start_date"]} &mdash; MAJ {updated_at}</p>
</header>

<div class="stats-grid">
  <h3 class="head-label">Metrique</h3>
  <h3 class="head-week">Semaine pass&eacute;e</h3>
  <h3 class="head-cumul">Cumul&eacute;</h3>

  <div class="stats-row">
    <div class="label">Abonn&eacute;s<small>a ce jour</small></div>
    <div class="value week">&mdash;</div>
    <div class="value cumul">{subs}</div>
  </div>
  <div class="stats-row">
    <div class="label">Emails d&eacute;livr&eacute;s</div>
    <div class="value week">{week["delivered"]}</div>
    <div class="value cumul">{cumul["delivered"]}</div>
  </div>
  <div class="stats-row">
    <div class="label">Taux d'ouverture<small>uniques / d&eacute;livr&eacute;s</small></div>
    <div class="value week">{week["open_rate"]:.1f}%<small>{week["unique_opens"]} uniques &middot; {week["opens"]} total</small></div>
    <div class="value cumul">{cumul["open_rate"]:.1f}%<small>{cumul["unique_opens"]} uniques &middot; {cumul["opens"]} total</small></div>
  </div>
  <div class="stats-row">
    <div class="label">Taux de clic<small>uniques / d&eacute;livr&eacute;s</small></div>
    <div class="value week">{week["click_rate"]:.1f}%<small>{week["unique_clicks"]} uniques &middot; {week["clicks"]} total</small></div>
    <div class="value cumul">{cumul["click_rate"]:.1f}%<small>{cumul["unique_clicks"]} uniques &middot; {cumul["clicks"]} total</small></div>
  </div>
  <div class="stats-row">
    <div class="label">CTOR<small>clic / ouverture</small></div>
    <div class="value week">{week["ctor"]:.1f}%</div>
    <div class="value cumul">{cumul["ctor"]:.1f}%</div>
  </div>
</div>

<div class="card">
  <h2>Top articles &mdash; <span class="tag">Semaine pass&eacute;e</span></h2>
  <p class="hint">Articles les plus cliqu&eacute;s par des abonn&eacute;s distincts cette semaine.</p>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Date</th>
        <th>Cat&eacute;gorie</th>
        <th>Article</th>
        <th>Lecteurs</th>
        <th>Clics</th>
      </tr>
    </thead>
    <tbody>
{week_top_rows}
    </tbody>
  </table>
</div>

<div class="card">
  <h2>Top articles &mdash; <span class="tag cumul">Cumul&eacute;</span></h2>
  <p class="hint">Articles les plus cliqu&eacute;s depuis le d&eacute;but (hors clics historiques sur homepage avant le 2026-04-11).</p>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Date</th>
        <th>Cat&eacute;gorie</th>
        <th>Article</th>
        <th>Lecteurs</th>
        <th>Clics</th>
      </tr>
    </thead>
    <tbody>
{cumul_top_rows}
    </tbody>
  </table>
</div>

<p class="footer">Dashboard priv&eacute; Pharm'Actus &mdash; Donn&eacute;es via Brevo API &mdash; Meta noindex actif</p>
</body>
</html>
'''


def render_email_dashboard(**ctx):
    """Render a simplified HTML dashboard for email (inline styles, table layouts)."""
    subs = ctx["subscribers"]
    week = ctx["week_stats"]
    cumul = ctx["cumul_stats"]
    articles_map = ctx["articles_map"]

    updated_at = datetime.now(PARIS_TZ).strftime("%Y-%m-%d %H:%M")

    def format_stat_row(label, week_val, cumul_val, sublabel=""):
        sub = f'<br><span style="font-size:10px;color:#aaa;font-weight:400;">{sublabel}</span>' if sublabel else ""
        return f'''<tr>
          <td style="padding:14px 12px;border-bottom:1px solid #f0f0f0;font-size:13px;color:#555;font-weight:500;">{label}{sub}</td>
          <td style="padding:14px 12px;border-bottom:1px solid #f0f0f0;text-align:right;font-size:18px;font-weight:700;color:#f97316;font-variant-numeric:tabular-nums;">{week_val}</td>
          <td style="padding:14px 12px;border-bottom:1px solid #f0f0f0;text-align:right;font-size:18px;font-weight:700;color:#0d9488;font-variant-numeric:tabular-nums;">{cumul_val}</td>
        </tr>'''

    stats_rows = ""
    stats_rows += format_stat_row("Abonnes", "&mdash;", str(subs))
    stats_rows += format_stat_row("Emails delivres", str(week["delivered"]), str(cumul["delivered"]))
    stats_rows += format_stat_row(
        "Taux d'ouverture",
        f'{week["open_rate"]:.1f}%',
        f'{cumul["open_rate"]:.1f}%',
        f'{week["unique_opens"]} / {cumul["unique_opens"]} uniques'
    )
    stats_rows += format_stat_row(
        "Taux de clic",
        f'{week["click_rate"]:.1f}%',
        f'{cumul["click_rate"]:.1f}%',
        f'{week["unique_clicks"]} / {cumul["unique_clicks"]} uniques'
    )
    stats_rows += format_stat_row("CTOR (clic/ouverture)", f'{week["ctor"]:.1f}%', f'{cumul["ctor"]:.1f}%')

    # Top articles de la semaine (simplifie)
    top_html = ""
    week_top = week["top_articles"][:10]
    if not week_top:
        top_html = '<p style="margin:0;padding:24px;text-align:center;color:#888;font-size:13px;">Pas encore de clics identifi&eacute;s par article.<br><small>Les liens per-article sont activ&eacute;s depuis le 2026-04-11.</small></p>'
    else:
        rows = ""
        for i, aid in enumerate(week_top, 1):
            meta = articles_map.get(aid, {})
            titre = meta.get("titre", aid)
            date = meta.get("date", "-")
            cat = meta.get("categorie", "")
            bg, fg, label = BADGE_COLORS.get(cat, ("#f0f0f0", "#666", cat or "-"))
            unique = len(week["article_unique_clickers"][aid])
            total = week["article_clicks"][aid]
            rows += f'''<tr>
              <td style="padding:10px 8px;border-bottom:1px solid #f0f0f0;font-size:11px;color:#aaa;font-weight:700;width:24px;">{i}</td>
              <td style="padding:10px 8px;border-bottom:1px solid #f0f0f0;font-size:11px;color:#888;font-family:monospace;white-space:nowrap;">{date}</td>
              <td style="padding:10px 8px;border-bottom:1px solid #f0f0f0;font-size:13px;">
                <span style="display:inline-block;background:{bg};color:{fg};font-size:9px;font-weight:700;padding:2px 8px;border-radius:100px;text-transform:uppercase;letter-spacing:0.3px;">{label}</span><br>
                <span style="font-weight:500;color:#1a1a1a;">{titre}</span>
              </td>
              <td style="padding:10px 8px;border-bottom:1px solid #f0f0f0;text-align:right;font-size:14px;font-weight:700;width:50px;">{unique}</td>
            </tr>'''
        top_html = f'''<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
          <thead>
            <tr>
              <th style="padding:8px;text-align:left;font-size:10px;color:#666;text-transform:uppercase;letter-spacing:0.3px;border-bottom:2px solid #f0f0f0;">#</th>
              <th style="padding:8px;text-align:left;font-size:10px;color:#666;text-transform:uppercase;letter-spacing:0.3px;border-bottom:2px solid #f0f0f0;">Date</th>
              <th style="padding:8px;text-align:left;font-size:10px;color:#666;text-transform:uppercase;letter-spacing:0.3px;border-bottom:2px solid #f0f0f0;">Article</th>
              <th style="padding:8px;text-align:right;font-size:10px;color:#666;text-transform:uppercase;letter-spacing:0.3px;border-bottom:2px solid #f0f0f0;">Lecteurs</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>'''

    return f'''<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;">
<tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.06);">
  <tr><td style="background:#ffffff;padding:24px 28px 16px;border-bottom:2px solid #f97316;">
    <div style="font-size:24px;font-weight:800;color:#1a1a1a;letter-spacing:-0.5px;">Dashboard <span style="color:#f97316;">Pharm'Actus</span></div>
    <div style="font-size:12px;color:#888;margin-top:4px;">Rapport hebdomadaire &mdash; MAJ {updated_at}</div>
  </td></tr>

  <tr><td style="padding:24px 28px 8px;">
    <h2 style="margin:0 0 12px;font-size:16px;color:#1a1a1a;">Vue d'ensemble</h2>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
      <thead>
        <tr>
          <th style="padding:10px 12px;text-align:left;font-size:10px;color:#666;text-transform:uppercase;letter-spacing:0.3px;border-bottom:2px solid #f0f0f0;font-weight:700;">M&eacute;trique</th>
          <th style="padding:10px 12px;text-align:right;font-size:10px;color:#f97316;text-transform:uppercase;letter-spacing:0.3px;border-bottom:2px solid #f0f0f0;font-weight:700;">Semaine</th>
          <th style="padding:10px 12px;text-align:right;font-size:10px;color:#0d9488;text-transform:uppercase;letter-spacing:0.3px;border-bottom:2px solid #f0f0f0;font-weight:700;">Cumul&eacute;</th>
        </tr>
      </thead>
      <tbody>
        {stats_rows}
      </tbody>
    </table>
  </td></tr>

  <tr><td style="padding:24px 28px 8px;">
    <h2 style="margin:0 0 12px;font-size:16px;color:#1a1a1a;">Top 10 articles &mdash; semaine pass&eacute;e</h2>
    {top_html}
  </td></tr>

  <tr><td style="padding:24px 28px 28px;text-align:center;">
    <a href="{DASHBOARD_URL}" style="display:inline-block;background:#f97316;color:#ffffff;font-size:14px;font-weight:700;padding:12px 28px;border-radius:8px;text-decoration:none;letter-spacing:0.3px;">Voir le dashboard complet &rarr;</a>
    <p style="margin:12px 0 0;font-size:11px;color:#aaa;">Acc&egrave;s direct : <a href="{DASHBOARD_URL}" style="color:#888;">{DASHBOARD_URL}</a></p>
  </td></tr>

  <tr><td style="padding:16px 28px 24px;border-top:1px solid #f0f0f0;text-align:center;">
    <p style="margin:0;font-size:11px;color:#aaa;">Dashboard priv&eacute; &mdash; Envoy&eacute; automatiquement chaque lundi matin &mdash; Donn&eacute;es Brevo API</p>
  </td></tr>
</table>
</td></tr></table>
</body></html>'''


def send_dashboard_email(api_key, html_content):
    """Send the dashboard by email to Stephen."""
    today = datetime.now(PARIS_TZ).strftime("%Y-%m-%d")
    payload = {
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "to": [{"email": EMAIL_RECIPIENT, "name": "Stephen"}],
        "subject": f"Dashboard Pharm'Actus - Semaine du {today}",
        "htmlContent": html_content,
    }
    result = brevo_api("/smtp/email", api_key, method="POST", payload=payload)
    if result.get("messageId"):
        print(f"  [EMAIL] Envoye a {EMAIL_RECIPIENT} (messageId: {result['messageId']})")
    else:
        print(f"  [EMAIL] Echec: {result}")


def main():
    api_key = os.environ.get("BREVO_API_KEY", "")
    if not api_key:
        print("[ERROR] BREVO_API_KEY non definie dans l'environnement")
        print("Usage PowerShell :")
        print('  $env:BREVO_API_KEY="xkeysib-..."')
        print("  python scripts/generate_dashboard.py")
        return

    build_dashboard(api_key)


if __name__ == "__main__":
    main()
