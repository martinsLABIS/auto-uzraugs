"""Diagnostika: pārbauda, vai portāli ļauj nolasīt lapas no GitHub servera."""
import json, re, time, requests
from pathlib import Path
out = Path("debug_out/probe"); out.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
     "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
     "Accept-Language": "lv,en;q=0.8,de;q=0.6"}
URLS = {
 "auto24_lv": "https://www.auto24.lv/",
 "auto24_lv_list": "https://www.auto24.lv/lietoti/saraksts.php?bn=2&a=100",
 "auto24_ee_list": "https://www.auto24.ee/kasutatud/nimekiri.php?bn=2&a=100",
 "autoplius": "https://autoplius.lt/skelbimai/naudoti-automobiliai",
 "mobile_de": "https://suchen.mobile.de/fahrzeuge/search.html?isSearchRequest=true&s=Car&vc=Car",
 "mobile_de_m": "https://m.mobile.de/auto/search.html?isSearchRequest=true&s=Car&vc=Car",
 "autoscout24": "https://www.autoscout24.com/lst?atype=C&cy=D",
 "autoscout24_de": "https://www.autoscout24.de/lst?atype=C",
 "bravo": "https://bravo-auto.lv/auto?orderby=price%2Casc&pageSize=12&pageIndex=1",
 "mg56_json": "https://mg56.lv/collections/frontpage/products.json?limit=250",
 "musa": "https://lietotiauto.musamotors.lv/lv/filter",
 "autobrava": "https://mazlietoti.autobrava.lv/",
 "ss": "https://www.ss.com/lv/transport/cars/sell/",
 "moller": "https://mollerauto.lv/lv/used-cars.html",
}
BLOCK = re.compile(r"captcha|access denied|are you a robot|cf-chl|challenge-platform|datadome|perimeterx|px-captcha|unusual traffic|blocked", re.I)
rep = {}
for k, u in URLS.items():
    try:
        r = requests.get(u, headers=H, timeout=30, allow_redirects=True)
        body = r.text
        (out / f"{k}.html").write_text(body, "utf-8")
        title = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
        rep[k] = {"status": r.status_code, "len": len(body), "final": r.url,
                  "title": (title.group(1).strip()[:100] if title else ""),
                  "block_words": sorted(set(m.group(0).lower() for m in BLOCK.finditer(body)))[:6]}
    except Exception as e:
        rep[k] = {"error": str(e)[:200]}
    print(k, rep[k], flush=True)
    time.sleep(1.5)
(out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), "utf-8")
