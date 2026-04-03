#!/usr/bin/env python3
"""
Pharm'Actus TikTok - Pipeline video v5
Style : VoxTemporis / StoryFrance / CortexRaconte / PetitProph

Structure :
  Hook video (5s) -> Story video clips (50s) -> Facecam CTA (7s) -> Slide fin (3s)
  Voix ElevenLabs ininterrompue sur hook + story.
  Clips video generes par Grok Imagine (xAI).
  Sous-titres mot par mot.
  Musique d'ambiance de fond (libre de droits).
  Facecam HeyGen pour CTA final.
  Slide fin avec logo Pharm'Alpha.
  RIEN d'autre sur la video (pas de watermark).
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
XAI_API_KEY = os.environ.get("XAI_API_KEY", "")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
HEYGEN_API_KEY = os.environ.get("HEYGEN_API_KEY", "")
HEYGEN_AVATAR_IDS = os.environ.get("HEYGEN_AVATAR_IDS", "")
CREATOMATE_API_KEY = os.environ.get("CREATOMATE_API_KEY", "")

# Musiques d'ambiance libres de droits (Archive.org, CC0)
MUSIC_TRACKS = {
    "medieval": "https://archive.org/download/medieval-instrumental-background-music/Cold%20Journey.mp3",
    "epic": "https://archive.org/download/medieval-instrumental-background-music/The%20Britons.mp3",
    "warm": "https://archive.org/download/medieval-instrumental-background-music/Royal%20Coupling.mp3",
    "mysterious": "https://archive.org/download/medieval-instrumental-background-music/Nordic%20Wist.mp3",
    "celebration": "https://archive.org/download/medieval-instrumental-background-music/Dancing%20at%20the%20Inn.mp3",
    "default": "https://archive.org/download/medieval-instrumental-background-music/Cold%20Journey.mp3",
}


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
    print(f"[1/7] LSV charge : {lsv.get('titre', '')[:60]}...")
    return lsv


# -- Step 2: Claude Script ------------------------------------------------

SCRIPT_PROMPT = """Tu es le narrateur de Pharm'Alpha, chaine TikTok "Le Saviez-Vous" pharma/sante.
Style : VoxTemporis, StoryFrance, CortexRaconte. Narration captivante, rythme soutenu, ton conversationnel.

ARTICLE DU JOUR :
TITRE : {titre}
RESUME : {resume}
TEXTE COMPLET :
{full_text}

Cree un script TikTok de 65 secondes. Voix off continue du debut a la fin.

STRUCTURE :
1. HOOK (5s) : accroche CHOC, phrase complete en 5 secondes. Donne envie de rester.
2. STORY en 5 parties enchainee sans rupture (50s total) :
   - part1 (10s) : mise en contexte
   - part2 (10s) : le fait principal
   - part3 (10s) : developpement ou anecdote
   - part4 (10s) : twist ou fait surprenant
   - part5 (10s) : conclusion + "Pharmusez-vous bien !"
3. FACECAM CTA (7s) : texte que Stephen dit face camera pour conclure. Ex : "Si cette histoire t'a plu, commente, partage et abonne-toi !"
4. SLIDE FIN (3s) : geree par le code (logo + "Abonne-toi")

REGLES :
- full_voiceover = hook + story concatenes (~55 secondes, ~190 mots). Rythme soutenu, pas de pause.
- facecam_cta = phrase courte pour le face camera final (7 sec max)
- Chaque partie a un "video_prompt" DETAILLE pour generer un clip video IA (Grok Imagine).
  Les prompts doivent etre ULTRA SPECIFIQUES et VISUELS. Decrire une SCENE avec action, mouvement, eclairage.
  Ex : "Close-up of dark brown carob seeds being carefully poured from an old hand onto a brass pharmacy scale, warm candlelight, medieval apothecary, cinematic slow motion"
  PAS de descriptions vagues. PAS de texte dans la video.
- music_mood : le mood de la musique d'ambiance parmi : medieval, epic, warm, mysterious, celebration
- titre_tiktok : conversationnel, PAS de majuscules agressives

JSON UNIQUEMENT :
{{
  "hook": {{
    "voiceover": "Accroche choc, phrase COMPLETE en 5 sec (~20 mots)",
    "video_prompt": "Scene detaillee pour clip video IA, mouvement, eclairage, cinematique..."
  }},
  "story": {{
    "full_voiceover": "Texte COMPLET hook + story (5 parties enchainees). ~190 mots, 55 sec. Se termine par 'Pharmusez-vous bien !'",
    "parts": [
      {{"id": "part1", "video_prompt": "Scene detaillee...", "duration": 10}},
      {{"id": "part2", "video_prompt": "Scene detaillee...", "duration": 10}},
      {{"id": "part3", "video_prompt": "Scene detaillee...", "duration": 10}},
      {{"id": "part4", "video_prompt": "Scene detaillee...", "duration": 10}},
      {{"id": "part5", "video_prompt": "Scene detaillee...", "duration": 10}}
    ]
  }},
  "facecam_cta": {{
    "speech": "Phrase CTA face camera (7s max). Ex: 'Si cette histoire t'a plu, laisse un commentaire et abonne-toi !'",
    "duration": 7
  }},
  "music_mood": "medieval|epic|warm|mysterious|celebration",
  "titre_tiktok": "Titre conversationnel accrocheur (max 80 car)",
  "description_tiktok": "Description + hashtags (max 300 car)",
  "hashtags": "#lesaviezvous #pharmalpha #pharmacie #sante",
  "tiktok_caption": "Caption COMPLET pret a copier-coller sur TikTok, optimise pour le SEO TikTok et la page Pour Toi. Structure : 1) Premiere ligne = hook accrocheur avec emoji (reprend le titre). 2) 2-3 lignes de description engageante avec mots-cles naturels (pharma, sante, histoire, medicament, etc). 3) CTA : 'Commente si tu savais !' ou 'Tag un pote pharmacien !'. 4) 15-20 hashtags melangeant populaires (#fyp #pourtoi #apprendresurtiktok #culture #histoire) et niches (#pharmacie #pharma #lesaviezvous #pharmalpha #sante #medicament #anecdote). Max 2200 caracteres."
}}"""


def generate_script(lsv):
    print("[2/7] Generation du script via Claude...")
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


# -- Step 3: Grok Imagine Video Clips -------------------------------------

def generate_grok_clip(prompt, label, duration=10):
    """Generate a video clip via xAI Grok Imagine. Returns public URL."""
    print(f"  {label} : generation ({duration}s)...")
    try:
        resp = api_request(
            "https://api.x.ai/v1/videos/generations",
            data={
                "model": "grok-imagine-video",
                "prompt": prompt,
                "duration": duration,
                "aspect_ratio": "9:16",
                "resolution": "720p",
            },
            headers={"Authorization": f"Bearer {XAI_API_KEY}"},
        )
        request_id = resp.get("request_id")
        if not request_id:
            print(f"  [WARN] {label} : pas de request_id")
            return None

        for attempt in range(60):
            time.sleep(5)
            result = api_request(
                f"https://api.x.ai/v1/videos/{request_id}",
                headers={"Authorization": f"Bearer {XAI_API_KEY}"},
            )
            status = result.get("status", "")
            if status == "done":
                video_url = result.get("video", {}).get("url", "")
                # Save locally for queue
                clip_path = OUTPUT_DIR / f"{label}.mp4"
                urllib.request.urlretrieve(video_url, str(clip_path))
                print(f"  {label} : OK ({attempt * 5}s)")
                return video_url
            elif status in ("failed", "expired"):
                print(f"  [WARN] {label} echoue : {result}")
                return None

        print(f"  [WARN] {label} timeout")
        return None
    except Exception as e:
        print(f"  [WARN] {label} : {e}")
        return None


def generate_video_clips(script):
    """Generate all video clips via Grok Imagine. Returns {label: url}."""
    print("[3/7] Generation clips video Grok Imagine...")
    clips = {}

    # Hook clip (5s)
    hook_prompt = script.get("hook", {}).get("video_prompt", "")
    if hook_prompt:
        url = generate_grok_clip(hook_prompt, "hook", duration=5)
        if url:
            clips["hook"] = url

    # Story clips (10s each)
    for part in script.get("story", {}).get("parts", []):
        part_id = part["id"]
        prompt = part.get("video_prompt", "")
        dur = part.get("duration", 10)
        if prompt:
            url = generate_grok_clip(prompt, part_id, duration=dur)
            if url:
                clips[part_id] = url

    return clips


# -- Step 4: ElevenLabs Voiceover -----------------------------------------

def generate_voiceover(script):
    """One continuous voiceover: hook + story. Returns (path, url)."""
    print("[4/7] Generation voix off ElevenLabs...")
    full_text = script.get("story", {}).get("full_voiceover", "")
    if not full_text:
        hook = script.get("hook", {}).get("voiceover", "")
        full_text = hook

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


# -- Step 5: HeyGen Facecam CTA -------------------------------------------

def get_today_avatar_id():
    if not HEYGEN_AVATAR_IDS:
        return None
    ids = [x.strip() for x in HEYGEN_AVATAR_IDS.split(",") if x.strip()]
    return ids[datetime.now().timetuple().tm_yday % len(ids)] if ids else None


def generate_facecam_cta(script):
    """Generate facecam CTA via HeyGen. Returns video URL."""
    print("[5/7] Generation facecam CTA HeyGen...")
    avatar_id = get_today_avatar_id()
    if not avatar_id or not HEYGEN_API_KEY:
        print("  [SKIP] Pas d'avatar HeyGen")
        return None

    cta_text = script.get("facecam_cta", {}).get("speech", "")
    if not cta_text:
        return None

    # Pre-generate speech via ElevenLabs
    print("  Speech CTA via ElevenLabs...")
    audio_bytes = api_request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
        data={
            "text": cta_text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75,
                               "style": 0.4, "use_speaker_boost": True},
        },
        headers={"xi-api-key": ELEVENLABS_API_KEY, "Accept": "audio/mpeg"},
    )
    audio_path = OUTPUT_DIR / "speech_cta.mp3"
    with open(audio_path, "wb") as f:
        f.write(audio_bytes)
    audio_url = upload_temp(audio_path)

    # Generate HeyGen clip
    print("  HeyGen CTA : generation...")
    try:
        resp = api_request(
            "https://api.heygen.com/v2/video/generate",
            data={
                "video_inputs": [{
                    "character": {"type": "avatar", "avatar_id": avatar_id,
                                  "avatar_style": "normal"},
                    "voice": {"type": "audio", "audio_url": audio_url},
                    "background": {"type": "color", "value": "#0f1117"},
                }],
                "test": False,
                "dimension": {"width": 1080, "height": 1920},
            },
            headers={"X-Api-Key": HEYGEN_API_KEY},
        )
        video_id = resp.get("data", {}).get("video_id")
        if not video_id:
            print(f"  [WARN] HeyGen CTA : pas de video_id")
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
                clip_path = OUTPUT_DIR / "facecam_cta.mp4"
                urllib.request.urlretrieve(video_url, str(clip_path))
                print(f"  HeyGen CTA : OK ({attempt * 5}s)")
                return video_url
            elif status == "failed":
                print(f"  [WARN] HeyGen CTA echoue : {st.get('data', {}).get('error', '')}")
                return None

        print("  [WARN] HeyGen CTA timeout")
        return None
    except Exception as e:
        print(f"  [WARN] HeyGen CTA : {e}")
        return None


# -- Step 6: Creatomate Assembly -------------------------------------------

def build_subtitle_elements(text, start_time, duration):
    """Sous-titres 3 mots, gros, blanc + ombre noire epaisse."""
    words = text.split()
    if not words:
        return []
    chunks = []
    for i in range(0, len(words), 3):
        chunks.append(" ".join(words[i:i + 3]))

    chunk_dur = duration / len(chunks)
    elements = []
    for idx, chunk in enumerate(chunks):
        elements.append({
            "type": "text",
            "text": chunk.upper(),
            "x": "50%", "y": "75%", "width": "90%",
            "time": round(start_time + idx * chunk_dur, 2),
            "duration": round(chunk_dur, 2),
            "font_family": "Montserrat", "font_weight": "800",
            "font_size": "9.5 vmin",
            "fill_color": "#ffffff",
            "shadow_color": "rgba(0,0,0,0.95)", "shadow_blur": "8",
            "shadow_x": "3", "shadow_y": "3",
            "x_alignment": "50%", "y_alignment": "50%",
        })
    return elements


def build_creatomate_source(script, clips, voiceover_url, vo_text,
                             facecam_url, logo_url):
    elements = []
    t = 0.0

    hook_dur = 5.0
    parts = script.get("story", {}).get("parts", [])
    story_dur = sum(p.get("duration", 10) for p in parts)
    cta_dur = script.get("facecam_cta", {}).get("duration", 7)
    slide_dur = 3.0
    vo_total = hook_dur + story_dur  # voiceover covers hook + story

    # Music mood
    mood = script.get("music_mood", "default")
    music_url = MUSIC_TRACKS.get(mood, MUSIC_TRACKS["default"])

    # ── BACKGROUND MUSIC (full duration, low volume) ─────────────────────────
    total_dur = hook_dur + story_dur + cta_dur + slide_dur
    elements.append({
        "type": "audio", "source": music_url,
        "time": 0, "duration": round(total_dur, 2),
        "volume": "12%",
    })

    # ── VOICEOVER (hook + story) ─────────────────────────────────────────────
    elements.append({
        "type": "audio", "source": voiceover_url,
        "time": 0, "duration": round(vo_total, 2),
        "volume": "100%",
    })

    # ── 1. HOOK (5s) — video clip ────────────────────────────────────────────
    if clips.get("hook"):
        elements.append({
            "type": "video", "source": clips["hook"],
            "x": "50%", "y": "50%", "width": "100%", "height": "100%",
            "time": t, "duration": hook_dur,
            "volume": "0%",  # mute clip audio, we have voiceover
        })

    # Hook subtitles
    hook_vo = script.get("hook", {}).get("voiceover", "")
    if hook_vo:
        elements.extend(build_subtitle_elements(hook_vo, t, hook_dur))
    t += hook_dur

    # ── 2. STORY (5 × 10s) — video clips ────────────────────────────────────
    story_text = script.get("story", {}).get("full_voiceover", "")
    # Remove hook text from story text for subtitles (it's already in full_voiceover)
    if hook_vo and story_text.startswith(hook_vo):
        story_only = story_text[len(hook_vo):].strip()
    else:
        story_only = story_text

    story_words = story_only.split()
    total_story_words = len(story_words)
    word_offset = 0

    for i, part in enumerate(parts):
        part_dur = part.get("duration", 10)
        part_id = part["id"]

        # Video clip
        if clips.get(part_id):
            elements.append({
                "type": "video", "source": clips[part_id],
                "x": "50%", "y": "50%", "width": "100%", "height": "100%",
                "time": round(t, 2), "duration": part_dur,
                "volume": "0%",
            })

        # Subtitles proportional
        part_word_count = max(1, int(total_story_words * part_dur / story_dur))
        if i == len(parts) - 1:
            part_word_count = total_story_words - word_offset
        part_words = story_words[word_offset:word_offset + part_word_count]
        if part_words:
            elements.extend(build_subtitle_elements(" ".join(part_words), t, part_dur))
        word_offset += part_word_count

        t += part_dur

    # ── 3. FACECAM CTA (7s) ─────────────────────────────────────────────────
    if facecam_url:
        elements.append({
            "type": "video", "source": facecam_url,
            "x": "50%", "y": "50%", "width": "100%", "height": "100%",
            "time": round(t, 2), "duration": cta_dur,
        })
    t += cta_dur

    # ── 4. SLIDE FIN (3s) — logo + "Abonne-toi" ─────────────────────────────
    # Fond sombre
    elements.append({
        "type": "shape", "shape": "rectangle",
        "fill_color": "#0f1117",
        "x": "50%", "y": "50%", "width": "100%", "height": "100%",
        "time": round(t, 2), "duration": slide_dur,
    })
    # Logo
    if logo_url:
        elements.append({
            "type": "image", "source": logo_url,
            "x": "50%", "y": "38%", "width": "50%",
            "time": round(t, 2), "duration": slide_dur,
            "color_filter": "invert(1)",  # invert black logo to white on dark bg
        })
    # "ABONNE-TOI"
    elements.append({
        "type": "text", "text": "ABONNE-TOI",
        "x": "50%", "y": "62%", "width": "80%",
        "time": round(t, 2), "duration": slide_dur,
        "font_family": "Montserrat", "font_weight": "900",
        "font_size": "12 vmin",
        "fill_color": "#f97316",
        "x_alignment": "50%", "y_alignment": "50%",
        "animations": [{"type": "scale", "start_scale": "80%", "end_scale": "100%",
                         "easing": "ease-out", "duration": 0.3}],
    })
    # @pharmalpha
    elements.append({
        "type": "text", "text": "@pharmalpha",
        "x": "50%", "y": "72%", "width": "80%",
        "time": round(t, 2), "duration": slide_dur,
        "font_family": "Montserrat", "font_weight": "600",
        "font_size": "6 vmin",
        "fill_color": "rgba(255,255,255,0.7)",
        "x_alignment": "50%", "y_alignment": "50%",
    })
    t += slide_dur

    return {
        "output_format": "mp4", "width": 1080, "height": 1920,
        "frame_rate": 30, "duration": round(t, 2),
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
            err = st.get("error_message", "")
            print(f"  [ERROR] Rendu echoue : {err}")
            return None

    print("  [ERROR] Timeout 10 min")
    return None


def assemble_video(script, clips, vo_url, vo_text, facecam_url, logo_url):
    print("[6/7] Assemblage Creatomate...")
    source = build_creatomate_source(script, clips, vo_url, vo_text,
                                      facecam_url, logo_url)
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


# -- Step 7: Save to Queue ------------------------------------------------

def save_to_queue(video_path, script):
    today = datetime.now().strftime("%Y-%m-%d")
    publish_date = (datetime.now() + timedelta(days=PUBLISH_DELAY_DAYS)).strftime("%Y-%m-%d")

    slot = QUEUE_DIR / today
    slot.mkdir(parents=True, exist_ok=True)

    shutil.copy2(video_path, slot / "video.mp4")
    for f in OUTPUT_DIR.glob("*.mp4"):
        if f.name != "tiktok_video.mp4":
            shutil.copy2(f, slot / f.name)

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

    # Caption TikTok pret a copier-coller
    caption = script.get("tiktok_caption", "")
    if not caption:
        titre = script.get("titre_tiktok", "")
        desc = script.get("description_tiktok", "")
        hashtags = script.get("hashtags", "")
        caption = f"{titre}\n\n{desc}\n\n{hashtags}"
    with open(slot / "tiktok_caption.txt", "w", encoding="utf-8") as f:
        f.write(caption)

    print(f"  Queue : {slot}")
    print(f"  Caption TikTok : tiktok_caption.txt")
    print(f"  Publication : {publish_date} a 18h30")
    return slot


# -- Main ------------------------------------------------------------------

def main():
    print("=" * 60)
    print("PHARM'ACTUS TIKTOK v5 - Grok Imagine + ElevenLabs")
    print(f"Date : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    missing = []
    for key in ["ANTHROPIC_API_KEY", "XAI_API_KEY", "ELEVENLABS_API_KEY",
                 "ELEVENLABS_VOICE_ID", "CREATOMATE_API_KEY"]:
        if not os.environ.get(key):
            missing.append(key)
    if missing:
        print(f"[ERROR] Cles manquantes : {', '.join(missing)}")
        sys.exit(1)

    if not HEYGEN_API_KEY:
        print("[INFO] HeyGen non configure -> pas de facecam CTA")

    # Upload logo for end slide
    logo_path = ROOT_DIR / "assets" / "logo_pharmalpha.png"
    logo_url = None
    if logo_path.exists():
        logo_url = upload_temp(logo_path)
        print(f"  Logo uploade : OK")

    lsv = load_lsv()
    script = generate_script(lsv)

    with open(OUTPUT_DIR / "tiktok_script.json", "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    clips = generate_video_clips(script)
    vo_path, vo_url, vo_text = generate_voiceover(script)
    facecam_url = generate_facecam_cta(script)
    video_path = assemble_video(script, clips, vo_url, vo_text, facecam_url, logo_url)

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
