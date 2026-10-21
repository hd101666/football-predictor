# -*- coding: utf-8 -*-
# corner_model.py — 角球负二项预测模型（v2 校准版）
# 数据来源: corner_team_stats + corner_league_baseline
# 后备: fd_corner_stats 动态查询 + 通用联赛默认基线
# 改进: 联赛校准因子 + 联赛白名单 + 球队级数据优先
# 输出: over/under 各档概率 + 校准后的推荐

import sys, math, logging, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
log = logging.getLogger(__name__)

from scipy.stats import nbinom
from sqlalchemy import create_engine, text

import env_setup
from config import DB_ENGINE_URL

engine = create_engine(DB_ENGINE_URL, connect_args={"timeout": 30})

# ── 联赛白名单（仅这些联赛有足够的 fd_corner_stats 训练数据）──────────────
LEAGUE_WHITELIST = {
    "E0": "英格兰超级联赛", "E1": "英格兰冠军联赛", "E2": "英格兰甲级联赛", "E3": "英格兰乙级联赛",
    "SC0": "苏格兰超级联赛",
    "D1": "德国甲级联赛", "D2": "德国乙级联赛",
    "SP1": "西班牙甲级联赛", "SP2": "西班牙乙级联赛",
    "I1": "意大利甲级联赛", "I2": "意大利乙级联赛",
    "F1": "法国甲级联赛", "F2": "法国乙级联赛",
    "N1": "荷兰甲级联赛",
    "B1": "比利时甲级联赛",
    "P1": "葡萄牙超级联赛",
    "T1": "土耳其超级联赛",
    "G1": "希腊超级联赛",
    "EC": "National League",  # 英格兰全国联赛
}

# ── 联赛校准因子（根据回测 v2 的偏差修正）
# 回测发现：模型在某些联赛/盘口系统性低估或高估
# key = league_code:line, value = (偏差, 样本数)
# 正偏差 = 模型P < 实际率（模型低估），应加回
# 负偏差 = 模型P > 实际率（模型高估），应减去
LEAGUE_CALIBRATION = {
    # 英系联赛大8.5（模型系统性低估5-7%）
    "E0:8.5":  {"bias": 0.048, "games": 3441},
    "E1:8.5":  {"bias": 0.036, "games": 4637},
    "E2:8.5":  {"bias": 0.054, "games": 4686},
    "E3:8.5":  {"bias": 0.053, "games": 4695},
    "SC0:8.5": {"bias": 0.048, "games": 1975},
    # 法甲大8.5（模型低估4.4%）
    "F1:8.5":  {"bias": 0.044, "games": 2314},
    # 意甲大8.5（模型低估5%）
    "I1:8.5":  {"bias": 0.050, "games": 2834},
    # 德甲大8.5（模型低估5.2%）
    "D1:8.5":  {"bias": 0.052, "games": 2372},
    # 英系小12.5（模型高估1-2%）
    "E0:12.5": {"bias": -0.012, "games": 3441},
    "E1:12.5": {"bias": -0.013, "games": 4637},
    "E2:12.5": {"bias": -0.017, "games": 4686},
    "E3:12.5": {"bias": -0.015, "games": 4695},
    # 西班牙系 大8.5（模型低估5.4%）
    "SP1:8.5": {"bias": 0.054, "games": 2699},
    "SP2:8.5": {"bias": 0.036, "games": 1186},
    # 意乙大8.5（模型低估4.6%）
    "I2:8.5":  {"bias": 0.046, "games": 1141},
    # 西甲小12.5（模型高估2.2%）
    "SP1:12.5":{"bias": -0.022, "games": 2699},
    # 意甲小12.5（模型高估2.7%）
    "I1:12.5": {"bias": -0.027, "games": 2834},
    # 其他联赛9.5线校准度很好，偏差<1%，不做调整
}

def is_league_supported(league_code: str) -> bool:
    """检查联赛是否在支持的白名单中"""
    return league_code in LEAGUE_WHITELIST

def get_calibration_factor(league_code: str, line: float) -> float:
    """获取联赛/盘口的校准偏差，精确匹配"""
    key = f"{league_code}:{line}"
    if key in LEAGUE_CALIBRATION:
        return LEAGUE_CALIBRATION[key]["bias"]
    return 0.0

# ── 负二项分布参数估计 ─────────────────────────────────────────────────────────
_DEFAULT_DISPERSION = 6.0
_MIN_DISPERSION     = 1.5
_MAX_DISPERSION     = 20.0

def _nbinom_r(mu: float, std: float) -> float:
    var = std ** 2
    if var <= mu or mu <= 0:
        return _MAX_DISPERSION
    r = mu ** 2 / (var - mu)
    return max(_MIN_DISPERSION, min(_MAX_DISPERSION, r))

def _nbinom_pmf_array(mu: float, r: float, max_k: int = 35) -> list:
    p = r / (r + mu)
    return [nbinom.pmf(k, r, p) for k in range(max_k + 1)]

def _over_prob(pmf: list, line: float) -> float:
    k_max = int(math.floor(line))
    return max(0.0, min(1.0, 1.0 - sum(pmf[:k_max + 1])))

# ── 球队中文名→英文名映射 ──────────────────────────────────────────────────
_CN2EN_TEAM: dict = {
    "美国": "USA", "加拿大": "Canada", "墨西哥": "Mexico",
    "韩国": "Korea Republic", "捷克": "Czech Republic",
    "巴拉圭": "Paraguay", "南非": "South Africa", "波黑": "Bosnia",
    "沙姆洛克流浪": "Shamrock Rovers", "德里城": "Derry City",
    "波希米亚人": "Bohemians", "舒尔本": "Shelbourne",
    "圣帕特里克竞技": "St Patrick's", "德罗赫达联": "Drogheda United",
    "戈尔韦联": "Galway United", "敦达克": "Dundalk",
    "沃特福德FC": "Waterford", "斯莱戈流浪者": "Sligo Rovers",
    "科克城": "Cork City", "布雷": "Bray Wanderers",
    "都柏林大学": "UCD", "费恩夏普": "Finn Harps",
    "韦克斯福德": "Wexford", "亚隆城": "Athlone Town",
    "凯里": "Kerry", "特瑞特联": "Treaty United",
    "阿尔科威特": "Kuwait SC", "卡斯马": "Kazma",
    "沙米亚": "Al Shamiya", "阿尔纳赛尔费尔瓦尼耶": "Al Nasr",
    "沙巴伯科威特": "Shabab Al Kuwait", "阿尔杰拉": "Al Jahra",
    "奥达克斯意大利人": "Audax Italiano", "拉塞雷纳": "La Serena",
    "戈亚尼亚竞技GO": "Atletico Go", "巴西雷加塔斯AL": "CRB",
    "圣贝纳多SP": "Sao Bernardo", "基斯奥马SC": "Chapecoense",
    "尤文图德RS": "Juventude", "库亚巴体育MT": "Cuiaba",
    "庞特普雷塔SP": "Ponte Preta", "福塔莱萨CE": "Fortaleza",
    "累西腓航海PE": "Nautico", "铁路工人PR": "Ferroviario",
    "隆德里纳PR": "Londrina",
    "卡萨布兰卡拉贾": "Raja Casablanca", "拉巴特联盟": "FUS Rabat",
    "马格里布菲斯": "Maghreb Fez", "奥林匹克萨非": "Olympic Safi",
    "托加联合队": "Ittihad Tanger", "拉巴特": "AS FAR",
    "梅克内斯": "COD Meknes", "马拉肯查": "Mouloudia Oujda",
    "雅各布曼苏尔": "Yacoub El Mansour",
    "DHJ哈斯沙尼亚": "DHJ El Jadida", "奥林匹克迪瑟利亚": "Olympic Dcheira",
    "扎尔吉里斯": "Zalgiris", "帕纳瓦兹": "FK Panevezys",
    "斯奥利埃": "FA Siauliai", "泰尔希艾久加斯": "FK Transinvest",
    "瑞特瑞埃": "FK Riteriai",
    "利耶帕亚": "FK Liepaja", "超新星": "Super Nova",
    "图库姆斯": "FK Tukums", "陶格夫匹尔斯": "BFC Daugavpils",
    "贝鲁特星": "Bourj", "阿尔阿赫德": "Al Ahed",
    "萨杰斯": "Sagesse", "雷亚迪阿巴塞亚": "Racing Beirut",
    "布雷堡": "Bleiburg", "特赖巴赫": "Treibach",
}

def _normalize_team_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower().strip())

def _fuzzy_match_team(name: str, candidates: list) -> str | None:
    n1 = _normalize_team_name(name)
    for c in candidates:
        n2 = _normalize_team_name(c)
        if n1 == n2:
            return c
        if len(n1) >= 3 and (n1 in n2 or n2 in n1):
            return c
    return None

def _dynamic_lookup_team(team: str, league_code: str = "") -> dict | None:
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT hc, ac, hst, ast
                FROM fd_corner_stats
                WHERE (LOWER(home_team) LIKE LOWER(:t)
                   OR LOWER(away_team) LIKE LOWER(:t))
                  AND league_code = :lc
                  AND hc IS NOT NULL AND ac IS NOT NULL
            """), {"t": f"%{team}%", "lc": league_code}).fetchall()
            if not rows:
                rows = conn.execute(text("""
                    SELECT hc, ac, hst, ast
                    FROM fd_corner_stats
                    WHERE (LOWER(home_team) LIKE LOWER(:t)
                       OR LOWER(away_team) LIKE LOWER(:t))
                      AND hc IS NOT NULL AND ac IS NOT NULL
                """), {"t": f"%{team}%"}).fetchall()
            if not rows:
                return None

            crn_for = [r[0] for r in rows]
            crn_against = [r[1] for r in rows]

            n = len(crn_for)
            if n < 3:
                return None

            import numpy as np
            cf_arr = np.array(crn_for, dtype=float)
            ca_arr = np.array(crn_against, dtype=float)

            return {
                "avg_crn_for": float(cf_arr.mean()),
                "avg_crn_against": float(ca_arr.mean()),
                "std_crn_for": float(cf_arr.std(ddof=1)) if n > 1 else 3.0,
                "avg_crn_for_home": float(cf_arr.mean()),
                "avg_crn_for_away": float(cf_arr.mean()),
                "avg_crn_against_home": float(ca_arr.mean()),
                "avg_crn_against_away": float(ca_arr.mean()),
                "attack_rating": 1.0,
                "defense_rating": 1.0,
                "games": n,
                "_dynamic": True,
            }
    except Exception:
        return None

_LEAGUE_BASELINE_GUESS: dict = {
    "世界杯": "E0", "世界盃": "E0",
    "爱尔兰超级": "SC0", "爱尔兰甲级": "SC2",
    "科威特超级": "T1", "黎巴嫩超级": "I2",
    "立陶宛甲级": "SC3", "拉脱维亚超级": "SC3",
    "智利甲级": "SP1", "摩洛哥甲级": "G1",
    "奥地利业余": "EC", "巴西乙级": "I2", "巴西": "I2",
}
_LEAGUE_BASELINE_DEFAULT = "E0"

def _guess_league_code(league_name: str) -> str | None:
    if not league_name:
        return None
    ln = league_name.lower()
    for kw, lc in _LEAGUE_BASELINE_GUESS.items():
        if kw.lower() in ln:
            return lc
    kw_map = [
        ("premier league", "E0"), ("premier", "E0"),
        ("championship", "E1"), ("league one", "E2"), ("league two", "E3"),
        ("bundesliga", "D1"), ("2. bundesliga", "D2"),
        ("la liga", "SP1"), ("serie a", "I1"), ("serie b", "I2"),
        ("ligue 1", "F1"), ("ligue 2", "F2"),
        ("eredivisie", "N1"), ("primeira", "P1"),
        ("premiership", "SC0"), ("super lig", "T1"),
        ("super league", "G1"), ("jupiler", "B1"),
        ("national league", "EC"),
    ]
    # Bug修复(2026-08-10)：原来按上面手写的固定顺序逐个查"kw in ln"命中就返回，
    # 但"premier"是"premiership"的前缀子串、"bundesliga"是"2. bundesliga"的前缀
    # 子串——顺序写反时短关键词会抢先命中，把"Scotland - Premiership"错误映射成
    # 英超"E0"（应为苏超"SC0"）、把"Germany - 2. Bundesliga"错误映射成德甲"D1"
    # （应为德乙"D2"）。这个联赛代码错了，会让_lookup_league()后续拿错联赛的
    # avg_total去做scale校正，把预测值悄悄拉向错误联赛的角球风格，属于"看似有
    # 真实球队数据支撑、实际被联赛级别信号污染"的隐蔽陷阱，跟CLAUDE.md"推荐单
    # 数据支撑规则"警告的兜底伪装同一类问题。按关键词长度降序排序再遍历，让
    # 更具体的长关键词永远先于其子串短关键词被检查，一次性堵死这整类问题，
    # 不需要以后新增联赛时手动排查顺序。
    for kw, lc in sorted(kw_map, key=lambda x: -len(x[0])):
        if kw in ln:
            return lc
    return None

def _lookup_team(team: str, league_code: str = "") -> dict | None:
    search_names = [team]
    if team in _CN2EN_TEAM:
        search_names.append(_CN2EN_TEAM[team])
    else:
        # 2026-07-29修复：_CN2EN_TEAM是本文件自维护的小众联赛专用词典，覆盖面
        # 有限——用team_mapping.py维护的通用中英文词典(~160条主流球队/国家队)
        # 补一次，team_en()对已经是英文的输入本身安全直通，不会误翻译
        try:
            from team_mapping import team_en
            en_name = team_en(team)
            if en_name != team:
                search_names.append(en_name)
        except Exception:
            pass

    for chars in [7, 6, 5, 4]:
        for sname in search_names:
            t_pat = f"%{sname[:chars]}%"
            try:
                with engine.connect() as conn:
                    if league_code:
                        row = conn.execute(text("""
                            SELECT avg_crn_for, avg_crn_against, std_crn_for,
                                   avg_crn_for_home, avg_crn_for_away,
                                   avg_crn_against_home, avg_crn_against_away,
                                   attack_rating, defense_rating, games
                            FROM corner_team_stats
                            WHERE LOWER(team) LIKE LOWER(:t)
                              AND league_code = :lc
                            ORDER BY games DESC LIMIT 1
                        """), {"t": t_pat, "lc": league_code}).fetchone()
                        if row and row[0]:
                            return dict(zip(
                                ["avg_crn_for","avg_crn_against","std_crn_for",
                                 "avg_crn_for_home","avg_crn_for_away",
                                 "avg_crn_against_home","avg_crn_against_away",
                                 "attack_rating","defense_rating","games"], row))
                    row = conn.execute(text("""
                        SELECT avg_crn_for, avg_crn_against, std_crn_for,
                               avg_crn_for_home, avg_crn_for_away,
                               avg_crn_against_home, avg_crn_against_away,
                               attack_rating, defense_rating, games
                        FROM corner_team_stats
                        WHERE LOWER(team) LIKE LOWER(:t)
                        ORDER BY games DESC LIMIT 1
                    """), {"t": t_pat}).fetchone()
                    if row and row[0]:
                        return dict(zip(
                            ["avg_crn_for","avg_crn_against","std_crn_for",
                             "avg_crn_for_home","avg_crn_for_away",
                             "avg_crn_against_home","avg_crn_against_away",
                             "attack_rating","defense_rating","games"], row))
            except Exception:
                pass

    for sname in search_names:
        result = _dynamic_lookup_team(sname, league_code)
        if result:
            return result
    return None

def _lookup_league(league_code: str, league_name: str = "") -> dict:
    _lc_map = [
        ("premier", "E0"), ("championship", "E1"), ("league one", "E2"),
        ("league two", "E3"), ("bundesliga 2", "D2"), ("bundesliga", "D1"),
        ("la liga 2", "SP2"), ("la liga", "SP1"), ("serie a", "I1"),
        ("serie b", "I2"), ("ligue 1", "F1"), ("ligue 2", "F2"),
        ("eredivisie", "N1"), ("primeira", "P1"), ("premiership", "SC0"),
        ("super lig", "T1"), ("super league", "G1"), ("jupiler", "B1"),
        ("national league", "EC"),
    ]
    candidates = [league_code] if league_code else []
    guessed = _guess_league_code(league_name)
    if guessed:
        candidates.append(guessed)
    ln_lower = (league_name or "").lower()
    for kw, lc in _lc_map:
        if kw in ln_lower:
            candidates.append(lc)
    candidates = list(dict.fromkeys(candidates))

    for lc in candidates:
        try:
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT avg_total, std_total, avg_home_crn, avg_away_crn,
                           over_9_5_pct, over_10_5_pct, over_11_5_pct
                    FROM corner_league_baseline WHERE league_code=:lc LIMIT 1
                """), {"lc": lc}).fetchone()
            if row:
                return {
                    "avg_total": float(row[0]), "std_total": float(row[1]),
                    "avg_home_crn": float(row[2]), "avg_away_crn": float(row[3]),
                    "over_9_5_pct": float(row[4]), "over_10_5_pct": float(row[5]),
                    "over_11_5_pct": float(row[6]), "_is_fallback": False,
                }
        except Exception:
            pass
    # Bug修复(2026-08-10)：以下是查不到真实联赛baseline时的全局硬编码兜底
    # (混合了全部联赛的粗略均值，不代表任何具体联赛的角球风格)。之前这里
    # 返回的dict没有任何"这是兜底值"的标记，predict_corners()的used_team_data
    # 判断只看球队级数据是否真实，完全没检查联赛级scale校正用的是不是这个
    # 兜底值——实测2026-08-10发现Scotland Premiership曾因_guess_league_code()
    # 联赛代码识别bug落到这里，把预测悄悄拉向10.57这个跟苏超真实均值(11.011)
    # 不符的全局数字，而used_team_data却显示True，是"看似有真实数据支撑、
    # 实际被兜底污染"的隐蔽陷阱。现在显式标记_is_fallback=True，让调用方能
    # 识别并按"没数据就跳过、不伪造信号"的原则处理，不再无声地把污染值
    # 当真实信号用。
    return {"avg_total": 10.57, "std_total": 3.50, "_is_fallback": True,
            "avg_home_crn": 5.78, "avg_away_crn": 4.79,
            "over_9_5_pct": 0.57, "over_10_5_pct": 0.50, "over_11_5_pct": 0.38}

# ── 核心预测函数（v2 校准版）──────────────────────────────────────────────
def predict_corners(home: str, away: str,
                    league_code: str = "", league_name: str = "",
                    is_home_game: bool = True) -> dict:
    """
    负二项预测角球大小球/让球概率（v2 校准版）。

    相比v1的改进：
    1. 联赛白名单检查（不在白名单的联赛打标记）
    2. 校准因子修正（基于回测偏差）
    3. 球队级数据优先（corner_team_stats）
    4. 输出额外字段：calibration_info, league_supported
    """
    lb = _lookup_league(league_code, league_name)
    h_stats = _lookup_team(home, league_code)
    a_stats = _lookup_team(away, league_code)

    league_supported = is_league_supported(league_code) if league_code else False

    _USE_DYNAMIC = False
    # Bug修复(2026-08-10)：原来只检查球队级数据是否真实，没检查lb(联赛baseline)
    # 是否也命中了真实的corner_league_baseline记录——球队数据真实但联赛baseline
    # 兜底(_is_fallback=True)时，后面的scale校正仍会用兜底值把预测拉偏，
    # used_team_data却错误地显示True。现在把lb的兜底标记也纳入判断，任何一层
    # 是伪造/兜底信号，整体就不算"有真实数据支撑"，跟FotMob角球影子桶
    # "缺信号直接返回None、不伪造"的原则保持一致。
    _USE_TEAM_DATA = bool(h_stats and a_stats and not h_stats.get('_default') and not a_stats.get('_default')
                           and not lb.get('_is_fallback'))

    if not h_stats or not a_stats:
        if not h_stats:
            h_stats = {
                "avg_crn_for": lb["avg_home_crn"],
                "avg_crn_against": lb["avg_away_crn"],
                "std_crn_for": 3.0,
                "avg_crn_for_home": lb["avg_home_crn"],
                "avg_crn_for_away": lb["avg_away_crn"],
                "avg_crn_against_home": lb["avg_away_crn"],
                "avg_crn_against_away": lb["avg_home_crn"],
                "attack_rating": 1.0,
                "defense_rating": 1.0,
                "games": 0,
                "_default": True,
            }
            _USE_DYNAMIC = True
        if not a_stats:
            a_stats = {
                "avg_crn_for": lb["avg_away_crn"],
                "avg_crn_against": lb["avg_home_crn"],
                "std_crn_for": 3.0,
                "avg_crn_for_home": lb["avg_home_crn"],
                "avg_crn_for_away": lb["avg_away_crn"],
                "avg_crn_against_home": lb["avg_away_crn"],
                "avg_crn_against_away": lb["avg_home_crn"],
                "attack_rating": 1.0,
                "defense_rating": 1.0,
                "games": 0,
                "_default": True,
            }
            _USE_DYNAMIC = True

    lg_home_avg = lb["avg_home_crn"]
    lg_away_avg = lb["avg_away_crn"]

    if is_home_game:
        lam_h = (h_stats["avg_crn_for_home"] or h_stats["avg_crn_for"]) * \
                (a_stats["defense_rating"] or 1.0)
        lam_a = (a_stats["avg_crn_for_away"] or a_stats["avg_crn_for"]) * \
                (h_stats["defense_rating"] or 1.0)
    else:
        lam_h = h_stats["avg_crn_for"] * (a_stats["defense_rating"] or 1.0)
        lam_a = a_stats["avg_crn_for"] * (h_stats["defense_rating"] or 1.0)

    if _USE_DYNAMIC:
        lam_h = lb["avg_home_crn"]
        lam_a = lb["avg_away_crn"]

    pred_total = lam_h + lam_a
    scale = lb["avg_total"] / max(pred_total, 0.5)
    scale = max(0.6, min(1.4, scale))
    lam_h = round(lam_h * scale, 3)
    lam_a = round(lam_a * scale, 3)

    std_h = h_stats["std_crn_for"] or 3.0
    std_a = a_stats["std_crn_for"] or 3.0
    r_h   = _nbinom_r(lam_h, std_h)
    r_a   = _nbinom_r(lam_a, std_a)

    pmf_h = _nbinom_pmf_array(lam_h, r_h)
    pmf_a = _nbinom_pmf_array(lam_a, r_a)
    max_k = len(pmf_h) + len(pmf_a) - 2
    pmf_total = [0.0] * (max_k + 1)
    for i, p_h in enumerate(pmf_h):
        for j, p_a in enumerate(pmf_a):
            if i + j <= max_k:
                pmf_total[i + j] += p_h * p_a

    result: dict = {
        "exp_home":  lam_h,
        "exp_away":  lam_a,
        "exp_total": round(lam_h + lam_a, 2),
        "source":    "corner_nbinom_v2",
        "league_supported": league_supported,
        "used_team_data": _USE_TEAM_DATA,
        "calibration_info": {},
    }

    # ── 大小球概率（校准版）───────────────────────────────────────────────────
    for line in [8.5, 9.5, 10.5, 11.5, 12.5]:
        ov_raw = round(_over_prob(pmf_total, line), 4)
        # 应用校准因子
        cal_bias = get_calibration_factor(league_code, line)
        ov_calibrated = round(max(0.001, min(0.999, ov_raw + cal_bias)), 4)
        under_calibrated = round(1 - ov_calibrated, 4)

        key = f"over_{str(line).replace('.','_')}"
        result[key]   = ov_calibrated
        result[f"under_{str(line).replace('.','_')}"] = under_calibrated
        result["calibration_info"][f"line_{line}"] = {
            "raw_p": ov_raw,
            "bias": cal_bias,
            "calibrated_p": ov_calibrated,
        }

    # ── 让球盘口概率 (-3.5 ~ +3.5)────────────────────────────────────────────
    sigma_diff = math.sqrt(lam_h / r_h * (r_h + lam_h) +
                           lam_a / r_a * (r_a + lam_a))
    margin = lam_h - lam_a
    hdp: dict = {}
    from scipy.stats import norm as _norm
    for h in [-3.5, -2.5, -1.5, -0.5, 0.5, 1.5, 2.5, 3.5]:
        p_home = round(float(_norm.sf(h, loc=margin, scale=sigma_diff)), 4)
        hdp[str(h)] = (max(0.02, min(0.98, p_home)),
                       max(0.02, min(0.98, round(1 - p_home, 4))))
    result["handicap_probs"] = hdp

    return result

# ── 世界杯国家队角球模型 ─────────────────────────────────────────────────────
_WC_CORNERS: dict = {
    "netherlands": {"for": 5.2, "against": 3.8}, "japan":       {"for": 4.1, "against": 5.1},
    "ivory coast": {"for": 4.5, "against": 4.8}, "cote d'ivoire":{"for": 4.5,"against": 4.8},
    "ecuador":     {"for": 4.2, "against": 4.6}, "sweden":      {"for": 4.8, "against": 4.4},
    "tunisia":     {"for": 3.6, "against": 5.2}, "spain":       {"for": 5.5, "against": 3.7},
    "cape verde":  {"for": 3.8, "against": 5.5}, "belgium":     {"for": 5.2, "against": 3.9},
    "egypt":       {"for": 3.8, "against": 5.4}, "saudi arabia":{"for": 3.9, "against": 5.3},
    "uruguay":     {"for": 4.6, "against": 4.6}, "iran":        {"for": 3.8, "against": 5.2},
    "new zealand": {"for": 4.0, "against": 5.0}, "france":      {"for": 5.4, "against": 3.8},
    "senegal":     {"for": 4.0, "against": 5.2}, "iraq":        {"for": 3.7, "against": 5.5},
    "norway":      {"for": 4.8, "against": 4.4}, "argentina":   {"for": 5.1, "against": 4.0},
    "algeria":     {"for": 3.8, "against": 5.4}, "austria":     {"for": 5.0, "against": 4.2},
    "jordan":      {"for": 3.5, "against": 5.8}, "portugal":    {"for": 5.3, "against": 3.9},
    "dr congo":    {"for": 4.0, "against": 5.2}, "england":     {"for": 5.4, "against": 3.8},
    "croatia":     {"for": 4.5, "against": 4.7}, "ghana":       {"for": 4.2, "against": 4.9},
    "panama":      {"for": 3.5, "against": 5.7}, "uzbekistan":  {"for": 4.0, "against": 5.0},
    "colombia":    {"for": 4.8, "against": 4.4}, "czechia":     {"for": 4.8, "against": 4.4},
    "south africa":{"for": 4.1, "against": 4.9}, "switzerland": {"for": 4.9, "against": 4.3},
    "canada":      {"for": 4.5, "against": 4.7}, "qatar":       {"for": 3.8, "against": 5.4},
    "mexico":      {"for": 4.7, "against": 4.5}, "south korea": {"for": 4.4, "against": 4.8},
    "usa":         {"for": 4.6, "against": 4.6}, "australia":   {"for": 4.3, "against": 4.9},
    "scotland":    {"for": 4.8, "against": 4.4}, "morocco":     {"for": 4.4, "against": 4.8},
    "brazil":      {"for": 5.6, "against": 3.7}, "haiti":       {"for": 3.2, "against": 6.0},
    "turkiye":     {"for": 4.6, "against": 4.6}, "turkey":      {"for": 4.6, "against": 4.6},
    "paraguay":    {"for": 4.3, "against": 4.9},
    "bosnia and herzegovina": {"for": 4.2, "against": 4.8},
    "bosnia":      {"for": 4.2, "against": 4.8},
}

def _wc_lookup(name: str) -> dict | None:
    nl = name.lower().strip()
    if nl in _WC_CORNERS:
        return _WC_CORNERS[nl]
    for k, v in _WC_CORNERS.items():
        if k in nl or nl in k:
            return v
    return None

# ── 混合分布概率计算 ──────────────────────────────────────────────────────────
# 回测结论: 正态在 ≤10.5 更准(误差<-0.1%), 负二项在 ≥11.5 更准(误差<-1.5%)
def _over_prob_hybrid(mu: float, sigma: float, pmf_total: list, line: float) -> float:
    """线 ≤ 10.5 用正态, ≥ 11.5 用负二项"""
    from scipy.stats import norm as _norm
    if line <= 10.5:
        return float(_norm.sf(line, mu, sigma))
    return _over_prob(pmf_total, line)

# ── 角球投注单生成（集成入命中系统）─────────────────────────────────────────
MU_BIAS_CORRECTION = 0.25   # 回测发现模型系统低估 +0.25 角球
CORNER_EV_THRESHOLD = 0.10  # EV门槛 10%（回测：EV≥10%+双队=65.2%胜率）
CORNER_KELLY_FRAC   = 0.25  # 四分之一凯利


def _fotmob_corner_probs_safe(home: str, away: str, league_name: str, line: float) -> dict:
    """安全调用00_命中系统.py里get_fotmob_corner_probs()——2026-08-10新增，
    corner_model.py合并FotMob信号(58联赛覆盖)成为新版角球正式投注单，
    弥补原有corner_team_stats(football-data.co.uk，20个欧洲联赛白名单)覆盖
    不到的联赛。

    联赛名映射(_fotmob_league_lookup())是踩过多次坑才积累出来的逻辑
    (Pinnacle/FotMob/多数据源之间联赛拼写惯例完全不重叠，见00_命中系统.py
    2026-07-22那处修复注释)，不在这里重新写一份，避免两处维护、后续修复
    不同步。

    但corner_model.py不能直接`import 00_命中系统`——该文件是脚本式主控文件，
    独立测试/被非正常流程调用时会把7800+行主脚本当新模块重新执行一遍(见
    00_命中系统.py顶部2026-08-08修复说明的同类教训)。这里改用sys.modules
    防御性读取：只有当00_命中系统.py已经作为主流程加载完毕(该模块已注册到
    sys.modules)才会调用它的函数；corner_model.py被独立调用/测试时(如
    py_compile/单元验证)sys.modules里没有这个key，直接返回{}——诚实地承认
    这条路径在当前调用上下文不可用，不是伪造数据。"""
    import sys as _sys
    _hitsys = _sys.modules.get("00_命中系统")
    if _hitsys is None:
        return {}
    try:
        return _hitsys.get_fotmob_corner_probs(home, away, league_name, line=line) or {}
    except Exception:
        return {}

def get_corner_odds_candidates(fetch_date: str | None = None) -> list:
    """
    读取Pinnacle角球大小盘口，去重整理成候选比赛列表（未开赛、已选定主线）。
    从 generate_corner_slip() 抽出（2026-07-22），供该函数和FotMob角球影子桶
    (00_命中系统.py的_run_one_date())共用同一份候选源——后者此前直接复用
    generate_corner_slip()算出的corner_recs（只包含corner_team_stats覆盖到的
    20个欧洲联赛），导致FotMob覆盖的另外38个联赛（如美职联/巴西乙/韩K联/挪超，
    实测fotmob_match_team_stats.corners字段完整覆盖）永远没机会被独立评估。
    现在两边各自从这份候选源出发，各自判断"有没有自己能用的数据"，不再互相依赖。

    返回: [{"league","home","away","kick","bj","line","odds_o","odds_u"}, ...]
    """
    from datetime import datetime, timezone, timedelta

    if fetch_date is None:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    TZ_BJ = timezone(timedelta(hours=8))
    now_utc = datetime.now(timezone.utc)
    # 上界：次日12:00北京时间前(今日全部未开赛+次日12:00前，不推第三日)，
    # 跟00_命中系统.py主推荐单窗口口径一致。之前只过滤了"已开赛"(下界)，
    # 没有上界，导致pinnacle_corner_odds里任何还没开赛的比赛(哪怕是第三天/
    # 第四天的盘口)都会被当成候选，2026-07-27发现FotMob角球影子观察单混入了
    # 07-29(第三天)的比赛。
    _base_date = datetime.strptime(fetch_date, "%Y-%m-%d")
    win_end_utc = (_base_date + timedelta(days=1)).replace(
        hour=12, minute=0, second=0, tzinfo=TZ_BJ
    ).astimezone(timezone.utc)

    try:
        with engine.connect() as conn:
            raw = conn.execute(text("""
                SELECT DISTINCT league_name, home_team, away_team, kickoff_utc,
                       market_type, period, side, line, price_dec
                FROM pinnacle_corner_odds
                WHERE fetch_date = :fd
                  AND is_alternate = 0
                  AND status = 'open'
                  AND market_type = 'total'
                  AND period = 0
                ORDER BY kickoff_utc, line
            """), {"fd": fetch_date}).fetchall()
    except Exception as e:
        log.warning(f"  角球盘口读取失败: {e}")
        return []

    odds_map: dict = {}
    for league, home, away, kick, mtype, period, side, line, price in raw:
        if "(Corners)" in home or "(Bookings)" in home:
            continue
        try:
            dt = datetime.fromisoformat(kick.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt <= now_utc or dt > win_end_utc:
                continue
        except Exception:
            continue
        key = (league, home, away, kick)
        odds_map.setdefault(key, {})
        odds_map[key].setdefault(line, {})
        odds_map[key][line][side] = price

    match_keys: dict = {}
    for (league, home, away, kick), line_odds in odds_map.items():
        k = (league, home, away)
        if k not in match_keys:
            match_keys[k] = (kick, line_odds)

    def _get_main_line(line_odds: dict):
        best, best_score = None, 999.0
        for line, sides in line_odds.items():
            if "over" in sides and "under" in sides:
                score = abs(sides["over"] - 1.9) + abs(sides["under"] - 1.9)
                if score < best_score:
                    best_score = score
                    best = line
        if best is None:
            return None, None, None
        return best, line_odds[best]["over"], line_odds[best]["under"]

    candidates = []
    for (league, home, away), (kick, line_odds) in match_keys.items():
        main_line, odds_o, odds_u = _get_main_line(line_odds)
        if main_line is None:
            continue
        dt = datetime.fromisoformat(kick.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        bj = dt.astimezone(TZ_BJ)
        candidates.append({
            "league": league, "home": home, "away": away,
            "kickoff_utc": kick, "bj": bj,
            "line": main_line, "odds_o": odds_o, "odds_u": odds_u,
        })
    return candidates


def generate_corner_slip(fetch_date: str | None = None, validated: bool = True) -> list:
    """
    生成角球投注推荐单并输出标准格式。
    集成到命中系统第四点五阶段。

    validated: 调用方(00_命中系统.py _run_one_date())传入_corner_validation_status()
    的结果。2026-09-06修复——此前这个函数无论转正与否都无条件把候选写进
    corner_recommendations（真钱结算表），00_命中系统.py那边的"转正"门控
    (_corner_validation_status())只改了展示阶段的标题文字("⚽角球投注单" vs
    "📊角球候选观察单")，完全没有拦截这里的DB写入——corner是全系统唯一一个
    "转正判定"跟"是否真的进真钱表"完全脱节的市场（对比market='total'/'moneyline'/
    'correct_score'走的_in_scope()，未转正的候选根本不会进hit_recommendations，
    而是被转存进shadow_multi['gated']反事实观察）。现在改成跟其他市场同一套
    架构：validated=False时候选正常计算/返回，但跳过INSERT，不再写入
    corner_recommendations；调用方(generate_recommendations())负责把返回的
    候选转存进shadow_multi['gated']。

    返回: list of dict (角球推荐记录) —— 不论validated与否都会返回完整候选列表，
    只是validated=False时不会持久化到corner_recommendations。
    """
    from datetime import datetime, timezone, timedelta
    from scipy.stats import norm as _norm

    if fetch_date is None:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    log.info(f"⚽ 角球分析 [{fetch_date}] 混合分布(正态≤10.5/负二项≥11.5) EV≥{CORNER_EV_THRESHOLD*100:.0f}%")

    # ── 0. 预加载国家队ELO（用于强弱悬殊惩罚）────────────────────────────────
    _elo_cache: dict = {}
    try:
        with engine.connect() as _ec:
            _elo_rows = _ec.execute(text("""
                SELECT team_name, elo_rating
                FROM national_team_elo
                WHERE (team_name, fetch_date) IN (
                    SELECT team_name, MAX(fetch_date)
                    FROM national_team_elo GROUP BY team_name
                )
            """)).fetchall()
        for tn, er in _elo_rows:
            _elo_cache[tn.lower().strip()] = float(er)
    except Exception:
        pass  # ELO不影响流程，失败时跳过惩罚

    def _get_elo(name: str) -> float | None:
        nl = name.lower().strip()
        if nl in _elo_cache:
            return _elo_cache[nl]
        for k, v in _elo_cache.items():
            if k in nl or nl in k:
                return v
        return None

    # ── 1-3. 候选比赛（读取Pinnacle主角球大小盘口 + 去重 + 选主线）──────────
    candidates = get_corner_odds_candidates(fetch_date)
    log.info(f"  有效场次（未开赛、含角球大小盘口）: {len(candidates)}")

    def _implied_fair(odds_o: float, odds_u: float):
        ro, ru = 1.0 / odds_o, 1.0 / odds_u
        t = ro + ru
        return ro / t, ru / t

    def _kelly(p: float, odds: float) -> float:
        b = odds - 1.0
        e = p * b - (1.0 - p)
        return max(0.0, e / b * CORNER_KELLY_FRAC) if e > 0 else 0.0

    def _hit_score(p_model: float, edge: float) -> float:
        return round(min(0.999, 0.5 + edge * 2.5 + p_model * 0.10), 3)

    is_wc = lambda lg: any(x in lg for x in ("FIFA", "World Cup", "世界杯"))

    # ── 4. 逐场预测 & EV筛选 ─────────────────────────────────────────────────
    recs = []
    skip_no_data, skip_no_ev = 0, 0

    for cand in candidates:
        league, home, away = cand["league"], cand["home"], cand["away"]
        kick, bj = cand["kickoff_utc"], cand["bj"]
        main_line, odds_o, odds_u = cand["line"], cand["odds_o"], cand["odds_u"]

        # ── 预测 ──────────────────────────────────────────────────────────
        if is_wc(league):
            # 世界杯国家队模型（中性场）
            h_wc, a_wc = _wc_lookup(home), _wc_lookup(away)
            if not (h_wc and a_wc):
                skip_no_data += 1
                continue
            mu_total = (h_wc["for"] + a_wc["against"]) / 2 + (a_wc["for"] + h_wc["against"]) / 2
            sigma_total = 3.2

            # ── 强弱悬殊惩罚：弱队蜷缩防守 → 实际角球低于均值 ───────────────
            over_hs_penalty = 1.0   # hit_score乘数（仅作用于over方向）
            h_elo = _get_elo(home)
            a_elo = _get_elo(away)
            if h_elo and a_elo:
                elo_gap = abs(h_elo - a_elo)
                if elo_gap >= 350:
                    mu_total     -= 1.5
                    over_hs_penalty = 0.65
                elif elo_gap >= 250:
                    mu_total     -= 1.0
                    over_hs_penalty = 0.75
                elif elo_gap >= 150:
                    mu_total     -= 0.5
                    over_hs_penalty = 0.88
            # 防守型弱队额外惩罚（corners_for < 3.8 → 主动进攻极少）
            if min(h_wc["for"], a_wc["for"]) < 3.8:
                mu_total -= 0.4
                over_hs_penalty *= 0.92
            mu_total = max(5.0, mu_total)   # 不低于合理下限

            # 用正态计算（WC赛均为常用线段 8.5-10.5）
            pmf_total = []
            p_over_model = float(_norm.sf(main_line, mu_total, sigma_total))
            src = "wc_model"
        else:
            over_hs_penalty = 1.0  # 俱乐部联赛不使用ELO惩罚
            # 俱乐部联赛：优先corner_team_stats(football-data.co.uk，20个欧洲
            # 联赛白名单，负二项/正态混合分布，有回测校准的sigma)
            lc = _guess_league_code(league) or ""
            crn = predict_corners(home, away, lc, league)
            if crn and crn.get("used_team_data"):
                mu_total = crn["exp_total"] + MU_BIAS_CORRECTION
                sigma_total = crn.get("_sigma", 3.4)
                lb = _lookup_league(lc, league)
                std_total = lb.get("std_total", 3.4)
                p_over_model = _over_prob_hybrid(mu_total, std_total,
                                                  crn.get("_pmf_total", []), main_line)
                src = "team_stats"
            else:
                # 2026-08-10新增：主数据源没有真实数据(球队缺统计，或联赛baseline
                # 是兜底值，见predict_corners()的used_team_data判定)——不直接跳过，
                # 改用FotMob信号(58联赛覆盖，见_fotmob_corner_probs_safe()说明)当
                # 补充数据源，扩大正式投注单的联赛覆盖面。两个数据源都没有才真正
                # 跳过，不伪造信号。FotMob路径没有回测校准的sigma，用跟其他缺失
                # 场景一致的默认值3.4，不假装有精确度。
                _fm = _fotmob_corner_probs_safe(home, away, league, main_line)
                if not _fm or _fm.get("over") is None:
                    skip_no_data += 1
                    continue
                mu_total = _fm["exp_total"]
                sigma_total = 3.4
                p_over_model = _fm["over"]
                src = "fotmob_team_stats"

        # ── EV计算 ────────────────────────────────────────────────────────
        p_fair_o, p_fair_u = _implied_fair(odds_o, odds_u)
        p_under_model = 1.0 - p_over_model

        edge_o = p_over_model  - p_fair_o
        edge_u = p_under_model - p_fair_u

        best_dir   = "over"  if edge_o >= edge_u else "under"
        best_edge  = edge_o  if edge_o >= edge_u else edge_u
        best_p     = p_over_model  if best_dir == "over"  else p_under_model
        best_odds  = odds_o        if best_dir == "over"  else odds_u
        best_pfair = p_fair_o      if best_dir == "over"  else p_fair_u

        if best_edge < CORNER_EV_THRESHOLD:
            skip_no_ev += 1
            continue

        k = _kelly(best_p, best_odds)
        p_fus = round(best_p * 0.6 + best_pfair * 0.4, 3)
        hs    = _hit_score(best_p, best_edge)
        # wc_model强弱悬殊时对over方向施加hit_score惩罚
        if src == "wc_model" and best_dir == "over":
            hs = round(hs * over_hs_penalty, 3)
        dir_label = f"大球>{main_line}" if best_dir == "over" else f"小球<{main_line}"

        recs.append({
            "bj": bj, "league": league, "home": home, "away": away,
            "kickoff_utc": kick, "line": main_line,
            "odds_o": odds_o, "odds_u": odds_u,
            "direction": best_dir, "odds": best_odds,
            "mu": round(mu_total, 2), "sigma": sigma_total,
            "p_model": round(best_p, 4), "p_fair": round(best_pfair, 4),
            "edge": round(best_edge, 4), "kelly": round(k, 4),
            "p_fusion": p_fus, "hit_score": hs,
            "dir_label": dir_label, "src": src,
        })

    recs.sort(key=lambda x: x["hit_score"], reverse=True)

    log.info(f"  无数据跳过: {skip_no_data}  EV不足跳过: {skip_no_ev}  推荐: {len(recs)}注")

    # ── 5. 输出标准格式投注单 ────────────────────────────────────────────────
    if recs:
        SEP = "=" * 110
        print()
        print(SEP)
        if validated:
            print(f"  ⚽ 角球投注单  [{fetch_date}]  混合分布(正态≤10.5/负二项≥11.5) | EV≥10% | 偏差修正+0.25")
        else:
            print(f"  📊 角球候选观察单  [{fetch_date}]  混合分布(正态≤10.5/负二项≥11.5) | EV≥10% | 偏差修正+0.25"
                  f"  [仅数据追踪，未正式启用]")
        print(SEP)
        hdr = (f"  {'开赛时间':<14}{'联赛':<18}{'主队':<17}{'客队':<17}"
               f"{'市场':<6}{'方向':<12}{'赔率':>6}{'p融合':>7}{'K₁/₄':>7}{'命中分':>8}  数据源")
        print(hdr)
        print("  " + "-" * 107)
        for r in recs[:15]:
            bj_s = r["bj"].strftime("%m月%d日%H:%M")
            lg   = (r["league"].replace("FIFA - ", "FIFA-")
                               .replace("Spain - ", "西班牙-")
                               .replace("Brazil - ", "巴西-")
                               .replace("Iceland - ", "冰岛-")
                               .replace("Sweden - ", "瑞典-")
                               .replace("Chile - ", "智利-")
                               .replace("Argentina - ", "阿根廷-"))[:16]
            h_s = f"[主]{r['home'][:12]}"
            a_s = f"[客]{r['away'][:12]}"
            src_cn = {"team_stats": "队伍统计", "wc_model": "WC模型",
                      "fotmob_team_stats": "FotMob统计"}.get(r["src"], r["src"])
            print(f"  {bj_s:<14}{lg:<18}{h_s:<17}{a_s:<17}"
                  f"{'角球':<6}{r['dir_label']:<12}{r['odds']:>6.2f}"
                  f"{r['p_fusion']:>7.3f}{r['kelly']:>7.4f}{r['hit_score']:>8.3f}  {src_cn}")
        print("  " + "-" * 107)
        print(f"  共推荐 {len(recs)} 注角球 | 前15注已列出 | μ=预测均角 | EV门槛={CORNER_EV_THRESHOLD*100:.0f}%")
        print(SEP)
        print()

    # ── 6. 保存推荐到 corner_recommendations 表（仅validated=True时持久化，
    #    见函数docstring 2026-09-06修复说明）──────────────────────────────
    if recs and validated:
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS corner_recommendations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        fetch_date TEXT,
                        league_name TEXT,
                        home_team TEXT,
                        away_team TEXT,
                        kickoff_utc TEXT,
                        market TEXT DEFAULT 'corner_total',
                        direction TEXT,
                        line REAL,
                        odds REAL,
                        p_model REAL,
                        p_fusion REAL,
                        edge REAL,
                        kelly REAL,
                        hit_score REAL,
                        mu_predicted REAL,
                        src TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(fetch_date, league_name, home_team, away_team, direction, line)
                    )
                """))
                for r in recs:
                    conn.execute(text("""
                        INSERT OR REPLACE INTO corner_recommendations
                        (fetch_date, league_name, home_team, away_team, kickoff_utc,
                         direction, line, odds, p_model, p_fusion, edge, kelly,
                         hit_score, mu_predicted, src)
                        VALUES (:fd, :lg, :h, :a, :kick, :dir, :line, :odds,
                                :pm, :pf, :edge, :k, :hs, :mu, :src)
                    """), {
                        "fd": fetch_date, "lg": r["league"],
                        "h": r["home"], "a": r["away"], "kick": r["kickoff_utc"],
                        "dir": r["direction"], "line": r["line"], "odds": r["odds"],
                        "pm": r["p_model"], "pf": r["p_fusion"],
                        "edge": r["edge"], "k": r["kelly"],
                        "hs": r["hit_score"], "mu": r["mu"], "src": r["src"],
                    })
            log.info(f"  角球推荐已保存 {len(recs)} 条 → corner_recommendations")
        except Exception as e:
            log.warning(f"  角球推荐保存失败: {e}")
    elif recs and not validated:
        log.info(f"  角球候选 {len(recs)} 条（尚未转正，不写入corner_recommendations，仅供观察）")

    return recs


# ── 快速测试 ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tests = [
        ("Arsenal",    "Chelsea",     "E0", "Premier League"),
        ("Barcelona",  "Real Madrid", "SP1", "La Liga"),
        ("Inter",      "AC Milan",    "I1", "Serie A"),
        ("Feyenoord",  "Ajax",        "N1", "Eredivisie"),
    ]
    print(f"\n{'联赛':<6} {'主队':<15} vs {'客队':<15} "
          f"{'预期主':<8} {'预期客':<8} {'预期总':<8} "
          f"{'过8.5校准':>7} {'过9.5校准':>7} {'过10.5校准':>7}")
    print("-" * 90)
    for home, away, lc, ln in tests:
        r = predict_corners(home, away, lc, ln)
        if r:
            cal_info = [f"{r['calibration_info'][f'line_{l}']['bias']:+.1%}"
                       for l in [8.5, 9.5, 10.5]]
            print(f"{lc:<6} {home:<15} vs {away:<15} "
                  f"{r['exp_home']:<8.2f} {r['exp_away']:<8.2f} {r['exp_total']:<8.2f} "
                  f"{r['over_8_5']:>7.3f} {r['over_9_5']:>7.3f} {r['over_10_5']:>7.3f}")
            print(f"      校准偏差(8.5/9.5/10.5): {cal_info}  "
                  f"球队数据: {'✅' if r['used_team_data'] else '❌'}")
        else:
            print(f"{lc:<6} {home:<15} vs {away:<15}  (无数据)")
