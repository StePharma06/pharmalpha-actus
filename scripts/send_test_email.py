#!/usr/bin/env python3
"""
Send a test email via Brevo API.
Usage: python send_test_email.py <BREVO_API_KEY> <TO_EMAIL>
"""
import sys, os, json, requests

def build_email_html(articles):
    """Build the daily newsletter HTML from articles list."""
    from datetime import datetime

    today = datetime.now()
    jours = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
    mois = ["","janvier","février","mars","avril","mai","juin",
            "juillet","août","septembre","octobre","novembre","décembre"]
    date_str = f"{jours[today.weekday()]} {today.day} {mois[today.month]} {today.year}"

    actus = [a for a in articles if a["type"] == "actu"][:3]
    lsv = next((a for a in articles if a["type"] == "lsv"), None)

    badge_colors = {
        "pharma_france": ("#fff7ed", "#f97316"),
        "pharma_monde": ("#eff6ff", "#2563eb"),
        "sante": ("#f0fdf4", "#16a34a"),
        "lsv": ("#f5f3ff", "#7c3aed"),
    }

    def actu_block(a, is_first=False):
        bg, fg = badge_colors.get(a.get("categorie",""), ("#fff7ed","#f97316"))
        pad_top = "24px" if is_first else "20px"
        img_url = a.get("image_url", "")
        img_html = ""
        if img_url:
            full_url = f"https://actus.pharmalpha.fr/{img_url}"
            img_html = f'<tr><td style="padding-top:12px;"><img src="{full_url}" alt="" width="536" style="width:100%;max-width:536px;height:auto;border-radius:8px;display:block;" /></td></tr>'
        return f'''
  <tr>
    <td style="padding:{pad_top} 32px 0;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr><td>
          <span style="display:inline-block;background:{bg};color:{fg};font-size:11px;font-weight:700;padding:3px 10px;border-radius:100px;text-transform:uppercase;letter-spacing:0.4px;">{a.get("badge_label","")}</span>
        </td></tr>
        {img_html}
        <tr><td style="padding-top:10px;">
          <a href="https://actus.pharmalpha.fr/" style="font-size:18px;font-weight:700;color:#1a1a1a;text-decoration:none;line-height:1.35;">{a["titre"]}</a>
        </td></tr>
        <tr><td style="padding-top:8px;">
          <p style="margin:0;font-size:14px;color:#555;line-height:1.6;">{a["resume"]}</p>
        </td></tr>
        <tr><td style="padding-top:10px;">
          <span style="font-size:12px;color:#888;">Source : {a.get("source","")}</span>
        </td></tr>
      </table>
    </td>
  </tr>
  <tr><td style="padding:20px 32px 0;"><div style="border-top:1px solid #f0f0f0;"></div></td></tr>'''

    def lsv_block(a):
        return f'''
  <tr><td style="padding:24px 32px 0;"><div style="border-top:2px solid #7c3aed;"></div></td></tr>
  <tr>
    <td style="padding:20px 32px 0;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f5f3ff;border-radius:10px;overflow:hidden;">
        <tr><td style="padding:20px 24px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
            <tr><td>
              <span style="display:inline-block;background:#ede9fe;color:#7c3aed;font-size:11px;font-weight:700;padding:3px 10px;border-radius:100px;text-transform:uppercase;letter-spacing:0.4px;">Le Saviez-Vous</span>
            </td></tr>
            <tr><td style="padding-top:12px;">
              <a href="https://actus.pharmalpha.fr/" style="font-size:18px;font-weight:700;color:#1a1a1a;text-decoration:none;line-height:1.35;">{a["titre"]}</a>
            </td></tr>
            <tr><td style="padding-top:8px;">
              <p style="margin:0;font-size:14px;color:#555;line-height:1.6;">{a["resume"]}</p>
            </td></tr>
          </table>
        </td></tr>
      </table>
    </td>
  </tr>'''

    nb_content = len(actus) + (1 if lsv else 0)
    count_str = f"{len(actus)} actus" + (" + 1 Le Saviez-Vous" if lsv else "")

    articles_html = ""
    for i, a in enumerate(actus):
        articles_html += actu_block(a, is_first=(i == 0))
    if lsv:
        articles_html += lsv_block(lsv)

    return f'''<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;">
<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">{count_str} — {date_str}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;">
<tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.06);">

  <tr>
    <td style="background:#ffffff;padding:28px 32px 16px;text-align:center;border-bottom:2px solid #f97316;">
      <span style="font-size:28px;font-weight:800;color:#f97316;letter-spacing:-0.5px;">PHARM'ACTUS</span><br>
      <span style="font-size:13px;color:#888;letter-spacing:0.3px;">L'actu pharma par un pharmacien, pour les pharmaciens</span>
    </td>
  </tr>

  <tr>
    <td style="background:#fafafa;padding:10px 32px;text-align:center;">
      <span style="color:#1a1a1a;font-size:14px;font-weight:600;">{date_str}</span>
      <span style="color:#888;font-size:14px;"> &mdash; {count_str}</span>
    </td>
  </tr>

  <tr>
    <td style="padding:28px 32px 20px;">
      <p style="margin:0;font-size:15px;color:#333;line-height:1.6;">
        Salut !<br><br>
        Voici ton briefing pharma du jour. {count_str} pour rester au top. Bonne lecture !
      </p>
      <p style="margin:12px 0 0;font-size:13px;color:#999;line-height:1.5;font-style:italic;">
        Astuce : r&eacute;ponds juste &laquo; bien re&ccedil;u &raquo; &agrave; cet email. &Ccedil;a indique &agrave; ta messagerie qu'on se conna&icirc;t, et mes actus atterriront toujours dans ta bo&icirc;te principale.
      </p>
    </td>
  </tr>

  <tr><td style="padding:0 32px;"><div style="border-top:1px solid #e5e5e5;"></div></td></tr>

  {articles_html}

  <tr>
    <td style="padding:28px 32px 0;" align="center">
      <table role="presentation" cellpadding="0" cellspacing="0">
        <tr>
          <td style="background:#f97316;border-radius:8px;">
            <a href="https://actus.pharmalpha.fr/" style="display:inline-block;padding:14px 32px;color:#ffffff;font-size:15px;font-weight:700;text-decoration:none;letter-spacing:0.3px;">
              Lire les articles complets &rarr;
            </a>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <tr><td style="padding:28px 32px 0;">
    <div style="border-top:1px solid #e5e5e5;padding-top:20px;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="vertical-align:top;width:60px;padding-right:16px;">
            <div style="width:52px;height:52px;border-radius:50%;background:#f97316;color:#fff;font-size:22px;font-weight:700;line-height:52px;text-align:center;">S</div>
          </td>
          <td style="vertical-align:top;">
            <p style="margin:0 0 4px;font-size:14px;font-weight:700;color:#1a1a1a;">Stephen ROBERT</p>
            <p style="margin:0;font-size:13px;color:#666;line-height:1.5;">Pharmacien d'officine devenu consultant. Je d&eacute;crypte l'actu pharma chaque matin pour que tu restes dans la boucle, sans y passer des heures.</p>
          </td>
        </tr>
      </table>
    </div>
  </td></tr>
  <tr><td style="padding:20px 32px 28px;">
    <div style="border-top:1px solid #f0f0f0;padding-top:16px;text-align:center;">
      <p style="margin:0 0 8px;font-size:13px;font-weight:700;color:#f97316;">Pharm'Alpha</p>
      <p style="margin:0;font-size:11px;color:#aaa;line-height:1.5;">
        Tu re&ccedil;ois cet email car tu t'es inscrit(e) sur
        <a href="https://actus.pharmalpha.fr/" style="color:#888;">Pharm'Actus</a>.<br>
        <a href="{{{{ unsubscribe }}}}" style="color:#888;">Se d&eacute;sinscrire</a> &bull;
        <a href="https://actus.pharmalpha.fr/" style="color:#888;">Voir en ligne</a>
      </p>
    </div>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>'''


def send_email(api_key, to_email, subject, html_content):
    """Send email via Brevo API."""
    url = "https://api.brevo.com/v3/smtp/email"
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    payload = {
        "sender": {"name": "Pharm'Actus", "email": "actus@pharmalpha.fr"},
        "replyTo": {"email": "stephen.pharmacien@gmail.com", "name": "Pharm'Actus"},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def get_today_articles():
    """Extract today's articles from index.html."""
    import re
    from datetime import datetime

    index_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    m = re.search(r'const ARTICLES = (\[.*?\]);', html, re.DOTALL)
    if not m:
        print("[ERROR] Cannot find ARTICLES in index.html")
        sys.exit(1)

    # Parse JS array as JSON (need to convert JS object syntax to JSON)
    js_array = m.group(1)
    # Add quotes around keys
    js_array = re.sub(r'(\s)(\w+):', r'\1"\2":', js_array)
    # Fix trailing commas
    js_array = re.sub(r',\s*}', '}', js_array)
    js_array = re.sub(r',\s*]', ']', js_array)

    articles = json.loads(js_array)

    today = datetime.now().strftime("%Y-%m-%d")
    today_articles = [a for a in articles if a["date"] == today]

    if not today_articles:
        # Fallback: use latest date
        dates = sorted(set(a["date"] for a in articles), reverse=True)
        latest = dates[0]
        today_articles = [a for a in articles if a["date"] == latest]
        print(f"[INFO] No articles for today, using latest date: {latest}")

    return today_articles


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python send_test_email.py <BREVO_API_KEY> <TO_EMAIL>")
        sys.exit(1)

    api_key = sys.argv[1]
    to_email = sys.argv[2]

    print("Fetching today's articles...")
    articles = get_today_articles()
    actus = [a for a in articles if a["type"] == "actu"]
    lsvs = [a for a in articles if a["type"] == "lsv"]
    print(f"  Found {len(actus)} actus + {len(lsvs)} LSV")

    print("Building email HTML...")
    html = build_email_html(articles)

    from datetime import datetime
    jours = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
    mois = ["","janvier","février","mars","avril","mai","juin",
            "juillet","août","septembre","octobre","novembre","décembre"]
    now = datetime.now()
    date_str = f"{jours[now.weekday()]} {now.day} {mois[now.month]} {now.year}"
    subject = f"Pharm'Actus du {date_str}"

    print(f"Sending to {to_email}...")
    result = send_email(api_key, to_email, subject, html)
    print(f"Sent! Message ID: {result.get('messageId', 'N/A')}")
