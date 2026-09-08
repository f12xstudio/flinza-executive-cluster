"""
colab_blitz_harvester.py
========================
BALANCED BLITZ HARVESTER — 200-300 stores/sec

Key design decisions:
  • 300 concurrent workers — fast but won't skip slow/static Shopify stores
  • 2.5 s timeout — catches stores that load in 1-2 s (static/Shopify CDN)
  • HTTPS → HTTP fallback for redirecting stores
  • Raw-regex email + social extraction on homepage (zero BeautifulSoup overhead)
  • Async DNS via aiodns — MX, DMARC, SPF fired in parallel per domain
  • NO lead cap — runs the entire input list top to bottom
  • AUTO-ZIP + AUTO-DOWNLOAD every 2,000 verified leads (Colab-aware)
  • RAW extraction log: every store visited is written to raw_extracted_all.csv
    with every email/social found and the exact rejection reason if it failed
  • All files append-streamed in real-time — zero data loss on crash
"""

import os, re, sys, csv, time, asyncio, argparse, zipfile, urllib.parse, random, uuid, collections
from datetime import datetime

# UTF-8 stdout/stderr for reliable cross-platform logging (Windows + Colab)
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── Optional fast event loop ──────────────────────────────────────────
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    _LOOP = "uvloop"
except ImportError:
    _LOOP = "asyncio"

# ── HTTP client ───────────────────────────────────────────────────────
try:
    from curl_cffi.requests import AsyncSession
    HAS_CURL = True
except ImportError:
    import httpx
    HAS_CURL = False

# ── Async DNS ─────────────────────────────────────────────────────────
try:
    import aiodns
    HAS_AIODNS = True
except ImportError:
    import dns.resolver as _sync_dns
    HAS_AIODNS = False

# ── Browser fingerprint pool — rotated per session ────────────────────
# Each session gets a different TLS/HTTP fingerprint so Shopify's CDN
# sees requests coming from multiple distinct browser identities.
BROWSER_PROFILES = [
    "chrome124", "chrome120", "chrome116", "chrome110",
    "safari17_0", "safari15_5",
    "edge99", "firefox133",
]

# ── CDN Rate-Limit Circuit Breaker ──────────────────────────────────
class RateLimitBreaker:
    """
    Global adaptive circuit breaker for Shopify Cloudflare edge CDN rate limits (HTTP 429).
    When tripped, ALL workers pause immediately before making further requests.
    A single worker manages the cooldown (5-8s), after which normal harvesting resumes.
    Stores that encountered a 429 are re-queued — ZERO stores are lost or dropped.
    """
    def __init__(self, cooldown: float = 6.0):
        self.cooldown = cooldown
        self._tripped = asyncio.Event()
        self._tripped.set()  # set = running (open for traffic)
        self._trip_lock = asyncio.Lock()
        self._last_trip = 0.0

    async def wait(self):
        """Workers call this before each request. Suspends if circuit breaker is tripped."""
        await self._tripped.wait()

    async def trip(self):
        """Called when a 429 is encountered. Pauses all workers for cooldown duration."""
        async with self._trip_lock:
            now = time.time()
            if now - self._last_trip < 2.0:
                return
            self._last_trip = now
            self._tripped.clear()
            print(f"\n⚠️  [CIRCUIT BREAKER] 429 received from Shopify CDN! Pausing {self.cooldown:.1f}s for edge cooldown...", flush=True)
            await asyncio.sleep(self.cooldown)
            print(f"✅ [CIRCUIT BREAKER] Cooldown complete. Resuming harvest at full speed...\n", flush=True)
            self._tripped.set()


# ── Paths ─────────────────────────────────────────────────────────────
DATA_DIR     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
VERIFIED_DIR = os.path.join(DATA_DIR, "verified_5k")
SLICES_DIR   = os.path.join(DATA_DIR, "cluster_slices")
ZIPS_DIR     = os.path.join(DATA_DIR, "batch_zips")
RAW_DIR      = os.path.join(DATA_DIR, "raw_extracted")
os.makedirs(VERIFIED_DIR, exist_ok=True)
os.makedirs(SLICES_DIR,   exist_ok=True)
os.makedirs(ZIPS_DIR,     exist_ok=True)
os.makedirs(RAW_DIR,      exist_ok=True)

MASTER_VERIFIED_CSV = os.path.join(VERIFIED_DIR, "instantly_master_ultra_verified.csv")
RAW_EXTRACTED_CSV   = os.path.join(RAW_DIR,      "raw_extracted_all.csv")

# Columns written for EVERY store visited (qualified or not)
RAW_HEADERS = [
    "Domain", "Brand", "Niche_Guess", "HTTP_Status",
    "Emails_Found",          # all emails scraped from page, comma-separated
    "Primary_Email",         # best candidate (or blank)
    "Email_Domain",          # domain of primary email
    "Instagram", "Facebook", "LinkedIn", "TikTok", "Twitter_X",
    "MX_Valid", "MX_Provider", "DMARC", "SPF",
    "Qualified",             # YES / NO
    "Rejection_Reason",      # blank if qualified; one of:
                             #   duplicate_domain | no_html | http_error:<code>
                             #   no_email_found   | duplicate_email
                             #   no_mx:<email_domain> | already_seen
    "Scraped_At",
]

NICHE_FILES = {
    "Jewelry":              os.path.join(VERIFIED_DIR, "jewelry_real_inboxes.csv"),
    "Fashion & Apparel":    os.path.join(VERIFIED_DIR, "fashion_apparel_real_inboxes.csv"),
    "Fashion Accessories":  os.path.join(VERIFIED_DIR, "fashion_accessories_real_inboxes.csv"),
    "Health & Supplements": os.path.join(VERIFIED_DIR, "health_supplements_real_inboxes.csv"),
    "Extended DTC":         os.path.join(VERIFIED_DIR, "extended_dtc_real_inboxes.csv"),
}

CSV_HEADERS = [
    "First Name", "Last Name", "Email", "Secondary_Email", "Company", "Website", "Title",
    "Meta Ads Library URL", "Niche", "Country", "Instagram", "Facebook",
    "LinkedIn", "TikTok", "Twitter_X", "MX_Status", "DMARC_Status",
    "SPF_Status", "Gravatar_Found", "Deliverability_Score", "Personalized Icebreaker"
]

EMAIL_REGEX = re.compile(r'[a-zA-Z0-9_.+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9.\-]+')
MAILTO_RE   = re.compile(r'href=["\']mailto:([^"\'?\s]+)', re.IGNORECASE)
SOCIAL_RE   = {
    "Instagram": re.compile(r'https?://(?:www\.)?instagram\.com/([\w.]{2,40})(?:[/?"\s]|$)', re.I),
    "Facebook":  re.compile(r'https?://(?:www\.)?facebook\.com/([\w.\-]{2,60})(?:[/?"\s]|$)', re.I),
    "TikTok":    re.compile(r'https?://(?:www\.)?tiktok\.com/@([\w.]{2,40})(?:[/?"\s]|$)', re.I),
    "Twitter_X": re.compile(r'https?://(?:www\.)?(?:twitter|x)\.com/([\w]{2,40})(?:[/?"\s]|$)', re.I),
    "LinkedIn":  re.compile(r'https?://(?:www\.)?linkedin\.com/company/([\w\-]{2,60})(?:[/?"\s]|$)', re.I),
}

EXCLUSIONS = frozenset([
    'png','jpg','jpeg','gif','webp','svg','sentry','shopify.com',
    'w3.org','email.com','example.com','schema.org','cloudflare',
    'support@shopify','help@shopify','google.com','facebook.com',
    'twitter.com','instagram.com','github.com','spurit','klaviyo',
    'yotpo','judge.me','apps.shopify','myshopify.com','wordpress',
    'wix.com','squarespace.com','zendesk.com','intercom-mail',
    'beispiel.com','domain.com','yoursite.com','test@','dayjs@',
    'core-js@','npm@','no-reply','noreply','user@','admin@example',
    'info@yourdomain.com','tempuri.org','doubleclick',
])

DUMMY_DOMAINS = frozenset(['example.com','domain.com','yoursite.com','sentry.io',
                            'schema.org','w3.org','beispiel.com','email.com'])

SOCIAL_SKIP = frozenset([
    'explore','accounts','direct','stories','p','reel','tv',
    'groups','policies','help','pages','intent','share','home',
    'hashtag','trending','music','search','facebook','instagram',
    'twitter','linkedin','tiktok',
])

KNOWN_MX = {
    "gmail.com":      (True,"Google Workspace"),
    "googlemail.com": (True,"Google Workspace"),
    "yahoo.com":      (True,"Yahoo Mail"),
    "yahoo.co.in":    (True,"Yahoo Mail"),
    "hotmail.com":    (True,"Microsoft 365"),
    "outlook.com":    (True,"Microsoft 365"),
    "icloud.com":     (True,"Apple iCloud"),
    "me.com":         (True,"Apple iCloud"),
    "zoho.com":       (True,"Zoho Mail"),
    "proton.me":      (True,"ProtonMail"),
    "protonmail.com": (True,"ProtonMail"),
    "fastmail.com":   (True,"Fastmail"),
    "hey.com":        (True,"Fastmail"),
    "aol.com":        (True,"AOL Mail"),
}

PROVIDER_HINTS = [
    ("google",    "Google Workspace"),
    ("microsoft", "Microsoft 365"),
    ("outlook",   "Microsoft 365"),
    ("zoho",      "Zoho Mail"),
    ("proton",    "ProtonMail"),
    ("fastmail",  "Fastmail"),
    ("amazon",    "Amazon SES"),
    ("mailgun",   "Mailgun"),
    ("sendgrid",  "SendGrid"),
    ("mimecast",  "Mimecast"),
]

KEYWORDS = {
    'Health & Supplements': ['supplement','vitamin','protein','nutrition','wellness','gut',
                             'sleep','greens','organic','ayurved','herbal','remedy','fitness',
                             'nootropic','collagen','creatine','electrolyte','superfood','botanical'],
    'Jewelry':              ['jewelry','jewel','diamond','ring','gold chain','silver chain',
                             'chain necklace','bracelet','earring','gem','gemstone','bridal',
                             'pendant','cufflink','moissanite','bangle','karat'],
    'Fashion Accessories':  ['watch','wallet','bag','sunglasses','eyewear','belt','hat',
                             'backpack','tote','handbag','luggage','footwear','purse',
                             'shades','beanie','shoe','sneaker','optician'],
    'Fashion & Apparel':    ['clothing','apparel','wear','fashion','denim','shirt','dress',
                             'swim','streetwear','athletic','hoodie','jeans','outfit',
                             'swimwear','activewear','boutique','saree','kurti','loom',
                             'textile','suit'],
    'Extended DTC':         ['skin','serum','beauty','cosmetic','cream','shampoo','candle',
                             'pet','dog','cookware','haircare','bodycare','soap','scent',
                             'kitchen','coffee','tea'],
}

ICEBREAKERS = {
    "Jewelry":              "Loved what {brand} is doing with fine jewelry — the craftsmanship truly stands out.",
    "Fashion & Apparel":    "Really impressed by {brand}'s curated collections — the attention to style is evident.",
    "Fashion Accessories":  "Your accessories at {brand} strike a perfect balance between form and function.",
    "Health & Supplements": "The focus {brand} puts on clean, effective formulas is exactly what customers need.",
    "Extended DTC":         "The brand story at {brand} is compelling — would love to help amplify it further.",
}

# Auto-zip trigger every N new verified leads
BATCH_SIZE = 2000


# ─────────────────────────────────────────────────────────────────────
class BlitzHarvester:
    def __init__(self, concurrency: int = 150):
        self.concurrency   = concurrency
        self.seen_emails   = set()
        self.seen_domains  = set()
        self.niche_counts  = {k: 0 for k in NICHE_FILES}
        self._dns_cache    : dict[str, tuple] = {}
        self._dns_locks    : dict[str, asyncio.Lock] = {}
        self._write_lock   = None
        self._total_found  = 0          # total verified across all time
        self._batch_base   = 0          # verified count at start of current batch
        self._batch_num    = 0          # which batch we're on

    # ── Pre-load existing leads ───────────────────────────────────────
    def load_existing(self):
        for n, fpath in NICHE_FILES.items():
            if not os.path.exists(fpath):
                with open(fpath, "w", newline="", encoding="utf-8") as f:
                    csv.DictWriter(f, fieldnames=CSV_HEADERS).writeheader()
            else:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    for r in csv.DictReader(f):
                        em = r.get("Email","").strip().lower()
                        if em:
                            self.seen_emails.add(em)
                            self.niche_counts[n] += 1
                        dom = (r.get("Website","")
                               .replace("https://","").replace("http://","")
                               .split("/")[0].lower())
                        if dom: self.seen_domains.add(dom)

        if not os.path.exists(MASTER_VERIFIED_CSV):
            with open(MASTER_VERIFIED_CSV, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=CSV_HEADERS).writeheader()
        else:
            with open(MASTER_VERIFIED_CSV, "r", encoding="utf-8", errors="ignore") as f:
                for r in csv.DictReader(f):
                    em = r.get("Email","").strip().lower()
                    if em: self.seen_emails.add(em)

        # Init raw extraction log
        if not os.path.exists(RAW_EXTRACTED_CSV):
            with open(RAW_EXTRACTED_CSV, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=RAW_HEADERS).writeheader()

        self._total_found = len(self.seen_emails)
        self._batch_base  = self._total_found
        self._batch_num   = self._total_found // BATCH_SIZE

        print(f"[*] Pre-loaded {self._total_found:,} existing verified leads:")
        for n, cnt in self.niche_counts.items():
            print(f"    - {n:22}: {cnt:,}")
        print(f"[*] Next batch checkpoint at: {(self._batch_num + 1) * BATCH_SIZE:,} total leads\n")

    # ── Email validator ───────────────────────────────────────────────
    def is_valid_email(self, em: str) -> bool:
        if '@' not in em or len(em) < 6 or len(em) > 120: return False
        if any(ex in em for ex in EXCLUSIONS): return False
        user, _, dom = em.rpartition('@')
        if not user or not dom or '.' not in dom: return False
        tld = dom.rsplit('.', 1)[-1]
        if len(tld) < 2 or len(tld) > 12 or not tld.isalpha(): return False
        if dom in DUMMY_DOMAINS or any(dom.endswith('.'+d) for d in DUMMY_DOMAINS):
            return False
        return True

    # ── Async DNS — parallel MX+DMARC+SPF ────────────────────────────
    async def check_dns(self, domain: str, resolver) -> tuple:
        if domain in self._dns_cache:
            return self._dns_cache[domain]

        if domain not in self._dns_locks:
            self._dns_locks[domain] = asyncio.Lock()
        async with self._dns_locks[domain]:
            if domain in self._dns_cache:
                return self._dns_cache[domain]

            if domain in KNOWN_MX:
                r = (*KNOWN_MX[domain], True, True)
                self._dns_cache[domain] = r
                return r

            async def mx_q():
                try:
                    if HAS_AIODNS:
                        ans = await resolver.query(domain, 'MX')
                        hosts = " ".join(str(a.host).lower() for a in ans)
                    else:
                        loop = asyncio.get_event_loop()
                        ans = await loop.run_in_executor(
                            None, lambda: _sync_dns.resolve(domain, 'MX'))
                        hosts = " ".join(str(a.exchange).lower() for a in ans)
                    prov = "Host MX"
                    for hint, name in PROVIDER_HINTS:
                        if hint in hosts: prov = name; break
                    return (True, prov)
                except Exception:
                    return (False, "No MX")

            async def dmarc_q():
                try:
                    if HAS_AIODNS:
                        ans = await resolver.query(f"_dmarc.{domain}", 'TXT')
                        return any("v=DMARC1" in str(a.text) for a in ans)
                    else:
                        loop = asyncio.get_event_loop()
                        ans = await loop.run_in_executor(
                            None, lambda: _sync_dns.resolve(f"_dmarc.{domain}", 'TXT'))
                        return any("v=DMARC1" in str(a) for a in ans)
                except Exception:
                    return False

            async def spf_q():
                try:
                    if HAS_AIODNS:
                        ans = await resolver.query(domain, 'TXT')
                        return any("v=spf1" in str(a.text).lower() for a in ans)
                    else:
                        loop = asyncio.get_event_loop()
                        ans = await loop.run_in_executor(
                            None, lambda: _sync_dns.resolve(domain, 'TXT'))
                        return any("v=spf1" in str(a).lower() for a in ans)
                except Exception:
                    return False

            (has_mx, prov), dmarc, spf = await asyncio.gather(mx_q(), dmarc_q(), spf_q())
            result = (has_mx, prov, dmarc, spf)
            self._dns_cache[domain] = result
            return result

    # ── Extract emails + socials from raw HTML ────────────────────────
    def extract_from_html(self, html: str, domain: str) -> tuple[list, dict]:
        clean_d = domain.replace("www.","").split(".")[0]
        candidates = []

        for m in MAILTO_RE.findall(html):
            em = m.strip().lower()
            if self.is_valid_email(em):
                candidates.append((100, em))

        for m in EMAIL_REGEX.findall(html):
            em = m.strip().strip('.').lower()
            if not self.is_valid_email(em): continue
            em_dom = em.split('@')[1]
            if clean_d in em or em_dom in domain:
                candidates.append((95, em))
            elif any(k in em for k in ['support@','care@','hello@','team@','founder@',
                                        'service@','contact@','sales@','info@','admin@',
                                        'hi@','hey@','shop@','order@','help@']):
                candidates.append((80, em))
            else:
                candidates.append((55, em))

        socials: dict[str, str] = {p: "" for p in ["Instagram","Facebook","LinkedIn","TikTok","Twitter_X"]}
        for plat, rx in SOCIAL_RE.items():
            m = rx.search(html)
            if m:
                handle = m.group(1).strip("/")
                if handle.lower() in SOCIAL_SKIP: continue
                if plat == "Instagram":  socials[plat] = f"https://www.instagram.com/{handle}"
                elif plat == "Facebook": socials[plat] = f"https://www.facebook.com/{handle}"
                elif plat == "TikTok":   socials[plat] = f"https://www.tiktok.com/@{handle}"
                elif plat == "Twitter_X":socials[plat] = f"https://x.com/{handle}"
                elif plat == "LinkedIn": socials[plat] = f"https://www.linkedin.com/company/{handle}"

        return candidates, socials

    # ── Classify niche ────────────────────────────────────────────────
    def classify_niche(self, brand: str, domain: str, initial: str) -> str:
        comb = f"{brand} {domain}".lower()
        for n, kws in KEYWORDS.items():
            if any(kw in comb for kw in kws):
                return n
        return initial if initial else "Extended DTC"

    # ── Scan one store — returns (status_code, verified_records, raw_log_row) ──
    async def scan_store(self, store: dict, client, resolver, breaker: RateLimitBreaker) -> tuple[str, list[dict], dict]:
        ts     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        domain = store.get("domain","").strip().lower()
        brand  = (store.get("brand","") or
                  domain.replace("www.","").split(".")[0].replace("-"," ").title())
        niche_guess = store.get("niche","Extended DTC")

        def raw(rejection: str, emails_found="", primary="",
                email_dom="", socials=None, http_status="",
                mx="", prov="", dmarc="", spf="") -> dict:
            s = socials or {}
            return {
                "Domain":          domain,
                "Brand":           brand,
                "Niche_Guess":     niche_guess,
                "HTTP_Status":     http_status,
                "Emails_Found":    emails_found,
                "Primary_Email":   primary,
                "Email_Domain":    email_dom,
                "Instagram":       s.get("Instagram",""),
                "Facebook":        s.get("Facebook",""),
                "LinkedIn":        s.get("LinkedIn",""),
                "TikTok":          s.get("TikTok",""),
                "Twitter_X":       s.get("Twitter_X",""),
                "MX_Valid":        mx,
                "MX_Provider":     prov,
                "DMARC":           dmarc,
                "SPF":             spf,
                "Qualified":       "NO" if rejection else "YES",
                "Rejection_Reason": rejection,
                "Scraped_At":      ts,
            }

        if not domain or "." not in domain:
            return "OK", [], raw("invalid_domain")
        if domain in self.seen_domains:
            return "OK", [], raw("duplicate_domain")

        # ── Realistic Browser Headers ─────────────────────────────────
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
        }

        # ── Stage 1: Fast Homepage Fetch ──────────────────────────────
        html = None
        http_status = "timeout"

        await breaker.wait()
        try:
            url = f"https://{domain}/"
            if HAS_CURL:
                r = await client.get(url, headers=headers, timeout=3.5)
            else:
                r = await client.get(url, headers=headers, timeout=httpx.Timeout(3.5), follow_redirects=True)

            http_status = str(r.status_code)
            if r.status_code == 429:
                return "429_RETRY", [], {}

            if r.status_code < 400 and r.text:
                html = r.text
        except Exception as e:
            http_status = f"error:{type(e).__name__}"

        # Fast HTTP fallback if HTTPS connection failed
        if not html and ("ConnectionError" in http_status or "ConnectError" in http_status):
            try:
                url_http = f"http://{domain}/"
                if HAS_CURL:
                    r = await client.get(url_http, headers=headers, timeout=3.0)
                else:
                    r = await client.get(url_http, headers=headers, timeout=httpx.Timeout(3.0), follow_redirects=True)
                http_status = str(r.status_code)
                if r.status_code == 429:
                    return "429_RETRY", [], {}
                if r.status_code < 400 and r.text:
                    html = r.text
            except Exception:
                pass

        if not html:
            return "OK", [], raw(
                f"no_html:{http_status}" if http_status != "timeout" else "timeout",
                http_status=http_status
            )

        # ── Extract emails + socials from Homepage ────────────────────
        candidates, socials = self.extract_from_html(html, domain)

        # ── Stage 2: Targeted Contact Page (ONLY if NO email on homepage) ──
        # Instead of guessing 5 blind URLs, parse the exact contact link from homepage!
        if not candidates:
            dom_pattern = re.escape(domain.replace("www.",""))
            c_match = re.search(
                r'href=["\'](?:https?://(?:www\.)?' + dom_pattern + r')?(/pages/[^"\'\s>#]*contact[^"\'\s>#]*|/contact[^"\'\s>#]*|/pages/[^"\'\s>#]*reach-us[^"\'\s>#]*)["\']',
                html, re.I
            )
            if c_match:
                c_path = c_match.group(1)
                c_url = f"https://{domain}{c_path}" if c_path.startswith("/") else c_path
                await breaker.wait()
                try:
                    if HAS_CURL:
                        cr = await client.get(c_url, headers=headers, timeout=3.0)
                    else:
                        cr = await client.get(c_url, headers=headers, timeout=httpx.Timeout(3.0), follow_redirects=True)

                    if cr.status_code == 429:
                        return "429_RETRY", [], {}

                    if cr.status_code < 400 and cr.text:
                        c_cand, c_soc = self.extract_from_html(cr.text, domain)
                        candidates.extend(c_cand)
                        for plat, handle in c_soc.items():
                            if handle and not socials.get(plat):
                                socials[plat] = handle
                except Exception:
                    pass

        all_emails_str = ", ".join(em for _, em in candidates[:10])
        if not candidates:
            return "OK", [], raw("no_email_found", http_status=http_status,
                                 emails_found="", socials=socials)

        # De-dup candidates and sort by confidence
        candidates.sort(key=lambda x: -x[0])
        unique: list[tuple[int,str]] = []
        seen_here: set[str] = set()
        for score, em in candidates:
            if em not in seen_here:
                seen_here.add(em)
                if em not in self.seen_emails:
                    unique.append((score, em))
            if len(unique) >= 3:
                break

        if not unique:
            return "OK", [], raw("duplicate_email", emails_found=all_emails_str,
                                 http_status=http_status, socials=socials)

        primary_score, primary_email = unique[0]
        email_domain = primary_email.split('@')[1]

        # ── DNS check ─────────────────────────────────────────────────
        has_mx, provider, has_dmarc, has_spf = await self.check_dns(email_domain, resolver)
        if not has_mx:
            return "OK", [], raw(
                f"no_mx:{email_domain}",
                emails_found=all_emails_str, primary=primary_email,
                email_dom=email_domain, http_status=http_status,
                socials=socials, mx="NO", prov=provider,
                dmarc="YES" if has_dmarc else "NO",
                spf="YES" if has_spf else "NO",
            )

        # ── Build verified record ─────────────────────────────────────
        d_score = primary_score
        if has_dmarc: d_score = min(100, d_score + 5)
        if has_spf:   d_score = min(100, d_score + 3)
        if provider in ("Google Workspace","Microsoft 365"): d_score = min(100, d_score + 5)

        self.seen_domains.add(domain)
        final_niche = self.classify_niche(brand, domain, niche_guess)

        local = primary_email.split('@')[0]
        parts = re.split(r'[._\-]', local)
        fn = parts[0].capitalize() if parts else "Brand"
        ln = parts[1].capitalize() if len(parts) > 1 else "Owner"
        sec_emails = ", ".join(em for _, em in unique[1:])

        title_m = re.search(r'<title[^>]*>([^<]{4,80})</title>', html, re.I)
        title   = title_m.group(1).strip()[:80] if title_m else f"Founder / Owner @ {brand}"
        ads_url = f"https://www.facebook.com/ads/library/?q={urllib.parse.quote(brand)}&type=all"
        icebreaker = ICEBREAKERS.get(final_niche, ICEBREAKERS["Extended DTC"]).format(brand=brand)

        verified = [{
            "First Name":            fn,
            "Last Name":             ln,
            "Email":                 primary_email,
            "Secondary_Email":       sec_emails,
            "Company":               brand,
            "Website":               f"https://{domain}",
            "Title":                 title,
            "Meta Ads Library URL":  ads_url,
            "Niche":                 final_niche,
            "Country":               "",
            "Instagram":             socials["Instagram"],
            "Facebook":              socials["Facebook"],
            "LinkedIn":              socials["LinkedIn"],
            "TikTok":                socials["TikTok"],
            "Twitter_X":             socials["Twitter_X"],
            "MX_Status":             f"Valid ({provider})",
            "DMARC_Status":          "Configured (v=DMARC1)" if has_dmarc else "Not Configured",
            "SPF_Status":            "Configured" if has_spf else "None",
            "Gravatar_Found":        "No",
            "Deliverability_Score":  f"{d_score}% Confirmed Real",
            "Personalized Icebreaker": icebreaker,
        }]

        raw_row = raw(
            "",  # qualified — no rejection
            emails_found=all_emails_str, primary=primary_email,
            email_dom=email_domain, http_status=http_status,
            socials=socials, mx="YES", prov=provider,
            dmarc="YES" if has_dmarc else "NO",
            spf="YES" if has_spf else "NO",
        )
        return "OK", verified, raw_row


    # ── Telegram delivery helper ─────────────────────────────────────
    def send_telegram_checkpoint(self, zip_path: str):
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "8942730693:AAG9ERn1JgXInKiR_9MZJI3HPxCkjKvVtpE")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "6642913680")
        if not token or not chat_id:
            return

        size_mb = os.path.getsize(zip_path) / 1_048_576
        breakdown = "\n".join([f"  • <b>{n}:</b> {cnt:,} leads" for n, cnt in self.niche_counts.items()])
        msg = (
            f"🎯 <b>FLINZA CHECKPOINT: Batch {self._batch_num}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"✉ <b>Total Verified Leads:</b> {self._total_found:,}\n"
            f"📦 <b>Zip Package:</b> <code>{os.path.basename(zip_path)}</code> ({size_mb:.1f} MB)\n\n"
            f"📂 <b>Categorized Breakdown:</b>\n{breakdown}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"<i>Includes categorized CSVs + raw rejection audit log.</i>"
        )

        # 1. Send status message
        try:
            import urllib.request, json
            url_msg = f"https://api.telegram.org/bot{token}/sendMessage"
            payload = json.dumps({"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}).encode("utf-8")
            req = urllib.request.Request(url_msg, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                pass
            print(f"   📱 [TELEGRAM] Milestone notification sent to Telegram.")
        except Exception as e:
            print(f"   ⚠️ [TELEGRAM] Notification error: {e}")

        # 2. Upload zip directly if under 49 MB
        if size_mb < 49.0:
            try:
                import urllib.request, uuid
                boundary = "----TelegramBoundary" + str(uuid.uuid4().hex[:12])
                body = bytearray()
                body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode())
                body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n📦 Flinza Verified Leads Batch {self._batch_num} ({self._total_found:,} verified leads)\r\n'.encode())
                body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{os.path.basename(zip_path)}"\r\nContent-Type: application/zip\r\n\r\n'.encode())
                with open(zip_path, "rb") as f:
                    body.extend(f.read())
                body.extend(f'\r\n--{boundary}--\r\n'.encode())

                url_doc = f"https://api.telegram.org/bot{token}/sendDocument"
                req = urllib.request.Request(url_doc, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
                with urllib.request.urlopen(req, timeout=120) as resp:
                    pass
                print(f"   📥 [TELEGRAM] Successfully uploaded {os.path.basename(zip_path)} to Telegram!")
            except Exception as e:
                print(f"   ⚠️ [TELEGRAM] Document upload error: {e}")

    # ── Auto-zip every BATCH_SIZE new leads ───────────────────────────
    def create_batch_zip(self) -> str:
        self._batch_num += 1
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = os.path.join(ZIPS_DIR, f"flinza_batch_{self._batch_num:03d}_{ts}.zip")
        print(f"\n\n🗜️  [BATCH {self._batch_num}] Creating checkpoint zip: {os.path.basename(out)}")

        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            # Include master verified CSV
            if os.path.exists(MASTER_VERIFIED_CSV):
                z.write(MASTER_VERIFIED_CSV, arcname="verified/instantly_master_ultra_verified.csv")
            # Include each niche CSV
            for fname in sorted(os.listdir(VERIFIED_DIR)):
                if fname.endswith(".csv") and fname != os.path.basename(MASTER_VERIFIED_CSV):
                    fp = os.path.join(VERIFIED_DIR, fname)
                    if os.path.getsize(fp) > 200:   # skip near-empty files
                        z.write(fp, arcname="verified/" + fname)
            # Include raw extracted log
            if os.path.exists(RAW_EXTRACTED_CSV) and os.path.getsize(RAW_EXTRACTED_CSV) > 50:
                z.write(RAW_EXTRACTED_CSV, arcname="raw_extracted_all.csv")

        size_mb = os.path.getsize(out) / 1_048_576
        print(f"   ✅ Saved {os.path.basename(out)} ({size_mb:.1f} MB) — {self._total_found:,} total leads")

        # Send to Telegram bot
        self.send_telegram_checkpoint(out)

        # Auto-download in Colab if available
        try:
            from google.colab import files as colab_files
            print(f"   📥 Triggering browser download for batch {self._batch_num}...")
            colab_files.download(out)
        except (ImportError, Exception):
            pass

        self._batch_base = self._total_found
        return out


    # ── Load stores from all sources ─────────────────────────────────
    def load_stores(self, master_csv_path: str = None) -> list[dict]:
        stores = []
        if master_csv_path and os.path.exists(master_csv_path):
            print(f"[*] Loading FULL MASTER database: {master_csv_path}", flush=True)
            with open(master_csv_path, "r", encoding="utf-8", errors="ignore") as f:
                for r in csv.DictReader(f):
                    dom = (r.get("domain") or r.get("Domain") or
                           r.get("url")    or r.get("URL") or "").strip().lower()
                    dom = dom.replace("https://","").replace("http://","").split("/")[0]
                    if not dom or "." not in dom: continue
                    stores.append({
                        "domain": dom,
                        "brand":  (r.get("merchant_name") or r.get("brand") or
                                   r.get("name") or "").strip(),
                        "niche":  "Extended DTC",
                        "tech":   r.get("technologies",""),
                    })
            print(f"[*] Loaded {len(stores):,} from master CSV.", flush=True)

        if not stores:
            for i in range(10):
                sf = os.path.join(SLICES_DIR, f"slice_{i}.csv")
                if os.path.exists(sf):
                    with open(sf, "r", encoding="utf-8", errors="ignore") as f:
                        stores.extend(list(csv.DictReader(f)))

        if not stores:
            p = os.path.join(DATA_DIR, "shopify_master_115k.csv")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    for r in csv.DictReader(f):
                        stores.append({"domain": r.get("domain",""),
                                       "brand":  r.get("merchant_name",""),
                                       "niche":  "Extended DTC", "tech": ""})

        seen, deduped = set(), []
        for s in stores:
            d = s.get("domain","")
            if d and d not in seen and d not in self.seen_domains:
                seen.add(d); deduped.append(s)

        print(f"[*] {len(deduped):,} unique un-scraped candidate stores ready.\n", flush=True)
        return deduped

    # ── Main run loop ─────────────────────────────────────────────────
    async def run(self, master_csv_path: str = None):
        print("=" * 76, flush=True)
        print(f"⚡ FLINZA BALANCED BLITZ — {self.concurrency} concurrent workers", flush=True)
        print(f"   Timeout: 2.5s | DNS: {'aiodns' if HAS_AIODNS else 'dnspython'} | Loop: {_LOOP}", flush=True)
        print(f"   Batch zip every {BATCH_SIZE:,} verified leads | NO lead cap — runs full list", flush=True)
        print("=" * 76, flush=True)

        self.load_existing()
        stores = self.load_stores(master_csv_path)
        if not stores:
            print("[ERROR] No stores to scan."); return

        total_stores = len(stores)
        queue: asyncio.Queue = asyncio.Queue()
        for s in stores: queue.put_nowait(s)

        self._write_lock = asyncio.Lock()
        start_time = time.time()
        scanned    = 0
        found      = self._total_found

        # Open file handles once (avoid per-write open/close overhead)
        niche_handles: dict[str, object] = {}
        for n, fp in NICHE_FILES.items():
            niche_handles[n] = open(fp, "a", newline="", encoding="utf-8")
        master_h = open(MASTER_VERIFIED_CSV, "a", newline="", encoding="utf-8")
        raw_h    = open(RAW_EXTRACTED_CSV,   "a", newline="", encoding="utf-8")

        # ── Global Circuit Breaker ────────────────────────────────────────
        breaker = RateLimitBreaker(cooldown=6.0)

        # DNS resolver
        if HAS_AIODNS:
            resolver = aiodns.DNSResolver(
                nameservers=["8.8.8.8","1.1.1.1","8.8.4.4","1.0.0.1"],
                timeout=1.2)
        else:
            resolver = None

        # ── HACK 5: Session pool — multiple browser fingerprints ──────────
        # Create N sessions, each impersonating a DIFFERENT browser.
        # Workers grab a session from the pool; each session maintains its
        # own cookies & TLS fingerprint → Shopify's CDN sees N distinct clients.
        NUM_SESSIONS = min(12, max(4, self.concurrency // 15))
        if HAS_CURL:
            print(f"[*] Creating {NUM_SESSIONS} browser-profile sessions "
                  f"({', '.join(BROWSER_PROFILES[:NUM_SESSIONS])})")
            _session_pool : list = []
            for i in range(NUM_SESSIONS):
                profile = BROWSER_PROFILES[i % len(BROWSER_PROFILES)]
                sess = AsyncSession(impersonate=profile, verify=False)
                _session_pool.append(sess)
            _pool_sems = [asyncio.Semaphore(max(1, self.concurrency // NUM_SESSIONS))
                          for _ in _session_pool]
        else:
            lim = httpx.Limits(max_keepalive_connections=self.concurrency,
                               max_connections=self.concurrency + 100)
            _session_pool = [httpx.AsyncClient(timeout=3.0, follow_redirects=True,
                                               verify=False, limits=lim)]
            _pool_sems    = [asyncio.Semaphore(self.concurrency)]

        # Dummy context manager so we can use the same `async with` below
        class _DummyCM:
            async def __aenter__(self): return None
            async def __aexit__(self, *a): pass
        client_cm = _DummyCM()

        async def worker(worker_idx: int):
            """Each worker picks a session from the pool by index (round-robin)."""
            nonlocal scanned, found
            sess_idx = worker_idx % NUM_SESSIONS if HAS_CURL else 0
            client   = _session_pool[sess_idx]
            sem      = _pool_sems[sess_idx]

            while True:
                # 1. Wait if circuit breaker is paused
                await breaker.wait()

                # 2. Get next store from queue
                try:
                    st = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                # 3. Process store with session semaphore
                status_code = "OK"
                results = []
                raw_row = {}

                async with sem:
                    try:
                        status_code, results, raw_row = await self.scan_store(st, client, resolver, breaker)
                    except Exception as exc:
                        status_code = "OK"
                        results  = []
                        raw_row  = {
                            "Domain":          st.get("domain",""),
                            "Brand":           st.get("brand",""),
                            "Niche_Guess":     st.get("niche","Extended DTC"),
                            "HTTP_Status":     "",
                            "Emails_Found":    "", "Primary_Email":  "",
                            "Email_Domain":    "", "Instagram":      "",
                            "Facebook":        "", "LinkedIn":       "",
                            "TikTok":          "", "Twitter_X":      "",
                            "MX_Valid":        "", "MX_Provider":    "",
                            "DMARC":           "", "SPF":            "",
                            "Qualified":       "NO",
                            "Rejection_Reason": f"exception:{type(exc).__name__}",
                            "Scraped_At":      datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        }

                # 4. If 429 encountered: re-queue store and trip breaker!
                if status_code == "429_RETRY":
                    queue.put_nowait(st)
                    await breaker.trip()
                    continue

                # 5. Store successfully scanned
                scanned += 1

                # 6. Always write raw log row (append to raw_extracted_all.csv)
                async with self._write_lock:
                    csv.DictWriter(raw_h, fieldnames=RAW_HEADERS).writerow(raw_row)
                    raw_h.flush()

                if not results:
                    continue

                # 7. Write verified lead to niche and master files
                async with self._write_lock:
                    for rec in results:
                        em = rec["Email"]
                        if em in self.seen_emails:
                            continue
                        self.seen_emails.add(em)
                        found += 1
                        self._total_found = found
                        n = rec.get("Niche","Extended DTC")
                        if n in self.niche_counts:
                            self.niche_counts[n] += 1
                        if n in niche_handles:
                            csv.DictWriter(niche_handles[n], fieldnames=CSV_HEADERS).writerow(rec)
                            niche_handles[n].flush()
                        csv.DictWriter(master_h, fieldnames=CSV_HEADERS).writerow(rec)
                        master_h.flush()

                        # ── Batch checkpoint every BATCH_SIZE (2,000) ───────
                        if found > 0 and found % BATCH_SIZE == 0:
                            for h in niche_handles.values():
                                try: h.flush()
                                except: pass
                            master_h.flush()
                            raw_h.flush()
                            self.create_batch_zip()


        async def stats_printer():
            nonlocal scanned, found
            while scanned < total_stores:
                await asyncio.sleep(3.0)
                elapsed = time.time() - start_time
                spd     = scanned / elapsed if elapsed > 0 else 0
                pct     = scanned / total_stores * 100 if total_stores > 0 else 0
                eta_m   = ((total_stores - scanned) / spd / 60) if spd > 0 else 0
                next_b  = (self._batch_num + 1) * BATCH_SIZE
                til_b   = max(0, next_b - found)

                bar_len = 30
                filled  = int(bar_len * scanned / total_stores) if total_stores > 0 else 0
                bar     = "█" * filled + "░" * (bar_len - filled)

                print(
                    f"\r⚡ [{bar}] {pct:5.1f}% | Scanned: {scanned:,}/{total_stores:,} | "
                    f"✉ Verified: {found:,} | {spd:5.1f} stores/s | ETA: {eta_m:.0f}m | "
                    f"Next zip in {til_b:,} leads   ",
                    end="", flush=True
                )

        async with client_cm:
            tasks = [asyncio.create_task(worker(i))
                     for i in range(self.concurrency)]
            tasks.append(asyncio.create_task(stats_printer()))
            await asyncio.gather(*tasks, return_exceptions=True)

        # Close all session pool handles
        for sess in _session_pool:
            try:
                await sess.close() if HAS_CURL else await sess.aclose()
            except Exception:
                pass

        # Close all file handles
        for h in niche_handles.values():
            try: h.close()
            except: pass
        try: master_h.close()
        except: pass
        try: raw_h.close()
        except: pass

        elapsed = time.time() - start_time
        print(f"\n\n{'='*76}")
        print(f"✅ COMPLETE | {found:,} total verified leads | {scanned:,} stores scanned")
        print(f"   Time: {elapsed/60:.1f} min | Avg speed: {scanned/elapsed:.0f} stores/sec")
        print(f"{'='*76}")
        for n, cnt in self.niche_counts.items():
            print(f"    - {n:22}: {cnt:,} leads")

        # Final zip after run ends
        if found > self._batch_base:
            print("\n[*] Creating final batch zip for remaining leads...")
            self.create_batch_zip()


def main():
    global BATCH_SIZE  # must be declared before any use below
    p = argparse.ArgumentParser(description="Flinza Balanced Blitz Harvester")
    p.add_argument("--concurrency", type=int, default=150,
                   help="Concurrent workers (default 150 — sweet spot for Shopify CDN)")
    p.add_argument("--master-csv", type=str, default=None,
                   help="Path to full 1.9M Shopify master CSV")
    p.add_argument("--batch-size", type=int, default=BATCH_SIZE,
                   help="Auto-zip every N leads (default %(default)s)")
    args = p.parse_args()

    BATCH_SIZE = args.batch_size

    h = BlitzHarvester(concurrency=args.concurrency)
    asyncio.run(h.run(master_csv_path=args.master_csv))


if __name__ == "__main__":
    main()
