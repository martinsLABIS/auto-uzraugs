"""Diagnostika: saglabā norādītās lapas (NAME=URL ar atstarpēm atdalīti)."""
import os, time, requests
from pathlib import Path
out = Path("debug_out/fetch"); out.mkdir(parents=True, exist_ok=True)
H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
     "Accept-Language": "lv,en;q=0.8,de;q=0.6"}
for item in os.getenv("URLS", "").split():
    name, url = item.split("=", 1)
    try:
        r = requests.get(url, headers=H, timeout=30)
        (out / name).write_bytes(r.content)
        print(name, r.status_code, len(r.content), r.url, flush=True)
    except Exception as e:
        print(name, "ERR", e)
    time.sleep(1.2)
