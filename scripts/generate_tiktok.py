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

Cree un script TikTok FLUIDE. Voix off continue du debut a la fin. Pas de facecam, juste clips video IA + voix ElevenLabs + sous-titres.

STRUCTURE :
1. HOOK (5s) : accroche CHOC, phrase complete en 5 secondes. Donne envie de rester.
2. STORY en 4 parties enchainees sans rupture (40s total) :
   - part1 (10s) : contexte
   - part2 (10s) : fait principal
   - part3 (10s) : twist ou developpement surprenant
   - part4 (10s) : conclusion + "Pharmusez-vous bien !" + LOOP PHRASE
   La LOOP PHRASE est la derniere phrase du voiceover. Elle doit se connecter NATURELLEMENT au debut du hook pour que la video tourne en boucle sans rupture.
   Ex si hook = "Tu savais que le mot carat vient des pharmaciens..." -> fin = "...et la prochaine fois que tu verras un bijou, tu y penseras."

REGLES CRITIQUES :
- full_voiceover = hook + story concatenes. MAXIMUM 130 mots. Rythme fluide, pas de pause.
- L'EXPRESSION "Pharmusez-vous bien !" DOIT apparaitre EXACTEMENT UNE FOIS, et UNIQUEMENT a la TOUTE FIN du voiceover, juste avant la loop phrase. JAMAIS au milieu.
- Ordre strict de fin : [...conclusion de l'histoire...] "Pharmusez-vous bien !" [LOOP PHRASE qui connecte au hook].
- Ecrire en FRANCAIS NATUREL avec les accents (é, è, à, ç, etc). PAS d'emoji, PAS de guillemets typographiques.
- Chaque partie a un "video_prompt" DETAILLE pour Grok Imagine (scene, action, mouvement, eclairage, cinematique).
  Ex : "Close-up of dark brown carob seeds being carefully poured onto a brass pharmacy scale, warm candlelight, medieval apothecary, cinematic slow motion"
  PAS de descriptions vagues. PAS de texte dans la video.
- music_mood parmi : medieval, epic, warm, mysterious, celebration
- titre_tiktok : conversationnel, PAS de majuscules agressives

JSON UNIQUEMENT :
{{
  "hook": {{
    "voiceover": "Accroche choc complete en 5 sec (~15-18 mots)",
    "video_prompt": "Scene detaillee cinematique..."
  }},
  "story": {{
    "full_voiceover": "Texte COMPLET hook + 4 parties enchainees. 130 mots MAX. Se termine par 'Pharmusez-vous bien !' puis LOOP PHRASE connectant au debut du hook.",
    "parts": [
      {{"id": "part1", "video_prompt": "Scene detaillee...", "duration": 10}},
      {{"id": "part2", "video_prompt": "Scene detaillee...", "duration": 10}},
      {{"id": "part3", "video_prompt": "Scene detaillee...", "duration": 10}},
      {{"id": "part4", "video_prompt": "Scene detaillee...", "duration": 10}}
    ]
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
    raw = match.group()
    # Parse robustly: find matching closing brace
    depth = 0
    end_pos = 0
    for i, c in enumerate(raw):
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end_pos = i + 1
                break
    script = json.loads(raw[:end_pos])
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


def generate_video_clips(script, target_story_dur):
    """Generate clips sized to match actual voice duration.

    target_story_dur = total duration voice needs for the story (after hook).
    Hook is always 5s. Story clips are split to fill target_story_dur.
    """
    print(f"[3/7] Generation clips video Grok (target story: {target_story_dur:.1f}s)...")
    clips = {}
    clip_durations = {}

    # Hook clip = 5s fixed
    hook_prompt = script.get("hook", {}).get("video_prompt", "")
    if hook_prompt:
        url = generate_grok_clip(hook_prompt, "hook", duration=5)
        if url:
            clips["hook"] = url
            clip_durations["hook"] = 5

    # Story: N clips of equal duration summing to target_story_dur
    parts = script.get("story", {}).get("parts", [])
    # Grok max 10s per clip -> minimum N clips = ceil(target / 10)
    import math
    n_needed = max(1, math.ceil(target_story_dur / 10))
    n_clips = max(n_needed, len(parts))  # use at least the parts Claude defined
    # Clamp each clip to [4, 10] seconds
    clip_dur = max(4, min(10, target_story_dur / n_clips))
    # Recompute n_clips so total matches exactly
    n_clips = math.ceil(target_story_dur / clip_dur)
    print(f"  Strategy : {n_clips} clips de {clip_dur:.1f}s (total story {n_clips * clip_dur:.1f}s)")

    # Reuse the prompts Claude provided, extend with hook prompt if needed
    prompts = [p.get("video_prompt", "") for p in parts if p.get("video_prompt")]
    if not prompts:
        prompts = [hook_prompt]
    while len(prompts) < n_clips:
        # Reuse existing prompts in rotation
        prompts.append(prompts[len(prompts) % len(parts)] if parts else hook_prompt)

    for i in range(n_clips):
        time.sleep(10)  # rate limit protection
        part_id = f"part{i+1}"
        url = generate_grok_clip(prompts[i], part_id, duration=int(round(clip_dur)))
        if url:
            clips[part_id] = url
            clip_durations[part_id] = clip_dur

    return clips, clip_durations


# -- Step 4: ElevenLabs Voiceover -----------------------------------------

def clean_text_for_tts(text):
    """Clean text for ElevenLabs: fix encoding issues, keep accents."""
    import unicodedata
    # Fix double-encoded UTF-8 (e.g. Ã© -> é)
    try:
        text = text.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    # Normalize unicode
    text = unicodedata.normalize('NFC', text)
    # Replace fancy quotes
    text = text.replace('\u2018', "'").replace('\u2019', "'")
    text = text.replace('\u201c', '"').replace('\u201d', '"')
    text = text.replace('\u00ab', '"').replace('\u00bb', '"')
    # Keep accents! Only remove non-printable chars
    text = ''.join(c for c in text if c.isprintable() or c in '\n\r\t ')
    # Replace "10eme" type patterns with spoken form
    import re
    text = re.sub(r'(\d+)(?:eme|ème)', r'\1ème', text)
    return text.strip()


def generate_voiceover(script):
    """Voiceover with word-level timestamps. Returns (path, url, word_timestamps)."""
    print("[4/7] Generation voix off ElevenLabs (avec timestamps)...")
    full_text = script.get("story", {}).get("full_voiceover", "")
    if not full_text:
        hook = script.get("hook", {}).get("voiceover", "")
        full_text = hook

    full_text = clean_text_for_tts(full_text)
    print(f"  Texte : {len(full_text)} chars, {len(full_text.split())} mots")

    # Use with-timestamps endpoint for word-level sync
    resp = api_request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/with-timestamps",
        data={
            "text": full_text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.85, "similarity_boost": 0.75,
                               "style": 0.1, "use_speaker_boost": True},
        },
        headers={"xi-api-key": ELEVENLABS_API_KEY},
    )

    # Response contains audio_base64 + alignment
    import base64
    audio_b64 = resp.get("audio_base64", "")
    alignment = resp.get("alignment", {})
    audio_bytes = base64.b64decode(audio_b64)

    path = OUTPUT_DIR / "voiceover.mp3"
    with open(path, "wb") as f:
        f.write(audio_bytes)
    print(f"  Voix off : {len(audio_bytes) / 1024:.0f} KB")

    # Extract word timestamps: {characters, character_start_times_seconds, character_end_times_seconds}
    word_timestamps = []
    chars = alignment.get("characters", [])
    starts = alignment.get("character_start_times_seconds", [])
    ends = alignment.get("character_end_times_seconds", [])

    if chars and starts and ends:
        current_word = ""
        word_start = 0
        for i, ch in enumerate(chars):
            if ch == " " or ch == "\n":
                if current_word:
                    word_timestamps.append({
                        "word": current_word,
                        "start": word_start,
                        "end": ends[i - 1] if i > 0 else starts[i],
                    })
                    current_word = ""
            else:
                if not current_word:
                    word_start = starts[i] if i < len(starts) else 0
                current_word += ch
        if current_word:
            word_timestamps.append({
                "word": current_word,
                "start": word_start,
                "end": ends[-1] if ends else 0,
            })
        print(f"  Timestamps : {len(word_timestamps)} mots synchronises")
    else:
        print("  [WARN] Pas de timestamps, fallback proportionnel")

    # Save timestamps for debug
    with open(OUTPUT_DIR / "word_timestamps.json", "w", encoding="utf-8") as f:
        json.dump(word_timestamps, f, ensure_ascii=False, indent=2)

    url = upload_temp(path)
    print(f"  Upload : OK")
    return path, url, full_text, word_timestamps


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
            "voice_settings": {"stability": 0.85, "similarity_boost": 0.75,
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

def build_subtitle_elements_from_timestamps(word_timestamps, audio_offset=0.0, max_duration=None):
    """Build subtitles from word timestamps, grouped by punctuation, min 1s each."""
    if not word_timestamps:
        return []

    # Clean: strip whitespace, skip empty words
    clean = [w for w in word_timestamps if w["word"].strip()]
    if not clean:
        return []

    # Group words into chunks: 2-3 words, break on punctuation
    chunks = []
    current = []
    for w in clean:
        current.append(w)
        word_text = w["word"]
        has_punct = any(p in word_text for p in ".!?,;:")
        if len(current) >= 3 or has_punct or len(" ".join(x["word"] for x in current)) > 22:
            chunks.append(current)
            current = []
    if current:
        if chunks:  # merge last small chunk with previous
            chunks[-1].extend(current)
        else:
            chunks.append(current)

    elements = []
    for idx, chunk in enumerate(chunks):
        text = " ".join(w["word"] for w in chunk).strip()
        # Strip trailing/leading punctuation for cleaner subtitle
        text = text.strip(" ,;")
        if not text:
            continue

        start = chunk[0]["start"] + audio_offset
        end = chunk[-1]["end"] + audio_offset
        dur = end - start

        # Enforce minimum 1s display, and extend to next chunk start if possible
        min_dur = 1.0
        if dur < min_dur:
            if idx + 1 < len(chunks):
                next_start = chunks[idx + 1][0]["start"] + audio_offset
                dur = min(min_dur, next_start - start)
            else:
                dur = min_dur

        if max_duration is not None and start + dur > max_duration:
            dur = max_duration - start
        if dur <= 0:
            continue

        elements.append({
            "type": "text",
            "text": text.upper(),
            "x": "50%", "y": "75%", "width": "90%",
            "time": round(start, 2),
            "duration": round(dur, 2),
            "font_family": "Oswald", "font_weight": "700",
            "font_size": "9 vmin",
            "fill_color": "#ffffff",
            "shadow_color": "rgba(0,0,0,0.95)", "shadow_blur": "10",
            "shadow_x": "4", "shadow_y": "4",
            "x_alignment": "50%", "y_alignment": "50%",
        })
    return elements


def build_subtitle_elements_fallback(text, start_time, duration):
    """Fallback: proportional subtitles if no timestamps available."""
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
            "font_family": "Oswald", "font_weight": "700",
            "font_size": "9 vmin",
            "fill_color": "#ffffff",
            "shadow_color": "rgba(0,0,0,0.95)", "shadow_blur": "10",
            "shadow_x": "4", "shadow_y": "4",
            "x_alignment": "50%", "y_alignment": "50%",
        })
    return elements


def build_creatomate_source(script, clips, clip_durations, voiceover_url, vo_text,
                             word_timestamps, hook_end_s, facecam_url):
    """Assemble timeline. Video duration = voice duration (computed from clips)."""
    elements = []
    t = 0.0

    hook_dur = clip_durations.get("hook", 5.0)
    # Compute total from clip_durations
    total_visual_dur = sum(clip_durations.values())

    # Use real voiceover duration (ends when voice ends)
    if word_timestamps:
        vo_actual_dur = word_timestamps[-1]["end"]
    else:
        vo_actual_dur = total_visual_dur

    # Music ends with voice (not video, so music tail doesn't persist)
    end_dur = max(vo_actual_dur, total_visual_dur)

    # Music
    mood = script.get("music_mood", "default")
    music_url = MUSIC_TRACKS.get(mood, MUSIC_TRACKS["default"])
    elements.append({
        "type": "audio", "source": music_url,
        "time": 0, "duration": round(end_dur, 2),
        "volume": "12%",
    })

    # Voiceover (full duration)
    elements.append({
        "type": "audio", "source": voiceover_url,
        "time": 0, "duration": round(vo_actual_dur, 2),
        "volume": "100%",
    })

    # Hook video clip (ajoute AVANT les sous-titres pour qu'ils soient par-dessus)
    if clips.get("hook"):
        elements.append({
            "type": "video", "source": clips["hook"],
            "x": "50%", "y": "50%", "width": "100%", "height": "100%",
            "time": t, "duration": hook_dur,
            "volume": "0%",
        })
    t += hook_dur

    # Story clips
    story_parts = sorted([k for k in clips.keys() if k.startswith("part")],
                          key=lambda x: int(x.replace("part", "")))
    for part_id in story_parts:
        part_dur = clip_durations.get(part_id, 10.0)
        elements.append({
            "type": "video", "source": clips[part_id],
            "x": "50%", "y": "50%", "width": "100%", "height": "100%",
            "time": round(t, 2), "duration": round(part_dur, 2),
            "volume": "0%",
        })
        t += part_dur

    total_dur_final = round(max(t, vo_actual_dur), 2)

    # ─── SOUS-TITRES EN DERNIER (pour qu'ils soient au-dessus des videos) ───
    if word_timestamps:
        elements.extend(build_subtitle_elements_from_timestamps(
            word_timestamps, audio_offset=0, max_duration=total_dur_final))
    else:
        elements.extend(build_subtitle_elements_fallback(vo_text, 0, vo_actual_dur))
    print(f"  Timeline : {total_dur_final}s (video {t:.1f}s, voice {vo_actual_dur:.1f}s)")

    return {
        "output_format": "mp4", "width": 1080, "height": 1920,
        "frame_rate": 30, "duration": total_dur_final,
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


def assemble_video(script, clips, clip_durations, vo_url, vo_text,
                    word_timestamps, hook_end_s, facecam_url):
    print("[6/7] Assemblage Creatomate...")
    source = build_creatomate_source(script, clips, clip_durations, vo_url, vo_text,
                                      word_timestamps, hook_end_s, facecam_url)
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

    # Facecam desactive : voix ElevenLabs + clips Grok uniquement

    lsv = load_lsv()
    script = generate_script(lsv)

    with open(OUTPUT_DIR / "tiktok_script.json", "w", encoding="utf-8") as f:
        json.dump(script, f, ensure_ascii=False, indent=2)

    # STEP 1: Generate voice first to know exact duration
    vo_path, vo_url, vo_text, word_timestamps = generate_voiceover(script)
    if word_timestamps:
        vo_actual_dur = word_timestamps[-1]["end"]
    else:
        vo_actual_dur = 45.0
    print(f"  Duree voix reelle : {vo_actual_dur:.1f}s")

    # STEP 2: Compute hook + story durations from voice
    # Hook = first ~5s of voice (end at first period/question mark near 5s)
    hook_end_s = 5.0
    for w in word_timestamps:
        if w["end"] > 4.0 and w["end"] < 7.0:
            if any(p in w["word"] for p in ".!?"):
                hook_end_s = w["end"]
                break
    story_dur = vo_actual_dur - hook_end_s
    print(f"  Hook : {hook_end_s:.1f}s | Story : {story_dur:.1f}s")

    # STEP 3: Generate clips sized to match voice
    clips, clip_durations = generate_video_clips(script, story_dur)
    print("[5/7] Facecam HeyGen desactive (pipeline fluide uniquement)")

    video_path = assemble_video(script, clips, clip_durations, vo_url, vo_text,
                                 word_timestamps, hook_end_s, None)

    if video_path:
        slot = save_to_queue(video_path, script)
        print()
        print("=" * 60)
        print(f"VIDEO EN QUEUE : {slot}")
        print(f"Publication dans {PUBLISH_DELAY_DAYS} jours")
        print("=" * 60)

        # Affiche le caption TikTok dans les logs
        caption_file = slot / "tiktok_caption.txt"
        if caption_file.exists():
            print()
            print("=" * 60)
            print("CAPTION TIKTOK (a copier-coller)")
            print("=" * 60)
            print(caption_file.read_text(encoding="utf-8"))
            print("=" * 60)
    else:
        print("\n[ERROR] Pipeline echoue")
        sys.exit(1)


if __name__ == "__main__":
    main()
