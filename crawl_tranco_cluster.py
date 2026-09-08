import os
import re
import csv
import io
import time
import zipfile
import asyncio
import urllib.parse
import httpx
from email_verifier import EmailVerifier
from config import DATA_DIR

TRANCO_ZIP = os.path.join(DATA_DIR, "tranco_top_1m.csv.zip")
INSTANTLY_CSV = os.path.join(DATA_DIR, "instantly_real_scraped_leads.csv")
VERIFIED_DIR = os.path.join(DATA_DIR, "verified_5k")

EMAIL_REGEX = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'

EXCLUSIONS = {
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'sentry', 'shopify.com',
    'w3.org', 'email.com', 'example.com', 'schema.org', 'cloudflare',
    'support@shopify', 'help@shopify', 'google.com', 'facebook.com',
    'twitter.com', 'instagram.com', 'github.com', 'spurit', 'klaviyo',
    'yotpo', 'judge.me', 'apps.shopify', 'myshopify.com', 'wordpress',
    'wix.com', 'squarespace.com', 'zendesk.com', 'intercom-mail'
}

INSTANTLY_HEADERS = [
    "First Name", "Last Name", "Email", "Secondary_Email", "Company", "Website",
    "Title", "Meta Ads Library URL", "Niche", "Country", "Personalized Icebreaker"
]

NICHE_KEYWORDS = {
    "Health & Supplements": [
        'supplement', 'vitamin', 'protein', 'nutrition', 'wellness', 'gut', 'fitness',
        'organic', 'remedy', 'herb', 'nootropic', 'collagen', 'pharma', 'bio', 'health',
        'cbd', 'hemp', 'serum', 'creatine', 'electrolytes', 'superfood', 'botanical'
    ],
    "Jewelry": [
        'jewelry', 'jewel', 'diamond', 'ring', 'chain', 'silver', 'gold', 'bracelet',
        'gem', 'necklace', 'earring', 'gemstone', 'bridal', 'pendant', 'customjewelry',
        'finejewelry', 'moissanite', 'cufflink'
    ],
    "Fashion Accessories": [
        'watch', 'wallet', 'bag', 'eyewear', 'sunglass', 'belt', 'hat', 'tote',
        'backpack', 'leather', 'purse', 'handbag', 'luggage', 'footwear', 'boot',
        'sneaker', 'optical', 'cases', 'scarf', 'beanie', 'cap', 'shades'
    ],
    "Extended DTC": [
        'skin', 'beauty', 'cosmetic', 'candle', 'pet', 'dog', 'cat', 'cookware',
        'coffee', 'tea', 'soap', 'scent', 'kitchen', 'glow', 'lash', 'hair',
        'fragrance', 'perfume', 'decor', 'baby', 'pan', 'blade', 'grooming'
    ],
    "Fashion & Apparel": [
        'clothing', 'apparel', 'wear', 'fashion', 'denim', 'shirt', 'dress', 'swim',
        'streetwear', 'athletic', 'hoodie', 'jeans', 'outfit', 'swimwear', 'activewear',
        'lingerie', 'tee', 'tailor', 'couture', 'boutique', 'jacket', 'legging', 'sweats'
    ]
}

def load_tranco_ecommerce_domains():
    print("[*] Extracting e-commerce brand domains from Tranco 1M archive...", flush=True)
    domains_by_niche = {n: [] for n in NICHE_KEYWORDS}
    other_ecom = []
    seen = set()

    excluded_exts = ('.edu', '.gov', '.mil', '.org', '.int', '.cn', '.ru', '.ir')
    excluded_terms = ['cdn', 'api', 'dev', 'static', 'mail', 'ns1', 'ns2', 'admin', 'portal', 'cloud', 'server', 'blog']
    ecom_indicators = ['shop', 'store', 'brand', 'market', 'goods', 'outlet', 'direct', 'boutique']

    with zipfile.ZipFile(TRANCO_ZIP, 'r') as z:
        name = z.namelist()[0]
        with z.open(name) as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding='utf-8', errors='ignore'))
            for row in reader:
                if len(row) < 2:
                    continue
                domain = row[1].lower().strip()
                if domain.endswith(excluded_exts):
                    continue
                if any(ex in domain for ex in excluded_terms):
                    continue

                matched = False
                for niche, kws in NICHE_KEYWORDS.items():
                    if any(kw in domain for kw in kws):
                        if domain not in seen:
                            seen.add(domain)
                            domains_by_niche[niche].append(domain)
                        matched = True
                        break

                if not matched and any(ind in domain for ind in ecom_indicators):
                    if domain not in seen:
                        seen.add(domain)
                        other_ecom.append(domain)

    # Interleave to prioritize underrepresented niches first
    prioritized_domains = []
    # 1. Health & Supplements
    prioritized_domains.extend([(d, "Health & Supplements") for d in domains_by_niche["Health & Supplements"]])
    # 2. Jewelry
    prioritized_domains.extend([(d, "Jewelry") for d in domains_by_niche["Jewelry"]])
    # 3. Fashion Accessories
    prioritized_domains.extend([(d, "Fashion Accessories") for d in domains_by_niche["Fashion Accessories"]])
    # 4. Extended DTC
    prioritized_domains.extend([(d, "Extended DTC") for d in domains_by_niche["Extended DTC"]])
    # 5. Fashion & Apparel
    prioritized_domains.extend([(d, "Fashion & Apparel") for d in domains_by_niche["Fashion & Apparel"]])
    # 6. General ecom
    prioritized_domains.extend([(d, "Extended DTC") for d in other_ecom])

    print(f"[*] Prepared {len(prioritized_domains):,} prioritized e-commerce brand domains.", flush=True)
    return prioritized_domains

class TrancoClusterCrawler:
    def __init__(self, concurrency: int = 40):
        self.concurrency = concurrency
        self.verifier = EmailVerifier(timeout=3)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    def clean_brand_name(self, domain: str) -> str:
        name = domain.split('.')[0]
        name = re.sub(r'^(shop|the|my|get|try|buy|store|wear)', '', name, flags=re.IGNORECASE)
        name = re.sub(r'(shop|store|online|co|brand|official)$', '', name, flags=re.IGNORECASE)
        if not name:
            name = domain.split('.')[0]
        return name.capitalize()

    def classify_store(self, text: str, domain: str, default_niche: str) -> tuple[str, str]:
        t = (text + " " + domain).lower()
        if any(w in t for w in ["supplement", "vitamin", "protein", "nutrition", "wellness", "gut", "sleep", "greens", "organic", "creatine"]):
            return "Health & Supplements", "Nutrition & Wellness"
        elif any(w in t for w in ["jewelry", "jewel", "necklace", "ring", "diamond", "chain", "bracelet", "earring", "silver", "gold"]):
            return "Jewelry", "Fine Jewelry & Chains"
        elif any(w in t for w in ["watch", "wallet", "bag", "sunglasses", "eyewear", "belt", "hat", "backpack", "tote"]):
            return "Fashion Accessories", "Bags & Everyday Accessories"
        elif any(w in t for w in ["skin", "serum", "beauty", "cosmetic", "cream", "shampoo", "candle", "pet", "dog", "cookware"]):
            return "Extended DTC", "Skincare & Home Goods"
        elif any(w in t for w in ["clothing", "apparel", "denim", "dress", "hoodie", "shirt", "jeans", "streetwear", "athletic"]):
            return "Fashion & Apparel", "Apparel & Streetwear"
        return default_niche, f"{default_niche} Goods"

    async def crawl_domain(self, domain: str, default_niche: str, client: httpx.AsyncClient) -> list[dict]:
        clean_d = domain.split('.')[0]
        paths = ["/pages/contact-us", "/pages/contact", "/contact-us", "/contact", "/pages/about-us", "", "/policies/privacy-policy", "/policies/terms-of-service"]
        candidates = []
        html_sample = ""

        for path in paths:
            url = f"https://{domain}{path}"
            try:
                r = await client.get(url, headers=self.headers)
                if r.status_code == 200:
                    html_sample += " " + r.text[:2500]
                    matches = re.findall(EMAIL_REGEX, r.text)
                    for m in matches:
                        m_clean = m.strip().strip('.').lower()
                        if not any(ex in m_clean for ex in EXCLUSIONS):
                            if clean_d in m_clean or m_clean.split('@')[1] in domain or any(d_part in m_clean for d_part in domain.split('.') if len(d_part) > 3):
                                candidates.append((100, m_clean))
                            elif any(k in m_clean for k in ['support@', 'care@', 'hello@', 'team@', 'founder@', 'service@', 'contact@', 'sales@']):
                                candidates.append((80, m_clean))
                            elif 'info@' in m_clean:
                                candidates.append((60, m_clean))
                            else:
                                candidates.append((40, m_clean))
                    if any(s == 100 for s, _ in candidates):
                        break
            except Exception:
                continue

        if not candidates:
            return []

        unique_emails = []
        seen_em = set()
        for _, em in candidates:
            if em not in seen_em:
                seen_em.add(em)
                unique_emails.append(em)

        brand_name = self.clean_brand_name(domain)
        niche, sub_niche = self.classify_store(html_sample, domain, default_niche)
        ads_url = f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&q={urllib.parse.quote(brand_name.lower())}&search_type=keyword_unordered&media_type=all"
        icebreaker = (
            f"Saw {brand_name}'s live campaigns in {sub_niche} — noticed a high-leverage opportunity to test "
            f"iterative UGC hooks and creative variations to scale Meta spend profitably."
        )

        leads_for_store = []
        for found_email in unique_emails:
            email_domain = found_email.split('@')[1]
            has_mx = await asyncio.to_thread(self.verifier.has_active_mx, email_domain)
            if not has_mx:
                continue

            email_user = found_email.split('@')[0].lower()
            if any(k in email_user for k in ['support', 'care', 'service', 'help']):
                title = "Customer Care / Operations Lead"
                first_name, last_name = "Support", "Lead"
            elif any(k in email_user for k in ['marketing', 'growth', 'media', 'press', 'pr']):
                title = "Head of Marketing & Growth"
                first_name, last_name = "Marketing", "Lead"
            elif any(k in email_user for k in ['info', 'contact', 'hello', 'team', 'sales', 'office', 'admin']):
                title = "Founder / Marketing Lead"
                first_name, last_name = "Founder", "Team"
            else:
                name_parts = re.split(r'[._-]', email_user)
                first_name = name_parts[0].capitalize()
                last_name = name_parts[1].capitalize() if len(name_parts) > 1 else "Founder"
                title = "Founder & Owner"

            other_emails = [e for e in unique_emails if e != found_email]
            sec_emails_str = "; ".join(other_emails)

            leads_for_store.append({
                "First Name": first_name,
                "Last Name": last_name,
                "Email": found_email,
                "Secondary_Email": sec_emails_str,
                "Company": brand_name,
                "Website": f"https://{domain}",
                "Title": title,
                "Meta Ads Library URL": ads_url,
                "Niche": niche,
                "Country": "United States" if domain.endswith(".com") else "International",
                "Personalized Icebreaker": icebreaker
            })

        return leads_for_store

    def print_progress(self, scanned: int, total: int, valid: int, start_time: float, niche_counts: dict):
        elapsed = time.time() - start_time
        pct = (scanned / total) * 100 if total else 0
        speed = (scanned / elapsed) if elapsed > 0 else 0
        rem_sec = ((total - scanned) / speed) if speed > 0 else 0
        rem_min = rem_sec / 60

        bar_len = 24
        filled = int(bar_len * (scanned / total)) if total else 0
        bar = "=" * filled + "-" * (bar_len - filled)

        summary = f"[CLUSTER-WORKER] [{bar}] {pct:5.1f}% | Scanned: {scanned:,}/{total:,} | Found: {valid:,} | Speed: {speed:.1f}/s | ETA: {rem_min:.1f}m"
        breakdown = " | ".join(f"{k.split()[0]}: {v}" for k, v in niche_counts.items())
        print(f"{summary}\n  --> Niches: {breakdown}", flush=True)

    async def run(self):
        print("[*] Launching Tranco Cluster High-Throughput Store Crawler...", flush=True)
        domain_tuples = load_tranco_ecommerce_domains()
        total_domains = len(domain_tuples)

        # Load existing leads to avoid any duplicates
        existing_domains = set()
        if os.path.exists(INSTANTLY_CSV):
            with open(INSTANTLY_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("Website"):
                        d = row["Website"].replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0].lower()
                        existing_domains.add(d)

        print(f"[*] Already scanned/present in CSV: {len(existing_domains):,} domains.", flush=True)
        remaining = [(d, n) for d, n in domain_tuples if d not in existing_domains]
        print(f"[*] Starting crawl on {len(remaining):,} fresh brand domains...", flush=True)

        scanned = 0
        valid = 0
        niche_counts = {n: 0 for n in NICHE_KEYWORDS}
        start_time = time.time()
        semaphore = asyncio.Semaphore(self.concurrency)
        write_lock = asyncio.Lock()

        async with httpx.AsyncClient(timeout=4, follow_redirects=True, verify=False) as client:
            async def worker(item):
                nonlocal scanned, valid
                d, default_niche = item
                async with semaphore:
                    res_list = await self.crawl_domain(d, default_niche, client)
                    scanned += 1

                    if res_list:
                        for res in res_list:
                            valid += 1
                            n = res.get("Niche", default_niche)
                            if n in niche_counts:
                                niche_counts[n] += 1
                            
                            # Thread-safe file append
                            async with write_lock:
                                with open(INSTANTLY_CSV, "a", newline="", encoding="utf-8") as f:
                                    writer = csv.DictWriter(f, fieldnames=INSTANTLY_HEADERS)
                                    writer.writerow(res)

                    if scanned % 25 == 0 or scanned <= 15:
                        self.print_progress(scanned, len(remaining), valid, start_time, niche_counts)

            tasks = [worker(item) for item in remaining]
            await asyncio.gather(*tasks)

        print(f"\n[OK] Cluster worker completed: {valid:,} new real leads verified into {INSTANTLY_CSV}", flush=True)

if __name__ == "__main__":
    crawler = TrancoClusterCrawler(concurrency=40)
    asyncio.run(crawler.run())
