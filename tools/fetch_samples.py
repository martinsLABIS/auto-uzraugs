"""Diagnostika: saglabā paraugu lapas, lai varētu pārbaudīt parsēšanu."""
import json, os, re, time, requests
from pathlib import Path
out = Path("debug_out/samples"); out.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
     "Accept-Language": "lv,en;q=0.8"}
urls = {"ss_list_p1.html": "https://www.ss.com/lv/transport/cars/sell/",
        "ss_list_p2.html": "https://www.ss.com/lv/transport/cars/sell/page2.html",
        "moller_list_p1.html": "https://mollerauto.lv/lv/used-cars.html?product_list_order=price&product_list_dir=asc&p=1"}
st = json.load(open("state.json")) if Path("state.json").exists() else {"tracked": {}}
i = 0
for k, v in st.get("tracked", {}).items():
    if k.startswith("ss:") and i < 6:
        urls[f"ss_detail_{i}.html"] = v["url"]; i += 1
    if k.startswith("moller:"):
        urls[f"moller_detail_{k.split(':')[1]}.html"] = v["url"]
for name, u in urls.items():
    try:
        r = requests.get(u, headers=H, timeout=30)
        (out / name).write_bytes(r.content)
        print(name, r.status_code, len(r.content), r.url)
    except Exception as e:
        print(name, "ERR", e)
    time.sleep(1.5)
