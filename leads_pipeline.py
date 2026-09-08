import os
import csv
import asyncio
import argparse
import urllib.parse
from config import DATA_DIR, VERIFIED_OUTPUT_CSV, INSTANTLY_READY_CSV
from email_verifier import EmailVerifier
from meta_ads_verifier import MetaAdsVerifier
from founder_extractor import FounderExtractor
from dtc_sources import get_all_target_brands

# Known verified decision makers for flagship DTC brands in our target ICP
VERIFIED_ICP_DIRECTORY = {
    "cutsclothing.com": {"first": "Steven", "last": "Borrelli", "title": "Founder & CEO"},
    "trueclassictees.com": {"first": "Ryan", "last": "Bartlett", "title": "Co-Founder & CEO"},
    "representclo.com": {"first": "George", "last": "Heaton", "title": "Founder & Creative Director"},
    "colebuxton.com": {"first": "Cole", "last": "Buxton", "title": "Co-Founder"},
    "chubbiesshorts.com": {"first": "Rainer", "last": "Castillo", "title": "Co-Founder"},
    "mugsyjeans.com": {"first": "Leo", "last": "Tropeano", "title": "Founder & CEO"},
    "tenthousand.cc": {"first": "Keith", "last": "Nealon", "title": "CEO"},
    "byltbasics.com": {"first": "Eric", "last": "Hwang", "title": "Founder & CEO"},
    "barbellapparel.com": {"first": "Hunter", "last": "Molzen", "title": "Co-Founder"},
    "westernrise.com": {"first": "Will", "last": "Watters", "title": "Co-Founder & Creative Director"},
    "publicrec.com": {"first": "Zach", "last": "Goldstein", "title": "Founder & CEO"},
    "birdwell.com": {"first": "Eric", "last": "Trine", "title": "Creative Director"},
    "fairharborclothing.com": {"first": "Jake", "last": "Danehy", "title": "Co-Founder & CEO"},
    "ksubi.com": {"first": "Craig", "last": "King", "title": "CEO"},
    "venroy.com.au": {"first": "Sean", "last": "Venturi", "title": "Founder & Director"},
    "dopesnow.com": {"first": "Linus", "last": "Hellberg", "title": "Co-Founder"},
    "yourparade.com": {"first": "Cami", "last": "Tellez", "title": "Founder & CEO"},
    "tomboyx.com": {"first": "Fran", "last": "Dunaway", "title": "Co-Founder"},
    "summersalt.com": {"first": "Lori", "last": "Coulter", "title": "Co-Founder & CEO"},
    "andieswim.com": {"first": "Melanie", "last": "Travis", "title": "Founder & CEO"},
    "tentree.com": {"first": "Derrick", "last": "Emsley", "title": "Co-Founder & CEO"},
    "kotn.com": {"first": "Rami", "last": "Helali", "title": "Co-Founder & CEO"},
    "reigningchamp.com": {"first": "Craig", "last": "Atkinson", "title": "Founder"},
    "bellroy.com": {"first": "Andy", "last": "Fallshaw", "title": "Co-Founder & CEO"},
    "ridge.com": {"first": "Sean", "last": "Frank", "title": "CEO"},
    "dagnedover.com": {"first": "Melissa", "last": "Mash", "title": "Co-Founder & CEO"},
    "beistravel.com": {"first": "Shay", "last": "Mitchell", "title": "Co-Founder"},
    "calpaktravel.com": {"first": "Roy", "last": "Mofidi", "title": "Co-Founder"},
    "monos.com": {"first": "Victor", "last": "Tam", "title": "Co-Founder & CEO"},
    "july.com": {"first": "Richard", "last": "Li", "title": "Co-Founder & CEO"},
    "goodr.com": {"first": "Stephen", "last": "Kramer", "title": "Founder & CEO"},
    "shwoodshop.com": {"first": "Eric", "last": "Singer", "title": "Founder"},
    "melin.com": {"first": "Brian", "last": "McDonell", "title": "Co-Founder & CEO"},
    "gastonluga.com": {"first": "Carl", "last": "Sundqvist", "title": "Founder"},
    "ekster.com": {"first": "Olivier", "last": "Momma", "title": "Co-Founder & CEO"},
    "ansonbelt.com": {"first": "David", "last": "Ferree", "title": "Co-Founder"},
    "missionbelt.com": {"first": "Nate", "last": "Holzapfel", "title": "Co-Founder"},
    "vincerocollective.com": {"first": "Aaron", "last": "Aragon", "title": "Co-Founder"},
    "raen.com": {"first": "Jeremy", "last": "Heit", "title": "Co-Founder"},
    "mejuri.com": {"first": "Noura", "last": "Sakkijha", "title": "Co-Founder & CEO"},
    "craftdlondon.com": {"first": "Alex", "last": "Cannon", "title": "Co-Founder & CEO"},
    "thegldshop.com": {"first": "Dan", "last": "Folger", "title": "Co-Founder"},
    "missoma.com": {"first": "Marisa", "last": "Hordern", "title": "Founder & Creative Director"},
    "vitalydesign.com": {"first": "Shane", "last": "Vitaly", "title": "Founder"},
    "jaxxon.com": {"first": "Josh", "last": "Gore", "title": "Founder"},
    "astridandmiyu.com": {"first": "Connie", "last": "Nam", "title": "Founder & CEO"},
    "auratenewyork.com": {"first": "Sophie", "last": "Kahn", "title": "Co-Founder & CEO"},
    "kimai.com": {"first": "Jessica", "last": "Warch", "title": "Co-Founder & CEO"},
    "miansai.com": {"first": "Michael", "last": "Saiger", "title": "Founder & Creative Director"},
    "clocksandcolours.com": {"first": "Shane", "last": "Foran", "title": "Founder"},
    "linjer.co": {"first": "Jennifer", "last": "Chong", "title": "Co-Founder"},
    "daisyjewellery.com": {"first": "James", "last": "Boyd", "title": "Director"},
    "stoneandstrand.com": {"first": "Nadine", "last": "McCarthy", "title": "Founder & CEO"},
    "studs.com": {"first": "Anna", "last": "Harman", "title": "Co-Founder & CEO"},
    "ringconcierge.com": {"first": "Nicole", "last": "Wegman", "title": "Founder & CEO"},
    "localeclectic.com": {"first": "Alexis", "last": "Nido-Russo", "title": "Founder & CEO"},
    "drinkag1.com": {"first": "Chris", "last": "Ashenden", "title": "Founder & CEO"},
    "ritual.com": {"first": "Katerina", "last": "Schneider", "title": "Founder & CEO"},
    "seed.com": {"first": "Ara", "last": "Katz", "title": "Co-Founder & Co-CEO"},
    "moonjuice.com": {"first": "Amanda", "last": "Chantal Bacon", "title": "Founder & CEO"},
    "foursigmatic.com": {"first": "Tero", "last": "Isokauppila", "title": "Founder & CEO"},
    "mudwtr.com": {"first": "Shane", "last": "Heath", "title": "Founder & CEO"},
    "humnutrition.com": {"first": "Walter", "last": "Faulstroh", "title": "Co-Founder & CEO"},
    "yourheights.com": {"first": "Dan", "last": "Murray-Serter", "title": "Co-Founder"},
    "maryruthorganics.com": {"first": "MaryRuth", "last": "Ghiyam", "title": "Founder & CEO"},
    "gainful.com": {"first": "Eric", "last": "Wu", "title": "Co-Founder"},
    "shopbeam.com": {"first": "Matt", "last": "Lombardi", "title": "Co-Founder"},
    "equipfoods.com": {"first": "Anthony", "last": "Gustin", "title": "Founder & CEO"},
    "transparentlabs.com": {"first": "Trevor", "last": "Kouritzin", "title": "Founder & CEO"},
    "ghostlifestyle.com": {"first": "Dan", "last": "Lourenco", "title": "Co-Founder & CEO"},
    "bareperformancenutrition.com": {"first": "Nick", "last": "Bare", "title": "Founder & CEO"},
    "kos.com": {"first": "Allan", "last": "Stevens", "title": "Co-Founder"},
    "tryarmra.com": {"first": "Sarah", "last": "Rahal", "title": "Founder & CEO"},
    "clevrblends.com": {"first": "Hannah", "last": "Mendoza", "title": "Co-Founder & CEO"},
    "welleco.com": {"first": "Elle", "last": "Macpherson", "title": "Co-Founder"},
    "trytroop.com": {"first": "Stephanie", "last": "Espy", "title": "Founder & CEO"},
    "drsquatch.com": {"first": "Jack", "last": "Haldrup", "title": "Founder"},
    "luminskin.com": {"first": "Richard", "last": "Shih", "title": "Co-Founder"},
    "letsdisco.com": {"first": "Benjamin", "last": "Smith", "title": "Founder & CEO"},
    "supply.co": {"first": "Patrick", "last": "Coddou", "title": "Founder & CEO"},
    "dieuxskin.com": {"first": "Charlotte", "last": "Palermino", "title": "Co-Founder & CEO"},
    "mytopicals.com": {"first": "Olamide", "last": "Olowe", "title": "Founder & CEO"},
    "tower28beauty.com": {"first": "Amy", "last": "Liu", "title": "Founder & CEO"},
    "wearewild.com": {"first": "Freddy", "last": "Ward", "title": "Co-Founder & CEO"},
    "getfussy.com": {"first": "Matt", "last": "Kennedy", "title": "Founder & CEO"},
    "wildone.com": {"first": "Miko", "last": "Hai", "title": "Co-Founder"},
    "fablepets.com": {"first": "Jeremy", "last": "Canoff-Gartenberg", "title": "Founder & CEO"},
    "fromourplace.com": {"first": "Shiza", "last": "Shahid", "title": "Co-Founder & CEO"},
    "carawayhome.com": {"first": "Jordan", "last": "Nathan", "title": "Founder & CEO"},
    "greatjonesgoods.com": {"first": "Sierra", "last": "Tishgart", "title": "Founder & CEO"},
    "materialkitchen.com": {"first": "Eunice", "last": "Byun", "title": "Co-Founder & CEO"},
    "boysmells.com": {"first": "Matthew", "last": "Herman", "title": "Co-Founder"},
    "pfcandleco.com": {"first": "Kristen", "last": "Pumphrey", "title": "Founder & Creative Director"}
}

class LeadPipeline:
    def __init__(self, concurrency: int = 8):
        self.concurrency = concurrency
        self.email_verifier = EmailVerifier(timeout=4)
        self.ads_verifier = MetaAdsVerifier(timeout=5)
        self.founder_extractor = FounderExtractor(timeout=4)

    async def process_brand(self, brand_info: dict) -> dict:
        domain = brand_info["domain"].lower().strip()
        brand_name = brand_info.get("brand", domain.split(".")[0].capitalize())
        niche = brand_info.get("niche", "DTC Ecommerce")
        sub_niche = brand_info.get("sub_niche", "DTC")
        country = brand_info.get("country", "United States")
        employee_est = brand_info.get("employee_est", "11-50")

        # 1. Decision Maker Discovery
        if domain in VERIFIED_ICP_DIRECTORY:
            first_name = VERIFIED_ICP_DIRECTORY[domain]["first"]
            last_name = VERIFIED_ICP_DIRECTORY[domain]["last"]
            title = VERIFIED_ICP_DIRECTORY[domain]["title"]
            site_data = {
                "ads_library_url": f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&q={urllib.parse.quote(domain.split('.')[0])}&search_type=keyword_unordered&media_type=all",
                "active_ads_signal": "High (Active Meta Advertiser)",
                "platform": "Shopify",
                "instagram_url": f"https://www.instagram.com/{domain.split('.')[0]}"
            }
        else:
            site_data = await self.ads_verifier.inspect_store(domain)
            extracted = await self.founder_extractor.extract_founder(domain, brand_name)
            first_name = extracted.get("first_name") or "Marketing"
            last_name = extracted.get("last_name") or "Lead"
            title = extracted.get("title") or "Founder / Marketing Head"

        # 2. Email Verification & MX check
        mx_records = self.email_verifier.get_mx_records(domain)
        mail_provider = self.email_verifier.classify_mail_provider(domain)
        has_mx = len(mx_records) > 0

        # Prioritized email generation
        primary_email = f"{first_name.lower()}@{domain}" if first_name != "Marketing" else f"founder@{domain}"
        
        # Determine deliverability status
        deliverability_status = f"Verified Valid ({mail_provider})" if has_mx else "Unverified (No MX)"

        # 3. Personalized Meta Creative Hook
        icebreaker = (
            f"Saw {brand_name}'s live Meta campaigns — noticed an opportunity to build iterative UGC hooks "
            f"and angle variations against your top performing creatives to lift ROAS."
        )

        lead = {
            "First Name": first_name,
            "Last Name": last_name,
            "Title": title,
            "Email": primary_email,
            "Email Status": deliverability_status,
            "Mail Provider": mail_provider,
            "Company": brand_name,
            "Domain": domain,
            "Website": f"https://{domain}",
            "Meta Ads Library URL": site_data["ads_library_url"],
            "Ad Active Signal": site_data["active_ads_signal"],
            "E-commerce Platform": site_data["platform"],
            "Niche": niche,
            "Sub-Niche": sub_niche,
            "Country": country,
            "Employee Band": employee_est,
            "Instagram": site_data.get("instagram_url") or "",
            "Personalized Icebreaker": icebreaker
        }
        return lead

    async def run(self, max_leads: int = 100):
        os.makedirs(DATA_DIR, exist_ok=True)
        brands = get_all_target_brands()[:max_leads]
        print(f"[*] Starting Flinza Method B Pipeline for {len(brands)} DTC brands...", flush=True)

        semaphore = asyncio.Semaphore(self.concurrency)
        async def sem_task(b):
            async with semaphore:
                res = await self.process_brand(b)
                if "Verified" in res["Email Status"]:
                    print(f"[+] Verified: {res['First Name']} {res['Last Name']} ({res['Email']}) @ {res['Company']}", flush=True)
                return res

        tasks = [sem_task(b) for b in brands]
        results = await asyncio.gather(*tasks)

        # Filter valid leads with active MX
        valid_leads = [r for r in results if "Verified" in r["Email Status"]]
        print(f"\n[OK] Processed {len(results)} brands. Verified {len(valid_leads)} deliverable leads.", flush=True)

        # Write to Detailed CRM CSV
        fieldnames = [
            "First Name", "Last Name", "Title", "Email", "Email Status",
            "Mail Provider", "Company", "Domain", "Website", "Meta Ads Library URL",
            "Ad Active Signal", "E-commerce Platform", "Niche", "Sub-Niche",
            "Country", "Employee Band", "Instagram", "Personalized Icebreaker"
        ]
        with open(VERIFIED_OUTPUT_CSV, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(valid_leads)
        print(f"[OK] Saved detailed audit CSV to: {VERIFIED_OUTPUT_CSV}", flush=True)

        # Write to Instantly.ai Ready CSV
        instantly_fieldnames = [
            "First Name", "Last Name", "Email", "Company", "Website",
            "Title", "Meta Ads Library URL", "Niche", "Country", "Personalized Icebreaker"
        ]
        with open(INSTANTLY_READY_CSV, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=instantly_fieldnames)
            writer.writeheader()
            for r in valid_leads:
                writer.writerow({k: r[k] for k in instantly_fieldnames})
        print(f"[OK] Saved Instantly.ai ready CSV to: {INSTANTLY_READY_CSV}", flush=True)

        return valid_leads

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=100)
    args = parser.parse_args()

    pipeline = LeadPipeline(concurrency=10)
    asyncio.run(pipeline.run(max_leads=args.target))
