# -*- coding: utf-8 -*-
# 04_2_Football_xG_Module.py — 足球 xG 三源融合特征计算
# 数据优先级:
#   1. understat_xg_teams  (StatsBomb xG 模型, 6大欧洲联赛, 最精准)
#   2. fbref_xg_teams      (StatsBomb 历史, 40+联赛)
#   3. sofascore_xg        (实时场次, 按队汇总均值)
#   4. football_matches    (历史比分均值, 兜底)
# 输出表: football_xg_stats (league, team, xg_off, xg_def)

import sys
import logging
import argparse

import pandas as pd
from sqlalchemy import create_engine, text

import env_setup
from config import DB_ENGINE_URL
from db_utils import exec_ddl

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

engine = create_engine(DB_ENGINE_URL)

# ── 联赛名称标准化映射 ────────────────────────────────────────────────────────
# Understat / FBref slug → API-Sports 联赛名（football_matches.league 字段）
SLUG_TO_LEAGUE = {
    "premier_league": ["Premier League", "England - Premier League", "EPL"],
    "laliga":         ["La Liga", "Spain - La Liga", "LaLiga"],
    "bundesliga":     ["Bundesliga", "Germany - Bundesliga", "Germany Bundesliga"],
    "serie_a":        ["Serie A", "Italy - Serie A"],
    "ligue_1":        ["Ligue 1", "France - Ligue 1"],
    "rfpl":           ["Russian Premier League", "Russia - Premier League"],
    "mls":            ["MLS", "USA - MLS", "Major League Soccer"],
    "j1":             ["J1 League", "Japan - J League", "J League"],
    "championship":   ["Championship", "England - Championship"],
    "eredivisie":     ["Eredivisie", "Netherlands - Eredivisie"],
    "liga_portugal":  ["Primeira Liga", "Portugal - Primeira Liga", "Liga Portugal"],
    "csl":            ["Chinese Super League", "China - Super League", "CSL"],
    "k_league_1":     ["K League 1", "South Korea - K League 1"],
    "serie_a_br":     ["Serie A", "Brazil - Serie A"],
    "liga_mx":        ["Liga MX", "Mexico - Liga MX"],
}

# 反向映射: 任意联赛名 → slug
_LEAGUE_TO_SLUG: dict = {}
for slug, names in SLUG_TO_LEAGUE.items():
    for n in names:
        _LEAGUE_TO_SLUG[n.lower()] = slug


def _to_slug(league_name: str) -> str | None:
    return _LEAGUE_TO_SLUG.get(league_name.lower().strip())


def _table_exists(tbl_name: str) -> bool:
    with engine.connect() as conn:
        r = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
            {"n": tbl_name},
        )
        return r.fetchone() is not None


# ── 四个数据源读取 ────────────────────────────────────────────────────────────

def _load_understat() -> pd.DataFrame:
    """加载 understat_xg_teams 最新赛季数据。"""
    if not _table_exists("understat_xg_teams"):
        return pd.DataFrame()
    try:
        df = pd.read_sql(
            """SELECT league_slug, team_name, xg_off, xg_def
               FROM understat_xg_teams
               WHERE season = (SELECT MAX(season) FROM understat_xg_teams)
               AND matches_played >= 5""",
            engine,
        )
        df["source"] = "understat"
        log.info(f"  Understat: {len(df)} 条")
        return df
    except Exception as e:
        log.warning(f"  Understat 读取失败: {e}")
        return pd.DataFrame()


def _load_fbref() -> pd.DataFrame:
    """加载 fbref_xg_teams 最新赛季数据。"""
    if not _table_exists("fbref_xg_teams"):
        return pd.DataFrame()
    try:
        df = pd.read_sql(
            """SELECT league_slug, team_name, xg_off, xg_def
               FROM fbref_xg_teams
               WHERE season = (SELECT MAX(season) FROM fbref_xg_teams)
               AND matches_played >= 5""",
            engine,
        )
        df["source"] = "fbref"
        log.info(f"  FBref: {len(df)} 条")
        return df
    except Exception as e:
        log.warning(f"  FBref 读取失败: {e}")
        return pd.DataFrame()


def _load_sofascore() -> pd.DataFrame:
    """从 sofascore_xg 按队汇总场均 xG，仅取近90天数据。"""
    if not _table_exists("sofascore_xg"):
        return pd.DataFrame()
    try:
        # 主队统计
        sql_home = """
            SELECT league_name, home_team_name AS team_name,
                   AVG(home_xg) AS xg_off, AVG(away_xg) AS xg_def,
                   COUNT(*) AS cnt
            FROM sofascore_xg
            WHERE home_xg IS NOT NULL
              AND date(fetch_date) >= date('now', '-90 days')
            GROUP BY league_name, home_team_name
            HAVING cnt >= 3
        """
        # 客队统计
        sql_away = """
            SELECT league_name, away_team_name AS team_name,
                   AVG(away_xg) AS xg_off, AVG(home_xg) AS xg_def,
                   COUNT(*) AS cnt
            FROM sofascore_xg
            WHERE away_xg IS NOT NULL
              AND date(fetch_date) >= date('now', '-90 days')
            GROUP BY league_name, away_team_name
            HAVING cnt >= 3
        """
        df_h = pd.read_sql(sql_home, engine)
        df_a = pd.read_sql(sql_away, engine)

        # 合并主客场均值
        combined = pd.concat([df_h, df_a], ignore_index=True)
        if combined.empty:
            return pd.DataFrame()

        agg = combined.groupby(["league_name", "team_name"]).agg(
            xg_off=("xg_off", "mean"),
            xg_def=("xg_def", "mean"),
        ).reset_index().rename(columns={"league_name": "league_slug"})

        # league_name 直接当 slug 用（后续统一通过 _to_slug 处理）
        agg["source"] = "sofascore"
        log.info(f"  SofaScore: {len(agg)} 条")
        return agg
    except Exception as e:
        log.warning(f"  SofaScore 读取失败: {e}")
        return pd.DataFrame()


def _load_historical() -> pd.DataFrame:
    """从 football_matches 历史比分计算场均进失球（兜底）。"""
    if not _table_exists("football_matches"):
        return pd.DataFrame()
    try:
        df = pd.read_sql(
            "SELECT league, home_team, away_team, home_score, away_score FROM football_matches",
            engine,
        )
        df = df.dropna(subset=["home_score", "away_score"])
        df["home_score"] = pd.to_numeric(df["home_score"], errors="coerce")
        df["away_score"] = pd.to_numeric(df["away_score"], errors="coerce")
        df = df.dropna()

        home_agg = df.groupby(["league", "home_team"]).agg(
            xg_off=("home_score", "mean"),
            xg_def=("away_score", "mean"),
        ).reset_index().rename(columns={"home_team": "team_name", "league": "league_slug"})

        away_agg = df.groupby(["league", "away_team"]).agg(
            xg_off_a=("away_score", "mean"),
            xg_def_a=("home_score", "mean"),
        ).reset_index().rename(columns={"away_team": "team_name", "league": "league_slug"})

        merged = pd.merge(home_agg, away_agg, on=["league_slug", "team_name"], how="outer")
        merged["xg_off"] = (merged["xg_off"].fillna(0) + merged["xg_off_a"].fillna(0)) / 2
        merged["xg_def"] = (merged["xg_def"].fillna(0) + merged["xg_def_a"].fillna(0)) / 2
        merged["source"] = "historical"
        result = merged[["league_slug", "team_name", "xg_off", "xg_def", "source"]].dropna(
            subset=["team_name"]
        )
        log.info(f"  历史比分: {len(result)} 条")
        return result
    except Exception as e:
        log.warning(f"  历史比分读取失败: {e}")
        return pd.DataFrame()


# ── 融合逻辑 ─────────────────────────────────────────────────────────────────

def _build_team_key(league_slug: str, team_name: str) -> str:
    return f"{league_slug.lower()}::{team_name.lower().strip()}"


def merge_xg_sources() -> pd.DataFrame:
    """
    按优先级合并四个数据源，每支球队取最高优先级有效值。
    优先级: understat > fbref > sofascore > historical
    """
    log.info("加载各数据源 xG...")
    sources = [
        ("understat", _load_understat()),
        ("fbref",     _load_fbref()),
        ("sofascore", _load_sofascore()),
        ("historical",_load_historical()),
    ]

    # 建立优先级字典: key → (xg_off, xg_def, source, league_slug, team_name)
    priority_map: dict = {}  # key → dict

    for source_name, df in sources:
        if df.empty:
            continue
        for _, row in df.iterrows():
            slug      = str(row.get("league_slug", "")).strip()
            team      = str(row.get("team_name",   "")).strip()
            xg_off    = float(row.get("xg_off", 0) or 0)
            xg_def    = float(row.get("xg_def", 0) or 0)

            if not slug or not team:
                continue
            if xg_off <= 0 and xg_def <= 0:
                continue

            key = _build_team_key(slug, team)
            if key not in priority_map:   # 先到先得（已按优先级排序）
                priority_map[key] = {
                    "league_slug": slug,
                    "team_name":   team,
                    "xg_off":      round(xg_off, 4),
                    "xg_def":      round(xg_def, 4),
                    "source":      source_name,
                }

    if not priority_map:
        log.warning("所有数据源均无有效 xG 数据")
        return pd.DataFrame()

    df_merged = pd.DataFrame(list(priority_map.values()))
    log.info(f"融合后共 {len(df_merged)} 条 xG 记录")

    # 统计来源分布
    src_counts = df_merged["source"].value_counts().to_dict()
    log.info(f"  来源分布: {src_counts}")

    return df_merged


# ── 联赛名还原 ────────────────────────────────────────────────────────────────

def _slug_to_display_league(slug: str) -> str:
    """slug → 显示用联赛名（取映射第一个）。"""
    names = SLUG_TO_LEAGUE.get(slug)
    if names:
        return names[0]
    return slug  # 无映射时直接用 slug


def save_xg_to_db(df_merged: pd.DataFrame):
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS football_xg_stats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league    VARCHAR(100),
        team      VARCHAR(100),
        xg_off    FLOAT,
        xg_def    FLOAT,
        source    VARCHAR(20),
        update_time DATETIME DEFAULT CURRENT_TIMESTAMP
    )""")

    # 添加 source 列（若表已存在且无此列，静默忽略报错）
    try:
        exec_ddl(engine, "ALTER TABLE football_xg_stats ADD COLUMN source VARCHAR(20)")
    except Exception:
        pass

    # 构造输出行
    rows = []
    for _, row in df_merged.iterrows():
        slug  = str(row["league_slug"])
        team  = str(row["team_name"])
        league_display = _slug_to_display_league(slug)
        rows.append({
            "league":  league_display,
            "team":    team,
            "xg_off":  float(row["xg_off"]),
            "xg_def":  float(row["xg_def"]),
            "source":  str(row.get("source", "")),
        })

    if not rows:
        log.warning("无数据可写入 football_xg_stats")
        return

    df_out = pd.DataFrame(rows)
    df_out.to_sql("football_xg_stats", engine, if_exists="replace", index=False)
    log.info(f"✅ football_xg_stats 写入 {len(rows)} 条（三源融合）")


# ── 查询接口（供其他模块调用）────────────────────────────────────────────────

def get_team_xg(league: str, team: str) -> dict:
    """
    按联赛名和队名查询 xG，返回 {'xg_off': float, 'xg_def': float, 'source': str}。
    未命中时返回默认值 {xg_off: 1.3, xg_def: 1.3}。
    """
    DEFAULT = {"xg_off": 1.3, "xg_def": 1.3, "source": "default"}
    if not _table_exists("football_xg_stats"):
        return DEFAULT
    try:
        with engine.connect() as conn:
            r = conn.execute(
                text("""SELECT xg_off, xg_def, source
                        FROM football_xg_stats
                        WHERE LOWER(league) = LOWER(:l) AND LOWER(team) = LOWER(:t)
                        LIMIT 1"""),
                {"l": league, "t": team},
            ).fetchone()
        if r:
            return {"xg_off": r[0], "xg_def": r[1], "source": r[2] or ""}
    except Exception:
        pass
    return DEFAULT


# ── 主入口 ───────────────────────────────────────────────────────────────────

def calc_and_save():
    df = merge_xg_sources()
    if df.empty:
        log.warning("⚠️ 无 xG 数据，请先运行 10_understat_xg_scraper.py / 11_fbref_xg_scraper.py")
        return
    save_xg_to_db(df)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-scrape", action="store_true",
                        help="只做融合计算，不触发上游爬虫")
    args = parser.parse_args()
    calc_and_save()
