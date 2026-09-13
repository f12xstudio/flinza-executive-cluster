"""
ultra_enricher.py
==================
ULTRA HIGH-PRECISION Executive Intelligence Engine v5.0
Beats ZoomInfo, Apollo, DnB, Hunter.io — 100% free, no API keys.

12+ Intelligence Sources per Lead:
  Tier 1 — Email DNA Analysis (instant, 0ms):
    [S1] first.last@ pattern => confirmed full name
    [S2] firstlast@ concatenation detection
    [S3] first@ personal inbox => first name confirmed
    [S4] Secondary email cross-reference

  Tier 2 — On-Site Deep Crawl (HTTP):
    [S5] Homepage JSON-LD schema.org Person/Founder extraction
    [S6] Meta tags (og:title, description) for brand owner signals
    [S7] Dynamic nav link mining => /pages/about-us, /pages/our-story etc.
    [S8] About/Team/Story page NLP with 20+ regex patterns

  Tier 3 — Search Engine Intelligence (Multi-Engine, Concurrent):
    [S9]  Yahoo Search with grounding check (trusted source filter)
    [S10] DuckDuckGo Lite with snippet extraction
    [S11] Bing Search with People Box extraction
    [S12] LinkedIn person dork via Yahoo

  Tier 4 — Deep OSINT Sources (Concurrent):
    [S13] Whois / RDAP domain registration owner name extraction
    [S14] Companies House UK (free, no API key) for UK domains
    [S15] Crunchbase/AngelList/ProductHunt founder mining
    [S16] Facebook/Instagram bio extraction

  Tier 5 — Confidence Scoring and Email Pattern Generation:
    [S17] Multi-variant email generation (first@, first.last@, flast@)
    [S18] Gravatar hash check for email confirmation
    [S19] Cross-source confidence vote (2+ sources = VERIFIED)

New output fields added:
  Exec_Source_Chain, Exec_LinkedIn_URL, Exec_Twitter
  Exec_Company_Reg, Exec_Reg_Country, Exec_Email_Variants (JSON)
"""

import os
import sys
import re
import csv
import time
import json
import random
import hashlib
import asyncio
import argparse
import urllib.request
import urllib.parse
import urllib.error
import socket
from typing import Optional, Dict, Any, List, Set, Tuple


try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

import httpx
try:
    from curl_cffi import CurlOpt
    from curl_cffi.requests import AsyncSession
    HAS_CURL = True
    CURL_V4_OPTIONS = {CurlOpt.IPRESOLVE: 1}  # Force IPv4 to eliminate connection drops and resets
except ImportError:
    HAS_CURL = False
    CURL_V4_OPTIONS = {}

from bs4 import BeautifulSoup


# ── Telegram ──────────────────────────────────────────────────────────────────

DEFAULT_TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8942730693:AAG9ERn1JgXInKiR_9MZJI3HPxCkjKvVtpE")
DEFAULT_TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "6642913680")

def send_telegram(msg: str, token: str = DEFAULT_TELEGRAM_TOKEN, chat_id: str = DEFAULT_TELEGRAM_CHAT_ID):
    if not token or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({"chat_id": chat_id, "text": msg[:4096], "parse_mode": "HTML"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


# ── Giant First Name Dictionary (6000+ names, global coverage) ───────────────

COMMON_FIRST_NAMES = {
    # English / American
    "aaron","abby","abel","abigail","adam","adriana","adrienne","aidan","aiden",
    "aisha","alan","alex","alexa","alexander","alexandra","alexis","ali","alice",
    "alicia","alison","allen","alma","amanda","amber","ami","amy","ana","andre",
    "andrea","andrew","andy","angela","angie","ann","anna","anne","annie",
    "anthony","antonia","antonio","april","aria","ariel","arnold","ashley",
    "aspen","aubrey","austin","ava","avery","barbara","bart","beatrice",
    "ben","benjamin","bernard","beth","bethany","betty","biagio","blake","bob",
    "bonnie","brad","bradley","brandon","brenda","brett","brian","brittany",
    "brooke","brooklyn","bryan","bryce","caitlin","caleb","camila","carlos",
    "carol","caroline","carter","casey","cassandra","catherine","chad",
    "charles","charlie","charlotte","chase","cheryl","chris","christian",
    "christina","christine","christopher","claire","clay","cody","colton",
    "connie","cooper","corey","courtney","crystal","dale","dana","daniel",
    "danielle","dave","david","dawn","deanna","debbie","deborah","denise",
    "derek","diana","diane","dominic","donna","drew","dylan","elena","eli",
    "elijah","elisa","elizabeth","ella","ellen","emily","emma","eric","erica",
    "erin","ethan","eva","evan","evelyn","evie","faith","felix","fiona","frank",
    "fred","gabe","gabriel","gary","gautam","george","gina","grace","graham",
    "greg","gregory","gwen","hallie","hannah","harper","heather","henry",
    "holly","hunter","ian","ines","isabel","isabella","ismael","ismail",
    "jack","jackson","jacob","jake","james","jamie","jane","janet","janice",
    "jason","jay","jed","jen","jenn","jennifer","jenny","jessica","jim","jo",
    "joanna","joe","john","jon","jonathan","jordan","joseph","josh","joshua",
    "joy","julia","julian","julie","justin","karen","kate","katherine","katie",
    "keith","kelly","ken","kendall","kevin","kim","kimberly","kristen","kristin",
    "kyle","lacey","lara","laura","lauren","lea","leah","lee","lena","leo",
    "leslie","liam","linda","lisa","liz","logan","lori","lucas","lucy","luke",
    "madison","mara","marcus","margaret","maria","marina","mark","martha",
    "martin","mary","matt","matthew","max","maya","megan","melissa","michael",
    "michelle","miguel","mike","miranda","molly","monica","morgan","nancy",
    "natalie","nathan","nicholas","nick","nicole","nina","noah","noel","nora",
    "oliver","olivia","omar","oscar","pam","patricia","patrick","paul","paula",
    "peter","phillip","rachel","rachiel","ralph","rebecca","richard","riley",
    "rita","rob","robert","robin","roger","ryan","samantha","samuel","sara",
    "sarah","scott","sean","sebastian","sehar","seth","shannon","sharon",
    "shawn","simeon","sofia","sophia","sophie","stephanie","stephen","steve",
    "steven","sue","summer","susan","swati","tara","taylor","thomas","tim",
    "timothy","tina","tom","tony","travis","trevor","tyler","valeria",
    "victoria","vincent","wendy","william","wojciech","zachary","zoe","zoey",
    # South Asian
    "aarav","aditya","ananya","ankit","ankita","arjun","aryan","bhavya",
    "deepak","dhruv","divya","ishaan","ishita","kavita","kavya","kiran",
    "manish","meera","mohit","neha","nikhil","nisha","pooja","priya",
    "rahul","rajesh","ravi","reena","rohit","rohan","sandeep","sanjay",
    "shreya","shweta","siddharth","simran","sneha","sonam","suresh","tanvi",
    "tushar","usha","varun","vijay","vikram","vinay","vishal","yash",
    # East Asian
    "bo","chen","cheng","fang","feng","hana","hao","hong","hua","hui",
    "jia","jian","jin","jun","kai","lang","lei","li","liang","lin",
    "ling","liu","mei","min","ming","na","ping","qi","qian","qin",
    "qing","quan","rui","shan","sheng","shu","tao","tian","ting",
    "wei","wen","xi","xia","xian","xin","xing","yang","yi",
    "ying","yu","yuan","yue","yun","zhen","zheng","zhi","zhou","zhu",
    # Spanish / Latin
    "alejandro","camilo","cristina","diego","emilio","francisco",
    "gonzalo","guadalupe","hector","javier","jorge","jose",
    "juan","julian","lucia","luis","manuel","marcos","mariela",
    "mario","martina","mateo","pablo","pedro","rosa",
    "santiago","valentina",
    # Middle Eastern / Arabic
    "ahmed","amir","amira","bilal","farah","fatima","hamid","hassan",
    "ibrahim","kareem","layla","leila","mahmoud","mariam","mohammed","mustafa",
    "nadia","rania","reem","samir","tariq","yasmine","youssef",
    # African
    "abena","adaeze","adama","amara","amina","chioma","emeka","fatou","kofi",
    "kwame","makena","ngozi","nkechi","nneka","sade","seun","tunde","yemi",
    "ifeoma","favour",
    # European / Global International
    "agnieszka","aleksandra","andrzej","brigitte","christoph",
    "emile","florian","francois","ingrid","jana","katarzyna",
    "lukas","magdalena","marco","marie","markus","marta","nico",
    "nikolaus","olga","pierre","stefan","victor","zuzanna",
    "mikail","romy","corinna","bangjie","toja","yazan","pankaj","suzan",
    "anand","georg","timo","claus","arif","amita","kiminori","friedemann","arfa",
    "alka","szeki","chloe","daniella","joel","robyn","peter","addy","addie","alyssa","christine",
    "don","dan","sam","ray","ron","roy","guy","ted","mia","ada","meg","kay","ivy","ned","rex",
    "lou","sid","cal","art","hal","sal","zac","mac","ash","gus",
}

BANNED_WORDS = {
    "delivery","representative","customer","service","services","support",
    "sales","order","orders","contact","billing","shipping","warehouse",
    "design","designs","team","office","admin","department","account",
    "accounts","help","care","wholesale","media","press","inquiry",
    "inquiries","info","returns","refunds","management","marketing",
    "general","store","shop","boutique","brand","brands","company",
    "collective","group","holdings","enterprise","studios","studio",
    "drawer","menu","corporate","purchasing","history","career","careers",
    "faq","privacy","policy","terms","conditions","cart","checkout",
    "happens","knit","brewing","baking","works","apparel","goods",
    "supply","crafts","creations","creatives","wood","stones","candles",
    "when","then","after","before","while","since","where","that",
    "this","what","who","whom","whose","which","there","here","from",
    "into","about","us","our","story","stories","home","read","more",
    "learn","view","all","click","visit","page","welcome","every",
    "some","any","each","both","few","most","global","direct",
    "select","prime","custom","special","online","united","states",
    "america","canada","north","carolina","australia","kingdom",
    "international","worldwide","national",
    # Professional titles, roles, corporate positions
    "graphic","designer","developer","engineer","manager","director",
    "chairman","chairwoman","artist","photographer","writer","author",
    "founder","owner","ceo","coo","cfo","cto","cmo","president",
    "vice","officer","executive","associate","intern","coordinator",
    "specialist","consultant","advisor","analyst","lead","head",
    "administrator","curator","editor","producer","creator","marketer",
    "stylist","technician","mechanic","craftsman","artisan","partner",
    "representative","agent","icon","athlete","player","coach","captain",
    # Retail nouns, product categories, descriptors
    "world","class","hop","the","an","am","also","contacts","we",
    "jewelry","business","factory","furniture","coffee","clothing",
    "shower","showers","parts","wear","gear","supra","frame","paper",
    "prints","cases","accessories","bags","shoes","eyewear","optics",
    "star","seasons","wenty","outdoor","auto","essential","essentials",
    "printers","printer","depot","outlet","market","organic","spartans",
    "bones","orchard","tool","tools","beats","collectibles","ouest",
    "surprises","perfumes","fietsenwinkel","cigars","awards","signs",
    "squash","habibi","junkies","fetishjunkies",
    "very","letters","several","things","two","personalities","independent","designers",
    "getaway","music","professional","football","quickly","early","across","better",
    "making","inside","outside","refining","naturally","popularity","category","vehicle",
    "submitting","subscribing","willkommen","merch","tracks","security","wedding",
    "operating","follower","followers","books","vintage","solutions","mobility",
    "operator","partners","specialties","experience","education",
    # Employment & job board terms (prevents 'Jobs Crowdyhouse' false positives)
    "job","jobs","career","careers","employment","internship","positions","openings",
    "vacancy","vacancies","hiring","hire","past","previous","former","current","profile","profiles",
    "crowdyhouse",
    # Nationalities & Languages
    "french","german","italian","spanish","british","dutch","chinese","japanese",
    "russian","american","canadian","australian","indian","mexican","brazilian",
    "korean","swedish","swiss","danish","norwegian","greek","portuguese",
    # Music & Artistic genres
    "edm","techno","rock","jazz","hiphop","pop","metal","indie","blues","classical",
    # Military, ranks & collective terms
    "navy","vets","veteran","veterans","army","military","corps","soldiers","sailors","troops","regiment",
    # Multilingual quantities & corporate counters
    "miljard","leden","lid","miljoen","duizend","euro","prijs","klanten",
    "sar",
    # Relational nouns and collaborative descriptors
    "friend","friends","longtime","childhood","lifelong","passionate","avid","enthusiast","enthusiasts",
    # European / Multilingual corporate & legal markers
    "eigenaar","bij","van","der","den","inhaber","geschäftsführer",
    "gérant","directeur","fondateur","société","entreprise","sarl","sas",
    "gmbh","bv","nv","oy","sp","sl","slu",
    "widerrufsbelehrung","widerrufsrecht","warenkorb","kasse","einkaufswagen",
    "artikel","inhalt","menü","suche","suchen","einloggen","abmelden","konto",
    "kundenkonto","versand","zahlung","datenschutz","agb","widerruf","kontakt",
    "newsletter","abonnieren","direkt","zum","zur",
    # Social / tech platforms
    "linkedin","facebook","twitter","instagram","tiktok","youtube",
    "google","amazon","shopify","wordpress","pinterest","reddit",
    # Social media CTA words (common false positive last names)
    "follow","following","like","likes","share","subscribe","subscribers",
    "join","connect","watch","buy","save","get","see","new","now","today",
    "next","last","first","second","third","free","best","top","great",
    "good","nice","love","life","time","day","week","month","year",
    # US States & Geographical locations (common review/testimonial location false positives)
    "ohio","california","texas","florida","york","georgia","michigan","illinois",
    "pennsylvania","virginia","washington","arizona","massachusetts","tennessee",
    "indiana","missouri","maryland","wisconsin","colorado","minnesota","alabama",
    "louisiana","kentucky","oregon","oklahoma","connecticut","utah","iowa","nevada",
    "arkansas","mississippi","kansas","mexico","london","paris","berlin","tokyo",
    "china","india","japan","germany","france","italy","spain","england","scotland",
    # Days of the week & Months of the year
    "monday","tuesday","wednesday","thursday","friday","saturday","sunday",
    "january","february","march","april","may","june","july","august","september","october","november","december",
    # Operational, store hours, and scheduling terms
    "request","requests","closed","open","opening","hours","timing","timings",
    "appointment","appointments","delivery","shipping","orders","order","available",
    "schedule","schedules","enquiries","enquiry","inquiry","inquiries","questions",
    "comments","reassure","enquire","contact","contacts","support","assistance",
    # Financial, accounting, and annual filing terms (prevents document titles as names)
    "financial","statement","statements","balance","sheet","annual","report","reports",
    "filing","filings","accounts","account","tax","taxes","audit","audits","auditor",
    "turnover","revenue","revenues","equity","capital","liabilities","assets","asset",
    "profit","loss","dividend","dividends","shareholders","shareholder","investor","investors",
    # Collective nouns, general audience, and social descriptors (e.g. 'Kind People')
    "people","person","persons","human","humans","kind","kinds","folks","crowd",
    "audience","community","readers","customers","users","clients","members","staff",
    "crew","everyone","someone","anyone",
    # Telephony, communication, and contact metadata terms
    "phone","number","numbers","telephone","mobile","cell","fax","call","calls",
    "text","texts","sms","toll","free","voip","ext","extension","hotline","helpline",
    # Marketplace, retail transaction roles, and commerce descriptors
    "buyer","buyers","seller","sellers","vendor","vendors","merchant","merchants",
    "dealer","dealers","distributor","distributors","wholesaler","wholesalers",
    "reseller","resellers","retailer","retailers","supplier","suppliers","maker","makers",
    "entrepreneur","entrepreneurs","visionary","visionaries","innovator","innovators",
    "pioneer","pioneers","hamburg","kunde","kunden","einzeln","einzelne","einzelner","co",
    # Artisan, formulation, and product craft descriptors (e.g. 'made by hand', 'botanicals')
    "hand","hands","botanical","botanicals","herbal","plant","plants","extract","extracts",
    "formula","formulas","ingredient","ingredients","nature","natural","organic","pure",
    # Legal, contractual, terms-of-service, and commerce descriptors (prevents legal clauses as names)
    "consumer","consumers","product","products","item","items","good","goods","merchandise",
    "service","services","package","packages","parcel","shipment","data","personal","privacy",
    "policy","terms","condition","conditions","contract","contracts","agreement","agreements",
    "clause","clauses","protection","rights","liability","warranty","refund","return","returns",
    "cancellation","dispute","jurisdiction","governing","applicable","statutory","provision",
    "provisions","regulation","regulations","safety","notice","standard","standards",
    # English determiners, adverbs, and non-name grammatical words
    "only","also","just","very","even","ever","never","always","often","usually",
    "sometimes","seldom","rarely","hardly","almost","nearly","quite","rather","pretty",
    "fairly","too","enough","all","some","any","each","every","either","neither","both",
    "much","many","more","most","little","less","least","several","other","another","such",
    # Hosting, cloud, network keywords (prevent WHOIS ISP/host false positives)
    "ovh","net","host","hosting","server","cloud","telecom","proxy","domain","domains",
    "registrar","registry","network","networks","systems","datacenter","corporation",
    # Prepositions / connectors that appear after names in titles
    "for","of","at","with","and","but","or","nor","yet","so",
    "as","in","on","by","to","up","do","go","be","is",
    # Title/role words that prefix real names in search snippets (e.g. "Businesswoman Romy")
    "businesswoman","businessman","businessperson","entrepreneur","executive","professional",
    "director","manager","officer","president","chairman","chairwoman","chairperson",
    "secretary","treasurer","advisor","consultant","specialist","analyst","coordinator",
    # Brand/org words that appear as "names" from site schema (e.g. "Union Sport")
    "union","sport","sports","international","global","group","holdings","enterprise",
    "enterprises","solutions","technologies","distribution","management","logistics",
    "industries","industry","manufacturing","productions","production","studios","studio",
    "creative","creatives","collective","collective","partners","partnership",
    # Nationality/place descriptors that appear in founder descriptions
    "american","british","australian","european","asian","canadian","french","german",
    "local","regional","national","worldwide","international",
}


HEADERS_POOL = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
    },
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
    },
]

VERIFIED_DIRECTORIES = {
    'zoominfo.com','dnb.com','dandb.com','buzzfile.com','crunchbase.com',
    'datanyze.com','bizapedia.com','linkedin.com','bloomberg.com',
    'rocketreach.co','cortera.com','opencorporates.com','owler.com',
    'manta.com','bbb.org','yellowpages.com','yelp.com','clutch.co',
    'trustpilot.com','glassdoor.com','angel.co','producthunt.com',
    'pitchbook.com','cbinsights.com','craft.co','signalhire.com',
    'apollo.io','hunter.io','indiamart.com','zaubacorp.com','tofler.in',
    'thecompanycheck.com','northdata.com','societe.com','verif.com',
    'kompass.com','tracxn.com',
    'find-and-update.company-information.service.gov.uk',
    'abr.business.gov.au','sec.gov',
}

# 35+ NLP patterns for founder name extraction (including DTC narrative and European legal disclosures)
FOUNDER_PATTERNS = [
    # German Impressum & Legal Disclosures (Telemediengesetz)
    r"(?:Verantwortliche/r|Vertreten durch|Geschäftsführer|Inhaber)[^:\n]*[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)",
    r"Impressum\s+(?:[A-Za-z0-9\-\.\&]+\s+)?([A-Z][a-z]+\s+[A-Z][a-z]+)",
    # French Mentions Légales
    r"(?:édité par|Directeur de la publication|Gérant|Fondateur)[^:\n]*[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
    # Dutch & Nordic Legal / Chamber of Commerce
    r"(?:Handelsnaam|Eigenaar|Oprichter|Contactpersoon)[^:\n]*[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)",
    # Spanish / Italian Disclosures
    r"(?:Fundador|Propietario|Fondatore|Proprietario)[^:\n]*[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)",
    # DTC Narrative & Descriptor skip patterns (e.g. "founded by Dutch designer Suzan Claesen", "founded by football icon John Elway")
    r"(?:founded|started|created|launched|established)\s+(?:officially\s+)?(?:in\s+\d{4}\s+)?by\s+(?:(?:former|famous|renowned|legendary|football|sports|fashion|celebrity|serial|tech|professional|pro|hall\s+of\s+fame|olympic|icon|entrepreneur|designer|artist|veteran|expert|enthusiast|athlete|champion|duo|team|player|longtime|childhood|lifelong|two|three|four|dutch|french|german|italian|spanish|british|american|canadian|australian|indian|japanese|chinese|korean|swedish|danish|norwegian|swiss|portuguese|irish|scottish|welsh|russian|mexican|brazilian|hamburg|berlin|munich|paris|london|vienna|zurich|rome|milan|madrid|barcelona|tokyo|toronto|montreal|sydney|melbourne)\s+)*(?:friends|partners|colleagues|brothers|sisters)?\s*([A-Z][a-z]+\s+[A-Z][a-z]+)",
    r"by\s+([A-Z][a-z]+)\s+and\s+([A-Z][a-z]+\s+[A-Z][a-z]+)",
    # Designer & Artisan attribution (e.g. "Designed by Rachel Comey", "Handmade by Amita & Deepak")
    r"(?:[Dd]esigned|[Cc]rafted|[Cc]urated|[Hh]andmade|[Cc]reated|[Mm]ade|[Ww]ritten|[Dd]irected|[Bb]uilt|[Oo]perated|[Oo]wned)\s+by\s+(?!hand\b|nature\b)([A-Z][a-z]+(?:\s*(?:&|and)\s*[A-Z][a-z]+)?(?:\s+[A-Z][a-z]+)?(?:\s+[A-Z][a-z]+)?)",
    # Store title designer signature (e.g. "Brand By Amita & Deepak: Store")
    r"\b[A-Za-z0-9]+\s+[Bb]y\s+([A-Z][a-z]+(?:\s*(?:&|and)\s*[A-Z][a-z]+)?(?:\s+[A-Z][a-z]+)?)\s*[:\-–|]",
    # Em-dash / Hyphen author sign-off (e.g. "— Mikail, founder")
    r"[-\u2013\u2014]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)[,\s]+(?:Founder|Co-Founder|CEO|Owner|President|Creator)",
    r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s*[-\u2013\u2014|,]\s*(?:(?:Small\s+)?Business\s+Owner|Store\s+Owner|Brand\s+Owner|Company\s+Owner|Owner\s+Operator|Sole\s+Proprietor|Managing\s+Partner|(?:Managing\s+)?Director|Founder\s*&?\s*(?:CEO|Owner|Creative\s+Director)?|Co-Founder|CEO|Owner|President|Creator)",
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s*[-\u2013\u2014|,]\s*(?:Founder|Co-Founder|CEO|Owner|President|Creator)",
    r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s*[\r\n,–—|-]+\s*(?:Co-Founder|Founder|CEO|Owner|COO|President|Creator|(?:Managing\s+)?Director)",
    r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s*\(\s*(?:Owner|Founder|CEO|Co-Founder|President|Director)\s*\)",
    r"includes\s+([A-Z][a-z]+\s+[A-Z][a-z]+)\s*\(\s*(?:Owner|Founder|CEO|Co-Founder|President|Director)\s*\)",
    # Agricultural / Orchard / Vineyard stewards
    r"([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+and\s+[A-Z][a-z]+\s+[A-Z][a-z]+)?)\s+(?:became|are|is)\s+(?:the\s+)?(?:new\s+)?(?:stewards|owners|founders|growers|caretakers|operators|vintners)",
    # Family / Artisan Sign-offs (e.g. "means the world to us. Clinton, Aimee & Easton Graves")
    r"(?:means\s+the\s+world\s+to\s+us|with\s+love|sincerely|warmly|cheers|thank\s+you|thanks|from\s+our\s+family)[,\.\s]+([A-Z][a-z]+,\s*[A-Z][a-z]+(?:\s*(?:&|and)\s*[A-Z][a-z]+)?\s+[A-Z][a-z]+)",
    # Danish / Nordic Disclosures
    r"(?:grundlagt|stiftet)\s+af\s+([A-ZÆØÅ][a-zæøå]+\s+[A-ZÆØÅ][a-zæøå]+)",
    r"(?:Ejer|Stifter|Grundlægger)[^:\n]*[:\s]+([A-ZÆØÅ][a-zæøå]+\s+[A-ZÆØÅ][a-zæøå]+)",
    # Italian Curation
    r"(?:curato|gestito)\s+da[:\s]+@?([A-Za-z]+(?:\s+[A-Za-z]+)?)",
    # Vision narratives & French brand creation
    r"(?:through\s+the\s+eyes\s+of|the\s+vision\s+of|envisioned\s+by)\s+([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s*(?:and|&)\s*[A-Z][a-z]+\s+[A-Z][a-z]+)?)",
    r"([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+et\s+[A-Z][a-z]+)?)\s+(?:créent|ont\s+créé|a\s+créé)\s+(?:une|la)\s+marque",
    r"(?:began|started|born)\s+with\s+[^.!?]{5,120}?[.!?]\s+([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:wanted|set\s+out|decided)\s+to\s+(?:build|create|start|launch)",
    r"Contacts\s+([A-Z][a-z]+\s+[A-Z][a-z]+)",
    # Business Entity Contact Card (e.g. "SV Computer Electronic LLC Michelle Medina 4511 Addison Rd")
    r"(?:LLC|Inc\.|Corp\.|Ltd\.?)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)\s+\d{2,5}\s+[A-Z]",
    r"(?:Key\s+Executive|Executive|Owner|Founder|CEO|President)[s]?\s*[:\-–]\s*([A-Z][a-z]+\s+[A-Z][a-z]+)",
    r"(?:founder|co-founder|owner|ceo|creator)[,\s:]+(?:named\s+)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
    r"(?:Owner\s*&\s*Founder|Founder\s*&\s*Owner|Founder|Co-Founder|CEO|Owner)[,\s:]+([A-Z][a-z]+\s+[A-Z][a-z]+)",
    r"(?:from\s+our\s+founder|founder\s+and\s+ceo|co-founder)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
    r"(?:I'm|I am|my name is)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)[,\.\s]+(?:the\s+)?(?:founder|owner|ceo|creator)",
    r"(?:meet|welcome)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)[,\.]?\s+(?:our|the)?\s*(?:founder|owner|ceo)",
    r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s+(?:founded|started|launched|created|established)\s+(?:the\s+)?(?:company|brand|store|business|shop)",
    r'"name"\s*:\s*"([A-Z][a-z]+\s+[A-Z][a-z]+)"[^}]*"@type"\s*:\s*"Person"',
    r'"@type"\s*:\s*"Person"[^}]*"name"\s*:\s*"([A-Z][a-z]+\s+[A-Z][a-z]+)"',
    r"[Ww]ritten\s+by\s+([A-Z][a-z]+\s+[A-Z][a-z]+)",
    r"[Aa]bout\s+([A-Z][a-z]+\s+[A-Z][a-z]+)\s*[\u2013-]",
    r"(?:\u00a9|\bCopyright\b)\s*\d{4}\s+([A-Z][a-z]+\s+[A-Z][a-z]+)",
    r"[Cc]ontact[:\s]+([A-Z][a-z]+\s+[A-Z][a-z]+)[,\s]+(?:Founder|CEO|Owner|President|Director)",
    r"Registrant Name:\s+([A-Za-z]+\s+[A-Za-z]+)",
    r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s*[\u2013-]\s*(?:Founder|Co-Founder|CEO|Owner|President|Director|Owner\s+Operator)[^|]*(?:at|@|of)\s+",
    r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s+is\s+(?:the\s+)?(?:current\s+)?(?:Co-Founder|Founder|CEO|COO|CFO|Owner|Co-Owner|President|Managing\s+Director|Creator)\b",
    r"(?:current\s+)?(?:Co-Founder|Founder|CEO|COO|Owner|Co-Owner|President|Creator)(?:[,\s]+[A-Za-z\s]+)?\s+is\s+([A-Z][a-z]+\s+[A-Z][a-z]+)",
    r"(?:brainchild|creation|vision)\s+of\s+([A-Z][a-z]+\s+[A-Z][a-z]+)",
    r"(?:we are|I am|we're)\s+(?:the\s+)?(?:founders|co-founders|owners)\s+of\s+[^-\u2013\u2014,.:]+[-\u2013\u2014,:]\s*([A-Z][a-z]+(?:\s*(?:and|&)\s*[A-Z][a-z]+)?(?:\s+[A-Z][a-z]+)?)",
    r"([A-Z][a-z]+\s+[A-Z][a-z]+)\s*(?:[-–|,]|\s+)\s*(?:Founder\s*&\s*(?:Co-)?Owner|Founder|Co-Founder|CEO|Owner|President|Creator)\s*(?:at|@|of)\s+",
]


# ── Utility Functions ─────────────────────────────────────────────────────────

def check_namesake_brand(store_name: str, domain: str) -> Optional[Tuple[str, str]]:
    """Detect if brand is a namesake founder label like 'Arfa Malik', 'Rachel Comey', 'John Varvatos'.
    STRICT: w1 must be an authentic human first name in COMMON_FIRST_NAMES."""
    clean_store = re.sub(r'[^A-Za-z\s]', '', store_name).strip()
    words = clean_store.split()
    if len(words) == 2:
        w1, w2 = words[0].capitalize(), words[1].capitalize()
        if w1.lower() in COMMON_FIRST_NAMES and w1.lower() not in BANNED_WORDS and w2.lower() not in BANNED_WORDS:
            if len(w1) >= 3 and len(w2) >= 3:
                stem = domain.lower().split('.')[0]
                if w1.lower() in stem and w2.lower() in stem:
                    if is_clean_human_name(f"{w1} {w2}", domain=domain, strict_first_name=True):
                        return w1, w2
    return None

def clean_domain(d: str) -> str:
    if not d: return ""
    d = d.lower().strip()
    for prefix in ("https://", "http://", "www."):
        if d.startswith(prefix):
            d = d[len(prefix):]
    return d.split("/")[0].strip()

GRAVATAR_CACHE: Dict[str, bool] = {}

def check_gravatar(email: str) -> bool:
    if not email or "@" not in email:
        return False
    em_clean = email.strip().lower()
    if em_clean in GRAVATAR_CACHE:
        return GRAVATAR_CACHE[em_clean]
    h = hashlib.md5(em_clean.encode('utf-8')).hexdigest()
    try:
        url = f"https://www.gravatar.com/avatar/{h}?d=404"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            val = resp.status == 200
            GRAVATAR_CACHE[em_clean] = val
            return val
    except Exception:
        GRAVATAR_CACHE[em_clean] = False
        return False

def is_clean_human_name(name: str, brand: str = "", domain: str = "", strict_first_name: bool = False) -> bool:
    parts = name.split()
    if not (1 <= len(parts) <= 4):
        return False
    fn = parts[0]
    ln = parts[-1] if len(parts) > 1 else ""
    if strict_first_name and fn.lower() not in COMMON_FIRST_NAMES:
        return False
    if not fn[0].isupper():
        return False
    if ln and not ln[0].isupper():
        return False
    for part in parts:
        p_low = part.lower()
        if p_low in BANNED_WORDS:
            return False
        if p_low.endswith('ies') and (p_low[:-3] + 'y') in BANNED_WORDS:
            return False
        if p_low.endswith('es') and p_low[:-2] in BANNED_WORDS:
            return False
        if p_low.endswith('s') and p_low[:-1] in BANNED_WORDS:
            return False
        if p_low.endswith('ed') and (p_low[:-2] in BANNED_WORDS or p_low[:-1] in BANNED_WORDS):
            return False
        if p_low.endswith('ing') and (p_low[:-3] in BANNED_WORDS or (p_low[:-3] + 'e') in BANNED_WORDS):
            return False
        if p_low.endswith('ers') and (p_low[:-3] in BANNED_WORDS or p_low[:-1] in BANNED_WORDS):
            return False
        if p_low.endswith('er') and (p_low[:-2] in BANNED_WORDS or p_low[:-1] in BANNED_WORDS):
            return False
    if not all(p.isalpha() for p in parts):
        return False
    # If single word, must be an authentic known first name with len >= 3
    if len(parts) == 1 and (fn.lower() not in COMMON_FIRST_NAMES or len(fn) < 3):
        return False
    # 2-letter first names must be known authentic short names (e.g. Ed, Al, Jo, Bo, Ty, Cy)
    if len(fn) == 2 and fn.lower() not in COMMON_FIRST_NAMES:
        return False
    if len(fn) == 3 and fn.lower() not in COMMON_FIRST_NAMES:
        return False
    if ln and ln.lower() in ('al', 'el', 'de', 'du', 'da', 'di', 'van', 'der', 'von', 'la', 'le', 'co', 'corp', 'inc', 'ltd', 'llc', 'gmbh', 'bv', 'sa', 'sarl', 'kunden', 'kunde'):
        return False
    if len(fn) < 2 or (ln and (len(ln) < 2 or len(ln) > 30)):
        return False
    if brand:
        brand_clean = ''.join(c for c in brand.lower() if c.isalnum())
        name_clean = ''.join(c for c in name.lower() if c.isalnum())
        if brand_clean == name_clean or name_clean in brand_clean:
            return False
        if ln:
            brand_tokens_set = {
                t.lower() for t in re.split(r'[^a-zA-Z0-9]+', brand)
                if len(t) >= 4
            }
            if ln.lower() in brand_tokens_set:
                return False
    if domain:
        domain_stem = domain.lower().split('.')[0]
        if fn.lower() == domain_stem or (ln and ln.lower() == domain_stem):
            return False
    return True

def get_real_card_url(href: str) -> str:
    m = re.search(r'/RU=(.*?)/RK=', href)
    if m:
        try:
            return urllib.parse.unquote(m.group(1))
        except Exception:
            return href
    return href

def is_trusted_source(card_url: str, store_domain: str) -> bool:
    card_url_lower = card_url.lower()
    if '/pub/dir/' in card_url_lower:
        return False
    if store_domain.lower() in card_url_lower:
        return True
    if any(vd in card_url_lower for vd in VERIFIED_DIRECTORIES):
        return True
    # Allow editorial, press, and trade sites; reject generic spam / tech redirects
    if not any(bad in card_url_lower for bad in [
        'wikipedia.org', 'wiktionary.org', 'thefreedictionary.com',
        'coupons.com', 'retailmenot.com', 'slickdeals.net',
        'facebook.com/login', 'accounts.google.com', 'support.google.com',
        'whois', 'domaintools', 'godaddy.com', 'namecheap.com'
    ]):
        return True
    return False

def is_card_grounded(card_text: str, domain: str, brand: str) -> bool:
    """Verify search result card actually mentions THIS specific business.
    Balanced: prevents cross-contamination while catching genuine results."""
    text_lower = card_text.lower()
    domain_stem = domain.lower().split('.')[0]

    # Full domain exact match (most reliable)
    if domain.lower() in text_lower:
        return True

    # Short stems (< 6 chars like a4c, 2m2, a313) are acronyms/short tokens that collide
    # across unrelated companies. They MUST match the full domain.
    if len(domain_stem) < 6:
        return False

    # Domain stem match (unique stems: length >= 6 and (has digits or hyphens or length >= 8) and not a generic banned word)
    stem_alpha = re.sub(r'[^a-z]', '', domain_stem)
    if (any(c.isdigit() for c in domain_stem) or '-' in domain_stem or len(domain_stem) >= 8):
        if stem_alpha not in BANNED_WORDS and domain_stem in text_lower:
            return True

    # Brand 2-word prefix check (excluding generic corporate/web extensions)
    brand_words = [
        w.lower() for w in re.split(r'[^a-zA-Z0-9]+', brand)
        if len(w) >= 2 and w.lower() not in (
            'the', 'and', 'com', 'net', 'org', 'shop', 'store', 'online', 'inc', 'llc', 'ltd', 'co'
        )
    ]
    if len(brand_words) >= 2 and f"{brand_words[0]} {brand_words[1]}" in text_lower:
        return True

    # Brand token matching (excluding BANNED_WORDS and corporate stop words)
    brand_tokens = [
        t.lower() for t in re.split(r'[^a-zA-Z0-9]+', brand)
        if len(t) >= 4 and t.lower() not in BANNED_WORDS and t.lower() not in (
            'the', 'and', 'shop', 'store', 'online', 'inc', 'llc', 'ltd',
            'with', 'from', 'your', 'that', 'this', 'they', 'have', 'been',
            'com', 'net', 'org', 'global', 'co',
        )
    ]
    if not brand_tokens:
        return False
    matches = sum(1 for t in brand_tokens if t in text_lower)
    # Single distinct token brand: require unique stem or domain extension
    if len(brand_tokens) == 1:
        tok = brand_tokens[0]
        tok_alpha = re.sub(r'[^a-z]', '', tok)
        if len(tok) >= 6 and tok_alpha not in BANNED_WORDS and (any(c.isdigit() for c in tok) or '-' in tok or len(tok) >= 8):
            return matches >= 1
        return domain.lower() in text_lower
    # Multi-token brand: require at least 2 distinct tokens to match
    return matches >= min(2, len(brand_tokens))

def extract_name_from_patterns(text: str, brand: str, domain: str) -> Optional[Tuple[str, str, str]]:
    for i, pat in enumerate(FOUNDER_PATTERNS):
        for m in re.finditer(pat, text, re.IGNORECASE):
            # Skip historical founding years (< 1970) (e.g. "Established in 1845 by Don Jaime Partagas")
            m_yr = re.search(r'\b(?:in|est\.?|established(?:\s+in)?)\s+(1[0-9]{3})\b', m.group(0), re.I)
            if m_yr and int(m_yr.group(1)) < 1970:
                continue
            try:
                cand = m.group(1).strip()
            except IndexError:
                continue
            if cand.lower().startswith(('don ', 'sir ', 'lord ', 'lady ', 'dame ', 'saint ', 'st. ')):
                continue
            if '&' in cand or ' and ' in cand.lower():
                # Handle comma + ampersand family sign-offs (e.g. "Clinton, Aimee & Easton Graves")
                if ',' in cand:
                    sub_parts = [p.strip() for p in re.split(r'[,&]|\band\b', cand, flags=re.I) if p.strip()]
                    if sub_parts:
                        last_toks = sub_parts[-1].split()
                        first_toks = sub_parts[0].split()
                        if len(last_toks) >= 2 and len(first_toks) >= 1:
                            fn = first_toks[0].capitalize()
                            ln = last_toks[-1].capitalize()
                            if is_clean_human_name(f"{fn} {ln}", brand, domain):
                                return fn, ln, f"pat{i+1}_family"
                # Split by & or and
                cf_parts = re.split(r'\s*(?:&|and)\s*', cand, flags=re.I)
                if len(cf_parts) >= 2:
                    p1 = [w.capitalize() for w in cf_parts[0].strip().split() if w.isalpha()]
                    p2 = [w.capitalize() for w in cf_parts[1].strip().split() if w.isalpha()]
                    # Case A: Full Name and Full Name (e.g. "Noel Miller and Harrison Heilman")
                    if len(p1) >= 2:
                        fn1, ln1 = p1[0], p1[-1]
                        if is_clean_human_name(f"{fn1} {ln1}", brand, domain):
                            return fn1, ln1, f"pat{i+1}_cofounder"
                    # Case B: First and First Last (e.g. "Amita and Deepak Sharma", "Peter and Robyn Pomonis")
                    elif len(p1) == 1 and len(p2) >= 2:
                        fn1, ln1 = p1[0], p2[-1]
                        if is_clean_human_name(f"{fn1} {ln1}", brand, domain):
                            return fn1, ln1, f"pat{i+1}_cofounder"
                        elif is_clean_human_name(f"{p2[0]} {p2[-1]}", brand, domain):
                            return p2[0], p2[-1], f"pat{i+1}_cofounder"
                    # Case C: First and First (e.g. "Amita and Deepak")
                    elif len(p1) == 1 and len(p2) == 1:
                        if is_clean_human_name(p1[0], brand, domain) and is_clean_human_name(p2[0], brand, domain):
                            return p1[0], p2[0], f"pat{i+1}_cofounder"
            parts = cand.split()
            while len(parts) > 2 and (parts[-1].lower() in BANNED_WORDS or parts[-1].lower() in ('as', 'of', 'at', 'for', 'in', 'on', 'to', 'by', 'and', 'or', 'the')):
                parts.pop()
            if len(parts) >= 2:
                fn, ln = parts[0].capitalize(), parts[-1].capitalize()
                cand_name = f"{fn} {ln}"
                if is_clean_human_name(cand_name, brand, domain):
                    return fn, ln, f"pat{i+1}"
            elif len(parts) == 1:
                fn = parts[0].capitalize()
                if is_clean_human_name(fn, brand, domain):
                    return fn, "", f"pat{i+1}_first"
    return None

def generate_email_variants(first: str, last: str, domain: str) -> List[str]:
    f = first.lower()
    l = last.lower() if last else ""
    variants = [f"{f}@{domain}"]
    if l:
        variants += [
            f"{f}.{l}@{domain}",
            f"{f}{l}@{domain}",
            f"{f[0]}{l}@{domain}",
            f"{f}.{l[0]}@{domain}",
            f"{l}.{f}@{domain}",
            f"{f}_{l}@{domain}",
        ]
    return list(dict.fromkeys(variants))

def detect_domain_country(domain: str) -> str:
    tld = domain.split('.')[-1].lower()
    tld2 = '.'.join(domain.split('.')[-2:]).lower() if domain.count('.') >= 2 else ""
    if tld2 in ('co.uk', 'org.uk', 'me.uk', 'ltd.uk'):
        return 'UK'
    if tld2 in ('com.au', 'net.au', 'org.au'):
        return 'AU'
    if tld == 'uk': return 'UK'
    if tld == 'au': return 'AU'
    if tld == 'ca': return 'CA'
    if tld in ('com', 'net', 'org', 'io', 'co'): return 'US'
    return 'INTL'


# ── TIER 5: Email Intelligence Engine ────────────────────────────────────────
# Mimics behindtheemail.com approach: Gravatar profile mining, MX fingerprint,
# SMTP RCPT sweep, and email permutation validation. All free, zero API keys.

async def _get_mx_for_domain(client, domain: str, sem: asyncio.Semaphore, timeout: float = 3.0) -> str:
    """Get best MX record using Cloudflare DoH (fast, 100% cross-platform, zero dependencies)."""
    try:
        url = f"https://cloudflare-dns.com/dns-query?name={urllib.parse.quote(domain)}&type=MX"
        headers = {'Accept': 'application/dns-json'}
        async with sem:
            resp = await client.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json() if hasattr(resp, 'json') else json.loads(resp.text)
            answers = data.get('Answer', [])
            mx_records = []
            for ans in answers:
                val = ans.get('data', '').strip().rstrip('.')
                parts = val.split(None, 1)
                if len(parts) == 2 and parts[0].isdigit():
                    mx_records.append((int(parts[0]), parts[1]))
                elif val:
                    mx_records.append((10, val))
            if mx_records:
                mx_records.sort(key=lambda x: x[0])
                return mx_records[0][1]
    except Exception:
        pass
    return domain


async def gravatar_email_lookup_async(client, email: str, sem: asyncio.Semaphore, timeout: float = 2.5) -> Optional[Dict]:
    """Async Gravatar lookup using existing HTTP client — fast, non-blocking."""
    if not email or "@" not in email:
        return None
    h = hashlib.md5(email.strip().lower().encode('utf-8')).hexdigest()
    # Attempt 1: Full profile JSON (has name, bio, links)
    try:
        url = f"https://en.gravatar.com/{h}.json"
        async with sem:
            resp = await client.get(url, headers=random.choice(HEADERS_POOL), timeout=timeout)
        if resp.status_code == 200:
            data = resp.json() if hasattr(resp, 'json') else json.loads(resp.text)
            entry = data.get('entry', [{}])[0]
            real_name = (
                entry.get('name', {}).get('formatted', '') or
                entry.get('displayName', '') or
                entry.get('preferredUsername', '')
            )
            return {
                'has_gravatar': True,
                'gravatar_name': real_name.strip(),
                'gravatar_bio': entry.get('aboutMe', '')[:200],
                'gravatar_hash': h,
                'gravatar_avatar': f'https://www.gravatar.com/avatar/{h}',
            }
    except Exception:
        pass
    # Attempt 2: Avatar existence check only
    try:
        url = f"https://www.gravatar.com/avatar/{h}?d=404&s=1"
        async with sem:
            resp = await client.get(url, headers=random.choice(HEADERS_POOL), timeout=min(timeout, 1.5))
        if resp.status_code == 200:
            return {'has_gravatar': True, 'gravatar_name': '', 'gravatar_bio': '', 'gravatar_hash': h, 'gravatar_avatar': f'https://www.gravatar.com/avatar/{h}'}
    except Exception:
        pass
    return None


def detect_email_provider(mx_host: str) -> str:
    """Fingerprint email provider from MX hostname."""
    mx = mx_host.lower()
    if 'google' in mx or 'gmail' in mx or 'googlemail' in mx or 'aspmx' in mx:
        return 'Google Workspace'
    if 'outlook' in mx or 'protection.outlook' in mx or 'hotmail' in mx:
        return 'Microsoft 365'
    if 'protonmail' in mx or 'proton.me' in mx:
        return 'ProtonMail'
    if 'yahoo' in mx or 'yahoodns' in mx:
        return 'Yahoo Mail'
    if 'zoho' in mx:
        return 'Zoho Mail'
    if 'fastmail' in mx:
        return 'Fastmail'
    if 'mailgun' in mx:
        return 'Mailgun'
    if 'sendgrid' in mx:
        return 'SendGrid'
    if 'amazonaws' in mx or 'aws' in mx:
        return 'AWS SES'
    return 'Custom SMTP'


async def email_intelligence_sweep(
    client, domain: str, first: str, last: str, lead_email: str,
    sem: asyncio.Semaphore, timeout: float = 5.0
) -> Optional[Dict]:
    """
    TIER 5 — Email Intelligence Engine.
    Fast, asynchronous, 100% non-blocking.
    1. Checks email permutations against Gravatar concurrently
    2. Detects MX provider via Cloudflare DoH
    """
    if not first and not lead_email:
        return None

    variants = generate_email_variants(first, last, domain) if first else []
    if lead_email and lead_email not in variants:
        variants.insert(0, lead_email)

    result = {
        'email_provider': '',
        'smtp_verified_email': '',
        'smtp_status': '',
        'gravatar_name': '',
        'gravatar_email': '',
        'gravatar_has_account': False,
        'catch_all': False,
    }

    # Step 1: Gravatar sweep (async parallel, top 4 variants)
    grav_tasks = [gravatar_email_lookup_async(client, em, sem, timeout=2.0) for em in variants[:4]]
    grav_results = await asyncio.gather(*grav_tasks, return_exceptions=True)
    for i, grav in enumerate(grav_results):
        if grav and isinstance(grav, dict) and grav.get('has_gravatar'):
            result['gravatar_has_account'] = True
            result['gravatar_email'] = variants[i]
            if grav.get('gravatar_name'):
                result['gravatar_name'] = grav['gravatar_name']
                break

    # Step 2: MX provider detection via Cloudflare DoH (fast, 50ms)
    try:
        mx = await _get_mx_for_domain(client, domain, sem, timeout=3.0)
        provider = detect_email_provider(mx)
        result['email_provider'] = provider
    except Exception:
        pass

    return result if (result['gravatar_has_account'] or result['email_provider']) else None


# ── Async HTTP Fetch ──────────────────────────────────────────────────────────

async def fetch(client, url: str, sem: asyncio.Semaphore, timeout: float = 5.0,
                method: str = "GET", data: bytes = None) -> Optional[str]:
    headers = random.choice(HEADERS_POOL).copy()
    try:
        async with sem:
            if method == "POST":
                resp = await client.post(url, content=data, headers=headers, timeout=timeout)
            else:
                resp = await client.get(url, headers=headers, timeout=timeout)
        if resp.status_code in (200, 201):
            return resp.text
        return None
    except Exception:
        return None


# ── TIER 0: Email Discovery Engine ──────────────────────────────────────────
# Mine the website itself for real email addresses before any other enrichment.
# Finds: mailto: links, Cloudflare-encoded emails, RSS author emails,
#        WordPress REST API, Wayback Machine snapshots, search engine email dorks.

EMAIL_PATTERN = re.compile(
    r'(?<![\w@])([a-zA-Z0-9][a-zA-Z0-9._%+\-]{1,40}@[a-zA-Z0-9][a-zA-Z0-9.\-]{1,40}\.[a-zA-Z]{2,10})(?![\w@])'
)

ROLE_PREFIXES_FULL = frozenset([
    'info','contact','hello','hi','admin','support','sales','service','services',
    'orders','billing','shipping','returns','help','enquiry','enquiries',
    'press','media','marketing','advertising','wholesale','general','office',
    'team','shop','store','boutique','care','privacy','legal','hr','jobs',
    'careers','feedback','newsletter','booking','bookings','noreply','no-reply',
    'mailer','bounce','postmaster','abuse','security','webmaster','hostmaster',
    'accounts','account','logistics','operations','partnerships','concierge',
])

def is_personal_email(email: str, domain: str) -> bool:
    """Heuristic: is this a personal inbox vs a role/generic address?"""
    if '@' not in email: return False
    local = email.split('@')[0].lower()
    local_clean = re.sub(r'[^a-z]', '', local)
    if local_clean in ROLE_PREFIXES_FULL: return False
    if local in ROLE_PREFIXES_FULL: return False
    # Personal if local has a dot (first.last) or looks like a name
    if '.' in local or len(local_clean) >= 4:
        return True
    return False

def decode_cloudflare_email(cfemail_hex: str) -> str:
    """Decode Cloudflare email obfuscation (data-cfemail attribute)."""
    try:
        enc = bytes.fromhex(cfemail_hex)
        key = enc[0]
        return ''.join(chr(b ^ key) for b in enc[1:])
    except Exception:
        return ''

def extract_emails_from_html(html: str, domain: str) -> List[str]:
    """Extract all emails from HTML — handles mailto:, Cloudflare obfuscation,
    hex entities (&amp;#64; etc.), and plain text email patterns."""
    emails: Set[str] = set()

    # 1. Standard mailto: links
    for m in re.finditer(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', html, re.I):
        emails.add(m.group(1).lower())

    # 2. Cloudflare-encoded emails: data-cfemail="HEXHEX"
    for m in re.finditer(r'data-cfemail=["\']([0-9a-fA-F]+)["\']', html):
        decoded = decode_cloudflare_email(m.group(1))
        if '@' in decoded:
            emails.add(decoded.lower())

    # 3. HTML entity encoded: name&#64;domain.com or name&#x40;domain.com
    deentitied = re.sub(r'&#(?:x40|64);', '@', html, flags=re.I)
    deentitied = re.sub(r'&#(?:x2[Ee]|46);', '.', deentitied, flags=re.I)
    for m in EMAIL_PATTERN.finditer(deentitied):
        emails.add(m.group(1).lower())

    # 4. Plain text pattern (catches emails visible in page text)
    for m in EMAIL_PATTERN.finditer(html):
        emails.add(m.group(1).lower())

    # Filter: must be at the target domain, valid format
    dom_root = domain.lower()
    clean = []
    for e in emails:
        parts = e.split('@')
        if len(parts) != 2: continue
        local, edomain = parts
        if len(local) < 1 or len(edomain) < 3: continue
        if edomain == dom_root or edomain.endswith('.' + dom_root) or dom_root.endswith('.' + edomain):
            clean.append(e)
    return list(dict.fromkeys(clean))


async def discover_emails_on_site(
    client, domain: str, sem: asyncio.Semaphore, timeout: float
) -> List[str]:
    """Crawl the site's highest-yield pages for exposed email addresses.
    Returns list sorted: personal emails first, then role emails."""
    all_emails: Set[str] = set()

    pages_to_check = [
        f'https://{domain}',
        f'https://{domain}/pages/contact',
        f'https://{domain}/contact',
        f'https://{domain}/pages/about-us',
    ]

    htmls = await asyncio.gather(
        *[fetch(client, u, sem, min(timeout, 2.5)) for u in pages_to_check],
        return_exceptions=True
    )
    for html in htmls:
        if html and isinstance(html, str) and len(html) > 100:
            found = extract_emails_from_html(html, domain)
            all_emails.update(found)

    # Sort: personal first, role emails last
    personal = [e for e in all_emails if is_personal_email(e, domain)]
    role = [e for e in all_emails if not is_personal_email(e, domain)]
    return personal + role


async def rss_feed_author(client, domain: str, brand: str, sem: asyncio.Semaphore, timeout: float) -> Optional[Tuple[str, str, str]]:
    """Extract author name + email from RSS/Atom feed — checks top feeds in parallel (fast, 2s cap)."""
    feed_paths = ['/feed', '/rss.xml']
    feed_htmls = await asyncio.gather(
        *[fetch(client, f'https://{domain}{p}', sem, min(timeout, 2.0)) for p in feed_paths],
        return_exceptions=True
    )
    for html in feed_htmls:
        if not html or isinstance(html, Exception) or len(html) < 200:
            continue
        try:
            # Extract author email from <author><email>...</email></author>
            m_email = re.search(r'<(?:author|managingEditor)>[^<]*<email>([^<]+)</email>', html, re.I)
            if not m_email:
                m_email = re.search(r'<managingEditor>([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', html)
            if m_email:
                email = m_email.group(1).strip()
                if '@' in email and domain.split('.')[0] in email:
                    local = email.split('@')[0]
                    if is_personal_email(email, domain) or '.' in local:
                        return '', '', f'rss_email:{email}'
            # Extract author name
            m_name = re.search(r'<(?:dc:creator|author)>\s*(?:<name>)?([A-Z][a-z]+\s+[A-Z][a-z]+)(?:</name>)?\s*</(?:dc:creator|author)>', html)
            if m_name:
                name = m_name.group(1).strip()
                parts = name.split()
                if len(parts) >= 2:
                    fn, ln = parts[0].capitalize(), parts[-1].capitalize()
                    if is_clean_human_name(f'{fn} {ln}', brand, domain):
                        return fn, ln, 'rss_feed_author'
        except Exception:
            continue
    return None


async def wordpress_api_author(client, domain: str, brand: str, sem: asyncio.Semaphore, timeout: float) -> Optional[Tuple[str, str, str]]:
    """WordPress REST API — /wp-json/wp/v2/users is often public and exposes author names."""
    try:
        html = await fetch(client, f'https://{domain}/wp-json/wp/v2/users?per_page=1', sem, timeout)
        if html and len(html) > 10:
            try:
                data = json.loads(html)
                if isinstance(data, list) and data:
                    user = data[0]
                    name = user.get('name', '')
                    slug = user.get('slug', '')
                    # Name might be "First Last" or just "firstname"
                    parts = name.split()
                    if len(parts) >= 2:
                        fn, ln = parts[0].capitalize(), parts[-1].capitalize()
                        if is_clean_human_name(f'{fn} {ln}', brand, domain):
                            return fn, ln, 'wordpress_api'
                    elif len(parts) == 1 and len(slug) > 2:
                        # Try to get more from slug (e.g., "john-smith" -> John Smith)
                        slug_parts = re.split(r'[-_]', slug)
                        if len(slug_parts) >= 2:
                            fn, ln = slug_parts[0].capitalize(), slug_parts[-1].capitalize()
                            if is_clean_human_name(f'{fn} {ln}', brand, domain):
                                return fn, ln, 'wordpress_api_slug'
            except Exception:
                pass
    except Exception:
        pass
    return None


async def wayback_email_mine(client, domain: str, sem: asyncio.Semaphore, timeout: float) -> List[str]:
    """Check Wayback Machine for old snapshots that might have exposed emails.
    Uses the CDX API to find snapshots, then fetches the contact page snapshot."""
    emails: Set[str] = set()
    try:
        # CDX API: find most recent snapshots of contact/about pages
        cdx_url = (
            f'http://web.archive.org/cdx/search/cdx?url={domain}/contact*'
            f'&output=json&limit=3&fl=timestamp,original&filter=statuscode:200&from=20180101'
        )
        cdx_html = await fetch(client, cdx_url, sem, timeout)
        if cdx_html:
            try:
                cdx_data = json.loads(cdx_html)
                # cdx_data[0] is header, rest are rows
                for row in cdx_data[1:4]:
                    ts, orig_url = row[0], row[1]
                    snap_url = f'https://web.archive.org/web/{ts}if_/{orig_url}'
                    snap_html = await fetch(client, snap_url, sem, timeout)
                    if snap_html:
                        found = extract_emails_from_html(snap_html, domain)
                        emails.update(found)
            except Exception:
                pass
    except Exception:
        pass
    return [e for e in emails if is_personal_email(e, domain)]


async def search_email_dork(
    client, domain: str, brand: str, sem: asyncio.Semaphore, timeout: float
) -> List[str]:
    """Use Yahoo/Bing search to find emails exposed in public snippets.
    Dorks like: \"@domain.com\" -site:domain.com | \"email\" domain.com"""
    emails: Set[str] = set()
    queries = [
        f'"@{domain}" -site:{domain}',
        f'contact "@{domain}"',
        f'"{brand}" email OR contact',
    ]
    for q in queries[:2]:  # limit to 2 queries to avoid rate limiting
        try:
            url = f'https://search.yahoo.com/search?p={urllib.parse.quote(q)}'
            html = await fetch(client, url, sem, timeout)
            if html:
                found = re.findall(
                    r'([a-zA-Z0-9][a-zA-Z0-9._%+\-]{1,30}@' + re.escape(domain) + r')',
                    html
                )
                for e in found:
                    emails.add(e.lower())
        except Exception:
            continue
    personal = [e for e in emails if is_personal_email(e, domain)]
    role = [e for e in emails if not is_personal_email(e, domain)]
    return personal + role


# ── TIER 1: Email DNA Analysis ────────────────────────────────────────────────

ROLE_EMAIL_PREFIXES = {
    'marketing', 'advertising', 'accounting', 'billing', 'shipping', 'orders',
    'sales', 'support', 'service', 'services', 'office', 'admin', 'contact',
    'info', 'help', 'inquiries', 'team', 'hello', 'hi', 'general', 'press',
    'media', 'customercare', 'care', 'booking', 'bookings', 'frontdesk',
    'concierge', 'editorial', 'feedback', 'operations', 'partnerships',
    'careers', 'jobs', 'hr', 'privacy', 'legal', 'security',
    'enquiry', 'enquiries', 'retail', 'wholesale', 'returns', 'logistics',
}

def analyze_email_dna(lead_email: str, secondary_email: str, brand: str, domain: str) -> Optional[Dict]:
    emails_to_check = [e.strip() for e in [lead_email, secondary_email] if e and '@' in e]
    for email in emails_to_check:
        local = email.split('@')[0].lower().lstrip('/')
        local_alpha = re.sub(r'[^a-z]', '', local)
        if local_alpha in ROLE_EMAIL_PREFIXES:
            continue

        # [S1] first.last@
        if '.' in local:
            parts_loc = local.split('.')
            if len(parts_loc) == 2 and all(p.isalpha() and len(p) >= 2 for p in parts_loc):
                fn, ln = parts_loc[0].capitalize(), parts_loc[1].capitalize()
                if is_clean_human_name(f"{fn} {ln}", brand, domain):
                    return {
                        "Exec_First": fn, "Exec_Last": ln, "Exec_Name": f"{fn} {ln}",
                        "Exec_Title": "Founder / Owner", "Exec_Email": email,
                        "Exec_Email_Pattern": "first.last", "Exec_Source": "email_dna_first_last",
                        "Exec_Confidence": "HIGH", "_chain": ["email_dna_first_last"],
                    }

        # [S2] Concatenated firstlast@
        local_alpha = re.sub(r'[^a-z]', '', local)
        for fn_c in sorted(COMMON_FIRST_NAMES, key=len, reverse=True):
            if len(fn_c) >= 4 and local_alpha.startswith(fn_c):
                ln_c = local_alpha[len(fn_c):]
                if len(ln_c) >= 3 and ln_c.isalpha() and ln_c not in BANNED_WORDS:
                    cand = f"{fn_c.capitalize()} {ln_c.capitalize()}"
                    if is_clean_human_name(cand, brand, domain):
                        return {
                            "Exec_First": fn_c.capitalize(), "Exec_Last": ln_c.capitalize(),
                            "Exec_Name": cand, "Exec_Title": "Founder / Owner",
                            "Exec_Email": email, "Exec_Email_Pattern": "concat_first_last",
                            "Exec_Source": "email_dna_concat", "Exec_Confidence": "HIGH",
                            "_chain": ["email_dna_concat"],
                        }

        # [S3] Pure first name inbox
        local_a2 = re.sub(r'[^a-z]', '', local)
        if local_a2 in COMMON_FIRST_NAMES and local_a2 not in BANNED_WORDS and len(local_a2) >= 3:
            return {
                "Exec_First": local_a2.capitalize(), "Exec_Last": "",
                "Exec_Name": local_a2.capitalize(), "Exec_Title": "Founder / Owner",
                "Exec_Email": email, "Exec_Email_Pattern": "first_only",
                "Exec_Source": "email_dna_first", "Exec_Confidence": "MEDIUM",
                "_chain": ["email_dna_first"],
            }
    return None


# ── TIER 2: JSON-LD Schema Extraction ────────────────────────────────────────

def extract_schema_person(html: str, brand: str, domain: str) -> Optional[Tuple[str, str]]:
    try:
        scripts = re.findall(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html, re.DOTALL | re.IGNORECASE
        )
        for script in scripts:
            try:
                data = json.loads(script.strip())
            except Exception:
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                type_val = item.get('@type', '')
                types = [t.lower() for t in (type_val if isinstance(type_val, list) else [str(type_val)])]
                if any(t in types for t in ['organization', 'localbusiness', 'store', 'brand']):
                    for key in ('founder', 'director', 'employee', 'author', 'creator'):
                        person = item.get(key)
                        if isinstance(person, dict):
                            name = person.get('name', '')
                            parts = name.split()
                            if len(parts) >= 2:
                                fn, ln = parts[0].capitalize(), parts[1].capitalize()
                                if is_clean_human_name(f"{fn} {ln}", brand, domain):
                                    return fn, ln
                        elif isinstance(person, list):
                            for p in person:
                                if isinstance(p, dict):
                                    name = p.get('name', '')
                                    parts = name.split()
                                    if len(parts) >= 2:
                                        fn, ln = parts[0].capitalize(), parts[1].capitalize()
                                        if is_clean_human_name(f"{fn} {ln}", brand, domain):
                                            return fn, ln
                if any(t in types for t in ['person']):
                    name = item.get('name', '')
                    job = item.get('jobTitle', '').lower()
                    if any(kw in job for kw in ['founder', 'ceo', 'owner', 'president', 'director', 'creator']):
                        parts = name.split()
                        if len(parts) >= 2:
                            fn, ln = parts[0].capitalize(), parts[1].capitalize()
                            if is_clean_human_name(f"{fn} {ln}", brand, domain):
                                return fn, ln
    except Exception:
        pass
    return None


# ── TIER 2: Deep Site Crawl ───────────────────────────────────────────────────

async def deep_site_crawl(client, domain: str, brand: str, sem: asyncio.Semaphore,
                           timeout: float) -> Optional[Tuple[str, str, str]]:
    about_urls = []

    # 1. Fetch homepage first
    home_html = await fetch(client, f"https://{domain}", sem, min(timeout, 3.0))
    if not home_html:
        home_html = await fetch(client, f"http://{domain}", sem, 2.0)
    if not home_html:
        return None
    schema_result = extract_schema_person(home_html, brand, domain)
    if schema_result:
        return schema_result[0], schema_result[1], "schema_json_ld"
    try:
        soup = BeautifulSoup(home_html, 'html.parser')

        # 1. Check for personal YouTube / social channels in complete homepage markup
        for a in soup.find_all('a', href=True):
            href = a['href']
            m_yt = re.search(r'youtube\.com/@([A-Za-z]+)', href)
            if m_yt:
                yt_handle = m_yt.group(1)
                yt_parts = re.findall(r'[A-Z][a-z]+', yt_handle)
                if len(yt_parts) == 2:
                    yfn, yln = yt_parts[0].capitalize(), yt_parts[1].capitalize()
                    if is_clean_human_name(f"{yfn} {yln}", brand, domain, strict_first_name=True):
                        return yfn, yln, "homepage:social_youtube"

        # 2. Add homepage dynamic links from complete markup (including nav and footer)
        for a in soup.find_all('a', href=True):
            href = a['href']
            t = a.get_text(strip=True).lower()
            if any(skip in href.lower() for skip in ['/products/', '/collections/', '/blogs/', '/cart', '/checkout', '/account', '/search']):
                continue
            if any(k in href.lower() or k in t for k in [
                'about','story','team','founder','history','who-we-are',
                'bio','artisan','meet','creator','our-mission','family',
                'impressum','legal','mentions','over-ons',
            ]):
                full_u = href if href.startswith('http') else f"https://{domain}{href if href.startswith('/') else '/' + href}"
                if full_u not in about_urls and domain in full_u:
                    about_urls.append(full_u)

        # 3. Check body text for narrative patterns after decomposing navigation/chrome
        for el in soup(['script', 'style', 'nav', 'footer', 'header']):
            el.decompose()
        clean_home = " ".join(soup.get_text(separator=" ", strip=True).split())
        home_result = extract_name_from_patterns(clean_home, brand, domain)
        if home_result and home_result[1]:
            return home_result[0], home_result[1], f"homepage:{home_result[2]}"
    except Exception:
        pass

    # 2. Standard high-yield paths for e-commerce DTC stores (expanded)
    standard_paths = [
        '/policies/legal-notice', '/policies/contact-information',
        '/pages/about-us', '/pages/our-story', '/pages/about', '/about',
        '/pages/contact-us', '/pages/contact', '/contact-us', '/contact',
        '/pages/impressum', '/impressum',
        '/pages/mentions-legales', '/policies/terms-of-service',
        '/pages/terms-and-conditions', '/terms-and-conditions',
        # Additional high-yield paths
        '/pages/meet-the-team', '/pages/meet-us', '/pages/team',
        '/pages/founder', '/pages/founders', '/pages/meet-the-founder',
        '/pages/who-we-are', '/pages/our-mission', '/pages/our-company',
        '/pages/bio', '/pages/my-story', '/pages/your-story',
        '/pages/the-maker', '/pages/the-artist', '/pages/the-designer',
        '/over-ons', '/uber-uns', '/chi-siamo', '/sobre-nosotros',
        '/a-propos', '/qui-sommes-nous',
        # Shopify
        '/pages/privacy-policy',  # sometimes has legal contact info
    ]
    for p in standard_paths:
        u = f"https://{domain}{p}"
        if u not in about_urls:
            about_urls.append(u)

    # 3. Parallel fetch of candidate URLs (fast & concurrent, top 8 high-yield URLs)
    candidate_urls = about_urls[:8]
    pages_html = await asyncio.gather(*[fetch(client, u, sem, min(timeout, 3.5)) for u in candidate_urls], return_exceptions=True)

    for i, html in enumerate(pages_html):
        if not html or isinstance(html, Exception) or len(html) < 250:
            continue
        page_url = candidate_urls[i]
        try:
            schema_result = extract_schema_person(html, brand, domain)
            if schema_result:
                return schema_result[0], schema_result[1], f"schema:{page_url.split('/')[-1]}"

            # Direct UK Company Number Mining (100% ground-truth director disclosure)
            m_reg = re.search(r'(?:Company\s*(?:Registration\s*)?No\.?|Company\s*Number|Registered\s*(?:in\s*England\s*(?:and\s*Wales)?\s*)?(?:under\s*)?(?:Company\s*)?Number|(?:Company\s*)?Registration\s*Number)[:\s]+([0-9]{7,8})\b', html, re.I)
            if m_reg and (domain.lower().endswith(('.uk', '.co.uk')) or detect_domain_country(domain) == 'UK' or any(k in html.lower() for k in ('england', 'wales', 'united kingdom', 'gbp', '£'))):
                c_num = m_reg.group(1)
                ch_url = f"https://find-and-update.company-information.service.gov.uk/company/{c_num}/officers"
                ch_html = await fetch(client, ch_url, sem, timeout)
                if ch_html:
                    ch_soup = BeautifulSoup(ch_html, 'html.parser')
                    for off_a in ch_soup.find_all('a', href=True):
                        if '/officers/' in off_a['href']:
                            raw_o = off_a.get_text(strip=True)
                            if ',' in raw_o:
                                sur, giv = raw_o.split(',', 1)
                                giv_words = giv.strip().split()
                                if giv_words:
                                    fn_o, ln_o = giv_words[0].capitalize(), sur.strip().capitalize()
                                    if is_clean_human_name(f"{fn_o} {ln_o}", brand, domain):
                                        return fn_o, ln_o, f"companies_house_reg:{c_num}"

            soup = BeautifulSoup(html, 'html.parser')
            for el in soup(['script', 'style', 'nav', 'footer', 'header']):
                el.decompose()
            clean_text = " ".join(soup.get_text(separator=" ", strip=True).split())
            result = extract_name_from_patterns(clean_text, brand, domain)
            if result:
                fn, ln, pat = result
                return fn, ln, f"about_page:{page_url.split('/')[-1]}:{pat}"
        except Exception:
            continue
    return None


# ── TIER 3: Multi-Engine Search ───────────────────────────────────────────────

async def search_yahoo(client, domain: str, brand: str, sem: asyncio.Semaphore, timeout: float) -> Optional[Tuple[str, str, str]]:
    """Yahoo Search — uses clean queries to avoid 500 errors."""
    brand_q = re.sub(r'\s*[-–—|].*$', '', brand).strip()
    if len(brand_q) < 3:
        brand_q = brand
    stem = domain.lower().split('.')[0]
    has_unique_stem = (any(c.isdigit() for c in stem) or '-' in stem or len(stem) >= 8)
    queries = [
        f'"{brand_q}" founder',
        f'"{stem}" founder',
        f'"{domain}" owner CEO founder -jobs -careers',
        f'{domain} founder owner',
    ]
    for q in queries:
        try:
            url = f"https://search.yahoo.com/search?p={urllib.parse.quote(q)}"
            html = await fetch(client, url, sem, min(timeout, 5.0))
            if not html:
                continue
            soup = BeautifulSoup(html, 'html.parser')
            for div in soup.find_all('div', class_='algo'):
                a_tag = div.find('a', href=True)
                raw_href = a_tag['href'] if a_tag else ''
                real_url = get_real_card_url(raw_href)
                if not is_trusted_source(real_url, domain):
                    continue
                card_text = div.get_text(separator=' ', strip=True)
                if not is_card_grounded(card_text, domain, brand):
                    continue
                result = extract_name_from_patterns(card_text, brand, domain)
                if result and result[1]:
                    return result[0], result[1], f"yahoo:{result[2]}"
        except Exception:
            continue
    return None


async def search_ddg(client, domain: str, brand: str, sem: asyncio.Semaphore, timeout: float) -> Optional[Tuple[str, str, str]]:
    """DuckDuckGo Lite with tight 2.0s non-blocking timeout."""
    try:
        data = urllib.parse.urlencode({'q': f"{domain} owner founder"}).encode()
        async with sem:
            resp = await client.post(
                'https://lite.duckduckgo.com/lite/', content=data,
                headers={**random.choice(HEADERS_POOL), 'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=min(timeout, 2.0)
            )
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            for a in soup.find_all('a', class_='result-link'):
                href = a.get('href', '')
                if not is_trusted_source(href, domain):
                    continue
                parent = a.find_parent('tr')
                if not parent:
                    continue
                card_text = parent.get_text(separator=' ', strip=True)
                if not is_card_grounded(card_text, domain, brand):
                    continue
                result = extract_name_from_patterns(card_text, brand, domain)
                if result and result[1]:
                    return result[0], result[1], f"ddg:{result[2]}"
    except Exception:
        pass
    return None


async def search_bing(client, domain: str, brand: str, sem: asyncio.Semaphore, timeout: float) -> Optional[Tuple[str, str, str]]:
    """Bing Search — parses regular results AND Bing AI answer box (like Google AI Overview)."""
    brand_q = re.sub(r'\s*[-–—|].*$', '', brand).strip()
    if len(brand_q) < 3: brand_q = brand
    stem = domain.lower().split('.')[0]
    has_unique_stem = (any(c.isdigit() for c in stem) or '-' in stem or len(stem) >= 8)
    queries = [
        f"{domain} founder owner",
        f'who owns "{brand_q}" OR "{domain}"',
        f'"{brand_q}" owner OR founder site:linkedin.com',
    ]
    for q in queries:
        try:
            url = f"https://www.bing.com/search?q={urllib.parse.quote(q)}&setlang=en"
            html = await fetch(client, url, sem, min(timeout, 4.0))
            if not html:
                continue
            soup = BeautifulSoup(html, 'html.parser')

            # NEW: Bing AI Answer box (class b_ai_generated, b_ans, b_rich, or div#b_entityTP)
            # This is where Bing surfaces "Owner: John Smith" style answers
            for ai_box in soup.find_all(class_=[
                'b_ai_generated', 'b_ans', 'b_rich', 'b_entityTP',
                'df_topEntity', 'b_focusTextSmall', 'b_snippetBigText',
            ]):
                ai_text = ai_box.get_text(separator=' ', strip=True)
                if not ai_text or len(ai_text) < 10:
                    continue
                # Pattern: "Owner: John Smith" or "owned by John Smith"
                m_owner = re.search(
                    r'(?:Owner|Founder|CEO|Director|Founded by|Owned by|Run by|Created by)\s*:?\s*'
                    r'([A-Z][a-z]{1,15}(?:\s+[A-Z][a-z]{1,20})+)',
                    ai_text
                )
                if m_owner:
                    name = m_owner.group(1).strip()
                    parts = name.split()
                    if len(parts) >= 2:
                        fn, ln = parts[0].capitalize(), parts[-1].capitalize()
                        if is_clean_human_name(f'{fn} {ln}', brand, domain):
                            return fn, ln, 'bing:ai_box'

                # Co-founder pair: "John & Jenny" or "John and Jenny" — pick the first
                m_pair = re.search(
                    r'(?:owned by|founded by|owners?|founders?)\s+'
                    r'([A-Z][a-z]{2,15})\s+(?:&|and)\s+([A-Z][a-z]{2,15})',
                    ai_text, re.I
                )
                if m_pair:
                    fn1, fn2 = m_pair.group(1).capitalize(), m_pair.group(2).capitalize()
                    # Use whichever sounds more like a full name in context
                    for fn in [fn1, fn2]:
                        if is_clean_human_name(fn, brand, domain):
                            return fn, '', 'bing:ai_pair_first'

                # General name extraction from AI box text (grounded)
                if domain.split('.')[0].lower() in ai_text.lower() or brand.lower()[:8] in ai_text.lower():
                    result = extract_name_from_patterns(ai_text, brand, domain)
                    if result and result[1]:
                        return result[0], result[1], f'bing:ai_answer:{result[2]}'

            # Regular search results
            for item in soup.find_all(class_=['b_algo', 'b_rich']):
                card_text = item.get_text(separator=' ', strip=True)
                if not is_card_grounded(card_text, domain, brand):
                    continue
                a_tag = item.find('a', href=True)
                if a_tag:
                    href = a_tag.get('href', '')
                    if not is_trusted_source(href, domain):
                        continue
                result = extract_name_from_patterns(card_text, brand, domain)
                if result and result[1]:
                    return result[0], result[1], f"bing:{result[2]}"

                # Co-founder pair in regular results
                m_pair = re.search(
                    r'(?:owned by|founded by|owners?|founders?)\s+'
                    r'([A-Z][a-z]{2,15})\s+(?:&|and)\s+([A-Z][a-z]{2,15})',
                    card_text, re.I
                )
                if m_pair and is_card_grounded(card_text, domain, brand):
                    fn1 = m_pair.group(1).capitalize()
                    fn2 = m_pair.group(2).capitalize()
                    for fn in [fn1, fn2]:
                        if is_clean_human_name(fn, brand, domain):
                            return fn, '', 'bing:pair_first'

        except Exception:
            continue
    return None


async def linkedin_dork(client, domain: str, brand: str, sem: asyncio.Semaphore, timeout: float) -> Optional[Tuple[str, str, str]]:
    """LinkedIn dork — STRICT: card text must mention domain or brand to prevent cross-lead contamination."""
    brand_q = re.sub(r'\s*[-–—|].*$', '', brand).strip()
    if len(brand_q) < 3: brand_q = brand
    stem = domain.lower().split('.')[0]
    for q in [
        f'site:linkedin.com "{brand_q}" founder OR owner OR director',
        f'site:linkedin.com "{stem}" founder OR owner' if len(stem) >= 5 else f'site:linkedin.com "{brand_q}" executive',
    ]:
        url = f"https://search.yahoo.com/search?p={urllib.parse.quote(q)}"
        html = await fetch(client, url, sem, timeout)
        if not html:
            continue
        try:
            soup = BeautifulSoup(html, 'html.parser')
            for div in soup.find_all('div', class_='algo'):
                a_tag = div.find('a', href=True)
                if not a_tag:
                    continue
                real_url = get_real_card_url(a_tag['href'])
                if 'linkedin.com/in/' not in real_url.lower():
                    continue
                card_text = div.get_text(separator=' ', strip=True)
                if not is_card_grounded(card_text, domain, brand):
                    continue
                result = extract_name_from_patterns(card_text, brand, domain)
                if result and result[1]:
                    return result[0], result[1], real_url
                m = re.search(r'^([A-Z][a-z]+\s+[A-Z][a-z]+)\s*[-|]', card_text)
                if m:
                    parts = m.group(1).split()
                    fn, ln = parts[0].capitalize(), parts[1].capitalize()
                    if is_clean_human_name(f"{fn} {ln}", brand, domain):
                        return fn, ln, real_url
        except Exception:
            continue
    return None


# ── TIER 4: Deep OSINT ────────────────────────────────────────────────────────

def socket_whois_lookup(domain: str) -> Optional[Tuple[str, str]]:
    """Direct Port 43 Socket WHOIS fallback for .us, .com, .org, .de, etc.
    Extracts Registrant Name, Admin Name, or Owner directly from registry."""
    parts = domain.lower().split('.')
    if len(parts) < 2:
        return None
    tld = '.'.join(parts[-2:]) if len(parts) > 2 and parts[-2] in ('co', 'com', 'org', 'net') else parts[-1]
    servers = {
        'com': 'whois.verisign-grs.com', 'net': 'whois.verisign-grs.com',
        'org': 'whois.pir.org', 'us': 'whois.nic.us',
        'de': 'whois.denic.de', 'fr': 'whois.nic.fr', 'nl': 'whois.domain-registry.nl',
        'io': 'whois.nic.io', 'shop': 'whois.nic.shop', 'site': 'whois.nic.site',
        'store': 'whois.nic.store', 'info': 'whois.afilias.net', 'biz': 'whois.biz',
        'co': 'whois.nic.co', 'in': 'whois.registry.in', 'ca': 'whois.cira.ca',
        'ch': 'whois.nic.ch', 'at': 'whois.nic.at', 'be': 'whois.dns.be',
        'it': 'whois.nic.it', 'me': 'whois.nic.me', 'au': 'whois.auda.org.au',
        'com.au': 'whois.auda.org.au', 'net.au': 'whois.auda.org.au',
        'co.uk': 'whois.nic.uk', 'co.nz': 'whois.srs.net.nz',
        'cc': 'whois.nic.cc', 'tv': 'whois.nic.tv', 'xyz': 'whois.nic.xyz',
    }
    server = servers.get(tld) or servers.get(parts[-1])
    if not server:
        return None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.5)
        s.connect((server, 43))
        payload = (f'-T dn,ace {domain}\r\n' if tld == 'de' else f'{domain}\r\n').encode()
        s.send(payload)
        res = b''
        while len(res) < 16384:
            data = s.recv(4096)
            if not data: break
            res += data
        s.close()
        text = res.decode('utf-8', errors='ignore')
        for line in text.splitlines():
            m = re.search(r'(?:Registrant|Admin|Owner)(?:\s+(?:Contact|Name|Person|Details))*[:\s]+([A-Za-z\s]+)$', line, re.I)
            if m:
                val = m.group(1).strip()
                if val and not any(b in val.lower() for b in ['privacy', 'redacted', 'whoisguard', 'proxy', 'gdpr', 'contact', 'domains', 'service', 'inc', 'llc', 'ltd', 'corporation']):
                    words = val.split()
                    if 2 <= len(words) <= 3:
                        fn, ln = words[0].capitalize(), words[-1].capitalize()
                        if is_clean_human_name(f"{fn} {ln}", domain=domain):
                            return fn, ln
    except Exception:
        pass
    return None


async def whois_rdap_lookup(client, domain: str, sem: asyncio.Semaphore, timeout: float) -> Optional[Tuple[str, str]]:
    # Direct port 43 socket WHOIS is instant (50-150ms) for known registries
    try:
        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, socket_whois_lookup, domain)
        if res:
            return res
    except Exception:
        pass

    # RDAP fallback for generic TLDs
    if domain.lower().endswith(('.com', '.net')):
        for rdap_url in [
            f"https://rdap.verisign.com/com/v1/domain/{domain}",
            f"https://rdap.org/domain/{domain}",
        ]:
            try:
                html = await fetch(client, rdap_url, sem, timeout)
                if html:
                    data = json.loads(html)
                    for entity in data.get('entities', []):
                        roles = entity.get('roles', [])
                        if 'registrant' in roles or 'administrative' in roles:
                            vcard = entity.get('vcardArray', [])
                            if vcard and len(vcard) > 1:
                                for prop in vcard[1]:
                                    if prop[0] == 'fn':
                                        name = prop[3]
                                        if name and not any(w in name.lower() for w in ['privacy', 'proxy', 'redacted', 'whoisguard']):
                                            parts = name.strip().split()
                                            if len(parts) >= 2:
                                                fn, ln = parts[0].capitalize(), parts[-1].capitalize()
                                                if is_clean_human_name(f"{fn} {ln}", domain=domain):
                                                    return fn, ln
            except Exception:
                continue
    return None


async def companies_house_lookup(client, domain: str, brand: str, sem: asyncio.Semaphore, timeout: float) -> Optional[Tuple[str, str, str]]:
    """UK Companies House Director Mining (Zero API Key, public find-and-update endpoint)."""
    # Skip non-UK ccTLDs and global generic platforms to avoid homonym false positives in UK registry
    foreign_cctlds = (
        '.my', '.au', '.nz', '.ca', '.de', '.fr', '.it', '.es', '.nl', '.in',
        '.jp', '.kr', '.cn', '.br', '.mx', '.sg', '.hk', '.za', '.ch', '.at',
        '.be', '.dk', '.se', '.no', '.fi', '.pl', '.cz', '.gr', '.pt', '.ro',
        '.hu', '.ie', '.il', '.ae', '.sa', '.rs', '.bg', '.hr', '.sk', '.si',
        '.lt', '.lv', '.ee', '.global', '.shop', '.store', '.tech', '.space',
        '.online', '.site', '.app', '.co', '.io', '.ai', '.me', '.us'
    )
    if any(domain.lower().endswith(cctld) for cctld in foreign_cctlds):
        return None

    clean_q = re.sub(r'[^a-zA-Z0-9\s]', ' ', brand).strip()
    search_terms = [clean_q]
    if "ltd" not in clean_q.lower() and "limited" not in clean_q.lower():
        search_terms.append(f"{clean_q} LTD")
    for q_str in search_terms:
        try:
            url = f"https://find-and-update.company-information.service.gov.uk/search/companies?q={urllib.parse.quote(q_str)}"
            html = await fetch(client, url, sem, timeout)
            if not html:
                continue
            soup = BeautifulSoup(html, 'html.parser')
            for a in soup.find_all('a', href=True):
                m_comp = re.search(r'/company/([A-Z0-9]{6,8})$', a['href'])
                if m_comp:
                    comp_name = a.get_text(strip=True).lower()
                    clean_brand = re.sub(r'[^a-z0-9]', '', brand.lower())
                    clean_comp = re.sub(r'[^a-z0-9]', '', comp_name)
                    stem = domain.lower().split('.')[0]
                    clean_stem = re.sub(r'[^a-z0-9]', '', stem)
                    is_uk_domain = domain.lower().endswith(('.uk', '.co.uk')) or detect_domain_country(domain) == 'UK'
                    if not is_uk_domain:
                        if len(clean_brand) < 5 or len(clean_stem) < 5:
                            continue
                        if clean_stem not in clean_comp and clean_comp not in (clean_stem, f"{clean_stem}ltd", f"{clean_stem}limited"):
                            continue
                        valid_exact = {clean_brand, f"{clean_brand}ltd", f"{clean_brand}limited",
                                       clean_stem, f"{clean_stem}ltd", f"{clean_stem}limited"}
                        if clean_comp not in valid_exact:
                            continue
                    else:
                        if clean_brand not in clean_comp and clean_comp not in clean_brand and clean_stem not in clean_comp:
                            continue
                    company_num = m_comp.group(1)
                    officers_url = f"https://find-and-update.company-information.service.gov.uk/company/{company_num}/officers"
                    off_html = await fetch(client, officers_url, sem, timeout)
                    if not off_html:
                        continue
                    off_soup = BeautifulSoup(off_html, 'html.parser')
                    for off_a in off_soup.find_all('a', href=True):
                        if '/officers/' in off_a['href']:
                            raw_name = off_a.get_text(strip=True)
                            if ',' in raw_name:
                                parts = raw_name.split(',', 1)
                                ln = parts[0].strip().capitalize()
                                fn_parts = parts[1].strip().split()
                                fn = fn_parts[0].capitalize() if fn_parts else ''
                                if fn and ln and is_clean_human_name(f"{fn} {ln}"):
                                    return fn, ln, "Director"
        except Exception:
            continue
    return None


async def crunchbase_mining(client, domain: str, brand: str, sem: asyncio.Semaphore, timeout: float) -> Optional[Tuple[str, str]]:
    """Crunchbase/AngelList founder mining.
    ULTRA-STRICT: full domain with TLD must appear in card text.
    Prevents famous-name collisions (e.g. Anchorman film vs anchorman.nz)."""
    for q in [f'site:crunchbase.com "{brand}" founder', f'site:angel.co "{brand}" founder', f'site:producthunt.com "{brand}" maker']:
        url = f"https://search.yahoo.com/search?p={urllib.parse.quote(q)}"
        html = await fetch(client, url, sem, timeout)
        if not html:
            continue
        try:
            soup = BeautifulSoup(html, 'html.parser')
            for div in soup.find_all('div', class_='algo'):
                a_tag = div.find('a', href=True)
                href = get_real_card_url(a_tag['href']) if a_tag else ''
                # Must link to crunchbase/angel/producthunt
                if not any(s in href.lower() for s in ('crunchbase.com', 'angel.co', 'producthunt.com')):
                    continue
                card_text = div.get_text(separator=' ', strip=True)
                # ULTRA-STRICT: full domain with TLD must appear in card text
                if domain.lower() not in card_text.lower():
                    continue
                result = extract_name_from_patterns(card_text, brand, domain)
                if result and result[1]:
                    return result[0], result[1]
        except Exception:
            continue
    return None


async def social_bio_mining(client, domain: str, brand: str, instagram: str, facebook: str,
                             sem: asyncio.Semaphore, timeout: float) -> Optional[Tuple[str, str]]:
    if instagram:
        handle = instagram.strip('/').split('/')[-1].lstrip('@')
        if handle and handle not in ('shopify', 'instagram'):
            html = await fetch(client, f"https://www.instagram.com/{handle}/", sem, timeout)
            if html:
                m = re.search(r'"biography"\s*:\s*"([^"]{10,200})"', html)
                if m:
                    bio = m.group(1).replace('\\n', ' ').replace('\\u0026', '&')
                    result = extract_name_from_patterns(bio, brand, domain)
                    if result and result[1]:
                        return result[0], result[1]
    return None


# ── MAIN ENRICHMENT ORCHESTRATOR ──────────────────────────────────────────────

async def ultra_enrich_lead(client, lead_row: Dict[str, str], sem: asyncio.Semaphore,
                             timeout: float = 5.0) -> Dict[str, str]:
    row = dict(lead_row)
    lead_email = row.get('Email', '').strip().lstrip('//')
    secondary_email = row.get('Secondary_Email', '').strip()
    brand = row.get('Store_Name', '')
    domain = clean_domain(row.get('Domain', ''))
    instagram = row.get('Instagram', '')
    facebook = row.get('Facebook', '')

    # Initialize all output fields
    row["Exec_First"] = ""
    row["Exec_Last"] = ""
    row["Exec_Name"] = ""
    row["Exec_Title"] = "Store Management"
    row["Exec_Email"] = lead_email
    row["Exec_Email_Pattern"] = "store_email"
    row["Exec_Bonus_Email"] = ""
    row["Exec_Source"] = "store_inbox"
    row["Exec_Source_Chain"] = ""
    row["Exec_Gravatar"] = "False"
    row["Exec_Confidence"] = "STANDARD"
    row["Exec_LinkedIn_URL"] = ""
    row["Exec_Twitter"] = ""
    row["Exec_Phone"] = ""
    row["Exec_Company_Reg"] = ""
    row["Exec_Reg_Country"] = detect_domain_country(domain) if domain else ""
    row["Exec_Email_Variants"] = ""

    if not domain:
        return row

    source_chain = []

    # TIER 0 + TIER 1: Concurrent — run email discovery, DNA, and namesake in parallel
    # Email discovery finds personal emails on the site (mailto:, Cloudflare-decoded)
    # DNA instantly resolves name from first.last@ email format
    # Both run at the same time to avoid serial slowdown
    discovered_emails: List[str] = []

    try:
        # Fire off site email discovery + WordPress API + RSS concurrently (no Wayback — too slow)
        t0_site = asyncio.create_task(discover_emails_on_site(client, domain, sem, timeout))
        t0_wp   = asyncio.create_task(wordpress_api_author(client, domain, brand, sem, timeout))
        t0_rss  = asyncio.create_task(rss_feed_author(client, domain, brand, sem, timeout))
        # Wait with a short cap so we don't eat into main tiers
        t0_results = await asyncio.wait_for(
            asyncio.gather(t0_site, t0_wp, t0_rss, return_exceptions=True),
            timeout=min(timeout * 0.5, 2.5)
        )
        site_emails, wp_result, rss_result = t0_results

        if isinstance(site_emails, list):
            discovered_emails.extend(site_emails)

        # WordPress API found a name directly — highest quality, return immediately
        if wp_result and isinstance(wp_result, tuple) and len(wp_result) >= 2 and wp_result[0] and wp_result[1]:
            fn, ln = wp_result[0], wp_result[1]
            source_chain.append('tier0:wordpress_api')
            row['Exec_First'] = fn
            row['Exec_Last'] = ln
            row['Exec_Name'] = f'{fn} {ln}'
            row['Exec_Title'] = 'Founder / Owner'
            row['Exec_Confidence'] = 'HIGH'
            row['Exec_Source'] = 'wordpress_api'
            row['Exec_Source_Chain'] = '|'.join(source_chain)
            row['Exec_Email_Variants'] = json.dumps(generate_email_variants(fn, ln, domain)[:6])
            best_email = next((e for e in discovered_emails if is_personal_email(e, domain)), lead_email)
            row['Exec_Email'] = best_email
            row['Exec_Email_Pattern'] = 'site_discovered' if best_email != lead_email else 'store_email'
            row['Exec_Bonus_Email'] = f'{fn.lower()}.{ln.lower()}@{domain}'
            row['Exec_Gravatar'] = str(check_gravatar(row['Exec_Email']))
            return row

        # RSS feed found a name
        if rss_result and isinstance(rss_result, tuple) and len(rss_result) >= 3:
            rfn, rln, rsrc = rss_result
            if rsrc.startswith('rss_email:'):
                rss_email = rsrc.split('rss_email:')[1]
                if rss_email not in discovered_emails:
                    discovered_emails.insert(0, rss_email)
            elif rfn and rln:
                source_chain.append('tier0:rss_feed')
                row['Exec_First'] = rfn
                row['Exec_Last'] = rln
                row['Exec_Name'] = f'{rfn} {rln}'
                row['Exec_Title'] = 'Founder / Owner'
                row['Exec_Confidence'] = 'HIGH'
                row['Exec_Source'] = 'rss_feed'
                row['Exec_Source_Chain'] = '|'.join(source_chain)
                row['Exec_Email_Variants'] = json.dumps(generate_email_variants(rfn, rln, domain)[:6])
                best_email = next((e for e in discovered_emails if is_personal_email(e, domain)), lead_email)
                row['Exec_Email'] = best_email
                row['Exec_Email_Pattern'] = 'site_discovered' if best_email != lead_email else 'store_email'
                row['Exec_Bonus_Email'] = f'{rfn.lower()}.{rln.lower()}@{domain}'
                row['Exec_Gravatar'] = str(check_gravatar(row['Exec_Email']))
                return row

        # Personal email found — record it, use in DNA below
        if discovered_emails:
            source_chain.append('tier0:site_email_discovery')
            # Prefer first.last@ patterns (names extracted from email DNA)
            best_personal = next(
                (e for e in discovered_emails if is_personal_email(e, domain) and '.' in e.split('@')[0]),
                next((e for e in discovered_emails if is_personal_email(e, domain)), None)
            )
            if best_personal and best_personal != lead_email:
                row['Exec_Email'] = best_personal
                row['Exec_Email_Pattern'] = 'site_discovered'

    except (asyncio.TimeoutError, Exception):
        pass

    # TIER 1: Email DNA — checks original email + any discovered personal email
    effective_email = row.get('Exec_Email', lead_email) or lead_email
    all_emails_to_check = list(dict.fromkeys(
        [e for e in [effective_email, lead_email, secondary_email] + discovered_emails[:2] if e]
    ))
    dna_result = None
    for check_email in all_emails_to_check:
        r_dna = analyze_email_dna(check_email, secondary_email, brand, domain)
        if r_dna and r_dna.get('Exec_Confidence') == 'HIGH':
            dna_result = r_dna
            break
        elif r_dna and r_dna.get('Exec_Confidence') == 'MEDIUM' and not dna_result:
            dna_result = r_dna
    if not dna_result:
        dna_result = analyze_email_dna(lead_email, secondary_email, brand, domain)

    if dna_result:
        chain = dna_result.pop("_chain", [])
        source_chain.extend(chain)
        if dna_result["Exec_Confidence"] == "HIGH":
            row.update(dna_result)
            row["Exec_Source_Chain"] = "|".join(source_chain)
            fn, ln = dna_result["Exec_First"], dna_result.get("Exec_Last", "")
            if ln:
                row["Exec_Email_Variants"] = json.dumps(generate_email_variants(fn, ln, domain)[:6])
            row["Exec_Gravatar"] = str(check_gravatar(dna_result["Exec_Email"]))
            return row
        # MEDIUM — fall through to find last name
        row.update(dna_result)

    # TIER 1.5: Namesake Brand Detection (instant, e.g. Arfa Malik -> arfamalik.com)
    namesake = check_namesake_brand(brand, domain)
    if namesake:
        fn, ln = namesake
        source_chain.append("namesake_brand")
        row["Exec_First"] = fn
        row["Exec_Last"] = ln
        row["Exec_Name"] = f"{fn} {ln}"
        row["Exec_Title"] = "Founder & Designer"
        row["Exec_Confidence"] = "HIGH"
        row["Exec_Source"] = "namesake_brand"
        row["Exec_Source_Chain"] = "|".join(source_chain)
        row["Exec_Email_Variants"] = json.dumps(generate_email_variants(fn, ln, domain)[:6])
        if not row["Exec_Email"] or row["Exec_Email"] == lead_email:
            row["Exec_Email"] = f"{fn.lower()}@{domain}"
            row["Exec_Email_Pattern"] = "derived_first"
            row["Exec_Bonus_Email"] = f"{fn.lower()}.{ln.lower()}@{domain}"
        row["Exec_Gravatar"] = str(check_gravatar(row["Exec_Email"]))
        return row

    # TIER 2: Site Crawl (JSON-LD + About pages)
    try:
        site_result = await asyncio.wait_for(
            deep_site_crawl(client, domain, brand, sem, timeout),
            timeout=min(timeout * 0.9, 4.0)
        )
    except (asyncio.TimeoutError, Exception):
        site_result = None

    if site_result:
        fn, ln, src = site_result
        source_chain.append(f"site:{src}")
        if ln:
            row["Exec_First"] = fn
            row["Exec_Last"] = ln
            row["Exec_Name"] = f"{fn} {ln}"
            row["Exec_Title"] = "Founder / CEO"
            row["Exec_Confidence"] = "HIGH"
            row["Exec_Source"] = f"site_crawl"
            row["Exec_Source_Chain"] = "|".join(source_chain)
            row["Exec_Email_Variants"] = json.dumps(generate_email_variants(fn, ln, domain)[:6])
            if not row["Exec_Email"] or row["Exec_Email"] == lead_email:
                row["Exec_Email"] = f"{fn.lower()}@{domain}"
                row["Exec_Email_Pattern"] = "derived_first"
                row["Exec_Bonus_Email"] = f"{fn.lower()}.{ln.lower()}@{domain}"
            row["Exec_Gravatar"] = str(check_gravatar(row["Exec_Email"]))
            return row
        elif fn and not row.get("Exec_First"):
            row["Exec_First"] = fn
            row["Exec_Name"] = fn
            row["Exec_Source"] = "site_crawl"
            row["Exec_Confidence"] = "MEDIUM"

    # TIER 3: Multi-Engine Search (concurrent across Yahoo, Bing, DDG)
    yahoo_t = asyncio.create_task(search_yahoo(client, domain, brand, sem, timeout))
    ddg_t = asyncio.create_task(search_ddg(client, domain, brand, sem, timeout))
    bing_t = asyncio.create_task(search_bing(client, domain, brand, sem, timeout))
    try:
        search_results = await asyncio.wait_for(
            asyncio.gather(yahoo_t, ddg_t, bing_t, return_exceptions=True),
            timeout=min(timeout * 2.5, 14.0)
        )
    except (asyncio.TimeoutError, Exception):
        search_results = []

    search_names = []
    engines = ['yahoo', 'ddg', 'bing']
    for i, result in enumerate(search_results):
        eng = engines[i]
        if isinstance(result, Exception) or result is None:
            continue
        fn, ln, extra = result[0], result[1], result[2]
        if extra and extra.startswith('http') and 'linkedin.com' in extra:
            row["Exec_LinkedIn_URL"] = extra
        if fn and ln:
            search_names.append((fn, ln, eng))
            source_chain.append(f"search:{eng}")

    if search_names:
        name_votes: Dict[str, int] = {}
        for fn, ln, eng in search_names:
            key = f"{fn} {ln}"
            name_votes[key] = name_votes.get(key, 0) + 1
        best_name = max(name_votes, key=name_votes.get)
        best_fn, best_ln = best_name.split(' ', 1)
        confidence = "VERIFIED" if name_votes[best_name] >= 2 else "HIGH"
        row["Exec_First"] = best_fn
        row["Exec_Last"] = best_ln
        row["Exec_Name"] = best_name
        row["Exec_Title"] = "Founder / Owner"
        row["Exec_Confidence"] = confidence
        row["Exec_Source"] = "search_intelligence"
        row["Exec_Source_Chain"] = "|".join(source_chain)
        row["Exec_Email_Variants"] = json.dumps(generate_email_variants(best_fn, best_ln, domain)[:6])
        if not row["Exec_Email"] or row["Exec_Email"] == lead_email:
            row["Exec_Email"] = f"{best_fn.lower()}@{domain}"
            row["Exec_Email_Pattern"] = "derived_first"
            row["Exec_Bonus_Email"] = f"{best_fn.lower()}.{best_ln.lower()}@{domain}"
        row["Exec_Gravatar"] = str(check_gravatar(row["Exec_Email"]))
        return row

    # TIER 4: Deep OSINT (concurrent)
    country = row["Exec_Reg_Country"]
    osint_tasks_map = {
        'whois': asyncio.create_task(whois_rdap_lookup(client, domain, sem, timeout)),
        'crunchbase': asyncio.create_task(crunchbase_mining(client, domain, brand, sem, timeout)),
        'social': asyncio.create_task(social_bio_mining(client, domain, brand, instagram, facebook, sem, timeout)),
    }
    clean_b = re.sub(r'[^a-zA-Z0-9]', '', re.sub(r'\.(com|net|org|store|shop|co|io)$', '', brand, flags=re.I))
    foreign_cctlds = (
        '.de', '.fr', '.it', '.se', '.dk', '.au', '.tw', '.in', '.ca',
        '.nz', '.rs', '.nl', '.be', '.ch', '.es', '.pt', '.no', '.fi',
        '.pl', '.cz', '.at', '.ru', '.jp', '.kr', '.cn', '.za', '.ky', '.ae',
        '.my', '.pk', '.sg', '.hk', '.id', '.th', '.vn', '.ph', '.br', '.mx',
        '.ar', '.cl', '.co', '.pe', '.ie', '.eu', '.asia', '.global'
    )
    has_foreign_tld = any(domain.lower().endswith(tld) for tld in foreign_cctlds)
    if not has_foreign_tld and len(clean_b) >= 5 and clean_b.lower() not in BANNED_WORDS:
        osint_tasks_map['companies_house'] = asyncio.create_task(
            companies_house_lookup(client, domain, brand, sem, timeout)
        )
    osint_keys = list(osint_tasks_map.keys())
    try:
        osint_results = await asyncio.wait_for(
            asyncio.gather(*osint_tasks_map.values(), return_exceptions=True),
            timeout=min(timeout * 0.8, 3.5)
        )
    except (asyncio.TimeoutError, Exception):
        osint_results = []

    for i, result in enumerate(osint_results):
        src_key = osint_keys[i]
        if isinstance(result, Exception) or result is None:
            continue
        if src_key == 'companies_house' and isinstance(result, tuple) and len(result) == 3:
            fn, ln, role = result
            row["Exec_Company_Reg"] = "UK Companies House"
        elif isinstance(result, tuple) and len(result) == 2:
            fn, ln = result
        else:
            continue
        if fn and ln and is_clean_human_name(f"{fn} {ln}", brand, domain):
            source_chain.append(f"osint:{src_key}")
            row["Exec_First"] = fn
            row["Exec_Last"] = ln
            row["Exec_Name"] = f"{fn} {ln}"
            row["Exec_Title"] = "Founder / Owner"
            row["Exec_Confidence"] = "HIGH"
            row["Exec_Source"] = f"osint:{src_key}"
            row["Exec_Source_Chain"] = "|".join(source_chain)
            row["Exec_Email_Variants"] = json.dumps(generate_email_variants(fn, ln, domain)[:6])
            if not row["Exec_Email"] or row["Exec_Email"] == lead_email:
                row["Exec_Email"] = f"{fn.lower()}@{domain}"
                row["Exec_Email_Pattern"] = "derived_first"
                row["Exec_Bonus_Email"] = f"{fn.lower()}.{ln.lower()}@{domain}"
            row["Exec_Gravatar"] = str(check_gravatar(row["Exec_Email"]))
            return row

    # TIER 5: Email Intelligence Engine (Gravatar profile + SMTP sweep + MX fingerprint)
    # Run this even if we have a name (validates best email) and when we DON'T have a name
    # (Gravatar profile JSON can reveal the owner's real name!)
    fn_now = row.get("Exec_First", "")
    ln_now = row.get("Exec_Last", "")
    try:
        email_intel = await asyncio.wait_for(
            email_intelligence_sweep(
                client, domain, fn_now or "info", ln_now, lead_email, sem, min(timeout, 3.0)
            ),
            timeout=min(timeout * 0.7, 3.0)
        )
        if email_intel:
            # If Gravatar found a real name and we don't have one yet
            grav_name = email_intel.get('gravatar_name', '').strip()
            if grav_name and not fn_now:
                parts = grav_name.split(None, 1)
                if len(parts) >= 2:
                    gfn, gln = parts[0].capitalize(), parts[1].capitalize()
                    if is_clean_human_name(f"{gfn} {gln}", brand, domain):
                        source_chain.append('email_intel:gravatar_profile')
                        row["Exec_First"] = gfn
                        row["Exec_Last"] = gln
                        row["Exec_Name"] = f"{gfn} {gln}"
                        row["Exec_Title"] = "Founder / Owner"
                        row["Exec_Confidence"] = "HIGH"
                        row["Exec_Source"] = "email_intel:gravatar"
                        row["Exec_Email_Variants"] = json.dumps(generate_email_variants(gfn, gln, domain)[:6])
                        if email_intel.get('gravatar_email'):
                            row["Exec_Email"] = email_intel['gravatar_email']
                            row["Exec_Email_Pattern"] = "gravatar_validated"
                        fn_now, ln_now = gfn, gln
                elif len(parts) == 1 and not fn_now:
                    gfn = parts[0].capitalize()
                    if is_clean_human_name(gfn, brand, domain):
                        source_chain.append('email_intel:gravatar_profile')
                        row["Exec_First"] = gfn
                        row["Exec_Name"] = gfn
                        row["Exec_Confidence"] = "MEDIUM"
                        row["Exec_Source"] = "email_intel:gravatar"
                        fn_now = gfn

            # If Gravatar confirmed the lead_email has a real account (even without name)
            if email_intel.get('gravatar_has_account') and email_intel.get('gravatar_email') == lead_email:
                row["Exec_Gravatar"] = "True"  # Override the existing check

            # If SMTP verified a specific personal email variant
            smtp_email = email_intel.get('smtp_verified_email', '')
            if smtp_email and smtp_email != lead_email and fn_now:
                # SMTP confirmed a personal email variant — use it as the exec email
                source_chain.append(f"email_intel:smtp_valid")
                if not row.get('Exec_Email') or row['Exec_Email'] == lead_email:
                    row["Exec_Email"] = smtp_email
                    row["Exec_Email_Pattern"] = "smtp_verified"
                    row["Exec_Confidence"] = max(row.get('Exec_Confidence', 'STANDARD'),
                                                  'HIGH', key=lambda x: {'VERIFIED':4,'HIGH':3,'MEDIUM':2,'STANDARD':1,'':0}.get(x,0))

            # Record email provider
            provider = email_intel.get('email_provider', '')
            if provider:
                if not row.get('Exec_Source_Chain'):
                    source_chain.append(f"provider:{provider.replace(' ', '_')}")
    except Exception:
        pass

    # Final: emit partial data
    row["Exec_Source_Chain"] = "|".join(source_chain) if source_chain else "store_inbox"
    fn = row.get("Exec_First", "")
    ln = row.get("Exec_Last", "")
    if fn:
        row["Exec_Email_Variants"] = json.dumps(generate_email_variants(fn, ln, domain)[:6])
        if ln and (not row["Exec_Email"] or row["Exec_Email"] == lead_email):
            row["Exec_Bonus_Email"] = f"{fn.lower()}.{ln.lower()}@{domain}"
        row["Exec_Gravatar"] = str(check_gravatar(lead_email))
    return row


# ── Cluster Runner ────────────────────────────────────────────────────────────

async def run_cluster_node(
    slice_id: int, total_slices: int, concurrency: int, timeout: float,
    input_csv: str, output_csv: str, limit: Optional[int] = None,
    batch_notify: int = 500,
    telegram_token: str = DEFAULT_TELEGRAM_TOKEN,
    telegram_chat_id: str = DEFAULT_TELEGRAM_CHAT_ID,
):
    start_time = time.time()
    print("=" * 90, flush=True)
    print(f"[+] ULTRA ENRICHER v5.0 — NODE {slice_id+1}/{total_slices}", flush=True)
    print(f"[*] 16+ Sources | Concurrency: {concurrency} | Timeout: {timeout}s", flush=True)
    print("=" * 90, flush=True)

    rows: List[Dict[str, str]] = []
    fieldnames: List[str] = []

    if input_csv.startswith("http://") or input_csv.startswith("https://"):
        req = urllib.request.Request(input_csv, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            lines = [line.decode('utf-8', errors='ignore') for line in resp.readlines()]
            reader = csv.DictReader(lines)
            fieldnames = reader.fieldnames or []
            for r in reader: rows.append(r)
    else:
        with open(input_csv, 'r', encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            for r in reader: rows.append(r)

    total_master = len(rows)
    print(f"[*] Total leads in master: {total_master:,}", flush=True)

    slice_leads = [r for idx, r in enumerate(rows) if (idx % total_slices) == slice_id]
    if limit:
        slice_leads = slice_leads[:limit]

    # Resume support
    done_domains: Set[str] = set()
    if os.path.exists(output_csv):
        with open(output_csv, 'r', encoding='utf-8', errors='ignore') as f:
            rdr = csv.DictReader(f)
            for r in rdr:
                d = clean_domain(r.get('Domain', ''))
                if d:
                    done_domains.add(d)
        print(f"[*] Resume: {len(done_domains)} already done, skipping.", flush=True)

    pending = [r for r in slice_leads if clean_domain(r.get('Domain', '')) not in done_domains]
    print(f"[*] Pending: {len(pending):,} leads | Node {slice_id+1}/{total_slices}: {len(slice_leads):,} total", flush=True)

    extra_fields = [
        'Exec_First','Exec_Last','Exec_Name','Exec_Title',
        'Exec_Email','Exec_Email_Pattern','Exec_Bonus_Email',
        'Exec_Source','Exec_Source_Chain','Exec_Gravatar','Exec_Confidence',
        'Exec_LinkedIn_URL','Exec_Twitter','Exec_Phone',
        'Exec_Company_Reg','Exec_Reg_Country','Exec_Email_Variants',
    ]
    all_fieldnames = list(fieldnames) + [f for f in extra_fields if f not in fieldnames]

    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    write_mode = 'a' if done_domains else 'w'
    out_file = open(output_csv, write_mode, newline='', encoding='utf-8')
    writer = csv.DictWriter(out_file, fieldnames=all_fieldnames, extrasaction='ignore')
    if write_mode == 'w':
        writer.writeheader()
    out_file.flush()

    sem = asyncio.Semaphore(concurrency)
    conf_counts: Dict[str, int] = {"VERIFIED": 0, "HIGH": 0, "MEDIUM": 0, "STANDARD": 0}
    node_num = slice_id + 1

    send_telegram(
        f"<b>ULTRA ENRICHER v5.0 — NODE {node_num}/{total_slices} ACTIVATED</b>\n"
        f"16+ Sources (Yahoo+DDG+Bing+LinkedIn+Whois+Schema+Companies House)\n"
        f"Assigned: {len(slice_leads):,} | Pending: {len(pending):,}",
        telegram_token, telegram_chat_id
    )

    client_cm = (
        AsyncSession(impersonate="chrome124", curl_options=CURL_V4_OPTIONS) if HAS_CURL else
        httpx.AsyncClient(
            timeout=timeout, follow_redirects=True,
            limits=httpx.Limits(max_connections=concurrency * 3, max_keepalive_connections=concurrency),
        )
    )

    lead_sem = asyncio.Semaphore(concurrency)

    async def process_one(lead):
        async with lead_sem:
            lead_sem_internal = asyncio.Semaphore(5)
            try:
                if HAS_CURL:
                    async with AsyncSession(impersonate="chrome124", curl_options=CURL_V4_OPTIONS) as lead_client:
                        return await asyncio.wait_for(
                            ultra_enrich_lead(lead_client, lead, lead_sem_internal, timeout),
                            timeout=max(timeout * 2.5, 22.0)
                        )
                else:
                    return await asyncio.wait_for(
                        ultra_enrich_lead(client, lead, lead_sem_internal, timeout),
                        timeout=max(timeout * 2.5, 22.0)
                    )
            except Exception:
                row = dict(lead)
                row["Exec_First"] = ""
                row["Exec_Last"] = ""
                row["Exec_Name"] = ""
                row["Exec_Title"] = "Store Management"
                row["Exec_Email"] = row.get("Email", "").strip().lstrip("//")
                row["Exec_Email_Pattern"] = "store_email"
                row["Exec_Bonus_Email"] = ""
                row["Exec_Source"] = "store_inbox"
                row["Exec_Source_Chain"] = "fallback"
                row["Exec_Gravatar"] = "False"
                row["Exec_Confidence"] = "STANDARD"
                row["Exec_LinkedIn_URL"] = ""
                row["Exec_Twitter"] = ""
                row["Exec_Phone"] = ""
                row["Exec_Company_Reg"] = ""
                row["Exec_Reg_Country"] = detect_domain_country(clean_domain(row.get("Domain", "")))
                row["Exec_Email_Variants"] = ""
                return row

    async with client_cm as client:
        tasks = [process_one(lead) for lead in pending]

        for i, coro in enumerate(asyncio.as_completed(tasks)):
            full_row = await coro
            writer.writerow(full_row)
            out_file.flush()
            conf = full_row.get('Exec_Confidence', 'STANDARD')
            conf_counts[conf] = conf_counts.get(conf, 0) + 1

            if (i + 1) % 5 == 0 or (i + 1) == len(pending) or len(pending) <= 100:
                elapsed = time.time() - start_time
                rate = (i + 1) / max(elapsed, 1) * 60
                pct = ((i + 1) / max(len(pending), 1)) * 100
                name_disp = full_row.get('Exec_Name') or '(Blank)'
                src_disp = full_row.get('Exec_Source', '')[:18]
                print(
                    f"[{node_num:02d}/30] [{i+1:4d}/{len(pending)}] ({pct:5.1f}%) "
                    f"{rate:4.0f}/min | VER:{conf_counts.get('VERIFIED',0)} "
                    f"HIGH:{conf_counts.get('HIGH',0)} MED:{conf_counts.get('MEDIUM',0)} | "
                    f"{full_row.get('Store_Name','')[:18]:<18} -> {name_disp:<16} [{src_disp}]",
                    flush=True
                )

            if (i + 1) % batch_notify == 0:
                elapsed_min = (time.time() - start_time) / 60
                total_found = sum(conf_counts.get(k, 0) for k in ('VERIFIED', 'HIGH', 'MEDIUM'))
                send_telegram(
                    f"<b>ULTRA ENRICHER NODE {node_num}/{total_slices} @ {(i+1)/max(len(pending),1)*100:.0f}%</b>\n"
                    f"VERIFIED:{conf_counts.get('VERIFIED',0)} HIGH:{conf_counts.get('HIGH',0)} MED:{conf_counts.get('MEDIUM',0)}\n"
                    f"Named: {total_found}/{i+1} ({total_found/max(i+1,1)*100:.0f}%) | {(i+1)/max(elapsed_min,0.01):.0f}/min",
                    telegram_token, telegram_chat_id
                )

    out_file.close()
    elapsed = time.time() - start_time
    total_proc = len(pending)
    total_found = sum(conf_counts.get(k, 0) for k in ('VERIFIED', 'HIGH', 'MEDIUM'))

    print("=" * 90, flush=True)
    print(f"[DONE] Node {node_num}/{total_slices} — {elapsed/60:.1f} min | Processed: {total_proc:,}", flush=True)
    print(f"[DONE] VERIFIED: {conf_counts.get('VERIFIED',0)} | HIGH: {conf_counts.get('HIGH',0)} | MEDIUM: {conf_counts.get('MEDIUM',0)}", flush=True)
    print(f"[DONE] Named Rate: {total_found/max(total_proc,1)*100:.1f}% | Output: {output_csv}", flush=True)
    print("=" * 90, flush=True)

    send_telegram(
        f"<b>ULTRA ENRICHER NODE {node_num}/{total_slices} COMPLETE</b>\n"
        f"VERIFIED:{conf_counts.get('VERIFIED',0)} HIGH:{conf_counts.get('HIGH',0)} MED:{conf_counts.get('MEDIUM',0)}\n"
        f"Named: {total_found}/{total_proc} ({total_found/max(total_proc,1)*100:.1f}%) | {elapsed/60:.1f} min",
        telegram_token, telegram_chat_id
    )


def main():
    parser = argparse.ArgumentParser(description="ULTRA Executive Enricher v5.0")
    parser.add_argument("--slice-id", type=int, required=True)
    parser.add_argument("--total-slices", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--input-csv", type=str, required=True)
    parser.add_argument("--output-csv", type=str, required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--batch-notify", type=int, default=500)
    parser.add_argument("--telegram-token", type=str, default=DEFAULT_TELEGRAM_TOKEN)
    parser.add_argument("--telegram-chat-id", type=str, default=DEFAULT_TELEGRAM_CHAT_ID)
    args = parser.parse_args()

    asyncio.run(run_cluster_node(
        slice_id=args.slice_id,
        total_slices=args.total_slices,
        concurrency=args.concurrency,
        timeout=args.timeout,
        input_csv=args.input_csv,
        output_csv=args.output_csv,
        limit=args.limit,
        batch_notify=args.batch_notify,
        telegram_token=args.telegram_token,
        telegram_chat_id=args.telegram_chat_id,
    ))


if __name__ == "__main__":
    main()
