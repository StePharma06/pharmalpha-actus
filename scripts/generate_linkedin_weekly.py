#!/usr/bin/env python3
"""
Pharm'Actus - Generateur LinkedIn hebdomadaire
Chaque mercredi matin, prepare un post LinkedIn pret a publier :
1. Selectionne le meilleur article de la semaine (priorite Business > Pharma Monde > Avenir)
2. Claude genere le post LinkedIn dans le style Stephen (sans lien pour eviter la penalisation algo)
3. Claude genere le commentaire a publier juste apres (avec le lien)
4. Envoie le tout par email a Stephen, pret a copier-coller

Usage:
  ANTHROPIC_API_KEY=sk-... BREVO_API_KEY=xkeysib-... python scripts/generate_linkedin_weekly.py
"""

import json
import os
import re
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

PARIS_TZ = ZoneInfo("Europe/Paris")

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent
ARTICLES_JSON = ROOT_DIR / "articles.json"
INDEX_HTML = ROOT_DIR / "index.html"

LOOKBACK_DAYS = 7
SITE_URL = "https://actus.pharmalpha.fr"
SUBSCRIBE_URL = "https://actus.pharmalpha.fr"

BREVO_API_BASE = "https://api.brevo.com/v3"
SENDER_EMAIL = "actus@pharmalpha.fr"
SENDER_NAME = "Pharm'Actus LinkedIn"
EMAIL_RECIPIENT = "stephen.pharmacien@gmail.com"

FALLBACK_MODEL = "claude-haiku-4-5-20251001"


def claude_create(client, **kwargs):
    """Call Claude API with retry + fallback to Haiku if Sonnet overloaded."""
    original_model = kwargs.get("model", "")
    for attempt in range(2):
        try:
            return client.messages.create(**kwargs)
        except anthropic.APIStatusError as e:
            if e.status_code in (429, 529) and attempt < 1:
                print(f"  [RETRY] Claude {e.status_code}, attente 30s...")
                time.sleep(30)
            elif e.status_code in (429, 529):
                print(f"  [FALLBACK] bascule sur Haiku...")
                kwargs["model"] = FALLBACK_MODEL
                try:
                    return client.messages.create(**kwargs)
                except Exception:
                    raise e
            else:
                raise


def load_articles():
    """Load articles from articles.json (preferred) or parse index.html (fallback)."""
    if ARTICLES_JSON.exists():
        with open(ARTICLES_JSON, encoding="utf-8") as f:
            data = json.load(f)
            return data.get("articles", [])

    # Fallback: parse index.html
    if not INDEX_HTML.exists():
        return []
    html = INDEX_HTML.read_text(encoding="utf-8")
    match = re.search(r"const ARTICLES = \[([\s\S]*?)\];", html)
    if not match:
        return []
    block = match.group(1)
    articles = []
    depth = 0
    start = None
    in_str = False
    esc = False
    for i, c in enumerate(block):
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start is not None:
                entry = block[start:i + 1]
                d = {}
                for field in ("id", "date", "categorie", "titre", "resume", "full_text", "source", "source_url", "badge_label", "image_url"):
                    m = re.search(rf'{field}:\s*"((?:[^"\\]|\\.)*)"', entry)
                    if m:
                        d[field] = m.group(1).replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
                tm = re.search(r'tags:\s*\[([^\]]*)\]', entry)
                if tm:
                    d["tags"] = [t.strip().strip('"') for t in re.findall(r'"([^"]*)"', tm.group(1))]
                if d.get("id"):
                    articles.append(d)
                start = None
    return articles


def pick_best_article(articles):
    """Pick the best article from the last 7 days for the LinkedIn post."""
    today = datetime.now(PARIS_TZ)
    cutoff = today - timedelta(days=LOOKBACK_DAYS)

    def article_date(a):
        try:
            return datetime.strptime(a.get("date", "1970-01-01"), "%Y-%m-%d").replace(tzinfo=PARIS_TZ)
        except Exception:
            return datetime(1970, 1, 1, tzinfo=PARIS_TZ)

    recent = [a for a in articles if article_date(a) >= cutoff]
    if not recent:
        print("  [WARN] Aucun article recent, prend les plus recents disponibles")
        recent = sorted(articles, key=article_date, reverse=True)[:10]

    # Scoring by category (differentiating + impact)
    def score(a):
        cat = a.get("categorie", "")
        base = {
            "business_officine": 100,
            "pharma_monde": 60,
            "avenir_pharma": 50,
            "bonne_nouvelle": 30,
            "pharma_france": 20,
            "sante": 15,
            "lsv": 5,
        }.get(cat, 10)
        # Bonus for recent articles (today > yesterday > etc.)
        days_ago = (today - article_date(a)).days
        recency_bonus = max(0, 10 - days_ago)
        return base + recency_bonus

    recent.sort(key=score, reverse=True)
    return recent[0] if recent else None


def generate_linkedin_content(article):
    """Use Claude to generate the LinkedIn post + comment in Stephen's style."""
    client = anthropic.Anthropic()

    article_url = f"{SITE_URL}/articles/{article.get('id', '')}.html"
    categorie = article.get("categorie", "")
    badge = article.get("badge_label", "")

    prompt = f"""Tu es Stephen ROBERT, pharmacien consultant chez Pharm'Alpha, influenceur LinkedIn (24K+ abonnes, 1 086 posts).

Tu rediges le post LinkedIn hebdomadaire qui promeut Pharm'Actus (ta newsletter quotidienne pharma).

=== TON STYLE LINKEDIN (tres specifique) ===
- Hook punchy en ouverture (1-2 lignes) : chiffre choc, question rhetorique, ou phrase polemique
- Tutoiement systematique
- Phrases COURTES. Une idee par phrase.
- Paragraphes tres courts (1-2 lignes max)
- Ton decontracte mais expert
- Questions rhetoriques pour interpeller ("Et devine quoi ?", "Ca te rappelle quelque chose ?")
- Un peu d'humour/ironie quand le sujet s'y prete
- Zero "bonjour LinkedIn", zero "chers confreres"
- Storytelling : tu parles a un pote pharmacien, pas a un auditoire
- Jargon metier assume (officine, marge, ROSP, LFSS, DP, DCI, AMM, missions, etc.)
- Public : 34% pharmaciens titulaires/adjoints/preparateurs, 13% commerciaux pharma, 9% industrie
- Emoji bullets ou check marks : 👉, ✅, 🟢, 🔴, ⚠️, 💡 (avec parcimonie, 3-4 max)

=== REGLES CRITIQUES ===
1. **AUCUN LIEN** dans le post principal (LinkedIn penalise l'algo avec liens externes). Le lien sera dans le premier commentaire.
2. **CTA subtil** vers le premier commentaire : "Article complet en commentaire 👇" ou "Detail en commentaire" ou "Toute l'analyse dans le 1er comm".
3. **Hashtags** : 2 ou 3 MAX a la fin. Choisir parmi : #pharmacie #officine #pharmacien #pharmaactus + 1 topical optionnel selon le sujet (#lfss #rosp #business #innovation #vaccination etc.)
4. **Longueur** : 1000-1500 caracteres (le sweet spot LinkedIn). Pas plus.
5. **Signature** : termine avant les hashtags par "— Stephen" ou rien du tout (optionnel)

=== ARTICLE SOURCE ===
Titre : {article.get("titre", "")}
Categorie : {badge}
Date : {article.get("date", "")}
Resume : {article.get("resume", "")}

Full text :
{article.get("full_text", "")[:3000]}

=== INSTRUCTIONS ===

Genere 2 textes :

1. **POST** (le texte principal du post LinkedIn, SANS lien)
   - Hook punchy en 1-2 lignes
   - Developpement : le chiffre choc ou l'insight cle, traite en 3-5 paragraphes courts
   - Un angle personnel de Stephen (consultant business, expert officine)
   - Teaser vers le commentaire : "Article complet dans le 1er comm 👇" ou equivalent
   - CTA subtil vers l'abonnement Pharm'Actus : "Pour ce genre d'analyse chaque matin, l'inscription est dans le 1er comm aussi" ou equivalent
   - 2-3 hashtags a la fin

2. **COMMENT** (le texte du premier commentaire, AVEC les liens)
   - Intro courte (1 ligne) style "Pour aller plus loin :"
   - Lien vers l'article : {article_url}
   - Intro (1 ligne) style "Abonne-toi a Pharm'Actus (c'est gratuit, 5 actus pharma + 1 business + 1 histoire, chaque matin) :"
   - Lien d'abonnement : {SUBSCRIBE_URL}

Retourne au format JSON UNIQUEMENT :
{{
  "post": "...",
  "comment": "...",
  "hook": "...",
  "angle": "...(1 phrase expliquant l'angle choisi pour le post)"
}}"""

    response = claude_create(
        client,
        model="claude-sonnet-4-6",
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        print("  [ERROR] Pas de JSON valide")
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError as e:
        print(f"  [ERROR] JSON parse: {e}")
        return None


def send_linkedin_email(content, article):
    """Send the LinkedIn post + comment by email, formatted for easy copy-paste."""
    api_key = os.environ.get("BREVO_API_KEY", "")
    if not api_key:
        print("  [SKIP] BREVO_API_KEY non definie, email non envoye")
        return

    today = datetime.now(PARIS_TZ).strftime("%d/%m/%Y")
    post_text = content.get("post", "")
    comment_text = content.get("comment", "")
    angle = content.get("angle", "")

    article_url = f"{SITE_URL}/articles/{article.get('id', '')}.html"
    article_titre = article.get("titre", "")
    article_cat = article.get("badge_label", "")
    post_chars = len(post_text)

    # Escape HTML in the post/comment for display (but keep as selectable text)
    def esc_html(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    post_escaped = esc_html(post_text)
    comment_escaped = esc_html(comment_text)

    html = f'''<!DOCTYPE html>
<html lang="fr">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;color:#1a1a1a;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f5;">
<tr><td align="center" style="padding:24px 16px;">
<table role="presentation" width="680" cellpadding="0" cellspacing="0" style="max-width:680px;width:100%;background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.06);">

  <tr><td style="background:#0a66c2;padding:24px 28px;">
    <div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#cfe4ff;margin-bottom:6px;">📱 LinkedIn &mdash; Mercredi {today}</div>
    <div style="font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.5px;">Ton post LinkedIn de la semaine</div>
    <div style="font-size:13px;color:#cfe4ff;margin-top:6px;">Pret a publier &mdash; 20 secondes, 2 copier-coller</div>
  </td></tr>

  <tr><td style="padding:20px 28px 16px;background:#f0f9ff;border-bottom:1px solid #dbeafe;">
    <div style="font-size:11px;text-transform:uppercase;color:#0a66c2;font-weight:700;letter-spacing:0.5px;margin-bottom:6px;">Article source</div>
    <div style="font-size:14px;font-weight:600;color:#1a1a1a;margin-bottom:4px;">{esc_html(article_titre)}</div>
    <div style="font-size:12px;color:#666;">{esc_html(article_cat)} &middot; {article.get("date", "")}</div>
    <div style="font-size:12px;color:#888;margin-top:6px;font-style:italic;">Angle choisi : {esc_html(angle)}</div>
  </td></tr>

  <tr><td style="padding:24px 28px 0;">
    <div style="display:flex;align-items:center;margin-bottom:12px;">
      <div style="background:#0a66c2;color:#fff;width:28px;height:28px;border-radius:50%;display:inline-block;text-align:center;line-height:28px;font-weight:700;font-size:14px;margin-right:12px;">1</div>
      <h2 style="font-size:16px;font-weight:800;color:#1a1a1a;margin:0;display:inline-block;vertical-align:middle;">Copie ce post sur LinkedIn</h2>
    </div>
    <p style="margin:0 0 12px;font-size:12px;color:#666;">⚠ Ne modifie rien, surtout pas de lien. Le post est optimise pour l'algo.</p>
  </td></tr>

  <tr><td style="padding:0 28px;">
    <div style="background:#f8fafc;border:2px solid #0a66c2;border-radius:12px;padding:20px 22px;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;font-size:14px;color:#1a1a1a;line-height:1.6;white-space:pre-wrap;word-wrap:break-word;user-select:all;">{post_escaped}</div>
    <div style="text-align:right;font-size:11px;color:#aaa;margin-top:4px;">{post_chars} caracteres</div>
  </td></tr>

  <tr><td style="padding:28px 28px 0;">
    <div style="display:flex;align-items:center;margin-bottom:12px;">
      <div style="background:#0a66c2;color:#fff;width:28px;height:28px;border-radius:50%;display:inline-block;text-align:center;line-height:28px;font-weight:700;font-size:14px;margin-right:12px;">2</div>
      <h2 style="font-size:16px;font-weight:800;color:#1a1a1a;margin:0;display:inline-block;vertical-align:middle;">Immediatement apres : commente avec ce texte</h2>
    </div>
    <p style="margin:0 0 12px;font-size:12px;color:#666;">💡 Poste le commentaire dans les 30 secondes suivant la publication &mdash; meilleur pour l'engagement.</p>
  </td></tr>

  <tr><td style="padding:0 28px 24px;">
    <div style="background:#fff7ed;border:2px solid #f97316;border-radius:12px;padding:20px 22px;font-family:'Segoe UI',system-ui,-apple-system,sans-serif;font-size:14px;color:#1a1a1a;line-height:1.6;white-space:pre-wrap;word-wrap:break-word;user-select:all;">{comment_escaped}</div>
  </td></tr>

  <tr><td style="padding:0 28px 28px;text-align:center;">
    <a href="{article_url}" style="display:inline-block;background:#0a66c2;color:#ffffff;font-size:13px;font-weight:700;padding:10px 24px;border-radius:100px;text-decoration:none;">Voir l'article sur Pharm'Actus &rarr;</a>
  </td></tr>

  <tr><td style="padding:20px 28px 24px;background:#f8f8f8;border-top:1px solid #e5e5e5;">
    <p style="margin:0 0 8px;font-size:12px;color:#666;line-height:1.5;">
      <strong>Rappel strategique</strong> : les posts avec lien externe dans le corps principal sont penalises par l'algo LinkedIn. Mettre le lien dans le premier commentaire preserve la portee organique tout en dirigeant les interesses vers l'article.
    </p>
    <p style="margin:0;font-size:11px;color:#aaa;">
      Genere automatiquement chaque mercredi matin. Si le ton ne te plait pas, dis-le moi &mdash; j'ajusterai le prompt.
    </p>
  </td></tr>

</table>
</td></tr></table>
</body></html>'''

    payload = {
        "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
        "to": [{"email": EMAIL_RECIPIENT, "name": "Stephen"}],
        "subject": f"📱 Post LinkedIn pret a publier - {today}",
        "htmlContent": html,
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{BREVO_API_BASE}/smtp/email",
            data=data,
            headers={"api-key": api_key, "Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            print(f"  [EMAIL] Envoye a {EMAIL_RECIPIENT} (messageId: {result.get('messageId', '?')})")
    except Exception as e:
        print(f"  [EMAIL-ERR] {e}")


def main():
    print("=== Pharm'Actus - LinkedIn Weekly Post ===")
    print(f"  Date: {datetime.now(PARIS_TZ).strftime('%Y-%m-%d %H:%M')}")

    print("\n[1/3] Chargement des articles...")
    articles = load_articles()
    print(f"  {len(articles)} articles charges")
    if not articles:
        print("  [ERROR] Aucun article disponible. Arret.")
        return

    print("\n[2/3] Selection du meilleur article...")
    best = pick_best_article(articles)
    if not best:
        print("  [ERROR] Aucun article eligible. Arret.")
        return
    print(f"  Article : {best.get('titre', '')[:70]}...")
    print(f"  Categorie : {best.get('badge_label', '')}")
    print(f"  Date : {best.get('date', '')}")

    print("\n[3/3] Generation du post + commentaire via Claude...")
    content = generate_linkedin_content(best)
    if not content:
        print("  [ERROR] Generation echouee. Arret.")
        return
    print(f"  Hook : {content.get('hook', '')[:80]}")
    print(f"  Angle : {content.get('angle', '')[:80]}")
    print(f"  Post : {len(content.get('post', ''))} caracteres")

    print("\n[Email] Envoi du post pret a publier...")
    send_linkedin_email(content, best)

    print("\n=== Termine ===")


if __name__ == "__main__":
    main()
