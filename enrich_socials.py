import os
import re
import csv
import time
import asyncio
import httpx
from bs4 import BeautifulSoup
from config import DATA_DIR

INPUT_CSV = os.path.join(DATA_DIR, "instantly_real_scraped_leads.csv")
OUTPUT_FULL_CSV = os.path.join(DATA_DIR, "real_scraped_leads_with_socials.csv")
OUTPUT_INSTANTLY_CSV = os.path.join(DATA_DIR, "instantly_real_leads_with_socials.csv")

SHARE_EXCLUSIONS = [
    "/sharer", "share.php", "intent/tweet", "pin/create", "/p/", "/reel/",
    "/stories/", "instagram.com/instagram", "facebook.com/facebook",
    "twitter.com/twitter", "linkedin.com/shareArticle", "whatsapp.com",
    "mailto:", "javascript:"
]

class SocialMediaScraper:
    def __init__(self, concurrency: int = 20):
        self.concurrency = concurrency
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }
        self.processed_domains = {}  # domain -> socials dict

    def clean_social_url(self, href: str, platform: str) -> str | None:
        if not href or any(ex in href.lower() for ex in SHARE_EXCLUSIONS):
            return None
        href = href.strip().split("?")[0].rstrip("/")
        
        if platform == "instagram" and "instagram.com/" in href:
            parts = href.split("instagram.com/")[1].split("/")
            if parts and parts[0] and not any(x in parts[0].lower() for x in ["explore", "accounts", "direct"]):
                return f"https://www.instagram.com/{parts[0]}"
        elif platform == "facebook" and "facebook.com/" in href:
            parts = href.split("facebook.com/")[1].split("/")
            if parts and parts[0] and not any(x in parts[0].lower() for x in ["groups", "policies", "help"]):
                return f"https://www.facebook.com/{parts[0]}"
        elif platform == "linkedin" and "linkedin.com/company/" in href:
            return href
        elif platform == "tiktok" and "tiktok.com/@" in href:
            parts = href.split("tiktok.com/@")[1].split("/")
            if parts and parts[0]:
                return f"https://www.tiktok.com/@{parts[0]}"
        elif platform == "twitter" and ("twitter.com/" in href or "x.com/" in href):
            handle = href.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[1] if len(href.split("/")) > 1 else ""
            if handle and not any(x in handle.lower() for x in ["intent", "share", "home"]):
                return f"https://x.com/{handle}"
        return None

    async def scrape_domain_socials(self, domain: str, client: httpx.AsyncClient) -> dict:
        socials = {
            "Instagram": "",
            "Facebook": "",
            "LinkedIn": "",
            "TikTok": "",
            "Twitter_X": ""
        }
        try:
            r = await client.get(f"https://{domain}", headers=self.headers)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    if not socials["Instagram"]:
                        ig = self.clean_social_url(href, "instagram")
                        if ig: socials["Instagram"] = ig
                    if not socials["Facebook"]:
                        fb = self.clean_social_url(href, "facebook")
                        if fb: socials["Facebook"] = fb
                    if not socials["LinkedIn"]:
                        li = self.clean_social_url(href, "linkedin")
                        if li: socials["LinkedIn"] = li
                    if not socials["TikTok"]:
                        tt = self.clean_social_url(href, "tiktok")
                        if tt: socials["TikTok"] = tt
                    if not socials["Twitter_X"]:
                        tw = self.clean_social_url(href, "twitter")
                        if tw: socials["Twitter_X"] = tw
        except Exception:
            pass

        return socials

    def print_progress(self, enriched: int, total: int, ig_count: int, fb_count: int, li_count: int):
        pct = (enriched / total) * 100 if total else 0
        bar_len = 24
        filled = int(bar_len * (enriched / total)) if total else 0
        bar = "=" * filled + "-" * (bar_len - filled)
        print(f"[SOCIALS] [{bar}] {pct:5.1f}% | Enriched: {enriched:,}/{total:,} | IG: {ig_count:,} | FB: {fb_count:,} | LinkedIn: {li_count:,}", flush=True)

    async def run(self):
        print("[*] Starting Dedicated Social Media Scraper Worker...", flush=True)
        
        # Load already processed from output if it exists
        already_processed_ids = set()
        if os.path.exists(OUTPUT_INSTANTLY_CSV):
            with open(OUTPUT_INSTANTLY_CSV, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("Email"):
                        already_processed_ids.add((row.get("Email"), row.get("Website")))
            print(f"[*] Resuming socials scraper: {len(already_processed_ids):,} leads already enriched.", flush=True)

        full_fields = [
            "First Name", "Last Name", "Email", "Secondary_Email", "Company", "Website", "Title",
            "Meta Ads Library URL", "Niche", "Country", "Instagram", "Facebook",
            "LinkedIn", "TikTok", "Twitter_X", "Personalized Icebreaker"
        ]

        if not os.path.exists(OUTPUT_INSTANTLY_CSV):
            with open(OUTPUT_INSTANTLY_CSV, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=full_fields).writeheader()

        ig_total = 0
        fb_total = 0
        li_total = 0
        enriched_count = len(already_processed_ids)
        semaphore = asyncio.Semaphore(self.concurrency)

        async with httpx.AsyncClient(timeout=5, follow_redirects=True, verify=False) as client:
            while True:
                if not os.path.exists(INPUT_CSV):
                    await asyncio.sleep(2)
                    continue

                # Read current input rows
                current_rows = []
                with open(INPUT_CSV, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        ident = (row.get("Email"), row.get("Website"))
                        if ident not in already_processed_ids:
                            current_rows.append(row)

                if not current_rows:
                    # Caught up with email scraper, wait for new leads
                    await asyncio.sleep(5)
                    continue

                print(f"[*] Found {len(current_rows)} new leads to enrich with socials...", flush=True)

                async def process_row(row):
                    nonlocal enriched_count, ig_total, fb_total, li_total
                    ident = (row.get("Email"), row.get("Website"))
                    website = row.get("Website", "")
                    domain = website.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0].lower()
                    
                    if not domain:
                        return

                    async with semaphore:
                        if domain in self.processed_domains:
                            socials = self.processed_domains[domain]
                        else:
                            socials = await self.scrape_domain_socials(domain, client)
                            self.processed_domains[domain] = socials

                    enriched_row = {
                        "First Name": row.get("First Name", "Founder"),
                        "Last Name": row.get("Last Name", "Team"),
                        "Email": row.get("Email", ""),
                        "Secondary_Email": row.get("Secondary_Email", ""),
                        "Company": row.get("Company", ""),
                        "Website": row.get("Website", ""),
                        "Title": row.get("Title", "Founder / Marketing Lead"),
                        "Meta Ads Library URL": row.get("Meta Ads Library URL", ""),
                        "Niche": row.get("Niche", "DTC"),
                        "Country": row.get("Country", "United States"),
                        "Instagram": socials.get("Instagram", ""),
                        "Facebook": socials.get("Facebook", ""),
                        "LinkedIn": socials.get("LinkedIn", ""),
                        "TikTok": socials.get("TikTok", ""),
                        "Twitter_X": socials.get("Twitter_X", ""),
                        "Personalized Icebreaker": row.get("Personalized Icebreaker", "")
                    }

                    if socials.get("Instagram"): ig_total += 1
                    if socials.get("Facebook"): fb_total += 1
                    if socials.get("LinkedIn"): li_total += 1

                    already_processed_ids.add(ident)
                    enriched_count += 1

                    # Append to output CSV
                    with open(OUTPUT_INSTANTLY_CSV, "a", newline="", encoding="utf-8") as f:
                        writer = csv.DictWriter(f, fieldnames=full_fields)
                        writer.writerow(enriched_row)

                    if enriched_count % 20 == 0 or enriched_count <= 10:
                        total_expected = enriched_count + len(current_rows)
                        self.print_progress(enriched_count, total_expected, ig_total, fb_total, li_total)

                # Process current batch concurrently
                tasks = [process_row(r) for r in current_rows]
                await asyncio.gather(*tasks)

                print(f"[OK] Completed current batch. Total leads with socials: {enriched_count:,}", flush=True)

if __name__ == "__main__":
    scraper = SocialMediaScraper(concurrency=25)
    asyncio.run(scraper.run())
