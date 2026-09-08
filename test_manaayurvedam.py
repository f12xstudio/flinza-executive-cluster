import httpx
import re

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}
domain = "manaayurvedam.com"
paths = ["", "/pages/contact", "/policies/privacy-policy", "/pages/about-us", "/pages/contact-us", "/policies/terms-of-service", "/policies/shipping-policy"]
email_regex = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'

print(f"=== LIVE INSPECTION OF https://{domain} ===\n")

with httpx.Client(timeout=10, follow_redirects=True, verify=False) as client:
    for path in paths:
        url = f"https://{domain}{path}"
        try:
            r = client.get(url, headers=headers)
            matches = list(set(re.findall(email_regex, r.text)))
            print(f"[*] Fetched: {url} -> HTTP {r.status_code}")
            if matches:
                print(f"    Emails found ({len(matches)}): {matches}")
                for m in matches:
                    idx = r.text.find(m)
                    if idx != -1:
                        snippet = r.text[max(0, idx - 100):min(len(r.text), idx + 100)]
                        snippet_clean = re.sub(r'\s+', ' ', snippet).strip()
                        print(f"    Snippet around {m}:")
                        print(f"      \"{snippet_clean}\"\n")
            else:
                print("    (No email regex pattern match on this path)\n")
        except Exception as e:
            print(f"[!] Error fetching {url}: {e}\n")
