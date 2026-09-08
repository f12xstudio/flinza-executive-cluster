import os
import csv
import glob
import re
from config import DATA_DIR

VERIFIED_DIR = os.path.join(DATA_DIR, "verified_5k")

CSV_HEADERS = [
    "First Name", "Last Name", "Email", "Secondary_Email", "Company", "Website", "Title",
    "Meta Ads Library URL", "Niche", "Country", "Instagram", "Facebook",
    "LinkedIn", "TikTok", "Twitter_X", "MX_Status", "DMARC_Status",
    "SPF_Status", "Gravatar_Found", "Deliverability_Score", "Personalized Icebreaker"
]

NICHE_FILES = {
    "Jewelry": os.path.join(VERIFIED_DIR, "jewelry_real_inboxes.csv"),
    "Fashion & Apparel": os.path.join(VERIFIED_DIR, "fashion_apparel_real_inboxes.csv"),
    "Fashion Accessories": os.path.join(VERIFIED_DIR, "fashion_accessories_real_inboxes.csv"),
    "Health & Supplements": os.path.join(VERIFIED_DIR, "health_supplements_real_inboxes.csv"),
    "Extended DTC": os.path.join(VERIFIED_DIR, "extended_dtc_real_inboxes.csv")
}

MASTER_VERIFIED_CSV = os.path.join(VERIFIED_DIR, "instantly_master_ultra_verified.csv")

OVERRIDES = {
    # Real Jewelry Brands
    'giva': 'Jewelry',
    'artkarat': 'Jewelry',
    'amama': 'Jewelry',
    'pehrsilver': 'Jewelry',
    'sonchafa': 'Jewelry',
    'dhwanibansal': 'Jewelry',
    'pratha': 'Jewelry',
    'etchcraft': 'Jewelry',
    'einaya': 'Jewelry',
    'sukkhi': 'Jewelry',
    'renaush': 'Jewelry',
    'diamondrensu': 'Jewelry',
    'ornatejewels': 'Jewelry',
    'leafyaffair': 'Jewelry',
    'shoprmcgems': 'Jewelry',
    'gemkart': 'Jewelry',
    'abagem': 'Jewelry',
    'bellarosagems': 'Jewelry',
    'houseofquadri': 'Jewelry',
    'bluestone': 'Jewelry',
    'caratlane': 'Jewelry',
    'tanishq': 'Jewelry',

    # Real Health & Supplements
    'nutrabox': 'Health & Supplements',
    'bioayurveda': 'Health & Supplements',
    'manaayurvedam': 'Health & Supplements',
    'himalayawellness': 'Health & Supplements',
    'indiahemporganics': 'Health & Supplements',
    'indiahempandco': 'Health & Supplements',
    'sasya': 'Health & Supplements',
    'artofliving': 'Health & Supplements',
    'kapiva': 'Health & Supplements',
    'oziva': 'Health & Supplements',
    'fastandup': 'Health & Supplements',
    'muscleblaze': 'Health & Supplements',

    # Real Apparel
    'zeelclothing': 'Fashion & Apparel',
    'bunaai': 'Fashion & Apparel',
    'fashor': 'Fashion & Apparel',
    'frenchcrown': 'Fashion & Apparel',
    'bummer': 'Fashion & Apparel',
    'thehandlooms': 'Fashion & Apparel',
    'shopethnos': 'Fashion & Apparel',
    'snitch': 'Fashion & Apparel',
    'bewakoof': 'Fashion & Apparel',

    # Real Accessories
    'helios': 'Fashion Accessories',
    'boat-lifestyle': 'Fashion Accessories',
    'hammer': 'Fashion Accessories',
    'fireboltt': 'Fashion Accessories',
    'neemans': 'Fashion Accessories',
    'urbanmonkey': 'Fashion Accessories',
    'gemopticians': 'Fashion Accessories',
    'bumsonthesaddle': 'Fashion Accessories',

    # Extended DTC (Beauty, Skincare, Pets, Food, Home)
    'pawsindia': 'Extended DTC',
    'detoxie': 'Extended DTC',
    'fuaointerio': 'Extended DTC',
    'fuaosanitaryware': 'Extended DTC',
    'cartrends': 'Extended DTC',
    'kitchenandhome': 'Extended DTC',
    'indulekha': 'Extended DTC',
    'swissbeauty': 'Extended DTC',
    'reequil': 'Extended DTC',
    'plumgoodness': 'Extended DTC',
    'veeba': 'Extended DTC',
    'nurserylive': 'Extended DTC',
    'sleepyowl': 'Extended DTC',
    'ragecoffee': 'Extended DTC',
    'happilo': 'Extended DTC',
    'headsupfortails': 'Extended DTC',
    'lakmeindia': 'Extended DTC',
    'juicychemistry': 'Extended DTC',
    'bellavitaorganic': 'Extended DTC',
    'devsmusic': 'Extended DTC',
    'codesustain': 'Extended DTC',
    'neonia': 'Extended DTC',
    'halfrate': 'Extended DTC',
    'resanskrit': 'Extended DTC',
    'aumnicrafts': 'Extended DTC',
    'seelove': 'Extended DTC',
    'kamakhyaa': 'Extended DTC',
    'urbancart': 'Extended DTC',
    'kent': 'Extended DTC',
    'kazeliving': 'Extended DTC',
    'justwowfactory': 'Extended DTC',
    'aubree': 'Extended DTC',
    'shinexpro': 'Extended DTC',
    'zestpics': 'Extended DTC',
    'gemeriahair': 'Extended DTC',
    'systemgemisch': 'Extended DTC',
    'runningemotion': 'Extended DTC',
    'gaugemagazine': 'Extended DTC',
    'sp-villa-management': 'Extended DTC'
}

JEWELRY_SUBSTRINGS = ['jewel', 'diamond', 'moissanite', 'gemstone', 'pendant', 'earring', 'necklace', 'bracelet', 'bangle', 'karat', 'gems']
JEWELRY_EXCLUSIONS = ['supplement', 'protein', 'vitamin', 'hair', 'optician', 'eyewear', 'auto', 'car', 'bike', 'cycle', 'villa', 'management', 'running', 'sport', 'sanitary', 'plumb', 'shoe', 'footwear', 'candle', 'pet', 'dog', 'cat', 'coffee', 'tea', 'cloth', 'apparel', 'dress', 'shirt', 'system', 'magazine']

HEALTH_SUBSTRINGS = ['supplement', 'vitamin', 'protein', 'nutrition', 'ayurved', 'herbal', 'wellness', 'gut health', 'immunity', 'nootropic', 'superfood', 'greens']
HEALTH_EXCLUSIONS = ['eyewear', 'jewelry', 'pet', 'dog', 'cat', 'auto', 'villa', 'shoe', 'cloth', 'apparel']

APPAREL_SUBSTRINGS = ['clothing', 'apparel', 'wear', 'dress', 'shirt', 'denim', 'jeans', 'hoodie', 'streetwear', 'boutique', 'swimwear', 'activewear', 'suit', 'saree', 'kurti', 'loom', 'textile', 'outfit']
APPAREL_EXCLUSIONS = ['jewel', 'diamond', 'supplement', 'vitamin', 'protein', 'dog', 'cat', 'pet', 'car', 'auto', 'sanitary', 'candle']

ACCESSORIES_SUBSTRINGS = ['watch', 'wallet', 'bag', 'eyewear', 'sunglasses', 'optician', 'belt', 'hat', 'footwear', 'shoe', 'handbag', 'tote', 'backpack', 'sneaker', 'purse', 'earphone', 'strap']
ACCESSORIES_EXCLUSIONS = ['supplement', 'protein', 'vitamin', 'auto', 'car', 'sanitary', 'dog', 'cat', 'pet', 'jewel', 'diamond']

def classify_lead(company, website, email):
    comb = (company + ' ' + website + ' ' + email).lower()

    # 1. Exact brand overrides
    for k, v in OVERRIDES.items():
        if k in comb:
            return v

    # 2. Jewelry
    if any(sub in comb for sub in JEWELRY_SUBSTRINGS) and not any(ex in comb for ex in JEWELRY_EXCLUSIONS):
        return 'Jewelry'

    # 3. Health & Supplements
    if any(sub in comb for sub in HEALTH_SUBSTRINGS) and not any(ex in comb for ex in HEALTH_EXCLUSIONS):
        return 'Health & Supplements'

    # 4. Fashion & Apparel
    if any(sub in comb for sub in APPAREL_SUBSTRINGS) and not any(ex in comb for ex in APPAREL_EXCLUSIONS):
        return 'Fashion & Apparel'

    # 5. Fashion Accessories
    if any(sub in comb for sub in ACCESSORIES_SUBSTRINGS) and not any(ex in comb for ex in ACCESSORIES_EXCLUSIONS):
        return 'Fashion Accessories'

    # 6. Default fallback to Extended DTC
    return 'Extended DTC'

def make_icebreaker(company, niche):
    niche_phrases = {
        "Jewelry": "Fine Jewelry & Precious Ornaments",
        "Fashion & Apparel": "Fashion & Apparel Collections",
        "Fashion Accessories": "Fashion Accessories & Lifestyle",
        "Health & Supplements": "Health, Wellness & Nutritional Supplements",
        "Extended DTC": "DTC & Consumer Goods"
    }
    phrase = niche_phrases.get(niche, "DTC Brand Marketing")
    return (
        f"Saw {company}'s live campaigns in {phrase} — noticed a high-leverage opportunity to test "
        f"iterative UGC hooks and creative variations to scale Meta spend profitably."
    )

def main():
    print("[*] Reading all verified records...", flush=True)
    all_leads = {}

    for p in glob.glob(os.path.join(VERIFIED_DIR, "*.csv")):
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                em = row.get("Email", "").strip().lower()
                if em and em not in all_leads:
                    all_leads[em] = row

    print(f"[*] Total unique verified leads: {len(all_leads):,}")

    classified_pools = {n: [] for n in NICHE_FILES}

    for em, row in all_leads.items():
        comp = row.get("Company", "")
        web = row.get("Website", "")
        correct_niche = classify_lead(comp, web, em)

        row["Niche"] = correct_niche
        row["Personalized Icebreaker"] = make_icebreaker(comp, correct_niche)

        clean_row = {k: row.get(k, "") for k in CSV_HEADERS}
        classified_pools[correct_niche].append(clean_row)

    print("\n[+] Rigorous Reclassification Complete:")
    for n, rows in classified_pools.items():
        print(f"    - {n:22}: {len(rows):,} leads")

    # Save to niche files
    for n, rows in classified_pools.items():
        out_path = NICHE_FILES[n]
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[OK] Saved {len(rows):,} leads -> {out_path}")

    # Save master
    all_rows = [r for rows in classified_pools.values() for r in rows]
    with open(MASTER_VERIFIED_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"[OK] Saved {len(all_rows):,} leads -> {MASTER_VERIFIED_CSV}")

if __name__ == "__main__":
    main()
