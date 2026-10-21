# 18_espn_scores_scraper.py — ESPN 公开 API 比分/节次爬虫
# 【目标网站】 https://site.api.espn.com (无需认证，公开JSON API)
# 【数据价值】 足球半场比分 + 篮球节次(Q1-Q4)比分 + 半场大小分
# 【覆盖范围】 足球27个联赛 + NBA + WNBA + NBA夏季联赛(拉斯维加斯/盐湖城/加州经典赛)
# 【接入方式】 直接请求 JSON，无反爬，已验证可用

import sys, time, logging, argparse
import requests
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
import env_setup
from config import DB_ENGINE_URL
from db_utils import batch_upsert, exec_ddl

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

from sqlalchemy import MetaData

def _get_table(engine, table_name):
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables[table_name]
engine = create_engine(DB_ENGINE_URL)

H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0'}

SOCCER_SLUGS = [
    # ── 欧洲五大联赛 ───────────────────────────────
    ('eng.1', 'England - Premier League'),
    ('eng.2', 'England - Championship'),
    ('eng.3', 'England - League One'),
    ('eng.4', 'England - League Two'),
    ('ger.1', 'Germany - Bundesliga'),
    ('ger.2', 'Germany - Bundesliga 2'),
    ('esp.1', 'Spain - La Liga'),
    ('esp.2', 'Spain - Segunda'),
    ('ita.1', 'Italy - Serie A'),
    ('ita.2', 'Italy - Serie B'),
    ('fra.1', 'France - Ligue 1'),
    ('fra.2', 'France - Ligue 2'),
    # ── 欧洲其他联赛 ──────────────────────────────
    ('por.1', 'Portugal - Primeira Liga'),
    ('ned.1', 'Netherlands - Eredivisie'),
    ('ned.2', 'Netherlands - Eerste Divisie'),
    ('bel.1', 'Belgium - Pro League'),
    ('den.1', 'Denmark - Superliga'),
    ('scot.1','Scotland - Premiership'),
    ('scot.2','Scotland - Championship'),
    ('nor.1', 'Norway - Eliteserien'),
    ('swe.1', 'Sweden - Allsvenskan'),
    ('irl.1', 'Ireland - Premier'),
    ('irl.2', 'Ireland - Division 1'),
    ('isl.1', 'Iceland - Urvalsdeild'),
    ('tur.1', 'Turkey - Super Lig'),
    ('gre.1', 'Greece - Super League'),
    ('aut.1', 'Austria - Bundesliga'),
    ('sui.1', 'Switzerland - Super League'),
    ('cze.1', 'Czech Republic - HET Liga'),
    # ── 亚洲 ───────────────────────────────────────
    ('chn.1', 'China - Super League'),
    ('jpn.1', 'Japan - J1 League'),
    ('ind.1', 'India - Super League'),
    # ── 北中美洲 ──────────────────────────────────
    ('usa.1', 'USA - MLS'),
    ('usa.nwsl','USA - NWSL'),
    ('mex.1', 'Mexico - Liga MX'),
    ('concacaf.champions', 'CONCACAF Champions Cup'),
    # ── 南美洲 ────────────────────────────────────
    ('bra.1', 'Brazil - Brasileirao Serie A'),
    ('bra.2', 'Brazil - Brasileirao Serie B'),
    ('arg.1', 'Argentina - Primera Division'),
    ('col.1', 'Colombia - Primera A'),
    ('ven.1', 'Venezuela - Primera Division'),
    ('bol.1', 'Bolivia - Division Profesional'),
    ('ecu.1', 'Ecuador - Liga Pro'),
    ('par.1', 'Paraguay - Division Profesional'),
    ('chl.1', 'Chile - Primera Division'),
    ('uru.1', 'Uruguay - Primera Division'),
    ('per.1', 'Peru - Liga 1'),
    ('conmebol.libertadores', 'CONMEBOL - Copa Libertadores'),
    ('conmebol.sudamericana', 'CONMEBOL - Copa Sudamericana'),
    # ── UEFA 欧战（资格赛阶段同 slug）──────────────────
    ('uefa.champions', 'UEFA - Champions League'),
    ('uefa.europa', 'UEFA - Europa League'),
    ('uefa.europa.conf', 'UEFA - Conference League'),
    # ── 大洋洲 ────────────────────────────────────
    ('aus.1', 'Australia - A-League'),
    # ── 非洲/亚洲杯赛 ──────────────────────────────
    ('caf.champions', 'CAF - Champions League'),
    ('afc.champions', 'AFC - Champions League'),
    # ── 芬兰/北欧补充 ─────────────────────────────
    ('fin.1', 'Finland - Veikkausliiga'),
]

BASKETBALL_SLUGS = [
    ('nba',  'NBA'),
    ('wnba', 'WNBA'),
    ('mens-college-basketball', 'NCAA - College Basketball'),
    ('nba-summer-las-vegas',  'NBA Summer League - Las Vegas'),
    ('nba-summer-utah',       'NBA Summer League - Salt Lake City'),
    ('nba-summer-california', 'NBA Summer League - California Classic'),
]

DONE = {'Full Time', 'Final', 'FT', 'After Extra Time', 'After Penalties', 'AET'}


def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS espn_scores (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            espn_event_id    TEXT    UNIQUE,
            sport_code       TEXT,
            league_slug      TEXT,
            league_name      TEXT,
            home_team        TEXT,
            away_team        TEXT,
            match_date       TEXT,
            home_score       INTEGER,
            away_score       INTEGER,
            home_score_ht    INTEGER,
            away_score_ht    INTEGER,
            home_q1          INTEGER,
            away_q1          INTEGER,
            home_q2          INTEGER,
            away_q2          INTEGER,
            home_q3          INTEGER,
            away_q3          INTEGER,
            home_q4          INTEGER,
            away_q4          INTEGER,
            home_ot          INTEGER,
            away_ot          INTEGER,
            status           TEXT,
            fetch_date       TEXT
        )
    """)


def _get(url, params=None):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=H, timeout=12)
            if r.status_code == 200:
                return r.json()
            return None
        except Exception:
            if attempt == 2:
                return None
            time.sleep(2 ** attempt)


def _fi(v):
    try:
        return int(float(v)) if v not in (None, '') else None
    except Exception:
        return None


def get_basketball_quarters(slug, event_id):
    """从 summary 端点获取节次比分"""
    data = _get(
        f'https://site.api.espn.com/apis/site/v2/sports/basketball/{slug}/summary',
        {'event': event_id}
    )
    if not data:
        return {}
    try:
        comps = data.get('header', {}).get('competitions', [{}])[0]
        result = {}
        for comp in comps.get('competitors', []):
            side   = comp.get('homeAway', '')
            prefix = 'home' if side == 'home' else 'away'
            scores = [_fi(ls.get('value')) for ls in comp.get('linescores', [])]
            for i, q in enumerate(['q1', 'q2', 'q3', 'q4', 'ot']):
                result[f'{prefix}_{q}'] = scores[i] if i < len(scores) else None
            ht = (scores[0] or 0) + (scores[1] or 0) if len(scores) >= 2 else None
            result[f'{prefix}_score_ht'] = ht
        return result
    except Exception:
        return {}


def get_soccer_halftime(competition):
    """从比赛数据提取半场比分"""
    try:
        for details in competition.get('details', []):
            if details.get('type', {}).get('text') == 'Halftime':
                home_val = details.get('homeScore')
                away_val = details.get('awayScore')
                return _fi(home_val), _fi(away_val)
    except Exception:
        pass
    return None, None


def process_scoreboard(events, sport_code, slug, league_name, fetch_date, is_basketball=False):
    count = 0
    for e in events:
        try:
            comps  = e.get('competitions', [{}])[0]
            status = comps.get('status', {}).get('type', {}).get('description', '')
            if not any(s in status for s in DONE):
                continue

            teams  = comps.get('competitors', [])
            home_t = next((t for t in teams if t.get('homeAway') == 'home'), None)
            away_t = next((t for t in teams if t.get('homeAway') == 'away'), None)
            if not home_t or not away_t:
                continue

            event_id = str(e.get('id', ''))
            params = {
                'espn_event_id': event_id,
                'sport_code':    sport_code,
                'league_slug':   slug,
                'league_name':   league_name,
                'home_team':     home_t['team']['displayName'],
                'away_team':     away_t['team']['displayName'],
                'match_date':    (e.get('date', '')[:10]),
                'home_score':    _fi(home_t.get('score')),
                'away_score':    _fi(away_t.get('score')),
                'home_score_ht': None, 'away_score_ht': None,
                'home_q1': None, 'away_q1': None,
                'home_q2': None, 'away_q2': None,
                'home_q3': None, 'away_q3': None,
                'home_q4': None, 'away_q4': None,
                'home_ot': None, 'away_ot': None,
                'status':     status,
                'fetch_date': fetch_date,
            }

            if is_basketball and event_id:
                quarters = get_basketball_quarters(slug, event_id)
                params.update(quarters)
                time.sleep(0.25)
            elif not is_basketball:
                ht_h, ht_a = get_soccer_halftime(comps)
                params['home_score_ht'] = ht_h
                params['away_score_ht'] = ht_a

            rows_to_insert.append(params)
            count += 1
        except Exception as ex:
            log.debug(f'event error: {ex}')
    return count


def run(fetch_date=None, sports=None, days_back=3):
    if not fetch_date:
        fetch_date = datetime.now().strftime('%Y-%m-%d')
    if not sports:
        sports = ['soccer', 'basketball']

    init_tables()
    log.info('=' * 60)
    log.info(f'ESPN 比分爬虫启动  [{fetch_date}]  回溯 {days_back} 天')
    log.info('=' * 60)

    base_dt = datetime.strptime(fetch_date, '%Y-%m-%d')
    date_strs = [
        (base_dt - timedelta(days=i)).strftime('%Y%m%d')
        for i in range(days_back)
    ]

    total = 0

    if 'soccer' in sports:
        for slug, league_name in SOCCER_SLUGS:
            count = 0
            for d in date_strs:
                data = _get(
                    f'https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/scoreboard',
                    {'dates': d}
                )
                if data:
                    count += process_scoreboard(
                        data.get('events', []), 'soccer', slug, league_name,
                        fetch_date, is_basketball=False
                    )
                time.sleep(0.25)
            if count:
                log.info(f'  [足球] {league_name}: {count} 场')
            total += count

    if 'basketball' in sports:
        for slug, league_name in BASKETBALL_SLUGS:
            count = 0
            for d in date_strs:
                data = _get(
                    f'https://site.api.espn.com/apis/site/v2/sports/basketball/{slug}/scoreboard',
                    {'dates': d}
                )
                if data:
                    count += process_scoreboard(
                        data.get('events', []), 'basketball', slug, league_name,
                        fetch_date, is_basketball=True
                    )
                time.sleep(0.25)
            if count:
                log.info(f'  [篮球] {league_name}: {count} 场 (含Q1-Q4节次)')
            total += count

    log.info(f'ESPN 完成: 共写入 {total} 场')

    # 把刚抓到的 espn_scores 比分同步回 unified_matches（回填 status/home_score/away_score）
    try:
        synced = _sync_unified_matches(fetch_date, days_back)
        log.info(f'ESPN→unified_matches 同步: {synced} 场比分回填')
    except Exception as e:
        log.warning(f'ESPN→unified_matches 同步失败: {e}')

    return total


def _sync_unified_matches(fetch_date: str, days_back: int = 3) -> int:
    """把 espn_scores 表里的比分回填到 unified_matches。
    匹配策略：队名标准化后双向子串匹配 + kickoff 日期窗口(±1天)。
    只更新 home_score IS NULL 的记录，避免覆盖已有比分。
    """
    import re
    from difflib import SequenceMatcher

    def _norm(name: str) -> str:
        if not name:
            return ""
        n = name.lower().strip()
        n = re.sub(r'[^a-z0-9\u4e00-\u9fff]', '', n)
        return n

    def _sport_norm(s: str) -> str:
        s = (s or "").lower()
        if s in ("football", "soccer"):
            return "football"
        if s in ("basketball", "basket"):
            return "basketball"
        return s

    def _match(rec_h: str, rec_a: str, espn_h: str, espn_a: str) -> bool:
        rh, ra, eh, ea = _norm(rec_h), _norm(rec_a), _norm(espn_h), _norm(espn_a)
        if not (rh and ra and eh and ea):
            return False
        if rh == eh and ra == ea:
            return True
        if (rh in eh or eh in rh) and (ra in ea or ea in ra):
            return True
        s_h = SequenceMatcher(None, rh, eh).ratio()
        s_a = SequenceMatcher(None, ra, ea).ratio()
        return (s_h + s_a) / 2 >= 0.58

    with engine.connect() as conn:
        # 取回溯窗口内 ESPN 有比分的比赛
        # 注：espn_scores 实际列名是 sport_code（不是 sport），且没有 kickoff_utc 列，
        # 只有 match_date——之前版本查错列名导致这个函数每次调用都直接抛
        # OperationalError，被外层 try/except 静默吞掉，从未真正回填过。
        espn_rows = conn.execute(text("""
            SELECT home_team, away_team, home_score, away_score,
                   match_date, sport_code, league_slug, home_score_ht, away_score_ht
            FROM espn_scores
            WHERE home_score IS NOT NULL AND away_score IS NOT NULL
        """)).fetchall()

        if not espn_rows:
            return 0

        # 按 match_date 分桶
        from collections import defaultdict
        by_date = defaultdict(list)
        for eh, ea, hs, aws, md, sp, lg, hs_ht, aws_ht in espn_rows:
            by_date[md or ''].append((eh, ea, hs, aws, sp, hs_ht, aws_ht))

        # 取 unified_matches 里待回填的（status 非 FT/Finished 或 home_score IS NULL）
        # 带上 sport_code：同名球队的足球/篮球赛（如国家队同天出场）不按运动过滤会
        # 撞车拿错比分，见 feedback_team_name_collision 同类bug的第四处修复。
        pending = conn.execute(text("""
            SELECT unified_id, sport_code, home_team_std, away_team_std, kickoff_utc, fetch_date
            FROM unified_matches
            WHERE home_score IS NULL
        """)).fetchall()

        updates = {}
        for uid, rec_sport, ht, at, ko, fd in pending:
            if not ht or not at:
                continue
            # 日期窗口：fetch_date ±1 + kickoff 前10位
            candidates = set()
            if fd:
                candidates.add(fd)
                try:
                    base = datetime.strptime(fd, '%Y-%m-%d')
                    candidates.add((base + timedelta(days=1)).strftime('%Y-%m-%d'))
                    candidates.add((base - timedelta(days=1)).strftime('%Y-%m-%d'))
                except Exception:
                    pass
            if ko:
                candidates.add(ko[:10])
            matched = None
            for d in candidates:
                for eh, ea, hs, aws, sp, hs_ht, aws_ht in by_date.get(d, []):
                    if _sport_norm(rec_sport) != _sport_norm(sp):
                        continue
                    if _match(ht, at, eh, ea):
                        matched = (hs, aws, hs_ht, aws_ht)
                        break
                if matched:
                    break
            if matched:
                updates[uid] = matched

        if updates:
            for uid, (hs, aws, hs_ht, aws_ht) in updates.items():
                conn.execute(text("""
                    UPDATE unified_matches
                    SET home_score = :hs, away_score = :aws,
                        home_score_ht = :hs_ht, away_score_ht = :aws_ht,
                        status = 'FT', last_updated = CURRENT_TIMESTAMP
                    WHERE unified_id = :uid AND home_score IS NULL
                """), {'hs': hs, 'aws': aws, 'hs_ht': hs_ht, 'aws_ht': aws_ht, 'uid': uid})
            conn.commit()

        return len(updates)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description='ESPN 比分/节次爬虫')
    p.add_argument('--date',   default=None)
    p.add_argument('--sports', nargs='+', default=None)
    p.add_argument('--days',   type=int, default=3)
    args = p.parse_args()
    run(fetch_date=args.date, sports=args.sports, days_back=args.days)
