# 22_fbref_scraper.py — FBref 高级统计爬虫
# 数据：xG/xGA、射门、传球、逼抢、控球率（StatsBomb质量）
# 覆盖：五大联赛 + 欧冠/欧联，nodriver + 真实Chrome用户数据绕过Cloudflare
import sys, os, time, logging, re, argparse, asyncio, shutil, tempfile
from bs4 import BeautifulSoup
from datetime import datetime
from sqlalchemy import create_engine, text

import env_setup
from config import DB_ENGINE_URL

# 防止 nodriver websocket 并发读取导致 AssertionError: cannot call get() concurrently
_page_lock = asyncio.Lock()
from db_utils import batch_upsert, exec_ddl

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

from sqlalchemy import MetaData

def _get_table(engine, table_name):
    md = MetaData()
    md.reflect(bind=engine)
    return md.tables[table_name]
engine = create_engine(DB_ENGINE_URL)

# 全局浏览器实例
_browser = None
_tmp_profile_dir = None

_CF_MARKERS = [
    'Just a moment',
    '请稍候',
    '_cf_chl_opt',
    'cf-turnstile',
    'challenges.cloudflare.com',
    '正在进行安全验证',
]

def _is_cf_challenge(html):
    """检测是否仍被 Cloudflare 拦截"""
    check = html[:5000]
    return any(m in check for m in _CF_MARKERS)


def _make_profile_with_cookies():
    """
    从 Chrome 默认配置文件复制 Cookies 到临时目录，
    让 nodriver 携带已有 Cookie 启动，提高 Cloudflare 信任度。
    """
    chrome_default = os.path.expanduser(
        r'~\AppData\Local\Google\Chrome\User Data\Default'
    )
    # Chrome 96+ stores cookies under Default\Network\Cookies
    cookies_src = os.path.join(chrome_default, 'Network', 'Cookies')
    if not os.path.isfile(cookies_src):
        cookies_src = os.path.join(chrome_default, 'Cookies')
    if not os.path.isfile(cookies_src):
        return None

    tmp_dir = tempfile.mkdtemp(prefix='fbref_chrome_')
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
        log.info('=' * 60)
        log.info('nodriver 浏览器已启动（携带真实 Chrome Cookie）')
        log.info('如果出现 Cloudflare 验证，请在弹出的 Chrome 窗口中手动完成')
        log.info('=' * 60)
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


async def _safe_get_content(page, retries=3):
    """带 lock + 重试的 get_content()，防止 websocket 并发断言错误"""
    for i in range(retries):
        try:
            async with _page_lock:
                return await page.get_content()
        except AssertionError:
            await asyncio.sleep(1 + i)
    return ""


async def _get_html_async(url, delay=20):
    """nodriver 获取页面 HTML，正确检测 Cloudflare 拦截"""
    browser = await _get_browser()
    try:
        page = await browser.get(url)
        await asyncio.sleep(6)
        html = await _safe_get_content(page)

        # 等待 Cloudflare 验证通过（最多 5 分钟）
        wait_count = 0
        while _is_cf_challenge(html) and wait_count < 60:
            wait_count += 1
            if wait_count % 6 == 1:
                elapsed = wait_count * 5
                log.info(f'⏳ 等待 Cloudflare 验证... (已等 {elapsed}秒) — 请在 Chrome 窗口中手动完成')
            await asyncio.sleep(5)
            html = await _safe_get_content(page)

        if _is_cf_challenge(html):
            log.warning(f'✗ Cloudflare 验证超时: {url[:80]}')
            return None

        # CF 通过后等待真实页面加载（CF 重定向页本身很小，真实 FBref 页 > 100KB）
        # 最多等 90 秒（18×5s），每次都 scroll 触发懒加载
        size_wait = 0
        while len(html) < 50000 and size_wait < 18:
            size_wait += 1
            if size_wait % 3 == 1:
                log.info(f'  ⏳ 等待页面渲染... ({len(html)} chars, {size_wait*5}s)')
            try:
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            except Exception:
                pass
            await asyncio.sleep(5)
            html = await _safe_get_content(page)

        log.info(f'  ✓ 页面加载成功 ({len(html)} chars)')
        await asyncio.sleep(delay)
        return html
    except Exception as e:
        log.warning(f'请求失败: {e}')
        return None


# 同步包装，让下面的 fetch_* 函数保持同步接口
_loop = None

def _get_html(url, delay=20):
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(_get_html_async(url, delay))

# comp_id → league name（comp_id 来自 fbref.com/en/comps/ 官方赛事索引，2026-07-12核对）
LEAGUES = {
    9:  'England - Premier League',
    12: 'Spain - La Liga',
    11: 'Italy - Serie A',
    20: 'Germany - Bundesliga',
    13: 'France - Ligue 1',
    8:  'Europe - Champions League',
    19: 'Europe - Europa League',
    10: 'England - Championship',
    22: 'USA - MLS',
    24: 'Brazil - Brasileirao',
    21: 'Argentina - Primera Division',
    # ── 美洲扩展 ──────────────────────────────────────
    31:  'Mexico - Liga MX',
    41:  'Colombia - Categoria Primera A',
    38:  'Brazil - Serie B',
    # ── 亚洲扩展（fetch_match_xg 用的 schedule 页不受Stathead付费墙影响，
    #   已用 J1 League 实测验证：380场真实xG数据，2026-07-12） ──────
    25:  'Japan - J1 League',
    55:  'South Korea - K League 1',
    62:  'China - Super League',
    65:  'Australia - A-League',
    70:  'Saudi Arabia - Pro League',
    82:  'India - Super League',
    # ── 欧洲其他联赛扩展 ──────────────────────────────
    26:  'Turkey - Super Lig',
    23:  'Netherlands - Eredivisie',
    32:  'Portugal - Primeira Liga',
    36:  'Belgium - Pro League',
}


def init_tables():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS fbref_team_stats (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            season      TEXT,
            league_name TEXT,
            team        TEXT,
            games       INTEGER,
            xg          REAL,
            xga         REAL,
            xg_diff     REAL,
            shots       REAL,
            shots_on_target REAL,
            possession  REAL,
            passes_pct  REAL,
            prog_passes REAL,
            prog_carries REAL,
            pressures   REAL,
            fetch_date  TEXT,
            UNIQUE(season, league_name, team)
        )
    """)
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS fbref_match_stats (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            season      TEXT,
            league_name TEXT,
            match_date  TEXT,
            home_team   TEXT,
            away_team   TEXT,
            home_score  INTEGER,
            away_score  INTEGER,
            home_xg     REAL,
            away_xg     REAL,
            fetch_date  TEXT,
            UNIQUE(season, league_name, match_date, home_team, away_team)
        )
    """)


def fetch_squad_shooting(comp_id, league_name, season_str, fetch_date):
    """获取联赛球队统计（xG来自标准统计页，射门数来自射门页）"""
    # xG 在标准统计页 /stats/（table: stats_squads_standard_for, data-stat='xg'）
    # 射门数在射门页 /shooting/（table: stats_squads_shooting_for）
    # 为避免双倍请求，只抓标准统计页（含 xG + games，shots 从同页提取）
    url = f'https://fbref.com/en/comps/{comp_id}/stats/'
    html = _get_html(url)
    if not html:
        return 0

    html = re.sub(r'<!--(.*?)-->', r'\1', html, flags=re.DOTALL)
    soup = BeautifulSoup(html, 'html.parser')

    # 优先找标准统计表（含 xG），fallback 找任何含 xg 的表
    table = (soup.find('table', id=re.compile(r'stats_squads_standard_for'))
             or soup.find('table', id=re.compile(r'standard'))
             or next((t for t in soup.find_all('table') if 'xg' in str(t).lower()), None))
    if not table:
        log.warning(f'  标准统计表未找到 (comp={comp_id})')
        return 0

    log.info(f'  标准统计表 id={table.get("id","?")}')
    rows_to_insert = []
    tbody = table.find('tbody')
    if not tbody:
        log.warning(f'  标准统计表无tbody')
        return 0

    all_rows2 = tbody.find_all('tr')
    log.info(f'  标准统计 共{len(all_rows2)}行')
    for _r in all_rows2[:3]:
        _cells = _r.find_all(['td','th'])
        if len(_cells) >= 5:
            _stats = [(c.name, c.get('data-stat','?')) for c in _cells[:12]]
            log.info(f'  示例: {_stats}')
            break

    for row in all_rows2:
        if row.get('class') and 'thead' in row.get('class', []):
            continue
        cells = row.find_all(['td', 'th'])
        if len(cells) < 5:
            continue
        try:
            team_cell = (row.find('th', {'data-stat': 'team'})
                         or row.find('th', {'data-stat': 'squad'})
                         or row.find('td', {'data-stat': 'team'})
                         or row.find('td', {'data-stat': 'squad'}))
            if not team_cell:
                continue
            team = team_cell.get_text(strip=True)
            if not team:
                continue

            def _f(stat):
                c = row.find('td', {'data-stat': stat})
                if not c:
                    return None
                txt = c.get_text(strip=True)
                return float(txt) if txt else None

            xg    = _f('xg')
            games = _f('games')

            if xg is None:
                continue

            rows_to_insert.append({
                'season': season_str, 'league_name': league_name, 'team': team,
                'games': int(games) if games is not None else None,
                'xg': xg, 'fetch_date': fetch_date,
            })
        except Exception as ex:
            log.warning(f'行解析失败: {ex}')

    if rows_to_insert:
        log.info(f'  标准统计 ✓ {len(rows_to_insert)} 队')
        tbl = _get_table(engine, 'fbref_team_stats')
        batch_upsert(engine, tbl, rows_to_insert, ['season', 'league_name', 'team'])
    return len(rows_to_insert)


def fetch_match_xg(comp_id, league_name, season_str, fetch_date):
    """获取联赛逐场 xG 数据"""
    url = f'https://fbref.com/en/comps/{comp_id}/schedule/'
    html = _get_html(url)
    if not html:
        return 0

    html = re.sub(r'<!--(.*?)-->', r'\1', html, flags=re.DOTALL)
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table', id=re.compile(r'sched'))
    if not table:
        return 0

    rows_to_insert = []
    for row in table.find('tbody').find_all('tr'):
        if row.get('class') and 'thead' in row.get('class', []):
            continue
        try:
            def _td(stat):
                c = row.find('td', {'data-stat': stat})
                return c.get_text(strip=True) if c else ''

            date   = _td('date')
            home   = _td('home_team')
            away   = _td('away_team')
            score  = _td('score')
            h_xg   = _td('home_xg')
            a_xg   = _td('away_xg')

            if not date or not home or not away or not score:
                continue
            if '\u2013' not in score and '-' not in score:
                continue

            parts = re.split(r'[\u2013-]', score)
            if len(parts) != 2:
                continue
            hs, as_ = int(parts[0].strip()), int(parts[1].strip())

            rows_to_insert.append({
                'season': season_str, 'league_name': league_name, 'match_date': date,
                'home_team': home, 'away_team': away, 'home_score': hs, 'away_score': as_,
                'home_xg': float(h_xg) if h_xg else None,
                'away_xg': float(a_xg) if a_xg else None,
                'fetch_date': fetch_date,
            })
        except Exception:
            pass

    if rows_to_insert:
        tbl = _get_table(engine, 'fbref_match_stats')
        batch_upsert(engine, tbl, rows_to_insert,
                     ['season', 'league_name', 'match_date', 'home_team', 'away_team'])
    return len(rows_to_insert)


def _run(fetch_date=None):
    if not fetch_date:
        fetch_date = datetime.now().strftime('%Y-%m-%d')

    init_tables()
    log.info('=' * 60)
    log.info(f'FBref 爬虫启动（nodriver + 真实Chrome Cookie） [{fetch_date}]')
    log.info('=' * 60)

    total_team = total_match = 0
    # schedule页URL不带赛季会自动指向最新赛季，这里只是给season字段打标签；
    # 之前写死'2025-26'，新赛季开始(8月)后标签就会过期，改成按日期动态算
    _now = datetime.now()
    _start = _now.year if _now.month >= 8 else _now.year - 1
    season_str = f'{_start}-{str(_start + 1)[-2:]}'

    # Bug修复(2026-07-20)：fetch_squad_shooting() 抓的 /stats/ 页 xG 列已被 Stathead
    # 付费墙下线（跟 11_fbref_xg_scraper.py 是同一个已知坑，见 feedback_fbref_xg_paywall），
    # 实测 fbref_team_stats 表历史总行数=0——从未成功写入过一行。但每个联赛仍会为它
    # 走一次完整 nodriver 页面加载（固定 6s+20s sleep 起步，24个联赛≥600s），是1800s
    # 超时预算里白白烧掉且从无产出的部分，予以跳过。如果日后付费墙解除或找到免费替代
    # 页面，可参考 fetch_squad_shooting() 的实现重新接入。
    for comp_id, league_name in LEAGUES.items():
        log.info(f'--- {league_name} ---')
        mc = fetch_match_xg(comp_id, league_name, season_str, fetch_date)
        if mc:
            log.info(f'  [逐场xG] ✓ {mc} 场')
            total_match += mc

    log.info(f'FBref 完成: {total_match} 场比赛xG')
    return total_match


def run(fetch_date=None, seasons=None):
    global _loop
    try:
        return _run(fetch_date)
    finally:
        if _loop and not _loop.is_closed():
            try:
                _loop.run_until_complete(_shutdown_browser())
            except Exception:
                pass
            _loop.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--date', default=None)
    args = p.parse_args()
    run(fetch_date=args.date)
