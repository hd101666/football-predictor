# -*- coding: utf-8 -*-
# import_corner_stats.py — 从 fd_matches 计算角球攻防统计
# 写入: corner_team_stats, corner_league_baseline
# 用法: python -X utf8 import_corner_stats.py

import sys, re, logging, unicodedata
import numpy as np
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from sqlalchemy import create_engine, text

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

import env_setup
from config import DB_ENGINE_URL
from db_utils import exec_ddl

engine = create_engine(DB_ENGINE_URL, connect_args={"timeout": 60})

# ── 赛季字符串 → 结束年份（用于排序取最近 N 赛季）──────────────────────────
def _season_end_year(s: str) -> int:
    """
    '2526' → 2026,  '25-26' → 2026
    '2425' → 2025,  '24-25' → 2025
    '2324' → 2024,  '23-24' → 2024
    '2016' → 2016 (单年)
    """
    s = str(s).strip()
    # xx-xx 或 xxxx-xx 格式
    m = re.match(r"(\d{2,4})-(\d{2,4})", s)
    if m:
        end = m.group(2)
        return int(end) + 2000 if len(end) == 2 else int(end)
    # 4位粘连 '2526'
    if len(s) == 4 and s.isdigit():
        return int(s[2:]) + 2000
    # 单年
    try:
        y = int(s)
        return y if y > 100 else y + 2000
    except ValueError:
        return 0


def _recent_seasons(seasons: list, n: int = 2) -> list:
    return sorted(set(seasons), key=_season_end_year, reverse=True)[:n]


# Bug修复(2026-08-26)：corner_team_stats/corner_league_baseline的computed_at一直
# 停在2026-06-13——本脚本原来只读fd_corner_stats(停更到2023-12-31)+fd_matches
# (2026-08-10一次性CSV导入，停在2026-05-31)，这两个源都是静态历史快照，不管这个
# 脚本重跑多少次、排不排进每日调度，"最近赛季"取到的永远是同一批旧数据，角球模型
# 完全不知道过去两个多月球队阵容/状态的变化，直接影响真钱的角球正式推荐单
# (corner_recommendations)。fotmob_match_team_stats.corners是43号FotMob爬虫
# 每天抓的逐场真实数据，一直更新到最新——现在把它加进来做"当前赛季"补充源，
# 不受_recent_seasons()两季筛选影响(本身就只有近几个月窗口，天然是新的)，
# 跟fd历史数据一起喂给球队统计，让模型重新有能力感知近期状态。
# 联赛白名单(corner_model.py的LEAGUE_WHITELIST，19/20个códe在FotMob里能找到
# 精确对应的league_name，EC=英格兰National League没有，保留旧行为不受影响)。
FD_CODE_TO_FOTMOB_LEAGUE = {
    "E0": "England - Premier League",
    "E1": "England - Championship",
    "E2": "England - League One",
    "E3": "England - League Two",
    "SC0": "Scotland - Premiership",
    "D1": "Germany - Bundesliga",
    "D2": "Germany - 2. Bundesliga",
    "SP1": "Spain - LaLiga",
    "SP2": "Spain - LaLiga2",
    "I1": "Italy - Serie A",
    "I2": "Italy - Serie B",
    "F1": "France - Ligue 1",
    "F2": "France - Ligue 2",
    "N1": "Netherlands - Eredivisie",
    "B1": "Belgium - First Division A",
    "P1": "Portugal - Primeira Liga",
    "T1": "Turkey - Super Lig",
    "G1": "Greece - Super League 1",
    # "EC": 英格兰National League，FotMob没有精确对应的联赛名，暂不补充
}


# Bug修复(2026-08-26第二版)：FotMob当季数据接入后发现同一支球队因为拼法不同
# 被拆成两条记录——如"Olympiacos"(fd数据)vs"Olympiakos"(FotMob)、"Fenerbahçe"
# (fd)vs"Fenerbahce"(FotMob，无变音符)，样本被拆散、统计力被稀释。跟
# 21_auto_settle.py._normalize()/_fuzzy_match()同一套思路(去变音符+去后缀+
# 模糊匹配)独立实现一份小的，不跨脚本import(避免带出21_auto_settle.py整个
# 模块的引擎初始化等副作用，本脚本只需要这两个纯字符串函数)。
def _normalize_team_name(name: str) -> str:
    if not name:
        return ""
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    n = n.lower().strip()
    for suffix in (" fc", " cf", " sc", " ac", " bc", " 1920", " 1899"):
        n = n.replace(suffix, "")
    n = re.sub(r"[^a-z0-9]", "", n)
    return n


def _fuzzy_match_team_name(a: str, b: str, threshold: float = 0.82) -> bool:
    na, nb = _normalize_team_name(a), _normalize_team_name(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def _canonicalize_fotmob_teams(fotmob_games: list, fd_team_names: set) -> list:
    """把fotmob_games里的球队名尽量对齐到fd_team_names(同联赛已有的历史队名集合)，
    对上的用fd这边的拼法(保证跟历史样本合并成同一支球队，不拆成两条)；对不上
    的(fd数据没覆盖到的新队/联赛覆盖缺口)保留FotMob原名，新建一条记录，不丢数据。
    每个fotmob名字只查一次+缓存，联赛内球队数通常几十支，O(n*m)开销可忽略。"""
    if not fd_team_names:
        return fotmob_games
    cache: dict = {}

    def _resolve(name: str) -> str:
        if name in cache:
            return cache[name]
        for fd_name in fd_team_names:
            if _fuzzy_match_team_name(name, fd_name):
                cache[name] = fd_name
                return fd_name
        cache[name] = name
        return name

    out = []
    for home, away, hc, ac, h_sot, a_sot in fotmob_games:
        out.append((_resolve(home), _resolve(away), hc, ac, h_sot, a_sot))
    return out


def load_fotmob_current_season(engine) -> dict:
    """按fd-style league_code分组的FotMob当季真实角球数据，(home,away,hc,ac,h_sot,a_sot)
    元组列表，结构跟fd_corner_stats/fd_matches那批完全一致，可以直接extend进
    games_list一起参与统计。取不到角球数据(corners IS NULL)的场次跳过，不伪造。"""
    fotmob_leagues = list(FD_CODE_TO_FOTMOB_LEAGUE.values())
    if not fotmob_leagues:
        return {}
    placeholders = ",".join(f":lg{i}" for i in range(len(fotmob_leagues)))
    params = {f"lg{i}": lg for i, lg in enumerate(fotmob_leagues)}
    with engine.connect() as conn:
        rows = conn.execute(text(f"""
            SELECT fm.league_name, fm.home_team, fm.away_team,
                   fh.corners, fa.corners, fh.shots_on_target, fa.shots_on_target
            FROM fotmob_matches fm
            JOIN fotmob_match_team_stats fh ON fh.match_id = fm.match_id AND fh.side = 'home'
            JOIN fotmob_match_team_stats fa ON fa.match_id = fm.match_id AND fa.side = 'away'
            WHERE fh.corners IS NOT NULL AND fa.corners IS NOT NULL
              AND fm.league_name IN ({placeholders})
        """), params).fetchall()

    league_name_to_code = {v: k for k, v in FD_CODE_TO_FOTMOB_LEAGUE.items()}
    by_code: dict = defaultdict(list)
    for league_name, home, away, hc, ac, h_sot, a_sot in rows:
        lc = league_name_to_code.get(league_name)
        if not lc:
            continue
        by_code[lc].append((home, away, float(hc), float(ac), h_sot or 0, a_sot or 0))
    return by_code


# ── DDL ──────────────────────────────────────────────────────────────────────
def ensure_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS corner_team_stats (
            league_code          TEXT,
            league_name          TEXT,
            team                 TEXT,
            games                INTEGER,
            games_home           INTEGER,
            games_away           INTEGER,
            avg_crn_for          REAL,
            avg_crn_against      REAL,
            std_crn_for          REAL,
            avg_crn_for_home     REAL,
            avg_crn_for_away     REAL,
            avg_crn_against_home REAL,
            avg_crn_against_away REAL,
            avg_sot_for          REAL,
            avg_sot_against      REAL,
            over_8_5_pct         REAL,
            over_9_5_pct         REAL,
            over_10_5_pct        REAL,
            over_11_5_pct        REAL,
            over_12_5_pct        REAL,
            attack_rating        REAL,
            defense_rating       REAL,
            seasons_used         TEXT,
            computed_at          TEXT
        )
    """)
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS corner_league_baseline (
            league_code   TEXT PRIMARY KEY,
            league_name   TEXT,
            games         INTEGER,
            avg_total     REAL,
            median_total  REAL,
            std_total     REAL,
            avg_home_crn  REAL,
            avg_away_crn  REAL,
            home_adv_crn  REAL,
            over_8_5_pct  REAL,
            over_9_5_pct  REAL,
            over_10_5_pct REAL,
            over_11_5_pct REAL,
            over_12_5_pct REAL,
            seasons_used  TEXT,
            computed_at   TEXT
        )
    """)


# ── 核心计算 ─────────────────────────────────────────────────────────────────
def compute_all():
    log.info("  📐 读取角球数据（fd_corner_stats + fd_matches 补充）...")
    with engine.connect() as conn:
        # 主数据源：fd_corner_stats（角球数据更完整）
        rows_primary = conn.execute(text("""
            SELECT league_code, league_name, season,
                   home_team, away_team,
                   hc, ac,
                   hst, ast,
                   0 as hr, 0 as ar
            FROM fd_corner_stats
            WHERE hc IS NOT NULL
              AND ac IS NOT NULL
        """)).fetchall()
        # 补充数据源：fd_matches 中 fd_corner_stats 没有的联赛
        rows_supplement = conn.execute(text("""
            SELECT m.league_code, m.league_name, m.season,
                   m.home_team, m.away_team,
                   m.home_corners, m.away_corners,
                   m.home_shots_target, m.away_shots_target,
                   m.home_red, m.away_red
            FROM fd_matches m
            WHERE m.home_corners IS NOT NULL
              AND m.away_corners IS NOT NULL
              AND m.league_code NOT IN (
                  SELECT DISTINCT league_code FROM fd_corner_stats
                  WHERE hc IS NOT NULL AND ac IS NOT NULL
              )
        """)).fetchall()
        rows = rows_primary + rows_supplement
    log.info(f"  全量: {len(rows_primary)} (主) + {len(rows_supplement)} (补充) = {len(rows)} 场")

    fotmob_extra = load_fotmob_current_season(engine)
    log.info(f"  FotMob当季补充: {sum(len(v) for v in fotmob_extra.values())} 场 "
             f"覆盖 {len(fotmob_extra)} 个联赛（见2026-08-26修复说明）")

    # ── 按联赛分组 ───────────────────────────────────────────────────────────
    # by_league[lc] = {season: [(home, away, hc, ac, h_sot, a_sot, h_red, a_red)]}
    by_league: dict = defaultdict(lambda: defaultdict(list))
    lc_name: dict = {}
    for lc, ln, season, home, away, hc, ac, h_sot, a_sot, h_red, a_red in rows:
        by_league[lc][season].append((home, away, hc, ac, h_sot or 0, a_sot or 0))
        lc_name[lc] = ln or lc

    team_rows    = []
    baseline_rows = []
    now_str = datetime.utcnow().isoformat()

    all_league_codes = set(by_league.keys()) | set(fotmob_extra.keys())
    for lc in all_league_codes:
        seasons_data = by_league.get(lc, {})
        ln = lc_name.get(lc) or FD_CODE_TO_FOTMOB_LEAGUE.get(lc, lc)
        recent = _recent_seasons(list(seasons_data.keys()), n=2)
        games_list = []
        for s in recent:
            games_list.extend(seasons_data[s])

        _fotmob_games_raw = fotmob_extra.get(lc, [])
        _fd_team_names = {t for g in games_list for t in (g[0], g[1])}
        _fotmob_games = _canonicalize_fotmob_teams(_fotmob_games_raw, _fd_team_names)
        games_list.extend(_fotmob_games)

        if len(games_list) < 10:
            continue

        seasons_str = ",".join(recent)
        if _fotmob_games:
            seasons_str = (seasons_str + "+FotMob当季" if seasons_str else "FotMob当季")

        # ── 联赛基准 ─────────────────────────────────────────────────────────
        totals  = np.array([hc + ac for _, _, hc, ac, _, _ in games_list], dtype=float)
        hc_arr  = np.array([hc      for _, _, hc, ac, _, _ in games_list], dtype=float)
        ac_arr  = np.array([ac      for _, _, hc, ac, _, _ in games_list], dtype=float)

        league_avg_total    = float(totals.mean())
        league_avg_home_crn = float(hc_arr.mean())
        league_avg_away_crn = float(ac_arr.mean())

        baseline_rows.append({
            "league_code":   lc,
            "league_name":   ln,
            "games":         len(totals),
            "avg_total":     round(league_avg_total, 4),
            "median_total":  round(float(np.median(totals)), 4),
            "std_total":     round(float(totals.std(ddof=1)), 4),
            "avg_home_crn":  round(league_avg_home_crn, 4),
            "avg_away_crn":  round(league_avg_away_crn, 4),
            "home_adv_crn":  round(league_avg_home_crn - league_avg_away_crn, 4),
            "over_8_5_pct":  round(float((totals > 8.5).mean()), 4),
            "over_9_5_pct":  round(float((totals > 9.5).mean()), 4),
            "over_10_5_pct": round(float((totals > 10.5).mean()), 4),
            "over_11_5_pct": round(float((totals > 11.5).mean()), 4),
            "over_12_5_pct": round(float((totals > 12.5).mean()), 4),
            "seasons_used":  seasons_str,
            "computed_at":   now_str,
        })

        # ── 球队统计 ─────────────────────────────────────────────────────────
        team_stats: dict = defaultdict(lambda: {
            "crn_for": [], "crn_ag": [], "total": [],
            "crn_for_h": [], "crn_ag_h": [],
            "crn_for_a": [], "crn_ag_a": [],
            "sot_for": [], "sot_ag": [],
        })

        for home, away, hc, ac, h_sot, a_sot in games_list:
            total = hc + ac
            # home side
            h = team_stats[home]
            h["crn_for"].append(hc); h["crn_ag"].append(ac)
            h["crn_for_h"].append(hc); h["crn_ag_h"].append(ac)
            h["sot_for"].append(h_sot); h["sot_ag"].append(a_sot)
            h["total"].append(total)
            # away side
            a = team_stats[away]
            a["crn_for"].append(ac); a["crn_ag"].append(hc)
            a["crn_for_a"].append(ac); a["crn_ag_a"].append(hc)
            a["sot_for"].append(a_sot); a["sot_ag"].append(h_sot)
            a["total"].append(total)

        for team, s in team_stats.items():
            n = len(s["crn_for"])
            if n < 3:
                continue
            cf_arr = np.array(s["crn_for"], dtype=float)
            ca_arr = np.array(s["crn_ag"],  dtype=float)
            tot_arr = np.array(s["total"],  dtype=float)

            avg_cf = float(cf_arr.mean())
            avg_ca = float(ca_arr.mean())

            # 攻防评级：相对联赛均值（>1 = 强，<1 = 弱）
            attack_r  = round(avg_cf / league_avg_home_crn, 4) if league_avg_home_crn > 0 else 1.0
            defense_r = round(avg_ca / league_avg_away_crn, 4) if league_avg_away_crn > 0 else 1.0

            def _safe_mean(lst): return round(float(np.mean(lst)), 4) if lst else None

            team_rows.append({
                "league_code":          lc,
                "league_name":          ln,
                "team":                 team,
                "games":                n,
                "games_home":           len(s["crn_for_h"]),
                "games_away":           len(s["crn_for_a"]),
                "avg_crn_for":          round(avg_cf, 4),
                "avg_crn_against":      round(avg_ca, 4),
                "std_crn_for":          round(float(cf_arr.std(ddof=1)) if n > 1 else 0.0, 4),
                "avg_crn_for_home":     _safe_mean(s["crn_for_h"]),
                "avg_crn_for_away":     _safe_mean(s["crn_for_a"]),
                "avg_crn_against_home": _safe_mean(s["crn_ag_h"]),
                "avg_crn_against_away": _safe_mean(s["crn_ag_a"]),
                "avg_sot_for":          _safe_mean(s["sot_for"]),
                "avg_sot_against":      _safe_mean(s["sot_ag"]),
                "over_8_5_pct":         round(float((tot_arr > 8.5).mean()), 4),
                "over_9_5_pct":         round(float((tot_arr > 9.5).mean()), 4),
                "over_10_5_pct":        round(float((tot_arr > 10.5).mean()), 4),
                "over_11_5_pct":        round(float((tot_arr > 11.5).mean()), 4),
                "over_12_5_pct":        round(float((tot_arr > 12.5).mean()), 4),
                "attack_rating":        attack_r,
                "defense_rating":       defense_r,
                "seasons_used":         seasons_str,
                "computed_at":          now_str,
            })

        log.info(f"  {ln:<35} 近{len(recent)}季={len(games_list)}场  "
                 f"球队={len([t for t in team_stats if len(team_stats[t]['crn_for'])>=3])}  "
                 f"场均={round(league_avg_total,2)}  "
                 f"主{round(league_avg_home_crn,2)}/客{round(league_avg_away_crn,2)}")

    return team_rows, baseline_rows


def write_all(team_rows: list, baseline_rows: list):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM corner_team_stats"))
        for r in team_rows:
            conn.execute(text("""
                INSERT INTO corner_team_stats
                  (league_code, league_name, team, games, games_home, games_away,
                   avg_crn_for, avg_crn_against, std_crn_for,
                   avg_crn_for_home, avg_crn_for_away,
                   avg_crn_against_home, avg_crn_against_away,
                   avg_sot_for, avg_sot_against,
                   over_8_5_pct, over_9_5_pct, over_10_5_pct,
                   over_11_5_pct, over_12_5_pct,
                   attack_rating, defense_rating,
                   seasons_used, computed_at)
                VALUES
                  (:league_code, :league_name, :team, :games, :games_home, :games_away,
                   :avg_crn_for, :avg_crn_against, :std_crn_for,
                   :avg_crn_for_home, :avg_crn_for_away,
                   :avg_crn_against_home, :avg_crn_against_away,
                   :avg_sot_for, :avg_sot_against,
                   :over_8_5_pct, :over_9_5_pct, :over_10_5_pct,
                   :over_11_5_pct, :over_12_5_pct,
                   :attack_rating, :defense_rating,
                   :seasons_used, :computed_at)
            """), r)

        conn.execute(text("DELETE FROM corner_league_baseline"))
        for r in baseline_rows:
            conn.execute(text("""
                INSERT INTO corner_league_baseline
                  (league_code, league_name, games,
                   avg_total, median_total, std_total,
                   avg_home_crn, avg_away_crn, home_adv_crn,
                   over_8_5_pct, over_9_5_pct, over_10_5_pct,
                   over_11_5_pct, over_12_5_pct,
                   seasons_used, computed_at)
                VALUES
                  (:league_code, :league_name, :games,
                   :avg_total, :median_total, :std_total,
                   :avg_home_crn, :avg_away_crn, :home_adv_crn,
                   :over_8_5_pct, :over_9_5_pct, :over_10_5_pct,
                   :over_11_5_pct, :over_12_5_pct,
                   :seasons_used, :computed_at)
            """), r)

    log.info(f"\n  ✅ corner_team_stats:      {len(team_rows)} 条")
    log.info(f"  ✅ corner_league_baseline: {len(baseline_rows)} 条")


def verify():
    with engine.connect() as conn:
        log.info("\n  corner_league_baseline（场均总角球降序）:")
        for r in conn.execute(text("""
            SELECT league_code, league_name, games, avg_total, std_total,
                   avg_home_crn, avg_away_crn, home_adv_crn,
                   over_10_5_pct
            FROM corner_league_baseline ORDER BY avg_total DESC
        """)).fetchall():
            log.info(f"    {r[0]:<5} {r[1]:<35} n={r[2]:<6} "
                     f"场均={r[3]:.2f}±{r[4]:.2f}  "
                     f"主{r[5]:.2f}/客{r[6]:.2f}(+{r[7]:.2f})  "
                     f"过10.5={r[8]*100:.1f}%")

        log.info("\n  corner_team_stats 攻击评级 TOP10（近2季）:")
        for r in conn.execute(text("""
            SELECT league_code, team, games, avg_crn_for, avg_crn_against,
                   attack_rating, defense_rating, over_10_5_pct
            FROM corner_team_stats
            ORDER BY attack_rating DESC LIMIT 10
        """)).fetchall():
            log.info(f"    {r[0]:<5} {r[1]:<28} GP={r[2]:<4} "
                     f"攻={r[3]:.2f} 守={r[4]:.2f}  "
                     f"攻评={r[5]:.3f} 守评={r[6]:.3f}  "
                     f"过10.5={r[7]*100:.1f}%")

        log.info("\n  corner_team_stats 防守评级 TOP10（最难攻）:")
        for r in conn.execute(text("""
            SELECT league_code, team, games, avg_crn_for, avg_crn_against,
                   attack_rating, defense_rating
            FROM corner_team_stats
            ORDER BY defense_rating ASC LIMIT 10
        """)).fetchall():
            log.info(f"    {r[0]:<5} {r[1]:<28} GP={r[2]:<4} "
                     f"攻={r[3]:.2f} 守={r[4]:.2f}  "
                     f"攻评={r[5]:.3f} 守评={r[6]:.3f}")


def run():
    log.info("=" * 60)
    log.info("  🚩 角球统计导入启动")
    log.info("=" * 60)

    ensure_tables()
    team_rows, baseline_rows = compute_all()

    log.info(f"\n  合计: 球队={len(team_rows)}, 联赛={len(baseline_rows)}")
    write_all(team_rows, baseline_rows)
    verify()

    log.info("\n✅ 角球统计导入完成")


if __name__ == "__main__":
    run()
