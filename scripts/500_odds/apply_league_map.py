# -*- coding: utf-8 -*-
"""把 gen_league_map.py 的自动映射写入 match_pinnacle_v2.LEAGUE_HINT。

生成一个外置 JSON（league_hint_auto.json），由 match_pinnacle_v2 在启动时加载，
避免手工改代码。
"""
import csv
import json
import os

SRC = r"D:\cl\qqsj_v2\league_map_auto.csv"
DST = r"D:\cl\qqsj_v2\league_hint_auto.json"

out = {}
with open(SRC, encoding="utf-8") as f:
    for r in csv.DictReader(f):
        zh = (r.get("league_zh") or "").strip()
        pl = (r.get("pinn_league") or "").strip()
        if zh and pl:
            out[zh] = [pl]

with open(DST, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

print(f"写入 {len(out)} 条自动联赛映射 → {DST}")
for k in list(out)[:5]:
    print(f"  {k} -> {out[k]}")
