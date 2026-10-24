# -*- coding: utf-8 -*-
"""改进版 pinn_id 匹配：先用联赛+时间缩小候选集，再做队名相似度。

相比原版（纯时间窗 + 队名）的改进：
  1. 联赛名映射：qiety 中文联赛 → Pinnacle league_name（如 英格兰冠军联赛 → England - Championship）
     同一联赛内匹配，候选从 39067 场降到几十场，准确率和速度都提升
  2. 时间窗放宽：同联赛内允许 ±30 分钟（不同源开赛时间常差几分钟到半小时）
  3. 队名归一化加强：去掉音译括号、常见后缀、处理 Al- 前缀
  4. 双向匹配：允许主客互换（个别源队序不同）
  5. 二次回退：联赛筛不出时，回退到 ±15 分钟全量时间窗

产出：把匹配结果写回 soft_odds_snapshots 的 pinn_id 列（原表该列全空）。
"""
import argparse
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher

sys.path.insert(0, r"D:\cl\qqsj_v2")

# qiety 中文联赛名 -> Pinnacle league_name 关键词（用于筛选）
LEAGUE_HINT = {
    # 英格兰
    "英格兰超级联赛": ["England - Premier League"],
    "英格兰冠军联赛": ["England - Championship"],
    "英格兰甲级联赛": ["England - League 1", "England - League One"],
    "英格兰乙级联赛": ["England - League 2", "England - League Two"],
    "英格兰足球协会全国联赛": ["England - National League"],
    "英格兰足球协会南部全国联赛": ["England - National League South"],
    "英格兰足球协会北部全国联赛": ["England - National League North"],
    "英格兰北部超级联赛": ["England - Northern Premier"],
    "英格兰足总锦标": ["England - FA Trophy"],
    "英格兰足总杯": ["England - FA Cup"],
    # 西班牙
    "西班牙甲级联赛": ["Spain - La Liga"],
    "西班牙乙级联赛": ["Spain - Segunda Division"],
    "西班牙足协甲级联赛": ["Spain - Primera Federacion"],
    "西班牙足协乙级联赛": ["Spain - Segunda Federacion"],
    "西班牙足协丙级联赛": ["Spain - Tercera Division"],
    "西班牙丙级联赛": ["Spain - Tercera Division"],
    "西班牙甲级联赛U19": ["Spain - U19 League"],
    "西班牙青年荣誉联赛U19": ["Spain - U19 League"],
    "西班牙国王杯": ["Spain - Copa del Rey"],
    # 德国
    "德国甲级联赛": ["Germany - Bundesliga"],
    "德国乙级联赛": ["Germany - 2. Bundesliga"],
    "德国丙级联赛": ["Germany - 3. Liga"],
    "德国地区联赛": ["Germany - Regionalliga"],
    "德国足协杯": ["Germany - DFB Pokal"],
    # 意大利
    "意大利甲级联赛": ["Italy - Serie A"],
    "意大利乙级联赛": ["Italy - Serie B"],
    "意大利丙级联赛": ["Italy - Serie C"],
    "意大利丁级联赛": ["Italy - Serie D"],
    "意大利青年春季乙级联赛U19": ["Italy - Primavera 2 U19"],
    "意大利青年联赛U19": ["Italy - Primavera"],
    "意大利杯": ["Italy - Coppa Italia"],
    # 法国
    "法国甲级联赛": ["France - Ligue 1"],
    "法国乙级联赛": ["France - Ligue 2"],
    "法国全国联赛": ["France - National"],
    "法国杯": ["France - Coupe de France"],
    # 荷兰 / 葡萄牙 / 比利时
    "荷兰甲级联赛": ["Netherlands - Eredivisie"],
    "荷兰乙级联赛": ["Netherlands - Eerste Divisie"],
    "荷兰丙级联赛": ["Netherlands - Tweede Divisie"],
    "葡萄牙超级联赛": ["Portugal - Primeira Liga"],
    "葡萄牙甲级联赛": ["Portugal - Liga Portugal 2", "Portugal - Segunda Liga"],
    "葡萄牙杯": ["Portugal - Taca de Portugal"],
    "比利时甲级联赛": ["Belgium - First Division A", "Belgium - Pro League"],
    # 亚洲
    "中国超级联赛": ["China - Super League"],
    "中国甲级联赛": ["China - League One"],
    "中国乙级联赛": ["China - League Two"],
    "日本J联赛": ["Japan - J1 League", "Japan - J1"],
    "日本J2联赛": ["Japan - J2 League", "Japan - J2"],
    "日本J3联赛": ["Japan - J3 League", "Japan - J3"],
    "韩国K1联赛": ["South Korea - K League 1", "Korea Republic - K League 1"],
    "韩国K2联赛": ["South Korea - K League 2", "Korea Republic - K League 2"],
    "沙特超级联赛": ["Saudi Arabia - Pro League"],
    "澳洲甲级联赛": ["Australia - A-League"],
    "泰国超级联赛": ["Thailand - Thai League 1"],
    # 美洲
    "美国职业大联盟": ["USA - Major League Soccer"],
    "美国USL": ["USA - USL"],
    "巴西甲级联赛": ["Brazil - Serie A"],
    "巴西乙级联赛": ["Brazil - Serie B"],
    "阿根廷甲级联赛": ["Argentina - Liga Profesional", "Argentina - Primera Division"],
    "阿根廷联赛后备队": ["Argentina - Liga Pro Reserves", "Argentina - Reserve"],
    "阿根廷乙级联赛": ["Argentina - Primera B", "Argentina - Primera Nacional"],
    "墨西哥超级联赛": ["Mexico - Liga MX"],
    # 东欧 / 北欧
    "波兰丙级联赛": ["Poland - 3rd Liga", "Poland - III Liga"],
    "波兰乙级联赛": ["Poland - 1. Liga"],
    "波兰甲级联赛": ["Poland - Ekstraklasa"],
    "捷克丁级联赛": ["Czech Republic - 4. Liga"],
    "捷克丙级联赛": ["Czech Republic - 3. Liga"],
    "捷克乙级联赛": ["Czech Republic - 2. Liga"],
    "捷克甲级联赛": ["Czech Republic - First League"],
    "挪威丙级联赛": ["Norway - 3rd Division"],
    "挪威乙级联赛": ["Norway - 2nd Division"],
    "挪威甲级联赛": ["Norway - 1st Division"],
    "瑞典乙级联赛": ["Sweden - 2nd Division"],
    "瑞典南部甲级联赛": ["Sweden - Division 1"],
    "瑞典甲级联赛": ["Sweden - Superettan"],
    "奥地利丙级联赛": ["Austria - Regionalliga"],
    "奥地利丁级联赛": ["Austria - Landesliga"],
    "罗马尼亚乙级联赛": ["Romania - Liga 2"],
    "罗马尼亚丙级联赛": ["Romania - Liga 3"],
    "俄罗斯乙级联赛": ["Russia - 2nd Division", "Russia - FNL"],
    "土耳其超级联赛": ["Turkey - Super Lig"],
    "土耳其甲级联赛": ["Turkey - 1. Lig"],
    "土耳其乙级联赛": ["Turkey - 2. Lig"],
    "以色列乙级联赛": ["Israel - Liga Leumit"],
    "以色列甲级联赛": ["Israel - Liga Alef"],
    # 英伦三岛
    "苏格兰超级联赛": ["Scotland - Premiership"],
    "苏格兰冠军联赛": ["Scotland - Championship"],
    "苏格兰甲级联赛": ["Scotland - League One"],
    "苏格兰乙级联赛": ["Scotland - League Two"],
    "苏格兰足总杯": ["Scotland - Cup"],
    "威尔士锦标赛": ["Wales - Championship"],
    "威尔士超级联赛": ["Wales - Premier League"],
    "爱尔兰超级联赛": ["Ireland - Premier Division"],
}

# 外置自动生成的联赛映射（由 gen_league_map.py -> apply_league_map.py 产出）
_AUTO_HINT = r"D:\cl\qqsj_v2\league_hint_auto.json"
try:
    import json as _json
    import os as _os
    if _os.path.exists(_AUTO_HINT):
        with open(_AUTO_HINT, encoding="utf-8") as _f:
            for _k, _v in _json.load(_f).items():
                # 手工规则优先，自动映射只补空缺
                LEAGUE_HINT.setdefault(_k, _v)
except Exception:
    pass

SUFFIX = re.compile(r"\b(fc|cf|sc|ac|afc|cd|ud|sv|fk|nk|bk|if|ff|sk|fk|ca|ec|ss|ssc|as|us)\b")

TEAM_MAP_CSV = r"D:\cl\qqsj_v2\qiety_team_map.csv"


def load_team_map(con):
    """qiety 中文队名 -> 英文。库内 team_name_map 优先，CSV 覆盖。"""
    import csv
    import os
    m = {}
    try:
        for r in con.execute("SELECT zh_name, en_name FROM team_name_map "
                             "WHERE zh_name IS NOT NULL AND en_name IS NOT NULL"):
            m[str(r[0]).strip()] = str(r[1]).strip()
    except sqlite3.OperationalError:
        pass
    if os.path.exists(TEAM_MAP_CSV):
        with open(TEAM_MAP_CSV, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                zh = (row.get("zh_name") or "").strip()
                en = (row.get("en_name") or "").strip()
                if zh and en:
                    m[zh] = en
    return m


def norm(x):
    s = str(x or "").lower()
    s = s.replace("-", " ").replace(".", " ").replace("'", "").replace("&", "and")
    s = re.sub(r"[（(].*?[)）]", " ", s)
    s = SUFFIX.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def sim(a, b):
    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    r = SequenceMatcher(None, na, nb).ratio()
    if na in nb or nb in na:
        r = max(r, 0.92)
    return r


def P(t):
    try:
        return datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def build_index(con):
    """建 Pinnacle 赛事索引：league_name -> [(kickoff_dt, pinn_id, home, away)]"""
    rows = con.execute("""
        SELECT pinn_id, home_team, away_team, kickoff_utc, league_name
        FROM theodds_fixtures
        WHERE source='pinnacle' AND pinn_id IS NOT NULL AND kickoff_utc IS NOT NULL
        GROUP BY pinn_id
    """).fetchall()
    by_league = defaultdict(list)
    allrows = []
    for r in rows:
        d = P(r["kickoff_utc"])
        if not d:
            continue
        item = (d, int(r["pinn_id"]), str(r["home_team"] or ""), str(r["away_team"] or ""))
        allrows.append(item)
        lg = str(r["league_name"] or "")
        by_league[lg].append(item)
    for v in by_league.values():
        v.sort(key=lambda x: x[0])
    allrows.sort(key=lambda x: x[0])
    return by_league, allrows


def match_one(h, a, ko, by_league, allrows, league_zh, tmap=None, window_min=30):
    """返回 (pinn_id, score, reason)

    h/a 是 qiety 中文队名，必须先用 tmap 转成英文再和 Pinnacle 比，
    否则中文 vs 英文相似度恒为 0（这是 v1 最大的 bug）。
    """
    if tmap:
        h = tmap.get(str(h).strip(), h)
        a = tmap.get(str(a).strip(), a)
    # 1) 联赛内匹配
    hints = []
    if league_zh:
        for k, v in LEAGUE_HINT.items():
            if k in str(league_zh):
                hints.extend(v)
                break
    pool = []
    if hints:
        for lg, items in by_league.items():
            if any(hh.lower() in lg.lower() for hh in hints):
                pool.extend([it for it in items
                             if abs((it[0] - ko).total_seconds()) <= window_min * 60])
    # 2) 联赛没筛出 -> 全量时间窗
    reason = "league" if pool else "time"
    if not pool:
        pool = [it for it in allrows if abs((it[0] - ko).total_seconds()) <= 15 * 60]

    if not pool:
        return None, 0.0, "notfound"

    scored = []
    for d, pid, ph, pa in pool:
        s1 = min(sim(h, ph), sim(a, pa))          # 正常主客
        s2 = min(sim(h, pa), sim(a, ph))          # 主客互换
        s = max(s1, s2)
        scored.append((s, pid))
    scored.sort(key=lambda x: -x[0])
    top = scored[0]
    second = scored[1][1] if len(scored) > 1 else -1
    if top[0] >= 0.80 and (len(scored) == 1 or top[0] > second * 0 + scored[1][0] or top[0] - scored[1][0] > 0.05):
        return top[1], round(top[0], 3), reason
    return None, round(top[0], 3), "lowscore"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"D:\cl\qqsj\data\sports_data.db")
    ap.add_argument("--write", action="store_true", help="写回 soft_odds_snapshots.pinn_id")
    ap.add_argument("--days", type=int, default=3)
    a = ap.parse_args()

    con = sqlite3.connect(a.db, timeout=120)
    con.row_factory = sqlite3.Row
    by_league, allrows = build_index(con)
    print(f"Pinnacle 赛事索引: {len(allrows)} 场, {len(by_league)} 个联赛")
    tmap = load_team_map(con)
    print(f"队名映射表: {len(tmap)} 条")

    rows = con.execute("""
        SELECT match_key, home_team, away_team, kickoff_utc, league,
               COUNT(*) n, MIN(id) min_id, MAX(id) max_id
        FROM soft_odds_snapshots
        WHERE source='qiety' AND kickoff_utc IS NOT NULL
          AND julianday('now') - julianday(kickoff_utc) < ?
        GROUP BY match_key
    """, (a.days,)).fetchall()
    print(f"待匹配 qiety 赛事: {len(rows)} 场")

    stat = defaultdict(int)
    updates = []
    for r in rows:
        ko = P(r["kickoff_utc"])
        if not ko:
            stat["badtime"] += 1
            continue
        pid, score, why = match_one(r["home_team"], r["away_team"], ko,
                                    by_league, allrows, r["league"], tmap)
        stat[why if pid else f"fail_{why}"] += 1
        if pid:
            updates.append((pid, r["min_id"], r["max_id"]))

    total = len(rows)
    ok = len(updates)
    print(f"\n匹配成功 {ok}/{total} ({ok/total*100:.1f}%)" if total else "\n无数据")
    for k, v in sorted(stat.items()):
        print(f"  {k:14} {v}")

    if a.write and updates:
        for pid, lo, hi in updates:
            con.execute("UPDATE soft_odds_snapshots SET pinn_id=? "
                        "WHERE source='qiety' AND id BETWEEN ? AND ? AND pinn_id IS NULL",
                        (pid, lo, hi))
        con.commit()
        print(f"\n已写回 {len(updates)} 个 match 的 pinn_id")
    elif not a.write:
        print("\n（未写库，加 --write 才更新）")
    con.close()


if __name__ == "__main__":
    main()
