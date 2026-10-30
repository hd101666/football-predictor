"""
P5b: 篮球正态分布模型 — 基于历史得分数据计算大小球概率
用法: from basketball_normal_model import compute_basketball_probs, basketball_total_probs
"""
import math
import sys
sys.path.insert(0, '.')
from sqlalchemy import create_engine, text
from config import DB_ENGINE_URL

engine = create_engine(DB_ENGINE_URL)


def _normal_cdf(x: float, mu: float, sigma: float) -> float:
    """
    标准正态分布 CDF（累积分布函数）
    使用 Abramowitz & Stegun 近似
    """
    if sigma <= 0:
        return 0.5
    z = (x - mu) / sigma
    t = 1.0 / (1.0 + 0.2316419 * abs(z))
    d = 0.3989423 * math.exp(-z * z / 2.0)
    p = d * (0.3193815 * t
             - 0.3565638 * t**2
             + 1.781478 * t**3
             - 1.821256 * t**4
             + 1.330274 * t**5)
    # Bug修复(2026-07-22)：p是Abramowitz&Stegun近似算出的上尾概率Q(|z|)，
    # 正确CDF应该是 z>=0时1-p(上尾之外的部分)，z<0时p(对称，下尾=Q(|z|))。
    # 原来写反了(return p if z>0 else 1-p)，导致这个函数从来算的都是1-真实CDF——
    # 用scipy.stats.norm.cdf()逐点核对验证过，所有z≠0的取值全部对不上，
    # z=0是巧合(1-0.5=0.5跟0.5相等，边界情况掩盖了这个bug)。这个函数是
    # basketball_total_probs()/compute_team_total_probs()的唯一CDF来源，
    # 相当于篮球大小球模型的大球/小球概率此前一直是反的。
    return (1 - p) if z > 0 else p


def _get_league_stats(conn, country: str, league_slug: str, min_games: int = 10) -> dict:
    """
    从 match_results 计算联赛级均值和标准差。

    返回的 dict 带 "tier" 字段标注数据来源可信度：
      1 = 该联赛自己的样本（country+league_slug 精确匹配）
      2 = 同国家但联赛不明（跨联赛混合，仍算同一国家篮球环境）
      3 = 全局兜底（跨国家/跨联赛全部混在一起的场均分布，NBA夏季联赛这类
          country_hint 本身就是league_name误当country解析出来的畸形值，
          必然查不到real country/league_slug，会摔到这一档——这个数字
          对任何具体联赛都没有代表性，调用方不能把它当真实模型信号用，
          见 00_命中系统.py 里 basketball totals 的 tier==3 排除逻辑）
    """
    row = conn.execute(text("""
        SELECT AVG(home_score), AVG(away_score),
               AVG(home_score + away_score),
               sqrt(AVG((home_score + away_score)*(home_score + away_score))
                    - AVG(home_score + away_score)*AVG(home_score + away_score)),
               COUNT(*)
        FROM match_results
        WHERE sport = 'basketball'
          AND home_score IS NOT NULL
          AND country = :country
          AND league_slug = :slug
    """), {"country": country, "slug": league_slug}).fetchone()

    if row and row[4] >= min_games and row[3]:
        return {"avg_home": row[0], "avg_away": row[1], "avg_total": row[2],
                "std_total": row[3], "n_games": row[4], "tier": 1}

    # Fallback: same country
    row2 = conn.execute(text("""
        SELECT AVG(home_score), AVG(away_score),
               AVG(home_score + away_score),
               sqrt(AVG((home_score + away_score)*(home_score + away_score))
                    - AVG(home_score + away_score)*AVG(home_score + away_score)),
               COUNT(*)
        FROM match_results
        WHERE sport = 'basketball'
          AND home_score IS NOT NULL
          AND country = :country
    """), {"country": country}).fetchone()

    if row2 and row2[4] >= min_games and row2[3]:
        return {"avg_home": row2[0], "avg_away": row2[1], "avg_total": row2[2],
                "std_total": row2[3], "n_games": row2[4], "tier": 2}

    # Final fallback: global basketball average（跨联赛均值，不代表任何具体联赛）
    row3 = conn.execute(text("""
        SELECT AVG(home_score), AVG(away_score),
               AVG(home_score + away_score),
               sqrt(AVG((home_score + away_score)*(home_score + away_score))
                    - AVG(home_score + away_score)*AVG(home_score + away_score)),
               COUNT(*)
        FROM match_results
        WHERE sport = 'basketball' AND home_score IS NOT NULL
    """)).fetchone()
    return {"avg_home": row3[0], "avg_away": row3[1], "avg_total": row3[2],
            "std_total": row3[3] or 20.0, "n_games": row3[4], "tier": 3}


def _get_team_scoring_stats(conn, team_name: str, min_games: int = 8) -> dict | None:
    """单队历史场均得分(不分主客场，篮球主客场得分差异远小于足球，不必分开建模)。
    样本不足时返回 None，调用方自行决定兜底（不像 _get_league_stats 那样内置多级fallback，
    因为球队级样本不够时应该直接说明"没有单队模型"，而不是悄悄退化成联赛均值冒充单队数据）。
    """
    # 2026-07-29修复：match_results存英文队名，见poisson_model_v2.py同一处说明
    try:
        from team_mapping import team_en
        team_name = team_en(team_name)
    except Exception:
        pass
    rows = conn.execute(text("""
        SELECT CASE WHEN home_team = :team THEN home_score ELSE away_score END as pts
        FROM match_results
        WHERE sport = 'basketball' AND home_score IS NOT NULL AND away_score IS NOT NULL
          AND (home_team = :team OR away_team = :team)
        ORDER BY match_date DESC LIMIT 40
    """), {"team": team_name}).fetchall()
    pts = [r[0] for r in rows if r[0] is not None]
    n = len(pts)
    if n < min_games:
        return None
    avg = sum(pts) / n
    var = sum((p - avg) ** 2 for p in pts) / n
    std = var ** 0.5
    return {"avg_pts": round(avg, 1), "std_pts": round(std, 1) if std > 0 else 10.0, "n_games": n}


def compute_team_total_probs(team_name: str, line: float) -> dict | None:
    """单队大小球(team_total)概率：用该队自己近40场历史得分的均值/标准差算正态分布，
    不再像修复前那样借用整场总分模型的分布（口径不对，那是两队合计不是单队）。
    样本不足(<8场)时返回 None，调用方应跳过该场的 team_total 打分，不要兜底硬凑。
    """
    with engine.connect() as conn:
        stats = _get_team_scoring_stats(conn, team_name)
    if not stats:
        return None
    p_over = 1 - _normal_cdf(line, stats["avg_pts"], stats["std_pts"])
    p_under = _normal_cdf(line, stats["avg_pts"], stats["std_pts"])
    return {
        "avg_pts": stats["avg_pts"], "std_pts": stats["std_pts"], "n_games": stats["n_games"],
        "over": round(p_over, 4), "under": round(p_under, 4),
    }


def basketball_total_probs(avg_total: float, std_total: float,
                           thresholds: list = None) -> dict:
    """
    基于正态分布计算篮球大小球概率
    thresholds: 盘口线列表，如 [200.5, 210.5, 215.5, 220.5]
    返回: {"over": {line: prob}, "under": {line: prob}, "fair_odds": {line: (over, under)}}
    """
    if thresholds is None:
        # 自动生成盘口线：均值 ± 2.5 * std 范围内，步长 5
        base = int(avg_total / 5) * 5 + 0.5  # e.g. 220.5
        thresholds = [base - 20, base - 15, base - 10, base - 5, 
                      base, base + 5, base + 10, base + 15, base + 20]

    result = {"over": {}, "under": {}, "fair_odds": {}}
    for line in thresholds:
        p_over = 1 - _normal_cdf(line, avg_total, std_total)
        p_under = _normal_cdf(line, avg_total, std_total)
        result["over"][line] = round(p_over, 4)
        result["under"][line] = round(p_under, 4)
        fair_over = round(1 / p_over, 2) if p_over > 0.01 else 99.99
        fair_under = round(1 / p_under, 2) if p_under > 0.01 else 99.99
        result["fair_odds"][line] = (fair_over, fair_under)

    return result


# 裸联赛名(不带"国家 - 联赛"分隔符)到 match_results 里真实(country, league_slug)的映射。
# 只覆盖有把握、样本量大的全球性联赛——不是每个联赛名变体都往这里塞，长尾的中文
# 描述性联赛名(如"智利萨耶萨篮球联赛")留给tier=3全局兜底+下游"无独立模型支撑排除"，
# 不做跨语言模糊匹配（2026-07-12，WNBA/NBA夏季联赛"大球"推荐排查发现，match_results
# 里实际有184场真实WNBA比赛(country='usa',league_slug='wnba')，但country_hint解析
# 拿的是整个"WNBA"字符串，查不到真实数据，白白摔到全局兜底——WNBA不该被排除）
_BARE_LEAGUE_ALIASES = {
    "wnba": ("usa", "wnba"),
    "wnba 美国女子职业篮球联赛": ("usa", "wnba"),
    "nba": ("usa", "nba"),
    # "NBA 夏季联赛"故意不加别名：match_results里没有夏季联赛的历史数据，
    # 加了别名也查不到东西，仍然会摔到tier=3，跟现在的行为一致，如实反映"没有数据"
    # Puerto Rico联赛显示名"Superior Nacional"和爬虫实际用的league_slug="bsn"
    # （Baloncesto Superior Nacional缩写）对不上，通用解析会查不到精确联赛只能退到
    # tier=2同国家兜底——该国目前只抓了bsn这一个篮球联赛，tier=2实际不影响结果，
    # 但加上别名让它稳定拿tier=1，避免以后该国多抓一个联赛时被稀释（2026-07-16复盘发现）
    "puerto rico - superior nacional": ("puerto-rico", "bsn"),

    # 2026-07-26全量70个生产篮球联赛复核：确认2个安全的同款slug对不上问题
    # (均已验证match_results里有充足真实样本，不是瞎猜)。France - Nationale 1
    # (14条推荐)和Uruguay - Liga Femenina(9条推荐)也在tier=3/2兜底名单里，
    # 但naive拆分对应到的"lnb"(107场)/"liga-uruguaya"(109场)分别疑似是
    # 法国男子高级别联赛/乌拉圭男子联赛，跟"Nationale 1"(法国第三级别)、
    # "Liga Femenina"(女子联赛)不是同一个赛事，没有把握不敢瞎加别名，
    # 保持如实排除。
    "turkey - super league":  ("turkey", "super-lig"),
    "germany - bundesliga":   ("germany", "bbl"),
}


def compute_basketball_probs(unified_id: str, fetch_date: str) -> dict:
    """
    为一场篮球比赛计算正态分布大小球概率
    """
    with engine.connect() as conn:
        match = conn.execute(text("""
            SELECT league_name FROM unified_matches
            WHERE unified_id = :uid AND fetch_date = :fd
        """), {"uid": unified_id, "fd": fetch_date}).fetchone()

        if not match:
            return {}

        league_name = match[0] or ""
        _alias = _BARE_LEAGUE_ALIASES.get(league_name.strip().lower())
        if _alias:
            country_hint, league_hint = _alias
        else:
            parts = league_name.split(" - ") if " - " in league_name else [league_name, ""]
            # 国家名也做空格→连字符归一化（此前只对联赛名做了，国家名漏了，导致
            # "Puerto Rico"解析成"puerto rico"但match_results存的是"puerto-rico"，
            # 精确匹配不上，尽管该国家其实有181场真实数据）
            country_hint = parts[0].strip().lower().replace(" ", "-")
            league_hint = parts[1].strip().lower().replace(" ", "-") if len(parts) > 1 else ""

        stats = _get_league_stats(conn, country_hint, league_hint)

    probs = basketball_total_probs(stats["avg_total"], stats["std_total"])

    return {
        "unified_id": unified_id,
        "fetch_date": fetch_date,
        "league": league_name,
        "avg_total": round(stats["avg_total"], 1),
        "std_total": round(stats["std_total"], 1),
        "sample_size": stats["n_games"],
        "tier": stats["tier"],
        "probs": probs,
    }


def batch_basketball(fetch_date: str) -> list:
    """
    批量计算当日所有篮球比赛的正态分布概率
    """
    with engine.connect() as conn:
        matches = conn.execute(text("""
            SELECT DISTINCT um.unified_id, um.league_name, um.sport_code
            FROM unified_matches um
            JOIN consensus_odds co ON um.unified_id = co.unified_id
            WHERE um.fetch_date = :fd
              AND co.market = 'total'
              AND um.sport_code IN ('Basketball', 'basketball')
        """), {"fd": fetch_date}).fetchall()

    results = []
    for uid, league, sport in matches:
        try:
            probs = compute_basketball_probs(uid, fetch_date)
            if probs:
                results.append(probs)
        except Exception:
            continue

    return results


def basketball_report(fetch_date: str = None, limit: int = 20):
    """输出篮球正态分布模型报告"""
    if fetch_date is None:
        from datetime import datetime
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    results = batch_basketball(fetch_date)
    if not results:
        print("  No basketball matches with total odds found for analysis")
        return results

    with engine.connect() as conn:
        for r in results[:limit]:
            uid = r["unified_id"]
            actual = conn.execute(text("""
                SELECT outcome, consensus_odds FROM consensus_odds
                WHERE unified_id = :uid AND market = 'total' AND fetch_date = :fd
            """), {"uid": uid, "fd": fetch_date}).fetchall()

            actual_over = next((o for _, o, out in actual if out == "over"), None)

            if actual_over:
                # Find the closest threshold line to actual
                fair_odds = r["probs"]["fair_odds"]
                closest_line = min(fair_odds.keys(), key=lambda x: abs(x - actual_over * 50))
                fair_o, fair_u = fair_odds[closest_line]
                edge = fair_o / actual_over - 1 if actual_over > 0 else 0
                edge_icon = "🔥" if edge > 0.10 else ("✅" if edge > 0 else "❌")
                print(f"  {r['league'][:30]:30} | avg={r['avg_total']:.0f} std={r['std_total']:.0f} | "
                      f"line={closest_line} fair={fair_o:.2f} vs actual={actual_over:.2f} | "
                      f"edge={edge*100:+.1f}% {edge_icon}")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()

    if args.demo:
        print("=== Basketball Normal Distribution Demo ===")
        # NBA averages
        probs = basketball_total_probs(222.0, 19.9, 
                    thresholds=[200.5, 210.5, 215.5, 220.5, 225.5, 230.5])
        print(f"  NBA: avg=222.0, std=19.9")
        for line in sorted(probs["fair_odds"].keys()):
            fo, fu = probs["fair_odds"][line]
            po = probs["over"][line]
            pu = probs["under"][line]
            print(f"  Line {line:>6}: P(Over)={po:.3f} (fair {fo:.2f}), P(Under)={pu:.3f} (fair {fu:.2f})")
    else:
        results = basketball_report(args.date)
        if results:
            print(f"\n  Total: {len(results)} matches analyzed")
