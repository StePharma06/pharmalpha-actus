#!/usr/bin/env python3
"""
Pharm'Actus TikTok - Pipeline video v4 (simple & clean)
Style : VoxTemporis / StoryFrance / CortexRaconte

Structure :
  Hook (5s) -> "Abonne-toi" (2s) -> Story narree (53s) -> CTA + "Abonne-toi" (5s)
  Voix ElevenLabs ininterrompue du debut a la fin.
  Images DALL-E plein ecran avec Ken Burns.
  Sous-titres mot par mot (blanc + ombre noire, gros, centres).
  PAS de facecam. PAS de videos stock.
"""

import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

# -- Config ----------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
LSV_INPUT = ROOT_DIR / "output" / "latest_lsv.json"
OUTPUT_DIR = ROOT_DIR / "output" / "tiktok"
QUEUE_DIR = ROOT_DIR / "output" / "tiktok" / "queue"
PUBLISH_DELAY_DAYS = 2

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
CREATOMATE_API_KEY = os.environ.get("CREATOMATE_API_KEY", "")


# -- Helpers ---------------------------------------------------------------

def api_request(url, data=None, headers=None, method=None):
    headers = headers or {}
    if data is not None and isinstance(data, dict):
        data = json.dumps(data).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    headers.setdefault("User-Agent", "Mozilla/5.0 PharmaAlpha/1.0")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=300) as resp:
        ct = resp.headers.get("Content-Type", "")
        raw = resp.read()
        if "json" in ct:
            return json.loads(raw)
        return raw


def upload_temp(file_path):
    """Upload to tmpfiles.org, return direct download URL."""
    boundary = f"----Boundary{int(time.time())}"
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        "https://tmpfiles.org/api/v1/upload", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                 "User-Agent": "Mozilla/5.0 PharmaAlpha/1.0"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read())
    page_url = result.get("data", {}).get("url", "")
    return page_url.replace("tmpfiles.org/", "tmpfiles.org/dl/", 1)


# -- Step 1: Load LSV -----------------------------------------------------

def load_lsv():
    if not LSV_INPUT.exists():
        print("[ERROR] output/latest_lsv.json introuvable")
        sys.exit(1)
    with open(LSV_INPUT, "r", encoding="utf-8") as f:
        lsv = json.load(f)
    print(f"[1/5] LSV charge : {lsv.get('titre', '')[:60]}...")
    return lsv


# -- Step 2: Claude Script ------------------------------------------------

SCRIPT_PROMPT = """Tu es le narrateur de Pharm'Alpha, chaine TikTok "Le Saviez-Vous" pharma/sante.
Style : VoxTemporis, StoryFrance, CortexRaconte. Narration captivante, rythme soutenu, ton conversationnel.

ARTICLE DU JOUR :
TITRE : {titre}
RESUME : {resume}
TEXTE COMPLET :
{full_text}

Cree un script TikTok de 65 secondes. PAS de facecam. Voix off ininterrompue du debut a la fin.

STRUCTURE EXACTE :
1. HOOK (5s) : phrase d'accroche CHOC qui donne envie de rester. Doit etre COMPLETE en 5 secondes.
2. [Pause visuelle "Abonne-toi @pharmalpha" pendant 2s — geree par le code, pas dans le texte]
3. STORY en 5 parties enchainee sans rupture :
   - part1 (10s) : mise en contexte, pose le decor
   - part2 (11s) : le fait principal, developpement
   - part3 (11s) : le twist ou fait surprenant
   - part4 (11s) : consequence, lien avec aujourd'hui
   - part5 (10s) : conclusion + "Pharmusez-vous bien !" + "Retrouvez toutes nos actus sur actus point pharmalpha point fr"
4. [Pause visuelle "Abonne-toi @pharmalpha" pendant 5s — geree par le code]

REGLES TEXTE :
- full_voiceover = texte COMPLET et CONTINU hook + story (PAS les pauses "abonne-toi"). ~220 mots pour 58 secondes.
- Le hook doit ACCROCHER : question rhetorique, fait choquant, mystere. Style conversationnel.
- titre_tiktok : style conversationnel naturel, pas de majuscules agressives. Ex: "Quand les pharmaciens inventaient le carat avec des graines..."
- Chaque partie a un "screen_text" court (le fait cle en 6-8 mots max) qui s'affiche en gros

REGLES IMAGES (6 images, une par partie + hook) :
- image_prompt en ANGLAIS
- Style : photorealistic editorial photography, shot on Canon EOS R5, 85mm, shallow depth of field
- CONCRET et SPECIFIQUE au sujet (pas generique). Ex: "close-up of carob seeds on antique brass pharmacy scale" pas "pharmacy interior"
- PAS de texte dans l'image, PAS de style cartoon/IA

Reponds UNIQUEMENT en JSON valide :
{{
  "hook": {{
    "voiceover": "Phrase d'accroche complete en 5 sec (~20 mots)",
    "screen_text": "Fait choc (6-8 mots max)",
    "image_prompt": "Prompt DALL-E specifique et concret..."
  }},
  "story": {{
    "full_voiceover": "Texte COMPLET et CONTINU des 5 parties enchainees (~200 mots, 53 sec de parole). Se termine par 'Pharmusez-vous bien ! Retrouvez toutes nos actus sur actus point pharmalpha point fr'",
    "parts": [
      {{"id": "part1", "screen_text": "Fait cle (6-8 mots)", "image_prompt": "Prompt DALL-E specifique...", "duration": 10}},
      {{"id": "part2", "screen_text": "Fait cle (6-8 mots)", "image_prompt": "Prompt DALL-E specifique...", "duration": 11}},
      {{"id": "part3", "screen_text": "Fait cle (6-8 mots)", "image_prompt": "Prompt DALL-E specifique...", "duration": 11}},
      {{"id": "part4", "screen_text": "Fait cle (6-8 mots)", "image_prompt": "Prompt DALL-E specifique...", "duration": 11}},
      {{"id": "part5", "screen_text": "Pharmusez-vous bien !", "image_prompt": "Prompt DALL-E specifique...", "duration": 10}}
    ]
  }},
  "titre_tiktok": "Titre conversationnel accrocheur (max 80 car)",
  "description_tiktok": "Description + hashtags (max 300 car)",
  "hashtags": "#lesaviezvous #pharmalpha #pharmacie #sante"
}}"""


def generate_script(lsv):
    print("[2/5] Generation du script via Claude...")
    prompt = SCRIPT_PROMPT.format(
        titre=lsv.get("titre", ""),
        resume=lsv.get("resume", ""),
        full_text=lsv.get("full_text", ""),
    )
    resp = api_request(
        "https://api.anthropic.com/v1/messages",
        data={"model": "claude-sonnet-4-20250514", "max_tokens": 2000,
              "messages": [{"role": "user", "content": prompt}]},
        headers={"x-api-key": ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"},
    )
    text = resp["content"][0]["text"].strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        print("[ERROR] Pas de JSON valide")
        sys.exit(1)
    script = json.loads(match.group())
    print(f"  Script : {script.get('titre_tiktok', '')[:50]}...")
    return script


# -- Step 3: Gemini Images (nanobanana) ------------------------------------

def generate_gemini_image(prompt, label):
    """Generate one image via Gemini API. Returns public URL or None."""
    import base64
    full_prompt = f"Generate a photorealistic vertical 9:16 image: {prompt}. No text, no watermark, no AI artifacts. Editorial photography quality."
    data = {
        "contents": [{"parts": [{"text": full_prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
    }
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={GEMINI_API_KEY}"
        resp = api_request(url, data=data)
        # Extract base64 image from response
        for part in resp.get("candidates", [{}])[0].get("content", {}).get("parts", []):
            if "inlineData" in part:
                img_data = base64.b64decode(part["inlineData"]["data"])
                mime = part["inlineData"].get("mimeType", "image/png")
                ext = "png" if "png" in mime else "jpg"
                img_path = OUTPUT_DIR / f"{label}.{ext}"
                with open(img_path, "wb") as f:
                    f.write(img_data)
                # Upload to tmpfiles for public URL (Creatomate needs URLs)
                img_url = upload_temp(img_path)
                return img_url
        print(f"  [WARN] {label} : pas d'image dans la reponse Gemini")
        return None
    except Exception as e:
        print(f"  [WARN] {label} : {e}")
        return None


def generate_images(script):
    """Generate images for hook + 5 story parts via Gemini. Returns {label: url}."""
    print("[3/5] Generation images Gemini (nanobanana)...")
    prompts = [("hook", script.get("hook", {}).get("image_prompt", ""))]
    for part in script.get("story", {}).get("parts", []):
        prompts.append((part["id"], part.get("image_prompt", "")))
    prompts = [(k, v) for k, v in prompts if v]

    image_urls = {}
    for label, prompt in prompts:
        url = generate_gemini_image(prompt, label)
        if url:
            image_urls[label] = url
            print(f"  {label} : OK")
        else:
            print(f"  {label} : ECHEC")
    return image_urls


# -- Step 4: ElevenLabs Voiceover -----------------------------------------

def generate_voiceover(script):
    """One continuous voiceover: hook + story. Returns (path, url)."""
    print("[4/5] Generation voix off ElevenLabs...")

    hook_text = script.get("hook", {}).get("voiceover", "")
    story_text = script.get("story", {}).get("full_voiceover", "")
    full_text = f"{hook_text} {story_text}".strip()

    audio_bytes = api_request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
        data={
            "text": full_text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75,
                               "style": 0.3, "use_speaker_boost": True},
        },
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Accept": "audio/mpeg"},
    )

    path = OUTPUT_DIR / "voiceover.mp3"
    with open(path, "wb") as f:
        f.write(audio_bytes)
    print(f"  Voix off : {len(audio_bytes) / 1024:.0f} KB")

    url = upload_temp(path)
    print(f"  Upload : OK")
    return path, url, full_text


# -- Step 5: Creatomate Assembly -------------------------------------------

def build_subtitle_elements(text, start_time, duration):
    """Word-by-word subtitles: 3 words at a time, big white text + black shadow."""
    words = text.split()
    if not words:
        return []

    # Group by 3 words
    chunks = []
    for i in range(0, len(words), 3):
        chunks.append(" ".join(words[i:i + 3]))

    chunk_dur = duration / len(chunks) if chunks else 1
    elements = []

    for idx, chunk in enumerate(chunks):
        t = start_time + idx * chunk_dur
        elements.append({
            "type": "text",
            "text": chunk.upper(),
            "x": "50%",
            "y": "72%",
            "width": "90%",
            "time": round(t, 2),
            "duration": round(chunk_dur, 2),
            "font_family": "Montserrat",
            "font_weight": "800",
            "font_size": "10 vmin",
            "fill_color": "#ffffff",
            "shadow_color": "rgba(0,0,0,0.95)",
            "shadow_blur": "6",
            "shadow_x": "3",
            "shadow_y": "3",
            "x_alignment": "50%",
            "y_alignment": "50%",
        })

    return elements


def build_abonne_toi_element(start_time, duration):
    """'ABONNE-TOI' popup element."""
    return [
        # Dark overlay
        {
            "type": "shape",
            "shape": "rectangle",
            "fill_color": "rgba(0,0,0,0.5)",
            "x": "50%", "y": "50%", "width": "100%", "height": "100%",
            "time": round(start_time, 2),
            "duration": round(duration, 2),
        },
        # Text
        {
            "type": "text",
            "text": "ABONNE-TOI\n@pharmalpha",
            "x": "50%", "y": "48%", "width": "80%",
            "time": round(start_time, 2),
            "duration": round(duration, 2),
            "font_family": "Montserrat",
            "font_weight": "900",
            "font_size": "14 vmin",
            "fill_color": "#ffffff",
            "shadow_color": "rgba(0,0,0,0.8)",
            "shadow_blur": "8",
            "x_alignment": "50%",
            "y_alignment": "50%",
            "line_height": "140%",
            "animations": [{"type": "scale", "start_scale": "80%", "end_scale": "100%",
                            "easing": "ease-out", "duration": 0.3}],
        },
        # Arrow emoji
        {
            "type": "text",
            "text": "👆",
            "x": "50%", "y": "62%",
            "time": round(start_time, 2),
            "duration": round(duration, 2),
            "font_size": "12 vmin",
            "x_alignment": "50%",
            "y_alignment": "50%",
        },
    ]


def build_creatomate_source(script, image_urls, voiceover_url, vo_text):
    """Build the Creatomate render JSON."""
    elements = []
    t = 0.0

    hook_dur = 5.0
    abonne1_dur = 2.0
    parts = script.get("story", {}).get("parts", [])
    story_dur = sum(p.get("duration", 10) for p in parts)
    abonne2_dur = 5.0

    total_vo_dur = hook_dur + story_dur  # voiceover covers hook + story

    # ── VOICEOVER (continuous, starts at 0, plays during hook + paused during abonne1 + resumes for story) ──
    # Place hook audio
    elements.append({
        "type": "audio", "source": voiceover_url,
        "time": 0, "duration": hook_dur, "trim_start": 0,
    })
    # Place story audio (after abonne1 pause)
    elements.append({
        "type": "audio", "source": voiceover_url,
        "time": hook_dur + abonne1_dur, "duration": story_dur,
        "trim_start": hook_dur,
    })

    # ── 1. HOOK (5s) ─────────────────────────────────────────────────────────
    hook_img = image_urls.get("hook")
    if hook_img:
        elements.append({
            "type": "image", "source": hook_img,
            "x": "50%", "y": "50%", "width": "100%", "height": "100%",
            "time": t, "duration": hook_dur,
            "animations": [{"type": "scale", "start_scale": "100%", "end_scale": "120%",
                            "easing": "linear"}],
        })

    # Hook screen text (big, dramatic)
    hook_text = script.get("hook", {}).get("screen_text", "")
    if hook_text:
        elements.append({
            "type": "text", "text": hook_text.upper(),
            "x": "50%", "y": "72%", "width": "85%",
            "time": t, "duration": hook_dur,
            "font_family": "Montserrat", "font_weight": "900", "font_size": "11 vmin",
            "fill_color": "#ffffff",
            "shadow_color": "rgba(0,0,0,0.95)", "shadow_blur": "8",
            "shadow_x": "3", "shadow_y": "3",
            "x_alignment": "50%", "y_alignment": "50%",
            "animations": [{"type": "text-appear", "split": "word", "duration": 0.25}],
        })

    # Hook subtitles
    hook_vo = script.get("hook", {}).get("voiceover", "")
    elements.extend(build_subtitle_elements(hook_vo, t, hook_dur))

    t += hook_dur

    # ── 2. ABONNE-TOI #1 (2s) ────────────────────────────────────────────────
    # Keep last hook image as background
    if hook_img:
        elements.append({
            "type": "image", "source": hook_img,
            "x": "50%", "y": "50%", "width": "120%", "height": "120%",
            "time": t, "duration": abonne1_dur,
            "color_filter": "blur(8px)",
        })
    elements.extend(build_abonne_toi_element(t, abonne1_dur))
    t += abonne1_dur

    # ── 3. STORY (5 parts, ~53s) ─────────────────────────────────────────────
    story_text = script.get("story", {}).get("full_voiceover", "")
    story_words = story_text.split()
    total_story_words = len(story_words)
    word_offset = 0

    for i, part in enumerate(parts):
        part_dur = part.get("duration", 10)
        part_id = part["id"]

        # Visual: image with Ken Burns
        img = image_urls.get(part_id)
        if img:
            # Alternate zoom direction
            if i % 2 == 0:
                anim = {"type": "scale", "start_scale": "100%", "end_scale": "115%", "easing": "linear"}
            else:
                anim = {"type": "scale", "start_scale": "115%", "end_scale": "100%", "easing": "linear"}
            elements.append({
                "type": "image", "source": img,
                "x": "50%", "y": "50%", "width": "100%", "height": "100%",
                "time": round(t, 2), "duration": part_dur,
                "animations": [anim],
            })

        # Screen text (fact overlay at top)
        screen_text = part.get("screen_text", "")
        if screen_text and part_id != "part5":
            elements.append({
                "type": "text", "text": screen_text.upper(),
                "x": "50%", "y": "18%", "width": "85%",
                "time": round(t, 2), "duration": part_dur,
                "font_family": "Montserrat", "font_weight": "800", "font_size": "6 vmin",
                "fill_color": "rgba(255,255,255,0.9)",
                "shadow_color": "rgba(0,0,0,0.7)", "shadow_blur": "4",
                "x_alignment": "50%", "y_alignment": "50%",
                "background_color": "rgba(0,0,0,0.35)",
                "background_x_padding": "5%", "background_y_padding": "3%",
                "background_border_radius": "8",
            })

        # Subtitles for this part (proportional word count)
        part_word_count = int(total_story_words * part_dur / story_dur)
        if i == len(parts) - 1:
            part_word_count = total_story_words - word_offset  # last part gets remainder
        part_words = story_words[word_offset:word_offset + part_word_count]
        part_text = " ".join(part_words)
        if part_text:
            elements.extend(build_subtitle_elements(part_text, t, part_dur))
        word_offset += part_word_count

        t += part_dur

    # ── 4. ABONNE-TOI #2 + CTA (5s) ──────────────────────────────────────────
    last_img = image_urls.get("part5") or image_urls.get("part4") or image_urls.get("hook")
    if last_img:
        elements.append({
            "type": "image", "source": last_img,
            "x": "50%", "y": "50%", "width": "120%", "height": "120%",
            "time": round(t, 2), "duration": abonne2_dur,
            "color_filter": "blur(8px)",
        })
    elements.extend(build_abonne_toi_element(t, abonne2_dur))
    # Add actus.pharmalpha.fr below
    elements.append({
        "type": "text",
        "text": "actus.pharmalpha.fr",
        "x": "50%", "y": "75%", "width": "80%",
        "time": round(t, 2), "duration": abonne2_dur,
        "font_family": "Montserrat", "font_weight": "600", "font_size": "5 vmin",
        "fill_color": "rgba(255,255,255,0.8)",
        "x_alignment": "50%", "y_alignment": "50%",
    })
    t += abonne2_dur

    # ── WATERMARK ─────────────────────────────────────────────────────────────
    elements.append({
        "type": "text", "text": "@pharmalpha",
        "x": "50%", "y": "5%", "time": 0, "duration": round(t, 2),
        "font_family": "Montserrat", "font_weight": "700", "font_size": "3.5 vmin",
        "fill_color": "rgba(255,255,255,0.6)",
        "x_alignment": "50%",
    })

    return {
        "output_format": "mp4",
        "width": 1080, "height": 1920,
        "frame_rate": 30,
        "duration": round(t, 2),
        "elements": elements,
    }


def render_video(source):
    print("  Rendu Creatomate...")
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
        st = api_request(
            f"https://api.creatomate.com/v1/renders/{render_id}",
            headers={"Authorization": f"Bearer {CREATOMATE_API_KEY}"},
        )
        state = st.get("status", "")
        if state == "succeeded":
            print("  Rendu OK !")
            return st.get("url", "")
        elif state == "failed":
            print(f"  [ERROR] Rendu echoue : {st.get('error_message', '')}")
            return None

    print("  [ERROR] Timeout 10 min")
    return None


def assemble_video(script, image_urls, vo_url, vo_text):
    print("[5/5] Assemblage Creatomate...")
    source = build_creatomate_source(script, image_urls, vo_url, vo_text)

    with open(OUTPUT_DIR / "creatomate_source.json", "w", encoding="utf-8") as f:
        json.dump(source, f, ensure_ascii=False, indent=2)

    video_url = render_video(source)
    if not video_url:
        return None

    video_path = OUTPUT_DIR / "tiktok_video.mp4"
    urllib.request.urlretrieve(video_url, str(video_path))
    size_mb = video_path.stat().st_size / (1024 * 1024)
    print(f"  Video finale : {size_mb:.1f} MB")
    return video_path


# -- Save to Queue ---------------------------------------------------------

def save_to_queue(video_path, script):
    today = datetime.now().strftime("%Y-%m-%d")
    publish_date = (datetime.now() + timedelta(days=PUBLISH_DELAY_DAYS)).strftime("%Y-%m-%d")

    slot = QUEUE_DIR / today
    slot.mkdir(parents=True, exist_ok=True)

    shutil.copy2(video_path, slot / "video.mp4")
    for png in OUTPUT_DIR.glob("*.png"):
        shutil.copy2(png, slot / png.name)

    with open(slot / "script.json", "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    metadata = {
        "generated_date": today,
        "publish_date": publish_date,
        "published": False,
        "publish_id": None,
        "titre": script.get("titre_tiktok", ""),
        "description": script.get("description_tiktok", ""),
        "hashtags": script.get("hashtags", ""),
    }
    with open(slot / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"  Queue : {slot}")
    print(f"  Publication : {publish_date} a 18h30")
    return slot


# -- Main ------------------------------------------------------------------

def main():
    print("=" * 60)
    print("PHARM'ACTUS TIKTOK v4 - Simple & Clean")
    print(f"Date : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    missing = []
    for key in ["ANTHROPIC_API_KEY", "GEMINI_API_KEY", "ELEVENLABS_API_KEY",
                 "ELEVENLABS_VOICE_ID", "CREATOMATE_API_KEY"]:
        if not os.environ.get(key):
            missing.append(key)
    if missing:
        print(f"[ERROR] Cles manquantes : {', '.join(missing)}")
        sys.exit(1)

    lsv = load_lsv()
    script = generate_script(lsv)

    with open(OUTPUT_DIR / "tiktok_script.json", "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    image_urls = generate_images(script)
    vo_path, vo_url, vo_text = generate_voiceover(script)
    video_path = assemble_video(script, image_urls, vo_url, vo_text)

    if video_path:
        slot = save_to_queue(video_path, script)
        print()
        print("=" * 60)
        print(f"VIDEO EN QUEUE : {slot}")
        print(f"Publication dans {PUBLISH_DELAY_DAYS} jours")
        print("=" * 60)
    else:
        print("\n[ERROR] Pipeline echoue")
        sys.exit(1)


if __name__ == "__main__":
    main()
