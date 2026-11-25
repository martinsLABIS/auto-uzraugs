"""Auto meklētājs: izpilda visus meklējumus no docs/searches.json.

Palaišana:  python -m finder.run
Vides mainīgie: NTFY_TOPIC, DRY_RUN=1 (bez paziņojumiem), DEBUG=1, FULL_SCAN=1,
STATE_FILE (noklusējums finder_state.json), SITE_DIR (noklusējums docs), DETAIL_LIMIT.
"""
import json
import os
import re
import time
from pathlib import Path

import requests

from . import sources as S
from .common import (dbg, detect_body, detect_drive, detect_fuel, detect_gearbox, fmt_price, log,
                     now_iso)
from .equipment import catalog, detect_equipment

SITE_DIR = Path(os.getenv("SITE_DIR", "docs"))
SEARCH_FILE = Path(os.getenv("SEARCH_FILE", str(SITE_DIR / "searches.json")))
STATE_FILE = Path(os.getenv("STATE_FILE", "finder_state.json"))
OLD_STATE = Path("state.json")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "").strip()
NTFY_SERVER = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"
FULL_SCAN = os.getenv("FULL_SCAN", "0") == "1"
DETAIL_LIMIT = int(os.getenv("DETAIL_LIMIT", "150"))
RECHECK_LIMIT = int(os.getenv("RECHECK_LIMIT", "60"))
SS_PAGES = int(os.getenv("SS_PAGES", "5"))
AS_PAGES = int(os.getenv("AS_PAGES", "2"))
STATE_VERSION = 1
FULL_LIST_SOURCES = {"moller", "autobrava", "mg56", "musa", "bravo"}   # avoti, kur redzams viss saraksts


# ------------------------------------------------------------ stāvoklis
def load_json(path, default):
    try:
        return json.loads(Path(path).read_text("utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def load_state():
    st = load_json(STATE_FILE, None)
    if st and st.get("version") == STATE_VERSION:
        return st
    st = {"version": STATE_VERSION, "details": {}, "cars": {}, "searches": {}}
    # pārņem iepriekšējā uzrauga (plug-in 4x4) atrastos auto, lai par tiem nepienāk atkārtoti paziņojumi
    old = load_json(OLD_STATE, {})
    if old.get("tracked"):
        tr = {}
        for key, c in old["tracked"].items():
            tr[key] = {"price": c["price"], "history": c.get("history") or [[c.get("first_seen", now_iso())[:10], c["price"]]],
                       "first_seen": c.get("first_seen", now_iso()), "last_seen": c.get("last_seen", now_iso()),
                       "silent": True}
            st["cars"][key] = {"key": key, "source": "ss" if key.startswith("ss:") else "moller", "url": c["url"],
                               "title": re.sub(r"\s(19|20)\d{2}$", "", c["title"]), "year": c.get("year"),
                               "km": c.get("km"), "img": c.get("img", ""), "price": c["price"]}
        st["searches"]["plugin4x4"] = {"tracked": tr, "seeded": ["ss", "moller"], "baseline": min(
            (v["first_seen"] for v in tr.values()), default=now_iso())}
        log(f"Pārņemti {len(tr)} auto no iepriekšējā uzrauga")
    return st


def save_state(st):
    cutoff = time.time() - 30 * 86400
    st["details"] = {k: v for k, v in st["details"].items() if v.get("ts", 0) > cutoff}
    tracked_keys = {k for s in st["searches"].values() for k in s.get("tracked", {})}
    st["cars"] = {k: v for k, v in st["cars"].items() if k in tracked_keys}
    STATE_FILE.write_text(json.dumps(st, ensure_ascii=False, separators=(",", ":")), "utf-8")


# ------------------------------------------------------------ paziņojumi
def notify(title, message, url=None, tags=None, priority=3):
    if DRY_RUN or not NTFY_TOPIC:
        log(f"  [paziņojums] {title}: {message}")
        return
    payload = {"topic": NTFY_TOPIC, "title": title, "message": message, "tags": tags or ["car"],
               "priority": priority}
    if url:
        payload["click"] = url
        payload["actions"] = [{"action": "view", "label": "Atvērt sludinājumu", "url": url}]
    try:
        requests.post(NTFY_SERVER, json=payload, timeout=20).raise_for_status()
    except requests.RequestException as e:
        log(f"ntfy kļūda: {e}")


# ------------------------------------------------------- auto īpašības
def enrich(car, det):
    """Apvieno saraksta un sludinājuma datus, nosaka degvielu, piedziņu u. c."""
    c = dict(car)
    if det:
        for k in ("price", "img", "year", "km"):
            if det.get(k) and (k == "price" or not c.get(k)):
                c[k] = det[k]
    d = det or {}
    model = f"{c.get('make', '')} {c.get('title', '')}"
    full = " ".join(x for x in (c.get("title"), c.get("text"), d.get("text")) if x)
    fuel_txt = " ".join(x for x in (c.get("fuel_text"), d.get("fuel_text")) if x)
    c["fuel"] = detect_fuel(fuel_txt, full, model)
    c["drive"] = detect_drive(d.get("drive_text") or c.get("drive_text"), full, model, c["fuel"])
    c["gearbox"] = detect_gearbox(d.get("gear_text") or c.get("gear_text"), full)
    c["body"] = detect_body(d.get("body_text") or c.get("body_text"), f"{c.get('title', '')} {c.get('text', '')}")
    c["equipment"] = sorted(detect_equipment(full))
    c["full"] = full.lower()
    c["final"] = bool(det) or bool(c.get("detail_done"))
    return c


def terms(s):
    return [t.strip().lower() for t in re.split(r"[,;]", s or "") if t.strip()]


def evaluate(c, f):
    """True – atbilst, False – neatbilst, None – jāatver sludinājums, lai izlemtu."""
    final = c["final"]
    price = c.get("price")
    watch = f.get("watch_max") or f.get("price_max")
    if not price or (watch and price > watch) or (f.get("price_min") and price < f["price_min"]):
        return False
    for key, lo, hi in (("year", "year_min", "year_max"), ("km", None, "km_max")):
        v = c.get(key)
        if (lo and f.get(lo)) or (hi and f.get(hi)):
            if v is None:
                if final:
                    return False
                return None
            if lo and f.get(lo) and v < f[lo]:
                return False
            if hi and f.get(hi) and v > f[hi]:
                return False
    if f.get("power_min") and c.get("power_kw") and c["power_kw"] < f["power_min"]:
        return False
    makes = [S.norm_make(m) for m in f.get("makes") or []]
    if makes and c.get("make") not in makes:
        return False
    title = (c.get("title") or "").lower()
    models = terms(f.get("model"))
    if models and not any(m in title or m in c["full"][:300] for m in models):
        return False
    if any(x in c["full"] for x in terms(f.get("exclude"))):
        return False
    undecided = False
    kws = terms(f.get("keywords"))
    if kws and not all(k in c["full"] for k in kws):
        if final:
            return False
        undecided = True
    want = f.get("fuel") or []
    if want and c.get("fuel") not in want:
        maybe = c.get("fuel") is None or (c.get("fuel") == "hybrid" and "phev" in want)
        if final or not maybe:
            return False
        undecided = True
    for field in ("drive", "gearbox", "body"):
        want = f.get(field) or []
        if want and c.get(field) not in want:
            if final or c.get(field) is not None:
                return False
            undecided = True
    req = f.get("equipment") or []
    if req:
        have = len(set(req) & set(c.get("equipment") or []))
        need = len(req) if f.get("equipment_mode", "all") == "all" else max(1, -(-len(req) * 7 // 10))
        if have < need:
            if final:
                return False
            undecided = True
    return None if undecided else True


# ---------------------------------------------------------- galvenā daļa
def main():
    started = time.time()
    cfg = load_json(SEARCH_FILE, {"searches": []})
    searches = [s for s in cfg.get("searches", []) if s.get("active", True)]
    st = load_state()
    log(f"Sākums {now_iso()} | meklējumi: {', '.join(s['name'] for s in searches) or 'nav'}")
    if not searches:
        write_site(cfg, st)
        save_state(st)
        return

    for s in searches:
        st["searches"].setdefault(s["id"], {"tracked": {}, "seeded": [], "baseline": now_iso()})
    need = {src for s in searches for src in s.get("sources", [])}
    unseeded = {src for s in searches for src in s.get("sources", [])
                if src not in st["searches"][s["id"]]["seeded"]}

    def fmax(key, default=None):
        vals = [(s["filters"].get("watch_max") or s["filters"].get(key)) for s in searches]
        return None if any(v is None for v in vals) else max(vals) if vals else default

    price_cap = fmax("price_max") or 10_000_000
    year_vals = [s["filters"].get("year_min") for s in searches]
    year_floor = None if any(v is None for v in year_vals) else min(year_vals)

    # 1) saraksti
    listed, ok_sources, seen_paged = {}, set(), set()
    if "ss" in need:
        pages = 400 if (FULL_SCAN or "ss" in unseeded) else SS_PAGES
        log(f"ss.com (līdz {pages} lapām) …")
        cars, seen = S.ss_list(pages, price_cap, year_floor)
        listed.update({c["key"]: c for c in cars})
        seen_paged |= seen
        ok_sources.add("ss") if seen else None
    simple = {"moller": lambda: S.moller_list(price_cap), "autobrava": S.autobrava_list,
              "mg56": S.mg56_list, "musa": S.musa_list, "bravo": S.bravo_list}
    for src, fn in simple.items():
        if src in need:
            log(f"{S.SOURCES[src]} …")
            cars, ok = fn()
            if ok:
                ok_sources.add(src)
            listed.update({c["key"]: c for c in cars})
    as_by_search = {}
    for s in searches:
        if "autoscout" in s.get("sources", []):
            seeded = "autoscout" in st["searches"][s["id"]]["seeded"]
            log(f"AutoScout24 meklējumam „{s['name']}” …")
            cars = S.autoscout_list(s["filters"], AS_PAGES if seeded and not FULL_SCAN else 5)
            as_by_search[s["id"]] = {c["key"] for c in cars}
            listed.update({c["key"]: c for c in cars})
            seen_paged |= as_by_search[s["id"]]
            if cars:
                ok_sources.add("autoscout")

    # 2) atlase ar sludinājumu atvēršanu, kur vajag
    details = st["details"]
    budget = [DETAIL_LIMIT]

    def get_detail(car):
        k = car["key"]
        if k in details:
            return details[k]
        fn = S.DETAIL.get(car["source"])
        if not fn or budget[0] <= 0 or car.get("detail_done"):
            return None
        budget[0] -= 1
        d = fn(car)
        if d is None:
            return None
        d["text"] = (d.get("text") or "")[:4000]
        d["ts"] = time.time()
        details[k] = d
        return d

    matches = {s["id"]: {} for s in searches}
    for s in searches:
        srcs = set(s.get("sources", []))
        for key, car in listed.items():
            if car["source"] not in srcs:
                continue
            if car["source"] == "autoscout" and key not in as_by_search.get(s["id"], set()):
                continue
            c = enrich(car, details.get(key))
            res = evaluate(c, s["filters"])
            if res is None:
                det = get_detail(car)
                if det:
                    c = enrich(car, det)
                    res = evaluate(c, s["filters"])
            dbg(f"  {s['name']}: {c.get('title')} {c.get('price')} -> {res}")
            if res:
                matches[s["id"]][key] = c

    # 3) zināmie auto lappušu avotos (ss, AutoScout24), kas šoreiz netika redzēti – pārbauda sludinājumu
    todo = []
    for s in searches:
        for key in st["searches"][s["id"]]["tracked"]:
            src = key.split(":")[0]
            if src in ("ss", "autoscout") and key not in seen_paged and key not in matches[s["id"]]:
                todo.append(key)
    todo = sorted(set(todo), key=lambda k: st["cars"].get(k, {}).get("last_checked", ""))
    gone = set()
    for key in todo[:RECHECK_LIMIT]:
        base = st["cars"].get(key)
        if not base:
            continue
        fn = S.DETAIL.get(key.split(":")[0])
        det = fn(base) if fn else None
        base["last_checked"] = now_iso()
        if det is None:
            gone.add(key)
            continue
        det["text"] = (det.get("text") or "")[:4000]
        det["ts"] = time.time()
        details[key] = det
        c = enrich(base, det)
        for s in searches:
            if key in st["searches"][s["id"]]["tracked"] and evaluate(c, s["filters"]):
                matches[s["id"]][key] = c
    log(f"Atvērti sludinājumi: {DETAIL_LIMIT - budget[0]} jauni, {min(len(todo), RECHECK_LIMIT)} pārbaudīti atkārtoti")

    # 4) izmaiņas, paziņojumi
    for s in searches:
        ss = st["searches"][s["id"]]
        tracked = ss["tracked"]
        f = s["filters"]
        notify_cfg = s.get("notify", {"new": True, "drop": True})
        limit = f.get("price_max") or 10_000_000
        silent_sources = set(s.get("sources", [])) - set(ss["seeded"])
        new_cars, drops = [], []
        for key, c in matches[s["id"]].items():
            prev = tracked.get(key)
            silent = c["source"] in silent_sources
            if prev is None:
                if c["price"] <= limit and not silent:
                    new_cars.append(c)
                hist = [[now_iso()[:10], c["price"]]]
                tracked[key] = {"price": c["price"], "history": hist, "first_seen": now_iso(),
                                "last_seen": now_iso(), "silent": silent}
            else:
                if c["price"] < prev["price"] and c["price"] <= limit:
                    drops.append((c, prev["price"]))
                if c["price"] != prev["price"]:
                    prev["history"] = (prev.get("history") or [])[-19:] + [[now_iso()[:10], c["price"]]]
                prev["price"] = c["price"]
                prev["last_seen"] = now_iso()
            keep = {k: c.get(k) for k in ("key", "source", "url", "title", "make", "year", "km", "price", "img",
                                          "fuel", "drive", "gearbox", "body", "equipment", "power_kw")}
            keep["last_checked"] = st["cars"].get(key, {}).get("last_checked", "")
            st["cars"][key] = keep
        # pārdotie vai noņemtie
        for key in list(tracked):
            src = key.split(":")[0]
            if key in gone or (src in FULL_LIST_SOURCES and src in ok_sources and key not in matches[s["id"]]):
                tracked.pop(key)
            elif src == "autoscout" and key not in matches[s["id"]] and key in seen_paged:
                tracked.pop(key)   # redzēts sarakstā, bet vairs neatbilst filtriem
            elif src == "ss" and key in seen_paged and key not in matches[s["id"]] and key in listed:
                tracked.pop(key)
        name = s["name"]
        if notify_cfg.get("new", True):
            for c in new_cars:
                notify(f"{name}: jauns {c['title']} {c.get('year') or ''}".strip(),
                       f"{fmt_price(c['price'])} · {S.SOURCES.get(c['source'], c['source'])}",
                       url=c["url"], tags=["car"], priority=4)
        if notify_cfg.get("drop", True):
            for c, old in drops:
                notify(f"{name}: lētāk {c['title']} {c.get('year') or ''}".strip(),
                       f"{fmt_price(old)} → {fmt_price(c['price'])} (−{fmt_price(old - c['price'])}) · "
                       f"{S.SOURCES.get(c['source'], c['source'])}",
                       url=c["url"], tags=["chart_with_downwards_trend"], priority=4)
        newly = [x for x in silent_sources if x in ok_sources]
        if newly:
            n = sum(1 for k, v in tracked.items() if v["price"] <= limit)
            names = ", ".join(S.SOURCES[x] for x in newly)
            notify(f"{name}: meklēšana sākta",
                   f"Pievienoti avoti: {names}. Pašlaik atbilst {n} auto. Turpmāk ziņošu par jauniem auto "
                   f"un cenu kritumiem.", tags=["white_check_mark"])
            ss["seeded"] = sorted(set(ss["seeded"]) | set(newly))
        log(f"„{name}”: atbilst {len(matches[s['id']])}, jauni {len(new_cars)}, lētāki {len(drops)}")

    # meklējumi, kas izdzēsti no saraksta
    ids = {s["id"] for s in cfg.get("searches", [])}
    for sid in list(st["searches"]):
        if sid not in ids:
            st["searches"].pop(sid)

    write_site(cfg, st)
    save_state(st)
    log(f"Gatavs ({int(time.time() - started)} s).")


def write_site(cfg, st):
    if not SITE_DIR.exists():
        return
    out = []
    for s in cfg.get("searches", []):
        ss = st["searches"].get(s["id"], {})
        cars = []
        for key, t in ss.get("tracked", {}).items():
            c = st["cars"].get(key)
            if not c:
                continue
            cars.append({**{k: c.get(k) for k in ("source", "url", "title", "year", "km", "img", "fuel", "drive",
                                                  "gearbox", "body", "equipment")},
                         "id": key, "price": t["price"], "history": t.get("history", []),
                         "first_seen": t.get("first_seen", ""), "baseline": t.get("silent", False)})
        cars.sort(key=lambda c: c["price"])
        out.append({"id": s["id"], "name": s["name"], "active": s.get("active", True),
                    "price_max": s["filters"].get("price_max"), "watch_max": s["filters"].get("watch_max"),
                    "cars": cars})
    data = {"updated": now_iso(), "sources": S.SOURCES, "equipment": catalog(), "searches": out}
    (SITE_DIR / "data2.json").write_text(json.dumps(data, ensure_ascii=False), "utf-8")


if __name__ == "__main__":
    main()
