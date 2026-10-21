# -*- coding: utf-8 -*-
# 10_oddsportal_scraper.py — OddsPortal 全量赔率爬虫（Playwright 渲染版）
# 数据来源: https://www.oddsportal.com
# 技术方案: Playwright 无头浏览器 → DOM 提取 eventRow + 单场赔率页

import sys, re, time, json, logging
from datetime import datetime, timezone
from typing import Optional

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import env_setup
from config import DB_ENGINE_URL
from db_utils import batch_upsert, exec_ddl
from sqlalchemy import create_engine, MetaData

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

engine = create_engine(DB_ENGINE_URL)

# ─── 模块级批量缓冲区 ─────────────────────────────────────────────────────────
_match_rows:   list = []
_odds_rows:    list = []
_history_rows: list = []

BASE = "https://www.oddsportal.com"

# 今日足球+篮球入口
SPORT_PAGES = [
    ("football",   "football"),
    ("basketball", "basketball"),
]

# ─── DDL ─────────────────────────────────────────────────────────────────────
def init_tables():
    ddls = [
        """CREATE TABLE IF NOT EXISTS oddsportal_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            op_match_id TEXT UNIQUE,
            sport_code TEXT,
            league_code TEXT,
            league_name TEXT,
            season TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            status TEXT,
            home_score INTEGER,
            away_score INTEGER,
            fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS oddsportal_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            op_match_id TEXT,
            market TEXT,
            bookmaker TEXT,
            outcome TEXT,
            odds_value REAL,
            is_closing INTEGER DEFAULT 0,
            fetch_date TEXT,
            UNIQUE(op_match_id, market, bookmaker, outcome)
        )""",
        """CREATE TABLE IF NOT EXISTS oddsportal_odds_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            op_match_id TEXT,
            market TEXT,
            bookmaker TEXT,
            outcome TEXT,
            odds_open REAL,
            odds_close REAL,
            odds_change REAL,
            odds_direction TEXT,
            recorded_at TEXT,
            fetch_date TEXT,
            UNIQUE(op_match_id, market, bookmaker, outcome)
        )""",
    ]
    for sql in ddls:
        exec_ddl(engine, sql)
    log.info("✅ OddsPortal 数据表初始化完成")


def _get_table(name: str):
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables.get(name)


def _flush_matches():
    global _match_rows
    if not _match_rows:
        return
    tbl = _get_table('oddsportal_matches')
    if tbl is not None:
        try:
            batch_upsert(engine, tbl, _match_rows, unique_keys=['op_match_id'])
        except Exception as e:
            log.warning(f"oddsportal_matches写入失败: {e}")
    _match_rows = []


def _flush_odds():
    global _odds_rows
    if not _odds_rows:
        return
    tbl = _get_table('oddsportal_odds')
    if tbl is not None:
        try:
            batch_upsert(engine, tbl, _odds_rows, unique_keys=['op_match_id', 'market', 'bookmaker', 'outcome'])
        except Exception as e:
            log.warning(f"oddsportal_odds写入失败: {e}")
    _odds_rows = []


def _flush_history():
    global _history_rows
    if not _history_rows:
        return
    tbl = _get_table('oddsportal_odds_history')
    if tbl is not None:
        try:
            batch_upsert(engine, tbl, _history_rows, unique_keys=['op_match_id', 'market', 'bookmaker', 'outcome'])
        except Exception as e:
            log.warning(f"oddsportal_odds_history写入失败: {e}")
    _history_rows = []


# ─── Playwright 浏览器上下文 ──────────────────────────────────────────────────
def _make_browser():
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
    )
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        viewport={"width": 1440, "height": 900},
        locale="en-US",
        timezone_id="America/New_York",
    )
    ctx.set_extra_http_headers({
        "Accept-Language": "en-US,en;q=0.9",
        "DNT": "1",
    })
    return pw, browser, ctx


# ─── DOM 解析：单场 eventRow ──────────────────────────────────────────────────
# JS 在浏览器里运行，提取每个 .eventRow 的结构化数据
_EXTRACT_JS = """() => {
    const rows = document.querySelectorAll('.eventRow');
    const results = [];
    rows.forEach(row => {
        const id = row.getAttribute('data-id') || '';
        // 比赛链接：优先取 sport/country/league/match 格式，h2h 链接仅用于兜底
        const links = Array.from(row.querySelectorAll('a[href]'));
        const detailLink = links.find(a => a.href && !a.href.includes('/h2h/')
            && /\/\w+\/\w+\/[\w-]+\/[\w-]+-[A-Za-z0-9]{4,}/.test(a.href));
        const h2hLink = links.find(a => a.href && a.href.includes('/h2h/'));
        const matchLink = detailLink || h2hLink;
        const href = matchLink ? matchLink.href : (links[0] ? links[0].href : '');

        // 队名：通常是两个加粗/span 文字
        const nameEls = row.querySelectorAll('[class*="participant"],[class*="team-name"],[class*="TeamName"]');
        let home = '', away = '';
        if (nameEls.length >= 2) {
            home = nameEls[0].innerText.trim();
            away = nameEls[1].innerText.trim();
        }

        // 分数
        const scoreEl = row.querySelector('[class*="score"],[class*="Score"],[class*="result"]');
        const scoreText = scoreEl ? scoreEl.innerText.trim() : '';

        // 时间/状态：优先取 data-start-time（Unix 时间戳），回退 innerText
        const timeEl = row.querySelector('[class*="time"],[class*="date"],[class*="Date"],[data-start-time]');
        let timeText = '';
        if (timeEl) {
            const ts = timeEl.getAttribute('data-start-time') || timeEl.getAttribute('data-time') || '';
            if (ts && /^\d{9,13}$/.test(ts.trim())) {
                // Unix 时间戳（秒或毫秒） → ISO 字符串
                const ms = ts.length >= 12 ? parseInt(ts) : parseInt(ts) * 1000;
                timeText = new Date(ms).toISOString();
            } else {
                timeText = timeEl.innerText.trim();
            }
        }
        // 全局 data-start-time 属性（OddsPortal 有时放在 row 本身或 p[t] 标签）
        if (!timeText) {
            const tsEl = row.querySelector('[data-start-time],[t]');
            const ts = tsEl ? (tsEl.getAttribute('data-start-time') || tsEl.getAttribute('t') || '') : '';
            if (ts && /^\d{9,13}$/.test(ts.trim())) {
                const ms = ts.length >= 12 ? parseInt(ts) : parseInt(ts) * 1000;
                timeText = new Date(ms).toISOString();
            }
        }

        // 赔率：美式 [+-]\d{2,4} 或十进制 \d+\.\d+ 或大数字 \d{3,4}
        // 排除比分单位数字（1, 2, 0等）
        const allSpans = Array.from(row.querySelectorAll('span,p,div'));
        const oddsVals = [];
        allSpans.forEach(el => {
            if (el.querySelector('*')) return;  // 只取叶子节点
            const t = el.innerText.trim();
            // 美式赔率: +190, -120 (有符号且>=2位)
            if (/^[+-]\d{2,4}$/.test(t)) { oddsVals.push(t); return; }
            // 十进制赔率: 1.90, 2.20
            if (/^\d+\.\d{1,3}$/.test(t)) { oddsVals.push(t); return; }
            // 大正整数赔率: 150, 340 (>=3位无符号，排除比分)
            if (/^\d{3,4}$/.test(t)) { oddsVals.push(t); return; }
        });

        // 联赛面包屑
        const breadcrumb = row.querySelector('[class*="breadcrumb"],[class*="league"],[class*="tournament"]');
        const leagueText = breadcrumb ? breadcrumb.innerText.trim() : '';

        // status
        const finishedEl = row.querySelector('[class*="Finished"],[class*="finished"],[class*="Live"],[class*="live"]');
        const status = finishedEl ? finishedEl.innerText.trim() : '';

        if (id || href) {
            results.push({id, href, home, away, scoreText, timeText, leagueText, status,
                          odds: oddsVals.slice(0, 4), fullText: row.innerText.slice(0, 400)});
        }
    });
    return results;
}"""


def _parse_event_row(ev: dict, sport_code: str, fetch_date: str) -> Optional[dict]:
    """将 JS 提取的 eventRow 转为 DB 行"""
    mid = ev.get('id', '')
    if not mid:
        # 从 href 提取 8 位 ID
        m = re.search(r'#([A-Za-z0-9]{6,10})$', ev.get('href', ''))
        if m:
            mid = m.group(1)
    if not mid:
        return None

    home = ev.get('home', '').strip()
    away = ev.get('away', '').strip()

    # 从 fullText 补充队名
    if not home or not away:
        full = ev.get('fullText', '')
        # 匹配 "Team A\n1–2\nTeam B" 或 "Team A 1–2 Team B"
        m2 = re.search(r'([A-Za-z][^\n\d]{2,40})\s+\d+\s*[–\-]\s*\d+\s+([A-Za-z][^\n\d]{2,40})', full)
        if m2:
            home = home or m2.group(1).strip()
            away = away or m2.group(2).strip()

    # 联赛从 href 提取 (football/england/premier-league/...)
    # h2h/ 开头是比赛个体链接，不是联赛路径，需跳过
    href = ev.get('href', '')
    league_code = ''
    m3 = re.search(r'oddsportal\.com/(\w+)/(\w+)/([\w-]+)/', href)
    if m3 and m3.group(2) != 'h2h':
        league_code = f"{m3.group(2)}/{m3.group(3)}"

    if not league_code:
        league_code = ev.get('leagueText', '').replace('\n', '/').strip()[:60]

    # 分数
    score_text = ev.get('scoreText', '')
    m4 = re.search(r'(\d+)\s*[–\-]\s*(\d+)', score_text or ev.get('fullText', ''))
    home_score = int(m4.group(1)) if m4 else None
    away_score = int(m4.group(2)) if m4 else None

    status_raw = ev.get('status', '').lower()
    status = 'FT' if ('finished' in status_raw or home_score is not None) else 'NS'

    # 踢球时间：JS 已优先提取 data-start-time → ISO 字符串
    time_text = ev.get('timeText', '').strip()
    if time_text and 'T' in time_text and len(time_text) >= 16:
        # 已是 ISO 格式（来自 data-start-time → new Date().toISOString()）
        kickoff_utc = time_text[:25].rstrip('Z') + 'Z' if not time_text.endswith('Z') else time_text[:25]
    else:
        kickoff_utc = ''

    return {
        "op_match_id": mid,
        "sport_code": sport_code,
        "league_code": league_code,
        "league_name": league_code,
        "season": "current",
        "home_team": home,
        "away_team": away,
        "kickoff_utc": kickoff_utc,
        "status": status,
        "home_score": home_score,
        "away_score": away_score,
        "fetch_date": fetch_date,
    }


def _parse_best_odds(ev: dict, mid: str, fetch_date: str):
    """从 eventRow 提取最优赔率（一行三个数字: home/draw/away）写入 _odds_rows"""
    odds = ev.get('odds', [])
    # 美式赔率转十进制
    def to_decimal(s):
        try:
            v = float(s.replace('+', ''))
            if abs(v) >= 100:
                return round(v / 100 + 1, 3) if v > 0 else round(100 / abs(v) + 1, 3)
            return round(v, 3)
        except Exception:
            return None

    labels = ['home', 'draw', 'away']
    for i, raw in enumerate(odds[:3]):
        dec = to_decimal(raw)
        if dec and 1.01 <= dec <= 100:
            _odds_rows.append({
                "op_match_id": mid,
                "market": "1X2",
                "bookmaker": "best",
                "outcome": labels[i],
                "odds_value": dec,
                "is_closing": 0,
                "fetch_date": fetch_date,
            })


# ─── 单场赔率页（Playwright 渲染）─────────────────────────────────────────────
_ODDS_TABLE_JS = """() => {
    // 找赔率表格行
    const rows = document.querySelectorAll('[class*="oddsCell"],[class*="OddsCell"],[class*="bookmaker"]');
    const result = [];
    rows.forEach(r => {
        const bm = r.querySelector('[class*="bookmakerName"],[class*="name"]');
        const cells = r.querySelectorAll('[class*="odds"],[class*="Odds"]');
        if (!bm) return;
        const bmName = bm.innerText.trim();
        const vals = Array.from(cells).map(c => c.innerText.trim()).filter(x => /^[+-]?\d/.test(x));
        if (bmName && vals.length >= 2) result.push({bm: bmName, vals});
    });
    return result;
}"""


def fetch_match_odds_pw(page, op_match_id: str, match_href: str, fetch_date: str):
    """在已有 page 上打开单场赔率页，提取各庄赔率"""
    if not match_href or op_match_id not in match_href:
        return
    try:
        page.goto(match_href, wait_until='domcontentloaded', timeout=20000)
        page.wait_for_timeout(3000)
        rows = page.evaluate(_ODDS_TABLE_JS)
        labels = ['home', 'draw', 'away']
        for row in rows:
            bm = row.get('bm', '')
            vals = row.get('vals', [])
            for i, raw in enumerate(vals[:3]):
                try:
                    v = float(raw.replace('+', ''))
                    if abs(v) >= 100:
                        dec = round(v / 100 + 1, 3) if v > 0 else round(100 / abs(v) + 1, 3)
                    else:
                        dec = round(v, 3)
                    if 1.01 <= dec <= 100:
                        _odds_rows.append({
                            "op_match_id": op_match_id, "market": "1X2",
                            "bookmaker": bm, "outcome": labels[i],
                            "odds_value": dec, "is_closing": 0,
                            "fetch_date": fetch_date,
                        })
                except Exception:
                    pass
    except Exception as e:
        log.debug(f"单场赔率失败 {op_match_id}: {e}")


# ─── 翻页滚动加载 ─────────────────────────────────────────────────────────────
def _scroll_load_all(page, max_scrolls: int = 15):
    """下滚触发懒加载，直到无新内容"""
    prev_count = 0
    for _ in range(max_scrolls):
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(1500)
            cur_count = page.evaluate("document.querySelectorAll('.eventRow').length")
            if cur_count == prev_count:
                break
            prev_count = cur_count
        except Exception as e:
            log.debug(f"滚动异常: {e}")
            break
    return prev_count


# ─── 主抓取流程 ───────────────────────────────────────────────────────────────
def fetch_sport_matches(page, sport: str, sport_code: str, fetch_date: str,
                        fetch_odds: bool = False) -> list:
    """抓取某运动今日全部比赛"""
    url = f"{BASE}/matches/{sport}/"
    log.info(f"  加载 {url}")
    loaded = False
    for attempt in range(4):
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
        except Exception as e:
            log.warning(f"  goto失败({attempt+1}): {e}")
            time.sleep(3)
            continue
        # 轮询等 JS 渲染完成（最多12s）
        cnt = 0
        for _ in range(12):
            page.wait_for_timeout(1000)
            try:
                cnt = page.evaluate("document.querySelectorAll('.eventRow').length")
            except Exception:
                break
            if cnt > 0:
                break
        if cnt > 0:
            loaded = True
            break
        log.warning(f"  页面无内容({attempt+1})，重试...")
        time.sleep(2)
    if not loaded:
        log.error(f"  {url} 持续无内容，跳过")
        return []

    total = _scroll_load_all(page, max_scrolls=20)
    log.info(f"  滚动后 eventRow 数: {total}")

    try:
        events = page.evaluate(_EXTRACT_JS) or []
    except Exception as e:
        log.warning(f"  DOM提取失败: {e}")
        events = []
    log.info(f"  提取比赛数: {len(events)}")

    match_ids = []
    hrefs = {}
    for ev in events:
        row = _parse_event_row(ev, sport_code, fetch_date)
        if row:
            _match_rows.append(row)
            mid = row['op_match_id']
            match_ids.append(mid)
            hrefs[mid] = ev.get('href', '')
            _parse_best_odds(ev, mid, fetch_date)

    _flush_matches()
    _flush_odds()

    # 可选：抓取今日未开赛场次的各庄赔率（限前80场，间隔保持1.5s防封——只放量不提速）
    if fetch_odds:
        pending = [(mid, hrefs[mid]) for mid in match_ids if hrefs.get(mid)]
        log.info(f"  抓取单场赔率: {len(pending[:80])} 场")
        for mid, href in pending[:80]:
            fetch_match_odds_pw(page, mid, href, fetch_date)
            _flush_odds()
            time.sleep(1.5)

    return match_ids


# ─── 联赛历史比赛（结果页翻页）────────────────────────────────────────────────
def fetch_league_results(page, league_path: str, league_code: str,
                         sport_code: str, fetch_date: str, pages: int = 3) -> list:
    """抓取联赛最近若干页赛果"""
    all_ids = []
    url = f"{BASE}{league_path}results/"
    log.info(f"  联赛 {league_code}: {url}")
    try:
        page.goto(url, wait_until='domcontentloaded', timeout=25000)
        page.wait_for_timeout(4000)
    except Exception as e:
        log.warning(f"  联赛页超时: {e}")
        return all_ids

    for pg in range(pages):
        _scroll_load_all(page, max_scrolls=8)
        events = page.evaluate(_EXTRACT_JS)
        for ev in events:
            row = _parse_event_row(ev, sport_code, fetch_date)
            if row and row['op_match_id'] not in all_ids:
                _match_rows.append(row)
                all_ids.append(row['op_match_id'])
                _parse_best_odds(ev, row['op_match_id'], fetch_date)

        if pg < pages - 1:
            # 翻页：找"下一页"按钮
            try:
                nxt = page.query_selector('[class*="next"],[aria-label="next page"],[class*="pagination"] a:last-child')
                if nxt:
                    nxt.click()
                    page.wait_for_timeout(3000)
                else:
                    break
            except Exception:
                break

    _flush_matches()
    _flush_odds()
    log.info(f"  {league_code}: {len(all_ids)} 场")
    return all_ids


# ─── 角球赔率专项 ────────────────────────────────────────────────────────────

# 各主要联赛的 OddsPortal corner 历史结果页路径（最近2赛季含角球赔率）
CORNER_LEAGUE_PATHS = [
    ("/soccer/england/premier-league/",          "england/premier-league"),
    ("/soccer/england/championship/",            "england/championship"),
    ("/soccer/germany/bundesliga/",              "germany/bundesliga"),
    ("/soccer/spain/laliga/",                    "spain/laliga"),
    ("/soccer/italy/serie-a/",                   "italy/serie-a"),
    ("/soccer/france/ligue-1/",                  "france/ligue-1"),
    ("/soccer/netherlands/eredivisie/",          "netherlands/eredivisie"),
    ("/soccer/portugal/liga-nos/",               "portugal/liga-nos"),
    ("/soccer/turkey/super-lig/",                "turkey/super-lig"),
    ("/soccer/brazil/serie-a/",                  "brazil/serie-a"),
    ("/soccer/argentina/primera-division/",      "argentina/primera-division"),
    ("/soccer/usa/mls/",                         "usa/mls"),
]

_CORNER_ODDS_JS = """() => {
    // OddsPortal 角球 tab 赔率提取
    const rows = document.querySelectorAll('[class*="oddsCell"],[class*="OddsCell"],[data-bookmaker-id]');
    const result = [];
    rows.forEach(r => {
        const bm = r.querySelector('[class*="bookmakerName"],[class*="name"],[class*="Logo"]');
        const bmName = bm ? bm.innerText.trim() || bm.getAttribute('title') : '';
        const cells = r.querySelectorAll('[class*="oddsVal"],[class*="odds-cell"],[class*="OddsVal"]');
        const vals = Array.from(cells).map(c => c.innerText.trim()).filter(x => x && /^[\d.]+$/.test(x));
        if (bmName && vals.length >= 2) {
            result.push({bm: bmName, over: vals[0], line: vals[1] || '', under: vals[2] || ''});
        }
    });
    return result;
}"""


def fetch_match_corner_odds(page, op_match_id: str, match_href: str, fetch_date: str):
    """
    从即将/进行中场次提取 Over/Under 市场里的角球赔率。
    OddsPortal 历史赛事无角球 tab；本函数仅适用于近期场次。
    策略: 导航到比赛页 → dispatchEvent 点 Over/Under → 提取含 Corners 关键字的行
    """
    # 清理 href 中的 # hash 片段
    base_url = match_href.split('#')[0].rstrip('/')
    if not base_url or 'oddsportal' not in base_url:
        return
    try:
        page.goto(base_url, wait_until='networkidle', timeout=25000)
        page.wait_for_timeout(4000)
        # 显示隐藏 tab 并点击 Over/Under
        page.evaluate("""() => {
            document.querySelectorAll('.hide-menu').forEach(el => el.style.display='flex');
            const links = Array.from(document.querySelectorAll('a')).filter(a => (a.innerText||'').trim()==='Over/Under');
            if (links.length) links[0].dispatchEvent(new MouseEvent('click', {bubbles: true}));
        }""")
        page.wait_for_timeout(3000)
        rows = page.evaluate(_CORNER_ODDS_JS) or []
    except Exception as e:
        log.debug(f"    corner odds {op_match_id}: {e}")
        return

    def to_dec(s):
        try:
            v = float(s)
            return v if v >= 1.01 else None
        except Exception:
            return None

    for row in rows[:20]:
        bm   = row.get('bm', 'unknown')
        over = to_dec(row.get('over', ''))
        under= to_dec(row.get('under', ''))
        line_str = row.get('line', '')

        if over:
            _odds_rows.append({
                "op_match_id": op_match_id,
                "market": "corners_total",
                "bookmaker": bm,
                "outcome": f"over {line_str}".strip(),
                "odds_value": over,
                "is_closing": 0,
                "fetch_date": fetch_date,
            })
        if under:
            _odds_rows.append({
                "op_match_id": op_match_id,
                "market": "corners_total",
                "bookmaker": bm,
                "outcome": f"under {line_str}".strip(),
                "odds_value": under,
                "is_closing": 0,
                "fetch_date": fetch_date,
            })


def fetch_corner_odds_by_league(page, league_path: str, league_code: str,
                                fetch_date: str, pages: int = 2):
    """
    从联赛结果页抓取比赛列表。
    注：OddsPortal 历史场次无角球市场 tab，仅落库比赛基础信息。
    """
    url = f"{BASE}{league_path}results/"
    log.info(f"  [角球列表] {league_code}: {url}")
    try:
        page.goto(url, wait_until='networkidle', timeout=30000)
        page.wait_for_timeout(5000)
        # 显示隐藏的 hide-menu（让市场 tab 进入 DOM，不影响数据提取）
        page.evaluate("document.querySelectorAll('.hide-menu').forEach(el => el.style.display='flex')")
    except Exception as e:
        log.warning(f"  角球联赛页超时 {league_code}: {e}")
        return 0

    all_ids = []
    for pg in range(pages):
        _scroll_load_all(page, max_scrolls=8)
        events = page.evaluate(_EXTRACT_JS) or []
        for ev in events:
            row = _parse_event_row(ev, "football", fetch_date)
            if row and row['op_match_id'] not in all_ids:
                _match_rows.append(row)
                all_ids.append(row['op_match_id'])
                _parse_best_odds(ev, row['op_match_id'], fetch_date)

        _flush_matches()
        _flush_odds()

        if pg < pages - 1:
            try:
                nxt = page.query_selector('[class*="next"],[aria-label="next page"]')
                if nxt:
                    nxt.click()
                    page.wait_for_timeout(3000)
                else:
                    break
            except Exception:
                break

    log.info(f"  {league_code}: {len(all_ids)} 场写入")
    return len(all_ids)


# ─── 主入口 ───────────────────────────────────────────────────────────────────
def run(fetch_odds: bool = False, fetch_leagues: bool = False, fetch_corners: bool = False):
    init_tables()
    fetch_date = datetime.now().strftime("%Y-%m-%d")
    log.info(f"🌐 OddsPortal Playwright 抓取开始 [{fetch_date}]")

    pw, browser, ctx = _make_browser()
    page = ctx.new_page()

    try:
        # 1. 今日全量比赛
        total_ids = []
        for sport, sport_code in SPORT_PAGES:
            log.info(f"\n{'⚽' if sport=='football' else '🏀'} {sport}")
            ids = fetch_sport_matches(page, sport, sport_code, fetch_date, fetch_odds=fetch_odds)
            total_ids.extend(ids)
            time.sleep(2)

        # 2. 主要联赛历史赛果（可选）
        if fetch_leagues:
            from leagues import FOOTBALL_LEAGUES, BASKETBALL_LEAGUES
            for path, code in list(FOOTBALL_LEAGUES.items())[:10]:
                fetch_league_results(page, path, code, "football", fetch_date, pages=2)
                time.sleep(2)
            for path, code in list(BASKETBALL_LEAGUES.items())[:5]:
                fetch_league_results(page, path, code, "basketball", fetch_date, pages=2)
                time.sleep(2)

        # 3. 角球历史赔率（可选）
        if fetch_corners:
            log.info("\n⚽ 角球赔率专项抓取")
            for path, code in CORNER_LEAGUE_PATHS:
                fetch_corner_odds_by_league(page, path, code, fetch_date, pages=2)
                time.sleep(2)

    finally:
        page.close()
        browser.close()
        pw.stop()

    # 统计
    import sqlite3
    conn = sqlite3.connect(engine.url.database, timeout=30)
    m_cnt = conn.execute("SELECT COUNT(*) FROM oddsportal_matches WHERE fetch_date=?", (fetch_date,)).fetchone()[0]
    o_cnt = conn.execute("SELECT COUNT(*) FROM oddsportal_odds WHERE fetch_date=?", (fetch_date,)).fetchone()[0]
    conn.close()

    log.info(f"\n{'='*55}")
    log.info(f"✅ OddsPortal 抓取完成 [{fetch_date}]")
    log.info(f"   比赛: {m_cnt} 场")
    log.info(f"   赔率: {o_cnt} 条")
    log.info(f"{'='*55}")
    return m_cnt, o_cnt


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--odds', action='store_true', help='抓取各庄详细赔率')
    ap.add_argument('--leagues', action='store_true', help='抓取联赛历史赛果')
    ap.add_argument('--corners', action='store_true', help='抓取角球历史赔率(12大联赛)')
    args = ap.parse_args()
    run(fetch_odds=args.odds, fetch_leagues=args.leagues, fetch_corners=args.corners)
