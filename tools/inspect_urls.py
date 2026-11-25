"""Diagnostika: parāda, kuri vārdi sludinājumā izraisīja atbilstību."""
import os, sys
sys.path.insert(0, ".")
import auto_monitor as m
out = []
for u in os.getenv("URLS", "").split():
    text, price = m.ss_detail(u)
    text = text or ""
    model = " ".join(u.split("/cars/")[-1].split("/")[:2]).replace("-", " ")
    out.append(f"== {m.classify(text, model)} | {price} | {u}")
    if os.getenv("COMPACT"):
        continue
    for name, rx in (("PLUG", m.PLUGIN_RE), ("AWD", m.AWD_RE), ("IV", m.SKODA_IV_RE)):
        for x in list(rx.finditer(text))[:4]:
            out.append(f"  {name}: …{text[max(0, x.start()-70):x.end()+50]}…")
open("debug_out/inspect.txt", "w").write("\n".join(out))
print("\n".join(out))
