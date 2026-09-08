import re
import urllib.parse
import httpx
from bs4 import BeautifulSoup

class MetaAdsVerifier:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def inspect_store(self, domain: str) -> dict:
        clean_domain = domain.lower().strip().replace("http://", "").replace("https://", "").replace("www.", "").split("/")[0]
        url = f"https://{clean_domain}"
        result = {
            "domain": clean_domain,
            "url": url,
            "reachable": False,
            "is_ecommerce": False,
            "has_meta_pixel": False,
            "pixel_id": None,
            "instagram_url": None,
            "facebook_url": None,
            "linkedin_url": None,
            "ads_library_url": f"https://www.facebook.com/ads/library/?active_status=active&ad_type=all&country=ALL&q={urllib.parse.quote(clean_domain.split('.')[0])}&search_type=keyword_unordered&media_type=all",
            "platform": "Unknown",
            "active_ads_signal": "Unverified"
        }

        async with httpx.AsyncClient(headers=self.headers, timeout=self.timeout, follow_redirects=True, verify=False) as client:
            try:
                response = await client.get(url)
                if response.status_code in [200, 301, 302, 304]:
                    result["reachable"] = True
                    html = response.text

                    # E-commerce platform detection
                    if "cdn.shopify.com" in html or "Shopify.shop" in html or "myshopify.com" in html or "/cart" in html or "/checkout" in html:
                        result["is_ecommerce"] = True
                        result["platform"] = "Shopify"
                    elif "wp-content" in html and "woocommerce" in html:
                        result["is_ecommerce"] = True
                        result["platform"] = "WooCommerce"
                    elif "bigcommerce" in html:
                        result["is_ecommerce"] = True
                        result["platform"] = "BigCommerce"
                    else:
                        result["is_ecommerce"] = any(k in html.lower() for k in ["cart", "bag", "checkout", "add to cart", "shop now", "free shipping"])

                    # Meta Pixel detection (fbq, fbevents.js, connect.facebook.net)
                    pixel_match = re.search(r'fbq\(\s*[\'"]init[\'"]\s*,\s*[\'"](\d+)[\'"]', html)
                    if pixel_match:
                        result["has_meta_pixel"] = True
                        result["pixel_id"] = pixel_match.group(1)
                        result["active_ads_signal"] = "High (Meta Pixel Installed)"
                    elif "connect.facebook.net/en_US/fbevents.js" in html or "facebook.com/tr?id=" in html:
                        result["has_meta_pixel"] = True
                        result["active_ads_signal"] = "Medium (Meta Tracking Present)"

                    # Social links extraction
                    soup = BeautifulSoup(html, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "instagram.com/" in href and not result["instagram_url"]:
                            if not any(x in href for x in ["/p/", "/reel/", "/stories/", "instagram.com/instagram"]):
                                result["instagram_url"] = href.split("?")[0]
                        elif "facebook.com/" in href and not result["facebook_url"]:
                            if not any(x in href for x in ["sharer", "share.php", "facebook.com/facebook"]):
                                result["facebook_url"] = href.split("?")[0]
                        elif "linkedin.com/company/" in href and not result["linkedin_url"]:
                            result["linkedin_url"] = href.split("?")[0]

            except Exception as e:
                result["error"] = str(e)

        return result

if __name__ == "__main__":
    import asyncio
    verifier = MetaAdsVerifier()
    res = asyncio.run(verifier.inspect_store("cutsandsews.com"))
    print(res)
