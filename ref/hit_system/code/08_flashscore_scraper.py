# 08_flashscore_scraper.py — Flashscore 数据爬虫
# Flashscore 使用 Cloudflare 保护 + 自定义管道协议
# 依赖 curl_cffi 进行 TLS 指纹伪造绕过反爬，首次运行自动安装
# 抓取：今日赛程、赛果、赔率历史变动
# 存储：flashscore_matches / flashscore_odds_history

import time
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import create_engine, text

import env_setup
from config import DB_ENGINE_URL, CRAWL_MIN_SLEEP, CRAWL_MAX_SLEEP
from db_utils import exec_ddl, batch_upsert
from sqlalchemy import MetaData, Table

# Bug修复(2026-08-12)：原先只有 getLogger、**没有 basicConfig**，独立运行时
# Python日志默认只输出WARNING及以上，所有 log.info 的成功信息被静默丢弃，
# 日志里只剩重试噪音——工作正常的爬虫会看起来像全线失败（09号即因此被误判）。
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

engine = create_engine(DB_ENGINE_URL)


def _get_table(engine, table_name):
    """获取表对象用于 batch_upsert"""
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables[table_name]


# ─── 依赖检测: curl_cffi ─────────────────────────────────────────────────────
try:
    from curl_cffi import requests as cffi_requests
    _SESSION = cffi_requests.Session(impersonate="chrome131")
except ImportError:
    print("错误: curl_cffi 未安装。请先安装: pip install curl_cffi", file=sys.stderr)
    sys.exit(1)

# ─── 常量 ─────────────────────────────────────────────────────────────────────
FLASH_HOST   = "https://www.flashscore.com"
FLASH_FEED   = "https://d.flashscore.com/x/feed"
FLASH_MOBILE = "https://m.flashscore.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer":         "https://www.flashscore.com/",
    "X-Fsign":         "SW9D1eZo",   # 必须字段（静态 token，来自 JS 源码）
}

# 管道协议分隔符
SEP_MAIN  = "¬"
SEP_KV    = "÷"

from leagues import FOOTBALL_LEAGUES, BASKETBALL_LEAGUES


# ─── DDL ──────────────────────────────────────────────────────────────────────
def init_tables():
    ddls = [
        """CREATE TABLE IF NOT EXISTS flashscore_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flash_id TEXT UNIQUE,
            sport_code TEXT,
            league_code TEXT,
            league_path TEXT,
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
        """CREATE TABLE IF NOT EXISTS flashscore_odds_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flash_id TEXT,
            bookmaker TEXT,
            market TEXT,
            outcome TEXT,
            odds_open REAL,
            odds_close REAL,
            odds_change REAL,
            fetch_date TEXT,
            UNIQUE(flash_id, bookmaker, market, outcome)
        )""",
        # 断点续跑记录：132个联赛(110足球+22篮球)逐个跑，历史上多次900s/1800s超时
        # 被杀掉重跑——没有这张表时每次重跑都从第一个联赛重新来过，超时问题永远
        # 解决不了。记录"今天已经成功处理过的联赛"，重跑时跳过，思路同
        # 46_qiety_lineup_scraper.py的qiety_lineup_scrape_log。
        """CREATE TABLE IF NOT EXISTS flashscore_scrape_log (
            league_code TEXT, sport_code TEXT, fetch_date TEXT, scraped_at TEXT,
            UNIQUE(league_code, sport_code, fetch_date)
        )""",
    ]
    for sql in ddls:
        exec_ddl(engine, sql)
    log.info("✅ Flashscore 数据表初始化完成")


# ─── HTTP 工具 ─────────────────────────────────────────────────────────────────
def _get(url: str, params: dict = None, retries: int = 3) -> Optional[str]:
    for attempt in range(retries):
        try:
            r = _SESSION.get(url, headers=HEADERS, params=params, timeout=25)
            if r.status_code == 200:
                return r.text
            if r.status_code == 429:
                wait = 20 * (attempt + 1)
                log.warning(f"限流 429，等待 {wait}s ...")
                time.sleep(wait)
                continue
            if r.status_code == 403:
                log.warning("403 Forbidden — Cloudflare 拦截（尝试中）")
                time.sleep(5)
                continue
            log.warning(f"HTTP {r.status_code}: {url[:80]}")
        except Exception as e:
            log.warning(f"请求异常 (attempt {attempt+1}): {e}")
            time.sleep(3)
    return None


def _sleep():
    t = CRAWL_MIN_SLEEP + (CRAWL_MAX_SLEEP - CRAWL_MIN_SLEEP) * 0.7
    time.sleep(t)


# ─── 管道格式解析 ──────────────────────────────────────────────────────────────
def _parse_pipe(raw: str) -> list[dict]:
    """
    解析 Flashscore 管道协议。
    每条记录以 ¬ 分隔，字段以 key÷value 格式存储。
    返回记录列表（每条为 dict）。
    """
    records = []
    for chunk in raw.split("¬"):
        chunk = chunk.strip()
        if not chunk:
            continue
        rec = {}
        for pair in chunk.split("÷"):
            if "÷" in pair:
                continue
        # 重新按 ÷ split
        parts = chunk.split("÷")
        for i in range(0, len(parts) - 1, 2):
            rec[parts[i]] = parts[i + 1]
        if rec:
            records.append(rec)
    return records


def _parse_pipe_v2(raw: str) -> list[dict]:
    """更健壮的管道解析：先按换行/~DA~/~ZA~ 切记录，再按÷解析键值"""
    records = []
    # Flashscore 记录分隔符可能是 ~DA~ 或 ~ZA~ 或换行
    chunks = re.split(r'~(?:DA|ZA)~|\n', raw)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk or len(chunk) < 3:
            continue
        parts = chunk.split("÷")
        if len(parts) < 2:
            continue
        rec = {}
        for i in range(0, len(parts) - 1, 2):
            key = parts[i].strip()
            val = parts[i + 1].strip() if i + 1 < len(parts) else ""
            if key:
                rec[key] = val
        if rec:
            records.append(rec)
    return records


# ─── 1. 抓取今日赛程 ───────────────────────────────────────────────────────────
def _parse_embedded_flash(html: str) -> list:
    """
    从 Flashscore HTML 提取内嵌管道格式的比赛数据。
    格式: KEY÷VALUE¬KEY÷VALUE~ (记录分隔符 ~, 字段分隔符 ¬, 键值分隔符 ÷)
    """
    idx = html.find('AA÷')
    if idx < 0:
        return []
    end = len(html)
    for marker in ['</script>', '</div>', '</body>']:
        pos = html.find(marker, idx)
        if idx < pos < end:
            end = pos
    data_block = html[idx:end]
    results = []
    for rec in data_block.split('~'):
        if 'AA÷' not in rec or 'CX÷' not in rec:
            continue
        fields = {}
        for part in rec.split('¬'):
            if '÷' in part:
                k, _, v = part.partition('÷')
                if k:
                    fields[k] = v
        if 'AA' in fields and 'CX' in fields:
            results.append(fields)
    return results


def fetch_fixtures_for_league(league_path: str, league_code: str,
                               sport_code: str, date_str: str, fetch_date: str) -> int:
    """抓取指定联赛的赛程和赛果（从 Flashscore HTML 内嵌数据解析）"""
    count = 0
    rows_to_insert = []
    for suffix in ["results/", "fixtures/"]:
        league_url = f"{FLASH_HOST}{league_path}{suffix}"
        html = _get(league_url)
        if not html:
            log.warning(f"  无法访问 {league_path}{suffix}")
            continue

        records = _parse_embedded_flash(html)
        for fields in records:
            flash_id = fields.get("AA", "")
            home     = fields.get("CX", "")
            away     = fields.get("AF", "")
            ts_kick  = fields.get("AD", "")
            # Bug修复(2026-08-11)：比分字段代号原先写的是 AS/AZ，是**错的**。
            # 实测拿30场巴西甲/阿根廷甲已完赛比赛跟干净的match_results对质：
            # AG/AH 命中28/30(93%)，AS/AZ 只命中5/30(17%，纯属小数字撞巧)。
            # 错得有多离谱：WNBA "Washington 95:75 Phoenix" 被存成 "1:1"、
            # "NY Liberty 111:71 Las Vegas" 存成 "1:1"、巴甲 "Bragantino 0:2
            # Corinthians" 存成 "2:2"。篮球侧尤其触目——790场全部存成个位数
            # (均值2.75/最大4)，直接导致 unified_matches 里篮球出现438场"平局"
            # (篮球打加时必分胜负，平局率应为0)和459场总分<100。
            # 而 unified_matches 是 21_auto_settle.py 的**主**比分来源，
            # 只是恰好大部分结算走了 match_results 兜底才没酿成大面积错结算。
            hs       = fields.get("AG")
            as_      = fields.get("AH")
            status_code = fields.get("AB", "0")
            status_map = {"0":"NS","1":"1H","2":"HT","3":"FT","31":"AET","41":"Pen","-1":"Canc","-2":"Post"}
            status   = status_map.get(status_code, status_code)

            if not flash_id or not home:
                continue

            kickoff_utc = ""
            if ts_kick:
                try:
                    kickoff_utc = datetime.fromtimestamp(int(ts_kick), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
                except Exception:
                    pass

            row = {
                "flash_id":      flash_id,
                "sport_code":    sport_code,
                "league_code":   league_code,
                "league_path":   league_path,
                "home_team":     home,
                "away_team":     away,
                "kickoff_utc":   kickoff_utc,
                "status":        status,
                "home_score":    int(hs)  if hs  and str(hs).lstrip('-').isdigit()  else None,
                "away_score":    int(as_) if as_ and str(as_).lstrip('-').isdigit() else None,
                "home_score_ht": None,
                "away_score_ht": None,
                "fetch_date":    fetch_date,
            }
            try:
                rows_to_insert.append(row)
                count += 1
            except Exception as e:
                log.debug(f"  入库异常: {e}")

    if rows_to_insert:
        tbl = _get_table(engine, "flashscore_matches")
        batch_upsert(engine, tbl, rows_to_insert, unique_keys=["flash_id"])

        _sleep()
    return count


# ─── 2. 赔率历史变动 ──────────────────────────────────────────────────────────
def fetch_odds_history(flash_id: str, fetch_date: str):
    """
    抓取某场比赛的赔率历史变动。
    Flashscore 赔率 API：/x/feed/1_{flash_id}_1_en_1
    返回开盘/收盘赔率及变化方向。
    """
    url = f"{FLASH_FEED}/1_{flash_id}_1_en_1"
    raw = _get(url)
    if not raw:
        return

    records = _parse_pipe_v2(raw)
    rows = []
    for rec in records:
        bookmaker = rec.get("XA") or rec.get("BN") or rec.get("bookmaker", "")
        market    = rec.get("XB") or rec.get("market", "1X2")
        # 典型字段：XC=home_open, XD=draw_open, XE=away_open
        #           XF=home_close, XG=draw_close, XH=away_close
        for outcome, open_key, close_key in [
            ("home", "XC", "XF"),
            ("draw", "XD", "XG"),
            ("away", "XE", "XH"),
        ]:
            open_val  = rec.get(open_key)
            close_val = rec.get(close_key)
            if not open_val and not close_val:
                continue
            try:
                ov = float(open_val)  if open_val  else None
                cv = float(close_val) if close_val else None
                change = round(cv - ov, 3) if (ov and cv) else None
                rows.append({
                    "flash_id":    flash_id,
                    "bookmaker":   bookmaker,
                    "market":      market,
                    "outcome":     outcome,
                    "odds_open":   ov,
                    "odds_close":  cv,
                    "odds_change": change,
                    "fetch_date":  fetch_date,
                })
            except (ValueError, TypeError):
                continue

    if not rows:
        return
    tbl = _get_table(engine, "flashscore_odds_history")
    batch_upsert(engine, tbl, rows, unique_keys=["flash_id", "bookmaker", "market", "outcome"])
    log.info(f"    赔率历史 {len(rows)} 条 → flash_id={flash_id}")


def _load_done_leagues(fetch_date: str) -> set:
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(
                "SELECT league_code, sport_code FROM flashscore_scrape_log WHERE fetch_date=:fd"
            ), {"fd": fetch_date}).fetchall()
        return {(r[0], r[1]) for r in rows}
    except Exception:
        return set()


def _mark_league_done(league_code: str, sport_code: str, fetch_date: str):
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT OR IGNORE INTO flashscore_scrape_log (league_code, sport_code, fetch_date, scraped_at)
                VALUES (:lc, :sc, :fd, :now)
            """), {"lc": league_code, "sc": sport_code, "fd": fetch_date,
                    "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
    except Exception:
        pass


# ─── 主流程 ──────────────────────────────────────────────────────────────────
def run(fetch_odds: bool = True, resume: bool = True):
    init_tables()
    fetch_date = datetime.now().strftime("%Y-%m-%d")
    today      = datetime.now().strftime("%Y-%m-%d")

    total_matches = 0
    done = _load_done_leagues(fetch_date) if resume else set()
    if done:
        log.info(f"  断点续跑: 跳过{len(done)}个今天已处理过的联赛")

    log.info("⚽ 抓取足球联赛赛程...")
    for path, code in FOOTBALL_LEAGUES.items():
        if (code, "football") in done:
            continue
        log.info(f"  {code}: {path}")
        n = fetch_fixtures_for_league(path, code, "football", today, fetch_date)
        log.info(f"    → {n} 场")
        total_matches += n
        _mark_league_done(code, "football", fetch_date)
        _sleep()

    log.info("🏀 抓取篮球联赛赛程...")
    for path, code in BASKETBALL_LEAGUES.items():
        if (code, "basketball") in done:
            continue
        log.info(f"  {code}: {path}")
        n = fetch_fixtures_for_league(path, code, "basketball", today, fetch_date)
        log.info(f"    → {n} 场")
        total_matches += n
        _mark_league_done(code, "basketball", fetch_date)
        _sleep()

    log.info(f"\n共写入 {total_matches} 场比赛")

    # 对今日未开赛场次抓取赔率历史
    if fetch_odds and total_matches > 0:
        log.info("💰 抓取赔率历史变动...")
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT flash_id FROM flashscore_matches
                WHERE fetch_date = :fd AND status NOT IN ('FT','AET','PEN','Canc')
                LIMIT 50
            """), {"fd": fetch_date}).fetchall()

        for (fid,) in rows:
            log.info(f"  赔率: {fid}")
            fetch_odds_history(fid, fetch_date)
            _sleep()

    log.info("✅ Flashscore 抓取完成")


if __name__ == "__main__":
    run(fetch_odds=True)
