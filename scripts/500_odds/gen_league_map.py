# -*- coding: utf-8 -*-
"""自动生成 qiety 中文联赛名 -> Pinnacle league_name 映射。

方法：
  1. 取所有未覆盖的 qiety 联赛名（如「阿根廷职业联赛」）
  2. 按国家/地区关键词 + 级别关键词拆解成英文候选
  3. 与 Pinnacle 1114 个联赛名做匹配打分
  4. 输出高分映射到 CSV，供 LEAGUE_HINT 扩充

国家/地区词典覆盖 qiety 里出现的全部主流国家。
"""
import argparse
import csv
import difflib
import os
import re
import sqlite3
import sys

sys.path.insert(0, r"D:\cl\qqsj_v2")
from match_pinnacle_v2 import LEAGUE_HINT  # noqa: E402

COUNTRY = {
    "阿根廷": "Argentina", "巴西": "Brazil", "乌拉圭": "Uruguay", "巴拉圭": "Paraguay",
    "智利": "Chile", "哥伦比亚": "Colombia", "秘鲁": "Peru", "厄瓜多尔": "Ecuador",
    "玻利维亚": "Bolivia", "委内瑞拉": "Venezuela", "墨西哥": "Mexico",
    "美国": "USA", "加拿大": "Canada",
    "英格兰": "England", "苏格兰": "Scotland", "威尔士": "Wales", "爱尔兰": "Ireland",
    "北爱尔兰": "Northern Ireland",
    "西班牙": "Spain", "德国": "Germany", "意大利": "Italy", "法国": "France",
    "荷兰": "Netherlands", "葡萄牙": "Portugal", "比利时": "Belgium",
    "瑞士": "Switzerland", "奥地利": "Austria", "丹麦": "Denmark",
    "瑞典": "Sweden", "挪威": "Norway", "芬兰": "Finland", "冰岛": "Iceland",
    "波兰": "Poland", "捷克": "Czech Republic", "斯洛伐克": "Slovakia",
    "匈牙利": "Hungary", "罗马尼亚": "Romania", "保加利亚": "Bulgaria",
    "塞尔维亚": "Serbia", "克罗地亚": "Croatia", "斯洛文尼亚": "Slovenia",
    "波黑": "Bosnia", "黑山": "Montenegro", "北马其顿": "North Macedonia",
    "阿尔巴尼亚": "Albania", "希腊": "Greece", "土耳其": "Turkey",
    "俄罗斯": "Russia", "乌克兰": "Ukraine", "白俄罗斯": "Belarus",
    "立陶宛": "Lithuania", "拉脱维亚": "Latvia", "爱沙尼亚": "Estonia",
    "摩尔多瓦": "Moldova", "格鲁吉亚": "Georgia", "亚美尼亚": "Armenia",
    "阿塞拜疆": "Azerbaijan", "哈萨克斯坦": "Kazakhstan", "以色列": "Israel",
    "塞浦路斯": "Cyprus", "马耳他": "Malta", "卢森堡": "Luxembourg",
    "安道尔": "Andorra", "直布罗陀": "Gibraltar", "法罗": "Faroe",
    "埃及": "Egypt", "摩洛哥": "Morocco", "突尼斯": "Tunisia", "阿尔及利亚": "Algeria",
    "利比亚": "Libya", "尼日利亚": "Nigeria", "加纳": "Ghana", "喀麦隆": "Cameroon",
    "科特迪瓦": "Ivory Coast", "塞内加尔": "Senegal", "南非": "South Africa",
    "肯尼亚": "Kenya", "乌干达": "Uganda", "坦桑尼亚": "Tanzania",
    "津巴布韦": "Zimbabwe", "赞比亚": "Zambia", "卢旺达": "Rwanda",
    "埃塞俄比亚": "Ethiopia", "苏丹": "Sudan", "刚果": "Congo",
    "中国": "China", "日本": "Japan", "韩国": "South Korea", "朝鲜": "North Korea",
    "沙特": "Saudi Arabia", "阿联酋": "UAE", "卡塔尔": "Qatar", "科威特": "Kuwait",
    "巴林": "Bahrain", "阿曼": "Oman", "约旦": "Jordan", "伊拉克": "Iraq",
    "伊朗": "Iran", "叙利亚": "Syria", "黎巴嫩": "Lebanon", "也门": "Yemen",
    "巴勒斯坦": "Palestine", "以色列": "Israel",
    "印度": "India", "泰国": "Thailand", "越南": "Vietnam", "印尼": "Indonesia",
    "马来西亚": "Malaysia", "新加坡": "Singapore", "菲律宾": "Philippines",
    "缅甸": "Myanmar", "柬埔寨": "Cambodia", "老挝": "Laos", "孟加拉": "Bangladesh",
    "尼泊尔": "Nepal", "斯里兰卡": "Sri Lanka", "马尔代夫": "Maldives",
    "澳大利亚": "Australia", "澳洲": "Australia", "新西兰": "New Zealand",
    "乌兹别克斯坦": "Uzbekistan", "塔吉克斯坦": "Tajikistan",
    "土库曼斯坦": "Turkmenistan", "吉尔吉斯斯坦": "Kyrgyzstan",
    "中国香港": "Hong Kong", "香港": "Hong Kong", "澳门": "Macau",
    "中华台北": "Chinese Taipei", "台湾": "Chinese Taipei",
    # 补充：之前识别不出的
    "乌兹别克": "Uzbekistan", "莫桑比克": "Mozambique", "科索沃": "Kosovo",
    "萨尔瓦多": "El Salvador", "牙买加": "Jamaica", "洪都拉斯": "Honduras",
    "危地马拉": "Guatemala", "哥斯达黎加": "Costa Rica", "巴拿马": "Panama",
    "尼加拉瓜": "Nicaragua", "多米尼加": "Dominican Republic", "海地": "Haiti",
    "特立尼达": "Trinidad", "苏里南": "Suriname", "圭亚那": "Guyana",
    "亚美尼亚": "Armenia", "阿塞拜疆": "Azerbaijan", "摩尔多瓦": "Moldova",
    "安哥拉": "Angola", "贝宁": "Benin", "布基纳法索": "Burkina Faso",
    "马里": "Mali", "几内亚": "Guinea", "加蓬": "Gabon", "刚果民主": "DR Congo",
    "马拉维": "Malawi", "纳米比亚": "Namibia", "博茨瓦纳": "Botswana",
    "莱索托": "Lesotho", "斯威士兰": "Eswatini", "毛里求斯": "Mauritius",
    "塞舌尔": "Seychelles", "佛得角": "Cape Verde", "冈比亚": "Gambia",
    "塞拉利昂": "Sierra Leone", "利比里亚": "Liberia", "多哥": "Togo",
    "尼日尔": "Niger", "乍得": "Chad", "中非": "Central African",
    "赤道几内亚": "Equatorial Guinea", "圣多美": "Sao Tome",
    "布隆迪": "Burundi", "吉布提": "Djibouti", "厄立特里亚": "Eritrea",
    "索马里": "Somalia", "马达加斯加": "Madagascar", "科摩罗": "Comoros",
    "留尼汪": "Reunion", "马约特": "Mayotte",
}

# 地区限定词（中文 -> 英文必须包含）
REGION = {
    "北部": ["North", "Norra", "Norte", "Nord"], "南部": ["South", "Sodra", "Sur", "Sud"],
    "东部": ["East", "Ostra", "Este", "Est"], "西部": ["West", "Vastra", "Oeste", "Ouest"],
    "中部": ["Central", "Center", "Centro"], "东北": ["North East", "Nord Est"],
    "西北": ["North West", "Nord Ouest"], "东南": ["South East", "Sud Est"],
    "西南": ["South West", "Sud Ouest"], "北区": ["North"], "南区": ["South"],
}

# 具体城市/联赛专名（不可用通用词猜）
CITY_LEAGUE = {
    "班加罗尔": ["Bangalore", "Bengaluru"], "米佐拉姆": ["Mizoram"],
    "加尔各答": ["Kolkata"], "孟买": ["Mumbai"], "德里": ["Delhi"],
    "伊斯米安": ["Isthmian"], "北部超级": ["Northern Premier"],
    "曼特波里顿": ["Metropolitana"], "马德里": ["Madrid"], "加泰罗尼亚": ["Catalonia"],
}

LEVEL = [
    ("超级联赛", ["Premier League", "Super Lig", "Super League", "Ekstraklasa",
                "First Division A", "Pro League", "Elite", "Premiership", "Veikkausliiga",
                "Allsvenskan", "Eliteserien", "Superliga"]),
    ("甲级联赛", ["1. Liga", "Liga 1", "Division 1", "Primera", "Serie A", "Championship",
                "First League", "Eerste Divisie", "League One", "Superettan"]),
    ("乙级联赛", ["2. Liga", "Liga 2", "Division 2", "Segunda", "Serie B", "League Two",
                "Second League", "1st Division"]),
    ("丙级联赛", ["3. Liga", "Liga 3", "Division 3", "Tercera", "Serie C", "Third League",
                "2nd Division"]),
    ("丁级联赛", ["4. Liga", "Liga 4", "Division 4", "Serie D", "Fourth League",
                "3rd Division"]),
    ("杯", ["Cup", "Taca", "Coupe", "Coppa", "Pokal", "Copa", "Kupa"]),
    ("联赛U19", ["U19 League", "U19"]),
    ("联赛U20", ["U20 League", "U20"]),
    ("联赛U21", ["U21 League", "U21"]),
    ("联赛U23", ["U23 League", "U23"]),
    ("后备队", ["Reserve", "Reserves", "Liga Pro"]),
    ("女子", ["Women", "Feminine", "Femenina"]),
]


# 级别矛盾检查：中文级别 -> 英文必须含的词 vs 禁止含的词
LEVEL_CHECK = {
    "超级联赛": (["Premier", "Super", "Ekstraklasa", "Elite", "Allsvenskan",
              "Eliteserien", "Veikkausliiga", "Pro League", "First Division A"],
             ["2.", "3.", "4.", "Segunda", "Tercera", "Second", "Third", "Fourth",
              "Serie B", "Serie C", "Serie D", "Championship", "Liga 2", "Liga 3"]),
    "甲级联赛": (["1. Liga", "Liga 1", "Division 1", "Primera A", "Primera Division",
              "Serie A", "Championship", "First League", "Superettan", "Eerste Divisie",
              "League One", "Primera"],
             # 禁止：乙级及以下的所有写法（含 Primera B / Primera Nacional）
             ["2.", "3.", "4.", "Segunda", "Tercera", "Second", "Third", "Serie B",
              "Serie C", "League Two", "Primera B", "Primera Nacional", "B Metro",
              "Federal B", "Liga 2", "Liga 3"]),
    "乙级联赛": (["2. Liga", "Liga 2", "Division 2", "Segunda", "Serie B", "League Two",
              "Second League", "Primera B", "Primera Nacional"],
             ["3.", "4.", "Tercera", "Serie C", "Serie D", "Premier"]),
    "丙级联赛": (["3. Liga", "Liga 3", "Division 3", "Tercera", "Serie C", "Liga 3"],
             ["4.", "Serie D", "Premier"]),
    "丁级联赛": (["4. Liga", "Liga 4", "Division 4", "Serie D"],
             ["Premier", "Serie A", "Serie B"]),
}
WOMEN_ZH = ["女", "女子"]
RESERVE_ZH = ["后备", "青年", "B队", "预备"]
YOUTH_ZH = ["U19", "U20", "U21", "U23", "U17", "U18"]


def contradictions(zh, pl):
    """返回矛盾列表，空表示无矛盾"""
    bad = []
    pll = pl.lower()
    # 级别矛盾
    for zh_lv, (must, forbid) in LEVEL_CHECK.items():
        if zh_lv in zh:
            if not any(m.lower() in pll for m in must):
                bad.append(f"级别需含{must[0]}")
            for f in forbid:
                if f.lower() in pll:
                    bad.append(f"级别不符(含{f})")
                    break
    # 女子
    zh_w = any(w in zh for w in WOMEN_ZH)
    pl_w = any(w in pll for w in ["women", "feminine", "femenina", "ladies", "damallsvenskan"])
    if zh_w != pl_w:
        bad.append("女子属性不符")
    # 后备/青年
    zh_r = any(r in zh for r in RESERVE_ZH)
    pl_r = any(r in pll for r in ["reserve", "ii", " b ", "b team", "jong", "proximo"])
    if zh_r and not pl_r:
        bad.append("后备属性不符")
    # 青年年龄段（双向检查：中文无青年则英文不能有）
    zh_y = [y for y in YOUTH_ZH if y in zh]
    pl_y = [y for y in YOUTH_ZH if y.lower() in pll]
    if zh_y:
        if not pl_y:
            bad.append(f"青年年龄段不符({'/'.join(zh_y)})")
    elif pl_y:
        bad.append(f"英文含青年但中文无({'/'.join(pl_y)})")
    # 杯赛属性双向检查
    zh_cup = any(w in zh for w in ["杯", "资格赛", "附加赛"]) and "联赛杯" not in zh
    pl_cup = any(w in pll for w in ["cup", "taca", "coupe", "coppa", "pokal", "copa"])
    if zh_cup and not pl_cup:
        bad.append("杯赛属性不符")
    if pl_cup and not zh_cup and "杯" not in zh:
        bad.append("英文是杯赛但中文不是")
    # 地区限定词：中文有就必须英文含对应词
    for zh_r, en_rs in REGION.items():
        if zh_r in zh:
            if not any(e.lower() in pll for e in en_rs):
                bad.append(f"地区需含{zh_r}")
                break
    # 城市/专名：中文有专名，英文必须含对应
    for zh_c, en_cs in CITY_LEAGUE.items():
        if zh_c in zh:
            if not any(e.lower() in pll for e in en_cs):
                bad.append(f"专名需含{zh_c}")
                break
    return bad


def suggest(zh_league, pinn_leagues):
    """给一个中文联赛名，推荐 Pinnacle 联赛名候选"""
    # 1) 国家
    country_en = None
    for zh_c, en_c in sorted(COUNTRY.items(), key=lambda x: -len(x[0])):
        if zh_c in zh_league:
            country_en = en_c
            break
    # 2) 级别关键词
    level_kws = []
    for zh_lv, en_lvs in LEVEL:
        if zh_lv in zh_league:
            level_kws.extend(en_lvs)
            break

    # 3) 候选打分
    scored = []
    for pl in pinn_leagues:
        s = 0.0
        if country_en and country_en.lower() in pl.lower():
            s += 0.6
        else:
            continue                          # 国家不匹配直接跳过
        hit_lv = False
        for kw in level_kws:
            if kw.lower() in pl.lower():
                s += 0.35
                hit_lv = True
                break
        if not hit_lv:
            continue                          # 级别不匹配跳过
        if contradictions(zh_league, pl):
            continue                          # 有矛盾跳过
        scored.append((s, pl))
    scored.sort(key=lambda x: -x[0])
    return country_en, level_kws, scored[:3]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"D:\cl\qqsj\data\sports_data.db")
    ap.add_argument("--out", default=r"D:\cl\qqsj_v2\league_map_auto.csv")
    ap.add_argument("--min-score", type=float, default=0.9)
    a = ap.parse_args()

    con = sqlite3.connect("file:" + a.db + "?mode=ro", uri=True, timeout=60)
    pinn_leagues = [r[0] for r in con.execute(
        "SELECT DISTINCT league_name FROM theodds_fixtures "
        "WHERE source='pinnacle' AND league_name IS NOT NULL")]
    qy = con.execute("""
        SELECT league, COUNT(DISTINCT match_key) n FROM soft_odds_snapshots
        WHERE source='qiety' AND league IS NOT NULL
        GROUP BY league ORDER BY n DESC
    """).fetchall()
    print(f"Pinnacle 联赛 {len(pinn_leagues)} 个 / qiety 联赛 {len(qy)} 个")

    rows = []
    no_country = []
    for lg_zh, n in qy:
        if not lg_zh:
            continue
        if any(k in lg_zh for k in LEAGUE_HINT):
            continue
        country_en, level_kws, cands = suggest(lg_zh, pinn_leagues)
        if not country_en:
            no_country.append((lg_zh, n))
            continue
        if cands and cands[0][0] >= a.min_score:
            rows.append((lg_zh, cands[0][1], round(cands[0][0], 2), n, country_en))
        else:
            rows.append((lg_zh, "", round(cands[0][0], 2) if cands else 0, n, country_en))

    rows.sort(key=lambda r: -r[3])
    with open(a.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["league_zh", "pinn_league", "score", "matches", "country_en"])
        w.writerows(rows)

    ok = [r for r in rows if r[1]]
    print(f"\n可自动映射 {len(ok)} 个联赛（覆盖 {sum(r[3] for r in ok)} 场）")
    print(f"无法识别国家 {len(no_country)} 个")
    print(f"\n=== 映射结果（前 35）===")
    for r in ok[:35]:
        print(f"  {r[0][:28]:28} -> {r[1][:34]:34} (分{r[2]} {r[3]}场)")
    print(f"\n=== 无法识别国家（前15）===")
    for lg, n in no_country[:15]:
        print(f"  {lg[:34]:34} {n} 场")
    print(f"\n输出: {a.out}")


if __name__ == "__main__":
    main()
