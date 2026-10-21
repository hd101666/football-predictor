# -*- coding: utf-8 -*-
"""
37_corner_stats_scraper.py — corner-stats.com 角球终值抓取

背景：scoremer.com（33_corner_odds_scraper.py 的主源）被 403 封锁，500.com 兜底源
的 match_status 恒为 "live"、match_minute 恒为 None，无法判断比赛是否结束，导致
角球推荐（corner_recommendations）长期无法结算。TotalCorner.com / FootyStats.org /
WinDrawWin.com 均被 Cloudflare JS 挑战拦截，实测 corner-stats.com 可直接访问
（curl_cffi + chrome120 指纹，无需过 Cloudflare），且比赛覆盖面（含各国低级别联赛、
World Cup 等）和赛程与本系统 Pinnacle/theodds 数据源高度重合。

页面结构（已验证，2026-07-05；/updates 的性质2026-08-11更正）：
  - /updates **不是**比赛列表页，而是网站的新闻/更新日志页（正文条目是2020-2022年
    的产品公告）。这里能提取到比赛链接，是因为页面侧边栏挂着"TOP MATCHES"推广
    小工具——里面列的是**即将开赛**的比赛，不是"进行中/刚结束"的。原注释写反了，
    据此得出的"数据源只有赛后短暂窗口"的结论也是错的。
  - 因此本爬虫的正确用法是"发现即入队、之后反复重试"：发现的比赛先进
    corner_stats_pending，等它踢完后的某一次调度再抓到终值。配合
    _corner_catchup.py 一天多跑几次。
  - 比赛详情页 <title> 标签：
      未结束: "DD/MM/YYYY 主队 - 客队. Game result: ? : ?"
      已结束: "DD/MM/YYYY 主队 - 客队. Game result: H : A"
  - 队名/ID: <span id="game_team1">主队</span><input hidden id="team1-id" value="N">
  - 角球数据（仅已结束比赛才有该 DOM 节点，与 CSS display:none 无关，抓 HTML 源码即可）：
      <span class="other_block_left">H_total (H_1h)</span>
      <span class="other_block_titles">Corners...</span>
      <span class="other_block_right">A_total (A_1h)</span>

用法：
  python 37_corner_stats_scraper.py                 # 抓取 /updates 里的新比赛
  python 37_corner_stats_scraper.py --max 80        # 限制单次最多访问的比赛详情页数
"""
import os, sys, re, time, random, argparse, logging, contextlib
from datetime import datetime

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import env_setup
from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.exc import OperationalError
from config import DB_ENGINE_URL, CRAWL_MIN_SLEEP, CRAWL_MAX_SLEEP
from db_utils import exec_ddl, batch_upsert

from curl_cffi import requests as cf_req

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("corner_stats")

# FIX-011-1（2026-09-14）：connect_args timeout=60 = SQLite busy_timeout 60s。
# 此前用 pysqlite 默认 5s 忙等——全量跑批并发期其他爬虫持写锁超过 5s 时，
# 本脚本第一个 INSERT 直接抛 OperationalError('database is locked') 退出 exit 1
#（09-13/09-14 两次全量跑批实证；同一 SQL 单跑/闲时正常，已复现排除语法问题）。
engine = create_engine(DB_ENGINE_URL, connect_args={"timeout": 60})
BASE = "https://corner-stats.com"

# Bug修复(2026-08-10)：原来每次_get()调用都走cf_req.get()模块级便捷函数，每次
# 隐式新建一条独立TLS连接——实测连续请求同一域名4-5次后必然触发
# "curl: (35) TLS connect error: OPENSSL_internal:invalid library (0)"，是
# curl_cffi/libcurl高频创建独立连接耗尽/损坏底层OpenSSL资源的已知模式，不是
# 网站封锁也不是网络问题(同一域名用同一个Session对象连续请求10次完全正常)。
# 改成模块级复用同一个Session对象，让libcurl内部连接池正常工作。
_SESSION = cf_req.Session(impersonate="chrome120")

# 待抓队列参数：一天多次调度时，同一场比赛至少隔这么久才重试一次
RETRY_GAP_HOURS = 3
MAX_ATTEMPTS = 24
GIVE_UP_DAYS = 10

_MATCH_URL_RE = re.compile(r'href="(/[a-z0-9-]+/[a-z0-9-]+/match/(\d+))"')
_TITLE_RE     = re.compile(r'<title>(\d{2}/\d{2}/\d{4}) ([^<]*?)\. Game result: (\?|\d+) : (\?|\d+)</title>')

# Bug修复(2026-08-10)：网站改版后队名被<a href="...">队名</a>包裹，不再是紧跟在
# id="game_teamN">后面的纯文本，原正则要求[^<]*后立即接</span>，遇到<a>标签就
# 匹配失败——实测27场"已结束"比赛全部因此被误判成解析失败。(?:<a[^>]*>)?...
# (?:</a>)?两个可选组同时兼容改版前后两种页面结构。
_TEAM1_RE     = re.compile(r'id="game_team1">(?:<a[^>]*>)?([^<]*)(?:</a>)?</span><input hidden id="team1-id" value="(\d+)"')
_TEAM2_RE     = re.compile(r'id="game_team2">(?:<a[^>]*>)?([^<]*)(?:</a>)?</span><input hidden id="team2-id" value="(\d+)"')
_CORNER_RE    = re.compile(
    r'other_block_left">\s*(\d+)\s*\((\d+)\)\s*</span>\s*'
    r'<span class="other_block_titles">Corners.*?'
    r'other_block_right">\s*(\d+)\s*\((\d+)\)\s*</span>',
    re.S,
)


def _get_tables():
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables


def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS corner_stats_final (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT DEFAULT 'corner-stats.com',
            match_url_id TEXT,
            league_slug TEXT,
            match_date TEXT,
            home_team TEXT,
            away_team TEXT,
            home_score INTEGER,
            away_score INTEGER,
            home_corners INTEGER,
            away_corners INTEGER,
            total_corners INTEGER,
            home_corners_1h INTEGER,
            away_corners_1h INTEGER,
            fetched_at TEXT,
            fetch_date TEXT,
            UNIQUE(source, match_url_id)
        )
    """)
    try:
        exec_ddl(engine, "ALTER TABLE corner_stats_final ADD COLUMN league_slug TEXT")
    except Exception:
        pass

    # Bug修复(2026-08-11)：待抓队列。原来"发现了但当时还没结束"的比赛id不落
    # 任何地方，只在下一次仍然出现在页面上时才会被重新发现——而 /updates 侧边栏
    # 列的是**即将开赛**的比赛，比赛一开赛就被挪走，id随即永久丢失，终值再也抓
    # 不到。这是 corner_stats_final 长期只有二十几行的真正原因（不是"赛后窗口太
    # 短、要卡着散场时间抓"）。现在发现即入队，之后每次跑都重试尚未拿到结果的。
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS corner_stats_pending (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT DEFAULT 'corner-stats.com',
            match_url_id TEXT,
            url_path TEXT,
            first_seen TEXT,
            last_try TEXT,
            attempts INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            UNIQUE(source, match_url_id)
        )
    """)


def _sleep():
    time.sleep(random.uniform(CRAWL_MIN_SLEEP, CRAWL_MAX_SLEEP))


@contextlib.contextmanager
def _begin_retry(attempts: int = 4):
    """FIX-011-1：整事务级重试。engine 的 60s busy_timeout 之外再兜一层——
    跑批高峰锁竞争可能超过60s（WAL 单写者）。engine.begin() 异常时自动回滚，
    重试不会产生部分提交；入队 INSERT 有 ON CONFLICT DO NOTHING、状态 UPDATE
    幂等，重放安全。重试成功打 WARNING 留痕（静默恢复会让锁竞争再次隐身）。"""
    for i in range(attempts):
        try:
            with engine.begin() as conn:
                yield conn
            return
        except OperationalError:
            if i == attempts - 1:
                raise
            wait = 5 * (i + 1)
            log.warning(f"数据库锁竞争，{wait}s 后重试事务（第{i+1}/{attempts-1}次）")
            time.sleep(wait)


def _get(url: str, retries: int = 3) -> str | None:
    for attempt in range(retries):
        try:
            r = _SESSION.get(url, timeout=15)
            if r.status_code == 200:
                return r.text
            log.warning(f"HTTP {r.status_code}: {url}")
        except Exception as e:
            log.warning(f"请求异常({attempt+1}): {e}")
        time.sleep(2 * (attempt + 1))
    return None


def discover_match_ids(fetch_date: str) -> list[str]:
    """从 /updates 页面侧边栏的"TOP MATCHES"推广位提取比赛ID（多为未开赛，见文件头）"""
    html = _get(f"{BASE}/updates")
    if not html:
        log.error("无法获取 /updates 页面")
        return []
    ids = list(dict.fromkeys(m.group(2) for m in _MATCH_URL_RE.finditer(html)))
    log.info(f"/updates 页面发现 {len(ids)} 场比赛")
    return ids


def parse_match(match_id: str, path_hint: str, fetch_date: str) -> dict | None:
    """抓取单场比赛详情页，返回终值角球数据；未结束或解析失败返回 None"""
    html = _get(f"{BASE}{path_hint}")
    if not html:
        return None

    tm = _TITLE_RE.search(html)
    if not tm:
        return None
    match_date, _title_teams, hs, as_ = tm.groups()
    if hs == "?" or as_ == "?":
        return None  # 比赛未结束

    t1 = _TEAM1_RE.search(html)
    t2 = _TEAM2_RE.search(html)
    if not t1 or not t2:
        return None
    home_team = t1.group(1).strip()
    away_team = t2.group(1).strip()

    cm = _CORNER_RE.search(html)
    if not cm:
        return None  # 页面无角球数据（极少数比赛缺失该统计项）
    h_total, h_1h, a_total, a_1h = (int(x) for x in cm.groups())

    # URL 格式: /[主队-客队-日期]/[联赛slug]/match/[id]，联赛信息不用额外请求即可拿到
    path_parts = path_hint.strip("/").split("/")
    league_slug = path_parts[1] if len(path_parts) >= 3 else None

    return {
        "source": "corner-stats.com",
        "match_url_id": match_id,
        "league_slug": league_slug,
        "match_date": datetime.strptime(match_date, "%d/%m/%Y").strftime("%Y-%m-%d"),
        "home_team": home_team,
        "away_team": away_team,
        "home_score": int(hs),
        "away_score": int(as_),
        "home_corners": h_total,
        "away_corners": a_total,
        "total_corners": h_total + a_total,
        "home_corners_1h": h_1h,
        "away_corners_1h": a_1h,
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fetch_date": fetch_date,
    }


def run(max_matches: int = 150, fetch_date: str | None = None) -> int:
    fetch_date = fetch_date or datetime.now().strftime("%Y-%m-%d")
    init_tables()

    html = _get(f"{BASE}/updates")
    if not html:
        log.error("无法获取 /updates 页面，跳过本次抓取")
        return 0
    pairs = list(dict.fromkeys(
        (m.group(1), m.group(2)) for m in _MATCH_URL_RE.finditer(html)
    ))
    log.info(f"/updates 发现 {len(pairs)} 场比赛链接（多为未开赛，先入队）")

    tables = _get_tables()
    if "corner_stats_final" not in tables:
        log.error("corner_stats_final 表不存在，init_tables 未生效")
        return 0

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _begin_retry() as conn:
        for path, mid in pairs:
            conn.execute(text("""
                INSERT INTO corner_stats_pending
                    (source, match_url_id, url_path, first_seen, attempts, status)
                VALUES ('corner-stats.com', :mid, :path, :now, 0, 'pending')
                ON CONFLICT(source, match_url_id) DO NOTHING
            """), {"mid": mid, "path": path, "now": now})

        # 已经抓到终值的直接结案，避免历史遗留数据重复入队重试
        conn.execute(text("""
            UPDATE corner_stats_pending SET status='done'
            WHERE status='pending' AND match_url_id IN
                (SELECT match_url_id FROM corner_stats_final WHERE source='corner-stats.com')
        """))

    # 只重试距上次尝试>=RETRY_GAP_HOURS的，避免一天多次调度时把请求浪费在
    # 同一批刚试过的比赛上；先试发现得最早的（最可能已经踢完）
    with engine.connect() as conn:
        to_fetch = [(r[0], r[1]) for r in conn.execute(text(f"""
            SELECT url_path, match_url_id FROM corner_stats_pending
            WHERE source='corner-stats.com' AND status='pending'
              AND (last_try IS NULL OR last_try <= datetime('now', '-{RETRY_GAP_HOURS} hours'))
            ORDER BY first_seen ASC
            LIMIT :lim
        """), {"lim": max_matches}).fetchall()]
        n_pending = conn.execute(text(
            "SELECT COUNT(*) FROM corner_stats_pending WHERE status='pending'"
        )).scalar()
    log.info(f"队列待抓 {n_pending} 场，本次尝试 {len(to_fetch)} 场")

    rows, done_ids, fail_ids = [], [], []
    for path, mid in to_fetch:
        row = parse_match(mid, path, fetch_date)
        if row:
            rows.append(row)
            done_ids.append(mid)
        else:
            fail_ids.append(mid)
        _sleep()

    if rows:
        batch_upsert(engine, tables["corner_stats_final"], rows,
                     unique_keys=["source", "match_url_id"])

    with _begin_retry() as conn:
        for mid in done_ids:
            conn.execute(text("""
                UPDATE corner_stats_pending SET status='done', last_try=:now,
                       attempts=attempts+1
                WHERE source='corner-stats.com' AND match_url_id=:mid
            """), {"mid": mid, "now": now})
        for mid in fail_ids:
            conn.execute(text("""
                UPDATE corner_stats_pending SET last_try=:now, attempts=attempts+1
                WHERE source='corner-stats.com' AND match_url_id=:mid
            """), {"mid": mid, "now": now})
        # 试了很多次仍抓不到（比赛被取消/页面下架/id失效）就别再占额度
        gave_up = conn.execute(text(f"""
            UPDATE corner_stats_pending SET status='gave_up'
            WHERE status='pending' AND attempts >= {MAX_ATTEMPTS}
              AND first_seen <= datetime('now', '-{GIVE_UP_DAYS} days')
        """)).rowcount

    log.info(f"角球终值抓取完成: 尝试 {len(to_fetch)} 场，成功解析(已结束) {len(rows)} 场，"
             f"仍待重试 {len(fail_ids)} 场，放弃 {gave_up} 场")
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="corner-stats.com 角球终值抓取")
    parser.add_argument("--max", type=int, default=150, help="单次最多访问的比赛详情页数")
    parser.add_argument("--date", default=None, help="fetch_date 标签，默认今日")
    args = parser.parse_args()
    run(max_matches=args.max, fetch_date=args.date)
