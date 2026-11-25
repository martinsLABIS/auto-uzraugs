"""Avotu lasītāji.

Katrs avots atgriež auto ierakstus (dict) ar kopīgiem laukiem:
  key, source, url, title, make, year, km, price, img,
  fuel_text, drive_text, gear_text, body_text, text (saraksta teksts), power_kw
un katram avotam ir detail(car) funkcija, kas atver sludinājumu un atgriež papildu laukus
(text, drive_text, fuel_text, gear_text, body_text, price, img, year, km) vai None, ja sludinājuma vairs nav.
"""
import json
import re
from html import unescape
from urllib.parse import quote

from bs4 import BeautifulSoup

from .common import EURO_FIRST_RE, get, log, dbg, parse_prices, to_int, year_of

SOURCES = {
    "ss": "ss.com",
    "moller": "Moller Auto",
    "autobrava": "Autobrava",
    "mg56": "MG56",
    "musa": "Mūsa Motors",
    "bravo": "Bravoauto",
    "autoscout": "AutoScout24",
}

MAKE_ALIASES = {
    "vw": "volkswagen", "mercedes": "mercedes-benz", "mercedes benz": "mercedes-benz",
    "škoda": "skoda", "citroën": "citroen", "land": "land rover", "range rover": "land rover",
    "bmw motorrad": "bmw-motorrad", "alfa": "alfa romeo",
}


def norm_make(s):
    m = (s or "").strip().lower().replace("_", " ").replace("-", " ")
    m = MAKE_ALIASES.get(m, m)
    return m.replace(" ", "-") if m in ("mercedes-benz",) else m


def clean(t):
    return re.sub(r"\s+", " ", unescape(t or "")).strip()


def _soup(r):
    return BeautifulSoup(r.text, "html.parser") if r is not None else None


# =============================================================== ss.com
SS_BASE = "https://www.ss.com/lv/transport/cars/sell/"


def ss_list(pages, price_max, year_min):
    cars, seen = [], set()
    for page in range(1, pages + 1):
        r = get(SS_BASE if page == 1 else f"{SS_BASE}page{page}.html")
        if not r:
            break
        soup = _soup(r)
        rows = [tr for tr in soup.select("tr[id^=tr_]") if not tr["id"].startswith("tr_bnr")]
        new = 0
        for tr in rows:
            a = tr.find("a", href=re.compile(r"/msg/"))
            if not a:
                continue
            link = a["href"] if a["href"].startswith("http") else "https://www.ss.com" + a["href"]
            key = "ss:" + link.split("/msg/")[-1]
            if key in seen:
                continue
            seen.add(key)
            new += 1
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(cells) < 6:
                continue
            prices = parse_prices(cells[-1])
            if not prices or prices[0] > price_max:
                continue
            year = to_int(cells[4]) if re.fullmatch(r"\d{4}", cells[4] or "") else None
            if year and year_min and year < year_min:
                continue
            path = link.split("/cars/")[-1].split("/")
            km_cell = cells[6] if len(cells) > 7 else ""
            km = to_int(km_cell) * 1000 if "tūkst" in km_cell and to_int(km_cell) else to_int(km_cell)
            img = tr.find("img", src=re.compile(r"i\.ss\.com"))
            cars.append({
                "key": key, "source": "ss", "url": link, "title": cells[3] or " ".join(path[:2]).title(),
                "make": norm_make(path[0] if path else ""), "year": year, "km": km, "price": prices[0],
                "img": img["src"] if img else "", "fuel_text": cells[5], "text": cells[2],
            })
        dbg(f"ss lapa {page}: {len(rows)} rindas, {new} jaunas")
        if new == 0:   # aiz pēdējās lapas ss.com rāda atkal pirmo
            break
    log(f"  ss.com: {len(seen)} sludinājumi, {len(cars)} atbilst cenai un gadam")
    return cars, seen


def ss_detail(car):
    r = get(car["url"])
    if not r or "/msg/" not in r.url:
        return None
    soup = _soup(r)
    out = {}
    box = soup.find(id="msg_div_msg")
    parts = []
    if box:
        spec = box.find(id="msg_div_spec")
        if spec:
            # aprīkojuma sarakstā ir visas iespējamās opcijas; auto ir tikai treknrakstā atzīmētās
            parts.append(" ".join(b.get_text(" ", strip=True) for b in spec.select("b.auto_c")))
            spec.decompose()
        parts.append(box.get_text(" ", strip=True))
    out["text"] = clean(" ".join(parts))
    fields = {tid: soup.find(id=tid) for tid in ("tdo_8", "tdo_15", "tdo_16", "tdo_18", "tdo_32", "tdo_35")}
    val = {k: (v.get_text(" ", strip=True) if v else "") for k, v in fields.items()}
    p = parse_prices(val["tdo_8"])
    if p:
        out["price"] = p[0]
    out["fuel_text"] = val["tdo_15"]
    out["gear_text"] = val["tdo_35"]
    out["body_text"] = val["tdo_32"]
    if val["tdo_16"]:
        out["km"] = to_int(val["tdo_16"])
    if val["tdo_18"]:
        out["year"] = year_of(val["tdo_18"])
    img = re.search(r"https://i\.ss\.com/gallery/[^\"' ]+?\.(?:t|th2|800)\.jpg", r.text)
    if img:
        out["img"] = img.group(0)
    return out


# ========================================================= Moller Auto
MOLLER_BASE = "https://mollerauto.lv/lv/used-cars.html"
MOLLER_ID_RE = re.compile(r"/lv/(\d{6,})\.html")


def moller_list(price_max):
    cars, seen_ids, ok = [], set(), False
    for page in range(1, 120):
        r = get(MOLLER_BASE, params={"product_list_order": "price", "product_list_dir": "asc", "p": page})
        if not r:
            break
        soup = _soup(r)
        page_cards = {}
        for a in soup.find_all("a", href=MOLLER_ID_RE):
            cid = MOLLER_ID_RE.search(a["href"]).group(1)
            if cid in page_cards:
                continue
            node = a
            for _ in range(8):
                node = node.parent
                if node is None or "€" in node.get_text(" ", strip=True):
                    break
            if node is None or len(set(MOLLER_ID_RE.findall(str(node)))) > 1:
                continue
            text = node.get_text(" ", strip=True)
            prices = parse_prices(text)
            if not prices:
                continue
            head = re.split(r"\d[\d\s]*,\d{2}\s*€", text)[0]
            head = re.sub(r"^(?:(?:Garantija|Jaunums|Akcija|Rezervēts)\s+)+", "", head).strip()
            m = re.match(r"(.*?)\s+((?:19|20)\d{2}),\s*(.*)$", head)
            title, year, spec = (m.group(1), int(m.group(2)), m.group(3)) if m else (head, None, "")
            lis = [li.get_text(" ", strip=True) for li in node.find_all("li")]
            km = next((to_int(x) for x in lis if x.endswith("km")), None)
            drive = next((x for x in lis if "piedziņa" in x), "")
            gear = next((x for x in lis if "pārnesumkārba" in x), "")
            fuel = lis[1] if len(lis) > 1 else spec
            img = node.find("img", src=re.compile(r"/media/catalog/product/"))
            page_cards[cid] = {
                "key": f"moller:{cid}", "source": "moller", "url": f"https://mollerauto.lv/lv/{cid}.html",
                "title": title, "make": norm_make(title.split(" ")[0]), "year": year, "km": km,
                "price": min(prices), "img": img["src"] if img else "", "fuel_text": f"{spec} {fuel}",
                "drive_text": drive, "gear_text": gear, "text": text,
            }
        new = [c for k, c in page_cards.items() if k not in seen_ids]
        if not new:
            break
        ok = True
        for c in new:
            seen_ids.add(c["key"].split(":")[1])
            if c["price"] <= price_max:
                cars.append(c)
        if min(c["price"] for c in page_cards.values()) > price_max:
            break
    log(f"  Moller Auto: {len(cars)} auto līdz cenai")
    return cars, ok


def moller_detail(car):
    r = get(car["url"])
    if not r:
        return None
    soup = _soup(r)
    main = soup.find(id="maincontent") or soup.find("main") or soup
    text = main.get_text(" ", strip=True)
    for stop in ("Uzzināt vairāk", "Biežāk uzdotie jautājumi"):
        text = text.split(stop)[0]
    out = {"text": clean(text)}
    m = re.search(r"Piedziņa\s+(\S+)", text)
    if m:
        out["drive_text"] = m.group(1)
    return out


# ============================================================ Autobrava
BRAVA_URL = "https://mazlietoti.autobrava.lv/"


def autobrava_list():
    r = get(BRAVA_URL)
    if not r:
        return [], False
    soup = _soup(r)
    cars = {}
    for a in soup.find_all("a", href=re.compile(r"/automasina/[^/]+/?$")):
        slug = a["href"].rstrip("/").split("/")[-1]
        if f"autobrava:{slug}" in cars:
            continue
        node = a
        for _ in range(10):
            node = node.parent
            if node is None:
                break
            t = node.get_text(" ", strip=True)
            if "Pārdošanas cena" in t and "Gads" in t:
                break
        if node is None:
            continue
        if len({x["href"].rstrip("/") for x in node.find_all("a", href=re.compile(r"/automasina/"))}) > 1:
            continue
        t = node.get_text(" | ", strip=True)
        flat = t.replace(" | ", " ")
        price = None
        for label in ("Autobrava cena", "Pārdošanas cena"):
            m = re.search(label + r"\s*([\d\s]+)\s*€", flat)
            if m:
                price = to_int(m.group(1))
                break
        if not price:
            continue
        title = clean(a.get("title") or "")
        lines = [x.strip() for x in t.split("|")]
        year = km = None
        if "Gads" in lines and lines.index("Gads") + 1 < len(lines):
            year = year_of(lines[lines.index("Gads") + 1])
        if "Nobraukums" in lines and lines.index("Nobraukums") + 1 < len(lines):
            km = to_int(lines[lines.index("Nobraukums") + 1])
        # modeļa rindiņa beidzas ar piedziņu, piem. "ZS Hybrid+ FWD"
        drive = next((x.split()[-1] for x in lines if re.search(r"\b(FWD|RWD|AWD|4WD)$", x)), "")
        fuel = next((x for x in lines if re.fullmatch(
            r"(benzīns|dīzelis|elektro|hibrīds|gāze)( / (hybrid|hibrīds|gāze|elektro))?", x, re.I)), "")
        gear = next((x for x in lines if x in ("Automāts", "Manuāla")), "")
        img = node.find("img", src=re.compile(r"/wp-content/uploads/"))
        make = lines[1] if len(lines) > 1 and not lines[0][0].isupper() else ""
        cars[f"autobrava:{slug}"] = {
            "key": f"autobrava:{slug}", "source": "autobrava", "url": a["href"],
            "title": title or lines[0], "make": norm_make((title or make).split(" ")[0]),
            "year": year, "km": km, "price": price, "img": img["src"] if img else "",
            "fuel_text": fuel, "drive_text": drive, "gear_text": gear, "text": flat,
        }
    log(f"  Autobrava: {len(cars)} auto")
    return list(cars.values()), bool(cars)


def autobrava_detail(car):
    r = get(car["url"])
    if not r:
        return None
    soup = _soup(r)
    main = soup.find("main") or soup.body or soup
    text = clean(main.get_text(" ", strip=True))
    out = {"text": text}
    m = re.search(r"\b(FWD|RWD|AWD|4WD)\b", text)
    if m:
        out["drive_text"] = m.group(1)
    return out


# ================================================================ MG56
MG56_URL = "https://mg56.lv/collections/frontpage/products.json"


def mg56_list():
    data = get(MG56_URL, params={"limit": 250}, as_json=True)
    if not data:
        return [], False
    cars = []
    for p in data.get("products", []):
        tags = [t.lower() for t in p.get("tags", [])]
        variant = (p.get("variants") or [{}])[0]
        if "sold" in tags or variant.get("available") is False:   # pārdotie auto ir "nav pieejams"
            continue
        try:
            price = int(float(p["variants"][0]["price"]))
        except (KeyError, IndexError, ValueError, TypeError):
            continue
        body = clean(re.sub(r"<[^>]+>", " | ", p.get("body_html") or ""))
        km = re.search(r"([\d\s]+)\s*km", body)
        title = clean(p.get("title"))
        cars.append({
            "key": f"mg56:{p['handle']}", "source": "mg56", "url": f"https://mg56.lv/products/{p['handle']}",
            "title": title, "make": norm_make(p.get("vendor") or title.split(" ")[0]),
            "year": year_of(body), "km": to_int(km.group(1)) if km else None, "price": price,
            "img": (p.get("images") or [{}])[0].get("src", ""),
            "fuel_text": body, "text": f"{title} | {body}",
            "detail_done": True,   # MG56 nav atsevišķas detaļu lapas ar vairāk datiem
        })
    log(f"  MG56: {len(cars)} pieejami auto")
    return cars, True


# =========================================================== Mūsa Motors
MUSA_URL = "https://lietotiauto.musamotors.lv/lv/filter"


def musa_list():
    cars, ok = {}, False
    for page in range(1, 40):
        r = get(MUSA_URL, params={"page": page})
        if not r:
            break
        soup = _soup(r)
        new = 0
        for a in soup.find_all("a", href=re.compile(r"/lv/details/\d+")):
            cid = re.search(r"/details/(\d+)", a["href"]).group(1)
            key = f"musa:{cid}"
            if key in cars:
                continue
            t = a.get_text(" | ", strip=True)
            flat = t.replace(" | ", " ")
            parts = [x.strip() for x in t.split("|")]
            year_idx = next((i for i, x in enumerate(parts) if re.fullmatch(r"(19|20)\d{2}", x)), None)
            if year_idx is None:
                continue
            before_month = flat.split("Mēneša")[0]
            prices = [to_int(m.group(1)) for m in EURO_FIRST_RE.finditer(before_month)]
            prices = [p for p in prices if p and p > 300]
            if not prices:
                continue
            title = " ".join(parts[:year_idx])
            spec = parts[year_idx + 1] if len(parts) > year_idx + 1 else ""
            gear = parts[year_idx + 2] if len(parts) > year_idx + 2 else ""
            km = next((to_int(x) for x in parts if x.endswith("km")), None)
            kw = re.search(r"(\d+)\s*kW", flat)
            img = a.find("img")
            url = a["href"] if a["href"].startswith("http") else "https://lietotiauto.musamotors.lv" + a["href"]
            cars[key] = {
                "key": key, "source": "musa", "url": url, "title": title,
                "make": norm_make(title.split(" ")[0]), "year": int(parts[year_idx]), "km": km,
                "price": min(prices), "img": img["src"] if img else "", "fuel_text": spec,
                "gear_text": gear, "power_kw": int(kw.group(1)) if kw else None, "text": flat,
            }
            new += 1
        ok = ok or new > 0
        if new == 0:
            break
    log(f"  Mūsa Motors: {len(cars)} auto")
    return list(cars.values()), ok


def musa_detail(car):
    r = get(car["url"])
    if not r:
        return None
    soup = _soup(r)
    main = soup.find("main") or soup.body or soup
    text = clean(main.get_text(" ", strip=True))
    return {"text": text.split("Norādītājam komplektācijas")[0][:5000]}


# ============================================================= Bravoauto
BRAVO_URL = "https://bravo-auto.lv/auto"


def bravo_list():
    r = get(BRAVO_URL, params={"orderby": "price,asc", "pageSize": 500, "pageIndex": 1})
    if not r:
        return [], False
    soup = _soup(r)
    cars = {}
    for li in soup.select("li.cards-car"):
        a = li.find("a", href=re.compile(r"^/auto/[^/]+/[^/]+"))
        if not a:
            continue
        href = a["href"]
        key = "bravo:" + href.rstrip("/").split("/")[-1]
        parts = [x.strip() for x in li.get_text(" | ", strip=True).split("|")]
        flat = " ".join(parts)
        m = EURO_FIRST_RE.search(flat)
        if not m:
            continue
        year_idx = next((i for i, x in enumerate(parts) if re.fullmatch(r"(19|20)\d{2}", x)), None)
        km = next((to_int(x) for x in parts if re.search(r"\bkm$", x, re.I)), None)
        body = ""
        if "Salīdzināt" in parts:
            body = parts[parts.index("Salīdzināt") - 1]
        img = li.find("img")
        cars[key] = {
            "key": key, "source": "bravo", "url": "https://bravo-auto.lv" + href,
            "title": f"{parts[0]} {parts[1]}" if len(parts) > 1 else parts[0], "make": norm_make(parts[0]),
            "year": int(parts[year_idx]) if year_idx is not None else None, "km": km,
            "price": to_int(m.group(1)), "img": img.get("src", "") if img else "",
            "fuel_text": parts[year_idx + 1] if year_idx is not None and len(parts) > year_idx + 1 else "",
            "gear_text": parts[year_idx + 2] if year_idx is not None and len(parts) > year_idx + 2 else "",
            "body_text": body, "text": flat,
        }
    log(f"  Bravoauto: {len(cars)} auto")
    return list(cars.values()), bool(cars)


def bravo_detail(car):
    r = get(car["url"])
    if not r:
        return None
    soup = _soup(r)
    main = soup.find("main") or soup.body or soup
    text = clean(main.get_text(" ", strip=True))
    out = {"text": text[:6000]}
    m = re.search(r"\b(FWD|RWD|AWD|4WD|4x4)\b", text)
    if m:
        out["drive_text"] = m.group(1)
    return out


# ========================================================== AutoScout24
AS_BASE = "https://www.autoscout24.de"
AS_FUEL = {"petrol": ["B"], "diesel": ["D"], "electric": ["E"], "phev": ["2", "3"], "hybrid": ["2", "3"],
           "lpg": ["L", "C"]}


def _next_data(html):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def autoscout_url(f, page):
    makes = f.get("makes") or []
    path = "/lst"
    if len(makes) == 1:
        path += "/" + quote(makes[0].lower().replace(" ", "-"))
    params = {"atype": "C", "cy": ",".join(f.get("as_countries") or ["D"]), "sort": "age", "desc": "1",
              "ustate": "N,U", "page": page}
    if f.get("watch_max") or f.get("price_max"):
        params["priceto"] = f.get("watch_max") or f.get("price_max")
    if f.get("price_min"):
        params["pricefrom"] = f["price_min"]
    if f.get("year_min"):
        params["fregfrom"] = f["year_min"]
    if f.get("year_max"):
        params["fregto"] = f["year_max"]
    if f.get("km_max"):
        params["kmto"] = f["km_max"]
    if f.get("power_min"):
        params["powerfrom"] = f["power_min"]
        params["powertype"] = "kw"
    fuels = sorted({c for x in (f.get("fuel") or []) for c in AS_FUEL.get(x, [])})
    if fuels:
        params["fuel"] = ",".join(fuels)
    if f.get("gearbox") == ["auto"]:
        params["gear"] = "A"
    elif f.get("gearbox") == ["manual"]:
        params["gear"] = "M"
    return AS_BASE + path + "?" + "&".join(f"{k}={quote(str(v), safe=',')}" for k, v in params.items())


def autoscout_list(f, pages):
    cars = {}
    for page in range(1, pages + 1):
        r = get(autoscout_url(f, page))
        data = _next_data(r.text) if r else None
        if not data:
            break
        pp = data.get("props", {}).get("pageProps", {})
        listings = pp.get("listings") or []
        for x in listings:
            v = x.get("vehicle", {})
            key = f"autoscout:{x.get('id')}"
            reg = (x.get("tracking") or {}).get("firstRegistration") or ""
            km = to_int(v.get("mileageInKm"))
            details = " ".join(d.get("data", "") for d in x.get("vehicleDetails") or [])
            kw = re.search(r"(\d+)\s*kW", details)
            title = clean(f"{v.get('make', '')} {v.get('model', '')} {v.get('modelVersionInput') or ''}")
            cars[key] = {
                "key": key, "source": "autoscout", "url": AS_BASE + x.get("url", ""),
                "title": title, "make": norm_make(v.get("make")), "year": year_of(reg), "km": km,
                "price": (x.get("price") or {}).get("priceRaw"), "img": (x.get("images") or [""])[0],
                "fuel_text": v.get("fuel", ""), "gear_text": v.get("transmission", ""),
                "power_kw": int(kw.group(1)) if kw else None,
                "text": clean(f"{title} {v.get('subtitle') or ''} {details}"),
                "country": (x.get("location") or {}).get("countryCode", ""),
            }
        if page >= (pp.get("numberOfPages") or 1):
            break
    log(f"  AutoScout24: {len(cars)} auto")
    return list(cars.values())


def autoscout_detail(car):
    r = get(car["url"])
    data = _next_data(r.text) if r else None
    if not data:
        return None
    d = data.get("props", {}).get("pageProps", {}).get("listingDetails") or {}
    v = d.get("vehicle") or {}
    equip = []
    for items in (v.get("equipment") or {}).values():
        equip += [i.get("id", "") for i in items or []]
    fuels = " ".join(str(x) for x in [v.get("fuelCategory"), v.get("primaryFuel"), v.get("allFuelTypes")])
    desc = clean(re.sub(r"<[^>]+>", " ", d.get("description") or ""))[:3000]
    out = {
        "text": clean(f"{v.get('modelVersionInput') or ''} {' | '.join(equip)} {desc}"),
        "drive_text": v.get("driveTrain") or "", "fuel_text": f"{car.get('fuel_text', '')} {fuels}",
        "gear_text": v.get("transmissionType") or "", "body_text": v.get("bodyType") or "",
    }
    price = (d.get("prices") or {}).get("public", {}).get("priceRaw") if isinstance(d.get("prices"), dict) else None
    price = price or (d.get("price") or {}).get("priceRaw") if isinstance(d.get("price"), dict) else price
    if price:
        out["price"] = int(price)
    if v.get("firstRegistrationDateRaw"):
        out["year"] = year_of(v["firstRegistrationDateRaw"])
    return out


DETAIL = {
    "ss": ss_detail, "moller": moller_detail, "autobrava": autobrava_detail,
    "musa": musa_detail, "bravo": bravo_detail, "autoscout": autoscout_detail,
}
