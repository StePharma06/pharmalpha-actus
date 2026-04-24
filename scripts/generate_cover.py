#!/usr/bin/env python3
"""
Genere automatiquement une image de couverture (cover) pour la video TikTok.

Usage (standalone) :
    python scripts/generate_cover.py output/tiktok/queue/2026-04-24/

Strategie :
- Prend une frame du clip part3 (moment central de l'histoire) a t=2.5s
- Format 9:16 (1080x1920), recadre si besoin
- Overlay : gradient noir en bas pour lisibilite
- Badge "PHARM'ACTUS" en haut (blanc + orange)
- Titre (titre_tiktok) centre dans la moitie basse, blanc + ombre noire
"""

import json
import sys
import subprocess
from pathlib import Path

try:
    import imageio.v2 as imageio
except ImportError:
    import imageio
from PIL import Image, ImageDraw, ImageFont


# Couleurs Pharm'Alpha
ORANGE = (249, 115, 22)
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

# Priorite de clips pour la frame : part3 > part2 > part4 > part1 > hook
CLIP_PRIORITY = ["part3", "part2", "part4", "part1", "hook"]

# Fonts candidates (par ordre de preference)
FONT_CANDIDATES_BOLD = [
    r"C:\Windows\Fonts\ariblk.ttf",
    r"C:\Windows\Fonts\impact.ttf",
    r"C:\Windows\Fonts\bahnschrift.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def find_font(size):
    for p in FONT_CANDIDATES_BOLD:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def extract_frame(video_path, t_seconds=2.5):
    """Extract a frame from video at t_seconds."""
    reader = imageio.get_reader(str(video_path))
    meta = reader.get_meta_data()
    fps = meta.get("fps", 24)
    duration = meta.get("duration", 10)
    target_t = min(t_seconds, max(0.5, duration - 0.5))
    frame_idx = int(target_t * fps)
    try:
        frame = reader.get_data(frame_idx)
    except Exception:
        frame = reader.get_data(0)
    reader.close()
    return Image.fromarray(frame)


def fit_to_9x16(img, target_w=1080, target_h=1920):
    """Resize and crop image to 1080x1920."""
    w, h = img.size
    src_ratio = w / h
    dst_ratio = target_w / target_h
    if src_ratio > dst_ratio:
        new_h = target_h
        new_w = int(w * target_h / h)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        img = img.crop((left, 0, left + target_w, target_h))
    else:
        new_w = target_w
        new_h = int(h * target_w / w)
        img = img.resize((new_w, new_h), Image.LANCZOS)
        if new_h >= target_h:
            top = (new_h - target_h) // 2
            img = img.crop((0, top, target_w, top + target_h))
        else:
            canvas = Image.new("RGB", (target_w, target_h), BLACK)
            canvas.paste(img, (0, (target_h - new_h) // 2))
            img = canvas
    return img


def add_bottom_gradient(img):
    """Add dark gradient from middle to bottom for text readability."""
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    half = h // 2
    for y in range(half, h):
        pct = (y - half) / half
        alpha = int(pct * 230)
        draw.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    img = img.convert("RGBA")
    return Image.alpha_composite(img, overlay)


def wrap_text(font, text, max_width_px):
    lines = []
    current = ""
    for word in text.split():
        test = (current + " " + word).strip()
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] > max_width_px and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def draw_title(img, title, font_size=90):
    """Draw title in the bottom half, wrapped, white with black shadow."""
    w, h = img.size
    font = find_font(font_size)
    max_width = w - 120
    lines = wrap_text(font, title, max_width)

    # Reduce font size if more than 3 lines
    while len(lines) > 3 and font_size > 50:
        font_size -= 6
        font = find_font(font_size)
        lines = wrap_text(font, title, max_width)

    line_height = int(font_size * 1.15)
    total_h = line_height * len(lines)
    y_start = int(h * 0.60) + (h * 0.35 - total_h) // 2

    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        tw = bbox[2] - bbox[0]
        x = (w - tw) // 2
        y = y_start + i * line_height
        # Ombre
        for dx, dy in [(-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, 2)]:
            draw.text((x + dx, y + dy), line, font=font, fill=BLACK)
        draw.text((x, y), line, font=font, fill=WHITE)
    return img


def draw_badge(img):
    """Draw PHARM'ACTUS badge at top."""
    w, h = img.size
    badge_font = find_font(42)
    draw = ImageDraw.Draw(img)

    pharm = "PHARM'"
    actus = "ACTUS"
    full = pharm + actus
    bbox = badge_font.getbbox(full)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    padding = 24

    rect_w = text_w + 2 * padding
    rect_h = text_h + 2 * padding
    bx = (w - rect_w) // 2
    by = 80

    # Rectangle noir 80% opacite
    draw.rectangle([(bx, by), (bx + rect_w, by + rect_h)], fill=(0, 0, 0, 220))

    # Texte
    tx = bx + padding
    ty = by + padding - bbox[1]
    bbox_p = badge_font.getbbox(pharm)
    w_p = bbox_p[2] - bbox_p[0]
    draw.text((tx, ty), pharm, font=badge_font, fill=WHITE)
    draw.text((tx + w_p, ty), actus, font=badge_font, fill=ORANGE)
    return img


def generate_cover(slot_dir):
    """Generate cover.jpg in slot_dir using script.json + part3.mp4."""
    slot = Path(slot_dir)
    script_file = slot / "script.json"
    if not script_file.exists():
        print(f"[ERROR] script.json introuvable dans {slot}")
        return None

    script = json.loads(script_file.read_text(encoding="utf-8"))
    title = script.get("titre_tiktok", "Le Saviez-Vous ?")
    # Nettoyer les emojis en fin de titre (optionnel, pour lisibilite)
    import re
    title_clean = re.sub(r"[^\w\s',!?àâäéèêëïîôöùûüÿç-]", "", title).strip()

    # Trouver un clip utilisable
    clip_path = None
    for clip_id in CLIP_PRIORITY:
        candidate = slot / f"{clip_id}.mp4"
        if candidate.exists():
            clip_path = candidate
            break
    if clip_path is None:
        print(f"[ERROR] aucun clip video trouve dans {slot}")
        return None

    print(f"[cover] frame depuis : {clip_path.name}")
    print(f"[cover] titre : {title_clean}")

    frame = extract_frame(clip_path, t_seconds=2.5)
    frame = fit_to_9x16(frame)
    frame = add_bottom_gradient(frame)
    frame = draw_title(frame, title_clean, font_size=90)
    frame = draw_badge(frame)

    out_path = slot / "cover.jpg"
    frame.convert("RGB").save(out_path, quality=92)
    print(f"[cover] saved : {out_path}")
    return out_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_cover.py <queue_slot_dir>")
        sys.exit(1)
    generate_cover(sys.argv[1])
