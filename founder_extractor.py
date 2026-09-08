import re
import httpx
from bs4 import BeautifulSoup

FOUNDER_PATTERNS = [
    r'(?:founded|started|created|launched)\s+by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})',
    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*,\s*(?:Founder|Co-Founder|CEO|Owner)',
    r'(?:Founder|Co-Founder|CEO|Owner)\s*:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})',
    r'meet\s+(?:our\s+founder|the\s+founder)\s*,?\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})',
    r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s+(?:founded|established)\s+(?:the\s+company|the\s+brand|[A-Z][a-z]+)',
]

COMMON_EXCLUSIONS = {
    "our team", "about us", "customer service", "terms of", "privacy policy",
    "contact us", "free shipping", "shop all", "all rights", "united states",
    "new arrivals", "best sellers", "gift card", "press release"
}

class FounderExtractor:
    def __init__(self, timeout: int = 8):
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }

    async def extract_founder(self, domain: str, brand_name: str = "") -> dict:
        clean_domain = domain.lower().strip().replace("http://", "").replace("https://", "").replace("www.", "").split("/")[0]
        paths = ["/pages/about-us", "/pages/about", "/pages/our-story", "/pages/meet-the-founder", "/pages/the-founder", "/pages/team"]
        
        result = {
            "first_name": "",
            "last_name": "",
            "full_name": "",
            "title": "Founder / CEO",
            "source_url": None
        }

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True, verify=False) as client:
            for path in paths:
                url = f"https://{clean_domain}{path}"
                try:
                    res = await client.get(url)
                    if res.status_code == 200:
                        html = res.text
                        soup = BeautifulSoup(html, "html.parser")
                        text = soup.get_text(" ", strip=True)

                        for pattern in FOUNDER_PATTERNS:
                            matches = re.findall(pattern, text, flags=re.IGNORECASE)
                            for match in matches:
                                name_candidate = match.strip()
                                parts = name_candidate.split()
                                if 2 <= len(parts) <= 3:
                                    lower_candidate = name_candidate.lower()
                                    if not any(ex in lower_candidate for ex in COMMON_EXCLUSIONS):
                                        result["first_name"] = parts[0].capitalize()
                                        result["last_name"] = " ".join(parts[1:]).capitalize()
                                        result["full_name"] = f"{result['first_name']} {result['last_name']}"
                                        result["source_url"] = url
                                        return result
                except Exception:
                    continue

        return result

if __name__ == "__main__":
    import asyncio
    extractor = FounderExtractor()
    print(asyncio.run(extractor.extract_founder("cutsandsews.com")))
