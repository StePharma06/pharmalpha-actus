"""Generate DALL-E images for all articles in index.html"""
import os, re, urllib.request
from openai import OpenAI

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(REPO, "index.html")
ASSETS = os.path.join(REPO, "assets")

# Read index.html and extract articles
with open(INDEX, "r", encoding="utf-8") as f:
    html = f.read()

# Find all articles with their id, titre, categorie, and image_url
pattern = r'id:\s*"([^"]+)".*?categorie:\s*"([^"]+)".*?titre:\s*"([^"]+)".*?image_url:\s*"([^"]*)"'
articles = re.findall(pattern, html, re.DOTALL)

CAT_STYLE = {
    "pharma_france": "French pharmacy, blue white red tones",
    "pharma_monde": "global pharmaceutical, blue tones, world map",
    "sante": "healthcare, medical, green and white tones",
    "lsv": "educational, curious, purple and warm tones"
}

generated = 0
for art_id, categorie, titre, existing_url in articles:
    img_name = f"img_{art_id}.png"
    img_path = os.path.join(ASSETS, img_name)

    # Skip if image already exists
    if os.path.exists(img_path):
        print(f"SKIP {art_id} (image exists)")
        continue

    style_hint = CAT_STYLE.get(categorie, "pharmacy, healthcare")
    prompt = f"Editorial illustration for a pharmacy news article titled '{titre}'. Style: {style_hint}. Clean modern digital art, no text, no logos, no watermarks, 16:9 landscape format."

    print(f"GEN  {art_id}: {titre[:50]}...")
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1792x1024",
            quality="standard",
            n=1
        )
        url = response.data[0].url
        urllib.request.urlretrieve(url, img_path)
        print(f"  OK -> {img_name}")
        generated += 1
    except Exception as e:
        print(f"  ERR: {e}")

# Update index.html with image_url paths
if generated > 0:
    for art_id, categorie, titre, existing_url in articles:
        img_name = f"img_{art_id}.png"
        img_path = os.path.join(ASSETS, img_name)
        if os.path.exists(img_path) and not existing_url:
            old = f'id: "{art_id}"'
            # Find the image_url line for this article and update it
            block_pattern = rf'(id:\s*"{re.escape(art_id)}".*?image_url:\s*)"([^"]*)"'
            html = re.sub(block_pattern, rf'\1"assets/{img_name}"', html, count=1, flags=re.DOTALL)

    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nDone! {generated} images generated, index.html updated.")
else:
    print("\nNo new images to generate.")
