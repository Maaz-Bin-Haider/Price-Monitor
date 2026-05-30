import re
from rapidfuzz import fuzz
from config import settings

# Words that indicate accessories/replacements — not the main product.
# If the query does NOT contain these words but the result title does,
# the result score is penalised heavily (dropped to 40%).
ACCESSORY_KEYWORDS = [
    # Physical accessories
    "cable", "mount", "bracket", "adaptor", "adapter", "case", "cover",
    "stand", "strap", "charger", "battery", "sleeve", "bag", "pouch",
    "hub", "dock", "skin", "bumper", "holster",
    # Audio accessories
    "ear pad", "ear pads", "earpads", "ear cushion", "cushion pads",
    "earbud tip", "ear tip", "ear tips", "foam tip", "wing tip",
    "replacement ear", "headband pad", "headband cover",
    # Display/camera accessories
    "screen protector", "tempered glass", "lens cap", "lens cover",
    "lens filter", "lens hood", "lens adapter", "filter kit",
    # Cables
    "ethernet cable", "power cable", "usb cable", "hdmi cable",
    "charging cable", "data cable", "extension cable",
    # Mounts / networking accessories
    "pole adaptor", "edge protector", "actuated cable", "power supply",
    "wall mount", "ceiling mount", "roof mount", "pipe mount",
    # General replacement parts
    "replacement", "spare part", "repair kit",
]


def normalise(text: str) -> str:
    t = text.lower()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    t = re.sub(r"(\d+)(gb)", r"\1 gb", t)
    t = re.sub(r"(\d+)(tb)", r"\1 tb", t)
    t = re.sub(r"(\d+)(mb)", r"\1 mb", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _is_accessory(query: str, candidate: str) -> bool:
    """True if candidate contains an accessory keyword not in the query."""
    q = query.lower()
    c = candidate.lower()
    for kw in ACCESSORY_KEYWORDS:
        if kw in c and kw not in q:
            return True
    return False


def score(query: str, candidate: str) -> float:
    q = normalise(query)
    c = normalise(candidate)
    token_set = fuzz.token_set_ratio(q, c)
    partial   = fuzz.partial_ratio(q, c)
    base      = round(0.6 * token_set + 0.4 * partial, 1)
    if _is_accessory(query, candidate):
        base = base * 0.4
    return base


def filter_matches(
    query: str,
    candidates: list[dict],
    threshold: float = None,
) -> list[dict]:
    if threshold is None:
        threshold = settings.MATCH_THRESHOLD
    scored = []
    for item in candidates:
        s = score(query, item.get("title", ""))
        if s >= threshold:
            scored.append({**item, "match_score": round(s, 1)})
    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored
