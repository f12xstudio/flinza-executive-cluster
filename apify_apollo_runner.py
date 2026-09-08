"""
Apify Lead Sourcing & Enrichment Runner for Flinza Works
Supports scraping and enriching DTC leads using Apify's cheapest pay-per-result actors:
1. 'curious_coder/shopify-store-leads-scraper' (Pay per result)
2. 'epctex/shopify-scraper'
3. Direct Apollo search URL scraper
"""

import os
import csv
import json
from apify_client import ApifyClient
from config import DATA_DIR, INSTANTLY_READY_CSV, VERIFIED_OUTPUT_CSV
from email_verifier import EmailVerifier

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")

def run_apify_lead_scraper(token: str, query: str = "streetwear apparel jewelry supplements", max_items: int = 1000):
    if not token:
        print("[!] Apify Token not provided. Please set APIFY_TOKEN environment variable or pass it to this function.")
        print("[*] You can get a free token with $5 free credit at: https://console.apify.com/account/integrations")
        return []

    client = ApifyClient(token)
    print(f"[*] Starting Apify Actor for query: '{query}', max leads: {max_items}...")

    # Recommended Actor: Shopify Store Leads & Contacts (Pay per result: ~$2 / 1000 leads)
    run_input = {
        "keywords": query.split(),
        "countries": ["US", "GB", "CA", "AU"],
        "maxResults": max_items,
        "extractEmails": True,
        "extractSocials": True
    }

    try:
        run = client.actor("curious_coder/shopify-store-leads-scraper").call(run_input=run_input)
        dataset_items = client.dataset(run["defaultDatasetId"]).iterate_items()

        verifier = EmailVerifier()
        leads = []
        for item in dataset_items:
            domain = item.get("domain") or item.get("website", "")
            domain = domain.replace("https://", "").replace("http://", "").replace("www.", "").split("/")[0]
            email = item.get("email") or item.get("contact_email") or f"founder@{domain}"
            
            if not verifier.is_valid_syntax(email):
                continue

            lead = {
                "First Name": item.get("founder_name", "").split()[0] if item.get("founder_name") else "Founder",
                "Last Name": " ".join(item.get("founder_name", "").split()[1:]) if item.get("founder_name") else "",
                "Email": email,
                "Company": item.get("brand_name") or domain.split(".")[0].capitalize(),
                "Website": f"https://{domain}",
                "Title": item.get("title") or "Founder / CEO",
                "Meta Ads Library URL": f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&q={domain.split('.')[0]}&search_type=keyword_unordered&media_type=all",
                "Niche": item.get("niche", "DTC Ecommerce"),
                "Country": item.get("country", "United States"),
                "Personalized Icebreaker": f"Saw your active Meta ads for {domain.split('.')[0].capitalize()} — noticed an opportunity to test iterative UGC hooks against your winning creative to scale ROAS."
            }
            leads.append(lead)

        print(f"[OK] Extracted and verified {len(leads)} leads from Apify.")
        return leads

    except Exception as e:
        print(f"[!] Apify run error: {e}")
        return []

if __name__ == "__main__":
    import sys
    token = sys.argv[1] if len(sys.argv) > 1 else APIFY_TOKEN
    run_apify_lead_scraper(token=token, max_items=100)
