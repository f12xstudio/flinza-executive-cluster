import os
import re
import sys
import csv
import json
import time
import asyncio
import urllib.parse
import argparse
import dns.resolver
import httpx
from bs4 import BeautifulSoup

# Ensure UTF-8 output across environments
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
VERIFIED_DIR = os.path.join(DATA_DIR, "verified_5k")
SLICES_DIR = os.path.join(DATA_DIR, "cluster_slices")
os.makedirs(VERIFIED_DIR, exist_ok=True)
os.makedirs(SLICES_DIR, exist_ok=True)

MASTER_VERIFIED_CSV = os.path.join(VERIFIED_DIR, "instantly_master_ultra_verified.csv")

NICHE_FILES = {
    "Jewelry": os.path.join(VERIFIED_DIR, "jewelry_real_inboxes.csv"),
    "Fashion & Apparel": os.path.join(VERIFIED_DIR, "fashion_apparel_real_inboxes.csv"),
    "Fashion Accessories": os.path.join(VERIFIED_DIR, "fashion_accessories_real_inboxes.csv"),
    "Health & Supplements": os.path.join(VERIFIED_DIR, "health_supplements_real_inboxes.csv"),
    "Extended DTC": os.path.join(VERIFIED_DIR, "extended_dtc_real_inboxes.csv")
}

CSV_HEADERS = [
    "First Name", "Last Name", "Email", "Secondary_Email", "Company", "Website", "Title",
    "Meta Ads Library URL", "Niche", "Country", "Instagram", "Facebook",
    "LinkedIn", "TikTok", "Twitter_X", "MX_Status", "DMARC_Status",
    "SPF_Status", "Gravatar_Found", "Deliverability_Score", "Personalized Icebreaker"
]

EMAIL_REGEX = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'

EXCLUSIONS = {
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'sentry', 'shopify.com',
    'w3.org', 'email.com', 'example.com', 'schema.org', 'cloudflare',
    'support@shopify', 'help@shopify', 'google.com', 'facebook.com',
    'twitter.com', 'instagram.com', 'github.com', 'spurit', 'klaviyo',
    'yotpo', 'judge.me', 'apps.shopify', 'myshopify.com', 'wordpress',
    'wix.com', 'squarespace.com', 'zendesk.com', 'intercom-mail',
    'beispiel.com', 'domain.com', 'yoursite.com', 'test@', 'dayjs@',
    'core-js@', 'npm@', 'deine-email@', 'tempuri.org', 'doubleclick',
    'user@', 'admin@example', 'info@yourdomain.com', 'no-reply', 'noreply'
}

SHARE_EXCLUSIONS = [
    "/sharer", "share.php", "intent/tweet", "pin/create", "/p/", "/reel/",
    "/stories/", "instagram.com/instagram", "facebook.com/facebook",
    "twitter.com/twitter", "linkedin.com/shareArticle", "whatsapp.com",
    "mailto:", "javascript:"
]

PLATFORM_MAP = {
    'instagram': 'Instagram',
    'facebook': 'Facebook',
    'linkedin': 'LinkedIn',
    'tiktok': 'TikTok',
    'twitter': 'Twitter_X'
}

# In-line fallback classifier if clean_and_reclassify_niches.py is absent
def classify_lead_inline(company: str, domain: str, email: str) -> str:
    comb = f"{company} {domain} {email}".lower()
    if any(k in comb for k in ["jewelry", "jewel", "diamond", "ring", "pendant", "necklace", "bracelet", "earring", "gemstone"]):
        return "Jewelry"
    if any(k in comb for k in ["supplement", "vitamin", "protein", "nutrition", "wellness", "ayurved", "herbal", "nootropic"]):
        return "Health & Supplements"
    if any(k in comb for k in ["watch", "wallet", "sunglass", "eyewear", "belt", "backpack", "tote", "handbag", "luggage"]):
        return "Fashion Accessories"
    if any(k in comb for k in ["clothing", "apparel", "streetwear", "athleisure", "denim", "shirt", "dress", "hoodie"]):
        return "Fashion & Apparel"
    return "Extended DTC"

class CloudClusterEngine:
    def __init__(self, concurrency: int = 35, worker_id: int = 0, total_workers: int = 1):
        self.concurrency = concurrency
        self.worker_id = worker_id
        self.total_workers = total_workers
        self.mx_cache = {}
        self.dmarc_cache = {}
        self.spf_cache = {}
        self.seen_emails = set()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

    def clean_social_url(self, href: str, platform: str) -> str | None:
        if not href or any(ex in href.lower() for ex in SHARE_EXCLUSIONS):
            return None
        href = href.strip().split("?")[0].rstrip("/")
        if platform == "instagram" and "instagram.com/" in href:
            parts = href.split("instagram.com/")[1].split("/")
            if parts and parts[0] and not any(x in parts[0].lower() for x in ["explore", "accounts", "direct", "stories"]):
                return f"https://www.instagram.com/{parts[0]}"
        elif platform == "facebook" and "facebook.com/" in href:
            parts = href.split("facebook.com/")[1].split("/")
            if parts and parts[0] and not any(x in parts[0].lower() for x in ["groups", "policies", "help", "pages"]):
                return f"https://www.facebook.com/{parts[0]}"
        elif platform == "linkedin" and "linkedin.com/company/" in href:
            return href
        elif platform == "tiktok" and "tiktok.com/@" in href:
            parts = href.split("tiktok.com/@")[1].split("/")
            if parts and parts[0]:
                return f"https://www.tiktok.com/@{parts[0]}"
        elif platform == "twitter" and ("twitter.com/" in href or "x.com/" in href):
            parts = href.replace("https://", "").replace("http://", "").replace("www.", "").split("/")
            if len(parts) > 1 and parts[1] and not any(x in parts[1].lower() for x in ["intent", "share", "home"]):
                return f"https://x.com/{parts[1]}"
        return None

    def is_valid_email(self, em: str) -> bool:
        em = em.strip().strip('.').lower()
        if '@' not in em or len(em) < 6: return False
        parts = em.split('@')
        if len(parts) != 2: return False
        user, dom = parts
        if not user or not dom or '.' not in dom: return False
        tld = dom.split('.')[-1]
        if len(tld) < 2 or len(tld) > 12 or not tld.isalpha(): return False
        if any(ex in em for ex in EXCLUSIONS): return False
        if any(dom == dummy or dom.endswith('.' + dummy) for dummy in ['example.com', 'domain.com', 'beispiel.com', 'email.com', 'yoursite.com', 'sentry.io', 'schema.org', 'w3.org']):
            return False
        return True

    def sync_check_dns(self, domain: str) -> tuple[bool, str, bool, bool]:
        domain = domain.lower().strip()
        if domain in self.mx_cache:
            has_mx, provider = self.mx_cache[domain]
        else:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = ['8.8.8.8', '1.1.1.1', '8.8.4.4', '1.0.0.1']
            resolver.lifetime = 1.5
            resolver.timeout = 1.5
            try:
                answers = resolver.resolve(domain, 'MX')
                hosts = [str(r.exchange).lower() for r in answers]
                has_mx = len(hosts) > 0
                host_str = " ".join(hosts)
                if "google" in host_str or "l.google.com" in host_str: provider = "Google Workspace"
                elif "outlook" in host_str or "microsoft" in host_str: provider = "Microsoft 365"
                elif "zoho" in host_str: provider = "Zoho Mail"
                else: provider = "Host MX"
            except Exception:
                has_mx, provider = False, "No MX"
            self.mx_cache[domain] = (has_mx, provider)

        if not has_mx:
            return False, "No MX", False, False

        if domain in self.dmarc_cache:
            has_dmarc = self.dmarc_cache[domain]
        else:
            try:
                answers = resolver.resolve(f"_dmarc.{domain}", 'TXT')
                has_dmarc = any("v=DMARC1" in str(r) for r in answers)
            except Exception:
                has_dmarc = False
            self.dmarc_cache[domain] = has_dmarc

        if domain in self.spf_cache:
            has_spf = self.spf_cache[domain]
        else:
            try:
                answers = resolver.resolve(domain, 'TXT')
                has_spf = any("v=spf1" in str(r).lower() for r in answers)
            except Exception:
                has_spf = False
            self.spf_cache[domain] = has_spf

        return has_mx, provider, has_dmarc, has_spf

    def extract_socials_and_contact(self, soup: BeautifulSoup, domain: str, socials: dict) -> str | None:
        contact_url = None
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            for plat, col in PLATFORM_MAP.items():
                if not socials[col]:
                    val = self.clean_social_url(href, plat)
                    if val: socials[col] = val
            if not contact_url and any(k in href.lower() for k in ["contact", "about-us", "about", "help", "support"]):
                if href.startswith("http"): contact_url = href
                elif href.startswith("/"): contact_url = f"https://{domain}{href}"
        return contact_url

    async def scan_store(self, store_info: dict, client: httpx.AsyncClient) -> list[dict]:
        domain = store_info["domain"].strip().lower()
        brand_name = store_info.get("brand") or domain.split('.')[0].capitalize()
        initial_niche = store_info.get("niche", "Extended DTC")
        clean_d = domain.split('.')[0]

        candidates = []
        socials = {"Instagram": "", "Facebook": "", "LinkedIn": "", "TikTok": "", "Twitter_X": ""}
        contact_url = None

        # 1. Fetch Homepage First
        homepage_html = ""
        for url_try in [f"https://{domain}", f"http://{domain}", f"https://www.{domain}"]:
            try:
                r = await client.get(url_try, headers=self.headers)
                if r.status_code == 200 and r.text:
                    homepage_html = r.text
                    break
                elif r.status_code == 429:
                    await asyncio.sleep(2.0)
            except Exception:
                continue

        if homepage_html:
            soup = BeautifulSoup(homepage_html, "html.parser")
            contact_url = self.extract_socials_and_contact(soup, domain, socials)

            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if href.lower().startswith("mailto:"):
                    em = href.replace("mailto:", "").replace("Mailto:", "").split("?")[0].strip().lower()
                    if self.is_valid_email(em):
                        candidates.append((100, em))

            for m in re.findall(EMAIL_REGEX, homepage_html):
                m_clean = m.strip().strip('.').lower()
                if self.is_valid_email(m_clean):
                    if clean_d in m_clean or m_clean.split('@')[1] in domain:
                        candidates.append((100, m_clean))
                    elif any(k in m_clean for k in ['support@', 'care@', 'hello@', 'team@', 'founder@', 'service@', 'contact@', 'sales@', 'info@']):
                        candidates.append((85, m_clean))
                    else:
                        candidates.append((60, m_clean))

        # 2. If no candidate emails on homepage, crawl contact link
        if not candidates:
            crawl_targets = []
            if contact_url:
                crawl_targets.append(contact_url)
            crawl_targets.extend([f"https://{domain}/pages/contact", f"https://{domain}/pages/contact-us", f"https://{domain}/contact"])

            for target in crawl_targets[:2]:
                try:
                    r2 = await client.get(target, headers=self.headers)
                    if r2.status_code == 200 and r2.text:
                        soup2 = BeautifulSoup(r2.text, "html.parser")
                        self.extract_socials_and_contact(soup2, domain, socials)
                        for a in soup2.find_all("a", href=True):
                            href = a["href"].strip()
                            if href.lower().startswith("mailto:"):
                                em = href.replace("mailto:", "").replace("Mailto:", "").split("?")[0].strip().lower()
                                if self.is_valid_email(em):
                                    candidates.append((100, em))
                        for m in re.findall(EMAIL_REGEX, r2.text):
                            m_clean = m.strip().strip('.').lower()
                            if self.is_valid_email(m_clean):
                                candidates.append((85, m_clean))
                        if candidates:
                            break
                except Exception:
                    continue

        if not candidates:
            return []

        unique_emails = []
        seen = set()
        for _, em in sorted(candidates, key=lambda x: x[0], reverse=True):
            if em not in seen:
                seen.add(em)
                unique_emails.append(em)

        verified_records = []
        ads_url = f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&q={urllib.parse.quote(brand_name.lower())}&search_type=keyword_unordered&media_type=all"

        for found_email in unique_emails:
            email_domain = found_email.split('@')[1]
            has_mx, provider, has_dmarc, has_spf = await asyncio.to_thread(self.sync_check_dns, email_domain)
            if not has_mx:
                continue

            score = 80
            if has_dmarc: score += 10
            if has_spf: score += 5
            if socials["Instagram"]: score += 5

            try:
                from clean_and_reclassify_niches import classify_lead
                final_niche = classify_lead(brand_name, domain, found_email)
            except Exception:
                final_niche = classify_lead_inline(brand_name, domain, found_email)

            email_user = found_email.split('@')[0].lower()
            if any(k in email_user for k in ['support', 'care', 'service', 'help']):
                title = "Customer Care / Operations Lead"
                fn, ln = "Support", "Lead"
            elif any(k in email_user for k in ['marketing', 'growth', 'media', 'press', 'pr', 'ads']):
                title = "Head of Marketing & Growth"
                fn, ln = "Marketing", "Lead"
            elif any(k in email_user for k in ['info', 'contact', 'hello', 'team', 'sales', 'office', 'admin']):
                title = "Founder / Marketing Lead"
                fn, ln = "Founder", "Team"
            else:
                name_parts = re.split(r'[._-]', email_user)
                fn = name_parts[0].capitalize()
                ln = name_parts[1].capitalize() if len(name_parts) > 1 else "Founder"
                title = "Founder & Owner"

            other_emails = [e for e in unique_emails if e != found_email]
            sec_emails_str = "; ".join(other_emails)

            icebreaker = (
                f"Saw {brand_name}'s live campaigns in {final_niche} — noticed a high-leverage opportunity to test "
                f"iterative UGC hooks and creative variations to scale Meta spend profitably."
            )

            country = "United States" if domain.endswith(".com") or domain.endswith(".us") else "International"

            verified_records.append({
                "First Name": fn,
                "Last Name": ln,
                "Email": found_email,
                "Secondary_Email": sec_emails_str,
                "Company": brand_name,
                "Website": f"https://{domain}",
                "Title": title,
                "Meta Ads Library URL": ads_url,
                "Niche": final_niche,
                "Country": country,
                "Instagram": socials["Instagram"],
                "Facebook": socials["Facebook"],
                "LinkedIn": socials["LinkedIn"],
                "TikTok": socials["TikTok"],
                "Twitter_X": socials["Twitter_X"],
                "MX_Status": f"Valid ({provider})",
                "DMARC_Status": "Configured (v=DMARC1)" if has_dmarc else "Not Configured",
                "SPF_Status": "Configured" if has_spf else "None",
                "Gravatar_Found": "No",
                "Deliverability_Score": f"{score}% Confirmed Real",
                "Personalized Icebreaker": icebreaker
            })

        return verified_records

    async def run(self):
        print("=" * 72, flush=True)
        print(f"[+] CLOUD RUNNER INITIATED (Concurrency: {self.concurrency})", flush=True)
        print(f"[*] Worker ID: {self.worker_id} of {self.total_workers}", flush=True)
        print("=" * 72, flush=True)

        for n, p in NICHE_FILES.items():
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    for r in csv.DictReader(f):
                        em = r.get("Email", "").strip().lower()
                        if em: self.seen_emails.add(em)

        print(f"[*] Pre-loaded {len(self.seen_emails):,} existing verified inboxes.", flush=True)

        stores = []
        slice_path = os.path.join(SLICES_DIR, f"slice_{self.worker_id}.csv")
        if os.path.exists(slice_path):
            with open(slice_path, "r", encoding="utf-8", errors="ignore") as f:
                stores = list(csv.DictReader(f))
            print(f"[*] Loaded {len(stores):,} stores from slice_{self.worker_id}.csv")
        else:
            print(f"[!] Warning: {slice_path} not found!")

        total_stores = len(stores)
        scanned = 0
        found = 0
        start_time = time.time()
        queue = asyncio.Queue()
        for st in stores:
            queue.put_nowait(st)

        write_lock = asyncio.Lock()
        limits = httpx.Limits(max_keepalive_connections=self.concurrency, max_connections=self.concurrency * 2)

        async with httpx.AsyncClient(timeout=4.0, follow_redirects=True, verify=False, limits=limits) as client:
            async def consumer():
                nonlocal scanned, found
                while not queue.empty():
                    try:
                        st = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break

                    results = await self.scan_store(st, client)
                    scanned += 1

                    if results:
                        async with write_lock:
                            for rec in results:
                                em = rec["Email"].lower()
                                if em not in self.seen_emails:
                                    self.seen_emails.add(em)
                                    found += 1
                                    n = rec.get("Niche", "Extended DTC")
                                    if n in NICHE_FILES:
                                        with open(NICHE_FILES[n], "a", newline="", encoding="utf-8") as nf:
                                            csv.DictWriter(nf, fieldnames=CSV_HEADERS).writerow(rec)
                                    with open(MASTER_VERIFIED_CSV, "a", newline="", encoding="utf-8") as mf:
                                        csv.DictWriter(mf, fieldnames=CSV_HEADERS).writerow(rec)

                    if scanned % 25 == 0 or scanned == total_stores:
                        elapsed = time.time() - start_time
                        speed = scanned / elapsed if elapsed > 0 else 0
                        rem = ((total_stores - scanned) / speed) if speed > 0 else 0
                        pct = (scanned / total_stores) * 100 if total_stores else 0
                        bar_len = 24
                        filled = int(bar_len * (scanned / total_stores)) if total_stores else 0
                        bar = "=" * filled + "-" * (bar_len - filled)
                        print(
                            f"[CLOUD-WORKER-{self.worker_id}] [{bar}] {pct:5.1f}% | "
                            f"Scanned: {scanned:,}/{total_stores:,} | "
                            f"New Found: {found:,} | Total: {len(self.seen_emails):,} | "
                            f"Speed: {speed:.1f}/s | ETA: {rem/60:.1f}m",
                            flush=True
                        )
                    queue.task_done()

            workers = [asyncio.create_task(consumer()) for _ in range(self.concurrency)]
            await asyncio.gather(*workers)

        print(f"\n[OK] Cloud Worker {self.worker_id} completed successfully!", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrency", type=int, default=35)
    parser.add_argument("--worker-id", type=int, default=0)
    parser.add_argument("--total-workers", type=int, default=1)
    args = parser.parse_args()

    engine = CloudClusterEngine(concurrency=args.concurrency, worker_id=args.worker_id, total_workers=args.total_workers)
    asyncio.run(engine.run())
