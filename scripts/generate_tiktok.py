#!/usr/bin/env python3
"""
Pharm'Actus TikTok - Pipeline video quotidien v3
Transforme le LSV du jour en video TikTok ~65s.

Structure :
  Hook anime (5s) -> Facecam intro (3s) -> Story animee (50s) -> Facecam outro (5s)
  Voix ElevenLabs ininterrompue sur hook + story (55s).
  Sous-titres mot par mot style TikTok viral.
  Videos stock Pexels + images DALL-E en Ken Burns.

Pipeline :
  1. Lire output/latest_lsv.json
  2. Claude -> script segmente
  3. DALL-E -> images photorealistes (fallback si pas de video Pexels)
  4. Pexels -> clips video stock 9:16
  5. ElevenLabs -> voiceover complet (hook + story, 55s)
  6. HeyGen -> 2 clips avatar (intro 3s + outro 5s)
  7. Creatomate -> assemblage final avec sous-titres
  8. Sauvegarde en queue (publication J+2)
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
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY", "")
HEYGEN_AVATAR_IDS = os.environ.get("HEYGEN_AVATAR_IDS", "")
CREATOMATE_API_KEY = os.environ.get("CREATOMATE_API_KEY", "")
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")


# -- Helpers ---------------------------------------------------------------

def api_request(url, data=None, headers=None, method=None):
    """Generic HTTP request helper."""
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
    """Upload file to tmpfiles.org, return direct download URL."""
    boundary = f"----Boundary{int(time.time())}"
    with open(file_path, "rb") as f:
        file_bytes = f.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        "https://tmpfiles.org/api/v1/upload",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "Mozilla/5.0 PharmaAlpha/1.0",
        },
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
    titre = lsv.get("titre", "")[:60]
    print(f"[1/8] LSV charge : {titre}...")
    return lsv


# -- Step 2: Claude Script ------------------------------------------------

SCRIPT_PROMPT = """Tu es le directeur creatif de Pharm'Alpha, chaine TikTok "Le Saviez-Vous" pharma/sante.
Style : HugoDecrypte pour la pharmacie. Ton conversationnel, dynamique, passionnant.
Format : 65 secondes. Structure HOOK -> FACECAM -> STORY -> OUTRO.

ARTICLE DU JOUR :
TITRE : {titre}
RESUME : {resume}
TEXTE COMPLET :
{full_text}

Cree un script TikTok de 65 secondes avec EXACTEMENT cette structure :

1. HOOK (5s) : accroche choc en voix off sur image/video animee. Le spectateur DOIT rester.
   La phrase doit etre COMPLETE en 5 secondes (pas coupee au milieu).

2. FACECAM INTRO (3s) : Stephen dit juste "Salut c'est Stephen, pharmacien !" — RIEN d'autre.

3. STORY (50s) : l'histoire complete en voix off ininterrompue.
   Decouper en 4 segments pour les visuels, mais le texte voix off est CONTINU.
   - seg1 (12s) : contexte, mise en situation
   - seg2 (13s) : developpement, le fait principal
   - seg3 (13s) : le twist ou fait surprenant
   - seg4 (12s) : conclusion + "Pharmusez-vous bien !" + "Abonnez-vous a @pharmalpha et retrouvez nos actus sur actus.pharmalpha.fr"

4. FACECAM OUTRO (5s) : phrase loop qui connecte SEAMLESSLY au debut du hook.
   Quand TikTok relance la video, le spectateur doit continuer a regarder sans s'en rendre compte.

REGLES TITRES / TEXTE :
- titre_tiktok : style conversationnel, PAS de majuscules agressives. Ex : "Quand on vendait des sirops a l'opium aux bebes..."
- screen_text : phrases courtes, percutantes, style sous-titre viral
- Le hook doit donner envie de rester, pas choquer gratuitement

REGLES VISUELS :
- Chaque segment a un "video_search" (mots-cles EN ANGLAIS pour chercher une video stock Pexels)
- ET un "image_prompt" en fallback (si pas de video trouvee) : photorealistic, editorial, Canon EOS R5
- video_search doit etre CONCRET et FILMABLE (pas abstrait) : "pharmacy bottles shelf", "baby sleeping crib", etc.

Reponds UNIQUEMENT en JSON valide :
{{
  "hook": {{
    "voiceover": "Accroche choc, phrase COMPLETE en 5 sec (~20 mots max)",
    "screen_text": "Texte ecran percutant (max 8 mots)",
    "video_search": "mots-cles anglais pour video stock Pexels",
    "image_prompt": "Fallback DALL-E : photorealistic editorial, Canon EOS R5...",
    "duration": 5
  }},
  "facecam_intro": {{
    "speech": "Salut c'est Stephen, pharmacien !",
    "duration": 3
  }},
  "story": {{
    "full_voiceover": "Texte voix off COMPLET et CONTINU pour les 50s de story (seg1+seg2+seg3+seg4 enchaines). ~170 mots. Rythme soutenu, pas de pause. Se termine par 'Pharmusez-vous bien ! Abonnez-vous a @pharmalpha et retrouvez nos actus sur actus.pharmalpha.fr'",
    "segments": [
      {{
        "id": "seg1",
        "screen_text": "Sous-titre percutant (max 10 mots)",
        "video_search": "mots-cles anglais concrets pour Pexels",
        "image_prompt": "Fallback DALL-E photorealistic...",
        "duration": 12
      }},
      {{
        "id": "seg2",
        "screen_text": "Sous-titre percutant (max 10 mots)",
        "video_search": "mots-cles anglais concrets",
        "image_prompt": "Fallback DALL-E photorealistic...",
        "duration": 13
      }},
      {{
        "id": "seg3",
        "screen_text": "Sous-titre percutant (max 10 mots)",
        "video_search": "mots-cles anglais concrets",
        "image_prompt": "Fallback DALL-E photorealistic...",
        "duration": 13
      }},
      {{
        "id": "seg4",
        "screen_text": "Pharmusez-vous bien !",
        "video_search": "mots-cles anglais concrets",
        "image_prompt": "Fallback DALL-E photorealistic...",
        "duration": 12
      }}
    ]
  }},
  "facecam_outro": {{
    "speech": "Phrase loop qui connecte seamlessly au debut du hook (5s max)",
    "duration": 5
  }},
  "titre_tiktok": "Titre conversationnel accrocheur (max 80 car, PAS de majuscules agressives)",
  "description_tiktok": "Description + hashtags (max 300 car)",
  "hashtags": "#lesaviezvous #pharmalpha #pharmacie #sante",
  "thumbnail_prompt": "Prompt DALL-E thumbnail impactante, vertical 9:16, photorealistic"
}}"""


def generate_tiktok_script(lsv):
    print("[2/8] Generation du script TikTok via Claude...")
    prompt = SCRIPT_PROMPT.format(
        titre=lsv.get("titre", ""),
        resume=lsv.get("resume", ""),
        full_text=lsv.get("full_text", ""),
    )
    resp = api_request(
        "https://api.anthropic.com/v1/messages",
        data={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        },
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
    print(f"  Script genere : {script.get('titre_tiktok', '')[:50]}...")
    return script


# -- Step 3: DALL-E Images ------------------------------------------------

def generate_images(script):
    """Generate DALL-E fallback images. Returns {label: url}."""
    print("[3/8] Generation des images DALL-E (fallback)...")
    prompts = [("hook", script.get("hook", {}).get("image_prompt", ""))]
    for seg in script.get("story", {}).get("segments", []):
        prompts.append((seg["id"], seg.get("image_prompt", "")))
    prompts = [(k, v) for k, v in prompts if v]

    image_urls = {}
    for label, prompt in prompts:
        if "photorealistic" not in prompt.lower():
            prompt = f"Photorealistic editorial photography, {prompt}, natural lighting, shot on Canon EOS R5, no text overlay"
        try:
            resp = api_request(
                "https://api.openai.com/v1/images/generations",
                data={"model": "dall-e-3", "prompt": prompt, "n": 1,
                      "size": "1024x1792", "quality": "hd", "style": "natural"},
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            )
            url = resp["data"][0]["url"]
            img_path = OUTPUT_DIR / f"{label}.png"
            urllib.request.urlretrieve(url, str(img_path))
            image_urls[label] = url
            print(f"  {label} : OK")
        except Exception as e:
            print(f"  [WARN] Image {label} : {e}")

    # Thumbnail
    thumb_prompt = script.get("thumbnail_prompt", "")
    if thumb_prompt:
        try:
            resp = api_request(
                "https://api.openai.com/v1/images/generations",
                data={"model": "dall-e-3", "prompt": thumb_prompt, "n": 1,
                      "size": "1024x1792", "quality": "hd", "style": "natural"},
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            )
            urllib.request.urlretrieve(resp["data"][0]["url"], str(OUTPUT_DIR / "thumbnail.png"))
            print("  thumbnail : OK")
        except Exception as e:
            print(f"  [WARN] thumbnail : {e}")

    return image_urls


# -- Step 4: Pexels Videos ------------------------------------------------

def search_pexels_video(query, orientation="portrait"):
    """Search Pexels for a stock video. Returns URL or None."""
    if not PEXELS_API_KEY:
        return None
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://api.pexels.com/videos/search?query={encoded}&orientation={orientation}&size=medium&per_page=5"
        resp = api_request(url, headers={"Authorization": PEXELS_API_KEY})
        videos = resp.get("videos", [])
        for video in videos:
            for vf in video.get("video_files", []):
                if vf.get("quality") == "hd" and vf.get("width", 0) <= 1080:
                    return vf["link"]
            # Fallback: any file
            if video.get("video_files"):
                return video["video_files"][0]["link"]
    except Exception as e:
        print(f"    [WARN] Pexels search '{query}' : {e}")
    return None


def fetch_pexels_videos(script):
    """Fetch stock videos for each segment. Returns {label: url}."""
    print("[4/8] Recherche videos stock Pexels...")
    video_urls = {}

    # Hook video
    hook_search = script.get("hook", {}).get("video_search", "")
    if hook_search:
        url = search_pexels_video(hook_search)
        if url:
            video_urls["hook"] = url
            print(f"  hook : OK ({hook_search})")
        else:
            print(f"  hook : pas de video, fallback image")

    # Story segments
    for seg in script.get("story", {}).get("segments", []):
        search = seg.get("video_search", "")
        if search:
            url = search_pexels_video(search)
            if url:
                video_urls[seg["id"]] = url
                print(f"  {seg['id']} : OK ({search})")
            else:
                print(f"  {seg['id']} : pas de video, fallback image")

    return video_urls


# -- Step 5: ElevenLabs Voiceover -----------------------------------------

def generate_voiceover(script):
    """Generate single continuous voiceover (hook + story). Returns (path, url)."""
    print("[5/8] Generation voix off ElevenLabs (continue, 55s)...")

    hook_text = script.get("hook", {}).get("voiceover", "")
    story_text = script.get("story", {}).get("full_voiceover", "")
    full_text = f"{hook_text} {story_text}".strip()

    audio_bytes = api_request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
        data={
            "text": full_text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75,
                "style": 0.3,
                "use_speaker_boost": True,
            },
        },
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Accept": "audio/mpeg"},
    )

    audio_path = OUTPUT_DIR / "voiceover.mp3"
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)
    print(f"  Voix off : {len(audio_bytes) / 1024:.0f} KB")

    vo_url = upload_temp(audio_path)
    print(f"  Uploadee : {vo_url[:50]}...")
    return audio_path, vo_url, full_text


# -- Step 6: HeyGen Avatar Clips ------------------------------------------

def get_today_avatar_id():
    if not HEYGEN_AVATAR_IDS:
        return None
    ids = [x.strip() for x in HEYGEN_AVATAR_IDS.split(",") if x.strip()]
    return ids[datetime.now().timetuple().tm_yday % len(ids)] if ids else None


def generate_heygen_clip(text, label, avatar_id):
    """Generate HeyGen clip with ElevenLabs pre-generated audio."""
    print(f"  HeyGen {label} : generation...")

    # Pre-generate speech audio
    audio_bytes = api_request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
        data={
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75,
                               "style": 0.3, "use_speaker_boost": True},
        },
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Accept": "audio/mpeg"},
    )
    audio_path = OUTPUT_DIR / f"speech_{label}.mp3"
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)
    audio_url = upload_temp(audio_path)

    try:
        resp = api_request(
            "https://api.heygen.com/v2/video/generate",
            data={
                "video_inputs": [{
                    "character": {"type": "avatar", "avatar_id": avatar_id, "avatar_style": "normal"},
                    "voice": {"type": "audio", "audio_url": audio_url},
                    "background": {"type": "color", "value": "#f0f0f0"},
                }],
                "test": False,
                "dimension": {"width": 1080, "height": 1920},
            },
            headers={"X-Api-Key": HEYGEN_API_KEY},
        )
        video_id = resp.get("data", {}).get("video_id")
        if not video_id:
            print(f"  [WARN] HeyGen {label} : pas de video_id")
            return None

        for attempt in range(60):
            time.sleep(5)
            st = api_request(
                f"https://api.heygen.com/v1/video_status.get?video_id={video_id}",
                headers={"X-Api-Key": HEYGEN_API_KEY},
            )
            status = st.get("data", {}).get("status", "")
            if status == "completed":
                video_url = st["data"]["video_url"]
                clip_path = OUTPUT_DIR / f"avatar_{label}.mp4"
                urllib.request.urlretrieve(video_url, str(clip_path))
                print(f"  HeyGen {label} : OK ({attempt * 5}s)")
                return video_url
            elif status == "failed":
                print(f"  [WARN] HeyGen {label} echoue : {st.get('data', {}).get('error', '')}")
                return None

        print(f"  [WARN] HeyGen {label} timeout")
        return None
    except Exception as e:
        print(f"  [WARN] HeyGen {label} : {e}")
        return None


def generate_avatar_clips(script):
    """Generate intro (3s) + outro (5s) avatar clips."""
    print("[6/8] Generation clips avatar HeyGen (intro + outro)...")
    avatar_id = get_today_avatar_id()
    if not avatar_id:
        print("  [SKIP] Pas d'avatar -> mode 100% anime")
        return None, None

    intro_text = script.get("facecam_intro", {}).get("speech", "Salut c'est Stephen, pharmacien !")
    outro_text = script.get("facecam_outro", {}).get("speech", "")

    intro_url = generate_heygen_clip(intro_text, "intro", avatar_id)
    outro_url = generate_heygen_clip(outro_text, "outro", avatar_id) if outro_text else None
    return intro_url, outro_url


# -- Step 7: Creatomate Assembly -------------------------------------------

def build_subtitle_elements(full_text, start_time, total_duration):
    """Generate word-by-word subtitle elements for the voiceover."""
    words = full_text.split()
    if not words:
        return []

    # Group words into chunks of 3-4 for readability
    chunks = []
    i = 0
    while i < len(words):
        chunk_size = 3 if len(words) - i > 4 else len(words) - i
        chunks.append(" ".join(words[i:i + chunk_size]))
        i += chunk_size

    chunk_duration = total_duration / len(chunks) if chunks else 1
    elements = []

    for idx, chunk in enumerate(chunks):
        t = start_time + idx * chunk_duration
        elements.append({
            "type": "text",
            "text": chunk,
            "x": "50%", "y": "70%", "width": "90%",
            "time": t,
            "duration": chunk_duration,
            "font_family": "Montserrat",
            "font_weight": "900",
            "font_size": "9 vmin",
            "fill_color": "#ffffff",
            "stroke_color": "#000000",
            "stroke_width": "2",
            "x_alignment": "50%",
            "y_alignment": "50%",
            "animations": [{"type": "text-appear", "split": "word", "duration": 0.15}],
        })

    return elements


def build_creatomate_source(script, image_urls, video_urls, voiceover_url, vo_text,
                             intro_url, outro_url):
    """Build Creatomate render source JSON."""
    elements = []
    t = 0

    hook_dur = script.get("hook", {}).get("duration", 5)
    intro_dur = script.get("facecam_intro", {}).get("duration", 3)
    outro_dur = script.get("facecam_outro", {}).get("duration", 5)
    segments = script.get("story", {}).get("segments", [])
    story_dur = sum(seg.get("duration", 12) for seg in segments)

    # ── 1. HOOK (5s) — animation + voix ElevenLabs ───────────────────────────
    hook_visual = video_urls.get("hook") or image_urls.get("hook")
    if hook_visual:
        media_type = "video" if "hook" in video_urls else "image"
        el = {
            "type": media_type, "source": hook_visual,
            "x": "50%", "y": "50%", "width": "100%", "height": "100%",
            "time": t, "duration": hook_dur,
        }
        if media_type == "image":
            el["animations"] = [{"type": "scale", "start_scale": "100%", "end_scale": "115%", "easing": "linear"}]
        elements.append(el)

    # Hook screen text
    hook_text = script.get("hook", {}).get("screen_text", "")
    if hook_text:
        elements.append({
            "type": "text", "text": hook_text,
            "x": "50%", "y": "78%", "width": "85%",
            "time": t, "duration": hook_dur,
            "font_family": "Montserrat", "font_weight": "900", "font_size": "9 vmin",
            "fill_color": "#ffffff", "stroke_color": "#000000", "stroke_width": "2",
            "x_alignment": "50%", "y_alignment": "50%",
            "animations": [{"type": "text-appear", "split": "word", "duration": 0.2}],
        })

    # Start voiceover at hook (runs through hook + story)
    vo_total = hook_dur + story_dur
    elements.append({
        "type": "audio", "source": voiceover_url,
        "time": t, "duration": vo_total,
    })
    t += hook_dur

    # ── 2. FACECAM INTRO (3s) — avatar ───────────────────────────────────────
    if intro_url:
        elements.append({
            "type": "video", "source": intro_url,
            "x": "50%", "y": "50%", "width": "100%", "height": "100%",
            "time": t, "duration": intro_dur,
        })
    t += intro_dur

    # ── 3. STORY SEGMENTS (50s) — animations + sous-titres ───────────────────
    # Voiceover continues (started at 0, plays through hook + story)
    # But voiceover audio was started at t=0 with duration = hook_dur + story_dur
    # The story portion starts at offset hook_dur in the audio.
    # Since we already placed the full audio starting at t=0 playing for vo_total,
    # and the facecam intro is 3s of video overlay without its own audio track,
    # the voiceover keeps playing underneath the intro facecam too.
    # We need to PAUSE the voiceover during the facecam intro.
    # Solution: split voiceover into 2 parts: hook portion + story portion

    # Actually, let's redo the audio: place hook portion, then story portion after intro
    # Remove the full audio element we just added and replace with split approach
    elements = [e for e in elements if not (e.get("type") == "audio" and e.get("source") == voiceover_url)]

    # Hook audio (plays during hook)
    elements.append({
        "type": "audio", "source": voiceover_url,
        "time": 0, "duration": hook_dur,
        "trim_start": 0,
    })

    # Story audio (plays after intro, trimmed to skip hook portion)
    elements.append({
        "type": "audio", "source": voiceover_url,
        "time": t, "duration": story_dur,
        "trim_start": hook_dur,
    })

    # Build story subtitles from full_voiceover (story part only)
    story_text = script.get("story", {}).get("full_voiceover", "")
    subtitle_elements = build_subtitle_elements(story_text, t, story_dur)
    elements.extend(subtitle_elements)

    # Segment visuals
    for seg in segments:
        seg_id = seg["id"]
        seg_dur = seg.get("duration", 12)

        visual = video_urls.get(seg_id) or image_urls.get(seg_id)
        if visual:
            media_type = "video" if seg_id in video_urls else "image"
            el = {
                "type": media_type, "source": visual,
                "x": "50%", "y": "50%", "width": "100%", "height": "100%",
                "time": t, "duration": seg_dur,
            }
            if media_type == "image":
                # Alternate Ken Burns direction
                idx = int(seg_id.replace("seg", "")) if seg_id.startswith("seg") else 1
                if idx % 2 == 1:
                    el["animations"] = [{"type": "scale", "start_scale": "110%", "end_scale": "100%", "easing": "linear"}]
                else:
                    el["animations"] = [{"type": "scale", "start_scale": "100%", "end_scale": "110%", "easing": "linear"}]
            elements.append(el)

        t += seg_dur

    # ── 4. FACECAM OUTRO (5s) — loop phrase ──────────────────────────────────
    if outro_url:
        elements.append({
            "type": "video", "source": outro_url,
            "x": "50%", "y": "50%", "width": "100%", "height": "100%",
            "time": t, "duration": outro_dur,
        })
    else:
        # Fallback text
        outro_text = script.get("facecam_outro", {}).get("speech", "Pharmusez-vous bien !")
        fallback_img = image_urls.get("seg4") or image_urls.get("seg3") or image_urls.get("hook")
        if fallback_img:
            elements.append({
                "type": "image", "source": fallback_img,
                "x": "50%", "y": "50%", "width": "100%", "height": "100%",
                "time": t, "duration": outro_dur,
                "color_overlay": "rgba(0,0,0,0.4)",
            })
        elements.append({
            "type": "text", "text": outro_text,
            "x": "50%", "y": "50%", "width": "80%",
            "time": t, "duration": outro_dur,
            "font_family": "Montserrat", "font_weight": "900", "font_size": "7 vmin",
            "fill_color": "#ffffff", "stroke_color": "#000000", "stroke_width": "1.5",
            "x_alignment": "50%", "y_alignment": "50%",
        })
    t += outro_dur

    # ── WATERMARK ─────────────────────────────────────────────────────────────
    elements.append({
        "type": "text", "text": "@pharmalpha",
        "x": "50%", "y": "5%", "time": 0, "duration": t,
        "font_family": "Montserrat", "font_weight": "700", "font_size": "3.5 vmin",
        "fill_color": "rgba(255,255,255,0.7)",
        "x_alignment": "50%",
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
        st = api_request(
            f"https://api.creatomate.com/v1/renders/{render_id}",
            headers={"Authorization": f"Bearer {CREATOMATE_API_KEY}"},
        )
        state = st.get("status", "")
        if state == "succeeded":
            print("  Rendu termine !")
            return st.get("url", "")
        elif state == "failed":
            print(f"  [ERROR] Rendu echoue : {st.get('error_message', '')}")
            return None

    print("  [ERROR] Timeout 10 min")
    return None


def assemble_video(script, image_urls, video_urls, voiceover_url, vo_text,
                    intro_url, outro_url):
    print("[7/8] Assemblage video Creatomate...")
    source = build_creatomate_source(
        script, image_urls, video_urls, voiceover_url, vo_text,
        intro_url, outro_url,
    )

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


# -- Step 8: Save to Queue ------------------------------------------------

def save_to_queue(video_path, script):
    today = datetime.now().strftime("%Y-%m-%d")
    publish_date = (datetime.now() + timedelta(days=PUBLISH_DELAY_DAYS)).strftime("%Y-%m-%d")

    slot_dir = QUEUE_DIR / today
    slot_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(video_path, slot_dir / "video.mp4")
    for png in OUTPUT_DIR.glob("*.png"):
        shutil.copy2(png, slot_dir / png.name)

    with open(slot_dir / "script.json", "w", encoding="utf-8") as f:
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
    with open(slot_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"  Queue : {slot_dir}")
    print(f"  Publication prevue : {publish_date} a 18h30 Paris")
    return slot_dir


# -- Main ------------------------------------------------------------------

def main():
    print("=" * 60)
    print("PHARM'ACTUS TIKTOK v3 - Generation video")
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
        print("[INFO] HeyGen non configure -> pas de facecam")
    if not PEXELS_API_KEY:
        print("[INFO] Pexels non configure -> images DALL-E uniquement")

    lsv = load_lsv()
    script = generate_tiktok_script(lsv)

    with open(OUTPUT_DIR / "tiktok_script.json", "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    image_urls = generate_images(script)
    video_urls = fetch_pexels_videos(script)
    vo_path, vo_url, vo_text = generate_voiceover(script)
    intro_url, outro_url = generate_avatar_clips(script)
    video_path = assemble_video(script, image_urls, video_urls, vo_url, vo_text,
                                 intro_url, outro_url)

    if video_path:
        slot = save_to_queue(video_path, script)
        print()
        print("=" * 60)
        print(f"VIDEO EN QUEUE : {slot}")
        print(f"Publication dans {PUBLISH_DELAY_DAYS} jours a 18h30")
        print("=" * 60)
    else:
        print("\n[ERROR] Pipeline echoue")
        sys.exit(1)


if __name__ == "__main__":
    main()
