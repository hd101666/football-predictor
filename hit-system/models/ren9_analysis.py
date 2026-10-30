#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任九/胜负彩 通用分析脚本（赔率方法论 + 模型分歧提示 + 投注单）
=====================================================================
来源：土豆(OpenClaw) qqsj/ren9_analysis.py v2，2026-08-17 从
E:\\potato_skills_backup 审查后适配落地本项目。原版依赖土豆自己那台机器上
run_today_prediction.py 的 _norm_team_key/_resolve_elo 两个辅助函数，
本项目版 run_today_prediction.py 没有这两个函数、poisson_prediction() 也
没有 home_elo/away_elo 参数（两边的 run_today_prediction.py 已经分叉），
改用：
  - 队名归一化 → 复用 00_命中系统.py 里的 _normalize_team()（原样抄入，
    纯函数无依赖）
  - ELO → 新写 _club_elo() 查 club_elo 表（clubelo.com 源，688队），
    只作为模型分歧提示的辅助校验信号（若 club_elo 方向跟泊松方向矛盾，
    降低"模型分歧"提示的置信度，不反过来影响三条硬纪律选号本身）
  - 选号逻辑（三条硬纪律）完全不依赖模型，见 RULES_任九胜负彩选号方法论.md，
    model_predict() 只用于文末"模型分歧提示"这一行 FYI 标注，不参与选号

用法:
  python ren9_analysis.py --period 26107            # 指定期号
  python ren9_analysis.py --period 26107 --no-push  # 只打印不推送（本项目
                                                        环境无飞书凭证，
                                                        --no-push 与默认
                                                        行为一致）

输出: 十四场(14场全选,64元=5双选9单选) + 任九(选9场,64元=5双选4单选)
"""
import sys, os, re, json, sqlite3, argparse
from datetime import datetime
from difflib import SequenceMatcher
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = r"D:\cl\qqsj"
sys.path.insert(0, BASE)
DB = os.path.join(BASE, "data", "sports_data.db")

# run_today_prediction.py 的历史死import已移除（FIX-005，2026-09-13）：
# grep实证本文件从未有任何 R.xxx 调用，该文件已归档 _archive/。
from team_mapping import TEAM_CN_TO_EN as _TEAM_MAPPING_CN2EN
from poisson_model_v2 import compute_advanced_poisson

# 2026-09-06：model_predict()的模型信号源从run_today_prediction.py的
# poisson_prediction()换成poisson_model_v2.py的compute_advanced_poisson()——
# 真实历史回测(1828场)发现前者即使修复三处真实bug(LSTM/Transformer相对强弱、
# GNN/RL/多模态死权重、主客场攻防率分离、真实联赛场均)后，favorite命中率也
# 只有41.6%，还跑不赢"永远猜主胜"这个零技术含量基线(43.8%)；而
# compute_advanced_poisson()是本项目全系统P_poisson主信号，同样1828场量级
# 真实回测favorite命中率53-56%，直接换成已验证好用的引擎，不再继续修一个
# 追不上基线的旧函数。compute_advanced_poisson()要英文"国家 - 联赛"格式的
# league_name，任九/十四场数据源(okooo_ren9_matches)用的是中文联赛简称，
# 这里补一张任九候选池实际出现过的联赛映射表(不是通用翻译器，只覆盖这个
# 数据源见过的29个联赛)。
_REN9_LEAGUE_MAP = {
    "英超": "England - Premier League", "英冠": "England - Championship",
    "德甲": "Germany - Bundesliga", "德乙": "Germany - Bundesliga 2",
    "意甲": "Italy - Serie A", "意大利杯": "Italy - Cup",
    "西甲": "Spain - La Liga",
    "法甲": "France - Ligue 1", "法乙": "France - Ligue 2",
    "荷甲": "Netherlands - Eredivisie", "荷乙": "Netherlands - Eerste Divisie",
    "葡超": "Portugal - Primeira Liga",
    "挪超": "Norway - Eliteserien",
    "瑞超": "Sweden - Allsvenskan", "瑞典超": "Sweden - Allsvenskan",
    "芬超": "Finland - Veikkausliiga",
    "巴甲": "Brazil - Serie A", "巴西甲": "Brazil - Serie A", "巴西杯": "Brazil - Cup",
    "美职": "USA - Major League Soccer",
    "欧冠": "UEFA - Champions League",
    "欧罗巴": "UEFA - Europa League", "欧联": "UEFA - Europa League",
    "欧超杯": "UEFA - Super Cup",
    "世界杯": "FIFA - World Cup",
    "英联赛杯": "England - EFL Cup", "英联杯": "England - EFL Cup",
    "英社区盾": "England - Community Shield",
    "德超杯": "Germany - Super Cup",
}

# 小规模补充映射：team_mapping.py 覆盖的是国家队/NBA/J联赛，任九/十四场
# 常见的欧洲低级别联赛（法乙/荷乙/挪超/瑞超等）球队名不在里面，靠这张表
# 逐期积累补充（原样保留土豆版已验证的条目）
CN2EN = {
    "狼队": "Wolverhampton", "布莱克": "Blackburn", "不伦瑞": "Braunschweig", "波鸿": "Bochum",
    "基尔": "Holstein", "圣保利": "St Pauli", "阿纳西": "Annecy", "罗德兹": "Rodez",
    "南锡": "Nancy", "蒙彼利": "Montpellier", "第戎": "Dijon", "波城F": "Pau", "波城": "Pau",
    "格勒诺": "Grenoble", "梅斯": "Metz", "甘冈": "Guingamp", "布洛涅": "Boulogne",
    "兰斯": "Reims", "敦刻克": "Dunkerque", "埃蒂安": "Saint-Etienne", "克莱蒙": "Clermont",
    "特尔斯": "Telstar", "鹿特丹": "Sparta Rotterdam", "里斯本": "Sporting", "吉马良": "Vitoria Guimaraes",
    "埃尔夫": "Elfsborg", "韦斯罗": "Vasteras", "罗森博": "Rosenborg", "维京": "Viking",
    # FIX-009-4（2026-09-14）补充：okooo短名精确映射（Pinnacle比对臂队名匹配
    # 实测覆盖率仅2/14后补；全部精确一对一，不引入模糊。顺带提高model_predict
    # 的模型信号覆盖率——这些短名此前查不到数据静默走兜底）
    "曼联": "Manchester United", "曼城": "Manchester City", "国米": "Inter",
    "乌迪内": "Udinese", "尤文": "Juventus", "巴萨": "Barcelona", "拜仁": "Bayern Munich",
    "莱比锡": "RB Leipzig", "那不勒": "Napoli", "博洛尼": "Bologna",
    "社会": "Real Sociedad", "马竞技": "Atletico Madrid", "布雷斯": "Brest",
    "日尔曼": "Paris Saint-Germain", "特鲁瓦": "Troyes", "圣克拉": "Santa Clara",
    "法马利": "Famalicao", "艾华斯": "Elversberg", "拉科鲁": "Deportivo La Coruna",
    "利兹": "Leeds United", "纽卡斯": "Newcastle United", "比利亚": "Villarreal",
    "贝蒂斯": "Real Betis", "圣红星": "Red Star", "里奥阿": "Rio Ave",
    "阿马多": "Estrela Amadora", "摩雷伦": "Moreirense", "马里迪": "Maritimo",
    "埃斯托": "Estoril", "代格福": "Degerfors", "佐加顿": "Djurgarden",
    "盖斯": "GAIS", "博德": "Bodo/Glimt", "桑纳菲": "Sandefjord",
    # FIX-017a（2026-09-15）补充：26126期14场映射失败清单逐条补——全部先查
    # theodds_fixtures 当日实际存储英文名再填（防再错）：利胜利/利新月在库里
    # 是连字符形 "Al-Nassr"/"Al-Hilal"，阿拉维是ASCII形 "Alaves"（非Alavés）。
    # 阿贾克错指向匈牙利ajka的词条在 team_mapping.py 源头修复（'ajax'/'ajka'
    # 两行），不在此重复。
    "国安": "Beijing Guoan", "浦项": "Pohang Steelers", "柔佛": "Johor Darul Ta'zim",
    "布里兰": "Buriram United", "艾因": "Al Ain", "利胜利": "Al-Nassr",
    "利新月": "Al-Hilal", "加拉法": "Al Gharafa", "伊普斯": "Ipswich Town",
    "热刺": "Tottenham Hotspur", "巴列卡": "Rayo Vallecano", "西班人": "Espanyol",
    "阿拉维": "Alaves", "巴伦西": "Valencia", "皇马": "Real Madrid",
    "阿贾克": "Ajax", "威廉": "Willem II", "普拉滕": "Platense",
    "弗鲁米": "Fluminense", "米德尔": "Middlesbrough", "米尔沃": "Millwall",
    "林肯城": "Lincoln City", "布里斯": "Bristol City",
    # ALIAS-26127（2026-09-16）补充：26127期13场未映射清单——全部先查
    # theodds_fixtures 2026-09-16 实际存储名再填（沿用FIX-017a做法）。
    # manual_queue（不硬配）：中国亚/朝鲜亚——Pinnacle按senior名存
    # "China"/"North Korea"（league=Asian Games U23区分），年龄段国家队
    # 属"女子队抢投票"同族歧义，留人工裁决，不入表。
    "奥莫尼": "Omonia Nicosia", "AC米": "AC Milan", "安德莱": "Anderlecht",
    "勒沃": "Bayer Leverkusen", "采列": "Celje", "奥林匹": "Olympiakos",
    "比亚韦": "Jagiellonia Bialystok", "格拉茨": "Sturm Graz",
    "桑德兰": "Sunderland", "阿尔克": "AZ Alkmaar", "维拉": "Aston Villa",
    "奥萨苏": "Osasuna", "塞维利": "Sevilla", "桑坦德": "Racing Santander",
    "毕尔巴": "Athletic Bilbao",
    # 注：莱万特 的脏词条'levante (bookings)'已在 team_mapping.py 源头隔离
    # （反向表过滤 ' (' 形态key + EXTRA 补净身'levante'），不在此重复。
}


import math

N_SINGLE, N_DOUBLE = 4, 5  # 任九64元复式 = 4单选+5双选+5跳过


def _devig(ho, dr, ao):
    """去水隐含概率：1/赔率归一化去掉庄家抽水"""
    ih, idr, ia = 1.0 / ho, 1.0 / dr, 1.0 / ao
    tot = ih + idr + ia
    return ih / tot, idr / tot, ia / tot


def _ren9_dp_optimal(entries, n_single=N_SINGLE, n_double=N_DOUBLE):
    """选场+单双选精确DP（2026-08-17新增，见 _backtest_ren9_dp_optimal_0817.py）。
    排序后硬切固定名额是启发式，这个DP是精确全局最优解：给定候选场次每场
    "单选成功概率"(去水后最高概率)和"双选成功概率"(去水后前两高概率之和)，在
    "恰好n_single个单选+n_double个双选(其余跳过)"约束下最大化P(全中)=各场概率
    连乘积（取log转成可DP的加法问题）。
    任九(默认n_single=4,n_double=5,可跳5场)：112280组伪期次回测5.72% vs v3
    启发式5.38%，+0.33pp/3.47倍标准误(统计显著)，相对+6.2%；939个真实官方
    期次交叉验证方向一致。
    十四场(n_single=9,n_double=5,14场全押无跳过，见下方调用处)：224560组
    伪期次回测0.1438% vs v2画像启发式0.1131%，+2.87倍标准误(统计显著)，
    相对+27.1%，比任九更明显(没有跳场自由度，全靠双选分配精确度)。
    两个场景都已替换启发式成为生产逻辑。返回 (single索引list, double索引list)。"""
    n = len(entries)
    log_s = [math.log(max(e["single_val"], 1e-12)) for e in entries]
    log_d = [math.log(max(e["double_val"], 1e-12)) for e in entries]

    NEG = float("-inf")
    dp = [[[NEG] * (n_double + 1) for _ in range(n_single + 1)] for _ in range(n + 1)]
    dp[0][0][0] = 0.0
    choice = [[[None] * (n_double + 1) for _ in range(n_single + 1)] for _ in range(n + 1)]

    for i in range(1, n + 1):
        for s in range(n_single + 1):
            for d in range(n_double + 1):
                best, best_c = dp[i-1][s][d], "skip"
                if s > 0 and dp[i-1][s-1][d] > NEG:
                    v = dp[i-1][s-1][d] + log_s[i-1]
                    if v > best:
                        best, best_c = v, "single"
                if d > 0 and dp[i-1][s][d-1] > NEG:
                    v = dp[i-1][s][d-1] + log_d[i-1]
                    if v > best:
                        best, best_c = v, "double"
                dp[i][s][d] = best
                choice[i][s][d] = best_c

    s, d = n_single, n_double
    singles, doubles = [], []
    for i in range(n, 0, -1):
        c = choice[i][s][d]
        if c == "single":
            singles.append(i - 1); s -= 1
        elif c == "double":
            doubles.append(i - 1); d -= 1
    return singles, doubles


def _normalize_team(name: str) -> str:
    """队名标准化：去标点、转小写、移除常见后缀（原样抄自 00_命中系统.py）"""
    name = name.lower().strip()
    name = re.sub(r"['\-\.\(\)&,]", " ", name)
    name = re.sub(r"\b(fc|cf|sc|ac|afc|bfc|united|city|town|sporting|club|de|del|el|la|le|les|'s)\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


from config import TEAM_CN_MAP as _TEAM_CN_MAP
_TEAM_CN_MAP_REV: dict = {}
for _en_k, _cn_v in _TEAM_CN_MAP.items():
    _TEAM_CN_MAP_REV.setdefault(_cn_v, _en_k)


def cn_to_en(cn: str) -> str:
    """中文队名 → 英文：先查 team_mapping（国家队/主流俱乐部），
    再查本文件顶部的 CN2EN 补充表，再查config.py的TEAM_CN_MAP反查(该表原本是
    英文->中文给00_命中系统.py展示用，2026-09-06新增反向查找复用)。

    2026-09-06发现的真实bug：team_mapping.team_en()覆盖的是"国家队/NBA/J联赛"
    (见上面注释)，压根不包含欧洲俱乐部——这意味着此前"曼城"/"拜仁"/"国米"这类
    任九候选池里绝大多数欧洲俱乐部队名，cn_to_en()从来没有真正翻译成功过，
    一直原样返回中文，导致后续不管是旧的_match()模糊匹配(against英文键的
    统计字典)还是新的compute_advanced_poisson()(直接拿队名去查DB)，全部
    静默查不到数据、拿的是默认兜底值——这比任何公式层面的bug影响都大，是
    ren9模型信号长期缺乏真实球队级支撑的根本原因。TEAM_CN_MAP存的是全名
    ("曼彻斯特城"/"拜仁慕尼黑")，任九数据源(okooo)用简称("曼城"/"拜仁")，
    先精确查反查表补一批。

    子串模糊匹配已经试过又撤掉了：实测"亚特兰"(亚特兰大竞技，意甲球队的okooo
    简称)会被子串匹配成"亚特兰大老鹰"(NBA球队，TEAM_CN_MAP里同样含"亚特兰"
    前缀)——完全不同的运动、错误的球队，比"查不到、用默认兜底值"更危险(会把
    错误球队的真实数据当成这场比赛的信号)，就是项目记忆
    feedback_team_name_collision.md警告过的同一类"队名前缀匹配撞车"。查不到
    就原样返回中文(compute_advanced_poisson()会正确识别成"无此球队"返回
    probs=None，不会静默用错数据)，覆盖率会打折扣，但不会引入更隐蔽的错误。

    2026-09-06第二次发现：原来这里调用的team_mapping.team_en()自己内部也带一个
    无视运动类别的全局SequenceMatcher模糊回退(阈值0.7)——实测"多伦多"(美职,
    Toronto FC)被它匹配成"toronto raptors"(NBA)，"波特兰"匹配成"poland"
    (国家队)，"巴伦西"(西甲,Valencia)匹配成"brazil"，全是同一类跨运动/跨类别
    撞车，而且比子串匹配更隐蔽(相似度打分，肉眼看不出规律)。ren9数据源只有
    足球，改成只查team_mapping.py的原始精确字典TEAM_CN_TO_EN，不再触发它的
    模糊回退——team_mapping.py本身服务于全项目(NBA/国家队/J联赛都要用)，这个
    模糊回退的风险不是本次任务范围内能一并评估修掉的，只在ren9这条独立调用
    链路上绕开，不改team_mapping.py本体。"""
    en = _TEAM_MAPPING_CN2EN.get(cn.strip()) if cn else None
    if en and en != cn:
        return en
    if cn in CN2EN:
        return CN2EN[cn]
    if cn in _TEAM_CN_MAP_REV:
        return _TEAM_CN_MAP_REV[cn]
    return cn


_COUNTRY_TEAM_CACHE: dict = {}  # country slug -> {归一化英文名: match_results真实队名}


def _loose_en_norm(name: str) -> str:
    """轻量英文队名归一化：只统一大小写/标点/utd缩写，刻意不剥离
    city/united/town这类球队身份词——跟_normalize_team()不是同一份实现，
    那份是给旧_match()用的宽松匹配。这里更保守是因为如果剥掉这些词，
    "Manchester City"和"Manchester Utd"会撞成同一个key(都变成"manchester")，
    在同一国家候选池内自己人打自己人，比对外部大池子模糊匹配更隐蔽危险。"""
    name = (name or "").lower().strip()
    name = re.sub(r"[^a-z0-9]+", " ", name)
    name = re.sub(r"\butd\b", "united", name)
    return re.sub(r"\s+", " ", name).strip()


def _country_team_names(conn, country: str) -> dict:
    """match_results里某国家全部真实英文队名，按_loose_en_norm()建索引，
    用于给cn_to_en_scoped()的联赛限定模糊匹配划定安全候选范围——只在同一
    国家的球队之间做子串/缩写匹配，跨国家/跨运动撞车在结构上不可能发生
    (feedback_team_name_collision历史教训)。归一化后撞出歧义的key直接丢弃
    (如两支队伍归一化后共用一个key)，不冒险二选一，参照
    poisson_model_v2.py _resolve_team_db_name()同样的处理方式。"""
    if country in _COUNTRY_TEAM_CACHE:
        return _COUNTRY_TEAM_CACHE[country]
    cur = conn.cursor()
    rows = cur.execute("""
        SELECT DISTINCT home_team AS t FROM match_results
        WHERE sport='football' AND country=? AND home_team IS NOT NULL
        UNION
        SELECT DISTINCT away_team AS t FROM match_results
        WHERE sport='football' AND country=? AND away_team IS NOT NULL
    """, (country, country)).fetchall()
    idx: dict = {}
    ambiguous = set()
    for (n,) in rows:
        if not n:
            continue
        nk = _loose_en_norm(n)
        if nk in idx and idx[nk] != n:
            ambiguous.add(nk)
            continue
        idx[nk] = n
    for nk in ambiguous:
        idx.pop(nk, None)
    _COUNTRY_TEAM_CACHE[country] = idx
    return idx


def _league_name_to_country(league_name: str) -> str:
    """复用poisson_model_v2.py compute_advanced_poisson()同一套联赛名->国家
    解析逻辑(裸联赛别名表+"国家 - 联赛"naive拆分)，只取country部分，用于给
    cn_to_en_scoped()圈定候选范围。两边算法必须保持一致，否则圈错国家、
    候选池跟真正_get_team_stats()查询用的country对不上，"安全"就是假象。"""
    from poisson_model_v2 import _BARE_LEAGUE_ALIASES
    alias = _BARE_LEAGUE_ALIASES.get((league_name or "").strip().lower())
    if alias:
        return alias[0]
    parts = league_name.split(" - ") if " - " in league_name else [league_name, ""]
    return parts[0].strip().lower().replace(" ", "-")


def _cn_abbrev_match(cn: str, cn_full: str) -> bool:
    """中文队名缩写匹配，处理两种常见模式：
    ①连续子串（如"拜仁"是"拜仁慕尼黑"的前缀，"热刺"是"托特纳姆热刺"的后缀）
    ②首尾字保留、中间省略（如"曼城"="曼[彻斯特]城"、"曼联"="曼[彻斯特]联"——
    欧洲球队中文译名最常见的缩写方式，音译地名中间部分被省略，只留第一个字
    +球队类型/末字，不是连续子串，普通in判断抓不到）。要求cn恰好2个字且
    严格短于cn_full，避免长名字之间误判——这条规则单独看仍有偶然撞车风险
    (同国家内两支队伍恰好首尾字相同)，靠调用方_country_team_names()把候选池
    收窄到几十支队+要求最终候选唯一来兜底，不是这条规则自己保证安全。"""
    if not cn or not cn_full or cn == cn_full:
        return False
    if cn in cn_full or cn_full in cn:
        return True
    if len(cn) == 2 and len(cn_full) > len(cn):
        return cn[0] == cn_full[0] and cn[-1] == cn_full[-1]
    return False


def cn_to_en_scoped(cn: str, league_name: str, conn) -> str:
    """2026-09-06新增：cn_to_en()精确匹配失败后的补充信号源。用league_name
    圈定的"国家候选池"(该国家在match_results里出现过的全部真实英文队名，通常
    几十支)做安全模糊匹配，取代此前撤掉的"对全局217条跨运动TEAM_CN_MAP做
    子串匹配"版本(见cn_to_en()文档字符串"亚特兰"撞车的教训，那个版本还有
    第二个问题：命中第一个候选就返回，没做唯一性校验)。

    这里的候选范围只收窄到"跟这场比赛同一个国家"的球队，跨国家/跨运动撞车
    在结构上不可能发生；唯一剩下的风险是同国家内部真的撞车(如"曼城"vs"曼联"
    如果两者恰好首尾字相同)，靠_country_team_names()对候选池做过归一化去重、
    再加这里"最终候选必须唯一"双重把关。查不到/有歧义都原样返回中文
    (compute_advanced_poisson()会识别成"无此球队"返回probs=None，不会静默
    用错数据)——覆盖率会打折扣，但不会引入更隐蔽的错误。"""
    exact = cn_to_en(cn)
    if exact != cn:
        return exact
    if not league_name or conn is None:
        return cn
    country = _league_name_to_country(league_name)
    if not country:
        return cn
    pool = _country_team_names(conn, country)
    if not pool:
        return cn
    candidates = set()
    for en_full, cn_full in _TEAM_CN_MAP.items():
        if not _cn_abbrev_match(cn, cn_full):
            continue
        nk = _loose_en_norm(en_full)
        if nk in pool:
            candidates.add(pool[nk])
            continue
        for pk, pv in pool.items():
            if nk and pk and (nk in pk or pk in nk):
                candidates.add(pv)
    if len(candidates) == 1:
        return candidates.pop()
    return cn


def _club_elo(conn, team_en: str):
    """查 club_elo 表（clubelo.com 源，688支俱乐部，2026-09起停更——现为
    _elo_pair() 的降级兜底源，主源是自建 fd_elo_ratings，见 FIX-008-2）。
    精确匹配优先，模糊匹配时用字符串相似度消歧，避免短子串误命中另一支球队
    （沿用 00_命中系统.py get_national_team_probs()._elo() 的处理方式）"""
    if not team_en:
        return None
    cur = conn.cursor()
    row = cur.execute("""
        SELECT elo_rating FROM club_elo
        WHERE LOWER(team_name) = LOWER(?) ORDER BY fetch_date DESC LIMIT 1
    """, (team_en,)).fetchone()
    if row:
        return float(row[0])
    for chars in (8, 6, 5):
        if len(team_en) < chars:
            continue
        rows = cur.execute("""
            SELECT team_name, elo_rating, fetch_date FROM club_elo
            WHERE LOWER(team_name) LIKE LOWER(?)
        """, (f"%{team_en[:chars]}%",)).fetchall()
        if not rows:
            continue
        distinct = {r[0] for r in rows}
        if len(distinct) > 1:
            best = max(distinct, key=lambda t: SequenceMatcher(None, t.lower(), team_en.lower()).ratio())
            rows = [r for r in rows if r[0] == best]
        row = max(rows, key=lambda r: r[2])
        if row:
            return float(row[1])
    return None


def _fd_elo(conn, team_en: str):
    """查自建 fd_elo_ratings（FIX-008-2：fd_matches 287776行滚动Elo，
    k=32/主场+60/初始1500，与 predict_football._build_elo 同参数，
    elo_fd_selfbuilt.py --rebuild 重建）。只做大小写不敏感精确匹配，
    不做模糊回退（错队比无信号危害大，同 _model_team_en 原则）。"""
    if not team_en:
        return None
    row = conn.execute(
        "SELECT elo FROM fd_elo_ratings WHERE LOWER(team) = LOWER(?) LIMIT 1",
        (team_en,)).fetchone()
    return float(row[0]) if row else None


def _elo_pair(conn, h_en, a_en):
    """FIX-008-2：主/客队ELO必须来自同一源同一刻度——自建 fd_elo 优先
    （clubelo.com 外部源 2026-09 起停更），任一缺失才整对降级 club_elo，
    绝不混用两个刻度（实测两源均值差+145，混用等于白给一方加145分）。
    返回 (home_elo, away_elo, home_adv)，home_adv 跟随源口径。"""
    he, ae = _fd_elo(conn, h_en), _fd_elo(conn, a_en)
    if he is not None and ae is not None:
        return he, ae, 60   # fd自建：与 _build_elo 的 ELO_HOME 一致
    he, ae = _club_elo(conn, h_en), _club_elo(conn, a_en)
    if he is not None and ae is not None:
        return he, ae, 65   # clubelo 惯用主场经验值
    return None, None, None


def _load_injury_cache(conn, fetch_dates):
    """加载okooo_injuries(40_okooo_injury_scraper.py写入)缺阵球员本赛季累计
    出场分钟数，按中文队名汇总。2026-08-31新增——伤停信号已在00_命中系统.py的
    get_injury_impact_probs()验证过计算逻辑(只是仍在影子观察单阶段，未过真实
    结算显著性门槛)，这里复用同一套"缺阵分钟数差=伤病严重程度差"的思路，但不
    是直接import主系统那个函数(00_命中系统.py是入口脚本不是库，import会触发
    模块级大量初始化代码，风险高)，改成在本文件里按需重写一份精简版，只做
    _club_elo()同类型的"模型分歧交叉校验"用途，不参与三条硬纪律选号本身。
    okooo_injuries队名格式跟okooo_ren9_matches同源(都是okooo.com中文缩写队名，
    如"亚特兰大"/"奥萨苏纳")，直接子串匹配，不需要cn_to_en()转英文。"""
    cur = conn.cursor()
    placeholders = ",".join("?" for _ in fetch_dates)
    rows = cur.execute(f"""
        SELECT team, minutes FROM okooo_injuries
        WHERE will_miss='是' AND fetch_date IN ({placeholders})
    """, fetch_dates).fetchall()
    cache: dict[str, int] = {}
    for team, mins in rows:
        if not team:
            continue
        try:
            m = int(mins) if mins else 0
        except (TypeError, ValueError):
            m = 0
        cache[team] = cache.get(team, 0) + m
    return cache


def _injury_direction(injury_cache: dict, hc: str, ac: str):
    """按中文队名匹配injury_cache，返回伤停信号方向或None。跟_club_elo()同一个
    道理：只作模型分歧的交叉校验，不参与选号。精确匹配优先，子串匹配只在唯一
    命中时采用(避免队名前缀撞车，如"马竞"误配到别的"马"字头球队——这个项目
    2026-08已经踩过一次队名前缀匹配撞车的真实bug，见项目记忆
    feedback_team_name_collision)。赛季初期大多数球员缺阵分钟数本身就是0，
    经常给不出方向是数据本身如此(样本量小)，不是这段代码的bug。"""
    def _lookup(name):
        if not name:
            return None
        if name in injury_cache:
            return injury_cache[name]
        matches = [v for k, v in injury_cache.items() if name in k or k in name]
        return matches[0] if len(matches) == 1 else None
    h_miss, a_miss = _lookup(hc), _lookup(ac)
    if h_miss is None and a_miss is None:
        return None
    h_miss, a_miss = h_miss or 0, a_miss or 0
    diff = a_miss - h_miss  # 正数：客队伤缺更严重(伤停球员更重要)，利好主队
    if abs(diff) < 200:  # 差距太小时不给方向，避免赛季初期小样本噪音（阈值参照
        return None       # get_injury_impact_probs()的3000分钟量级经验尺度取一个零头）
    return "主胜" if diff > 0 else "客胜"


def model_predict(conn, hc, ac, lg=""):
    """返回 (泊松方向或None, ph, pd, pa, elo_direction_or_None)。
    elo_direction 仅用于给泊松的"模型分歧"提示做交叉校验，不参与选号。

    2026-09-06：模型信号源从run_today_prediction.py的poisson_prediction()换成
    poisson_model_v2.py的compute_advanced_poisson()——即使修复三处真实bug后，
    前者1828场真实回测favorite命中率也只有41.6%，跑不赢"永远猜主胜"基线
    (43.8%)；后者是本项目全系统P_poisson主信号，同等量级回测命中率53-56%，
    直接换成已验证好用的引擎。lg是任九数据源(okooo_ren9_matches)的中文联赛
    简称，通过_REN9_LEAGUE_MAP转成compute_advanced_poisson()要的英文"国家 -
    联赛"格式；球队样本不足时该函数返回probs=None(不伪造信号)，这里同样原样
    返回model_dir=None，调用方按"没有模型信号"处理，不能当成"模型跟市场分歧"。"""
    league_name = _REN9_LEAGUE_MAP.get(lg, "")
    h_en = cn_to_en_scoped(hc, league_name, conn)
    a_en = cn_to_en_scoped(ac, league_name, conn)
    r = compute_advanced_poisson(h_en, a_en, league_name)
    probs = r.get("probs")
    if probs is None:
        ph = pd_ = pa = None
        model_dir = None
    else:
        ph, pd_, pa = probs["1x2"]["home"], probs["1x2"]["draw"], probs["1x2"]["away"]
        model_dir = max([("主胜", ph), ("平局", pd_), ("客胜", pa)], key=lambda x: x[1])[0]

    elo_dir = None
    he, ae, _elo_home_adv = _elo_pair(conn, h_en, a_en)
    if he is not None and ae is not None:
        diff = (he + _elo_home_adv) - ae   # 主场优势随源口径（fd自建60/clubelo65）
        if abs(diff) >= 40:     # 差距太小时不给方向，避免噪音
            elo_dir = "主胜" if diff > 0 else "客胜"

    return model_dir, ph, pd_, pa, elo_dir


# ===== FIX-001b（2026-09-12）：投注单"销售截止时间"必须来自官方源 =====
# 规则：出单时实时抓取官方销售截止时间并打印来源+抓取时间；抓不到就印
# "截止时间未核实 请以官方为准"，禁止输出任何假设的默认截止时间。
# 官方源实测情况（2026-09-12 取证）：
#   ① trade.500.com/sfc/ 购买页 span.zcfilter-endtime 字段
#      "官方售彩截止时间：MM-DD HH:MM"（500彩票网官方售彩渠道标注的官方截止
#      字段），但该页只展示"当前在售期"的截止时间——历史期的销售截止不再展示
#      （?expect=<期号> 切到已停售期后该元素消失）。
#   ② kaijiang.500.com 开奖公告页只有"开奖日期/兑奖截止日期"，没有销售截止字段。
#   ③ sporttery.cn（体彩官网）整域名 WAF 拦截，本环境 IP 层不可达（见既有调研记录）。
#   ④ 交叉校验源 m.okooo.com/zucai/ren9.php 的 p.listtoptxt "停售MM-DD HH:MM"
#      支持任意期号（含历史期），2026-09-12 实测当期值与500.com完全一致
#      （26124期两边都是 09-13 20:30），作为兜底源使用时标注"非官方"。
# 返回 {'deadline': 'MM-DD HH:MM', 'source': 来源描述, 'fetch_ts': 抓取时间戳}
# 或 None（全部源失败/期号不匹配）。deadline 原样保留源页面字符串，不补年份
# （源页面本身没标年份，补上就是假设值，违反本规则本意）。
_WWW_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
}
_MOBILE_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"),
    "Referer": "https://m.okooo.com/",
}


def _fetch_sale_deadline_500(period: str):
    """源①：trade.500.com 购买页的"官方售彩截止时间"（仅当前在售期可取到）。"""
    import requests
    from bs4 import BeautifulSoup
    from datetime import datetime as _dt
    r = requests.get("https://trade.500.com/sfc/", headers=_WWW_HEADERS, timeout=15)
    r.encoding = r.apparent_encoding
    soup = BeautifulSoup(r.text, "html.parser")
    cur = soup.select_one("li.on a[data-expect]")
    if not cur or cur["data-expect"] != str(period):
        return None  # 目标期不是当前在售期，500.com不再展示其截止时间
    et = soup.select_one("span.zcfilter-endtime")
    if not et:
        return None
    m = re.search(r"官方售彩截止时间[：:]\s*(\d{2}-\d{2}\s+\d{2}:\d{2})", et.get_text())
    if not m:
        return None
    return {"deadline": m.group(1).strip(),
            "source": "500.com官方售彩截止时间 trade.500.com/sfc/",
            "fetch_ts": _dt.now().strftime("%Y-%m-%d %H:%M:%S")}


def _fetch_sale_deadline_okooo(period: str):
    """源②（兜底，非官方）：okooo 任九页"停售MM-DD HH:MM"，支持任意期号。"""
    import requests
    from bs4 import BeautifulSoup
    from datetime import datetime as _dt
    r = requests.get("https://m.okooo.com/zucai/ren9.php", params={"LotteryNo": str(period)},
                     headers=_MOBILE_HEADERS, timeout=20)
    r.encoding = "gbk"
    soup = BeautifulSoup(r.text, "html.parser")
    qh = soup.select_one("p.qihaobox")
    if not qh or f"第{period}期" not in qh.get_text():
        return None  # 期号对不上，不能拿别的期的截止时间冒充
    # 页面上可能有多个 p.listtoptxt（历史期为空白占位），不能select_one取第一个，
    # 直接找含"停售"的文本节点（2026-09-12实测26123期就是这种情况）
    el = soup.find(string=re.compile(r"停售"))
    if not el:
        return None
    m = re.search(r"停售\s*(\d{2}-\d{2}\s+\d{2}:\d{2})", el)
    if not m:
        return None
    return {"deadline": m.group(1).strip(),
            "source": "澳客网停售时间(非官方,仅交叉校验) m.okooo.com/zucai/ren9.php",
            "fetch_ts": _dt.now().strftime("%Y-%m-%d %H:%M:%S")}


def fetch_sale_deadline(period: str):
    """FIX-001b 统一入口：按优先级尝试各源，返回 dict 或 None。
    抓取失败只打印警告（出单流程不能被网络问题中断），绝不编造默认值。"""
    for name, fn in (("500.com", _fetch_sale_deadline_500),
                     ("okooo(兜底)", _fetch_sale_deadline_okooo)):
        try:
            res = fn(period)
            if res:
                return res
        except Exception as e:
            print(f"  [FIX-001b] 截止时间抓取失败（{name}）: {type(e).__name__}: {e}")
    return None


def run(period, push=True, odds_file=None, save_tag="早场"):
    if odds_file and os.path.exists(odds_file):
        with open(odds_file, encoding='utf-8') as f:
            data = json.load(f)
        rows = [(m.get("seq"), m.get("league", ""), m.get("home", ""), m.get("away", ""),
                 m.get("odds_home"), m.get("odds_draw"), m.get("odds_away")) for m in data]
        print(f"用外部赔率文件: {odds_file}（{len(rows)} 场）")
    else:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        # FIX-009-1（2026-09-14）：取数前先列当期全部快照批次——快照留存修复前
        # 同日重抓会被 ON CONFLICT 覆盖写吞掉（26124期三次抓取无痕迹）。批次来自
        # okooo_ren9_snapshots（每抓一批）；该表尚无当期数据时退回主表的
        # DISTINCT fetch_date 口径。批次数<2说明快照链路疑似失效，显式警告。
        try:
            batches = [r[0] for r in cur.execute(
                "SELECT DISTINCT batch_ts FROM okooo_ren9_snapshots WHERE lottery_no=? "
                "ORDER BY batch_ts", (period,)).fetchall()]
            batch_src = "okooo_ren9_snapshots"
            if not batches:
                batches = [r[0] for r in cur.execute(
                    "SELECT DISTINCT fetch_date FROM okooo_ren9_matches WHERE lottery_no=? "
                    "ORDER BY fetch_date", (period,)).fetchall()]
                batch_src = "okooo_ren9_matches.fetch_date(旧口径)"
        except sqlite3.Error:
            batches = [r[0] for r in cur.execute(
                "SELECT DISTINCT fetch_date FROM okooo_ren9_matches WHERE lottery_no=? "
                "ORDER BY fetch_date", (period,)).fetchall()]
            batch_src = "okooo_ren9_matches.fetch_date(旧口径)"
        print(f"  当期批次({batch_src}): {len(batches)} 个 {batches}")
        if len(batches) < 2:
            print("  ⚠️ 快照功能疑似失效：当期不足2个批次，赔率时序对比不可用")
        # 同一期号可能被多天重复抓取（结算前每天补抓一次赔率快照），不按fetch_date
        # 取最新会导致每个seq出现2条以上重复行，把14场变成28场破坏选号逻辑——
        # 只取每个seq最新fetch_date那一条（关联子查询，按(lottery_no,seq)分组取
        # MAX(fetch_date)，同一天多次抓取以rowid更大的为准）。
        rows = cur.execute("""
            SELECT m.seq, m.league, m.home_team, m.away_team, m.odds_home, m.odds_draw, m.odds_away
            FROM okooo_ren9_matches m
            WHERE m.lottery_no=? AND m.rowid = (
                SELECT m2.rowid FROM okooo_ren9_matches m2
                WHERE m2.lottery_no=m.lottery_no AND m2.seq=m.seq
                ORDER BY m2.fetch_date DESC, m2.rowid DESC LIMIT 1
            )
            ORDER BY CAST(m.seq AS INTEGER)""", (period,)).fetchall()
        conn.close()
    if not rows:
        print(f"无 {period} 期数据")
        return

    conn = sqlite3.connect(DB)

    # 伤停信号(2026-08-31新增)：取okooo_injuries最新一次抓取日期的数据，跟_club_elo()
    # 同一个道理——只作模型分歧的交叉校验信号，不参与三条硬纪律选号本身。见
    # _injury_direction()说明。
    _inj_row = conn.cursor().execute("SELECT MAX(fetch_date) FROM okooo_injuries").fetchone()
    injury_cache = _load_injury_cache(conn, [_inj_row[0]]) if _inj_row and _inj_row[0] else {}

    entries = []
    for seq, lg, hc, ac, ho, dr, ao in rows:
        mdir, ph, pd_, pa, elo_dir = model_predict(conn, hc, ac, lg)
        injury_dir = _injury_direction(injury_cache, hc, ac)
        odds = {"主胜": ho, "平局": dr, "客胜": ao}
        hot, hot_odds = min(odds.items(), key=lambda x: x[1])
        # 三赔率组合画像（78596场回测）：碾压/偏热/势均力敌，看三赔率相对位置
        if ho < 0.6 * min(dr, ao):
            kind = "碾压"; hot = "主胜"; hot_odds = ho
        elif ao < 0.6 * min(ho, dr):
            kind = "碾压"; hot = "客胜"; hot_odds = ao
        elif ho < ao * 0.85:
            kind = "偏热"; hot = "主胜"; hot_odds = ho
        elif ao < ho * 0.85:
            kind = "偏热"; hot = "客胜"; hot_odds = ao
        else:
            kind = "势均"
        # 模型分歧：泊松方向≠市场热门方向，且（无elo数据 或 elo也不支持市场热门方向）
        # 且（无伤停数据 或 伤停信号也不支持市场热门方向）——伤停信号2026-08-31
        # 新增，跟elo同一个道理加多一道交叉校验，降低误报，不参与真正选号
        # 2026-09-06修复：mdir=None(compute_advanced_poisson()球队样本不足,没有
        # 真实模型信号)此前会被"mdir != hot"误判成"模型跟市场分歧"——没有信号
        # 不等于分歧，必须先判mdir确实存在才继续比较，否则会对没数据的比赛也
        # 打出FYI提示，误导性质跟"伪造信号"是一类问题。
        disagree = (mdir is not None and mdir != hot
                    and (elo_dir is None or elo_dir != hot)
                    and (injury_dir is None or injury_dir != hot))
        ph_v, pd_v, pa_v = _devig(ho, dr, ao)
        probs = {"主胜": ph_v, "平局": pd_v, "客胜": pa_v}
        ranked_outcomes = sorted(probs, key=probs.get, reverse=True)
        entries.append(dict(seq=seq, lg=lg, hc=hc, ac=ac, ho=ho, dr=dr, ao=ao,
                            hot=hot, hot_odds=hot_odds, kind=kind,
                            mdir=mdir, elo_dir=elo_dir, injury_dir=injury_dir, disagree=disagree,
                            probs=probs, single_pick=ranked_outcomes[0],
                            single_val=probs[ranked_outcomes[0]],
                            double_pick=set(ranked_outcomes[:2]),
                            double_val=probs[ranked_outcomes[0]] + probs[ranked_outcomes[1]]))
    conn.close()

    crush = [e for e in entries if e["kind"] == "碾压"]
    hot = [e for e in entries if e["kind"] == "偏热"]
    even = [e for e in entries if e["kind"] == "势均"]

    # ===== 硬纪律①（26104 首战教训，2026-08-15 写入；2026-08-17 用本项目
    # jingcai_history_matches 78596场独立回测验证：碾压AND<1.5命中67.9%(n=19804)
    # vs 1.5~1.9借调区52.3%(n=24554)，见 _backtest_ren9_hardrules_verify_0817.py）=====
    # 单选双门槛：画像=碾压 AND 热门赔率<1.5，缺一不可——十四场/任九(下方)现在
    # 都已改用DP精确解选场+分配单双选名额，这条不再直接决定选场，仅用于下方
    # 【提示】行的"达标单选场次"展示和单场[险]标注参考
    single_cand = sorted([e for e in crush if e["hot_odds"] < 1.5], key=lambda x: x["hot_odds"])

    def hot_cn(e):
        return {"主胜": f"{e['hc']}(主)胜", "客胜": f"{e['ac']}(客)胜", "平局": "平局"}[e["hot"]]

    def double_dir(e):
        # ③ 弱热门纪律（78596场回测，2026-08-15）：
        #    弱客热门(2.2<客胜赔率<3.0)：主队掀翻率38.3% > 客队自赢31.8% → 翻「主+平」
        #    弱主热门(2.2<主胜赔率<3.0)：主+平67.0% 仍优于 客+平62.9% → 不翻，但属最差覆盖档，优先避开
        if e["hot"] == "客胜" and 2.2 < e["hot_odds"] < 3.0:
            return f"{e['hc']}(主)胜 + 平局"
        if e["hot"] == "主胜":
            return f"{e['hc']}(主)胜 + 平局"
        if e["hot"] == "客胜":
            return f"{e['ac']}(客)胜 + 平局"
        return "主胜 + 客胜"

    def dbl_tag(e):
        if e["hot"] == "主胜" and 2.2 < e["hot_odds"] < 3.0:
            return " [弱主·最差覆盖档，能避则避]"
        if e["hot"] == "客胜" and 2.2 < e["hot_odds"] < 3.0:
            return " [弱客热门·翻主+平]"
        return ""

    def double_dir9(e):
        """任九v3专用双选方向（十四场沿用上面 double_dir，不受影响）：
        势均画像→主+客（三结果 主35.1/客36.0/平28.9，平局反而最小，覆盖
        71.1%>热门+平约64~65%，2026-08-17整期回测验证）；其余沿用弱热门纪律"""
        if e["kind"] == "势均":
            return "主胜 + 客胜"
        if e["hot"] == "客胜" and 2.2 < e["hot_odds"] < 3.0:
            return f"{e['hc']}(主)胜 + 平局"
        if e["hot"] == "主胜":
            return f"{e['hc']}(主)胜 + 平局"
        return f"{e['ac']}(客)胜 + 平局"

    lines = [f"任九/胜负彩 · 第{period}期 · 64元复式推荐", ""]

    # FIX-001b：销售截止时间必须来自官方源实时抓取，打印来源+抓取时间；
    # 抓不到印"未核实"，禁止输出假设的默认截止时间（函数说明见上方 FIX-001b 注释块）
    _dl = fetch_sale_deadline(period)
    if _dl:
        lines.append(f"【销售截止】第{period}期 {_dl['deadline']}（{_dl['source']}，抓取于 {_dl['fetch_ts']}）")
    else:
        lines.append(f"【销售截止】第{period}期 截止时间未核实 请以官方为准")
    lines.append("")

    # 择期信号（2026-08-17新增，见 _backtest_ren9_upset_timing_0817.py）：
    # 任九是单档全中制、彩池按中奖人数摊分(parimutuel)——同样是猜中，冷门越多的
    # 期次单注奖金越高(RULES文档5.6节：冷门6→约1907元，冷门8→约5226元，冷门
    # 11→约20587元)。冷门数是全部14场的属性，不是"选哪9场"能控制的，但可以在
    # 开奖前用14场赔率预判"这期冷门大概率多不多"，作为"要不要多下注"的参考。
    # 5614组伪期次回测：14场去水favorite概率均值按十分位分组，D1(把握度最低,
    # 均值0.46)组实际冷门数均值7.65场，D10(把握度最高,均值0.57)组仅6.05场，
    # 差距1.59场，Pearson相关系数-0.242，是真实可用的择期信号（不影响DP选场，
    # 只是提示这期整体"肉"厚不厚）
    _fav_conf_mean = sum(max(e["probs"].values()) for e in entries) / len(entries) if entries else 0
    if _fav_conf_mean < 0.48:
        _timing_hint = "本期14场市场整体把握度偏低（弱热门多），历史统计冷门数偏高，可能是大奖期，值得多投"
    elif _fav_conf_mean > 0.54:
        _timing_hint = "本期14场市场整体把握度偏高（强热门多），历史统计冷门数偏低，大概率是普通期，不建议重注"
    else:
        _timing_hint = "本期14场市场整体把握度中等，冷门数大概率在常规区间"
    lines.append(f"【择期信号】14场favorite概率均值={_fav_conf_mean:.3f} —— {_timing_hint}")
    lines.append("")

    # 达标单选(碾压+<1.5双门槛)场次提示：仅供参考。原"择期门槛"(<4场建议
    # 弃期)只对十四场(14场全选无法跳过难场)仍有参考意义；任九v3已经是"先按
    # 赔率排序选最有把握的9场"，本身就会自动避开难场，不再需要"整期弃期"这个
    # 更粗的开关
    if len(single_cand) < 4:
        lines.append(f"【提示】本期达标单选(碾压+<1.5)仅 {len(single_cand)} 场——十四场需14场全押，")
        lines.append("  缺料期建议弃期或小额观赏；任九v3已按赔率自动跳过最难的5场，不受此提示直接影响。")
        lines.append("")

    # ===== 十四场完整方案（14场全选，64元 = 5双选9单选）DP精确解 =====
    # 2026-08-17：原v2画像分配(势均+偏热池按draw odds升序取前5双选)在14场全押
    # 场景下也用DP重新验证——跟任九不同，十四场没有"跳场"自由度，全部14场都要
    # 押，改进空间理论上应该更小，但实测DP优势反而更明显：224560组伪期次回测
    # DP 0.1438% vs v2画像启发式0.1131%，+2.87倍标准误(统计显著)，相对+27.1%。
    # 已替换v2的画像驱动分配，改用DP在"恰好9单选+5双选(14场全押无跳过)"约束下
    # 精确求解。
    lines.append("【十四场胜负彩 · 14场全选 · 64元 = 5双选+9单选】DP精确解")
    single_idx14, double_idx14 = _ren9_dp_optimal(entries, n_single=9, n_double=5)
    def _qual(x):
        return x["kind"] == "碾压" and x["hot_odds"] < 1.5
    single14 = sorted([entries[i] for i in single_idx14], key=lambda x: x["hot_odds"])
    double14 = sorted([entries[i] for i in double_idx14], key=lambda x: x["hot_odds"])

    lines.append("  双选 5 场：")
    for e in double14:
        lines.append(f"  · {e['lg']} {e['hc']}(主) vs {e['ac']}(客) {e['ho']}/{e['dr']}/{e['ao']} 选 {double_dir(e)}{dbl_tag(e)}")
    lines.append("  单选 9 场：")
    for e in single14:
        risk = "" if _qual(e) else " [险]"
        lines.append(f"  · {e['lg']} {e['hc']}(主) vs {e['ac']}(客) {e['ho']}/{e['dr']}/{e['ao']} 选 {hot_cn(e)}{risk}")

    # ===== 任九方案（选9场，64元 = 5双选4单选）DP精确解 =====
    # 演进历史：v2(画像驱动分配) → v3(按hot_odds排序启发式选场，2026-08-17发现
    # v2比简单基线整期全中率低30~48%后的修正) → DP精确解(2026-08-17当天进一步
    # 优化，见 _backtest_ren9_dp_optimal_0817.py)。
    # v3虽然修正了"选场结构"的方向性错误，但"排序后硬切4单/5双"仍是启发式，
    # 不是数学最优。改用DP：给定14场每场"单选成功概率"(去水后最高概率)和
    # "双选成功概率"(去水后前两高概率之和)，在"恰好4单选+5双选(+5跳过)"约束下
    # 精确求解P(9场全中)连乘积最大化的组合（0/1背包式DP，全局最优解，不是近似）。
    # 112280组伪期次回测：DP整期全中率5.72% vs v3启发式5.38%，+0.33个百分点/
    # 3.47倍标准误(统计显著)，相对提升+6.2%。双选/单选具体选哪个方向仍用三赔率
    # 画像微调(势均→主+客等)——回测已证明这层微调本身对启发式选场结构无增益，
    # 但保留展示不影响DP选场/选量这一步的正确性，仅供参考。
    lines.append("")
    lines.append("【任九 · 14场选9场 · 64元 = 5双选+4单选】DP精确解")
    single_idx, double_idx = _ren9_dp_optimal(entries)
    single9 = sorted([entries[i] for i in single_idx], key=lambda x: x["hot_odds"])
    double9 = sorted([entries[i] for i in double_idx], key=lambda x: x["hot_odds"])
    kept_ids = {id(entries[i]) for i in single_idx + double_idx}
    skipped = [e for e in entries if id(e) not in kept_ids]

    lines.append("  单选 4 场：")
    for e in single9:
        mark = "" if (e["kind"] == "碾压" and e["hot_odds"] < 1.5) else " [险]"
        lines.append(f"  · {e['hc']}(主) vs {e['ac']}(客) {e['hot_odds']} 选 {hot_cn(e)}{mark}")
    lines.append("  双选 5 场：")
    for e in double9:
        lines.append(f"  · {e['hc']}(主) vs {e['ac']}(客) {e['ho']}/{e['dr']} 选 {double_dir9(e)}")
    if skipped:
        lines.append("  避开(DP判定放弃收益最优的5场)：" + "、".join(f"{e['hc']}vs{e['ac']}" for e in skipped))

    # 模型分歧提示（弱信号，仅FYI，土豆自测分歧时模型28.4%<赔率71.6%，不参与选号）
    div = [e for e in entries if e["disagree"]]
    if div:
        lines.append("")
        # 2026-08-31明确标注：entries对全部14场统一计算一次，disagree/injury_dir/
        # elo_dir同一份数据同时喂给上面十四场和任九两个板块的选号，这里只是排版上
        # 紧跟在任九下面，不是"只对任九生效"——用户曾误以为伤停信号没接入十四场，
        # 加这行说明避免同样的误解再发生。
        lines.append("【模型分歧提示·对上方十四场+任九两个板块同时生效，弱信号仅供参考】")
        for e in div:
            elo_note = f"，ELO同向支持" if e["elo_dir"] == e["mdir"] else ""
            inj_note = f"，伤停信号同向支持" if e.get("injury_dir") == e["mdir"] else ""
            lines.append(f"  · {e['hc']} vs {e['ac']} 模型判{e['mdir']}，市场判{e['hot']}，留意{elo_note}{inj_note}")

    lines.append("")
    lines.append("方法论：RULES_任九胜负彩选号方法论.md（十四场和任九均用DP精确解(去水概率+0/1背包式DP)选场+单双选。任九：v2画像分配比简单基线低30~48%→v3启发式选场追平基线→DP再+6.2%(3.47倍标准误显著，939个真实期次交叉验证)。十四场：DP比v2画像启发式+27.1%(2.87倍标准误显著)。三赔率画像分类经严谨对比证实对方向选择无额外贡献，只保留展示。详见_backtest_ren9_period_sim_0817.py/_backtest_ren9_dp_optimal_0817.py/_backtest_ren9_real_periods_0817.py）")

    text = "\n".join(lines)
    print(text)
    # FIX-007-7（2026-09-13）：早场/临场双单并列存档（D:\lucky，彩票推荐单
    # 固定保存路径），同时把任九DP pick落库ren9_live_slips（slip_type=
    # early/live），供ren9_daily_review对比"早场单 vs 临场单"的实际命中差异。
    # FIX-009-4（2026-09-14）：save_tag="Pinnacle临场" 是比对臂（pin_live）——
    # 只归档选号供复盘分歧对账，不在D:\lucky落txt（它不是投注单，落盘会与
    # 正式早/临场单混淆）。
    if save_tag:
        _TAG2TYPE = {"临场": "live", "Pinnacle临场": "pin_live"}
        slip_type = _TAG2TYPE.get(save_tag, "early")
        if save_tag == "Pinnacle临场":
            print("Pinnacle比对臂：仅归档 ren9_live_slips(slip_type=pin_live)，不落txt单")
        else:
            _path = _save_slip(text, period, save_tag)
            print(f"投注单已存: {_path}")
        _archive_picks(period, entries, single_idx, double_idx, slip_type)
    if push:
        _push(text)


# ── FIX-007-7 早场/临场双单存档（2026-09-13）──────────────────────────
SLIP_DIR = r"D:\lucky"   # 彩票推荐单保存路径（永久规则：存D:\lucky不是桌面）


def _save_slip(text: str, period: str, tag: str) -> str:
    ts = datetime.now().strftime("%Y-%m-%d_%H%M")
    path = os.path.join(SLIP_DIR, f"任九_第{period}期_{tag}单_{ts}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _init_live_slips(conn):
    # 新建表（CLAUDE.md规则：只允许ADD COLUMN或新建表）
    conn.execute("""CREATE TABLE IF NOT EXISTS ren9_live_slips (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period TEXT NOT NULL,
        seq INTEGER NOT NULL,
        mode TEXT,
        pick TEXT,
        slip_type TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now','localtime')),
        UNIQUE(period, seq, slip_type)
    )""")


def _double9_outcomes(e):
    """跟 run() 里 double_dir9() 同一套任九双选方向逻辑，但返回结果名集合
    （落库用，不带队名/赔率）。注意 double_dir9 是嵌在 run() 里的闭包，
    这里平行实现一份，改动 double_dir9 时必须同步改这里。"""
    if e["kind"] == "势均":
        return {"主胜", "客胜"}
    if e["hot"] == "客胜" and 2.2 < e["hot_odds"] < 3.0:
        return {"主胜", "平局"}
    if e["hot"] == "主胜":
        return {"主胜", "平局"}
    return {"客胜", "平局"}


def _archive_picks(period, entries, single_idx, double_idx, slip_type):
    """把任九DP选号结果落库 ren9_live_slips（同日重跑同类型覆盖更新）。"""
    conn = sqlite3.connect(DB)
    try:
        _init_live_slips(conn)
        n = 0
        for i in single_idx:
            e = entries[i]
            conn.execute("""INSERT INTO ren9_live_slips (period,seq,mode,pick,slip_type)
                VALUES (?,?,?,?,?)
                ON CONFLICT(period,seq,slip_type) DO UPDATE SET
                 mode=excluded.mode, pick=excluded.pick""",
                (str(period), int(e["seq"]), "single", e["single_pick"], slip_type))
            n += 1
        for i in double_idx:
            e = entries[i]
            pick = "+".join(sorted(_double9_outcomes(e)))
            conn.execute("""INSERT INTO ren9_live_slips (period,seq,mode,pick,slip_type)
                VALUES (?,?,?,?,?)
                ON CONFLICT(period,seq,slip_type) DO UPDATE SET
                 mode=excluded.mode, pick=excluded.pick""",
                (str(period), int(e["seq"]), "double", pick, slip_type))
            n += 1
        conn.commit()
        print(f"任九DP选号已归档 ren9_live_slips: {n}场 (slip_type={slip_type})")
    except Exception as e:
        # 归档失败不中断出单主流程，但必须显式可见（CLAUDE.md：禁止静默吞异常）
        print(f"⚠️ ren9_live_slips 归档失败: {type(e).__name__}: {e}")
    finally:
        conn.close()


def _push(text):
    """本项目环境没有土豆的飞书凭证文件，会打印提示后跳过，不影响主流程"""
    cfg_path = r"C:\Users\cn\.openclaw\openclaw.json"
    if not os.path.exists(cfg_path):
        print("（本项目环境无飞书凭证文件，跳过推送，仅打印/落库）")
        return
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    feishu = cfg.get("channels", {}).get("feishu", {})
    app_id = feishu.get("appId", ""); app_secret = feishu.get("appSecret", "")
    if not app_id or not app_secret:
        print("飞书凭证缺失"); return
    import requests
    tr = requests.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                       json={"app_id": app_id, "app_secret": app_secret}, timeout=20)
    token = (tr.json() or {}).get("tenant_access_token", "")
    if not token: return
    mr = requests.post("https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
                       headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                       json={"receive_id": "ou_730c288f062f663e4a393bfff8a8bca6",
                             "msg_type": "text", "content": json.dumps({"text": text}, ensure_ascii=False)}, timeout=20)
    code = (mr.json() or {}).get("code")
    print("飞书推送:", "成功" if code == 0 else f"失败 code={code}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", required=True)
    ap.add_argument("--odds-file", default=None, help="最新赔率 JSON 文件（99 家平均欧指）")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--save-tag", default="早场",
                    help="存档标签：早场/临场（FIX-007-7），传空字符串则只打印不落盘不归档")
    args = ap.parse_args()
    run(args.period, push=not args.no_push, odds_file=args.odds_file,
        save_tag=args.save_tag or None)
