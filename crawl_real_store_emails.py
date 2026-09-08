import os
import re
import csv
import time
import asyncio
import urllib.parse
import urllib.request
import httpx
from email_verifier import EmailVerifier
from config import DATA_DIR

OUTPUT_CSV = os.path.join(DATA_DIR, "real_scraped_store_leads.csv")
INSTANTLY_CSV = os.path.join(DATA_DIR, "instantly_real_scraped_leads.csv")

EMAIL_REGEX = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'

EXCLUSIONS = {
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'sentry', 'shopify.com',
    'w3.org', 'email.com', 'example.com', 'schema.org', 'cloudflare',
    'support@shopify', 'help@shopify', 'google.com', 'facebook.com',
    'twitter.com', 'instagram.com', 'github.com', 'spurit', 'klaviyo',
    'yotpo', 'judge.me', 'apps.shopify', 'myshopify.com'
}

def load_real_store_domains():
    urls = [
        'https://raw.githubusercontent.com/TeamDukaan/performance/master/shopify%20stores%20-%20shopify.csv',
        'https://gist.githubusercontent.com/alexfilatov/636dfa9d9a4b54eb0f13c21c21aa7597/raw',
        'https://raw.githubusercontent.com/chat-data-llc/shopify_store_traffic_api/main/data/stores_traffic.csv'
    ]
    domains = []
    seen = set()

    # 1. Load from online registries
    for u in urls:
        try:
            req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
            data = urllib.request.urlopen(req, timeout=15).read().decode('utf-8', errors='ignore')
            for line in data.splitlines():
                d = line.strip().replace('https://', '').replace('http://', '').replace('www.', '').split('/')[0].split(',')[0].lower()
                if d and '.' in d and ' ' not in d and not d.startswith(('url', 'store', 'http')):
                    if d not in seen:
                        seen.add(d)
                        domains.append(d)
        except Exception as e:
            print(f"[!] Error loading {u}: {e}")

    # 2. Load from 115k Master Shopify database if available locally
    local_master = os.path.join(DATA_DIR, "shopify_master_115k.csv")
    if os.path.exists(local_master):
        try:
            with open(local_master, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    d = row.get("domain", "").strip().lower()
                    if d and '.' in d and d not in seen:
                        seen.add(d)
                        domains.append(d)
            print(f"[*] Ingested {len(domains):,} total domains including 115k Shopify master list.")
        except Exception as e:
            print(f"[!] Error reading local 115k master: {e}")

    return domains

class StoreEmailCrawler:
    def __init__(self, concurrency: int = 35):
        self.concurrency = concurrency
        self.verifier = EmailVerifier(timeout=3)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    def clean_brand_name(self, domain: str) -> str:
        name = domain.split('.')[0]
        name = re.sub(r'^(shop|the|my|get|try|buy|store)', '', name, flags=re.IGNORECASE)
        name = re.sub(r'(shop|store|online|co|brand)$', '', name, flags=re.IGNORECASE)
        if not name:
            name = domain.split('.')[0]
        return name.capitalize()

    def classify_niche(self, text: str, domain: str) -> tuple[str, str]:
        t = (text + " " + domain).lower()
        # Health, Supplements & Herbal
        if any(w in t for w in ["supplement", "vitamin", "protein", "nutrition", "wellness", "gut", "sleep", "greens", "organic", "ayurved", "herbal", "remedy"]):
            return "Health & Supplements", "Nutrition & Wellness"
        # Fine Jewelry (use specific compound jewelry terms to prevent retail 'chain' collisions)
        elif any(w in t for w in ["jewelry", "jewel", "necklace", "ring", "diamond", "gold chain", "silver chain", "bracelet", "earring", "gemstone", "pendant", "cufflink"]):
            return "Jewelry", "Fine Jewelry & Chains"
        elif any(w in t for w in ["watch", "wallet", "bag", "sunglasses", "eyewear", "belt", "hat", "backpack", "tote", "handbag"]):
            return "Fashion Accessories", "Bags & Everyday Accessories"
        elif any(w in t for w in ["skin", "serum", "beauty", "cosmetic", "cream", "shampoo", "candle", "pet", "dog", "cookware", "haircare", "bodycare"]):
            return "Extended DTC", "Skincare & Home Goods"
        else:
            return "Fashion & Apparel", "Apparel & Streetwear"

    async def crawl_domain(self, domain: str, client: httpx.AsyncClient) -> dict | None:
        clean_d = domain.split('.')[0]
        # Prioritize dedicated contact and about pages BEFORE legal privacy policies
        paths = ["/pages/contact-us", "/pages/contact", "/contact-us", "/contact", "/pages/about-us", "", "/policies/privacy-policy", "/policies/terms-of-service"]
        
        candidates = []  # list of (score, email)
        html_sample = ""

        for path in paths:
            url = f"https://{domain}{path}"
            try:
                r = await client.get(url, headers=self.headers)
                if r.status_code == 200:
                    html_sample += " " + r.text[:2000]
                    matches = re.findall(EMAIL_REGEX, r.text)
                    for m in matches:
                        m_clean = m.strip().strip('.').lower()
                        if not any(ex in m_clean for ex in EXCLUSIONS):
                            # Scoring hierarchy:
                            # 100: Exact brand name inside the email (e.g. manaayurvedamservice@gmail.com or @manaayurvedam.com)
                            if clean_d in m_clean or m_clean.split('@')[1] in domain or any(d_part in m_clean for d_part in domain.split('.') if len(d_part) > 3):
                                candidates.append((100, m_clean))
                            # 80: Dedicated store customer care/founder email
                            elif any(k in m_clean for k in ['support@', 'care@', 'hello@', 'team@', 'founder@', 'service@', 'contact@', 'sales@']):
                                candidates.append((80, m_clean))
                            # 60: info@ or general contact
                            elif 'info@' in m_clean:
                                candidates.append((60, m_clean))
                            else:
                                candidates.append((40, m_clean))

                    # If we found a top-tier brand-matching email on a contact page, we can break early
                    if any(score == 100 for score, _ in candidates):
                        break
            except Exception:
                continue

        if not candidates:
            return []

        # Deduplicate emails while preserving order
        unique_emails = []
        seen_em = set()
        for _, em in candidates:
            if em not in seen_em:
                seen_em.add(em)
                unique_emails.append(em)

        brand_name = self.clean_brand_name(domain)
        niche, sub_niche = self.classify_niche(html_sample, domain)
        ads_url = f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&q={urllib.parse.quote(brand_name.lower())}&search_type=keyword_unordered&media_type=all"
        icebreaker = (
            f"Saw {brand_name}'s live campaigns in {sub_niche} — noticed a high-leverage opportunity to test "
            f"iterative UGC hooks and creative variations to scale Meta spend profitably."
        )

        leads_for_store = []

        for found_email in unique_emails:
            # Verify MX record for deliverability
            email_domain = found_email.split('@')[1]
            if not self.verifier.has_active_mx(email_domain):
                continue

            provider = self.verifier.classify_mail_provider(email_domain)
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
                "Email Status": f"Verified Real ({provider})",
                "Mail Provider": provider,
                "Company": brand_name,
                "Domain": domain,
                "Website": f"https://{domain}",
                "Title": title,
                "Meta Ads Library URL": ads_url,
                "Ad Active Signal": "High (Shopify Live Store)",
                "E-commerce Platform": "Shopify",
                "Niche": niche,
                "Sub-Niche": sub_niche,
                "Country": "United States" if domain.endswith(".com") else "International",
                "Employee Band": "11-50",
                "Personalized Icebreaker": icebreaker
            })

        return leads_for_store

    def print_progress(self, scanned: int, total: int, valid: int, start_time: float):
        elapsed = time.time() - start_time
        pct = (scanned / total) * 100 if total else 0
        speed = (scanned / elapsed) if elapsed > 0 else 0
        rem_sec = ((total - scanned) / speed) if speed > 0 else 0
        rem_min = rem_sec / 60
        
        # ASCII Progress Bar
        bar_len = 24
        filled = int(bar_len * (scanned / total)) if total else 0
        bar = "=" * filled + "-" * (bar_len - filled)

        print(f"[{bar}] {pct:5.1f}% | Scanned: {scanned:,}/{total:,} | Valid Inboxes: {valid:,} | Speed: {speed:.1f}/s | ETA: {rem_min:.1f}m", flush=True)

    async def run(self, max_leads: int = 25000):
        os.makedirs(DATA_DIR, exist_ok=True)
        domains = load_real_store_domains()
        total_domains = len(domains)
        print(f"[*] Loaded {total_domains:,} real store domains. Resuming email extraction...", flush=True)

        full_headers = [
            "First Name", "Last Name", "Title", "Email", "Secondary_Email", "Email Status",
            "Mail Provider", "Company", "Domain", "Website", "Meta Ads Library URL",
            "Ad Active Signal", "E-commerce Platform", "Niche", "Sub-Niche",
            "Country", "Employee Band", "Personalized Icebreaker"
        ]
        instantly_headers = [
            "First Name", "Last Name", "Email", "Secondary_Email", "Company", "Website",
            "Title", "Meta Ads Library URL", "Niche", "Country", "Personalized Icebreaker"
        ]

        # Check existing leads to resume
        existing_domains = set()
        valid_count = 0
        if os.path.exists(INSTANTLY_CSV):
            with open(INSTANTLY_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("Website"):
                        d = row["Website"].replace("https://", "").replace("http://", "").split("/")[0].lower()
                        existing_domains.add(d)
                        valid_count += 1
        else:
            with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=full_headers).writeheader()
            with open(INSTANTLY_CSV, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=instantly_headers).writeheader()

        print(f"[*] Resumed with {valid_count:,} already verified leads in CSV.", flush=True)

        remaining_domains = [d for d in domains if d not in existing_domains]
        scanned_count = len(existing_domains)
        start_time = time.time() - (scanned_count / 10 if scanned_count else 0)

        semaphore = asyncio.Semaphore(self.concurrency)

        async with httpx.AsyncClient(timeout=4, follow_redirects=True, verify=False) as client:
            async def worker(d):
                nonlocal valid_count, scanned_count
                if valid_count >= max_leads:
                    return
                async with semaphore:
                    res_list = await self.crawl_domain(d, client)
                    scanned_count += 1
                    
                    if res_list:
                        for item in res_list:
                            valid_count += 1
                            with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
                                csv.DictWriter(f, fieldnames=full_headers).writerow(item)
                            with open(INSTANTLY_CSV, "a", newline="", encoding="utf-8") as f:
                                csv.DictWriter(f, fieldnames=instantly_headers).writerow({k: item.get(k, "") for k in instantly_headers})

                    # Always show progress bar every 25 domains or on milestone
                    if scanned_count % 25 == 0 or scanned_count <= 20:
                        self.print_progress(scanned_count, total_domains, valid_count, start_time)

            tasks = [worker(d) for d in remaining_domains]
            await asyncio.gather(*tasks)

        print(f"\n[OK] Completed extraction: {valid_count:,} REAL verified leads into {OUTPUT_CSV}", flush=True)

if __name__ == "__main__":
    crawler = StoreEmailCrawler(concurrency=35)
    asyncio.run(crawler.run(max_leads=25000))
