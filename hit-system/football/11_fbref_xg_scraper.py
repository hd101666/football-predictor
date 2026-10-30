# -*- coding: utf-8 -*-
# 11_fbref_xg_scraper.py — FBref xG 数据抓取（StatsBomb数据，40+联赛）
# 使用 nodriver 真实 Chrome 绕过 Cloudflare（同 22_fbref_scraper.py 方案）
# 表: fbref_xg_teams (队伍赛季 xG 汇总)

import io
import sys
import os
import time
import shutil
import random
import tempfile
import logging
import asyncio
import argparse
from datetime import datetime

import pandas as pd
from sqlalchemy import create_engine, MetaData

import env_setup
from config import DB_ENGINE_URL
from db_utils import exec_ddl, batch_upsert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

engine = create_engine(DB_ENGINE_URL)

BASE_URL = "https://fbref.com"

FBREF_LEAGUES = {
    9:   ("Premier-League",       "premier_league"),
    12:  ("La-Liga",              "laliga"),
    20:  ("Bundesliga",           "bundesliga"),
    11:  ("Serie-A",              "serie_a"),
    13:  ("Ligue-1",              "ligue_1"),
    22:  ("Major-League-Soccer",  "mls"),
    25:  ("J1-League",            "j1"),
    23:  ("Championship",         "championship"),
    32:  ("Eredivisie",           "eredivisie"),
    53:  ("Primeira-Liga",        "liga_portugal"),
    206: ("Chinese-Super-League", "csl"),
    308: ("K-League-1",           "k_league_1"),
    37:  ("Serie-A",              "serie_a_br"),
}

# ── nodriver 基础设施（复用 22_fbref_scraper.py 方案）────────────────────────

_browser = None
_tmp_profile_dir = None
_loop = None

_CF_MARKERS = [
    'Just a moment', '请稍候', '_cf_chl_opt',
    'cf-turnstile', 'challenges.cloudflare.com', '正在进行安全验证',
]

def _is_cf_challenge(html):
    check = html[:5000]
    return any(m in check for m in _CF_MARKERS)


def _make_profile_with_cookies():
    chrome_default = os.path.expanduser(
        r'~\AppData\Local\Google\Chrome\User Data\Default'
    )
    cookies_src = os.path.join(chrome_default, 'Network', 'Cookies')
    if not os.path.isfile(cookies_src):
        cookies_src = os.path.join(chrome_default, 'Cookies')
    if not os.path.isfile(cookies_src):
        return None
    tmp_dir = tempfile.mkdtemp(prefix='fbref_xg_chrome_')
    default_dir = os.path.join(tmp_dir, 'Default')
    os.makedirs(default_dir, exist_ok=True)
    try:
        shutil.copy2(cookies_src, os.path.join(default_dir, 'Cookies'))
        log.info(f'已复制 Chrome Cookies → {tmp_dir}')
    except Exception as e:
        log.warning(f'复制 Cookies 失败: {e}')
    return tmp_dir


async def _get_browser():
    global _browser, _tmp_profile_dir
    if _browser is None:
        import nodriver as uc
        _tmp_profile_dir = _make_profile_with_cookies()
        kwargs = dict(
            headless=False,
            window_size=(1920, 1080),
            no_sandbox=True,
            arguments=[
                '--disable-blink-features=AutomationControlled',
                '--disable-features=ChromeWhatsNewUI,LeaveThisPage',
            ],
        )
        if _tmp_profile_dir:
            kwargs['user_data_dir'] = _tmp_profile_dir
        _browser = await uc.start(**kwargs)
        log.info('nodriver 浏览器已启动（携带真实 Chrome Cookie）')
    return _browser


async def _shutdown_browser():
    global _browser, _tmp_profile_dir
    if _browser:
        try:
            _browser.stop()
        except Exception:
            pass
        _browser = None
    if _tmp_profile_dir and os.path.isdir(_tmp_profile_dir):
        try:
            shutil.rmtree(_tmp_profile_dir, ignore_errors=True)
        except Exception:
            pass
        _tmp_profile_dir = None


async def _get_html_async(url, min_size=50000):
    browser = await _get_browser()
    try:
        page = await browser.get(url)
        await asyncio.sleep(8)
        html = await page.get_content()

        wait_count = 0
        while _is_cf_challenge(html) and wait_count < 60:
            wait_count += 1
            if wait_count % 6 == 1:
                log.info(f'⏳ 等待 Cloudflare... (已等 {wait_count*5}s)')
            await asyncio.sleep(5)
            html = await page.get_content()

        if _is_cf_challenge(html):
            log.warning(f'✗ Cloudflare 验证超时: {url[:80]}')
            return None

        size_wait = 0
        while len(html) < min_size and size_wait < 18:
            size_wait += 1
            try:
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            except Exception:
                pass
            await asyncio.sleep(5)
            html = await page.get_content()

        log.info(f'  ✓ 页面加载 ({len(html)} chars): {url[:60]}')
        await asyncio.sleep(random.uniform(5, 9))
        return html
    except Exception as e:
        log.warning(f'请求失败: {e}')
        return None


def _get_html(url):
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(_get_html_async(url))


def _shutdown():
    global _loop
    if _loop and not _loop.is_closed():
        _loop.run_until_complete(_shutdown_browser())


# ── 表初始化 ─────────────────────────────────────────────────────────────────

def init_tables():
    exec_ddl(engine, """CREATE TABLE IF NOT EXISTS fbref_xg_teams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        league_slug    TEXT,
        season         TEXT,
        team_name      TEXT,
        matches_played INTEGER,
        xg_off         REAL,
        xg_def         REAL,
        npxg_off       REAL,
        npxg_def       REAL,
        update_time    TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(league_slug, season, team_name)
    )""")
    log.info("✅ FBref xG 数据表初始化完成")


# ── HTML 解析辅助 ─────────────────────────────────────────────────────────────

def _flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [
            "_".join(str(c).strip() for c in col if str(c) not in ("", "nan")).strip("_")
            for col in df.columns
        ]
    return df


def _find_col(df: pd.DataFrame, candidates: list):
    cols_lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand.lower() in cols_lower:
            return cols_lower[cand.lower()]
    for cand in candidates:
        for col in df.columns:
            if cand.lower() in col.lower():
                return col
    return None


def _parse_html_tables(html: str, table_id: str):
    try:
        tables = pd.read_html(io.StringIO(html), attrs={"id": table_id}, header=[0, 1])
    except Exception:
        try:
            tables = pd.read_html(io.StringIO(html), attrs={"id": table_id})
        except Exception as e:
            log.debug(f"read_html 失败({table_id}): {e}")
            return None
    if not tables:
        return None
    return _flatten_columns(tables[0])


def _extract_xg_rows(df_for, df_aga, league_slug: str, season: str, fetch_date: str) -> list:
    squad_col  = _find_col(df_for, ["Squad", "squad", "Team"])
    mp_col     = _find_col(df_for, ["MP_Playing Time", "MP", "Matches"])
    xg_f_col   = _find_col(df_for, ["Expected_xG", "xG_Expected", "xG"])
    npxg_f_col = _find_col(df_for, ["Expected_npxG", "npxG_Expected", "npxG"])

    if not squad_col or not xg_f_col:
        log.warning(f"  关键列缺失: squad={squad_col}, xG={xg_f_col}")
        log.warning(f"  可用列(全部{len(df_for.columns)}个): {list(df_for.columns)}")
        return []

    rows = []
    for _, row in df_for.iterrows():
        team = str(row.get(squad_col, "")).strip()
        if not team or team in ("Squad", "vs. Total", "nan"):
            continue
        try:
            mp = int(float(str(row.get(mp_col, 0) or 0))) if mp_col else 0
        except (ValueError, TypeError):
            mp = 0
        try:
            xg_off = float(str(row.get(xg_f_col, 0) or 0))
        except (ValueError, TypeError):
            xg_off = 0.0
        try:
            npxg_off = float(str(row.get(npxg_f_col, 0) or 0)) if npxg_f_col else 0.0
        except (ValueError, TypeError):
            npxg_off = 0.0

        xg_def = npxg_def = 0.0
        if df_aga is not None:
            sc_aga  = _find_col(df_aga, ["Squad", "squad", "Team"])
            xg_ac   = _find_col(df_aga, ["Expected_xG", "xG_Expected", "xG"])
            npxg_ac = _find_col(df_aga, ["Expected_npxG", "npxG_Expected", "npxG"])
            if sc_aga and xg_ac:
                match = df_aga[df_aga[sc_aga].astype(str).str.strip() == team]
                if not match.empty:
                    try:
                        xg_def = float(str(match.iloc[0][xg_ac] or 0))
                    except (ValueError, TypeError):
                        pass
                    if npxg_ac:
                        try:
                            npxg_def = float(str(match.iloc[0][npxg_ac] or 0))
                        except (ValueError, TypeError):
                            pass

        if mp > 0:
            xg_off   = round(xg_off   / mp, 4)
            xg_def   = round(xg_def   / mp, 4)
            npxg_off = round(npxg_off / mp, 4)
            npxg_def = round(npxg_def / mp, 4)

        rows.append({
            "league_slug":    league_slug,
            "season":         season,
            "team_name":      team,
            "matches_played": mp,
            "xg_off":         xg_off,
            "xg_def":         xg_def,
            "npxg_off":       npxg_off,
            "npxg_def":       npxg_def,
            "update_time":    fetch_date,
        })
    return rows


# ── 主抓取逻辑 ────────────────────────────────────────────────────────────────

def fetch_league(league_id: int, league_slug: str, url_name: str,
                 season: str, fetch_date: str):
    url = f"{BASE_URL}/en/comps/{league_id}/stats/{url_name}-Stats"
    log.info(f"抓取 FBref xG {league_slug}: {url}")

    html = _get_html(url)
    if not html:
        log.warning(f"  获取失败: {league_slug}")
        return 0

    if "stats_squads_standard_for" not in html:
        log.warning(f"  页面无 stats_squads_standard_for 表: {league_slug}")
        return 0

    df_for = _parse_html_tables(html, "stats_squads_standard_for")
    df_aga = _parse_html_tables(html, "stats_squads_standard_against")

    if df_for is None:
        log.warning(f"  解析 for 表失败: {league_slug}")
        return 0

    rows = _extract_xg_rows(df_for, df_aga, league_slug, season, fetch_date)
    if not rows:
        log.warning(f"  解析到 0 行: {league_slug}")
        return 0

    md = MetaData()
    md.reflect(bind=engine)
    tbl = md.tables["fbref_xg_teams"]
    batch_upsert(engine, tbl, rows, unique_keys=["league_slug", "season", "team_name"])
    log.info(f"  ✅ fbref_xg_teams 写入 {len(rows)} 支球队 ({league_slug} {season})")
    return len(rows)


def _current_season_label() -> str:
    now = datetime.now()
    y = now.year if now.month >= 7 else now.year - 1
    return f"{y}-{y+1}"


def run(league_ids: list = None, season: str = None):
    init_tables()
    fetch_date = datetime.now().strftime("%Y-%m-%d")
    season     = season or _current_season_label()
    targets    = {k: v for k, v in FBREF_LEAGUES.items()
                  if league_ids is None or k in league_ids}

    log.info(f"=== FBref xG 抓取 | 赛季={season} | 联赛数={len(targets)} ===")

    total = 0
    try:
        for lid, (url_name, slug) in targets.items():
            n = fetch_league(lid, slug, url_name, season, fetch_date)
            total += n
    finally:
        _shutdown()

    log.info(f"=== FBref xG 抓取完成，共 {total} 支球队 ===")
    return total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season",  type=str, default=None)
    parser.add_argument("--leagues", nargs="+", type=int, default=None,
                        help="FBref 联赛 ID，如 9 12 20")
    args = parser.parse_args()
    run(league_ids=args.leagues, season=args.season)
