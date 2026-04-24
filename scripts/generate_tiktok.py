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
# Creatomate removed — we now use Remotion locally (npm run render)

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
2. STORY en 5 parties enchainees sans rupture (~50s total) :
   - part1 (10s) : contexte
   - part2 (10s) : fait principal
   - part3 (10s) : twist ou developpement surprenant
   - part4 (10s) : consequence / developpement
   - part5 (10s) : conclusion + LOOP PHRASE
   La LOOP PHRASE est la derniere phrase du voiceover. Elle doit se connecter NATURELLEMENT au debut du hook pour que la video tourne en boucle sans rupture.
   Ex si hook = "Tu savais que le mot carat vient des pharmaciens..." -> fin = "...et la prochaine fois que tu verras un bijou, tu y penseras."

REGLES CRITIQUES :
- full_voiceover = hook + story concatenes. EXACTEMENT 140-150 mots (strict, pour ~50 secondes de voix). Rythme fluide, pas de pause.
- UTILISER les noms propres authentiques (Radithor, Eben Byers, dates, lieux) pour la credibilite historique. Ne pas generaliser "un riche industriel", ecrire "Eben Byers".
- Pour chaque partie, FOURNIR text_segment = les mots EXACTS du voiceover qui correspondent a ce clip video. Les text_segments concatenes doivent EGALER full_voiceover (sauf le hook, qui a son propre text).
- COHERENCE CRITIQUE : le video_prompt de chaque partie doit ILLUSTRER exactement ce que dit le text_segment. Si text dit "Eben Byers boit", le prompt doit montrer Eben Byers en train de boire. Si text dit "les medecins de l'epoque", prompt = medecins 1930s. Si text dit "aujourd'hui", prompt = moderne.
- NE PAS inclure "Pharmusez-vous bien" ni signature personnelle.
- Le voiceover doit se terminer par la LOOP PHRASE qui connecte naturellement au debut du hook.
- Ecrire en FRANCAIS NATUREL avec les accents. PAS d'emoji, PAS de guillemets typographiques.
- video_prompt en ANGLAIS, DETAILLE (scene, action, mouvement, eclairage, cinematique, epoque specifique).
  Ex : "Close-up of Eben Byers in 1920s golf attire drinking from a glowing green Radithor bottle, luxurious mansion library, warm lamplight, cinematic slow motion"
- music_mood parmi : medieval, epic, warm, mysterious, celebration
- titre_tiktok : conversationnel, PAS de majuscules agressives

JSON UNIQUEMENT :
{{
  "hook": {{
    "voiceover": "Accroche choc complete en 5 sec (~15-18 mots)",
    "video_prompt": "Scene detaillee cinematique..."
  }},
  "story": {{
    "full_voiceover": "Texte COMPLET hook + 5 parties enchainees. 150 mots MAX. Avec noms propres authentiques. Se termine par LOOP PHRASE.",
    "parts": [
      {{"id": "part1", "text_segment": "Mots EXACTS du voiceover pour ce clip (apres le hook)", "video_prompt": "Scene detaillee qui illustre ces mots"}},
      {{"id": "part2", "text_segment": "Mots EXACTS du voiceover pour ce clip", "video_prompt": "Scene illustrant"}},
      {{"id": "part3", "text_segment": "Mots EXACTS du voiceover pour ce clip", "video_prompt": "Scene illustrant"}},
      {{"id": "part4", "text_segment": "Mots EXACTS du voiceover pour ce clip", "video_prompt": "Scene illustrant"}},
      {{"id": "part5", "text_segment": "Mots EXACTS du voiceover pour ce clip (fin incluant loop phrase)", "video_prompt": "Scene illustrant"}}
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


def find_segment_duration(text_segment, word_timestamps):
    """Trouve la duree d'un text_segment dans le voiceover via les timestamps.
    Retourne (start_seconds, end_seconds, duration_seconds)."""
    if not text_segment or not word_timestamps:
        return None

    # Nettoie le segment en mots
    target_words = [w.lower().strip(".,;:!?'\"") for w in text_segment.split() if w.strip()]
    if not target_words:
        return None

    # Cherche la sequence de mots dans les timestamps (matching tolerant)
    vo_words = [(i, w["word"].lower().strip(".,;:!?'\""), w) for i, w in enumerate(word_timestamps)]
    target_len = len(target_words)

    for start_idx in range(len(vo_words) - target_len + 1):
        # Match approximatif (5 premiers mots)
        match = True
        check_count = min(5, target_len)
        for j in range(check_count):
            if vo_words[start_idx + j][1] != target_words[j]:
                match = False
                break
        if match:
            start_t = vo_words[start_idx][2]["start"]
            end_t = vo_words[min(start_idx + target_len - 1, len(vo_words) - 1)][2]["end"]
            return (start_t, end_t, end_t - start_t)

    return None


def generate_video_clips(script, target_story_dur, word_timestamps=None):
    """Generate clips sized to match each text_segment's actual duration in the voice."""
    print(f"[3/7] Generation clips video Grok (target story: {target_story_dur:.1f}s)...")
    clips = {}
    clip_durations = {}

    # Hook clip : duree = duree reelle du hook dans le voiceover
    hook_prompt = script.get("hook", {}).get("video_prompt", "")
    hook_text = script.get("hook", {}).get("voiceover", "")
    hook_dur_real = 5.0
    if word_timestamps and hook_text:
        seg = find_segment_duration(hook_text, word_timestamps)
        if seg:
            hook_dur_real = max(3.0, min(7.0, seg[2]))
            print(f"  Hook detecte : {hook_dur_real:.1f}s (dans la voix)")

    if hook_prompt:
        url = generate_grok_clip(hook_prompt, "hook", duration=int(round(hook_dur_real)))
        if url:
            clips["hook"] = url
            clip_durations["hook"] = hook_dur_real

    # Story parts : utilise text_segment + timestamps pour calculer la vraie duree
    parts = script.get("story", {}).get("parts", [])
    parts = [p for p in parts if p.get("video_prompt")]

    # Calcule duree reelle de chaque text_segment dans la voix
    for part in parts:
        text_seg = part.get("text_segment", "")
        dur = None
        if word_timestamps and text_seg:
            seg = find_segment_duration(text_seg, word_timestamps)
            if seg:
                dur = seg[2]

        # Fallback : repartition egale si pas de match
        if dur is None:
            dur = target_story_dur / max(1, len(parts))
            print(f"  {part['id']} : fallback {dur:.1f}s (text_segment non trouve)")
        else:
            print(f"  {part['id']} : {dur:.1f}s (sync avec voix)")

        # Clamp Grok [4, 10]
        dur = max(4.0, min(10.0, dur))
        part["_computed_duration"] = dur

    # Si somme des clips < target_story_dur, on ajoute un clip final en repetant le dernier
    total_planned = sum(p["_computed_duration"] for p in parts)
    remaining = target_story_dur - total_planned
    if remaining > 3.0 and parts:
        # Ajoute un clip supplementaire en utilisant le dernier prompt
        last = parts[-1].copy()
        last["id"] = f"part{len(parts) + 1}"
        last["_computed_duration"] = min(10.0, remaining)
        parts.append(last)
        print(f"  Ajout clip supplementaire : {last['_computed_duration']:.1f}s (gap de {remaining:.1f}s)")

    # Genere les clips
    for i, part in enumerate(parts):
        time.sleep(10)  # rate limit
        part_id = f"part{i+1}"
        dur = part["_computed_duration"]
        url = generate_grok_clip(part["video_prompt"], part_id, duration=int(round(dur)))
        if url:
            clips[part_id] = url
            clip_durations[part_id] = dur

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


CTA_TEXT = "Abonne-toi pour continuer à découvrir d'autres secrets surprenants de la médecine d'aujourd'hui et d'autrefois."


def generate_cta_voiceover():
    """Genere le voiceover CTA final (texte fixe)."""
    print("[4.5/7] Generation voix CTA ElevenLabs...")
    resp = api_request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}/with-timestamps",
        data={
            "text": CTA_TEXT,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.85, "similarity_boost": 0.75,
                               "style": 0.1, "use_speaker_boost": True},
        },
        headers={"xi-api-key": ELEVENLABS_API_KEY},
    )
    import base64
    audio_bytes = base64.b64decode(resp.get("audio_base64", ""))
    alignment = resp.get("alignment", {})

    path = OUTPUT_DIR / "voiceover_cta.mp3"
    with open(path, "wb") as f:
        f.write(audio_bytes)

    # Calcule la duree (dernier character end)
    ends = alignment.get("character_end_times_seconds", [])
    duration = ends[-1] if ends else 5.0

    # Upload
    cta_url = upload_temp(path)
    print(f"  CTA voix : {duration:.1f}s, {len(audio_bytes) / 1024:.0f} KB")
    return path, cta_url, duration


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


import subprocess


def build_remotion_props(script, clips, clip_durations, voiceover_url,
                         word_timestamps, hook_end_s, cta_url=None, cta_duration=0.0):
    """Build inputProps for Remotion TikTokPharmactus composition."""
    mood = script.get("music_mood", "default")
    music_url = MUSIC_TRACKS.get(mood, MUSIC_TRACKS["default"])

    # Build ordered clip list (hook first, then part1, part2, ...)
    ordered_clips = []
    if clips.get("hook"):
        ordered_clips.append({
            "url": clips["hook"],
            "durationInSeconds": clip_durations.get("hook", 5.0),
        })
    story_parts = sorted([k for k in clips.keys() if k.startswith("part")],
                          key=lambda x: int(x.replace("part", "")))
    for part_id in story_parts:
        ordered_clips.append({
            "url": clips[part_id],
            "durationInSeconds": clip_durations.get(part_id, 10.0),
        })

    # Normalize words for Remotion (keep word/start/end)
    words = []
    for w in (word_timestamps or []):
        words.append({
            "word": w["word"],
            "start": float(w["start"]),
            "end": float(w["end"]),
        })

    props = {
        "clips": ordered_clips,
        "voiceoverUrl": voiceover_url,
        "musicUrl": music_url,
        "words": words,
    }

    if cta_url:
        # Dernier clip de story reste en visuel pendant le CTA
        last_clip = ordered_clips[-1] if ordered_clips else None
        props["cta"] = {
            "voiceoverUrl": cta_url,
            "durationInSeconds": cta_duration,
            "pauseBeforeSeconds": 1.0,  # silence dramatique
            "backgroundClipUrl": last_clip["url"] if last_clip else "",
        }

    return props


def render_video_remotion(props, output_path):
    """Call Remotion CLI via Node.js to render the video locally."""
    print("  Rendu Remotion (local)...")
    renderer_dir = ROOT_DIR / "tiktok-renderer"
    props_path = OUTPUT_DIR / "remotion_props.json"

    with open(props_path, "w", encoding="utf-8") as f:
        json.dump(props, f, ensure_ascii=False, indent=2)

    cmd = [
        "node", str(renderer_dir / "scripts" / "render.mjs"),
        f"--input={props_path}",
        f"--output={output_path}",
    ]
    print(f"  Commande : {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(renderer_dir), capture_output=True, text=True)
    if result.returncode != 0:
        print("  [ERROR] Remotion render echoue :")
        print(result.stdout[-1500:])
        print(result.stderr[-1500:])
        return False
    print(result.stdout[-500:])
    return True


def assemble_video(script, clips, clip_durations, vo_url, vo_text,
                    word_timestamps, hook_end_s, facecam_url,
                    cta_url=None, cta_duration=0.0):
    print("[6/7] Assemblage Remotion...")
    props = build_remotion_props(script, clips, clip_durations, vo_url,
                                  word_timestamps, hook_end_s,
                                  cta_url=cta_url, cta_duration=cta_duration)
    with open(OUTPUT_DIR / "remotion_props.json", "w", encoding="utf-8") as f:
        json.dump(props, f, ensure_ascii=False, indent=2)

    video_path = OUTPUT_DIR / "tiktok_video.mp4"
    ok = render_video_remotion(props, video_path)
    if not ok or not video_path.exists():
        return None

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
                 "ELEVENLABS_VOICE_ID"]:
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

    # STEP 3: Generate clips sized to match voice (text_segment sync)
    clips, clip_durations = generate_video_clips(script, story_dur, word_timestamps)

    # Abort early if Grok failed for all clips (rate limit, quota, etc.)
    if len(clips) < 2:
        print()
        print("=" * 60)
        print(f"[ERROR] Seulement {len(clips)} clip(s) generes par Grok.")
        print("Cause probable : quota xAI epuise (HTTP 429).")
        print("Verifie : https://console.x.ai/")
        print("=" * 60)
        sys.exit(1)

    # STEP 3.5: Generate CTA voiceover (fixed text + Abonne-toi overlay)
    cta_path, cta_url, cta_dur = generate_cta_voiceover()
    print("[5/7] Facecam HeyGen desactive (pipeline fluide uniquement)")

    video_path = assemble_video(script, clips, clip_durations, vo_url, vo_text,
                                 word_timestamps, hook_end_s, None,
                                 cta_url=cta_url, cta_duration=cta_dur)

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
