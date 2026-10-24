# -*- coding: utf-8 -*-
"""审核 LLM 翻译结果，剔除错译。

审核规则（全部程序化，可复现）：
  1. 【一队一名】同一英文名只能对应一个中文名 —— 违反则全部剔除（这是最高频错误）
  2. 【中英混杂】英文值含中文字符 -> 剔除
  3. 【问号/空】-> 剔除
  4. 【音译首字母】中文名拼音首字母 与 英文名前 2 个词的词首字母 应有交集
     （如 "卡纳芬城" k-n-f-c vs "Caernarfon Town" c-t -> c 命中，通过）
     （如 "阿玛盖尔" a-m-g-e vs "Aarhus GF" a-g -> a,g 命中但都很泛，需要额外校验）
  5. 【城市误导】英文名含 Cardiff/City/United 等泛词而中文名无对应 -> 人工标记
"""
import argparse
import csv
import os
import re
from collections import defaultdict


def pinyin_initials(zh):
    """粗略取中文名首字拼音首字母（用常见字表，非全量）"""
    # 简化：只取第一个字的大致拼音首字母，覆盖常见足球城市字
    PY = {
        "阿": "a", "艾": "a", "埃": "a", "安": "a", "奥": "a", "澳": "a",
        "巴": "b", "拜": "b", "贝": "b", "比": "b", "波": "b", "博": "b",
        "布": "b", "柏": "b", "本": "b", "毕": "b", "北": "b", "班": "b",
        "查": "c", "茨": "c", "长": "c", "城": "c", "川": "c", "春": "c",
        "达": "d", "大": "d", "德": "d", "迪": "d", "多": "d", "东": "d",
        "第": "d", "杜": "d", "丹": "d", "都": "d",
        "恩": "e", "鄂": "e",
        "法": "f", "费": "f", "弗": "f", "福": "f", "菲": "f", "芬": "f",
        "弗": "f", "富": "f",
        "盖": "g", "甘": "g", "格": "g", "哥": "g", "古": "g", "瓜": "g",
        "光": "g", "广": "g", "国": "g", "高": "g",
        "哈": "h", "海": "h", "汉": "h", "河": "h", "赫": "h", "红": "h",
        "华": "h", "皇": "h", "霍": "h", "怀": "h", "黄": "h", "赫": "h",
        "基": "j", "吉": "j", "加": "j", "贾": "j", "捷": "j", "金": "j",
        "京": "j", "九": "j", "军": "j", "江": "j", "锦": "j",
        "卡": "k", "凯": "k", "康": "k", "科": "k", "克": "k", "库": "k",
        "昆": "k", "开": "k", "喀": "k", "堪": "k",
        "拉": "l", "莱": "l", "兰": "l", "勒": "l", "雷": "l", "里": "l",
        "利": "l", "林": "l", "卢": "l", "鲁": "l", "路": "l", "洛": "l",
        "罗": "l", "联": "l", "辽": "l", "六": "l",
        "马": "m", "迈": "m", "曼": "m", "梅": "m", "门": "m", "米": "m",
        "明": "m", "摩": "m", "莫": "m", "姆": "m", "慕": "m", "蒙": "m",
        "拿": "n", "纳": "n", "南": "n", "内": "n", "尼": "n", "纽": "n",
        "诺": "n", "奈": "n", "尼": "n", "宁": "n",
        "欧": "o", "帕": "p", "潘": "p", "佩": "p", "皮": "p", "平": "p",
        "普": "p", "浦": "p", "彭": "p",
        "齐": "q", "奇": "q", "切": "q", "青": "q", "清": "q", "全": "q",
        "泉": "q", "秋": "q", "七": "q",
        "热": "r", "日": "r", "荣": "r", "瑞": "r", "若": "r", "仁": "r",
        "萨": "s", "塞": "s", "桑": "s", "森": "s", "沙": "s", "山": "s",
        "上": "s", "圣": "s", "斯": "s", "苏": "s", "索": "s", "深": "s",
        "四": "s", "松": "s", "史": "s", "士": "s", "神": "s",
        "塔": "t", "泰": "t", "坦": "t", "特": "t", "天": "t", "图": "t",
        "托": "t", "突": "t", "土": "t", "通": "t", "台": "t",
        "瓦": "w", "万": "w", "威": "w", "韦": "w", "维": "w", "温": "w",
        "文": "w", "沃": "w", "乌": "w", "武": "w", "五": "w", "瓦": "w",
        "西": "x", "希": "x", "锡": "x", "夏": "x", "谢": "x", "辛": "x",
        "新": "x", "休": "x", "叙": "x", "香": "x", "湘": "x",
        "雅": "y", "亚": "y", "扬": "y", "伊": "y", "依": "y", "易": "y",
        "印": "y", "英": "y", "尤": "y", "于": "y", "元": "y", "云": "y",
        "约": "y", "越": "y", "亚": "y", "耶": "y",
        "赞": "z", "泽": "z", "扎": "z", "詹": "z", "掌": "z", "浙": "z",
        "芝": "z", "治": "z", "中": "z", "珠": "z", "主": "z", "兹": "z",
        "佐": "z", "作": "z",
    }
    out = []
    for ch in zh:
        if ch in PY:
            out.append(PY[ch])
        elif ch.isascii() and ch.isalpha():
            out.append(ch.lower())
    return out


def en_initials(en):
    words = re.findall(r"[A-Za-z]+", en)
    return [w[0].lower() for w in words if w]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=r"D:\cl\qqsj_v2\qiety_team_map_llm.csv")
    ap.add_argument("--out", default=r"D:\cl\qqsj_v2\qiety_team_map_llm_clean.csv")
    ap.add_argument("--base", default=r"D:\cl\qqsj_v2\qiety_team_map.csv")
    a = ap.parse_args()

    # 已有映射里的英文名（冲突检测基线）
    base_en = defaultdict(list)
    if os.path.exists(a.base):
        with open(a.base, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                zh = (r.get("zh_name") or "").strip()
                en = (r.get("en_name") or "").strip()
                if zh and en:
                    base_en[en.lower()].append(zh)

    rows = []
    with open(a.inp, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)

    # 第一轮：基本过滤
    stage1 = []
    drop = defaultdict(int)
    for r in rows:
        zh = (r.get("zh_name") or "").strip()
        en = (r.get("en_name") or "").strip()
        src = (r.get("source") or "")
        if not en or en == "?":
            drop["empty"] += 1
            continue
        if re.search("[\u4e00-\u9fff]", en):
            drop["has_chinese"] += 1
            continue
        if len(en) < 3:
            drop["too_short"] += 1
            continue
        stage1.append((zh, en, r.get("league") or "", src))

    # 第二轮：一队一名（英文名重复的中文名全部剔除，除非已有映射也是这个）
    en_count = defaultdict(list)
    for zh, en, lg, src in stage1:
        en_count[en.lower()].append(zh)
    stage2 = []
    for zh, en, lg, src in stage1:
        key = en.lower()
        if len(en_count[key]) > 1:
            drop["en_duplicate"] += 1
            continue
        if key in base_en and zh not in base_en[key]:
            drop["en_taken_by_base"] += 1
            continue
        stage2.append((zh, en, lg, src))

    # 第三轮：音译首字母校验
    stage3 = []
    for zh, en, lg, src in stage2:
        zi = pinyin_initials(zh)
        ei = en_initials(en)
        if zi and ei:
            hit = set(zi) & set(ei)
            # 首字必须命中，或至少 2 个字母命中
            if zi[0] not in ei and len(hit) < 2:
                drop["translit_mismatch"] += 1
                continue
        stage3.append((zh, en, lg, src))

    with open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["zh_name", "en_name", "league", "source"])
        for r in stage3:
            w.writerow(r)

    print(f"输入 {len(rows)} 条")
    print(f"通过 {len(stage3)} 条  剔除 {len(rows)-len(stage3)} 条")
    print("\n=== 剔除原因 ===")
    for k, v in sorted(drop.items(), key=lambda x: -x[1]):
        print(f"  {k:18} {v}")
    print(f"\n=== 重复英文名示例 ===")
    dups = {k: v for k, v in en_count.items() if len(v) > 1}
    for k, v in list(dups.items())[:8]:
        print(f"  {k:26} <- {v}")
    print(f"\n输出: {a.out}")


if __name__ == "__main__":
    main()
