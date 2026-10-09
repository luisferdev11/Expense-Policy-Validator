"""keyword-classifier baseline: the ItemClassifier port with word lists, no model (FR-032).

Naive on purpose: it matches words, not meaning, like the keyword rules this project replaces
("beer-battered cod" becomes alcohol). Lists were written from the taxonomy's examples plus
generic vocabulary in the six languages, never copied from the receipts; a test checks that no
entry equals a real description. Disclosure: the assistant had seen the descriptions of the six
brief-case receipts while writing them. Categories are tried in a fixed order, restricted first;
anything unmatched is food_beverage at a restaurant, bar or hotel, and other elsewhere.
"""

from __future__ import annotations

import hashlib
import re

from expense_validator.domain.models import Classification, ClassificationSource, ClassifierRequest
from expense_validator.domain.taxonomy import Category, restricted_for

KEYWORD_VERSION = "kw-v1"
ON_PREMISES_MCC = frozenset({5812, 5813, 7011})

KEYWORDS: dict[str, tuple[str, ...]] = {
    "gift_card": ("gift card", "voucher", "prepaid card", "tarjeta regalo", "carte cadeau",
                  "gutschein", "vale-presente", "ギフトカード"),
    "alcohol": ("wine", "beer", "vodka", "whisky", "whiskey", "rum", "gin", "tequila",
                "cocktail", "champagne", "prosecco", "sake", "corkage", "vino", "cerveza",
                "vin", "bière", "biere", "wein", "bier", "vinho", "cerveja", "ワイン", "ビール",
                "日本酒"),
    "tobacco": ("cigarette", "cigarettes", "cigar", "cigars", "tobacco", "vape", "e-liquid",
                "cigarrillos", "tabaco", "tabac", "zigaretten", "tabak", "cigarros", "タバコ"),
    "gambling": ("casino", "poker", "lottery", "betting", "bet", "apuesta", "lotería",
                 "loterie", "lotto", "aposta", "カジノ"),
    "personal_electronics": ("headphones", "earbuds", "tablet", "smartwatch", "smart watch",
                             "fitness tracker", "camera", "drone", "speaker", "e-reader",
                             "auriculares", "écouteurs", "kopfhörer", "fones de ouvido",
                             "イヤホン", "ヘッドホン"),
    "jewelry": ("bracelet", "necklace", "earrings", "jewelry", "pulsera", "collar", "collier",
                "armband", "halskette", "pulseira", "colar", "ネックレス"),
    "gift": ("gift", "flowers", "bouquet", "gift basket", "greeting card", "regalo", "flores",
             "cadeau", "fleurs", "geschenk", "blumen", "presente", "ギフト"),
    "household_goods": ("detergent", "paper towels", "toilet paper", "mug", "cleaning",
                        "bedding", "kitchenware", "detergente", "lessive", "waschmittel",
                        "洗剤"),
    "personal_care": ("shampoo", "toothpaste", "razor", "haircut", "spa", "massage",
                      "cosmetics", "deodorant", "champú", "masaje", "coiffure", "friseur",
                      "massagem", "シャンプー", "マッサージ"),
    "clothing": ("shirt", "socks", "shoes", "jacket", "belt", "tie", "trousers", "camisa",
                 "calcetines", "chemise", "chaussettes", "hemd", "socken", "meias", "シャツ"),
    "service_fee": ("tip", "gratuity", "service charge", "delivery fee", "booking fee",
                    "propina", "pourboire", "trinkgeld", "gorjeta", "サービス料"),
    "computer_accessory": ("cable", "adapter", "dock", "docking", "mouse", "keyboard",
                           "monitor", "hdmi", "usb", "webcam", "laptop stand", "teclado",
                           "câble", "tastatur", "モニター"),
    "office_supplies": ("notebook", "pens", "paper", "printing", "stationery", "stapler",
                        "toner", "cuaderno", "cahier", "papier", "caderno", "ノート"),
    "lodging": ("room", "hotel", "resort fee", "lodging", "habitación", "chambre", "zimmer",
                "quarto", "宿泊"),
    "ground_transport": ("taxi", "uber", "rideshare", "train", "metro", "parking", "fuel",
                         "toll", "bus", "transit", "gasolina", "essence", "bahn", "タクシー"),
    "airfare": ("flight", "airfare", "seat selection", "baggage fee", "vuelo", "vol", "flug",
                "voo", "航空券"),
    "laundry_service": ("laundry", "dry cleaning", "pressing", "lavandería", "blanchisserie",
                        "wäscherei", "reinigung", "lavanderia", "limpeza a seco", "クリーニング"),
    "health_otc": ("ibuprofen", "paracetamol", "aspirin", "lozenges", "antacid", "cold and flu",
                   "ibuprofeno", "pastillas", "médicament", "tabletten", "remédio", "薬"),
    "software_subscription": ("subscription", "license", "licence", "saas", "software",
                              "suscripción", "abonnement", "lizenz", "assinatura"),
    "food_beverage": ("meal", "lunch", "dinner", "breakfast", "tea", "sandwich",
                      "burger", "salad", "water", "juice", "comida", "almuerzo", "cena",
                      "déjeuner", "dîner", "mittagessen", "abendessen", "almoço", "jantar",
                      "ランチ", "コーヒー"),
}  # fmt: skip

_CJK = re.compile(r"[぀-ヿ一-鿿]")


def matches(word: str, text: str) -> bool:
    if _CJK.search(word):
        return word in text
    return re.search(rf"(?<![\w]){re.escape(word)}(?![\w])", text) is not None


def keyword_category(text: str, mcc: int) -> str:
    folded = text.casefold()
    for category, words in KEYWORDS.items():
        if any(matches(w, folded) for w in words):
            return category
    return "food_beverage" if mcc in ON_PREMISES_MCC else "other"


class KeywordClassifier:
    name = "keyword-classifier"
    model_id = "keyword-lists"
    provider_endpoint = "none"
    prompt_version = KEYWORD_VERSION

    def classify(self, line_id: str, request: ClassifierRequest) -> Classification:
        category: Category = keyword_category(request.description_clean, request.mcc)  # type: ignore[assignment]
        key = hashlib.sha256(
            f"{KEYWORD_VERSION}|{request.description_clean}|{request.mcc}".encode()
        ).hexdigest()
        return Classification(
            line_id=line_id,
            status="classified",
            category=category,
            restricted=restricted_for(category),
            confidence=1.0,
            source=ClassificationSource(
                classifier=self.name,
                model_id=self.model_id,
                provider_endpoint=self.provider_endpoint,
                prompt_version=KEYWORD_VERSION,
                cache_key=key,
                request_id=None,
                cost_usd=None,
                prompt_tokens=None,
                completion_tokens=None,
                cache_hit=False,
            ),
        )
