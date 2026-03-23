"""Generate specific DALL-E images for each article"""
import os, time, urllib.request
from openai import OpenAI
from pathlib import Path

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
ASSETS = Path(__file__).parent.parent / "assets"
ASSETS.mkdir(exist_ok=True)

# Prompts specifiques par article
IMAGES = [
    ("img_actu_2026_03_23_1.png",
     "Close-up of biosimilar medication vials lined up on a pharmacy counter with a pharmacist hand picking one, soft focus background of a French pharmacy interior, warm natural lighting, photorealistic"),
    ("img_actu_2026_03_23_2.png",
     "An Ozempic-style injection pen next to a pile of affordable generic medicine boxes, with an Indian market street blurred in the background, contrasting luxury vs accessibility, photorealistic editorial photo"),
    ("img_actu_2026_03_23_3.png",
     "A hospital emergency room corridor with red warning lights, a map of England and northern France on a screen in the background showing epidemic spread dots, dramatic moody lighting, photorealistic"),
    ("img_actu_2026_w12_1.png",
     "A closed French village pharmacy with green cross sign turned off, empty cobblestone street, a town hall with French flag in the background, melancholic warm sunset light, photorealistic"),
    ("img_actu_2026_w12_2.png",
     "A pharmacist in white coat reading an official document with a stamp and seal, the French Ordre des Pharmaciens logo visible, professional office setting, photorealistic"),
    ("img_actu_2026_w12_3.png",
     "A modern clinical research laboratory in France with scientists working on fast-track drug trials, glass vials and digital screens showing molecular structures, bright clean lighting, photorealistic"),
    ("img_actu_2026_w12_4.png",
     "Colorectal cancer screening kits being handed from a pharmacist to a patient across a pharmacy counter, Mars Bleu blue ribbon visible, friendly warm interaction, photorealistic"),
    ("img_actu_2026_w12_5.png",
     "A futuristic pharmacy trade show exhibition hall with AI robots, digital prescription screens, and pharmacists networking, modern convention center with bright LED displays, photorealistic"),
    ("img_lsv_1.png",
     "A willow tree by a river with its bark peeled showing white interior, next to a mortar and pestle with crushed bark and aspirin tablets, golden hour nature lighting, artistic editorial photo"),
    ("img_lsv_2.png",
     "A glowing neon green pharmacy cross at night on a Parisian building facade, with historical overlay showing its medieval origins, cinematic atmospheric lighting, photorealistic"),
    ("img_lsv_3.png",
     "Alexander Fleming's messy laboratory desk with petri dishes showing mold growing on bacteria cultures, vintage 1928 setting, warm sepia tones mixed with scientific blue, artistic editorial photo"),
    ("img_lsv_4.png",
     "A split image showing paracetamol pills on one side and a medical illustration of a human liver on the other, dramatic red warning tones on the liver side, clean medical editorial style"),
    ("img_lsv_5.png",
     "A confident French pharmacist in white coat with stethoscope writing a prescription at a pharmacy desk, patient sitting across, modern French pharmacy interior, warm professional lighting, photorealistic"),
]

for img_name, prompt in IMAGES:
    img_path = ASSETS / img_name
    if img_path.exists():
        print(f"SKIP {img_name}")
        continue

    print(f"GEN  {img_name}...")
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1792x1024",
            quality="standard",
            n=1
        )
        url = response.data[0].url
        urllib.request.urlretrieve(url, str(img_path))
        print(f"  OK")
        time.sleep(62)  # Rate limit: 1/min
    except Exception as e:
        print(f"  ERR: {e}")
        if "429" in str(e):
            print("  Waiting 65s...")
            time.sleep(65)
            try:
                response = client.images.generate(
                    model="dall-e-3", prompt=prompt,
                    size="1792x1024", quality="standard", n=1
                )
                urllib.request.urlretrieve(response.data[0].url, str(img_path))
                print(f"  OK (retry)")
                time.sleep(62)
            except Exception as e2:
                print(f"  ERR retry: {e2}")

print("\nDone!")
