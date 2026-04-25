#!/usr/bin/env python3
"""
TikTok Safety : censure les mots a risque pour eviter shadowban.

Strategie :
- Sous-titres / caption : remplace une lettre du mot par * (ex: cocaine -> c*caine)
- Voix off : detecte le mot dans les timestamps ElevenLabs et bipe l'audio
- Hashtags : retire les hashtags trop risques

Liste evolutive : a ajuster selon les retours TikTok.
"""

import math
import re
import struct
import wave
from pathlib import Path

# Mots/concepts notoirement shadowbannes ou flaggees sur TikTok
# Pour le contenu pharma/sante : focus drogues, mort violente, abus de medicaments
BANNED_WORDS = {
    # Drogues classiques
    "cocaine", "cocaïne", "cocaïnes", "coke", "crack",
    "heroine", "héroine", "héroïne", "heroin",
    "opium", "opiace", "opiacé", "opiate",
    "meth", "metamphetamine", "métamphétamine", "methamphetamine",
    "lsd", "ecstasy", "mdma",
    "ketamine", "kétamine",
    "weed", "marijuana", "cannabis",
    "fentanyl",
    "morphine",  # parfois flagge
    # Mort violente / suicide
    "suicide", "suicider", "suicidé",
    "overdose", "overdoses",
    # Termes medicaux a risque
    "xanax", "adderall", "oxycodone", "oxycontin",
}

# Hashtags officiellement risques (a ne PAS utiliser dans le caption)
BANNED_HASHTAGS = {
    "#cocaine", "#cocaïne", "#heroine", "#héroïne",
    "#opium", "#meth", "#crack", "#lsd", "#ecstasy",
    "#mdma", "#weed", "#marijuana", "#cannabis", "#fentanyl",
    "#suicide", "#overdose", "#drugs", "#drogue",
    "#kill", "#die", "#death",
}


def normalize(word):
    """Lowercase, strip accents and punctuation for comparison."""
    import unicodedata
    w = word.lower()
    w = unicodedata.normalize("NFD", w)
    w = "".join(c for c in w if unicodedata.category(c) != "Mn")
    w = re.sub(r"[^a-z]", "", w)
    return w


def is_banned(word):
    """Check si un mot (avec ou sans accents) est banni."""
    norm = normalize(word)
    if not norm:
        return False
    for banned in BANNED_WORDS:
        bnorm = normalize(banned)
        if norm == bnorm:
            return True
        # Match partiel pour pluriels/conjugaisons
        if len(bnorm) >= 5 and norm.startswith(bnorm[:-1]):
            return True
    return False


def censor_word(word):
    """Remplace une lettre du milieu par * pour rendre le mot moins detectable."""
    if len(word) < 3:
        return word
    # Identifie la position de la 2e ou 3e voyelle du mot (visible mais filtree)
    vowels = "aeiouAEIOUéèêëàâïîôöùûüÿ"
    indices = [i for i, c in enumerate(word) if c in vowels]
    if indices:
        # Censure la 2e voyelle si possible, sinon la 1ere
        idx = indices[1] if len(indices) > 1 else indices[0]
    else:
        idx = len(word) // 2
    return word[:idx] + "*" + word[idx + 1:]


def censor_text(text):
    """Censure tous les mots bannis dans un texte. Capture sans apostrophe initiale (L'opium -> 'L', 'opium')."""
    def repl(m):
        word = m.group(0)
        if is_banned(word):
            return censor_word(word)
        return word
    # \w+ sans apostrophe : "L'opium" -> matches separes "L" et "opium"
    return re.sub(r"\b\w+\b", repl, text, flags=re.UNICODE)


def censor_caption(caption):
    """Censure le caption : 1) filtre hashtags risques, 2) censure mots restants."""
    # 1. Filtre hashtags risques AVANT censure (pour matcher exactement)
    def repl_hashtag(m):
        tag = m.group(0)
        norm = "#" + normalize(tag[1:])
        if norm in BANNED_HASHTAGS:
            return ""
        return tag
    out = re.sub(r"#[\wéèêëàâïîôöùûüÿ]+", repl_hashtag, caption, flags=re.UNICODE)
    # 2. Censure les mots restants
    out = censor_text(out)
    # 3. Cleanup espaces multiples
    out = re.sub(r"  +", " ", out)
    out = re.sub(r" +\n", "\n", out)
    return out.strip()


def find_banned_positions(word_timestamps):
    """Retourne liste de (start_seconds, end_seconds) pour chaque mot banni dans le voiceover."""
    positions = []
    for w in word_timestamps:
        if is_banned(w["word"]):
            positions.append((w["start"], w["end"]))
    return positions


def censor_word_timestamps(word_timestamps):
    """Retourne une copie des timestamps avec les mots bannis remplaces par * dans 'word'."""
    out = []
    for w in word_timestamps:
        if is_banned(w["word"]):
            out.append({**w, "word": censor_word(w["word"])})
        else:
            out.append(dict(w))
    return out


def generate_beep_wav(duration_seconds, output_path, freq_hz=880, sample_rate=44100, volume=0.5):
    """Genere un beep WAV mono en sinusoide."""
    n_samples = int(duration_seconds * sample_rate)
    amplitude = int(volume * 32767)
    with wave.open(str(output_path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # Fade in/out 5ms pour eviter les clics
        fade_samples = int(0.005 * sample_rate)
        for i in range(n_samples):
            sample = math.sin(2 * math.pi * freq_hz * i / sample_rate)
            # Fade
            if i < fade_samples:
                sample *= i / fade_samples
            elif i > n_samples - fade_samples:
                sample *= (n_samples - i) / fade_samples
            wf.writeframes(struct.pack("<h", int(sample * amplitude)))


def beep_audio_at_positions(input_mp3_path, output_mp3_path, positions, freq_hz=880):
    """Bipe les sections [start, end] d'un MP3 en utilisant ffmpeg directement.

    Utilise imageio_ffmpeg.get_ffmpeg_exe() pour avoir ffmpeg meme sans install.
    Pas de dependance a pydub (qui requiert ffprobe).
    Return True si succes, False sinon.
    """
    if not positions:
        import shutil
        shutil.copy2(str(input_mp3_path), str(output_mp3_path))
        return True

    # Trouve ffmpeg : imageio_ffmpeg embarque > PATH
    ffmpeg = None
    try:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        import shutil
        ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("  [WARN] ffmpeg introuvable, beep audio skip")
        return False

    # Build filter_complex :
    # - voice  : volume=0 sur les positions bannies
    # - sine   : volume=0 sauf sur les positions bannies
    # - mix    : combine voice + sine
    enable_expr = "+".join(
        f"between(t,{s:.3f},{e:.3f})" for s, e in positions
    )

    filter_complex = (
        f"[0:a]volume=enable='{enable_expr}':volume=0[voice];"
        f"sine=frequency={freq_hz}:sample_rate=44100,"
        f"volume=enable='not({enable_expr})':volume=0,"
        f"volume=0.4[beep];"
        f"[voice][beep]amix=inputs=2:duration=first:dropout_transition=0[out]"
    )

    import subprocess
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "warning",
        "-i", str(input_mp3_path),
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-c:a", "libmp3lame", "-b:a", "128k",
        str(output_mp3_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=120)
        if result.returncode != 0:
            err = result.stderr.decode(errors="replace")[:300]
            print(f"  [WARN] ffmpeg beep echec : {err}")
            return False
        return True
    except Exception as e:
        print(f"  [WARN] ffmpeg subprocess : {e}")
        return False


if __name__ == "__main__":
    # Tests rapides
    tests = [
        "Tu savais que la cocaïne servait d'anesthésique ?",
        "L'opium était vendu en pharmacie.",
        "L'aspirine vient du saule.",
        "#fyp #pourtoi #cocaine #histoire",
    ]
    for t in tests:
        print(f"AVANT : {t}")
        print(f"APRES : {censor_text(t) if not t.startswith('#') else censor_caption(t)}")
        print()
