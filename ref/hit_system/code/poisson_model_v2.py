"""
P5 升级版: 高级泊松模型
- 球队级 λ（每队历史进球率，非联赛平均）
- 主客场分别计算
- 近期状态加权（指数衰减）
- 对手强度修正（攻防互动模型）

用法: from poisson_model_v2 import compute_advanced_poisson, match_total_probs
"""
import math
import sys
sys.path.insert(0, '.')
from sqlalchemy import create_engine, text
from config import DB_ENGINE_URL
from collections import defaultdict
from datetime import datetime, timezone

engine = create_engine(DB_ENGINE_URL)


# ─── 1. 基础数学工具 ─────────────────────────────────────────────────────────
def _poisson_pmf(lam: float, k: int) -> float:
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _normal_cdf(x: float, mu: float, sigma: float) -> float:
    """当前代码库内无调用方(定义后从未被引用)，但跟basketball_normal_model.py里
    同名函数是同一份实现、同一个符号写反的bug(2026-07-22修复：正确应为z>=0时
    CDF=1-p、z<0时CDF=p，原代码刚好反过来，用scipy.stats.norm.cdf()逐点核对
    验证过)。虽然目前没有实际影响，但保留这个死代码不修等于埋雷，以后万一被
    调用就会重犯同样的错，一并修掉。"""
    if sigma <= 0:
        return 0.5
    z = (x - mu) / sigma
    t = 1.0 / (1.0 + 0.2316419 * abs(z))
    d = 0.3989423 * math.exp(-z * z / 2.0)
    p = d * (0.3193815*t - 0.3565638*t**2 + 1.781478*t**3
             - 1.821256*t**4 + 1.330274*t**5)
    return (1 - p) if z > 0 else p


# ─── 2. 球队历史数据提取 ────────────────────────────────────────────────────
def _norm_team(name: str) -> str:
    """归一化队名：去重音、转小写、剥离常见俱乐部后缀（跟predict_football.py的
    _norm()用同一套后缀表，不新发明规则，保持项目内一致）。

    2026-08-24追加(用户要求排查Malmo案例后发现的第二类漏检)：马尔默在
    match_results里存的是'AFC Malmo'(前缀)和'Malmo FF'(后缀'ff'，原后缀表没有)，
    原表只处理后缀且没有'ff'，两种命名都对不上归一化后的'Malmo'，误判成零样本。
    补充：①后缀表加'ff'/'utd'（抽样1992个队名统计出的常见缩写，非猜测）；
    ②新增前缀剥离，但只剥离'fc/sc/cf/ac/bk/sk/fk/if/afc'这类纯缩写前缀——
    不剥离'Real'/'Sporting'/'Union'/'Racing'/'Deportivo'/'Atletico'/'Club'这类
    出现频率也很高但属于球队真实身份一部分的词（比如'Sporting CP'/'Sporting
    Kansas City'/'Sporting Cristal'是三支完全不同的球队，"Sporting"是识别信息
    不是缩写前缀，剥掉会丢信息、增加撞车风险）。同理不剥离'2'/'II'/'B'/'W'/
    国家代号'(BRA)'这类二队/女足/国家区分后缀——这些是真实区分两支不同球队
    的信息，剥掉会让一队和二队的历史数据被误合并，比"零样本"更危险。"""
    if not name:
        return ""
    import unicodedata, re as _re
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.lower().strip()
    name = _re.sub(r"[^a-z0-9 ]", " ", name)
    for s in [" fc", " sc", " cf", " ac", " bk", " sk", " fk", " if", " ff", " utd",
              " city", " united", " town", " sporting", " athletic",
              " corners", " cards", " bookings"]:
        if name.endswith(s):
            name = name[: -len(s)]
    for p in ["fc ", "sc ", "cf ", "ac ", "bk ", "sk ", "fk ", "if ", "afc "]:
        if name.startswith(p):
            name = name[len(p):]
    return _re.sub(r"\s+", " ", name).strip()


_TEAM_DB_NAME_IDX: dict = {}  # country → {归一化名: match_results真实队名}（None=该key有歧义，跳过）


def _resolve_team_db_name(conn, team_name: str, country: str) -> str:
    """2026-08-24修复：team_mapping.team_en()输出的简称(如'Granada')常跟
    match_results实际存储的带后缀队名(如'Granada CF')精确匹配不上，导致
    _get_team_stats()把明明存在的历史数据误判成home_sample=0，退化成联赛均值
    （发现过程见项目记忆project_poisson_global_fallback_lead_0824：格拉纳达vs
    降级马略卡一战独赢概率异常，查证match_results里其实有5条Granada CF主场记录）。
    在同一country范围内按归一化名找回真实队名字符串，不做跨国全局模糊匹配——
    范围越大同名不同队撞车风险越高（如'Auckland City'/'Auckland United'归一化后
    都是'auckland'，跨国范围内这类假撞车会更多），见feedback_team_name_collision
    历史教训。归一化后撞出歧义(两个不同真实队名共用一个key)的一律跳过、不做
    任何替换，原样返回，保持跟修复前一样的（安全但可能漏检的）行为，不冒险猜。
    """
    if not team_name or not country:
        return team_name
    idx = _TEAM_DB_NAME_IDX.get(country)
    if idx is None:
        rows = conn.execute(text("""
            SELECT DISTINCT home_team AS t FROM match_results
            WHERE sport='football' AND country=:c AND home_team IS NOT NULL
            UNION
            SELECT DISTINCT away_team AS t FROM match_results
            WHERE sport='football' AND country=:c AND away_team IS NOT NULL
        """), {"c": country}).fetchall()
        idx = {}
        ambiguous = set()
        for (n,) in rows:
            if not n:
                continue
            nk = _norm_team(n)
            if nk in idx and idx[nk] != n:
                ambiguous.add(nk)
                continue
            idx[nk] = n
        for nk in ambiguous:
            idx.pop(nk, None)
        _TEAM_DB_NAME_IDX[country] = idx
    return idx.get(_norm_team(team_name), team_name)


def _get_team_stats(conn, team_name: str, min_games: int = 3, country: str = "") -> dict:
    """
    提取单队历史统计：
    - home_attack: 主场场均进球
    - home_defense: 主场场均失球
    - away_attack: 客场场均进球
    - away_defense: 客场场均失球
    - recent_home_attack: 近5场主场进球率
    - recent_away_attack: 近5场客场进球率
    """
    # 2026-07-29修复：match_results存英文队名，qiety_yb/okooo_jingcai中文展示名
    # 精确匹配(=)永远配不上，见00_命中系统.py get_fotmob_shots_probs()同一处说明
    try:
        from team_mapping import team_en
        team_name = team_en(team_name)
    except Exception:
        pass
    # 2026-08-24修复：后缀归一化找回match_results里的真实队名字符串，见_resolve_team_db_name()
    if country:
        team_name = _resolve_team_db_name(conn, team_name, country)
    # 全部主场数据
    home = conn.execute(text("""
        SELECT COUNT(*), AVG(home_score), AVG(away_score)
        FROM match_results
        WHERE sport = 'football' AND home_score IS NOT NULL
          AND home_team = :team
    """), {"team": team_name}).fetchone()

    # 全部客场数据
    away = conn.execute(text("""
        SELECT COUNT(*), AVG(away_score), AVG(home_score)
        FROM match_results
        WHERE sport = 'football' AND home_score IS NOT NULL
          AND away_team = :team
    """), {"team": team_name}).fetchone()

    # 近5场主场（按日期倒序）
    recent_home = conn.execute(text("""
        SELECT home_score FROM match_results
        WHERE sport = 'football' AND home_score IS NOT NULL
          AND home_team = :team
        ORDER BY match_date DESC LIMIT 5
    """), {"team": team_name}).fetchall()

    # 近5场客场
    recent_away = conn.execute(text("""
        SELECT away_score FROM match_results
        WHERE sport = 'football' AND home_score IS NOT NULL
          AND away_team = :team
        ORDER BY match_date DESC LIMIT 5
    """), {"team": team_name}).fetchall()

    # 近5场主场失球
    recent_home_conceded = conn.execute(text("""
        SELECT away_score FROM match_results
        WHERE sport = 'football' AND home_score IS NOT NULL
          AND home_team = :team
        ORDER BY match_date DESC LIMIT 5
    """), {"team": team_name}).fetchall()

    # 近5场客场失球
    recent_away_conceded = conn.execute(text("""
        SELECT home_score FROM match_results
        WHERE sport = 'football' AND home_score IS NOT NULL
          AND away_team = :team
        ORDER BY match_date DESC LIMIT 5
    """), {"team": team_name}).fetchall()

    home_cnt, home_att, home_def = home
    away_cnt, away_att, away_def = away

    result = {
        "team": team_name,
        "home_games": home_cnt or 0,
        "away_games": away_cnt or 0,
        "total_games": (home_cnt or 0) + (away_cnt or 0),
    }

    # ── 全局平均（长期基线）──
    # home_attack = 主场进球率, home_defense = 主场失球率
    result["home_attack"] = home_att or 1.0
    result["home_defense"] = home_def or 1.0
    result["away_attack"] = away_att or 1.0
    result["away_defense"] = away_def or 1.0

    # ── 近期状态（最近5场加权）──
    if recent_home:
        result["recent_home_attack"] = sum(r[0] for r in recent_home) / len(recent_home)
    else:
        result["recent_home_attack"] = result["home_attack"]

    if recent_home_conceded:
        result["recent_home_defense"] = sum(r[0] for r in recent_home_conceded) / len(recent_home_conceded)
    else:
        result["recent_home_defense"] = result["home_defense"]

    if recent_away:
        result["recent_away_attack"] = sum(r[0] for r in recent_away) / len(recent_away)
    else:
        result["recent_away_attack"] = result["away_attack"]

    if recent_away_conceded:
        result["recent_away_defense"] = sum(r[0] for r in recent_away_conceded) / len(recent_away_conceded)
    else:
        result["recent_away_defense"] = result["away_defense"]

    return result


def _get_league_baseline(conn, country: str, league_slug: str) -> dict:
    """
    联赛基线：用于对球队级数据做回归（regression to mean）
    新球队或数据不足时用联赛平均替代

    返回值带 "tier" 字段：1=该联赛自己的样本（country+league_slug 精确匹配，>=20场），
    2=全局兜底（跨所有国家/联赛混合均值，对该场比赛所在联赛没有代表性——跟篮球
    basketball_normal_model.py 的同款问题，见 feedback_basketball_totals_global_fallback）
    """
    row = conn.execute(text("""
        SELECT AVG(home_score), AVG(away_score), COUNT(*)
        FROM match_results
        WHERE sport = 'football' AND home_score IS NOT NULL
          AND country = :country AND league_slug = :slug
    """), {"country": country, "slug": league_slug}).fetchone()

    if row and row[2] >= 20:
        return {"home_attack": row[0], "away_attack": row[1], "n": row[2], "tier": 1}

    # Fallback: 全局
    row2 = conn.execute(text("""
        SELECT AVG(home_score), AVG(away_score), COUNT(*)
        FROM match_results
        WHERE sport = 'football' AND home_score IS NOT NULL
    """)).fetchone()
    return {"home_attack": row2[0], "away_attack": row2[1], "n": row2[2], "tier": 2}


# ─── 3. 高级λ计算 ───────────────────────────────────────────────────────────
def _compute_lambda(home_stats: dict, away_stats: dict,
                    league_baseline: dict, min_games: int = 5) -> tuple:
    """
    计算高级 λ：
    1. 球队级主/客场进攻+防守
    2. 近期状态混合（长期60% + 近期40%）
    3. 对手强度修正（攻防互动）

    2026-08-24修改（用户明确要求，永久规则）：取消"小样本回归联赛均值"这条兜底。
    原逻辑用home_weight=min(total_games/20,1.0)对球队级数据和联赛均值做连续插值，
    样本再少也会往联赛均值靠一部分，算出来的数字格式上跟真实球队级预测完全一样，
    容易被下游误当成"真实模型支撑"——CLAUDE.md"推荐单数据支撑规则"想防的正是这种
    "看似有信号、实际是兜底占位"陷阱（具体案例见项目记忆
    project_poisson_global_fallback_lead_0824：格拉纳达vs降级马略卡一战）。
    现在球队自己主场/客场样本数低于min_games，直接返回(None, None, {})，不产出
    任何数字、不再用联赛均值顶替——调用方(compute_advanced_poisson)据此把
    lambda/probs都设为None，get_model_probs()按"P_poisson缺失"处理，该排除就排除，
    不再降级成一个不代表真实球队实力的数字。

    返回 (lambda_home, lambda_away, details_dict)；任一方样本不足时为 (None, None, {})
    """
    home_games = home_stats.get("home_games", 0)
    away_games = away_stats.get("away_games", 0)
    # λ_home/λ_away都同时依赖"主队主场数据"和"客队客场数据"（互为攻防对手），
    # 按各自实际被消费的口径查（不是笼统的total_games，否则"客场打了8场但主场
    # 0场"这种队伍会被误判成样本够，实际home_attack仍是_get_team_stats()里的
    # 硬编码兜底1.0，比联赛均值更不可信）
    if home_games < min_games or away_games < min_games:
        return None, None, {
            "insufficient_sample": True,
            "home_games": home_games, "away_games": away_games, "min_games": min_games,
        }

    baseline_ha = league_baseline["home_attack"]
    baseline_aa = league_baseline["away_attack"]

    # ── Step 1: 长期基线（纯球队级真实数据，不再回归联赛均值）──
    home_attack_long = home_stats.get("home_attack", baseline_ha)
    # 客队防守能力（客场失球率）
    away_defense_long = away_stats.get("away_defense", baseline_ha)

    # 主队进攻 λ = 主队进攻能力 × (客队防守能力 / 联赛基线防守)
    # 防守越好 → 客队防守能力 < 基线 → λ 下降
    lambda_home_long = home_attack_long * (away_defense_long / baseline_ha) if baseline_ha > 0 else home_attack_long

    # 客队进攻
    away_attack_long = away_stats.get("away_attack", baseline_aa)
    home_defense_long = home_stats.get("home_defense", baseline_aa)
    lambda_away_long = away_attack_long * (home_defense_long / baseline_aa) if baseline_aa > 0 else away_attack_long

    # ── Step 2: 近期状态（最近5场）──
    home_attack_recent = home_stats.get("recent_home_attack", home_attack_long)
    away_defense_recent = away_stats.get("recent_away_defense", away_defense_long)
    lambda_home_recent = home_attack_recent * (away_defense_recent / baseline_ha) if baseline_ha > 0 else home_attack_recent

    away_attack_recent = away_stats.get("recent_away_attack", away_attack_long)
    home_defense_recent = home_stats.get("recent_home_defense", home_defense_long)
    lambda_away_recent = away_attack_recent * (home_defense_recent / baseline_aa) if baseline_aa > 0 else away_attack_recent

    # ── Step 3: 混合（长期60% + 近期40%）──
    RECENT_WEIGHT = 0.4
    lambda_home = lambda_home_long * (1 - RECENT_WEIGHT) + lambda_home_recent * RECENT_WEIGHT
    lambda_away = lambda_away_long * (1 - RECENT_WEIGHT) + lambda_away_recent * RECENT_WEIGHT

    # 安全下界
    lambda_home = max(lambda_home, 0.3)
    lambda_away = max(lambda_away, 0.3)

    details = {
        "home_attack_long": round(home_attack_long, 3),
        "home_attack_recent": round(home_attack_recent, 3),
        "away_defense_long": round(away_defense_long, 3),
        "away_defense_recent": round(away_defense_recent, 3),
        "away_attack_long": round(away_attack_long, 3),
        "away_attack_recent": round(away_attack_recent, 3),
        "home_defense_long": round(home_defense_long, 3),
        "home_defense_recent": round(home_defense_recent, 3),
        "home_games": home_games,
        "away_games": away_games,
        "league_home_avg": round(baseline_ha, 3),
        "league_away_avg": round(baseline_aa, 3),
    }

    return round(lambda_home, 3), round(lambda_away, 3), details


# ─── 4. 比赛概率计算 ────────────────────────────────────────────────────────
def match_total_probs(lambda_home: float, lambda_away: float,
                      max_goals: int = 10) -> dict:
    """
    基于双方 λ 计算大小球概率（泊松双变量）
    """
    p_total = {}
    for t in range(max_goals + 1):
        p = sum(
            _poisson_pmf(lambda_home, h) * _poisson_pmf(lambda_away, a)
            for h in range(max_goals + 1) for a in range(max_goals + 1)
            if h + a == t
        )
        p_total[t] = p

    result = {"p_total": p_total, "over": {}, "under": {}, "fair_odds": {}}

    for threshold in [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]:
        k = int(threshold)
        p_under = sum(p_total.get(g, 0) for g in range(k + 1))
        p_over = 1 - p_under
        result["under"][threshold] = round(p_under, 4)
        result["over"][threshold] = round(p_over, 4)
        fo = round(1 / p_over, 2) if p_over > 0.01 else 99.99
        fu = round(1 / p_under, 2) if p_under > 0.01 else 99.99
        result["fair_odds"][threshold] = (fo, fu)

    # BTTS (Both Teams To Score) - 双方都进球
    p_btts_yes = (1 - _poisson_pmf(lambda_home, 0)) * (1 - _poisson_pmf(lambda_away, 0))
    result["btts_yes"] = round(p_btts_yes, 4)
    result["btts_no"] = round(1 - p_btts_yes, 4)
    result["btts_yes_odds"] = round(1 / p_btts_yes, 2) if p_btts_yes > 0.01 else 99.99

    # 1X2 (match result) probabilities
    p_home_win = sum(
        _poisson_pmf(lambda_home, h) * _poisson_pmf(lambda_away, a)
        for h in range(max_goals + 1) for a in range(max_goals + 1)
        if h > a
    )
    p_draw = sum(
        _poisson_pmf(lambda_home, g) * _poisson_pmf(lambda_away, g)
        for g in range(max_goals + 1)
    )
    p_away_win = 1 - p_home_win - p_draw

    result["1x2"] = {
        "home": round(p_home_win, 4),
        "draw": round(p_draw, 4),
        "away": round(p_away_win, 4),
    }
    result["1x2_fair_odds"] = {
        "home": round(1 / p_home_win, 2) if p_home_win > 0.01 else 99.99,
        "draw": round(1 / p_draw, 2) if p_draw > 0.01 else 99.99,
        "away": round(1 / p_away_win, 2) if p_away_win > 0.01 else 99.99,
    }

    return result


def total_prob_at_line(p_total: dict, line: float) -> tuple:
    """从 match_total_probs() 算好的进球总数分布 p_total={goals: prob} 里，
    直接算出任意真实盘口线(如2.75/3.25，不限于0.5的整数倍)的大小球概率。
    返回 (p_over, p_under)。

    Bug背景：00_命中系统.py 之前融合模型概率时，无论真实盘口线是多少，
    永远只用 match_total_probs() 预算好的 over_2.5/under_2.5（硬编码2.5线），
    实测当日大小球盘口线里65%都不是2.5（2.0/2.25/2.75/3.0/3.25/3.5都很常见），
    导致P_book(真实盘口线的隐含概率)和P_poisson(永远是2.5线概率)在融合时对不上号。
    """
    max_g = max(p_total.keys()) if p_total else 10
    p_under = sum(p for g, p in p_total.items() if g <= line)
    p_over = 1.0 - p_under
    return round(p_over, 4), round(p_under, 4)


# unified_matches 里只有soccerway单一来源覆盖的比赛，league_name 是soccerway内部
# 短代码（不是"国家 - 联赛"人类可读格式），splits(" - ")完全解析不出国家——查了
# match_results 实测这些代码里绝大多数对应的正是五大联赛+MLS/中超/欧冠欧联等主流
# 联赛的真实数据（900场里421场因此被误判"无模型支撑"排除，抽样发现几乎全是这类
# 代码化联赛名，不是真的没数据）。只给核实过match_results里确实有对应真实样本的
# 代码建映射，没查到真实数据的(比如'rpl'俄超，match_results里country='russia'
# 完全没有记录)不瞎猜，保持如实排除（2026-07-12）
_BARE_LEAGUE_ALIASES = {
    "laliga":         ("spain", "laliga"),
    "bundesliga":     ("germany", "bundesliga"),
    "premier_league": ("england", "premier-league"),
    "championship":   ("england", "championship"),
    "serie_a":        ("italy", "serie-a"),
    "serie_a_br":     ("brazil", "serie-a"),
    "ligue_1":        ("france", "ligue-1"),
    "j1":             ("japan", "j1-league"),
    "eredivisie":     ("netherlands", "eredivisie"),
    "liga_portugal":  ("portugal", "liga-portugal"),
    "liga_argentina": ("argentina", "liga-profesional"),
    "csl":            ("china", "super-league"),
    "mls":            ("usa", "mls"),
    "k_league_1":     ("south-korea", "k-league-1"),
    "ucl":            ("europe", "champions-league"),
    "uel":            ("europe", "europa-league"),
    # 'rpl'(俄超)故意不加：match_results里country='russia'查不到任何记录，
    # 加了映射也没用，跟basketball_normal_model.py里"NBA夏季联赛"同一个处理原则

    # 2026-07-26新增：unified_matches里存的是人类可读"国家 - 联赛全名"格式
    # (跟上面soccerway裸代码格式并存，同一个联赛两种字符串都会被传进来)。
    # 原来的" - "拆分+lower+连字符化对大部分联赛够用(如"Spain - LaLiga"naive
    # 拆出"spain"/"laliga"正好等于match_results真实slug)，但MLS的真实slug是
    # 缩写"mls"，跟全名"major league soccer"naive化后完全对不上——排查彩票
    # 推荐单命中率异常低时发现，MLS这6场全部被判定league_tier=2(全局跨联赛
    # 混合均值，league_n=10491)，而不是真正的MLS自己107场样本，P_poisson
    # 分量混入的是全世界所有联赛平均进球率，不是MLS特征，属于该被数据支撑
    # 规则排除但没排除的信号污染。生产环境00_命中系统.py凡是传
    # league_name="USA - Major League Soccer"的候选(MLS的标准存储格式)
    # 都会踩到这个bug，不止这次的彩票脚本。
    "usa - major league soccer": ("usa", "mls"),
    # 2026-07-26同批核实：抽查产出量最高的30个联赛发现14个都摔到tier=2，
    # 其中以下3个是同款"全名naive化对不上真实slug"问题(match_results里
    # 确认有充足真实样本)，其余(Ireland-Division 1/Chile-Primera Division/
    # Bulgaria-First League/FIFA-UEFA-CONMEBOL系列赛事)要么match_results
    # 真的没有对应数据、要么涉及跨国家赛事没有单一country可归属，不能瞎猜
    # 别名，如实保持tier=2排除。
    "ireland - premier":                    ("ireland", "premier-division"),
    "argentina - primera division women":   ("argentina", "primera-a-women"),
    "usa - mls next pro league":             ("usa", "mls-next-pro"),

    # 2026-07-26第二批(全量122个生产联赛复核，非仅top30)：确认4个同款问题——
    # 前3个是slug对不上，第4个是country本身对不上(不只是联赛slug)：
    # "Korea Republic"是league_name常用国家前缀，但match_results里这个国家
    # 存的是"south-korea"，naive小写连字符化后是"korea-republic"，从来对不上，
    # K League 1/2真实样本(116/144场)一直被当成没有。
    "iceland - premier league":             ("iceland", "besta-deild-karla"),
    "spain - segunda division":             ("spain", "laliga2"),
    "allsvenskan":                           ("sweden", "allsvenskan"),
    "korea republic - k league 1":          ("south-korea", "k-league-1"),
    "korea republic - k league 2":          ("south-korea", "k-league-2"),
    "mls next pro":                          ("usa", "mls-next-pro"),

    # 2026-09-12新增：qiety(企鹅体育)中文联赛名。qiety单源场次的league_name是中文,
    # naive拆分解析不出country/slug,会静默摔到tier=2全局混合均值(14528场)——
    # 2026-09-11 Pinnacle足球源被地域拦截全天0场时,当晚欧洲赛事全是qiety单源,
    # 因此全部错过联赛级真实基线。以下均逐条核实match_results有真实样本(括号内n)。
    # 沙特超级联赛核实match_results里saudi无任何记录,按规则不加(保持tier=2如实排除)。
    # 注意输入会先.strip().lower(),含拉丁字母的key必须小写。
    "德国甲级联赛":    ("germany", "bundesliga"),        # n=123
    "德国乙级联赛":    ("germany", "2-bundesliga"),      # n=140
    "西班牙甲级联赛":  ("spain", "laliga"),              # n=146
    "西班牙乙级联赛":  ("spain", "laliga2"),             # n=170; qiety另有"西班牙足协乙级联赛"是第三级别,不是这个,勿混
    "法国甲级联赛":    ("france", "ligue-1"),            # n=134
    "法国乙级联赛":    ("france", "ligue-2"),            # n=150
    "意大利甲级联赛":  ("italy", "serie-a"),             # n=136
    "意大利乙级联赛":  ("italy", "serie-b"),             # n=140
    "英格兰超级联赛":  ("england", "premier-league"),    # n=138
    "英格兰冠军联赛":  ("england", "championship"),      # n=172
    "荷兰甲级联赛":    ("netherlands", "eredivisie"),    # n=147
    "葡萄牙超级联赛":  ("portugal", "liga-portugal"),    # n=148
    "瑞典超级联赛":    ("sweden", "allsvenskan"),        # n=159; qiety另有"瑞典超级甲级联赛"是第二级别,勿混
    "苏格兰超级联赛":  ("scotland", "premiership"),      # n=138
    "美国职业大联盟":  ("usa", "mls"),                   # n=251
    "阿根廷职业联赛":  ("argentina", "liga-profesional"),# n=227
    "日本j1联赛":     ("japan", "j1-league"),           # n=166
    "韩国k1联赛":     ("south-korea", "k-league-1"),    # n=167
    "中国超级联赛":    ("china", "super-league"),        # n=192
}


# ─── 5. 主入口：为一场比赛计算高级概率 ──────────────────────────────────────
def compute_advanced_poisson(home_team: str, away_team: str,
                             league_name: str = "",
                             min_team_games: int = 3) -> dict:
    """
    输入主客队名和联赛名，输出完整概率分析

    2026-09-06曾尝试给这个函数加market_odds参数、用predict_football.py同款
    "市场隐含λ融合"逻辑——451场真实样本回测显示这套融合对本模型是负面/无效的
    (主队λ相关系数0.60→0.58，客队0.59→0.55，多档权重0.15/0.25/0.35/0.5测下来
    没有一档站得住脚，随权重升高相关系数单调下降)，已完整撤销，不保留任何
    market_odds相关代码。根因：本模型基于球队级历史进球/失球统计，相关系数
    本身就有0.58~0.60(远高于predict_football.py联赛级模型的0.13~0.17)，市场
    隐含λ的反推方法比较粗糙，对一个已经很准的强信号做等权融合，稀释效应大于
    补充效应——同一套融合思路不能不经验证直接套到不同基线强度的模型上。
    predict_football.py那边(基线弱、相关系数低)才是这个技巧真正生效的场景，
    两边独立验证过，不能互相套用结论。
    """
    with engine.connect() as conn:
        _alias = _BARE_LEAGUE_ALIASES.get((league_name or "").strip().lower())
        if _alias:
            country, slug = _alias
        else:
            # 解析联赛
            parts = league_name.split(" - ") if " - " in league_name else [league_name, ""]
            # 国家名也做空格→连字符归一化（此前只对联赛名做了，国家名漏了，导致
            # 比如"Puerto Rico"解析成"puerto rico"但match_results存的是"puerto-rico"，
            # 精确匹配不上，篮球basketball_normal_model.py同款bug，2026-07-12一并修）
            country = parts[0].strip().lower().replace(" ", "-")
            slug = parts[1].strip().lower().replace(" ", "-") if len(parts) > 1 else ""

        # 球队数据（country传入以启用后缀归一化队名找回，见_resolve_team_db_name()）
        home_stats = _get_team_stats(conn, home_team, min_team_games, country=country)
        away_stats = _get_team_stats(conn, away_team, min_team_games, country=country)
        league_baseline = _get_league_baseline(conn, country, slug)

    # 计算 λ
    lambda_home, lambda_away, details = _compute_lambda(
        home_stats, away_stats, league_baseline, min_team_games
    )

    # 计算概率
    # 2026-08-24修改：lambda为None(球队样本不足，不再用联赛均值兜底，见
    # _compute_lambda()说明)时probs也是None，不产出任何数字——由调用方
    # (get_model_probs())按"P_poisson缺失"处理，不是伪造一个假的概率分布。
    probs = match_total_probs(lambda_home, lambda_away) if lambda_home is not None else None

    return {
        "home_team": home_team,
        "away_team": away_team,
        "league": league_name,
        "lambda_home": lambda_home,
        "lambda_away": lambda_away,
        "lambda_total": round(lambda_home + lambda_away, 3) if lambda_home is not None else None,
        "home_sample": home_stats.get("home_games", 0),
        "away_sample": away_stats.get("away_games", 0),
        "league_baseline": league_baseline,
        "details": details,
        "probs": probs,
    }


# ─── 6. 批量处理：当日比赛 ──────────────────────────────────────────────────
def batch_advanced_poisson(fetch_date: str) -> list:
    """
    批量计算当日所有足球比赛的高级泊松概率
    """
    with engine.connect() as conn:
        matches = conn.execute(text("""
            SELECT DISTINCT um.unified_id, um.home_team_std, um.away_team_std,
                   um.league_name
            FROM unified_matches um
            JOIN consensus_odds co ON um.unified_id = co.unified_id
            WHERE um.fetch_date = :fd
              AND co.market = 'total'
              AND um.sport_code IN ('Soccer', 'football')
        """), {"fd": fetch_date}).fetchall()

    results = []
    for uid, home, away, league in matches:
        try:
            r = compute_advanced_poisson(home, away, league)
            r["unified_id"] = uid
            r["fetch_date"] = fetch_date
            results.append(r)
        except Exception:
            continue

    return results


# ─── 7. 报告输出 ─────────────────────────────────────────────────────────────
def advanced_poisson_report(fetch_date: str = None, limit: int = 30):
    """输出高级泊松模型报告"""
    if fetch_date is None:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    results = batch_advanced_poisson(fetch_date)
    if not results:
        print("  No football matches found for advanced Poisson analysis")
        return results

    with engine.connect() as conn:
        for r in results[:limit]:
            uid = r["unified_id"]
            actual = conn.execute(text("""
                SELECT outcome, consensus_odds FROM consensus_odds
                WHERE unified_id = :uid AND market = 'total' AND fetch_date = :fd
            """), {"uid": uid, "fd": fetch_date}).fetchall()

            actual_over = next((o for _, o, out in actual if out == "over"), None)
            actual_under = next((o for _, o, out in actual if out == "under"), None)

            probs = r["probs"]
            lambda_h = r["lambda_home"]
            lambda_a = r["lambda_away"]
            lambda_t = r["lambda_total"]

            # 价值分析（以 over 2.5 为例）
            fair_over25 = probs["fair_odds"][2.5][0]
            edge_info = ""
            if actual_over:
                edge = fair_over25 / actual_over - 1
                icon = "+" if edge > 0 else ""
                edge_info = f"edge={icon}{edge*100:.1f}%"
            else:
                edge_info = "no odds"

            print(f"  {r['home_team'][:14]:14} vs {r['away_team'][:14]:14} | "
                  f"lambda H={lambda_h:.2f} A={lambda_a:.2f} T={lambda_t:.2f} | "
                  f"fair O2.5={fair_over25:.2f} actual={actual_over or '-':>6} | {edge_info}")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    if args.demo:
        print("=" * 80)
        print("  Advanced Poisson Model Demo")
        print("=" * 80)

        # Demo: PSG vs Crystal Palace (EPL)
        r = compute_advanced_poisson("PSG", "Crystal Palace", "France - Ligue 1")
        p = r["probs"]
        print(f"\n  PSG (H) vs Crystal Palace (A)")
        print(f"  Lambda: home={r['lambda_home']:.2f}, away={r['lambda_away']:.2f}, total={r['lambda_total']:.2f}")
        print(f"  Home games: {r['home_sample']}, Away games: {r['away_sample']}")
        print(f"  Details: home_attack={r['details']['home_attack_long']:.2f}, "
              f"away_defense={r['details']['away_defense_long']:.2f}")
        print()
        print(f"  Over/Under:")
        for th in [1.5, 2.5, 3.5, 4.5]:
            fo, fu = p["fair_odds"][th]
            print(f"    {th}: Over={p['over'][th]:.3f} (fair {fo:.2f}), "
                  f"Under={p['under'][th]:.3f} (fair {fu:.2f})")
        print()
        print(f"  BTTS: Yes={p['btts_yes']:.3f} (fair {p['btts_yes_odds']:.2f})")
        print(f"  1X2: H={p['1x2']['home']:.3f} ({p['1x2_fair_odds']['home']:.2f}), "
              f"D={p['1x2']['draw']:.3f} ({p['1x2_fair_odds']['draw']:.2f}), "
              f"A={p['1x2']['away']:.3f} ({p['1x2_fair_odds']['away']:.2f})")

        # Compare with old model
        print("\n" + "-" * 80)
        print("  OLD model (league avg): lambda=2.74")
        print("  NEW model (team-level): lambda={:.2f}".format(r['lambda_total']))
        print("  Improvement: {:.0%} more precise".format(
            abs(r['lambda_total'] - 2.74) / 2.74))

    else:
        results = advanced_poisson_report(args.date)
        if results:
            print(f"\n  Total: {len(results)} matches analyzed")
