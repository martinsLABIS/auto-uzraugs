"""Kopīgās funkcijas visiem avotiem: tīkls, cenas, auto īpašību atpazīšana."""
import os
import re
import time
from datetime import datetime, timezone

import requests

DELAY = float(os.getenv("DELAY", "1.5"))
DEBUG = os.getenv("DEBUG", "0") == "1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept-Language": "lv,en;q=0.8,de;q=0.6,ru;q=0.5",
}
session = requests.Session()
session.headers.update(HEADERS)


def log(*args):
    print(*args, flush=True)


def dbg(*args):
    if DEBUG:
        print("[debug]", *args, flush=True)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get(url, params=None, as_json=False):
    """Lejupielādē lapu ar pauzi un 3 mēģinājumiem. Atgriež Response, JSON vai None."""
    for attempt in range(3):
        try:
            time.sleep(DELAY)
            r = session.get(url, params=params, timeout=30)
            if r.status_code in (404, 410):
                return None
            r.raise_for_status()
            if not r.encoding:
                r.encoding = r.apparent_encoding
            return r.json() if as_json else r
        except (requests.RequestException, ValueError) as e:
            log(f"  kļūda ({attempt + 1}/3) {url}: {e}")
            time.sleep(4 * (attempt + 1))
    return None


# ------------------------------------------------------------------ skaitļi
PRICE_RE = re.compile(r"(\d{1,3}(?:[\s\u00a0\u202f,.]\d{3})+|\d+)(?:[.,]\d{2}(?!\d))?\s*€")
EURO_FIRST_RE = re.compile(r"€\s*(\d{1,3}(?:[\s\u00a0\u202f,.]\d{3})+|\d+)")


def to_int(s):
    d = re.sub(r"\D", "", str(s or ""))
    return int(d) if d else None


def parse_prices(text):
    """Visas cenas formā '21 300 €', '21,300 €', '27 600,00 €'."""
    out = []
    for m in PRICE_RE.finditer(text or ""):
        n = to_int(m.group(1))
        if n and 300 <= n <= 2_000_000:
            out.append(n)
    return out


def year_of(text):
    m = re.search(r"\b(19[89]\d|20[0-4]\d)\b", text or "")
    return int(m.group(1)) if m else None


def fmt_price(p):
    return f"{p:,}".replace(",", " ") + " €"


# ------------------------------------------------------- īpašību atpazīšana
PLUGIN_RE = re.compile(
    r"plug[\s-]?in|\bphev\b|uzlādējam\w*|lādējam\w* hibr|e-?hybrid|\bcooper se\b|\bse all4\b|"
    r"\btfsi ?e\b|\bgte\b|\b\d{2}e\b|\b[1-9]\d[05] ?[dx]?e\b(?!-)|\brecharge\b|\bt8\b|"
    r"\b4xe\b|\b450h\+|xdrive ?\d{2}e\b|плагин|подзаряжа\w*|подключаем\w* гибрид|"
    r"elektro/benzin.{0,40}plug|plug-in-hybrid",
    re.I,
)
AWD_RE = re.compile(
    r"4x4|4х4|pilnpiedzi\w*|\bquattro\b|4motion|x-?drive|4matic|\bawd\b|awd-i|4drive|"
    r"all[- ]wheel|\b4wd\b|hybrid4|\b4xe\b|e-?four|\bt8\b|\ball4\b|allrad|"
    r"полн\w* привод|полноприводн\w*",
    re.I,
)
FWD_RE = re.compile(r"\bfwd\b|priekšpiedz\w*|priekšēj\w* piedz\w*|frontantrieb|front[- ]wheel|передн\w* привод", re.I)
RWD_RE = re.compile(r"\brwd\b|aizmugur\w* piedz\w*|heckantrieb|rear[- ]wheel|задн\w* привод", re.I)
SKODA_IV_RE = re.compile(r"\biV\b")
EV_MODEL_RE = re.compile(
    r"enyaq|elroq|\bid\.? ?[3-7]\b|e-tron(?! ?quattro.*tfsi)|ioniq ?[56]|\bev[369]\b|model [3ysx]\b|"
    r"mustang mach|\beq[abceis]\b|\bix[13]?\b|\bi[3457]\b|\bc40\b|\bex[349]0\b|\bborn\b|\bzoe\b|"
    r"\bleaf\b|taycan|\be-?2008\b|\be-?208\b|polestar", re.I)
EV_TEXT_RE = re.compile(r"\bp[68]\b|twin motor|pure electric|elektroauto|\bbev\b|^\s*(elektro|elektriskais|electric|elektrisch)\s*$", re.I)
FWD_ONLY_PHEV_RE = re.compile(
    r"kuga|\ba3\b|\bq3\b|golf|passat|octavia|superb|niro|ceed|ioniq|formentor|\bleon\b|"
    r"\ba ?250|\bb ?250|captur|megane|\b308\b|astra|c5 aircross|corolla|c-hr|prius|xc ?40|\bx2\b", re.I)
ALWAYS_AWD_PHEV_RE = re.compile(r"outlander|rav ?4|\bt8\b|nx ?450|\b4xe\b", re.I)
HYBRID_RE = re.compile(r"hibr|hybrid|гибрид|\b\d[.,]\d\s?H\b", re.I)
EV_WORD_RE = re.compile(r"elektr(o|isk)|electric|\bev\b|elektro\b|электро", re.I)
DIESEL_RE = re.compile(r"dīzel|diesel|\btdi\b|\bcrdi\b|\bhdi\b|\bdci\b|\b\d[.,]\dD\b|дизел|\b\d{3}d\b", re.I)
LPG_RE = re.compile(r"\bgāz|\blpg\b|\bcng\b|autogas|газ", re.I)
AUTO_RE = re.compile(r"automāt|automat|\bdsg\b|\bcvt\b|steptronic|s[- ]?tronic|tiptronic|automatik|\bat\b|автомат", re.I)
MANUAL_RE = re.compile(r"manuāl|mehānisk|\bmanual\b|schaltgetriebe|\bmt\b|механ", re.I)

BODY_PATTERNS = [
    ("suv", r"apvidus|\bsuv\b|geländewagen|crossover|krosover|внедорожник|джип"),
    ("wagon", r"universāl|kombi\b|\bcombi\b|touring|avant|variant|sports ?tourer|estate|\bsw\b|\bwagon\b|универсал|allroad|cross country"),
    ("sedan", r"sedan|limousine|седан"),
    ("hatch", r"hečbek|hatchback|kleinwagen|sportback|хэтчбек"),
    ("mpv", r"minivan|minivens|\bvan/minibus\b|\bmpv\b|active tourer|touran|минивэн"),
    ("coupe", r"kupej|coup[eé]|купе|gran coupe"),
    ("cabrio", r"kabriolet|cabrio|convertible|roadster|кабриолет"),
    ("pickup", r"pikap|pick-?up|пикап"),
    ("van", r"furgon|kravas|transporter|\bvan\b|фургон"),
]
BODY_RES = [(k, re.compile(p, re.I)) for k, p in BODY_PATTERNS]


def detect_fuel(fuel_text, full_text, model=""):
    """Atgriež 'phev', 'hybrid', 'electric', 'diesel', 'lpg', 'petrol' vai None."""
    f = fuel_text or ""
    t = f"{f} {full_text or ''}"
    explicit_hybrid = bool(re.search(r"plug[\s-]?in|\bphev\b|hibr|hybrid", t, re.I))
    is_ev_model = (bool(EV_MODEL_RE.search(model)) or bool(EV_TEXT_RE.search(f))) and not explicit_hybrid
    hybrid4_phev = bool(re.search(r"hybrid4", t, re.I)) and not re.search(r"\bhdi\b|dīzel|diesel", t, re.I)
    if not is_ev_model and (PLUGIN_RE.search(t) or SKODA_IV_RE.search(t) or hybrid4_phev):
        return "phev"
    if is_ev_model or (EV_WORD_RE.search(f) and not HYBRID_RE.search(f) and not re.search(r"benz|petrol", f, re.I)):
        return "electric"
    if HYBRID_RE.search(f) or re.search(r"\bhybrid\b|hibrīd", t[:300], re.I) or \
            re.search(r"elektr\w*\s*/\s*(benzin|diesel|petrol)|(benzin|diesel|petrol)\s*/\s*elektr", f, re.I):
        return "hybrid"
    if DIESEL_RE.search(f) or (not f and DIESEL_RE.search(t[:200])):
        return "diesel"
    if LPG_RE.search(f):
        return "lpg"
    if re.search(r"benz|petrol|бенз|\btsi\b|\btfsi\b|\b\d[.,]\d\b", f, re.I):
        return "petrol"
    return None


def detect_drive(drive_text, full_text, model="", fuel=None):
    """Atgriež 'awd', 'fwd', 'rwd' vai None. drive_text – portāla piedziņas lauks, ja ir."""
    d = drive_text or ""
    if AWD_RE.search(d):
        return "awd"
    if FWD_RE.search(d):
        return "fwd"
    if RWD_RE.search(d):
        return "rwd"
    t = full_text or ""
    if fuel == "phev":
        if re.search(r"hybrid4", t, re.I) or ALWAYS_AWD_PHEV_RE.search(f"{model} {t[:300]}"):
            return "awd"
        if FWD_ONLY_PHEV_RE.search(model):
            return "fwd"
    if AWD_RE.search(t):
        return "awd"
    if FWD_RE.search(t):
        return "fwd"
    if RWD_RE.search(t):
        return "rwd"
    return None


def detect_gearbox(gear_text, full_text=""):
    g = gear_text or ""
    if AUTO_RE.search(g):
        return "auto"
    if MANUAL_RE.search(g):
        return "manual"
    t = full_text or ""
    if AUTO_RE.search(t[:400]):
        return "auto"
    if MANUAL_RE.search(t[:400]):
        return "manual"
    return None


# modeļi, kuru virsbūve ir zināma (izmanto, ja portāls virsbūvi nenorāda)
MODEL_BODY = [
    ("wagon", r"\bavant\b|touring|variant|\bv[679]0\b|\bkombi\b|\bcombi\b|estate|sports? ?tourer|allroad|"
              r"cross country|shooting brake|\bsw\b|\bt-?modell\b|\bwagon\b|\bst\b"),
    ("suv", r"\bq[2-8]\b|\bsq[5-8]\b|\bx[1-7]\b|\bix[13]?\b|\bxc ?[4-9]0\b|\bex[39]0\b|tiguan|touareg|t-?roc|"
            r"t-?cross|taigo|id\.? ?[4-7]\b|atlas|teramont|ateca|tarraco|arona|formentor|terramar|kodiaq|karoq|kamiq|"
            r"enyaq|elroq|kuga|puma|explorer|tucson|santa ?fe|kona|bayon|sportage|sorento|niro|\bev[59]\b|"
            r"outlander|eclipse cross|asx|rav ?4|c-?hr|highlander|land cruiser|bz4x|cx-?[3-9]0?\b|"
            r"\bgl[abceks]\b|\beq[abce] suv|macan|cayenne|\bnx\b|\brx\b|\bux\b|\bxc60\b|grandland|"
            r"mokka|crossland|3008|5008|2008|c5 aircross|austral|kadjar|captur|arkana|duster|qashqai|x-?trail|"
            r"juke|ariya|range rover|discovery|defender|evoque|velar|f-?pace|e-?pace|countryman|compass|"
            r"renegade|wrangler|forester|outback|vitara|s-?cross|\bzs\b|\bhs\b|\bmodel [xy]\b"),
]
MODEL_BODY_RES = [(k, re.compile(p, re.I)) for k, p in MODEL_BODY]


def detect_body(body_text, full_text=""):
    for src in (body_text or "", (full_text or "")[:400]):
        for key, rx in BODY_RES:
            if src and rx.search(src):
                return key
    for key, rx in MODEL_BODY_RES:
        if rx.search((full_text or "")[:200]):
            return key
    return None
