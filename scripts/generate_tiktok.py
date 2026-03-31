#!/usr/bin/env python3
"""
Pharm'Actus TikTok - Pipeline video quotidien
Transforme le LSV du jour en video TikTok ~60s et publie a 18h Paris.

Pipeline :
  1. Lire output/latest_lsv.json
  2. Claude API -> script segmente TikTok
  3. DALL-E 3 -> 4 images photorealistes (9:16)
  4. ElevenLabs -> voix off (~60s)
  5. HeyGen -> 2 clips avatar (intro + CTA)
  6. Creatomate -> assemblage video finale
  7. TikTok API -> publication programmee
"""

import base64
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# -- Config ----------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
LSV_INPUT = ROOT_DIR / "output" / "latest_lsv.json"
OUTPUT_DIR = ROOT_DIR / "output" / "tiktok"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY", "")
HEYGEN_AVATAR_IDS = os.environ.get("HEYGEN_AVATAR_IDS", "")
CREATOMATE_API_KEY = os.environ.get("CREATOMATE_API_KEY", "")
TIKTOK_ACCESS_TOKEN = os.environ.get("TIKTOK_ACCESS_TOKEN", "")


def api_request(url, data=None, headers=None, method=None):
    """Generic HTTP request helper. Returns parsed JSON or raw bytes."""
    headers = headers or {}
    if data is not None and isinstance(data, dict):
        data = json.dumps(data).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=300) as resp:
        ct = resp.headers.get("Content-Type", "")
        raw = resp.read()
        if "json" in ct:
            return json.loads(raw)
        return raw


def load_lsv():
    if not LSV_INPUT.exists():
        print("[ERROR] output/latest_lsv.json introuvable")
        sys.exit(1)
    with open(LSV_INPUT, "r", encoding="utf-8") as f:
        lsv = json.load(f)
    titre = lsv.get("titre", "")[:60]
    print(f"[1/7] LSV charge : {titre}...")
    return lsv


SCRIPT_PROMPT = """Tu es le directeur creatif de Pharm'Alpha, chaine TikTok "Le Saviez-Vous" pharma/sante.
Style de reference : HugoDecrypte pour la pharmacie. Dynamique, accessible, passionnant.
Format : 65 secondes minimum. Alternance facecam avatar + animation realiste (style Estherium TikTok).

Voici l'article "Le Saviez-Vous" du jour :

TITRE : {titre}
RESUME : {resume}
TEXTE COMPLET :
{full_text}

Cree un script TikTok de 65+ secondes avec EXACTEMENT cette structure :
1. HOOK anime (5s) : image realiste + accroche choc en voix off, fait surprenant
2. FACECAM INTRO (7s) : avatar Stephen presente le sujet face camera, style HugoDecrypte
3. SEGMENT 1 anime (15s) : le fait principal + contexte, images realistes + voix off
4. FACECAM REBOND (7s) : avatar Stephen reagit, "Mais le plus incroyable c'est que..."
5. SEGMENT 2 anime (12s) : le twist ou developpement surprenant + voix off
6. FACECAM CONCLUSION (15s) : avatar conclut + "Pharmusez vous bien" + CTA (@pharmalpha + actus.pharmalpha.fr) + PHRASE LOOP

REGLE IMPORTANTE - PHRASE LOOP (technique Estherium TikTok) :
La DERNIERE phrase de avatar_conclusion doit se connecter NATURELLEMENT et SEAMLESSLY
a la PREMIERE phrase du hook, pour que quand TikTok relance la video en boucle,
le spectateur ne s'en rende pas compte et continue a regarder.
Exemple : si hook commence par "Le saviez-vous ? L'aspirine est nee..." -> loop phrase finit
par "...la prochaine fois que vous prendrez de l'aspirine, vous y penserez."
Creer une continuite logique ou emotionnelle entre la fin et le debut.

REGLES IMAGES :
- image_prompt en ANGLAIS, style photorealistic editorial photography, shot on Canon EOS R5
- PAS de texte dans les images, PAS de style IA/cartoon/illustration
- Sujets concrets : personnes reelles, lieux, objets photographiables

Reponds UNIQUEMENT en JSON valide :
{{
  "hook": {{
    "voiceover": "Accroche voix off choc, 1-2 phrases max (5s de parole)",
    "screen_text": "Texte affiche a l'ecran (max 10 mots percutants)",
    "image_prompt": "Prompt DALL-E en anglais, photorealistic editorial, Canon EOS R5...",
    "duration": 5
  }},
  "avatar_intro": {{
    "speech": "Stephen face cam : presentation du sujet style HugoDecrypte (7s max)",
    "duration": 7
  }},
  "segment_1": {{
    "voiceover": "Voix off segment 1 : fait principal + contexte (~15s de parole, ~50 mots)",
    "screen_text": "Fait cle affiche (max 12 mots)",
    "image_prompt": "Prompt DALL-E en anglais, photorealistic editorial...",
    "duration": 15
  }},
  "avatar_rebond": {{
    "speech": "Stephen face cam : rebond sur seg1, 'Mais le plus incroyable c'est que...' (7s max)",
    "duration": 7
  }},
  "segment_2": {{
    "voiceover": "Voix off segment 2 : twist / developpement surprenant (~12s de parole, ~40 mots)",
    "screen_text": "Le twist (max 12 mots)",
    "image_prompt": "Prompt DALL-E en anglais, photorealistic editorial...",
    "duration": 12
  }},
  "avatar_conclusion": {{
    "speech": "Stephen face cam : conclusion + 'Pharmusez vous bien' + 'Abonnez-vous @pharmalpha sur TikTok et retrouvez toutes nos actus sur actus.pharmalpha.fr' + phrase loop (15s max)",
    "loop_phrase": "La derniere phrase exacte qui connecte seamlessly au debut du hook",
    "duration": 15
  }},
  "full_voiceover": "Voix off COMPLETE pour les parties animees UNIQUEMENT (hook + segment_1 + segment_2 concatenes). ~32 secondes de parole, ~110 mots. NE PAS inclure les parties avatar.",
  "titre_tiktok": "Titre TikTok accrocheur (max 80 car)",
  "description_tiktok": "Description + hashtags (max 300 car)",
  "hashtags": "#lesaviezvous #pharmalpha #pharmacie #sante",
  "thumbnail_prompt": "Prompt DALL-E thumbnail impactante, close-up dramatique, bold colors, photorealistic, vertical 9:16"
}}"""


def generate_tiktok_script(lsv):
    print("[2/7] Generation du script TikTok via Claude...")

    prompt = SCRIPT_PROMPT.format(
        titre=lsv.get("titre", ""),
        resume=lsv.get("resume", ""),
        full_text=lsv.get("full_text", ""),
    )

    data = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 2000,
        "messages": [{"role": "user", "content": prompt}],
    }
    resp = api_request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    text = resp["content"][0]["text"].strip()
    json_match = re.search(r"\{[\s\S]*\}", text)
    if not json_match:
        print("[ERROR] Claude n'a pas retourne de JSON valide")
        sys.exit(1)

    script = json.loads(json_match.group())
    titre = script.get("titre_tiktok", "")[:50]
    print(f"  Script genere : {titre}...")
    return script


def generate_images(script):
    print("[3/7] Generation des images via DALL-E 3...")

    prompts = [
        ("hook", script.get("hook", {}).get("image_prompt", "")),
        ("segment_1", script.get("segment_1", {}).get("image_prompt", "")),
        ("segment_2", script.get("segment_2", {}).get("image_prompt", "")),
    ]
    prompts = [(k, v) for k, v in prompts if v]

    images = {}
    for label, prompt in prompts:
        if "photorealistic" not in prompt.lower():
            prompt = f"Photorealistic editorial photography, {prompt}, natural lighting, shot on Canon EOS R5, no AI artifacts, no text"

        data = {
            "model": "dall-e-3",
            "prompt": prompt,
            "n": 1,
            "size": "1024x1792",
            "quality": "hd",
            "style": "natural",
        }
        try:
            resp = api_request(
                "https://api.openai.com/v1/images/generations",
                data=data,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            )
            img_url = resp["data"][0]["url"]
            img_path = OUTPUT_DIR / f"{label}.png"
            urllib.request.urlretrieve(img_url, str(img_path))
            images[label] = img_path
            print(f"  {label} : OK")
        except Exception as e:
            print(f"  [WARN] Image {label} echouee : {e}")

    thumb_prompt = script.get("thumbnail_prompt", "")
    if thumb_prompt:
        if "photorealistic" not in thumb_prompt.lower():
            thumb_prompt = f"Photorealistic, {thumb_prompt}, dramatic, bold"
        try:
            resp = api_request(
                "https://api.openai.com/v1/images/generations",
                data={
                    "model": "dall-e-3",
                    "prompt": thumb_prompt,
                    "n": 1,
                    "size": "1024x1792",
                    "quality": "hd",
                    "style": "natural",
                },
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            )
            thumb_path = OUTPUT_DIR / "thumbnail.png"
            urllib.request.urlretrieve(resp["data"][0]["url"], str(thumb_path))
            images["thumbnail"] = thumb_path
            print("  thumbnail : OK")
        except Exception as e:
            print(f"  [WARN] Thumbnail echouee : {e}")

    return images


def generate_voiceover(script):
    print("[4/7] Generation de la voix off via ElevenLabs...")

    voiceover_text = script.get("full_voiceover", "")
    if not voiceover_text:
        parts = [
            script.get("hook", {}).get("voiceover", ""),
            script.get("segment_1", {}).get("voiceover", ""),
            script.get("segment_2", {}).get("voiceover", ""),
        ]
        voiceover_text = " ".join(p for p in parts if p)

    data = {
        "text": voiceover_text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.3,
            "use_speaker_boost": True,
        },
    }

    audio_bytes = api_request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
        data=data,
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Accept": "audio/mpeg",
        },
    )

    audio_path = OUTPUT_DIR / "voiceover.mp3"
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)

    print(f"  Voix off generee : {len(audio_bytes) / 1024:.0f} KB")
    return audio_path


def get_today_avatar_id():
    if not HEYGEN_AVATAR_IDS:
        return None
    ids = [x.strip() for x in HEYGEN_AVATAR_IDS.split(",") if x.strip()]
    if not ids:
        return None
    return ids[datetime.now().timetuple().tm_yday % len(ids)]


def generate_heygen_clip(text, label, avatar_id):
    print(f"  HeyGen {label} : generation...")
    data = {
        "video_inputs": [{
            "character": {
                "type": "avatar",
                "avatar_id": avatar_id,
                "avatar_style": "normal",
            },
            "voice": {
                "type": "elevenlabs",
                "voice_id": ELEVENLABS_VOICE_ID,
                "api_key": ELEVENLABS_API_KEY,
                "input_text": text,
            },
            "background": {
                "type": "color",
                "value": "#f0f0f0",
            },
        }],
        "test": False,
        "dimension": {"width": 1080, "height": 1920},
    }

    try:
        resp = api_request(
            "https://api.heygen.com/v2/video/generate",
            data=data,
            headers={"X-Api-Key": HEYGEN_API_KEY},
        )
        video_id = resp.get("data", {}).get("video_id")
        if not video_id:
            print(f"  [WARN] HeyGen {label} : pas de video_id")
            return None

        for _ in range(60):
            time.sleep(5)
            status_resp = api_request(
                f"https://api.heygen.com/v1/video_status.get?video_id={video_id}",
                headers={"X-Api-Key": HEYGEN_API_KEY},
            )
            status = status_resp.get("data", {}).get("status", "")
            if status == "completed":
                video_url = status_resp["data"]["video_url"]
                clip_path = OUTPUT_DIR / f"avatar_{label}.mp4"
                urllib.request.urlretrieve(video_url, str(clip_path))
                print(f"  HeyGen {label} : OK")
                return clip_path
            elif status == "failed":
                err = status_resp.get("data", {}).get("error", "")
                print(f"  [WARN] HeyGen {label} echoue : {err}")
                return None

        print(f"  [WARN] HeyGen {label} timeout")
        return None
    except Exception as e:
        print(f"  [WARN] HeyGen {label} erreur : {e}")
        return None


def generate_avatar_clips(script):
    print("[5/7] Generation des clips avatar via HeyGen (intro + rebond + conclusion)...")
    avatar_id = get_today_avatar_id()
    if not avatar_id:
        print("  [SKIP] Pas d'avatar HeyGen configure -> mode 100% anime")
        return None, None, None

    intro_text = script.get("avatar_intro", {}).get("speech", "")
    rebond_text = script.get("avatar_rebond", {}).get("speech", "")
    conclusion_text = script.get("avatar_conclusion", {}).get("speech", "")

    intro_clip = generate_heygen_clip(intro_text, "intro", avatar_id) if intro_text else None
    rebond_clip = generate_heygen_clip(rebond_text, "rebond", avatar_id) if rebond_text else None
    conclusion_clip = generate_heygen_clip(conclusion_text, "conclusion", avatar_id) if conclusion_text else None
    return intro_clip, rebond_clip, conclusion_clip


def upload_to_creatomate(file_path, mime_type):
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    boundary = "----FormBoundary" + str(int(time.time()))
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        f"Content-Type: {mime_type}\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

    req = urllib.request.Request(
        "https://api.creatomate.com/v1/files",
        data=body,
        headers={
            "Authorization": f"Bearer {CREATOMATE_API_KEY}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
    return result.get("url", "")


def build_creatomate_source(script, images, voiceover_path, intro_clip, rebond_clip, conclusion_clip):
    print("  Upload des assets vers Creatomate...")
    voiceover_url = upload_to_creatomate(voiceover_path, "audio/mpeg")

    image_urls = {}
    for label, img_path in images.items():
        if label == "thumbnail":
            continue
        image_urls[label] = upload_to_creatomate(img_path, "image/png")
        print(f"    {label} uploade")

    intro_url = upload_to_creatomate(intro_clip, "video/mp4") if intro_clip and intro_clip.exists() else None
    rebond_url = upload_to_creatomate(rebond_clip, "video/mp4") if rebond_clip and rebond_clip.exists() else None
    conclusion_url = upload_to_creatomate(conclusion_clip, "video/mp4") if conclusion_clip and conclusion_clip.exists() else None

    elements = []
    t = 0
    vo_offset = 0  # position dans le fichier voiceover (parties animees seulement)

    # ── HOOK (animation) ──────────────────────────────────────────────────────
    hook = script.get("hook", {})
    hook_dur = hook.get("duration", 5)
    if image_urls.get("hook"):
        elements.append({
            "type": "image", "source": image_urls["hook"],
            "x": "50%", "y": "50%", "width": "100%", "height": "100%",
            "time": t, "duration": hook_dur,
            "animations": [{"type": "scale", "start_scale": "100%", "end_scale": "110%", "easing": "linear"}],
        })
    elements.append({
        "type": "text", "text": hook.get("screen_text", ""),
        "x": "50%", "y": "75%", "width": "85%",
        "time": t, "duration": hook_dur,
        "font_family": "Montserrat", "font_weight": "800", "font_size": "8.5 vmin",
        "fill_color": "#ffffff", "shadow_color": "rgba(0,0,0,0.7)", "shadow_blur": "4",
        "x_alignment": "50%", "y_alignment": "50%",
        "animations": [{"type": "text-appear", "split": "word", "duration": 0.3}],
    })
    elements.append({
        "type": "audio", "source": voiceover_url,
        "time": t, "duration": hook_dur, "trim_start": vo_offset,
    })
    vo_offset += hook_dur
    t += hook_dur

    # ── FACECAM INTRO (avatar) ────────────────────────────────────────────────
    intro_dur = script.get("avatar_intro", {}).get("duration", 7)
    if intro_url:
        elements.append({
            "type": "video", "source": intro_url,
            "x": "50%", "y": "50%", "width": "100%", "height": "100%",
            "time": t, "duration": intro_dur,
        })
    t += intro_dur

    # ── SEGMENT 1 (animation) ─────────────────────────────────────────────────
    seg1 = script.get("segment_1", {})
    seg1_dur = seg1.get("duration", 15)
    if image_urls.get("segment_1"):
        elements.append({
            "type": "image", "source": image_urls["segment_1"],
            "x": "50%", "y": "50%", "width": "100%", "height": "100%",
            "time": t, "duration": seg1_dur,
            "animations": [{"type": "scale", "start_scale": "110%", "end_scale": "100%", "easing": "linear"}],
        })
    if seg1.get("screen_text"):
        elements.append({
            "type": "text", "text": seg1["screen_text"],
            "x": "50%", "y": "80%", "width": "85%",
            "time": t, "duration": seg1_dur,
            "font_family": "Montserrat", "font_weight": "700", "font_size": "7 vmin",
            "fill_color": "#ffffff", "shadow_color": "rgba(0,0,0,0.6)", "shadow_blur": "3",
            "x_alignment": "50%", "y_alignment": "50%",
            "background_color": "rgba(0,0,0,0.4)",
            "background_x_padding": "8%", "background_y_padding": "4%",
            "background_border_radius": "8",
            "animations": [{"type": "text-appear", "split": "word", "duration": 0.2}],
        })
    elements.append({
        "type": "audio", "source": voiceover_url,
        "time": t, "duration": seg1_dur, "trim_start": vo_offset,
    })
    vo_offset += seg1_dur
    t += seg1_dur

    # ── FACECAM REBOND (avatar) ───────────────────────────────────────────────
    rebond_dur = script.get("avatar_rebond", {}).get("duration", 7)
    if rebond_url:
        elements.append({
            "type": "video", "source": rebond_url,
            "x": "50%", "y": "50%", "width": "100%", "height": "100%",
            "time": t, "duration": rebond_dur,
        })
    t += rebond_dur

    # ── SEGMENT 2 (animation) ─────────────────────────────────────────────────
    seg2 = script.get("segment_2", {})
    seg2_dur = seg2.get("duration", 12)
    if image_urls.get("segment_2"):
        elements.append({
            "type": "image", "source": image_urls["segment_2"],
            "x": "50%", "y": "50%", "width": "100%", "height": "100%",
            "time": t, "duration": seg2_dur,
            "animations": [{"type": "scale", "start_scale": "100%", "end_scale": "108%", "easing": "linear"}],
        })
    if seg2.get("screen_text"):
        elements.append({
            "type": "text", "text": seg2["screen_text"],
            "x": "50%", "y": "80%", "width": "85%",
            "time": t, "duration": seg2_dur,
            "font_family": "Montserrat", "font_weight": "700", "font_size": "7 vmin",
            "fill_color": "#ffffff", "shadow_color": "rgba(0,0,0,0.6)", "shadow_blur": "3",
            "x_alignment": "50%", "y_alignment": "50%",
            "background_color": "rgba(0,0,0,0.4)",
            "background_x_padding": "8%", "background_y_padding": "4%",
            "background_border_radius": "8",
            "animations": [{"type": "text-appear", "split": "word", "duration": 0.2}],
        })
    elements.append({
        "type": "audio", "source": voiceover_url,
        "time": t, "duration": seg2_dur, "trim_start": vo_offset,
    })
    t += seg2_dur

    # ── FACECAM CONCLUSION (avatar) ───────────────────────────────────────────
    conclusion_dur = script.get("avatar_conclusion", {}).get("duration", 15)
    if conclusion_url:
        elements.append({
            "type": "video", "source": conclusion_url,
            "x": "50%", "y": "50%", "width": "100%", "height": "100%",
            "time": t, "duration": conclusion_dur,
        })
    else:
        # Fallback : image avec texte CTA si pas d'avatar
        fallback_img = image_urls.get("segment_2") or image_urls.get("segment_1") or image_urls.get("hook")
        if fallback_img:
            elements.append({
                "type": "image", "source": fallback_img,
                "x": "50%", "y": "50%", "width": "100%", "height": "100%",
                "time": t, "duration": conclusion_dur,
                "color_overlay": "rgba(0,0,0,0.45)",
            })
        cta_speech = script.get("avatar_conclusion", {}).get("speech", "Pharmusez vous bien !")
        elements.append({
            "type": "text", "text": cta_speech,
            "x": "50%", "y": "50%", "width": "80%",
            "time": t, "duration": conclusion_dur,
            "font_family": "Montserrat", "font_weight": "800", "font_size": "7 vmin",
            "fill_color": "#ffffff", "shadow_color": "rgba(0,0,0,0.8)", "shadow_blur": "5",
            "x_alignment": "50%", "y_alignment": "50%",
            "animations": [{"type": "text-appear", "split": "line", "duration": 0.5}],
        })
    t += conclusion_dur

    # ── WATERMARK ─────────────────────────────────────────────────────────────
    elements.append({
        "type": "text", "text": "Pharm'Actus",
        "x": "85%", "y": "5%", "time": 0, "duration": t,
        "font_family": "Montserrat", "font_weight": "700", "font_size": "3.5 vmin",
        "fill_color": "rgba(255,255,255,0.6)",
    })

    return {
        "output_format": "mp4", "width": 1080, "height": 1920,
        "frame_rate": 30, "duration": t, "elements": elements,
    }


def render_video(source):
    print("  Lancement du rendu Creatomate...")
    resp = api_request(
        "https://api.creatomate.com/v1/renders",
        data={"source": source},
        headers={"Authorization": f"Bearer {CREATOMATE_API_KEY}"},
    )
    renders = resp if isinstance(resp, list) else [resp]
    render_id = renders[0].get("id", "")
    print(f"  Render ID : {render_id}")

    for _ in range(120):
        time.sleep(5)
        status = api_request(
            f"https://api.creatomate.com/v1/renders/{render_id}",
            headers={"Authorization": f"Bearer {CREATOMATE_API_KEY}"},
        )
        state = status.get("status", "")
        if state == "succeeded":
            print("  Rendu termine !")
            return status.get("url", "")
        elif state == "failed":
            print(f"  [ERROR] Rendu echoue : {status.get('error_message', '')}")
            return None

    print("  [ERROR] Rendu timeout apres 10 min")
    return None


def assemble_video(script, images, voiceover_path, intro_clip, rebond_clip, conclusion_clip):
    print("[6/7] Assemblage video via Creatomate...")
    source = build_creatomate_source(script, images, voiceover_path, intro_clip, rebond_clip, conclusion_clip)

    source_path = OUTPUT_DIR / "creatomate_source.json"
    with open(source_path, "w", encoding="utf-8") as f:
        json.dump(source, f, ensure_ascii=False, indent=2)

    video_url = render_video(source)
    if not video_url:
        return None

    video_path = OUTPUT_DIR / "tiktok_video.mp4"
    urllib.request.urlretrieve(video_url, str(video_path))
    size_mb = video_path.stat().st_size / (1024 * 1024)
    print(f"  Video finale : {size_mb:.1f} MB")
    return video_path


def publish_to_tiktok(video_path, script):
    print("[7/7] Publication sur TikTok...")

    if not TIKTOK_ACCESS_TOKEN:
        print("  [SKIP] Pas de TIKTOK_ACCESS_TOKEN -> publication manuelle")
        return None

    title = script.get("titre_tiktok", "Le Saviez-Vous ?")
    description = script.get("description_tiktok", "")
    post_title = f"{title}\n\n{description}"[:150]
    video_size = video_path.stat().st_size

    init_data = {
        "post_info": {
            "title": post_title,
            "privacy_level": "PUBLIC_TO_EVERYONE",
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": video_size,
            "chunk_size": video_size,
            "total_chunk_count": 1,
        },
    }

    try:
        init_resp = api_request(
            "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
            data=init_data,
            headers={
                "Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}",
                "Content-Type": "application/json; charset=UTF-8",
            },
        )
        publish_id = init_resp.get("data", {}).get("publish_id", "")
        upload_url = init_resp.get("data", {}).get("upload_url", "")
        if not upload_url:
            print(f"  [ERROR] TikTok init echoue : {init_resp}")
            return None

        with open(video_path, "rb") as f:
            video_bytes = f.read()

        req = urllib.request.Request(
            upload_url, data=video_bytes,
            headers={
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
            },
            method="PUT",
        )
        with urllib.request.urlopen(req, timeout=300) as resp:
            resp.read()

        print(f"  Video uploadee ! Publish ID : {publish_id}")
        time.sleep(5)
        status_resp = api_request(
            "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
            data={"publish_id": publish_id},
            headers={
                "Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}",
                "Content-Type": "application/json; charset=UTF-8",
            },
        )
        print(f"  Statut : {status_resp.get('data', {}).get('status', 'unknown')}")
        return publish_id

    except Exception as e:
        print(f"  [ERROR] Publication TikTok echouee : {e}")
        return None


def main():
    print("=" * 60)
    print("PHARM'ACTUS TIKTOK - Pipeline video quotidien")
    print(f"Date : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    missing = []
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY",
                 "ELEVENLABS_VOICE_ID", "CREATOMATE_API_KEY"]:
        if not os.environ.get(key):
            missing.append(key)
    if missing:
        print(f"[ERROR] Cles API manquantes : {', '.join(missing)}")
        sys.exit(1)

    if not HEYGEN_API_KEY:
        print("[INFO] HeyGen non configure -> mode 100% anime")
    if not TIKTOK_ACCESS_TOKEN:
        print("[INFO] TikTok non configure -> video generee mais pas publiee")

    lsv = load_lsv()
    script = generate_tiktok_script(lsv)

    with open(OUTPUT_DIR / "tiktok_script.json", "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    images = generate_images(script)
    voiceover_path = generate_voiceover(script)
    intro_clip, rebond_clip, conclusion_clip = generate_avatar_clips(script)
    video_path = assemble_video(script, images, voiceover_path, intro_clip, rebond_clip, conclusion_clip)

    if video_path:
        publish_id = publish_to_tiktok(video_path, script)
        print()
        print("=" * 60)
        if publish_id:
            print(f"VIDEO PUBLIEE sur TikTok ! (ID: {publish_id})")
        else:
            print(f"VIDEO GENEREE : {video_path}")
            print("Publication manuelle requise")
        print("=" * 60)
    else:
        print("\n[ERROR] Pipeline echoue - pas de video generee")
        sys.exit(1)


if __name__ == "__main__":
    main()
