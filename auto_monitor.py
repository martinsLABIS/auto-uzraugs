#!/usr/bin/env python3
"""
Auto sludinājumu uzraugs – plug-in hibrīdi ar pilnpiedziņu līdz 37 000 EUR.

Avoti: ss.com un mollerauto.lv (lietotie auto).
Paziņojumi telefonā caur ntfy (bezmaksas lietotne Android un iOS).

Paziņo, kad:
  1) parādās jauns atbilstošs auto ar cenu līdz MAX_PRICE;
  2) jau zināmam atbilstošam auto samazinās cena (un tā ir līdz MAX_PRICE).

Iestatījumi – vides mainīgie (sk. README.md).
"""
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------- iestatījumi
MAX_PRICE = int(os.getenv("MAX_PRICE", "37000"))   # paziņo tikai par auto līdz šai cenai
# Auto no MAX_PRICE līdz SCAN_MAX uzrauga klusām: ja cena nokrīt līdz MAX_PRICE, pienāk paziņojums.
# Dārgāki par SCAN_MAX netiek skatīti vispār.
SCAN_MAX = max(MAX_PRICE, int(os.getenv("SCAN_MAX", "40000")))
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "").strip()
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
INCLUDE_EV = os.getenv("INCLUDE_EV", "0") == "1"   # 1 = iekļaut arī tīros elektroauto ar 4x4
DELAY = float(os.getenv("DELAY", "1.5"))            # pauze starp pieprasījumiem (sekundes)
DEBUG = os.getenv("DEBUG", "0") == "1"
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"      # 1 = nesūtīt paziņojumus, tikai rakstīt žurnālā
REPORT_FILE = os.getenv("REPORT_FILE", "")      # ja norādīts – saglabā atrasto auto sarakstu JSON
STATE_FILE = Path(os.getenv("STATE_FILE", "state.json"))
STATE_VERSION = 2   # palielina, ja mainās loģika – vecais stāvoklis tiek atmests
FULL_SCAN = os.getenv("FULL_SCAN", "0") == "1"   # var kļūt True arī load_state() laikā
SS_PAGES_NORMAL = int(os.getenv("SS_PAGES", "5"))
SS_RECHECK_LIMIT = int(os.getenv("SS_RECHECK_LIMIT", "60"))

SS_BASE = "https://www.ss.com/lv/transport/cars/sell/"
MOLLER_BASE = "https://mollerauto.lv/lv/used-cars.html"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "lv,en;q=0.8,ru;q=0.6",
}

# ------------------------------------------------------- atpazīšanas noteikumi
PLUGIN_RE = re.compile(
    r"plug[\s-]?in|\bphev\b|uzlādējam\w*|lādējam\w* hibr|e-?hybrid|hybrid4|"
    r"\btfsi ?e\b|\bgte\b|\b\d{2}e\b|\b\d{3} ?d?e\b|\brecharge\b|\bt8\b|"
    r"\b4xe\b|\b450h\+|xdrive ?\d{2}e\b|плагин|подзаряжа\w*|подключаем\w* гибрид",
    re.I,
)
AWD_RE = re.compile(
    r"4x4|4х4|pilnpiedzi\w*|\bquattro\b|4motion|xdrive|4matic|\bawd\b|awd-i|"
    r"all[- ]wheel|\b4wd\b|hybrid4|\b4xe\b|e-?four|\bt8\b|\ball4\b|"
    r"полн\w* привод|полноприводн\w*",
    re.I,
)
SKODA_IV_RE = re.compile(r"\biV\b")   # reģistrjutīgs: Skoda iV, bet ne Golf IV
# tīri elektroauto modeļi – nekad nav plug-in hibrīdi
EV_MODEL_RE = re.compile(
    r"enyaq|elroq|\bid\.? ?[3-7]\b|e-tron|ioniq ?[56]|\bev[369]\b|model [3ysx]\b|"
    r"mustang mach|\beqa\b|\beqb\b|\beqc\b|\beqe\b|\bix[13]?\b|\bi[45]\b|xc40 recharge pure|c40", re.I)
# modeļi, kuru plug-in versijas vienmēr ir ar pilnpiedziņu
ALWAYS_AWD_RE = re.compile(r"outlander|rav ?4|\bt8\b|nx ?450|\b4xe\b|hybrid4", re.I)
EV_RE = re.compile(r"elektr\w*|\bev\b|e-tron|\bid\.? ?[4-7]\b|enyaq|электро", re.I)
# ss.com saraksta rindas norāde, ka vērts atvērt sludinājumu
SS_HINT_RE = re.compile(
    r"hibr|hybrid|plug|phev|\d[.,]\d\s?H\b|elektr|\d[.,]\d\s?E\b|recharge|\bt8\b|"
    r"\b4xe\b|tfsi ?e|\bgte\b|\biV\b|\b\d{2,3} ?e\b|гибрид",
    re.I,
)


def classify(text, model=""):
    """Atgriež 'Plug-in 4x4', 'Elektro 4x4' vai None. model – marka/modelis no saites vai virsraksta."""
    explicit_hybrid = bool(re.search(r"plug[\s-]?in|\bphev\b|hibr|hybrid", text, re.I))
    is_ev_model = bool(EV_MODEL_RE.search(model or text[:80])) and not explicit_hybrid
    plugin = not is_ev_model and bool(PLUGIN_RE.search(text) or SKODA_IV_RE.search(text))
    awd = bool(AWD_RE.search(text)) or (plugin and bool(ALWAYS_AWD_RE.search(text)))
    if plugin and awd:
        return "Plug-in 4x4"
    if INCLUDE_EV and awd and (is_ev_model or EV_RE.search(text)):
        return "Elektro 4x4"
    return None


# ------------------------------------------------------------- palīgfunkcijas
session = requests.Session()
session.headers.update(HEADERS)


def log(*args):
    print(*args, flush=True)


def dbg(*args):
    if DEBUG:
        print("[debug]", *args, flush=True)


def get(url, params=None):
    for attempt in range(3):
        try:
            time.sleep(DELAY)
            r = session.get(url, params=params, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            r.encoding = r.apparent_encoding if not r.encoding else r.encoding
            return r
        except requests.RequestException as e:
            log(f"  kļūda ({attempt + 1}/3) {url}: {e}")
            time.sleep(5 * (attempt + 1))
    return None


PRICE_RE = re.compile(r"(\d{1,3}(?:[\s\u00a0\u202f,]\d{3})+|\d+)(?:[.,]\d{2}(?!\d))?\s*€")


def parse_prices(text):
    out = []
    for m in PRICE_RE.finditer(text):
        n = int(re.sub(r"\D", "", m.group(1)))
        if 300 <= n <= 2_000_000:
            out.append(n)
    return out


def fmt_price(p):
    return f"{p:,}".replace(",", " ") + " €"


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state():
    global FULL_SCAN
    if STATE_FILE.exists():
        try:
            st = json.loads(STATE_FILE.read_text("utf-8"))
            if st.get("version") == STATE_VERSION:
                return st
            log("Stāvoklis no vecākas versijas – sāku no jauna")
        except json.JSONDecodeError:
            log("state.json bojāts – sāku no jauna")
    FULL_SCAN = True
    return {"version": STATE_VERSION, "tracked": {}, "checked": {}}


def save_state(state):
    # izmet pārbaudes kešu ierakstiem, kas nav redzēti 30 dienas
    cutoff = time.time() - 30 * 86400
    state["checked"] = {k: v for k, v in state["checked"].items() if v.get("ts", 0) > cutoff}
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True), "utf-8")


def notify(title, message, url=None, tags=None, priority=3):
    if DRY_RUN or not NTFY_TOPIC:
        log(f"(ntfy nav iestatīts) {title}: {message}")
        return
    payload = {"topic": NTFY_TOPIC, "title": title, "message": message,
               "tags": tags or ["car"], "priority": priority}
    if url:
        payload["click"] = url
        payload["actions"] = [{"action": "view", "label": "Atvērt sludinājumu", "url": url}]
    try:
        requests.post(NTFY_SERVER, json=payload, timeout=20).raise_for_status()
    except requests.RequestException as e:
        log(f"ntfy kļūda: {e}")


# ------------------------------------------------------------ mollerauto.lv
MOLLER_ID_RE = re.compile(r"/lv/(\d{6,})\.html")


def moller_cards(soup):
    cards = {}
    for a in soup.find_all("a", href=MOLLER_ID_RE):
        cid = MOLLER_ID_RE.search(a["href"]).group(1)
        if cid in cards:
            continue
        node = a
        for _ in range(8):
            node = node.parent
            if node is None or "€" in node.get_text(" ", strip=True):
                break
        if node is None or "€" not in node.get_text(" ", strip=True):
            continue
        # konteiners nedrīkst saturēt vairākus auto
        if len(set(MOLLER_ID_RE.findall(str(node)))) > 1:
            continue
        text = node.get_text(" ", strip=True)
        prices = parse_prices(text)
        if not prices:
            continue
        title = PRICE_RE.split(text)[0]
        title = re.sub(r"^(?:(?:Garantija|Jaunums|Akcija|Rezervēts)\s+)+", "", title).strip()[:70]
        cards[cid] = {"id": cid, "title": title, "price": min(prices), "text": text,
                      "url": f"https://mollerauto.lv/lv/{cid}.html"}
    return list(cards.values())


def moller_detail_text(url):
    r = get(url)
    if not r:
        return ""
    soup = BeautifulSoup(r.text, "html.parser")
    main = soup.find(id="maincontent") or soup.find("main") or soup
    text = main.get_text(" ", strip=True)
    # lapas beigās ir citu auto kartītes – tās nedrīkst ietekmēt šī auto vērtējumu
    for stop in ("Uzzināt vairāk", "Biežāk uzdotie jautājumi"):
        text = text.split(stop)[0]
    return text


def scan_moller(state, found):
    log("mollerauto.lv …")
    seen_ids = set()
    for page in range(1, 150):
        r = get(MOLLER_BASE, params={"product_list_order": "price",
                                     "product_list_dir": "asc", "p": page})
        if not r:
            return False
        cards = moller_cards(BeautifulSoup(r.text, "html.parser"))
        new_cards = [c for c in cards if c["id"] not in seen_ids]
        dbg(f"moller lapa {page}: {len(cards)} kartītes, {len(new_cards)} jaunas")
        if not new_cards:
            break
        for c in new_cards:
            seen_ids.add(c["id"])
            if c["price"] > SCAN_MAX:
                continue
            t = c["text"].lower()
            if "priekšējā piedziņa" in t or "aizmugurējā piedziņa" in t:
                continue
            key = "moller:" + c["id"]
            label = classify(c["text"], c["title"])
            if not label and re.search(r"hibr|elektr|plug|phev", t):
                cached = state["checked"].get(key)
                if cached is None:
                    label = classify(c["text"] + " " + moller_detail_text(c["url"]), c["title"])
                    dbg(f"  detaļas {c['title']}: {label}")
                else:
                    label = cached.get("label")
            state["checked"][key] = {"label": label, "ts": time.time()}
            if label:
                found[key] = {**c, "label": label, "source": "Moller"}
        if min(c["price"] for c in cards) > SCAN_MAX:
            break
    log(f"  pārskatīti {len(seen_ids)} auto")
    return len(seen_ids) > 0


# ------------------------------------------------------------------- ss.com
def ss_detail(url):
    """Atgriež (teksts, cena) vai (None, None), ja sludinājuma vairs nav."""
    r = get(url)
    if not r or "/msg/" not in r.url:
        return None, None
    soup = BeautifulSoup(r.text, "html.parser")
    parts = []
    box = soup.find(id="msg_div_msg")
    if box:
        spec = box.find(id="msg_div_spec")
        if spec:
            # aprīkojuma sarakstā ir visas iespējamās opcijas; auto ir tikai treknrakstā atzīmētās
            parts.append(" ".join(b.get_text(" ", strip=True) for b in spec.select("b.auto_c")))
            spec.decompose()
        parts.append(box.get_text(" ", strip=True))
    else:   # rezerves variants: parametru šūnas un meta apraksts, bez lapas izvēlnēm
        parts += [td.get_text(" ", strip=True) for td in soup.select("td.ads_opt, td[id^=tdo_]")]
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            parts.append(meta["content"])
    text = " ".join(parts)
    price_el = soup.find(id="tdo_8")
    prices = parse_prices(price_el.get_text(" ", strip=True)) if price_el else []
    if not prices:
        m = re.search(r"Cena:\s*([\d\s\u00a0]+)\s*€", soup.get_text(" ", strip=True))
        prices = parse_prices(m.group(0)) if m else []
    title_el = soup.find("h2") or soup.find("title")
    title = title_el.get_text(" ", strip=True) if title_el else ""
    return title + " " + text, (prices[0] if prices else None)


def ss_title_from_url(url):
    parts = url.rstrip("/").split("/")
    try:
        i = parts.index("cars")
        return " ".join(p.replace("-", " ").title() for p in parts[i + 1:i + 3])
    except ValueError:
        return "Auto"


def scan_ss(state, found):
    SS_PAGES = 400 if FULL_SCAN else SS_PAGES_NORMAL
    log(f"ss.com … (līdz {SS_PAGES} lapām)")
    seen = set()
    for page in range(1, SS_PAGES + 1):
        url = SS_BASE if page == 1 else f"{SS_BASE}page{page}.html"
        r = get(url)
        if not r:
            break
        soup = BeautifulSoup(r.text, "html.parser")
        rows = [tr for tr in soup.select("tr[id^=tr_]") if not tr["id"].startswith("tr_bnr")]
        page_new = 0
        for tr in rows:
            a = tr.find("a", href=re.compile(r"/msg/"))
            if not a:
                continue
            href = a["href"]
            link = href if href.startswith("http") else "https://www.ss.com" + href
            key = "ss:" + link.split("/msg/")[-1]
            if key in seen:
                continue
            seen.add(key)
            page_new += 1
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            row_text = " ".join(cells)
            prices = parse_prices(cells[-1]) if cells else []
            if not prices or prices[0] > SCAN_MAX:
                continue
            price = prices[0]
            model = cells[3] if len(cells) >= 8 and cells[3] else ss_title_from_url(link)
            label = classify(row_text, model)
            if not label and SS_HINT_RE.search(row_text):
                cached = state["checked"].get(key)
                if cached is None:
                    text, _ = ss_detail(link)
                    label = classify(row_text + " " + (text or ""), model)
                    dbg(f"  detaļas {link}: {label}")
                else:
                    label = cached.get("label")
            state["checked"][key] = {"label": label, "ts": time.time()}
            if label:
                title = model
                year = next((c for c in cells if re.fullmatch(r"(19|20)\d{2}", c)), "")
                found[key] = {"id": key, "title": f"{title} {year}".strip(), "price": price,
                              "url": link, "label": label, "source": "SS"}
        dbg(f"ss lapa {page}: {len(rows)} rindas, {page_new} jaunas")
        if page_new == 0:   # aiz pēdējās lapas ss.com rāda atkal pirmo
            break
    log(f"  pārskatīti {len(seen)} sludinājumi")
    return seen


def recheck_ss(state, found, seen):
    """Pārbauda zināmos ss.com auto, kas šoreiz nebija pārskatītajās lapās."""
    todo = [k for k in state["tracked"] if k.startswith("ss:") and k not in seen]
    for key in todo[:SS_RECHECK_LIMIT]:
        car = state["tracked"][key]
        text, price = ss_detail(car["url"])
        if text is None:
            log(f"  vairs nav: {car['title']}")
            state["tracked"].pop(key, None)
            continue
        if price:
            found[key] = {**car, "price": price}


# ------------------------------------------------------------- galvenā daļa
def main():
    state = load_state()
    silent = FULL_SCAN
    log(f"Sākums {now_iso()} | robeža {fmt_price(MAX_PRICE)} | "
        f"{'pilnā pārskatīšana' if FULL_SCAN else 'parastā pārbaude'}")

    found = {}
    moller_ok = scan_moller(state, found)
    ss_seen = scan_ss(state, found)
    recheck_ss(state, found, ss_seen)

    tracked = state["tracked"]
    new_cars, drops = [], []
    for key, car in found.items():
        prev = tracked.get(key)
        if prev is None:
            if car["price"] <= MAX_PRICE:
                new_cars.append(car)
        elif car["price"] < prev["price"] and car["price"] <= MAX_PRICE:
            drops.append((car, prev["price"]))
        tracked[key] = {"title": car["title"], "price": car["price"], "url": car["url"],
                        "label": car["label"], "source": car["source"],
                        "first_seen": prev["first_seen"] if prev else now_iso(),
                        "last_seen": now_iso()}

    # Moller auto, kas vairs nav sarakstā (pārdoti) – izņem no uzraudzības
    if moller_ok:
        for key in [k for k in tracked if k.startswith("moller:") and k not in found]:
            tracked.pop(key)

    matching = sorted((c for c in tracked.values() if c["price"] <= MAX_PRICE),
                      key=lambda c: c["price"])
    log(f"Atbilst: {len(matching)} | jauni: {len(new_cars)} | cenas kritumi: {len(drops)}")

    if silent:
        lines = [f"{c['title']} – {fmt_price(c['price'])}\n{c['url']}" for c in matching[:12]]
        more = f"\n\n… un vēl {len(matching) - 12}" if len(matching) > 12 else ""
        notify("Auto uzraugs darbojas",
               f"Atradu {len(matching)} plug-in 4x4 līdz {fmt_price(MAX_PRICE)}.\n\n"
               + "\n\n".join(lines) + more, tags=["white_check_mark"])
    else:
        for c in new_cars:
            notify(f"Jauns: {c['title']}",
                   f"{fmt_price(c['price'])} · {c['label']} · {c['source']}",
                   url=c["url"], tags=["car"], priority=4)
        for c, old in drops:
            notify(f"Cena samazināta: {c['title']}",
                   f"{fmt_price(old)} → {fmt_price(c['price'])} (−{fmt_price(old - c['price'])}) "
                   f"· {c['source']}",
                   url=c["url"], tags=["chart_with_downwards_trend"], priority=4)

    if REPORT_FILE:
        Path(REPORT_FILE).write_text(json.dumps(
            {"matching": matching, "found_all": list(found.values())},
            ensure_ascii=False, indent=1), "utf-8")
    save_state(state)
    log("Gatavs.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(1)
