import os
import csv
import re
from config import DATA_DIR

LIVE_115K_CSV = os.path.join(DATA_DIR, "shopify_master_115k.csv")
MASTER_CSV = os.path.join(DATA_DIR, "shopify_master_list.csv")
SLICES_DIR = os.path.join(DATA_DIR, "cluster_slices")
VERIFIED_DIR = os.path.join(DATA_DIR, "verified_5k")
os.makedirs(SLICES_DIR, exist_ok=True)
os.makedirs(VERIFIED_DIR, exist_ok=True)

NUM_WORKERS = 10
TARGET_PER_NICHE_STORES = 25000

KEYWORDS = {
    "Health & Supplements": [
        "supplement", "vitamin", "protein", "nutrition", "wellness", "gut", "sleep",
        "greens", "organic", "ayurved", "herbal", "remedy", "fitness", "nootropic",
        "collagen", "creatine", "electrolytes", "superfood", "botanical"
    ],
    "Jewelry": [
        "jewelry", "jewel", "diamond", "ring", "gold chain", "silver chain", "chain necklace",
        "bracelet", "earring", "gem", "gemstone", "bridal", "pendant", "cufflink", "moissanite",
        "bangle", "karat"
    ],
    "Fashion Accessories": [
        "watch", "wallet", "bag", "sunglasses", "eyewear", "belt", "hat", "backpack",
        "tote", "handbag", "luggage", "footwear", "purse", "shades", "beanie", "shoe", "sneaker", "optician"
    ],
    "Extended DTC": [
        "skin", "serum", "beauty", "cosmetic", "cream", "shampoo", "candle", "pet",
        "dog", "cookware", "haircare", "bodycare", "soap", "scent", "kitchen", "coffee", "tea"
    ],
    "Fashion & Apparel": [
        "clothing", "apparel", "wear", "fashion", "denim", "shirt", "dress", "swim",
        "streetwear", "athletic", "hoodie", "jeans", "outfit", "swimwear", "activewear", "boutique",
        "saree", "kurti", "loom", "textile", "suit"
    ]
}

def main():
    print("[*] Reading already verified domains to prevent any duplicates...", flush=True)
    seen_domains = set()
    master_v = os.path.join(VERIFIED_DIR, "instantly_master_ultra_verified.csv")
    if os.path.exists(master_v):
        with open(master_v, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                w = row.get("Website", "").replace("https://", "").replace("http://", "").split("/")[0].lower()
                if w:
                    seen_domains.add(w)

    print(f"[*] Found {len(seen_domains):,} already verified domains.", flush=True)

    niche_stores = {n: [] for n in KEYWORDS}

    # Step 1: Ingest high-converting active stores from shopify_master_115k.csv first
    if os.path.exists(LIVE_115K_CSV):
        print(f"[*] Step 1: Ingesting active stores with verified tech stacks from 115k list...", flush=True)
        with open(LIVE_115K_CSV, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                domain = row.get("domain", "").strip().lower()
                if not domain or domain in seen_domains:
                    continue

                brand = row.get("merchant_name", "")
                tags = row.get("tags", "")
                tech = row.get("technologies", "")
                comb = (domain + " " + brand + " " + tags + " " + tech).lower()

                for niche, kws in KEYWORDS.items():
                    if len(niche_stores[niche]) < TARGET_PER_NICHE_STORES:
                        if any(kw in comb for kw in kws):
                            niche_stores[niche].append({
                                "domain": domain,
                                "brand": brand,
                                "niche": niche,
                                "tech": tech,
                                "employees": row.get("employee_count_bucket", "11-50")
                            })
                            seen_domains.add(domain)
                            break

    print("\n[+] Stores after 115k Ingestion:")
    for n, s in niche_stores.items():
        print(f"    {n:22}: {len(s):,} stores")

    # Step 2: Fill remaining quota from 1.9M Shopify Master database
    if os.path.exists(MASTER_CSV) and any(len(s) < TARGET_PER_NICHE_STORES for s in niche_stores.values()):
        print(f"\n[*] Step 2: Supplementing remaining quotas from 1.9M master database...", flush=True)
        with open(MASTER_CSV, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                domain = row.get("domain", "").strip().lower()
                if not domain or domain in seen_domains:
                    continue

                brand = row.get("merchant_name", "")
                tags = row.get("tags", "")
                tech = row.get("technologies", "")
                comb = (domain + " " + brand + " " + tags + " " + tech).lower()

                for niche, kws in KEYWORDS.items():
                    if len(niche_stores[niche]) < TARGET_PER_NICHE_STORES:
                        if any(kw in comb for kw in kws):
                            niche_stores[niche].append({
                                "domain": domain,
                                "brand": brand,
                                "niche": niche,
                                "tech": tech,
                                "employees": row.get("employee_count_bucket", "11-50")
                            })
                            seen_domains.add(domain)
                            break

                if all(len(s) >= TARGET_PER_NICHE_STORES for s in niche_stores.values()):
                    break

    print("\n[+] Final Extracted Store Pools for 10-Worker Cluster:")
    for n, s in niche_stores.items():
        print(f"    {n:22}: {len(s):,} stores")

    # Combine and interleave across niches so each worker gets an even mix
    all_target_stores = []
    max_len = max(len(s) for s in niche_stores.values())
    for idx in range(max_len):
        for n in KEYWORDS:
            if idx < len(niche_stores[n]):
                all_target_stores.append(niche_stores[n][idx])

    print(f"\n[*] Total stores to partition: {len(all_target_stores):,}")

    # Partition into NUM_WORKERS slices
    worker_slices = [[] for _ in range(NUM_WORKERS)]
    for i, store in enumerate(all_target_stores):
        worker_slices[i % NUM_WORKERS].append(store)

    fields = ["domain", "brand", "niche", "tech", "employees"]
    for wid in range(NUM_WORKERS):
        slice_path = os.path.join(SLICES_DIR, f"slice_{wid}.csv")
        with open(slice_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(worker_slices[wid])
        print(f"[*] Slice {wid}: Saved {len(worker_slices[wid]):,} stores -> {slice_path}")

    print("\n[OK] Partitioning complete. Ready to deploy 10 parallel workers with 3.5s timeout!", flush=True)

if __name__ == "__main__":
    main()
