# -*- coding: utf-8 -*-
"""智能合并 LLM 翻译到主映射表（分级信任）。

之前的错误：只合并 map_verified.csv（560条），把 4234 条未验证的全丢了，
导致巴黎圣日耳曼、拜仁慕尼黑这种明显正确的翻译都没进表。

正确策略（按可信度分层）：
  L1 Pinnacle 验证通过           -> 直接采纳（最强证据）
  L2 LLM high + 音译校验通过     -> 采纳
  L3 LLM high + 英文名在知名俱乐部白名单 -> 采纳
  L4 LLM high 但音译不符         -> 拒绝
  L5 LLM low                     -> 拒绝

一队一名约束始终生效。
"""
import argparse
import csv
import os
import re
from collections import defaultdict

# 全球知名俱乐部白名单（这些翻译不需要额外验证）
FAMOUS = {
    "paris saint-germain", "bayern munich", "bayern munchen", "olympique de marseille",
    "olympique lyonnais", "montpellier hsc", "1. fc koln", "fc koln",
    "real madrid", "barcelona", "atletico madrid", "sevilla", "valencia",
    "manchester united", "manchester city", "liverpool", "chelsea", "arsenal",
    "tottenham hotspur", "newcastle united", "aston villa", "everton",
    "juventus", "ac milan", "inter milan", "as roma", "napoli", "lazio",
    "borussia dortmund", "rb leipzig", "bayer leverkusen", "eintracht frankfurt",
    "vfb stuttgart", "werder bremen", "borussia monchengladbach",
    "ajax", "psv", "feyenoord", "az alkmaar",
    "benfica", "fc porto", "sporting cp", "braga",
    "celtic", "rangers", "galatasaray", "fenerbahce", "besiktas",
    "zenit", "cska moscow", "shakhtar donetsk", "dinamo zagreb",
    "red star belgrade", "partizan", "olympiacos", "panathinaikos",
    "boca juniors", "river plate", "flamengo", "palmeiras", "corinthians",
    "santos", "sao paulo", "fluminense", "botafogo", "gremio", "internacional",
    "club america", "tigres", "monterrey", "chivas",
    "al hilal", "al nassr", "al ittihad", "al ahli",
    "shanghai port", "shanghai shenhua", "beijing guoan", "shandong taishan",
    "guangzhou", "kawasaki frontale", "yokohama f marinos", "urawa reds",
    "jeonbuk motors", "ulsan hd", "pohang steelers", "seoul",
}

PY = {  # 中文首字拼音（覆盖足球常见字）
    "阿": "a", "艾": "a", "埃": "a", "安": "a", "奥": "a", "澳": "a",
    "巴": "b", "拜": "b", "贝": "b", "比": "b", "波": "b", "博": "b",
    "布": "b", "柏": "b", "本": "b", "毕": "b", "北": "b", "班": "b",
    "查": "c", "茨": "c", "长": "c", "城": "c", "川": "c", "春": "c",
    "达": "d", "大": "d", "德": "d", "迪": "d", "多": "d", "东": "d",
    "第": "d", "杜": "d", "丹": "d", "都": "d",
    "恩": "e", "鄂": "e",
    "法": "f", "费": "f", "弗": "f", "福": "f", "菲": "f", "芬": "f",
    "富": "f", "费": "f",
    "盖": "g", "甘": "g", "格": "g", "哥": "g", "古": "g", "瓜": "g",
    "光": "g", "广": "g", "国": "g", "高": "g",
    "哈": "h", "海": "h", "汉": "h", "河": "h", "赫": "h", "红": "h",
    "华": "h", "皇": "h", "霍": "h", "怀": "h", "黄": "h",
    "基": "j", "吉": "j", "加": "j", "贾": "j", "捷": "j", "金": "j",
    "京": "j", "九": "j", "军": "j", "江": "j", "锦": "j", "甲": "j",
    "卡": "k", "凯": "k", "康": "k", "科": "k", "克": "k", "库": "k",
    "昆": "k", "开": "k", "喀": "k", "堪": "k",
    "拉": "l", "莱": "l", "兰": "l", "勒": "l", "雷": "l", "里": "l",
    "利": "l", "林": "l", "卢": "l", "鲁": "l", "路": "l", "洛": "l",
    "罗": "l", "联": "l", "辽": "l", "六": "l", "黎": "l",
    "马": "m", "迈": "m", "曼": "m", "梅": "m", "门": "m", "米": "m",
    "明": "m", "摩": "m", "莫": "m", "姆": "m", "慕": "m", "蒙": "m",
    "拿": "n", "纳": "n", "南": "n", "内": "n", "尼": "n", "纽": "n",
    "诺": "n", "奈": "n", "宁": "n",
    "欧": "o", "帕": "p", "潘": "p", "佩": "p", "皮": "p", "平": "p",
    "普": "p", "浦": "p", "彭": "p",
    "齐": "q", "奇": "q", "切": "q", "青": "q", "清": "q", "全": "q",
    "泉": "q", "秋": "q", "七": "q",
    "热": "r", "日": "r", "荣": "r", "瑞": "r", "若": "r", "仁": "r",
    "萨": "s", "塞": "s", "桑": "s", "森": "s", "沙": "s", "山": "s",
    "上": "s", "圣": "s", "斯": "s", "苏": "s", "索": "s", "深": "s",
    "四": "s", "松": "s", "史": "s", "士": "s", "神": "s", "首": "s",
    "塔": "t", "泰": "t", "坦": "t", "特": "t", "天": "t", "图": "t",
    "托": "t", "突": "t", "土": "t", "通": "t", "台": "t",
    "瓦": "w", "万": "w", "威": "w", "韦": "w", "维": "w", "温": "w",
    "文": "w", "沃": "w", "乌": "w", "武": "w", "五": "w",
    "西": "x", "希": "x", "锡": "x", "夏": "x", "谢": "x", "辛": "x",
    "新": "x", "休": "x", "叙": "x", "香": "x", "湘": "x",
    "雅": "y", "亚": "y", "扬": "y", "伊": "y", "依": "y", "易": "y",
    "印": "y", "英": "y", "尤": "y", "于": "y", "元": "y", "云": "y",
    "约": "y", "越": "y", "耶": "y",
    "赞": "z", "泽": "z", "扎": "z", "詹": "z", "掌": "z", "浙": "z",
    "芝": "z", "治": "z", "中": "z", "珠": "z", "主": "z", "兹": "z",
    "佐": "z", "作": "z",
    # 补充（LLM 结果里出现的高频字）
    "蒂": "d", "华": "h", "纳": "n", "悉": "x", "尼": "n", "流": "l", "浪": "l",
    "者": "z", "东": "d", "京": "j", "绿": "l", "茵": "y", "贝": "b", "拉": "l",
    "萨": "s", "乌": "w", "德": "d", "勒": "l", "支": "z", "青": "q", "年": "n",
    "埃": "a", "因": "y", "霍": "h", "温": "w", "甘": "g", "冈": "g",
    "邓": "d", "伯": "b", "什": "s", "阿": "a", "尔": "e", "梅": "m", "勒": "l",
    "美": "m", "洲": "z", "狮": "s", "坎": "k", "布": "b", "里": "l", "亚": "y",
    "罗": "l", "斯": "s", "基": "j", "卡": "k", "塞": "s", "尔": "e", "塔": "t",
    "卡": "k", "马": "m", "森": "s", "菲": "f", "利": "l", "竞": "j", "技": "j",
    "瓦": "w", "韦": "w", "克": "k", "雷": "l", "欧": "o", "多": "d", "夫": "f",
    "罗": "l", "格": "g", "尼": "n", "兹": "z", "法": "f", "沃": "w", "特": "t",
    "奈": "n", "科": "k", "温": "w", "湾": "w", "都": "d", "会": "h", "大": "d",
    "学": "x", "维": "w", "希": "x", "拉": "l", "蒂": "d", "米": "m", "奇": "q",
    "伊": "y", "斯": "s", "维": "w", "希": "x",
}


def initials_zh(zh):
    return [PY[c] for c in zh if c in PY]


def initials_en(en):
    return [w[0].lower() for w in re.findall(r"[A-Za-z]+", en) if w]


def attr_ok(zh, en):
    """女队/青年队/后备队 属性必须与英文一致"""
    enl = en.lower()
    zh_w = ("女" in zh)
    en_w = any(w in enl for w in ["women", "feminine", "femenina", "ladies", "dames", "frauen"])
    if zh_w != en_w:
        return False
    # 年龄段：中文有 U19 则英文必须有
    import re as _re
    zm = _re.search(r"U(\d{2})", zh)
    if zm:
        if zm.group(1) not in enl:
            return False
    elif _re.search(r"\bu(\d{2})\b", enl):
        return False
    # B队/青年/后备（排除 "FC B..." 这类前缀误判：只查中文侧语义）
    zh_b = any(w in zh for w in ["B队", "青年", "后备", "预备"])
    en_b = any(w in enl for w in [" ii", " ii ", "reserve", "jong", "youth", "proximo"])
    if zh_b and not en_b:
        return False
    return True


def translit_ok(zh, en):
    zi, ei = initials_zh(zh), initials_en(en)
    if not zi or not ei:
        return False
    common = set(zi) & set(ei)
    # 首字命中 或 至少2个字母交集 或 （中文>=4字时至少1个交集且英文>=2词）
    if zi[0] in ei or len(common) >= 2:
        return True
    if len(zh) >= 4 and len(common) >= 1 and len(ei) >= 2:
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=r"D:\cl\qqsj_v2\qiety_team_map.csv")
    ap.add_argument("--llm", default=r"D:\cl\qqsj_v2\qiety_team_map_llm.csv")
    ap.add_argument("--verified", default=r"D:\cl\qqsj_v2\map_verified.csv")
    ap.add_argument("--out", default=r"D:\cl\qqsj_v2\qiety_team_map.csv")
    a = ap.parse_args()

    # 现有表
    base = {}
    if os.path.exists(a.base):
        with open(a.base, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                zh = (r.get("zh_name") or "").strip()
                en = (r.get("en_name") or "").strip()
                if zh and en:
                    base[zh] = en
    n0 = len(base)

    # Pinnacle 验证通过的
    verified = set()
    if os.path.exists(a.verified):
        with open(a.verified, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                verified.add((r["zh_name"].strip(), r["en_name"].strip()))

    # LLM 结果
    llm = []
    if os.path.exists(a.llm):
        with open(a.llm, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                zh = (r.get("zh_name") or "").strip()
                en = (r.get("en_name") or "").strip()
                src = r.get("source") or ""
                if not zh or not en or en == "?" or re.search("[\u4e00-\u9fff]", en):
                    continue
                conf = src.split(":")[-1] if ":" in src else "unknown"
                llm.append((zh, en, conf))

    used_en = defaultdict(list)
    for zh, en in base.items():
        used_en[en.lower()].append(zh)

    stats = defaultdict(int)
    added = []

    # 先 L1 验证通过
    for zh, en in verified:
        if zh in base:
            stats["L1_skip_exists"] += 1
            continue
        if en.lower() in used_en:
            stats["L1_en_taken"] += 1
            continue
        base[zh] = en
        used_en[en.lower()].append(zh)
        added.append((zh, en, "L1_verified"))
        stats["L1"] += 1

    # 再 L2/L3
    for zh, en, conf in llm:
        if zh in base:
            continue
        enl = en.lower().strip()
        if enl in used_en:
            stats["en_taken"] += 1
            continue
        if not attr_ok(zh, en):
            stats["attr_mismatch"] += 1
            continue
        if conf == "high":
            if translit_ok(zh, en):
                base[zh] = en
                used_en[enl].append(zh)
                added.append((zh, en, "L2_high_translit"))
                stats["L2"] += 1
            elif enl in FAMOUS:
                base[zh] = en
                used_en[enl].append(zh)
                added.append((zh, en, "L3_high_famous"))
                stats["L3"] += 1
            else:
                stats["high_no_evidence"] += 1
        else:
            stats["low_conf"] += 1

    with open(a.out, "w", encoding="utf-8", newline="") as f:
        f.write("zh_name,en_name\n")
        for zh, en in sorted(base.items()):
            f.write(f'"{zh}","{en}"\n')

    print(f"原表 {n0} 条  ->  新表 {len(base)} 条  (新增 {len(added)})")
    print("\n=== 分层统计 ===")
    for k, v in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {k:20} {v}")
    print(f"\n=== 新增样例（前 20）===")
    for r in added[:20]:
        print(f"  [{r[2]:18}] {r[0]:16} -> {r[1]}")


if __name__ == "__main__":
    main()
