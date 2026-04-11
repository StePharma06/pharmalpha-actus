#!/usr/bin/env python3
"""
Pharm'Actus - Dashboard analytics
Fetch Brevo API stats + parse article clicks → generate HTML dashboard (local, prive)

Usage:
  BREVO_API_KEY=xkeysib-... python scripts/generate_dashboard.py

Output:
  dashboard/dashboard.html  (gitignore, ne sera pas publie)
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
DASHBOARD_DIR = ROOT_DIR / "dashboard"
DASHBOARD_HTML = DASHBOARD_DIR / "dashboard.html"
INDEX_HTML = ROOT_DIR / "index.html"

BREVO_LIST_ID = 5
BREVO_API_BASE = "https://api.brevo.com/v3"
PERIOD_DAYS = 30


def brevo_api(endpoint, api_key):
    """Call Brevo API."""
    url = f"{BREVO_API_BASE}{endpoint}"
    req = urllib.request.Request(
        url,
        headers={"api-key": api_key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  [API-ERR] {endpoint}: {e.code} {e.reason}")
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
        if offset > 25000:  # safety
            break
    return all_events


def get_daily_report(api_key, start_date, end_date):
    """Get day-by-day Brevo report."""
    endpoint = f"/smtp/statistics/aggregatedReport?startDate={start_date}&endDate={end_date}&days=0"
    return brevo_api(endpoint, api_key)


def load_articles_map():
    """Load article metadata from index.html to map IDs → title/date/category."""
    articles = {}
    if not INDEX_HTML.exists():
        return articles
    html = INDEX_HTML.read_text(encoding="utf-8")
    # Match each article block with id, date, categorie, titre
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
    # URLs look like: https://actus.pharmalpha.fr/articles/actu_2026_04_06_1.html
    match = re.search(r'/articles/([a-z0-9_]+)\.html', url)
    if match:
        return match.group(1)
    # Legacy: https://actus.pharmalpha.fr/?a=actu_XXX
    match = re.search(r'[?&]a=([a-z0-9_]+)', url)
    if match:
        return match.group(1)
    return None


def build_dashboard(api_key):
    """Main function: fetch data + build dashboard HTML."""
    today = datetime.now(PARIS_TZ)
    start = today - timedelta(days=PERIOD_DAYS)
    start_date = start.strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    print(f"=== Dashboard Pharm'Actus ({start_date} → {end_date}) ===")

    print("\n[1/5] Abonnes Brevo...")
    subscribers = get_subscribers_count(api_key)
    print(f"  {subscribers} abonnes dans la liste")

    print("\n[2/5] Rapport agrege Brevo...")
    report = get_aggregated_report(api_key, start_date, end_date)
    delivered = report.get("delivered", 0)
    unique_opens = report.get("uniqueOpens", 0)
    unique_clicks = report.get("uniqueClicks", 0)
    opens = report.get("opens", 0)
    clicks = report.get("clicks", 0)
    print(f"  {delivered} emails delivres, {unique_opens} ouvertures uniques, {unique_clicks} clics uniques")

    print("\n[3/5] Clics detailles (per URL)...")
    click_events = get_events(api_key, "clicks", start_date, end_date)
    print(f"  {len(click_events)} evenements de clic recuperes")

    print("\n[4/5] Mapping articles...")
    articles_map = load_articles_map()
    print(f"  {len(articles_map)} articles connus dans index.html")

    # Aggregate per-article stats
    article_clicks = defaultdict(int)
    article_unique_clickers = defaultdict(set)
    for event in click_events:
        url = event.get("link", "") or event.get("url", "")
        email = event.get("email", "")
        aid = extract_article_id_from_url(url)
        if aid:
            article_clicks[aid] += 1
            if email:
                article_unique_clickers[aid].add(email)

    # Top articles by unique clickers
    top_articles = sorted(
        article_clicks.keys(),
        key=lambda k: (len(article_unique_clickers[k]), article_clicks[k]),
        reverse=True,
    )[:20]

    print(f"  {len(article_clicks)} articles avec au moins 1 clic identifie")

    print("\n[5/5] Generation HTML...")
    html = render_dashboard(
        subscribers=subscribers,
        delivered=delivered,
        opens=opens,
        clicks=clicks,
        unique_opens=unique_opens,
        unique_clicks=unique_clicks,
        top_articles=top_articles,
        article_clicks=article_clicks,
        article_unique_clickers=article_unique_clickers,
        articles_map=articles_map,
        start_date=start_date,
        end_date=end_date,
        period_days=PERIOD_DAYS,
    )

    DASHBOARD_DIR.mkdir(exist_ok=True)
    DASHBOARD_HTML.write_text(html, encoding="utf-8")
    print(f"\n=== Dashboard genere : {DASHBOARD_HTML} ===")
    print(f"Ouvre-le dans ton navigateur : file:///{DASHBOARD_HTML.as_posix()}")


def render_dashboard(**ctx):
    """Render the HTML dashboard."""
    subs = ctx["subscribers"]
    delivered = ctx["delivered"]
    opens = ctx["opens"]
    clicks = ctx["clicks"]
    u_opens = ctx["unique_opens"]
    u_clicks = ctx["unique_clicks"]
    top_articles = ctx["top_articles"]
    article_clicks = ctx["article_clicks"]
    article_unique_clickers = ctx["article_unique_clickers"]
    articles_map = ctx["articles_map"]

    open_rate = (u_opens / delivered * 100) if delivered else 0
    click_rate = (u_clicks / delivered * 100) if delivered else 0
    ctr_on_opens = (u_clicks / u_opens * 100) if u_opens else 0

    badge_colors = {
        "pharma_france": ("#fff7ed", "#f97316", "Pharma France"),
        "pharma_monde": ("#eff6ff", "#2563eb", "Pharma Monde"),
        "sante": ("#f0fdf4", "#16a34a", "Sante"),
        "bonne_nouvelle": ("#f0fdfa", "#0d9488", "La bonne nouvelle"),
        "avenir_pharma": ("#eef2ff", "#4f46e5", "L'avenir de la pharma"),
        "lsv": ("#f5f3ff", "#7c3aed", "Le Saviez-Vous"),
    }

    top_rows = ""
    if not top_articles:
        top_rows = '<tr><td colspan="5" style="text-align:center;color:#888;padding:24px;">Aucun clic identifie sur un article specifique.<br><small>Rappel : avant la mise a jour du 2026-04, tous les clics email pointaient vers la homepage, donc pas de stats per-article avant cette date.</small></td></tr>'
    else:
        for i, aid in enumerate(top_articles, 1):
            meta = articles_map.get(aid, {})
            titre = meta.get("titre", aid)
            date = meta.get("date", "-")
            cat = meta.get("categorie", "")
            bg, fg, label = badge_colors.get(cat, ("#f0f0f0", "#666", cat or "-"))
            unique = len(article_unique_clickers[aid])
            total = article_clicks[aid]
            top_rows += f'''        <tr>
          <td class="rank">{i}</td>
          <td class="date">{date}</td>
          <td><span class="badge" style="background:{bg};color:{fg};">{label}</span></td>
          <td class="title">{titre}</td>
          <td class="num"><strong>{unique}</strong></td>
          <td class="num">{total}</td>
        </tr>
'''

    updated_at = datetime.now(PARIS_TZ).strftime("%Y-%m-%d %H:%M")
    period_days = ctx["period_days"]
    start_date = ctx["start_date"]
    end_date = ctx["end_date"]

    return f'''<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
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
.stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }}
.stat {{
  background: #fff;
  padding: 20px 24px;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}}
.stat-label {{ color: #888; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; font-weight: 600; }}
.stat-value {{ font-size: 32px; font-weight: 700; color: #1a1a1a; line-height: 1.1; }}
.stat-sub {{ color: #f97316; font-size: 11px; margin-top: 6px; font-weight: 600; }}
.card {{
  background: #fff;
  padding: 24px 28px;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  margin-bottom: 24px;
}}
.card h2 {{ font-size: 18px; margin-bottom: 6px; }}
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
</style>
</head>
<body>
<header>
  <h1>Dashboard <span>Pharm'Actus</span></h1>
  <p class="subtitle">{period_days} derniers jours &mdash; du {start_date} au {end_date} &mdash; MAJ {updated_at}</p>
</header>

<div class="stats">
  <div class="stat">
    <div class="stat-label">Abonn&eacute;s</div>
    <div class="stat-value">{subs}</div>
  </div>
  <div class="stat">
    <div class="stat-label">Emails d&eacute;livr&eacute;s</div>
    <div class="stat-value">{delivered}</div>
  </div>
  <div class="stat">
    <div class="stat-label">Taux d'ouverture</div>
    <div class="stat-value">{open_rate:.1f}%</div>
    <div class="stat-sub">{u_opens} uniques &middot; {opens} total</div>
  </div>
  <div class="stat">
    <div class="stat-label">Taux de clic</div>
    <div class="stat-value">{click_rate:.1f}%</div>
    <div class="stat-sub">{u_clicks} uniques &middot; {clicks} total</div>
  </div>
  <div class="stat">
    <div class="stat-label">CTOR (clic/ouverture)</div>
    <div class="stat-value">{ctr_on_opens:.1f}%</div>
    <div class="stat-sub">sur ceux qui ouvrent</div>
  </div>
</div>

<div class="card">
  <h2>Top articles cliqu&eacute;s</h2>
  <p class="hint">Classement par lecteurs uniques (nombre d'abonn&eacute;s distincts ayant cliqu&eacute;). Les clics multiples comptent s&eacute;par&eacute;ment dans la colonne Clics totaux.</p>
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
{top_rows}
    </tbody>
  </table>
</div>

<p class="footer">Dashboard priv&eacute; Pharm'Actus &mdash; Donn&eacute;es via Brevo API &mdash; Ne pas partager publiquement</p>
</body>
</html>
'''


def main():
    api_key = os.environ.get("BREVO_API_KEY", "")
    if not api_key:
        print("[ERROR] BREVO_API_KEY non definie dans l'environnement")
        print("")
        print("Usage PowerShell :")
        print('  $env:BREVO_API_KEY="xkeysib-..."')
        print("  python scripts/generate_dashboard.py")
        print("")
        print("Usage bash :")
        print("  BREVO_API_KEY=xkeysib-... python scripts/generate_dashboard.py")
        return

    build_dashboard(api_key)


if __name__ == "__main__":
    main()
