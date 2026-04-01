#!/usr/bin/env python3
"""
Pharm'Actus TikTok - Publication differee
Publie la video la plus ancienne de la queue dont la date de publication est atteinte.

Execute quotidiennement a 18h30 Paris via GitHub Actions.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
QUEUE_DIR = ROOT_DIR / "output" / "tiktok" / "queue"
TIKTOK_ACCESS_TOKEN = os.environ.get("TIKTOK_ACCESS_TOKEN", "")


def api_request(url, data=None, headers=None, method=None):
    headers = headers or {}
    if data is not None and isinstance(data, dict):
        data = json.dumps(data).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    headers.setdefault("User-Agent", "PharmaAlpha/1.0")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=300) as resp:
        ct = resp.headers.get("Content-Type", "")
        raw = resp.read()
        if "json" in ct:
            return json.loads(raw)
        return raw


def find_video_to_publish():
    """Find the oldest video in the queue ready for publication."""
    if not QUEUE_DIR.exists():
        return None, None

    today = datetime.now().strftime("%Y-%m-%d")
    candidates = []

    for slot_dir in sorted(QUEUE_DIR.iterdir()):
        if not slot_dir.is_dir():
            continue
        meta_file = slot_dir / "metadata.json"
        if not meta_file.exists():
            continue

        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)

        if meta.get("published"):
            continue
        if meta.get("publish_date", "9999-99-99") > today:
            continue

        candidates.append((slot_dir, meta))

    if not candidates:
        return None, None

    # Oldest first
    candidates.sort(key=lambda x: x[1].get("generated_date", ""))
    return candidates[0]


def publish_to_tiktok(video_path, meta):
    """Publish video to TikTok via Content Posting API v2."""
    title = meta.get("titre", "Le Saviez-Vous ?")
    description = meta.get("description", "")
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
    status = status_resp.get("data", {}).get("status", "unknown")
    print(f"  Statut TikTok : {status}")
    return publish_id


def main():
    print("=" * 60)
    print("PHARM'ACTUS TIKTOK - Publication differee")
    print(f"Date : {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    if not TIKTOK_ACCESS_TOKEN:
        print("[SKIP] Pas de TIKTOK_ACCESS_TOKEN configure")
        print("Les videos restent en queue pour publication manuelle.")
        # List pending videos
        result = find_video_to_publish()
        if result and result[0]:
            slot_dir, meta = result
            print(f"\n  Video prete : {slot_dir.name}")
            print(f"  Titre : {meta.get('titre', '')}")
            print(f"  Generee : {meta.get('generated_date', '')}")
            print(f"  Prevue : {meta.get('publish_date', '')}")
        else:
            print("\n  Aucune video en attente de publication.")
        sys.exit(0)

    result = find_video_to_publish()
    if not result or not result[0]:
        print("[INFO] Aucune video a publier aujourd'hui.")
        sys.exit(0)

    slot_dir, meta = result
    video_path = slot_dir / "video.mp4"
    if not video_path.exists():
        print(f"[ERROR] Video introuvable : {video_path}")
        sys.exit(1)

    print(f"[PUBLISH] Video du {meta.get('generated_date', '?')}")
    print(f"  Titre : {meta.get('titre', '')}")
    print(f"  Prevue le : {meta.get('publish_date', '')}")

    try:
        publish_id = publish_to_tiktok(video_path, meta)
        if publish_id:
            meta["published"] = True
            meta["publish_id"] = publish_id
            meta["published_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            with open(slot_dir / "metadata.json", "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            print()
            print("=" * 60)
            print(f"VIDEO PUBLIEE sur TikTok ! (ID: {publish_id})")
            print(f"Slot : {slot_dir.name}")
            print("=" * 60)
        else:
            print("\n[ERROR] Publication echouee")
            sys.exit(1)

    except Exception as e:
        print(f"\n[ERROR] Publication echouee : {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
