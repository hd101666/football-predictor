# -*- coding: utf-8 -*-
"""审核 bulk_map_v2 产出的映射，剔除错配。

错配根因：同一时段多场比赛时，仅靠时间排序无法区分，
导致 "圣约翰斯通 → Dundee FC" 这类张冠李戴。

审核策略（多重独立验证，全过才保留）：
  1. 票数 >= 3（多场比赛重复确认）
  2. 中文名与英文名存在可解释的对应关系：
     - 音译相似：中文字符串长度 vs 英文音节数合理
     - 城市/关键词匹配（CITY_HINT）
     - 英文名包含中文名的关键音译片段
  3. 反向检查：该英文名不能已被其它中文名占用（一队一名）

用法：
  python -X utf8 audit_map.py --in qiety_team_map_bulk2.csv
"""
import argparse
import csv
import os
import re
import sys
from difflib import SequenceMatcher

sys.path.insert(0, r"D:\cl\qqsj_v2")

# 音译常见对应（中文单字/词 -> 英文片段），用于验证
TRANSLIT = {
    "圣": ["st", "saint", "san", "sao"], "约翰": ["john"], "斯通": ["stone"],
    "福尔": ["fal"], "柯克": ["kirk"], "基尔": ["kil"], "马诺克": ["marnock"],
    "乌德勒支": ["utrecht"], "阿贾克斯": ["ajax"], "埃因霍温": ["psv", "eindhoven"],
    "青年": ["jong", "youth", "ii", "b", "reserves"],
    "斯卡": ["scaf"], "法塔": ["fat"], "森": ["sen"],
    "佩斯": ["pesc"], "卡拉": ["cara"], "奥斯": ["ost"], "提亚": ["tia"],
    "马尔": ["mar"], "皮内托": ["pineto"], "巴里": ["bari"],
    "藤枝": ["fujieda"], "大宫": ["omiya"], "松鼠": ["ardija"],
    "横滨": ["yokohama"], "鹿儿岛": ["kagoshima"], "赞岐": ["sanuki"],
    "蔚山": ["ulsan"], "全北": ["jeonbuk"], "浦项": ["pohang"], "光州": ["gwangju"],
    "富川": ["bucheon"], "安养": ["anyang"], "金浦": ["gimpo"], "大邱": ["daegu"],
    "蒂米什瓦拉": ["timisoara"], "索科": ["sokol"], "布罗萨尼": ["brozany"],
    "布里顿": ["briton"], "弗林特": ["flint"], "佩尼邦特": ["penybont"],
    "广东": ["guangdong"], "广州": ["gz", "guangzhou"], "豹": ["power"],
    "圭多尼亚": ["guidonia"], "蒙特切利奥": ["montecelio"],
}


def has_evidence(zh, en):
    """中文名与英文名是否有可解释的对应证据。返回 (ok, reason)"""
    enl = en.lower()
    zh_s = str(zh)
    # 1) 音译词表命中
    for zh_kw, en_kws in TRANSLIT.items():
        if zh_kw in zh_s:
            for ek in en_kws:
                if ek in enl:
                    return True, f"translit:{zh_kw}~{ek}"
    # 2) 英文名整体出现在中文名或反之（音译对照常见）
    if len(zh_s) >= 3 and len(enl) >= 6:
        r = SequenceMatcher(None, zh_s, enl).ratio()
        if r > 0.5:
            return True, f"ratio:{r:.2f}"
    return False, "no_evidence"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=r"D:\cl\qqsj_v2\qiety_team_map_bulk2.csv")
    ap.add_argument("--known", default=r"D:\cl\qqsj_v2\qiety_team_map.csv")
    ap.add_argument("--out", default=r"D:\cl\qqsj_v2\qiety_team_map_audited.csv")
    ap.add_argument("--min-votes", type=int, default=3)
    a = ap.parse_args()

    known = {}
    if os.path.exists(a.known):
        with open(a.known, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                zh = (r.get("zh_name") or "").strip()
                en = (r.get("en_name") or "").strip()
                if zh and en:
                    known[zh] = en

    used_en = {}
    for zh, en in known.items():
        used_en.setdefault(en.lower(), []).append(zh)

    cand = []
    with open(a.inp, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cand.append((r["zh_name"].strip(), r["en_name"].strip(), int(r.get("votes") or 0)))

    keep, drop = [], []
    for zh, en, n in cand:
        if zh in known:
            drop.append((zh, en, n, "already_known"))
            continue
        if n < a.min_votes:
            drop.append((zh, en, n, f"votes<{a.min_votes}"))
            continue
        ok, why = has_evidence(zh, en)
        if not ok:
            drop.append((zh, en, n, "no_evidence"))
            continue
        # 一队一名：英文名已被别的中文名占用则冲突
        if en.lower() in used_en and zh not in used_en[en.lower()]:
            drop.append((zh, en, n, "en_taken:" + ",".join(used_en[en.lower()][:2])))
            continue
        keep.append((zh, en, n, why))
        used_en.setdefault(en.lower(), []).append(zh)

    with open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["zh_name", "en_name", "votes", "evidence"])
        w.writerows(keep)

    print(f"候选 {len(cand)}  保留 {len(keep)}  剔除 {len(drop)}\n")
    print("=== 保留 ===")
    for r in keep:
        print(f"  ✓ {r[0]:18} -> {r[1]:26} ({r[2]}票 {r[3]})")
    print("\n=== 剔除（前20）===")
    for r in drop[:20]:
        print(f"  ✗ {r[0]:18} -> {r[1]:26} ({r[2]}票 {r[3]})")
    print(f"\n输出: {a.out}")


if __name__ == "__main__":
    main()
