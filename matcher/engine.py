import re
from rapidfuzz import fuzz
from config import settings


# ── ACCESSORY KEYWORDS ────────────────────────────────────────────────────────
# Split into STRONG and WEAK categories so penalties aren't binary.
# STRONG = almost always an accessory when not in the query
# WEAK   = could be the actual product (e.g. "Google Nest Hub", "Canon Lens")

STRONG_ACCESSORY_PHRASES = [
    # Replacement / repair
    "replacement", "spare part", "repair kit", "refurbished",
    # Protection — only when clearly an accessory case, not a product component
    "screen protector", "tempered glass", "privacy screen",
    "carrying case", "travel case", "hard case", "soft case",
    "phone case", "airpods case", "ipad case", "tablet case",
    "laptop case", "keyboard cover", "keyboard skin", "cooling pad",
    # Audio accessories
    "ear pad", "ear pads", "earpads", "ear cushion", "cushion pads",
    "earbud tip", "earbud tips", "ear tip", "ear tips",
    "foam tip", "foam tips", "wing tip", "wing tips",
    "replacement ear", "headband pad", "headband cover",
    # Camera accessories
    "lens cap", "lens cover", "lens hood", "lens filter",
    "nd filter", "filter set", "filter kit", "cpl filter",
    "polarizer", "wide-angle lens", "wide angle lens", "telephoto",
    # Cables
    "ethernet cable", "power cable", "usb cable", "hdmi cable",
    "charging cable", "data cable", "extension cable", "power lead",
    # Mounts
    "wall mount", "ceiling mount", "roof mount", "pipe mount",
    "pole adaptor", "edge protector",
    # Gaming accessories
    "controller skin", "thumb grip",
    # Wearable accessories
    "watch strap", "watch band",
    # Printer supplies
    "ink cartridge", "toner cartridge",
    # Enclosures
    "ssd enclosure", "hard drive enclosure",
    # Other strong indicators
    "stylus", "antenna", "propellers", "actuated cable",
    # Audio/video accessories
    "windscreen", "windscreens", "deadcat", "pop shield", "pop filter",
    "shock mount", "boom arm", "mic stand", "microphone stand",
    "transmitter", "receiver",
    # Covers and skins
    "front cover", "back cover", "lens cover",
]

WEAK_ACCESSORY_PHRASES = [
    # These could be the actual product
    "cable", "mount", "bracket", "adapter", "adaptor",
    "stand", "strap", "charger",
    "battery", "sleeve", "bag", "pouch", "hub", "dock",
    "skin", "bumper", "holster", "lens", "filters",
    "power supply", "extension", "cushion",
]

# Penalty multipliers
STRONG_PENALTY = 0.25   # 75% reduction — almost certainly an accessory
WEAK_PENALTY   = 0.60   # 40% reduction — might be an accessory

# Bundle indicators — if present, reduce accessory penalty
# e.g. "Nintendo Switch OLED + Carrying Case" is still a valid product
BUNDLE_INDICATORS = [
    "bundle", "combo", "fly more",
    "starter kit", "value pack", "complete kit",
]


# ── NORMALISATION ─────────────────────────────────────────────────────────────

def normalise(text: str) -> str:
    """Lowercase, remove punctuation, normalise storage units, collapse spaces."""
    t = text.lower()
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    # Normalise storage units so "256gb" == "256 gb"
    t = re.sub(r"(\d+)(gb)", r"\1 gb", t)
    t = re.sub(r"(\d+)(tb)", r"\1 tb", t)
    t = re.sub(r"(\d+)(mb)", r"\1 mb", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


# ── WORD-BOUNDARY MATCHING ───────────────────────────────────────────────────

def _contains_phrase(text: str, phrase: str) -> bool:
    """
    Word-boundary aware phrase check.
    Fixes Issue 1: substring matching causing false positives.
    e.g. "case" no longer matches inside "showcase" or "suitcase".
    """
    # Escape special regex chars in the phrase
    escaped = re.escape(phrase)
    pattern = r"(?<![a-z0-9])" + escaped + r"(?![a-z0-9])"
    return bool(re.search(pattern, text))


# ── MODEL NUMBER EXTRACTION ───────────────────────────────────────────────────

def _extract_model_numbers(text: str) -> set:
    """
    Extract model-number-like tokens (mix of letters and digits).
    Fixes Issue 12: model mismatch not detected.
    e.g. "WH1000XM5" vs "WH1000XM4"
    """
    tokens = re.findall(r"[a-z]*\d+[a-z0-9]*", text.lower())
    # Only keep tokens that look like model numbers (not just plain numbers)
    return {t for t in tokens if re.search(r"[a-z]", t) and re.search(r"\d", t)}


def _model_mismatch_penalty(query: str, candidate: str) -> float:
    """
    Returns a penalty multiplier if candidate contains model numbers
    that directly conflict with the query's model numbers.
    Fixes Issue 12.
    """
    q_models = _extract_model_numbers(query)
    c_models = _extract_model_numbers(candidate)

    if not q_models or not c_models:
        return 1.0   # can't determine mismatch, no penalty

    # If there are model numbers in candidate not in query → possible mismatch
    conflicting = c_models - q_models
    matching    = c_models & q_models

    if conflicting and not matching:
        return 0.5   # model numbers present but none match → heavy penalty
    if conflicting and matching:
        return 0.85  # some match, some don't → light penalty

    return 1.0


# ── BUNDLE DETECTION ─────────────────────────────────────────────────────────

def _is_bundle(candidate: str) -> bool:
    """
    Detects product bundles like "Nintendo Switch OLED + Carrying Case".
    Fixes Issue 11: bundles shouldn't be penalised as accessories.
    """
    c = candidate.lower()
    for indicator in BUNDLE_INDICATORS:
        if _contains_phrase(c, indicator):
            return True
    # Also detect "Product + Accessory" explicit bundle pattern
    if " + " in candidate:
        return True
    return False


# ── ACCESSORY DETECTION ───────────────────────────────────────────────────────

def _accessory_penalty(query: str, candidate: str) -> float:
    """
    Returns a penalty multiplier based on accessory keyword detection.
    Fixes Issues 2, 3, 4, 5, 6, 7, 10, 11.

    Key improvements:
    - Word-boundary matching (not substring)
    - Longer phrases checked first (most specific wins)
    - Strong vs weak penalty tiers
    - Bundle detection reduces penalty
    - Query intent considered
    """
    q = normalise(query)
    c = normalise(candidate)

    # If it's a bundle, reduce penalty significantly
    bundle = _is_bundle(candidate)

    # Special rule: title ends with "case" and query doesn't contain "case"
    # → almost certainly a protective case accessory
    # BUT exclude compound cases that are part of the product (charging case, carry case used as bundle)
    if c.endswith(" case") and not _contains_phrase(q, "case"):
        # Check it's not a product-component case (charging, carry, hard, soft already in STRONG)
        # Only penalise if "case" is likely standalone (preceded by brand/model name)
        # i.e. the word before "case" is not a product-descriptor word
        component_cases = ("charging case", "carry case", "transit case", "storage case")
        is_component = any(_contains_phrase(c, cc) for cc in component_cases)
        if not is_component:
            if bundle:
                return 0.70
            return STRONG_PENALTY

    # ── Check STRONG phrases first (sorted longest first for specificity) ──
    # Fixes Issue 10: longer phrases checked before shorter ones
    for phrase in sorted(STRONG_ACCESSORY_PHRASES, key=len, reverse=True):
        phrase_norm = normalise(phrase)
        if _contains_phrase(c, phrase_norm) and not _contains_phrase(q, phrase_norm):
            if bundle:
                return 0.70   # bundle softens strong penalty
            return STRONG_PENALTY

    # ── Check WEAK phrases ────────────────────────────────────────────────
    for phrase in sorted(WEAK_ACCESSORY_PHRASES, key=len, reverse=True):
        phrase_norm = normalise(phrase)
        if _contains_phrase(c, phrase_norm) and not _contains_phrase(q, phrase_norm):
            if bundle:
                return 0.90   # bundle almost neutralises weak penalty
            return WEAK_PENALTY

    return 1.0   # no accessory detected


# ── QUERY LENGTH BOOST ────────────────────────────────────────────────────────

def _query_length_factor(query: str) -> float:
    """
    Short queries match too many things because fuzzy ratio is high
    for short strings. Slightly raise the effective threshold for short queries.
    Fixes Issue 13.
    Returns a multiplier applied to the final score (not the threshold).
    """
    words = len(normalise(query).split())
    if words <= 2:
        return 0.90   # penalise short queries slightly
    if words <= 3:
        return 0.95
    return 1.0


# ── MAIN SCORING FUNCTION ─────────────────────────────────────────────────────

def score(query: str, candidate: str) -> float:
    """
    Score how well a candidate title matches the search query.
    Returns 0-100.
    """
    q = normalise(query)
    c = normalise(candidate)

    # Base fuzzy score
    token_set = fuzz.token_set_ratio(q, c)
    partial   = fuzz.partial_ratio(q, c)
    base      = round(0.6 * token_set + 0.4 * partial, 1)

    # Apply accessory penalty (tiered, phrase-aware, bundle-aware)
    accessory_mult = _accessory_penalty(query, candidate)
    base = base * accessory_mult

    # Apply model mismatch penalty
    model_mult = _model_mismatch_penalty(q, c)
    base = base * model_mult

    # Apply short-query penalty
    length_mult = _query_length_factor(query)
    base = base * length_mult

    return round(base, 1)


# ── FILTER AND RANK ───────────────────────────────────────────────────────────

def filter_matches(
    query: str,
    candidates: list[dict],
    threshold: float = None,
) -> list[dict]:
    """
    Score all candidates, filter by threshold, return sorted by score desc.
    """
    if threshold is None:
        threshold = settings.MATCH_THRESHOLD

    scored = []
    for item in candidates:
        s = score(query, item.get("title", ""))
        if s >= threshold:
            scored.append({**item, "match_score": round(s, 1)})

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    return scored
