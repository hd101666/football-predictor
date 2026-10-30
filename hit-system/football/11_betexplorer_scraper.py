# 11_betexplorer_scraper.py — BetExplorer 赔率历史爬虫
# 抓取：历史赔率、球队战绩统计、比赛结果
# 存储：betexplorer_matches / betexplorer_odds / betexplorer_stats
# 反爬：curl_cffi + 随机UA + 动态延迟 + 逆向JSON API

import sys, re, time, random, json, logging
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import create_engine, text
from bs4 import BeautifulSoup

import env_setup
from config import DB_ENGINE_URL, CRAWL_MIN_SLEEP, CRAWL_MAX_SLEEP
from db_utils import batch_upsert, exec_ddl
from http_utils import StealthSession, random_sleep

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

from sqlalchemy import MetaData

def _get_table(engine, table_name):
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables[table_name]
engine = create_engine(DB_ENGINE_URL)

# 模块级行缓冲（各函数追加，run() 末尾统一写库）
_match_rows: list = []
_odds_rows:  list = []
_avg_rows:   list = []

# ─── 依赖检测已在 http_utils 中统一处理 ───────────────────────────────────────

BASE = "https://www.betexplorer.com"

BE_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer":         BASE + "/",
}

from leagues import FOOTBALL_LEAGUES, BASKETBALL_LEAGUES


def init_tables():
    ddls = [
        """CREATE TABLE IF NOT EXISTS betexplorer_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            be_match_id TEXT UNIQUE,
            sport_code TEXT,
            league_code TEXT,
            season TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            status TEXT,
            home_score INTEGER,
            away_score INTEGER,
            home_score_ht INTEGER,
            away_score_ht INTEGER,
            fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS betexplorer_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            be_match_id TEXT,
            market TEXT,
            bookmaker TEXT,
            outcome TEXT,
            odds_open REAL,
            odds_close REAL,
            odds_max REAL,
            odds_min REAL,
            fetch_date TEXT,
            UNIQUE(be_match_id, market, bookmaker, outcome)
        )""",
        """CREATE TABLE IF NOT EXISTS betexplorer_avg_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            be_match_id TEXT,
            market TEXT,
            outcome TEXT,
            avg_odds REAL,
            max_odds REAL,
            fetch_date TEXT,
            UNIQUE(be_match_id, market, outcome)
        )""",
    ]
    for sql in ddls:
        exec_ddl(engine, sql)
    log.info("✅ BetExplorer 数据表初始化完成")


# ─── HTTP 会话（使用公共 StealthSession 基类）────────────────────────────────
class _BESession(StealthSession):
    """BetExplorer 专用会话，增加 get_json 便捷方法。"""

    def __init__(self):
        super().__init__(base_url=BASE, headers=BE_HEADERS)

    def get(self, url, params=None, is_json=False, retries=5) -> Optional[str]:
        hdrs = {
            "Accept": ("application/json, text/plain, */*" if is_json
                       else "text/html,application/xhtml+xml,*/*;q=0.8"),
            "X-Requested-With": "XMLHttpRequest" if is_json else "",
        }
        r = super().get(url, retries=retries, headers=hdrs, params=params)
        return r.text if r is not None else None

    def get_json(self, url, params=None) -> Optional[dict]:
        raw = self.get(url, params=params, is_json=True)
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass
        return None


_sess = _BESession()


def _sleep():
    time.sleep(random.uniform(CRAWL_MIN_SLEEP, CRAWL_MAX_SLEEP + 1))


def _soup(html):
    return BeautifulSoup(html, "lxml")


def _parse_score(text):
    m = re.match(r"(\d+)[:\-](\d+)", (text or "").strip())
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def _extract_be_id(href):
    m = re.search(r"/([a-zA-Z0-9]{6,12})/?(?:#.*)?$", href or "")
    return m.group(1) if m else None


def _normalize_be_date(raw: str, fetch_date: str) -> str:
    """把 BetExplorer 页面上的日期文本标准化成 ISO YYYY-MM-DD。
    处理三种格式：
      - "Yesterday" / "Today"      → 相对 fetch_date 偏移
      - "24.05." / "24.05.2026"   → DD.MM. 或 DD.MM.YYYY
      - 已是 ISO                   → 原样返回
    """
    if not raw:
        return fetch_date or ""
    s = raw.strip().lower()
    try:
        base = datetime.strptime(fetch_date, "%Y-%m-%d")
    except Exception:
        base = datetime.now()
    if "yesterday" in s:
        return (base - timedelta(days=1)).strftime("%Y-%m-%d")
    if "today" in s or "today." in s:
        return base.strftime("%Y-%m-%d")
    if re.match(r"^\d{4}-\d{2}-\d{2}", raw):
        return raw[:10]
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})?$", raw.strip())
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else base.year
        try:
            return datetime(y, mo, d).strftime("%Y-%m-%d")
        except ValueError:
            return raw
    return raw


# ─── 1. 联赛比赛列表 ──────────────────────────────────────────────────────────
def fetch_league_matches(league_path: str, league_code: str, sport_code: str,
                          fetch_date: str, seasons: int = 2) -> list:
    match_ids = []
    url = f"{BASE}{league_path}results/"
    html = _sess.get(url)
    if not html:
        log.warning(f"无法访问: {league_path}")
        return match_ids

    soup = _soup(html)

    # 当前赛季
    season_el = soup.select_one("select#selSeason option[selected], h2.main-filter__filter span")
    season = season_el.get_text(strip=True) if season_el else "current"

    ids = _parse_results_table(soup, league_code, sport_code, season, fetch_date)
    match_ids.extend(ids)

    # 历史赛季（翻页）
    season_opts = soup.select("select#selSeason option")
    for opt in season_opts[1:seasons]:
        season_val = opt.get("value", "")
        season_name = opt.get_text(strip=True)
        if not season_val:
            continue
        url2 = f"{BASE}{league_path}results/?season={season_val}"
        html2 = _sess.get(url2)
        if html2:
            soup2 = _soup(html2)
            ids2 = _parse_results_table(soup2, league_code, sport_code, season_name, fetch_date)
            match_ids.extend(ids2)
            _sleep()

    log.info(f"  {league_code}: {len(match_ids)} 场")
    return match_ids


def _parse_results_table(soup, league_code, sport_code, season, fetch_date) -> list:
    """解析赛果列表页，兼容两种结构：
    - 旧版: <table class="table-main"><tr><td>...</td></tr></table>
    - 新版: <ul class="table-main__matchInfo"> ... </ul>（div 布局）
    新版页面比分常为空(JS 动态加载)，只提取队名/日期/matchId，比分留空由其他源补。
    """
    ids = []
    table = soup.find("table", class_="table-main")
    rows = table.find_all("tr") if table else []
    parsed_any = False

    # ── 旧版 table 结构 ──────────────────────────────
    for row in rows:
        try:
            tds = row.find_all("td")
            if len(tds) < 2:
                continue
            link = row.find("a", class_="in-match")
            if not link:
                continue
            be_id = _extract_be_id(link.get("href", ""))
            if not be_id:
                continue
            strong = link.find("strong")
            spans  = link.find_all("span")
            if strong:
                home_team = strong.get_text(strip=True)
                away_span = next((s for s in spans if not s.find("strong")), None)
                away_team = away_span.get_text(strip=True) if away_span else ""
            else:
                raw = link.get_text(" ", strip=True)
                parts = re.split(r"\s+-\s+", raw, maxsplit=1)
                home_team = parts[0].strip()
                away_team = parts[1].strip() if len(parts) > 1 else ""
            score_td = next(
                (td for td in tds if re.match(r"^\d+:\d+$", td.get_text(strip=True))),
                None
            )
            hs, as_ = _parse_score(score_td.get_text(strip=True) if score_td else "")
            texts = [td.get_text(strip=True) for td in tds]
            kickoff_raw = _normalize_be_date(texts[-1] if texts else "", fetch_date)
            ids.append(be_id)
            _match_rows.append({
                "be_match_id": be_id, "sport_code": sport_code,
                "league_code": league_code, "season": season,
                "home_team": home_team, "away_team": away_team,
                "kickoff_utc": kickoff_raw,
                "status": "FT" if hs is not None else "NS",
                "home_score": hs, "away_score": as_,
                "home_score_ht": None, "away_score_ht": None,
                "fetch_date": fetch_date,
            })
            parsed_any = True
        except Exception as e:
            log.debug(f"行解析异常(table): {e}")

    # ── 新版 div 结构: ul.table-main__matchInfo ──────────
    if not parsed_any:
        match_uls = soup.find_all("ul", class_="table-main__matchInfo")
        for ul in match_uls:
            try:
                # match id 在 data-live 或 a[href] 末尾
                be_id = ul.get("data-live", "")
                if not be_id:
                    a = ul.find("a", href=re.compile(r"/football/|/basketball/"))
                    be_id = _extract_be_id(a["href"]) if a else None
                if not be_id:
                    continue
                # 日期: data-dt="17,7,2026,16,00"
                dt_raw = ul.get("data-dt", "")
                kickoff_raw = fetch_date
                m_dt = re.match(r"(\d+),(\d+),(\d+),(\d+),(\d+)", dt_raw)
                if m_dt:
                    d, mo, y = int(m_dt.group(1)), int(m_dt.group(2)), int(m_dt.group(3))
                    try:
                        kickoff_raw = datetime(y, mo, d).strftime("%Y-%m-%d")
                    except ValueError:
                        pass
                # 队名: participantHome / participantAway 或 p 标签
                home_team = away_team = ""
                home_div = ul.find("div", class_=re.compile("participantHome"))
                away_div = ul.find("div", class_=re.compile("participantAway"))
                if home_div:
                    p = home_div.find("p") or home_div
                    home_team = p.get_text(strip=True)
                if away_div:
                    p = away_div.find("p") or away_div
                    away_team = p.get_text(strip=True)
                # 降级: 所有 p 标签前两个
                if not home_team or not away_team:
                    ps = ul.find_all("p")
                    if len(ps) >= 2:
                        home_team = home_team or ps[0].get_text(strip=True)
                        away_team = away_team or ps[1].get_text(strip=True)
                # 比分: liveResult div (新版常为空)
                hs = as_ = None
                lr = ul.find("div", class_="liveResult")
                if lr:
                    sc = lr.get_text(strip=True)
                    if re.match(r"^\d+:\d+$", sc):
                        hs, as_ = _parse_score(sc)
                # 状态: FIN / NS
                status_el = ul.find("span", class_=re.compile("matchStatus|matchHour"))
                status_txt = status_el.get_text(strip=True) if status_el else ""
                status = "FT" if (hs is not None or "FIN" in status_txt.upper()) else "NS"

                if home_team and away_team:
                    ids.append(be_id)
                    _match_rows.append({
                        "be_match_id": be_id, "sport_code": sport_code,
                        "league_code": league_code, "season": season,
                        "home_team": home_team, "away_team": away_team,
                        "kickoff_utc": kickoff_raw,
                        "status": status,
                        "home_score": hs, "away_score": as_,
                        "home_score_ht": None, "away_score_ht": None,
                        "fetch_date": fetch_date,
                    })
                    parsed_any = True
            except Exception as e:
                log.debug(f"行解析异常(div): {e}")

    return ids


# ─── 2. 单场赔率 ──────────────────────────────────────────────────────────────


# ─── 2. 单场赔率 ──────────────────────────────────────────────────────────────
def fetch_match_odds(be_match_id: str, league_path: str, fetch_date: str):
    """抓取单场1X2/AH/OU赔率（BetExplorer JSON API）"""
    referer = f"{BASE}{league_path}results/"

    for market, market_num in [("1X2", 1), ("AH", 2), ("OU", 5), ("DC", 7)]:
        url = f"{BASE}/match-odds/{be_match_id}/{market_num}/1/"
        data = _sess.get_json(url)
        if not data:
            url2 = f"{BASE}/matchodds/{market_num}/{be_match_id}/"
            data = _sess.get_json(url2)
        if not data:
            continue

        _parse_be_odds(data, be_match_id, market, fetch_date)
        _sleep()


def _parse_be_odds(data: dict, be_match_id: str, market: str, fetch_date: str):
    """解析 BetExplorer 赔率JSON"""
    # 格式1: {"odds": [{"bookmaker": ..., "odds": [o1, o2, o3]}]}
    rows = data.get("odds", data.get("data", data.get("d", [])))
    if isinstance(rows, str):
        try:
            rows = json.loads(rows)
        except Exception:
            return
    if not isinstance(rows, list):
        rows = list(rows.values()) if isinstance(rows, dict) else []

    outcomes_map = {
        "1X2": ["home", "draw", "away"],
        "AH":  ["home", "away"],
        "OU":  ["over", "under"],
        "DC":  ["1X", "12", "X2"],
    }
    outcomes = outcomes_map.get(market, ["o1", "o2", "o3"])

    avg_acc = {o: [] for o in outcomes}

    for bm in rows:
        if not isinstance(bm, dict):
            continue
        bookmaker = (bm.get("bookmakerName") or bm.get("n") or bm.get("an") or "unknown")
        odds_list  = bm.get("odds") or bm.get("o") or []
        if isinstance(odds_list, str):
            odds_list = odds_list.split(";")

        for i, outcome in enumerate(outcomes):
            if i >= len(odds_list):
                break
            raw = odds_list[i]
            # BetExplorer格式: "open_odds/close_odds" 或单值
            if isinstance(raw, str) and "/" in raw:
                parts = raw.split("/")
                open_v  = _to_float(parts[0])
                close_v = _to_float(parts[-1])
            else:
                open_v  = _to_float(raw)
                close_v = open_v

            if open_v is None and close_v is None:
                continue

            _odds_rows.append({
                "be_match_id": be_match_id, "market": market,
                "bookmaker": bookmaker, "outcome": outcome,
                "odds_open": open_v, "odds_close": close_v,
                "fetch_date": fetch_date,
            })

            if close_v:
                avg_acc[outcome].append(close_v)

    # 计算并存储均值/最大赔率
    for outcome, vals in avg_acc.items():
        if not vals:
            continue
        _avg_rows.append({
            "be_match_id": be_match_id, "market": market, "outcome": outcome,
            "avg_odds": round(sum(vals)/len(vals), 3),
            "max_odds": max(vals),
            "fetch_date": fetch_date,
        })


def _to_float(v) -> Optional[float]:
    try:
        f = float(str(v).strip())
        return f if f > 0 else None
    except Exception:
        return None


# ─── 主流程 ───────────────────────────────────────────────────────────────────
def run(fetch_odds_flag: bool = False):
    init_tables()
    fetch_date = datetime.now().strftime("%Y-%m-%d")
    log.info(f"🌐 BetExplorer 全量数据抓取开始 [{fetch_date}]")

    all_ids = []

    for path, code in FOOTBALL_LEAGUES.items():
        log.info(f"\n⚽ {code}")
        ids = fetch_league_matches(path, code, "football", fetch_date, seasons=2)
        all_ids.extend([(i, path) for i in ids])
        _sleep()

    for path, code in BASKETBALL_LEAGUES.items():
        log.info(f"\n🏀 {code}")
        ids = fetch_league_matches(path, code, "basketball", fetch_date, seasons=2)
        all_ids.extend([(i, path) for i in ids])
        _sleep()

    # 赔率 API 已下线（404），暂跳过
    if fetch_odds_flag:
        log.info(f"\n共 {len(all_ids)} 场，开始抓取赔率...")
        for be_id, path in all_ids[:120]:
            fetch_match_odds(be_id, path, fetch_date)
            _sleep()

    # ── 写库 ──────────────────────────────────────────────────────────────────
    if _match_rows:
        tbl = _get_table(engine, "betexplorer_matches")
        batch_upsert(engine, tbl, _match_rows, unique_keys=["be_match_id"])
        log.info(f"  写入 betexplorer_matches: {len(_match_rows)} 行")

    if _odds_rows:
        tbl = _get_table(engine, "betexplorer_odds")
        batch_upsert(engine, tbl, _odds_rows,
                     unique_keys=["be_match_id", "market", "bookmaker", "outcome"])
        log.info(f"  写入 betexplorer_odds: {len(_odds_rows)} 行")

    if _avg_rows:
        tbl = _get_table(engine, "betexplorer_avg_odds")
        batch_upsert(engine, tbl, _avg_rows,
                     unique_keys=["be_match_id", "market", "outcome"])
        log.info(f"  写入 betexplorer_avg_odds: {len(_avg_rows)} 行")

    # 把 betexplorer_matches 的比分同步到 unified_matches + match_results
    # （结算脚本只查这两个表，betexplorer 比分不灌进去就结不掉）
    try:
        synced = _sync_results_to_settle_tables()
        if synced > 0:
            log.info(f"  BetExplorer→unified_matches/match_results 同步: {synced} 场比分")
    except Exception as e:
        log.warning(f"  BetExplorer 同步失败: {e}")

    log.info("✅ BetExplorer 抓取完成")


def _sync_results_to_settle_tables() -> int:
    """把 betexplorer_matches 里 home_score IS NOT NULL 的比分，
    同步到 unified_matches（待回填的）和 match_results（缺失的）。
    匹配：队名标准化双向子串 + kickoff 日期窗口 ±2天。
    """
    import re
    from difflib import SequenceMatcher
    from collections import defaultdict

    def _norm(name):
        if not name:
            return ""
        n = name.lower().strip()
        for suf in [" fc", " cf", " sc", " ac", " bc", " club", " team", " city"]:
            n = n.replace(suf, "")
        n = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", n)
        return n

    def _sport_norm(s):
        s = (s or "").lower()
        if s in ("football", "soccer"):
            return "football"
        if s in ("basketball", "basket"):
            return "basketball"
        return s

    def _match(rec_h, rec_a, be_h, be_a):
        rh, ra, bh, ba = _norm(rec_h), _norm(rec_a), _norm(be_h), _norm(be_a)
        if not (rh and ra and bh and ba):
            return False
        if rh == bh and ra == ba:
            return True
        if (rh in bh or bh in rh) and (ra in ba or ba in ra):
            return True
        sh = SequenceMatcher(None, rh, bh).ratio()
        sa = SequenceMatcher(None, ra, ba).ratio()
        return (sh + sa) / 2 >= 0.58

    with engine.connect() as conn:
        be_rows = conn.execute(text("""
            SELECT home_team, away_team, home_score, away_score,
                   kickoff_utc, sport_code, league_code
            FROM betexplorer_matches
            WHERE home_score IS NOT NULL AND away_score IS NOT NULL
        """)).fetchall()
        if not be_rows:
            return 0

        be_by_date = defaultdict(list)
        for bh, ba, hs, aws, ko, sp, lc in be_rows:
            d = ko[:10] if ko else ""
            be_by_date[d].append((bh, ba, hs, aws, sp, lc))

        # ── 同步到 unified_matches ──
        # 带上 sport_code：同名球队的足球/篮球赛不按运动过滤会撞车拿错比分，
        # 见 feedback_team_name_collision 同类bug的第四处修复。
        pending_um = conn.execute(text("""
            SELECT unified_id, sport_code, home_team_std, away_team_std, kickoff_utc, fetch_date
            FROM unified_matches WHERE home_score IS NULL
        """)).fetchall()
        um_updates = {}
        for uid, rec_sport, ht, at, ko, fd in pending_um:
            if not ht or not at:
                continue
            cands = set()
            if fd: cands.add(fd)
            if ko: cands.add(ko[:10])
            for off in [-2,-1,1,2]:
                try:
                    cands.add((datetime.strptime(fd, "%Y-%m-%d") + timedelta(days=off)).strftime("%Y-%m-%d"))
                except Exception:
                    pass
            matched = None
            for d in cands:
                for bh, ba, hs, aws, sp, lc in be_by_date.get(d, []):
                    if _sport_norm(rec_sport) != _sport_norm(sp):
                        continue
                    if _match(ht, at, bh, ba):
                        matched = (hs, aws, sp or "football")
                        break
                if matched:
                    break
            if matched:
                um_updates[uid] = matched
        for uid, (hs, aws, sp) in um_updates.items():
            conn.execute(text("""
                UPDATE unified_matches
                SET home_score=:hs, away_score=:aws, status='FT',
                    last_updated=CURRENT_TIMESTAMP
                WHERE unified_id=:uid AND home_score IS NULL
            """), {"hs": hs, "aws": aws, "uid": uid})

        # ── 同步到 match_results ──
        # 先建索引避免全表扫太慢：取已有 (home,away,date) 去重
        existing = set()
        for r in conn.execute(text("SELECT home_team, away_team, match_date FROM match_results")).fetchall():
            existing.add((_norm(r[0]), _norm(r[1]), r[2]))
        mr_inserts = []
        for bh, ba, hs, aws, ko, sp, lc in be_rows:
            d = ko[:10] if ko else ""
            key = (_norm(bh), _norm(ba), d)
            if key in existing:
                continue
            # 只插 7 天内的，避免一次性灌太多历史
            try:
                ko_dt = datetime.strptime(d, "%Y-%m-%d")
                if abs((datetime.now() - ko_dt).days) > 7:
                    continue
            except Exception:
                continue
            mr_inserts.append({
                "home_team": bh, "away_team": ba,
                "home_score": hs, "away_score": aws,
                "kickoff_utc": ko, "match_date": d,
                "sport": sp or "football", "league_slug": lc,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            existing.add(key)
        if mr_inserts:
            conn.execute(text("""
                INSERT INTO match_results
                    (home_team, away_team, home_score, away_score,
                     kickoff_utc, match_date, sport, league_slug, created_at)
                VALUES (:home_team, :away_team, :home_score, :away_score,
                        :kickoff_utc, :match_date, :sport, :league_slug, :created_at)
            """), mr_inserts)
        conn.commit()
        return len(um_updates) + len(mr_inserts)


if __name__ == "__main__":
    run()
