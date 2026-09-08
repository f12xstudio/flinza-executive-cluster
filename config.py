import os

# Flinza Works ICP Configuration
NICHES = {
    "Fashion & Apparel": [
        "Streetwear", "Athleisure", "Denim", "Outerwear", "Casual", 
        "Formal", "Plus-size", "Swimwear", "Loungewear", "Kids apparel"
    ],
    "Fashion Accessories": [
        "Hats & caps", "Bags & handbags", "Belts", "Sunglasses & eyewear",
        "Watches", "Scarves & wraps", "Wallets", "Hair accessories"
    ],
    "Jewelry": [
        "Chains", "Pendants & necklaces", "Rings", "Bracelets", 
        "Earrings", "Lab-grown diamonds", "Natural diamonds", "Men's jewelry", "Custom jewelry"
    ],
    "Health & Supplements": [
        "Vitamins & multivitamins", "Protein & fitness", "Weight management",
        "Collagen & skin", "Sleep & wellness", "Gut health & probiotics", 
        "Energy & pre-workout", "Women's health", "Men's health"
    ],
    "Extended DTC": [
        "Skincare & Beauty", "Pet products", "Home & lifestyle", "Tech accessories",
        "Candles & fragrance", "Outdoor & camping", "Kitchenware"
    ]
}

TARGET_ROLES = [
    "Founder", "Co-Founder", "CEO", "Chief Executive Officer",
    "CMO", "Chief Marketing Officer", "Head of Marketing",
    "VP Marketing", "Marketing Director", "Owner", "Co-Owner"
]

TARGET_COUNTRIES = [
    "United States", "United Kingdom", "Canada", "Australia", 
    "Germany", "France", "Netherlands", "United Arab Emirates"
]

EMPLOYEE_BANDS = ["1-10", "11-50", "51-100"]
REVENUE_BANDS = ["$0–1M", "$1–10M"]

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
VERIFIED_OUTPUT_CSV = os.path.join(DATA_DIR, "flinza_verified_leads.csv")
INSTANTLY_READY_CSV = os.path.join(DATA_DIR, "instantly_upload_ready.csv")
