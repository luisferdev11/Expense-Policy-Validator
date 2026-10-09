# %% [markdown]
# # 03 · Synthetic dev set (DRAFT)
#
# Two files, written **from the taxonomy and the policy text only**, never from the receipts:
#
# - `dev_items_draft.jsonl`: single line items with a proposed category, for comparing classifier
#   variants. Every label is a **DRAFT** proposed by the assistant; Luis verifies them by hand.
# - `engine_cases_draft.jsonl`: one synthetic receipt per policy-engine edge case, with the
#   exceptions, review signals and disposition the policy text implies.
#
# The only contact with `receipts.jsonl` is the contamination check at the end: real
# `description_raw` values are loaded through the label-stripping helper and compared with each
# synthetic description (difflib ratio, threshold 0.85). Real descriptions are never printed.

# %%
from __future__ import annotations

import difflib
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

REPO = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "data" / "policy-docs").is_dir())
EXP = REPO / "explorations"
sys.path.insert(0, str(EXP / "lib"))
from receipts_safe import assert_clean, load_inputs

TAX_TEXT = (REPO / "data" / "category-taxonomy.md").read_text()
TAXONOMY = {c: r == "yes" for c, r in re.findall(r"^\| `([a-z_]+)` \| (yes|no) \|", TAX_TEXT, re.M)}
print(len(TAXONOMY), "categories,", sum(TAXONOMY.values()), "restricted")

# %% [markdown]
# ## The items
#
# Each row: description, language, merchant, MCC, proposed category, rationale, and a `trap` tag
# when the item is built to catch keyword matching ("names lie") or sits on a category boundary.
# The six traps the taxonomy and policies name are all here, each with adversarial variants in
# other languages. Rationales marked *debatable* are the labels Luis should look at first.

# %%
ITEMS = [
    # alcohol
    (
        "House Cabernet Sauvignon by the glass",
        "en",
        "Copperline Bistro",
        5812,
        "alcohol",
        "Wine served by the glass is alcohol.",
        "",
    ),
    (
        "Shaoxing cooking wine, 750 ml bottle",
        "en",
        "Lucky Harvest Market",
        5411,
        "alcohol",
        "Cooking wine is still alcohol; the taxonomy names it explicitly.",
        "named:cooking wine",
    ),
    (
        "Corkage charge for one bottle we brought",
        "en",
        "Trattoria Lume",
        5812,
        "alcohol",
        "The taxonomy lists corkage under alcohol although it reads like a fee.",
        "boundary:service_fee",
    ),
    (
        "Moscow Mule cocktail with vodka, ginger beer and lime",
        "en",
        "The Oak Barrel Lounge",
        5813,
        "alcohol",
        "The cocktail itself contains vodka; contrast with the Moscow Mule mug.",
        "variant:moscow mule",
    ),
    (
        "Copa de vino tinto Rioja crianza",
        "es",
        "Taberna El Olivo",
        5812,
        "alcohol",
        "A glass of red wine.",
        "",
    ),
    (
        "Pils vom Fass, 0,4 Liter",
        "de",
        "Brauhaus am Markt",
        5813,
        "alcohol",
        "Draught lager beer.",
        "",
    ),
    (
        "Caipirinha de limão com cachaça",
        "pt",
        "Boteco Jardim",
        5813,
        "alcohol",
        "Cocktail made with cachaça, a spirit.",
        "",
    ),
    (
        "生ビール 中ジョッキ 2杯",
        "ja",
        "居酒屋さくら",
        5812,
        "alcohol",
        "Two mugs of draught beer.",
        "",
    ),
    (
        "本みりん 500ml 瓶",
        "ja",
        "スーパーマルヤ",
        5411,
        "alcohol",
        "Hon-mirin is a seasoning with about 14% alcohol, sold like cooking wine. Labelled alcohol for consistency with the cooking-wine rule. Debatable.",
        "variant:cooking wine",
    ),
    # food_beverage
    (
        "Beer-battered haddock with chips and peas",
        "en",
        "The Anchor Pub",
        5812,
        "food_beverage",
        "Food prepared with beer is food (policy note on identification).",
        "named:beer-battered",
    ),
    (
        "Slice of rum cake with whipped cream",
        "en",
        "Island Breeze Cafe",
        5812,
        "food_beverage",
        "Dessert made with rum is food (policy note on identification).",
        "named:rum cake",
    ),
    (
        "Arnold Palmer (half iced tea, half lemonade), large",
        "en",
        "Sunbelt Diner",
        5812,
        "food_beverage",
        "Non-alcoholic mixed drink; the taxonomy names it.",
        "named:arnold palmer",
    ),
    (
        "Virgin mojito with fresh mint and soda, tall glass",
        "en",
        "Copperline Bistro",
        5812,
        "food_beverage",
        "Non-alcoholic cocktail; the policy names it.",
        "named:mojito",
    ),
    (
        "Bourbon-glazed salmon fillet with rice",
        "en",
        "Copperline Bistro",
        5812,
        "food_beverage",
        "A cooked dish with a bourbon glaze is food.",
        "variant:cooked with alcohol",
    ),
    (
        "Boxed lunch catering for 8 people, sandwiches and fruit",
        "en",
        "Fresh Fold Catering",
        5812,
        "food_beverage",
        "Catering is food and beverage.",
        "",
    ),
    (
        "Coq au vin, gratin dauphinois",
        "fr",
        "Bistrot du Marché",
        5812,
        "food_beverage",
        "Chicken braised in wine; a cooked dish, not alcohol.",
        "variant:cooked with alcohol",
    ),
    (
        "Schwarzwälder Kirschtorte, ein Stück",
        "de",
        "Café Sommer",
        5812,
        "food_beverage",
        "Black Forest cake contains kirsch but is a dessert.",
        "variant:rum cake",
    ),
    (
        "Alkoholfreies Weißbier 0,5 l",
        "de",
        "Brauhaus am Markt",
        5813,
        "food_beverage",
        "Alcohol-free wheat beer is a non-alcoholic drink.",
        "variant:non-alcoholic",
    ),
    (
        "Mojito sin alcohol con hierbabuena",
        "es",
        "Taberna El Olivo",
        5812,
        "food_beverage",
        "Virgin mojito in Spanish.",
        "variant:mojito",
    ),
    (
        "Tarta de ron casera, porción",
        "es",
        "Café Malecón",
        5812,
        "food_beverage",
        "Rum cake in Spanish; a dessert.",
        "variant:rum cake",
    ),
    (
        "Cerveja sem álcool long neck",
        "pt",
        "Boteco Jardim",
        5813,
        "food_beverage",
        "Alcohol-free beer is a non-alcoholic drink.",
        "variant:non-alcoholic",
    ),
    ("味噌ラーメン 大盛り", "ja", "ラーメン一番", 5812, "food_beverage", "Miso ramen, a meal.", ""),
    (
        "ノンアルコールビール 瓶",
        "ja",
        "居酒屋さくら",
        5812,
        "food_beverage",
        "Non-alcoholic beer.",
        "variant:non-alcoholic",
    ),
    (
        "奈良漬 盛り合わせ",
        "ja",
        "割烹みやこ",
        5812,
        "food_beverage",
        "Vegetables pickled in sake lees; a food. Debatable only for a keyword matcher.",
        "variant:cooked with alcohol",
    ),
    # household_goods
    (
        "Copper Moscow Mule mug, set of two",
        "en",
        "Home & Hearth",
        5311,
        "household_goods",
        "Drinkware is household goods; the taxonomy names it.",
        "named:moscow mule",
    ),
    (
        "Liquid laundry detergent, 2 litre bottle",
        "en",
        "Lucky Harvest Market",
        5411,
        "household_goods",
        "Laundry products are household goods (HOUSE-01), not laundry_service.",
        "boundary:laundry_service",
    ),
    (
        "Stemless wine glasses, set of four",
        "en",
        "Home & Hearth",
        5311,
        "household_goods",
        "Drinkware, not wine.",
        "variant:drinkware",
    ),
    (
        "Corkscrew and bottle opener combo",
        "en",
        "Home & Hearth",
        5311,
        "household_goods",
        "Barware is household goods (policy note on identification).",
        "variant:drinkware",
    ),
    (
        "Glühweintasse mit Weihnachtsmotiv",
        "de",
        "Weihnachtsmarkt Stand 12",
        5999,
        "household_goods",
        "A mulled-wine mug is drinkware.",
        "variant:moscow mule",
    ),
    # personal_care
    (
        "Men's haircut and beard trim",
        "en",
        "Clip Joint Barbers",
        7230,
        "personal_care",
        "Haircut (PERS-01).",
        "",
    ),
    (
        "Hot stone massage, 90 min, back and shoulders",
        "en",
        "Serenity Day Spa",
        7297,
        "personal_care",
        "Massage (PERS-01).",
        "",
    ),
    (
        "Rasierklingen, Packung mit 4 Stück",
        "de",
        "Drogerie Lindner",
        5912,
        "personal_care",
        "Razor blades (PERS-01).",
        "",
    ),
    (
        "Escova de dentes macia",
        "pt",
        "Farmácia Central",
        5912,
        "personal_care",
        "Toothbrush, a toiletry.",
        "",
    ),
    (
        "Crème solaire SPF 50, 200 ml",
        "fr",
        "Pharmacie du Port",
        5912,
        "personal_care",
        "Sunscreen as a toiletry or cosmetic. Debatable: some would call it health_otc.",
        "boundary:health_otc",
    ),
    # clothing
    (
        "Silk necktie, navy stripe",
        "en",
        "Harbor Menswear",
        5611,
        "clothing",
        "Ties are named in PERS-02.",
        "",
    ),
    (
        "Black leather dress belt",
        "en",
        "Harbor Menswear",
        5611,
        "clothing",
        "Belts are named in PERS-02.",
        "",
    ),
    (
        "Leather laptop messenger bag",
        "en",
        "Harbor Menswear",
        5611,
        "clothing",
        "Bags are fashion accessories in the taxonomy even when they carry a laptop. Debatable.",
        "boundary:computer_accessory",
    ),
    ("Chemise blanche en coton", "fr", "Galeries Lumière", 5311, "clothing", "A shirt.", ""),
    ("Meias sociais, 3 pares", "pt", "Loja Central", 5311, "clothing", "Dress socks.", ""),
    # personal_electronics
    (
        "Wireless noise-cancelling headphones",
        "en",
        "TechHub",
        5732,
        "personal_electronics",
        "Headphones (TECH-01).",
        "",
    ),
    (
        "Smartwatch with fitness tracking, 44 mm",
        "en",
        "TechHub",
        5732,
        "personal_electronics",
        "Smart watch (TECH-01); contrast with the analog watch.",
        "boundary:jewelry",
    ),
    (
        "Charger for e-reader",
        "en",
        "TechHub",
        5732,
        "personal_electronics",
        "An accessory made for a personal device counts as personal electronics.",
        "boundary:computer_accessory",
    ),
    (
        "Funda para tableta de 11 pulgadas",
        "es",
        "Electrónica Sur",
        5732,
        "personal_electronics",
        "A case made for a tablet.",
        "boundary:computer_accessory",
    ),
    (
        "ワイヤレスイヤホン ノイズキャンセリング",
        "ja",
        "デンキ堂",
        5732,
        "personal_electronics",
        "Wireless earbuds.",
        "",
    ),
    # jewelry
    (
        "Analog stainless steel wristwatch",
        "en",
        "Fairfield Jewelers",
        5944,
        "jewelry",
        "A non-electronic watch is jewelry; contrast with the smartwatch.",
        "boundary:personal_electronics",
    ),
    (
        "Sterling silver bracelet for a client",
        "en",
        "Fairfield Jewelers",
        5944,
        "jewelry",
        "Category is what it is; gift rules also apply because of the purpose.",
        "boundary:gift",
    ),
    (
        "Gold-plated cufflinks",
        "en",
        "Harbor Menswear",
        5611,
        "jewelry",
        "Cufflinks are a metal jewelry item. Debatable: could be read as a fashion accessory (clothing).",
        "boundary:clothing",
    ),
    ("Pulseira de prata 925", "pt", "Joalheria Brilho", 5944, "jewelry", "Silver bracelet.", ""),
    # gift
    (
        "Flower bouquet delivered to client office",
        "en",
        "Bloom & Stem",
        5992,
        "gift",
        "Flowers are made to be given.",
        "",
    ),
    (
        "Gourmet gift basket for prospect",
        "en",
        "Harvest Hampers",
        5499,
        "gift",
        "Gift baskets are named in the taxonomy.",
        "",
    ),
    (
        "Handwritten thank-you card with envelope for client",
        "en",
        "Paper Lantern Cards",
        5947,
        "gift",
        "Greeting cards are named in the taxonomy.",
        "",
    ),
    (
        "Boxed chocolates gift set for client",
        "en",
        "Chocolatier Rue",
        5441,
        "gift",
        "Packaged to be given. Debatable: chocolate is food, but the item is made to be given.",
        "boundary:food_beverage",
    ),
    (
        "菓子折り 取引先へ",
        "ja",
        "和菓子松屋",
        5441,
        "gift",
        "Kashiori: a box of sweets made to be given to a business partner.",
        "boundary:food_beverage",
    ),
    # gift_card
    (
        "$50 bookstore gift card",
        "en",
        "Riverside Books",
        5942,
        "gift_card",
        "Gift card (GIFT-02).",
        "",
    ),
    (
        "Prepaid Visa card, $100 load",
        "en",
        "QuickMart",
        5499,
        "gift_card",
        "Prepaid card (GIFT-02).",
        "",
    ),
    (
        "Spa voucher for two people",
        "en",
        "Serenity Day Spa",
        7297,
        "gift_card",
        "A voucher is a cash equivalent, not personal care.",
        "boundary:personal_care",
    ),
    (
        "ギフトカード 5,000円分",
        "ja",
        "コンビニ東口店",
        5499,
        "gift_card",
        "Gift card in Japanese.",
        "",
    ),
    (
        "Gutschein Restaurant, Wert 50 €",
        "de",
        "Restaurant Linde",
        5812,
        "gift_card",
        "A voucher sold by a restaurant is still a cash equivalent.",
        "boundary:food_beverage",
    ),
    # tobacco
    ("Premium cigars, box of 5", "en", "Smoke & Leaf", 5993, "tobacco", "Cigars (PERS-03).", ""),
    (
        "Nicotine vape pods, mint, 4-pack",
        "en",
        "Smoke & Leaf",
        5993,
        "tobacco",
        "Vaping product (PERS-03).",
        "",
    ),
    ("Paquet de cigarettes", "fr", "Tabac de la Gare", 5993, "tobacco", "Cigarettes.", ""),
    (
        "Drehtabak, 30 g Beutel",
        "de",
        "Kiosk am Bahnhof",
        5994,
        "tobacco",
        "Loose rolling tobacco.",
        "",
    ),
    # gambling
    ("Casino chips, $200", "en", "Silver Star Casino", 7995, "gambling", "Casino chips.", ""),
    ("Sports betting stake, match winner", "en", "BetLine", 7995, "gambling", "Betting stake.", ""),
    (
        "Bilhete de loteria federal",
        "pt",
        "Lotérica Central",
        7995,
        "gambling",
        "Lottery ticket.",
        "",
    ),
    # computer_accessory
    (
        "DisplayPort to VGA converter for projector",
        "en",
        "TechHub",
        5732,
        "computer_accessory",
        "Adapter (TECH-02).",
        "",
    ),
    (
        "Ultrawide curved display, 34 inch, for laptop",
        "en",
        "TechHub",
        5732,
        "computer_accessory",
        "Monitor (TECH-02).",
        "",
    ),
    (
        "Thunderbolt 4 docking station, 11 ports",
        "en",
        "TechHub",
        5732,
        "computer_accessory",
        "Docking station (TECH-02).",
        "",
    ),
    (
        "USB-C-Kabel für Laptop, 2 m",
        "de",
        "Elektro Weber",
        5732,
        "computer_accessory",
        "Laptop cable.",
        "",
    ),
    (
        "ノートパソコンスタンド アルミ製",
        "ja",
        "デンキ堂",
        5732,
        "computer_accessory",
        "Laptop stand (TECH-02).",
        "",
    ),
    # office_supplies
    (
        "A4 printer paper, 5 reams",
        "en",
        "Paperline Office Supply",
        5943,
        "office_supplies",
        "Stationery.",
        "",
    ),
    (
        "Overnight courier envelope to client",
        "en",
        "ShipFast",
        4215,
        "office_supplies",
        "Shipping is listed under office_supplies.",
        "",
    ),
    (
        "Cuaderno A5 de tapa dura",
        "es",
        "Papelería Central",
        5943,
        "office_supplies",
        "Notebook.",
        "",
    ),
    ("Impression couleur, 50 pages", "fr", "Copy Plus", 7338, "office_supplies", "Printing.", ""),
    # lodging
    (
        "Standard double room, one night stay",
        "en",
        "Harborview Hotel",
        7011,
        "lodging",
        "Room charge.",
        "",
    ),
    (
        "Resort fee per night",
        "en",
        "Harborview Hotel",
        7011,
        "lodging",
        "Resort fees are named under lodging.",
        "boundary:service_fee",
    ),
    (
        "Taxe de séjour, 2 nuits",
        "fr",
        "Hôtel des Arts",
        7011,
        "lodging",
        "Tourist tax on a hotel stay.",
        "",
    ),
    (
        "宿泊料 1泊 朝食付き",
        "ja",
        "ビジネスホテル東",
        7011,
        "lodging",
        "One night with breakfast. Debatable: breakfast bundled into the room rate.",
        "boundary:food_beverage",
    ),
    # ground_transport
    ("Airport taxi to downtown", "en", "Metro Cab Co", 4121, "ground_transport", "Taxi.", ""),
    ("Parking garage, 4 hours", "en", "CityPark", 7523, "ground_transport", "Parking.", ""),
    (
        "Taxi al aeropuerto",
        "es",
        "Radio Taxi Sevilla",
        4121,
        "ground_transport",
        "Taxi in Spanish.",
        "",
    ),
    (
        "Bahnfahrkarte München–Berlin, 2. Klasse",
        "de",
        "Bahnreisezentrum",
        4112,
        "ground_transport",
        "Train ticket; transit.",
        "",
    ),
    (
        "Bilhete de metrô, ida e volta",
        "pt",
        "Metrô Linha Azul",
        4111,
        "ground_transport",
        "Metro ticket.",
        "",
    ),
    # airfare
    ("Economy ticket SFO to ORD", "en", "SkyWays Air", 4511, "airfare", "Air ticket.", ""),
    (
        "Checked bag fee, first bag",
        "en",
        "SkyWays Air",
        4511,
        "airfare",
        "Bag fees are named under airfare.",
        "boundary:service_fee",
    ),
    (
        "Seat selection, extra legroom",
        "en",
        "SkyWays Air",
        4511,
        "airfare",
        "Seat fees are named under airfare.",
        "",
    ),
    (
        "Billet d'avion Paris–Lyon",
        "fr",
        "Air Horizon",
        4511,
        "airfare",
        "Air ticket in French.",
        "",
    ),
    # laundry_service
    (
        "Dry clean and press two business suits",
        "en",
        "Prestige Cleaners",
        7216,
        "laundry_service",
        "Dry cleaning.",
        "",
    ),
    (
        "Shirt pressing, 5 shirts",
        "en",
        "Harborview Hotel",
        7011,
        "laundry_service",
        "Pressing at a hotel is still laundry service.",
        "",
    ),
    (
        "Pressing d'un costume",
        "fr",
        "Pressing Saint-Michel",
        7216,
        "laundry_service",
        "Pressing in French.",
        "",
    ),
    (
        "クリーニング ワイシャツ 3枚",
        "ja",
        "ビジネスホテル東",
        7011,
        "laundry_service",
        "Shirt cleaning at a hotel.",
        "",
    ),
    # health_otc
    (
        "Acetaminophen 500 mg caplets, 30 count",
        "en",
        "CityCare Pharmacy",
        5912,
        "health_otc",
        "OTC medication.",
        "",
    ),
    (
        "Cough and throat lozenges, honey",
        "en",
        "CityCare Pharmacy",
        5912,
        "health_otc",
        "Lozenges are named under health_otc.",
        "",
    ),
    (
        "Nicotine gum 2 mg, 20 pieces",
        "en",
        "CityCare Pharmacy",
        5912,
        "health_otc",
        "Nicotine replacement is OTC medication, not tobacco. Debatable.",
        "boundary:tobacco",
    ),
    (
        "Ibuprofeno 400 mg, 20 comprimidos",
        "es",
        "Farmacia San Juan",
        5912,
        "health_otc",
        "OTC medication in Spanish.",
        "",
    ),
    ("胃腸薬 錠剤", "ja", "ドラッグストア中央", 5912, "health_otc", "OTC stomach medicine.", ""),
    # software_subscription
    (
        "Video conferencing Pro plan, annual",
        "en",
        "MeetSpace Inc.",
        5734,
        "software_subscription",
        "SaaS subscription.",
        "",
    ),
    (
        "IDE license, 1 user, 1 year",
        "en",
        "CodeForge Tools",
        5734,
        "software_subscription",
        "Software licence.",
        "",
    ),
    (
        "Assinatura anual de antivírus",
        "pt",
        "SegurNet",
        5734,
        "software_subscription",
        "Antivirus subscription.",
        "",
    ),
    (
        "Cloud-Speicher Jahresabo 2 TB",
        "de",
        "Wolkenspeicher GmbH",
        5734,
        "software_subscription",
        "Cloud storage subscription.",
        "",
    ),
    # service_fee
    (
        "Tip added by card at the table",
        "en",
        "Copperline Bistro",
        5812,
        "service_fee",
        "Gratuity.",
        "",
    ),
    (
        "Propina para el mesero",
        "es",
        "Taberna El Olivo",
        5812,
        "service_fee",
        "Tip in Spanish.",
        "",
    ),
    (
        "Service compris 15 %",
        "fr",
        "Bistrot du Marché",
        5812,
        "service_fee",
        "Service charge in French.",
        "",
    ),
    ("サービス料 10%", "ja", "割烹みやこ", 5812, "service_fee", "Service charge in Japanese.", ""),
    # other
    (
        "Concert ticket, floor standing",
        "en",
        "LiveHall Box Office",
        7922,
        "other",
        "Event tickets have no category; the taxonomy says use other.",
        "boundary:policy-only item",
    ),
    (
        "Smartphone 128 GB, unlocked",
        "en",
        "TechHub",
        5732,
        "other",
        "Mobile phones have no category (TECH-03); the taxonomy says use other, not personal_electronics.",
        "boundary:personal_electronics",
    ),
    (
        "Prescription antibiotics, amoxicillin 500 mg",
        "en",
        "CityCare Pharmacy",
        5912,
        "other",
        "Prescription medication has no category; the taxonomy says use other.",
        "boundary:health_otc",
    ),
    (
        "Visa application fee",
        "en",
        "Consular Services Center",
        9399,
        "other",
        "Government fee; fits nothing above.",
        "",
    ),
    (
        "Total charge, items not listed",
        "en",
        "Grand Market",
        5411,
        "other",
        "A non-itemized charge is other by definition (EXC-03).",
        "",
    ),
]
print(len(ITEMS), "items")

# %%
rows = []
for n, (desc, lang, merchant, mcc, cat, why, trap) in enumerate(ITEMS, start=1):
    assert cat in TAXONOMY, cat
    rows.append(
        {
            "item_id": f"DEV-{n:03d}",
            "description": desc,
            "language": lang,
            "merchant_name": merchant,
            "mcc": mcc,
            "proposed_category": cat,
            "restricted": TAXONOMY[cat],
            "rationale": why,
            "trap": trap or None,
            "status": "DRAFT",
        }
    )
D = pd.DataFrame(rows)
print(
    "categories covered:",
    D["proposed_category"].nunique(),
    "of",
    len(TAXONOMY),
    "| missing:",
    sorted(set(TAXONOMY) - set(D["proposed_category"])) or "none",
)
print("languages:", D["language"].value_counts().to_dict())
print("restricted items:", int(D["restricted"].sum()), "of", len(D))
D["proposed_category"].value_counts().rename("items per category").to_frame().T

# %%
NAMED_TRAPS = [
    "beer-battered",
    "rum cake",
    "arnold palmer",
    "mojito",
    "moscow mule",
    "cooking wine",
]
text = " ".join(D["description"].str.lower())
print("named traps present:", {t: t in text for t in NAMED_TRAPS})
print("items tagged as trap or boundary:", int(D["trap"].notna().sum()))
D[D["trap"].notna()][["item_id", "description", "language", "proposed_category", "trap"]]

# %% [markdown]
# ## Contamination check against the real descriptions
#
# For every synthetic description, the highest difflib ratio against any real `description_raw`
# (both lowercased). Real descriptions are loaded with the label-stripping helper and **never
# printed**: only the synthetic item ID and its score are shown. Anything at or above 0.85 must be
# rewritten.

# %%
real = load_inputs()
assert_clean(real)
real_desc = [i["description_raw"].lower() for r in real for i in r["line_items"]]
D["max_similarity"] = [
    max(difflib.SequenceMatcher(None, d.lower(), x).ratio() for x in real_desc)
    for d in D["description"]
]
over = D[D["max_similarity"] >= 0.85]
print(f"compared {len(D)} synthetic items with {len(real_desc)} real descriptions")
print(
    "worst similarity:",
    round(D["max_similarity"].max(), 3),
    "| items at or above 0.85:",
    list(over["item_id"]) or "none",
)
D.sort_values("max_similarity", ascending=False)[
    ["item_id", "language", "proposed_category", "max_similarity"]
].head(10)

# %%
assert over.empty, "rewrite the items above before freezing"
with (EXP / "dev_set" / "dev_items_draft.jsonl").open("w") as fh:
    for row in rows:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
sha = hashlib.sha256((EXP / "dev_set" / "dev_items_draft.jsonl").read_bytes()).hexdigest()
print("wrote", len(rows), "items; dev_items_draft.jsonl SHA-256:", sha)

# %% [markdown]
# ## Engine edge cases
#
# One synthetic receipt per edge case. The receipt carries the same input fields as the real
# data, and its line items carry the category, restricted flag and confidence **as the classifier
# would hand them to the engine**, so each case tests the engine alone. Expected exceptions,
# review signals and disposition are my reading of the policy text (DRAFT). The disposition is
# derived from them with EXC-01 in code, never typed.


# %%
def receipt(
    rid,
    *,
    employee="E-9001",
    country="US",
    entity="GLOBAL",
    etype,
    merchant,
    mcc,
    mcc_desc,
    when="2026-05-12T19:30:00",
    ccy="USD",
    fx=1.0,
    attendees=None,
    trip=None,
    nights=None,
    ref=None,
    itemized=True,
    lines=(),
):
    items = []
    for k, (desc, lang, qty, unit, cat, conf) in enumerate(lines, start=1):
        amount = round(qty * unit, 2)
        items.append(
            {
                "line_id": f"{rid}-L{k}",
                "description_raw": desc,
                "language": lang,
                "quantity": qty,
                "unit_price": unit,
                "amount": amount,
                "amount_usd": round(amount * fx, 2),
                "category": cat,
                "restricted": TAXONOMY[cat],
                "confidence": conf,
            }
        )
    total = round(sum(i["amount"] for i in items), 2)
    return {
        "receipt_id": rid,
        "employee_id": employee,
        "employee_country": country,
        "entity": entity,
        "submitted_expense_type": etype,
        "merchant_name": merchant,
        "mcc": mcc,
        "mcc_description": mcc_desc,
        "transaction_datetime": when,
        "currency": ccy,
        "fx_rate_to_usd": fx,
        "total_amount": total,
        "total_amount_usd": round(total * fx, 2),
        "attendee_count": attendees,
        "trip_id": trip,
        "trip_nights": nights,
        "pre_approval_ref": ref,
        "itemized": itemized,
        "line_items": items,
    }


CASES = [
    dict(
        edge_case="apac_alcohol_override",
        receipt=receipt(
            "SYN-01",
            employee="E-9101",
            country="JP",
            entity="APAC",
            etype="Client Entertainment",
            merchant="Ginza Kappo Hana",
            mcc=5812,
            mcc_desc="Eating places and restaurants",
            ccy="JPY",
            fx=0.0067,
            attendees=4,
            trip="TRIP-9101",
            nights=3,
            lines=[
                ("懐石コース 4名", "ja", 1, 20000, "food_beverage", 0.97),
                ("赤ワイン ボトル", "ja", 1, 8000, "alcohol", 0.96),
            ],
        ),
        expected_exceptions=[{"rule_id": "REG-01", "severity": "high", "line_ids": ["SYN-01-L2"]}],
        expected_review_signals=[],
        justification_quote="For APAC employees REG-01 replaces ALC-01, ALC-02 and ALC-03: report REG-01 instead of those three.",
        why="L1 ¥20,000 + L2 ¥8,000 = ¥28,000 x 0.0067 = $187.60; / 4 = $46.90 <= $60 (no REG-02). L2 alcohol + entity APAC -> REG-01 high on L2; ALC-01/02 not reported.",
    ),
    dict(
        edge_case="regional_meal_cap",
        receipt=receipt(
            "SYN-02",
            employee="E-9102",
            country="DE",
            entity="EMEA",
            etype="Meals - Individual",
            merchant="Gasthaus Krone",
            mcc=5812,
            mcc_desc="Eating places and restaurants",
            ccy="EUR",
            fx=1.08,
            trip="TRIP-9102",
            nights=2,
            lines=[
                ("Rinderfilet mit Beilagen", "de", 1, 62.0, "food_beverage", 0.97),
                ("Apfelschorle", "de", 2, 4.5, "food_beverage", 0.95),
                ("Dessertvariation", "de", 1, 14.0, "food_beverage", 0.95),
            ],
        ),
        expected_exceptions=[
            {"rule_id": "REG-03", "severity": "medium", "line_ids": []},
            {"rule_id": "REG-04", "severity": "low", "line_ids": []},
        ],
        expected_review_signals=[],
        justification_quote="A breach is a medium exception, reported as REG-03, not MEAL-01.",
        why="EUR 85 x 1.08 = $91.80 per head (1 person) > EUR 70 x 1.08 = $75.60 -> REG-03 medium (MEAL-01 not reported). EUR 85 > EUR 50, VAT number absent -> REG-04 low.",
    ),
    dict(
        edge_case="government_official_gift",
        receipt=receipt(
            "SYN-03",
            employee="E-9103",
            etype="Client Entertainment",
            merchant="Capitol Steakhouse",
            mcc=5812,
            mcc_desc="Eating places and restaurants",
            attendees=2,
            lines=[
                (
                    "Dinner: Vice-Minister Ortega (Ministry of Trade) + me",
                    "en",
                    1,
                    90.0,
                    "food_beverage",
                    0.93,
                ),
                ("Gratuity", "en", 1, 18.0, "service_fee", 0.99),
            ],
        ),
        expected_exceptions=[
            {"rule_id": "GIFT-04", "severity": "critical", "line_ids": ["SYN-03-L1"]}
        ],
        expected_review_signals=[],
        justification_quote="Gifts, meals, or anything of value provided to a government official, public employee, or state-owned enterprise employee are prohibited",
        why="L1 provided to an official -> GIFT-04 critical, cites L1 only; L2 (tip) excluded per EXC-04. Meal: $108 / 2 = $54 <= $75.",
    ),
    dict(
        edge_case="reference_kind",
        receipt=receipt(
            "SYN-04",
            employee="E-9104",
            etype="Software",
            merchant="MeetSpace Inc.",
            mcc=5734,
            mcc_desc="Computer software stores",
            ref="PA-2026-0777",
            trip=None,
            lines=[
                (
                    "Video conferencing Business plan, annual",
                    "en",
                    1,
                    180.0,
                    "software_subscription",
                    0.98,
                )
            ],
        ),
        expected_exceptions=[{"rule_id": "TECH-04", "severity": "low", "line_ids": ["SYN-04-L1"]}],
        expected_review_signals=[],
        justification_quote="provided it is the kind the rule asks for: a pre-approval for TECH-02, a VP approval for ENT-01, a manager approval for TECH-04",
        why="ref prefix PA- = pre-approval kind; TECH-04 needs manager-approval kind -> TECH-04 low on L1.",
    ),
    dict(
        edge_case="tech02_unit_price",
        receipt=receipt(
            "SYN-05",
            employee="E-9105",
            etype="Computer Equipment",
            merchant="Paperline Office Supply",
            mcc=5943,
            mcc_desc="Office and stationery supply",
            lines=[
                ("24-inch monitor", "en", 2, 160.0, "computer_accessory", 0.97),
                ("Dock, USB-C, 2 screens", "en", 1, 249.0, "computer_accessory", 0.97),
            ],
        ),
        expected_exceptions=[
            {"rule_id": "TECH-02", "severity": "medium", "line_ids": ["SYN-05-L2"]}
        ],
        expected_review_signals=[],
        justification_quote="judged on the item's unit price in USD",
        why="L1 unit $160 <= $200 (line total $320 irrelevant); L2 unit $249 > $200, ref null -> TECH-02 medium on L2.",
    ),
    dict(
        edge_case="gratuity_excluded_from_line_ids",
        receipt=receipt(
            "SYN-06",
            employee="E-9106",
            etype="Meals - Individual",
            merchant="Northgate Grill",
            mcc=5812,
            mcc_desc="Eating places and restaurants",
            trip="TRIP-9106",
            nights=2,
            lines=[
                ("Cheeseburger and fries", "en", 1, 18.0, "food_beverage", 0.98),
                ("Pint of IPA", "en", 1, 8.0, "alcohol", 0.97),
                ("Tip", "en", 1, 5.0, "service_fee", 0.99),
            ],
        ),
        expected_exceptions=[{"rule_id": "ALC-01", "severity": "high", "line_ids": ["SYN-06-L2"]}],
        expected_review_signals=[],
        justification_quote="the items themselves, never a gratuity or service fee charged alongside them.",
        why="Meals - Individual + L2 alcohol -> ALC-01 high, line_ids [L2]; L3 tip excluded. Meal $31 <= $75.",
    ),
    dict(
        edge_case="meal01_cross_receipt_day",
        receipt=receipt(
            "SYN-07",
            employee="E-9107",
            etype="Meals - Individual",
            merchant="Midtown Deli",
            mcc=5812,
            mcc_desc="Eating places and restaurants",
            when="2026-05-14T12:40:00",
            trip="TRIP-9107",
            nights=3,
            lines=[("Club sandwich and iced tea", "en", 1, 40.0, "food_beverage", 0.98)],
        ),
        related_receipts=[
            receipt(
                "SYN-07B",
                employee="E-9107",
                etype="Meals - Individual",
                merchant="Harbor Fish House",
                mcc=5812,
                mcc_desc="Eating places and restaurants",
                when="2026-05-14T20:10:00",
                trip="TRIP-9107",
                nights=3,
                lines=[
                    ("Grilled sea bass", "en", 1, 42.0, "food_beverage", 0.98),
                    ("Lemonade", "en", 2, 4.0, "food_beverage", 0.97),
                ],
            )
        ],
        expected_exceptions=[{"rule_id": "MEAL-01", "severity": "medium", "line_ids": []}],
        expected_review_signals=[],
        justification_quote="When a day's total is over the cap, raise MEAL-01 on every meal receipt that contributes to that day.",
        why="Same employee, same date: $40 (SYN-07) + $50 (SYN-07B) = $90 > $75 domestic -> MEAL-01 medium on both; this row is SYN-07.",
    ),
    dict(
        edge_case="health01_per_trip",
        receipt=receipt(
            "SYN-08",
            employee="E-9108",
            etype="Travel - Other",
            merchant="CityCare Pharmacy",
            mcc=5912,
            mcc_desc="Drug stores and pharmacies",
            when="2026-05-20T09:15:00",
            trip="TRIP-9108",
            nights=5,
            lines=[("Ibuprofen 200 mg, 50 tablets", "en", 1, 15.0, "health_otc", 0.97)],
        ),
        related_receipts=[
            receipt(
                "SYN-08B",
                employee="E-9108",
                etype="Travel - Other",
                merchant="Airport Pharmacy Express",
                mcc=5912,
                mcc_desc="Drug stores and pharmacies",
                when="2026-05-23T18:00:00",
                trip="TRIP-9108",
                nights=5,
                lines=[
                    ("Cold and flu capsules", "en", 1, 9.0, "health_otc", 0.96),
                    ("Throat lozenges", "en", 1, 5.0, "health_otc", 0.97),
                ],
            )
        ],
        expected_exceptions=[
            {"rule_id": "HEALTH-01", "severity": "low", "line_ids": ["SYN-08-L1"]}
        ],
        expected_review_signals=["MCC-02"],
        justification_quote="up to $25 in total across all of that trip's receipts.",
        why="TRIP-9108 OTC: $15 (SYN-08) + $14 (SYN-08B) = $29 > $25 -> HEALTH-01 low, cites L1. MCC 5912 tier medium -> MCC-02. low + signal -> review.",
    ),
    dict(
        edge_case="mcc02_review_signal",
        receipt=receipt(
            "SYN-09",
            employee="E-9109",
            etype="Office Supplies",
            merchant="Lindell Department Store",
            mcc=5311,
            mcc_desc="Department stores",
            lines=[
                ("Spiral notebooks, 3-pack", "en", 1, 9.0, "office_supplies", 0.96),
                ("Ballpoint pens, box of 10", "en", 1, 6.5, "office_supplies", 0.97),
            ],
        ),
        expected_exceptions=[],
        expected_review_signals=["MCC-02"],
        justification_quote="It is not an exception by itself and must never be reported as one",
        why="MCC 5311 tier medium -> MCC-02; L1, L2 office_supplies match Office Supplies; zero exceptions -> review.",
    ),
    dict(
        edge_case="alcohol_retail_scope",
        receipt=receipt(
            "SYN-10",
            employee="E-9110",
            etype="Client Entertainment",
            merchant="FreshWay Supermarket",
            mcc=5411,
            mcc_desc="Grocery stores and supermarkets",
            attendees=3,
            lines=[
                ("Bottle of Chianti", "en", 1, 24.0, "alcohol", 0.97),
                ("Cheese and cracker platter", "en", 1, 12.0, "food_beverage", 0.96),
            ],
        ),
        expected_exceptions=[{"rule_id": "ALC-03", "severity": "high", "line_ids": ["SYN-10-L1"]}],
        expected_review_signals=["MCC-02"],
        justification_quote="Alcohol bought from any other merchant is retail and is governed by ALC-03 alone.",
        why="MCC 5411 not in {5812, 5813, 7011} -> L1 is retail -> ALC-03 high on L1 (ALC-01/02 out of scope). MCC 5411 tier medium -> MCC-02. Meal $36 / 3 = $12.",
    ),
    dict(
        edge_case="doc03_mismatch",
        receipt=receipt(
            "SYN-11",
            employee="E-9111",
            etype="Software",
            merchant="Paperline Office Supply",
            mcc=5943,
            mcc_desc="Office and stationery supply",
            lines=[
                ("Aluminium laptop stand", "en", 1, 45.0, "computer_accessory", 0.97),
                ("Shipping", "en", 1, 6.0, "service_fee", 0.95),
            ],
        ),
        expected_exceptions=[{"rule_id": "DOC-03", "severity": "medium", "line_ids": []}],
        expected_review_signals=[],
        justification_quote="A receipt is misclassified when none of its line items belongs to a category that its declared expense type covers.",
        why="Software covers {software_subscription}; L2 service_fee ignored; L1 computer_accessory not covered -> DOC-03 medium. L1 $45 <= $200 -> no TECH-02.",
    ),
    dict(
        edge_case="exc03_uncertain_item",
        receipt=receipt(
            "SYN-12",
            employee="E-9112",
            etype="Travel - Other",
            merchant="Station Kiosk 4",
            mcc=5994,
            mcc_desc="News dealers and newsstands",
            trip="TRIP-9112",
            nights=2,
            lines=[
                ("Assorted items bag", "en", 1, 22.0, "other", 0.35),
                ("City transit day pass", "en", 1, 8.0, "ground_transport", 0.96),
            ],
        ),
        expected_exceptions=[],
        expected_review_signals=["EXC-03"],
        justification_quote="raise a review signal with rule ID EXC-03 rather than an exception, and leave that item out of every other rule's calculation for the receipt.",
        why="L1 confidence 0.35 < threshold -> EXC-03, L1 removed from DOC-03 and every other rule; L2 ground_transport is covered by Travel - Other.",
    ),
    dict(
        edge_case="exc01_severity_ladder",
        receipt=receipt(
            "SYN-13",
            employee="E-9113",
            etype="Lodging",
            merchant="Harborview Hotel",
            mcc=7011,
            mcc_desc="Hotels, motels, resorts",
            trip="TRIP-9113",
            nights=2,
            lines=[
                ("Room charge, 2 nights", "en", 2, 139.0, "lodging", 0.99),
                ("Laundry service, 4 shirts", "en", 1, 16.0, "laundry_service", 0.98),
            ],
        ),
        expected_exceptions=[
            {"rule_id": "LAUNDRY-01", "severity": "low", "line_ids": ["SYN-13-L2"]}
        ],
        expected_review_signals=[],
        justification_quote="only low exceptions, or only review signals, and no exception above low",
        why="trip_nights 2 < 4 -> LAUNDRY-01 low on L2; only low -> review (EXC-01).",
    ),
]


def exc01(exceptions, signals) -> str:
    sev = {e["severity"] for e in exceptions}
    if sev & {"critical", "high", "medium"}:
        return "flag"
    return "review" if exceptions or signals else "pass"


docs_norm = [
    re.sub(r"\s+", " ", re.sub(r"[*`«»\"“”‘’]", "", t.lower())).strip()
    for t in (p.read_text() for p in (REPO / "data" / "policy-docs").glob("*.md"))
]
out = []
for n, c in enumerate(CASES, start=1):
    q = re.sub(r"\s+", " ", re.sub(r"[*`«»\"“”‘’]", "", c["justification_quote"].lower())).strip()
    assert any(q in d for d in docs_norm), c["edge_case"]
    out.append(
        {
            "case_id": f"CASE-{n:02d}",
            "edge_case": c["edge_case"],
            "receipt": c["receipt"],
            "related_receipts": c.get("related_receipts", []),
            "expected_exceptions": c["expected_exceptions"],
            "expected_review_signals": c["expected_review_signals"],
            "expected_disposition": exc01(c["expected_exceptions"], c["expected_review_signals"]),
            "justification_quote": c["justification_quote"],
            "why": c["why"],
            "status": "DRAFT",
        }
    )
with (EXP / "dev_set" / "engine_cases_draft.jsonl").open("w") as fh:
    for c in out:
        fh.write(json.dumps(c, ensure_ascii=False) + "\n")
print(len(out), "engine cases, every quote verbatim")
pd.DataFrame(
    [
        {
            "case": c["case_id"],
            "edge_case": c["edge_case"],
            "exceptions": ", ".join(
                f"{e['rule_id']}:{e['severity']}" for e in c["expected_exceptions"]
            ),
            "signals": ", ".join(c["expected_review_signals"]),
            "disposition": c["expected_disposition"],
        }
        for c in out
    ]
)

# %% [markdown]
# ## Frozen
#
# The SHA-256 printed above is recorded in the morning report. From here on the DRAFT labels are
# not edited after any model prediction is seen.
