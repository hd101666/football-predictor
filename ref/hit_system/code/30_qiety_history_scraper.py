#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
企鹅体育 YB 历史赛果 Playwright 爬虫
=====================================
策略：
  1. Playwright 打开 YB 平台（user-pc-new.lvjida8.com）
  2. 拦截所有到 api.fgqinxg.com / api.bvl8bs5.com 的请求
  3. 点击"结果"标签，按日期翻页
  4. 解码 gzip+base64 响应，提取历史比赛+比分
  5. 写入 qiety_history 表

用法：
  python 30_qiety_history_scraper.py --days 7      # 抓最近7天
  python 30_qiety_history_scraper.py --days 30     # 抓最近30天
  python 30_qiety_history_scraper.py --headless    # 无界面模式
"""
import sys, os, json, time, base64, gzip, hashlib, re, sqlite3, argparse
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(_BASE_DIR, "data", "sports_data.db")
TOKEN_FILE = os.path.join(_BASE_DIR, ".qiety_token.json")
# sanitized: 允许用环境变量 QIETY_TOKEN 直接提供 token（原实现只读 token 文件）
_ENV_TOKEN = os.environ.get("QIETY_TOKEN", "")
STORAGE_FILE = os.path.join(_BASE_DIR, ".qiety_storage.json")
ACCOUNT_FILE = os.path.join(_BASE_DIR, ".qiety_account.json")
TZ_BJ = timezone(timedelta(hours=8))

# API 域名（拦截这些域名的请求）
API_DOMAINS = ["api.fgqinxg.com", "api.bvl8bs5.com", "api."]

# qiety 可用域名（按优先级）
QIETY_DOMAINS = [
    "https://www.qiety1748.vip",
    "https://www.qiety1692.vip",
    "https://www.qiety1726.vip",
    "https://h5.qiety.vip",
]


# ─── 工具函数 ────────────────────────────────────────────

def load_storage():
    if os.path.exists(STORAGE_FILE):
        return json.load(open(STORAGE_FILE, encoding='utf-8'))
    return {}

def get_yb_url():
    """从 storage 提取 YB 平台 URL（含 token）"""
    storage = load_storage()
    for origin in storage.get('origins', []):
        for item in origin.get('localStorage', []):
            if item['name'] == 'server-cache-venue':
                try:
                    d = json.loads(item['value'])
                    if isinstance(d, list): d = d[0]
                    url = d['data']['data']['data'].get('url') or d['data']['data']['data'].get('token')
                    if url and 'user-pc-new' in url:
                        return url
                except:
                    pass
    return None

def get_qiety_cookies():
    """返回 Playwright 格式的 cookie 列表"""
    storage = load_storage()
    result = []
    for c in storage.get('cookies', []):
        result.append({
            "name":     c["name"],
            "value":    c["value"],
            "domain":   c["domain"],
            "path":     c.get("path", "/"),
            "secure":   c.get("secure", False),
            "httpOnly": c.get("httpOnly", False),
        })
    return result

def decode_yb_response(body_bytes):
    """解码 YB API 的 gzip+base64 响应体"""
    try:
        d = json.loads(body_bytes)
        if d.get("code") != "0000000":
            return None
        return json.loads(gzip.decompress(base64.b64decode(d["data"])))
    except:
        return None

def ts_to_date(ts_ms):
    """毫秒时间戳 → 北京时间日期字符串"""
    try:
        return datetime.fromtimestamp(int(ts_ms) / 1000, tz=TZ_BJ).strftime("%Y-%m-%d %H:%M")
    except:
        return ""


# ─── 数据库 ──────────────────────────────────────────────

def init_db(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS qiety_history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id    TEXT NOT NULL,
            sport       TEXT,
            league      TEXT,
            home_team   TEXT,
            away_team   TEXT,
            kickoff     TEXT,
            home_score  INTEGER,
            away_score  INTEGER,
            status      TEXT,
            fetch_date  TEXT,
            scraped_at  TEXT,
            UNIQUE(match_id)
        );
        CREATE INDEX IF NOT EXISTS idx_qh_mid   ON qiety_history(match_id);
        CREATE INDEX IF NOT EXISTS idx_qh_date  ON qiety_history(fetch_date);
        CREATE INDEX IF NOT EXISTS idx_qh_sport ON qiety_history(sport);
    """)
    conn.commit()

def upsert_history(conn, records):
    now = datetime.now(TZ_BJ).strftime("%Y-%m-%d %H:%M:%S")
    n = 0
    for r in records:
        try:
            conn.execute("""
                INSERT INTO qiety_history
                    (match_id, sport, league, home_team, away_team,
                     kickoff, home_score, away_score, status, fetch_date, scraped_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(match_id) DO UPDATE SET
                    home_score=excluded.home_score,
                    away_score=excluded.away_score,
                    status=excluded.status,
                    scraped_at=excluded.scraped_at
            """, (r['match_id'], r['sport'], r['league'], r['home'], r['away'],
                  r['kickoff'], r.get('hs'), r.get('as_'), r.get('status','FT'),
                  r['kickoff'][:10] if r['kickoff'] else None, now))
            n += 1
        except Exception as e:
            pass
    conn.commit()
    return n


# ─── 解析历史比赛数据 ────────────────────────────────────

def parse_result_matches(data, sport="football"):
    """
    解析 structureTournamentMatchesPB / getMatchResultListPB 等接口返回的历史数据
    支持多种可能的字段结构
    """
    records = []

    def extract_match(item):
        mid  = str(item.get("mids") or item.get("mid") or item.get("matchId") or "")
        home = item.get("mhn") or item.get("homeTeamName") or item.get("home") or ""
        away = item.get("man") or item.get("awayTeamName") or item.get("away") or ""
        tn   = item.get("tn") or item.get("leagueName") or item.get("league") or ""
        mgt  = item.get("mgt") or item.get("matchTime") or ""
        hs   = item.get("mhs") if item.get("mhs") is not None else item.get("homeScore")
        as_  = item.get("mas") if item.get("mas") is not None else item.get("awayScore")
        # 有时候比分在 msc 字段（"score": "2:1"）
        if hs is None and item.get("msc"):
            msc = str(item["msc"])
            m = re.search(r'(\d+)[:\-](\d+)', msc)
            if m:
                hs, as_ = int(m.group(1)), int(m.group(2))
        kickoff = ts_to_date(mgt) if mgt else ""
        status  = item.get("mst") or item.get("status") or "FT"
        if not mid or not home:
            return None
        return {
            "match_id": mid, "sport": sport,
            "league": tn, "home": home, "away": away,
            "kickoff": kickoff, "hs": hs, "as_": as_, "status": status,
        }

    # 处理多种嵌套结构
    def walk(obj):
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict):
                    r = extract_match(item)
                    if r and r["match_id"]:
                        records.append(r)
                    else:
                        walk(item)
        elif isinstance(obj, dict):
            # 常见的容器键
            for key in ["finisheddata", "resultdata", "livedata", "nolivedata",
                        "data", "list", "matches", "items", "rows"]:
                if key in obj and isinstance(obj[key], list):
                    for item in obj[key]:
                        r = extract_match(item)
                        if r and r["match_id"]:
                            records.append(r)

    walk(data)
    return records


# ─── 登录 qiety.vip ─────────────────────────────────────

def login_qiety(page, acct, pwd):
    """尝试登录 qiety.vip，返回成功的域名或 None"""
    for domain in QIETY_DOMAINS:
        print(f"  [登录] 尝试 {domain}")
        try:
            page.goto(domain, wait_until="domcontentloaded", timeout=60000)
            time.sleep(3)
        except Exception as e:
            print(f"    ⚠ 加载失败: {e}")
            continue

        # 点登录入口
        for txt in ["登录/注册后查看", "登录", "登 录", "注册登录"]:
            try:
                el = page.query_selector(f"text={txt}")
                if el and el.is_visible():
                    el.click(timeout=3000); time.sleep(2); break
            except: pass

        # 找账号/密码框
        user_inp = page.query_selector("input[type=text], input[placeholder*=账号], input[placeholder*=用户]")
        pass_inp = page.query_selector("input[type=password]")
        if not user_inp:
            vis = [i for i in page.query_selector_all("input") if i.is_visible()]
            user_inp = vis[0] if len(vis) >= 2 else None
            pass_inp = vis[1] if len(vis) >= 2 else pass_inp

        if user_inp and pass_inp:
            try:
                user_inp.fill(acct); time.sleep(0.3)
                pass_inp.fill(pwd);  time.sleep(0.3)
                # 提交
                submitted = False
                for sel in ["button[type=submit]", "text=登录", "text=登 录", "[class*=login-btn]", "[class*=loginBtn]"]:
                    try:
                        btn = page.query_selector(sel)
                        if btn and btn.is_visible():
                            btn.click(timeout=3000); submitted = True; break
                    except: pass
                if not submitted:
                    page.keyboard.press("Enter")
                time.sleep(5)
                # 验证
                body = page.inner_text("body")
                if len(body) > 200 and "登录/注册后查看" not in body:
                    print(f"    ✅ 登录成功 → {domain}")
                    return domain
            except Exception as e:
                print(f"    ⚠ 填写失败: {e}")

    return None


# ─── 主抓取逻辑 ──────────────────────────────────────────

def run_scraper(days=7, headless=True, sport_ids=None):
    if sport_ids is None:
        sport_ids = ["1", "2"]

    SPORTS = {
        "1": {"euid": "3020101", "mi": "101201", "name": "足球", "code": "football"},
        "2": {"euid": "3020102", "mi": "102201", "name": "篮球", "code": "basketball"},
    }

    tok = json.load(open(TOKEN_FILE, encoding='utf-8'))
    yb_url = get_yb_url()
    acct_info = json.load(open(ACCOUNT_FILE, encoding='utf-8')) if os.path.exists(ACCOUNT_FILE) else {}

    print(f"{'='*60}")
    print(f"  qiety YB 历史赛果爬虫")
    print(f"  目标: 最近 {days} 天  运动: {[SPORTS[s]['name'] for s in sport_ids]}")
    print(f"  模式: {'无界面' if headless else '有界面'}")
    print(f"{'='*60}")

    captured_responses = []   # 所有拦截到的解码响应

    def on_response(resp):
        """拦截 YB API 响应"""
        url = resp.url
        if not any(d in url for d in API_DOMAINS):
            return
        if resp.status != 200:
            return
        try:
            body = resp.body()
            decoded = decode_yb_response(body)
            if decoded:
                captured_responses.append({
                    "url": url,
                    "data": decoded,
                    "ts": datetime.now(TZ_BJ).isoformat(),
                })
                # 提取接口名
                ep = url.split("/w/")[-1].split("?")[0] if "/w/" in url else url.split("/")[-1].split("?")[0]
                print(f"  📡 捕获: {ep}")
        except:
            pass

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)
    total_written = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled",
                  "--disable-web-security", "--ignore-certificate-errors"],
        )
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            ignore_https_errors=True,
        )
        # 注入 qiety cookies（让网站认为已登录）
        cookies = get_qiety_cookies()
        if cookies:
            ctx.add_cookies(cookies)

        page = ctx.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
            window.chrome={runtime:{},loadTimes:function(){},csi:function(){},app:{}};
        """)
        page.on("response", on_response)

        # ── 步骤1：打开 qiety1748 → 进入体育平台 ──────────
        yb_opened = False

        # 先尝试直接导航到 qiety1748（cookie 已注入，可能直接进入已登录态）
        QIETY_MAIN = "https://www.qiety1748.vip"
        print(f"\n[Step1] 打开 {QIETY_MAIN} ...")
        try:
            page.goto(QIETY_MAIN, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
            body_txt = page.inner_text("body")
            print(f"  内容片段: {body_txt[:80].replace(chr(10),' ')}")

            # 关闭可能出现的弹窗（"确定"/"OK" 按钮）
            for btn_txt in ["确定", "OK", "好的", "关闭", "知道了"]:
                try:
                    btn = page.query_selector(f"button:has-text('{btn_txt}'), [class*=btn]:has-text('{btn_txt}')")
                    if btn and btn.is_visible():
                        btn.click(timeout=2000); time.sleep(1)
                        print(f"  关闭弹窗: {btn_txt}")
                        break
                except: pass

            # 如果需要登录
            body_txt = page.inner_text("body")
            if any(k in body_txt for k in ["登录", "Login", "注册", "失效"]):
                print("  需要登录，填写账号...")
                acct = acct_info.get("username") or os.environ.get("QIETY_ACCOUNT", "")
                pwd  = acct_info.get("password") or os.environ.get("QIETY_PASSWORD", "")

                # 点登录/注册入口按钮
                for login_kw in ["登录/注册", "登录", "注册登录", "立即登录", "Login"]:
                    try:
                        el = page.query_selector(
                            f"a:has-text('{login_kw}'), button:has-text('{login_kw}'), "
                            f"span:has-text('{login_kw}'), div[class*=login]:has-text('{login_kw}')"
                        )
                        if el and el.is_visible():
                            el.click(timeout=3000); time.sleep(2); print(f"  点击 {login_kw}"); break
                    except: pass

                # 找输入框并填写
                for _ in range(3):
                    inputs = [i for i in page.query_selector_all("input") if i.is_visible()]
                    if len(inputs) >= 2:
                        inputs[0].fill(acct); time.sleep(0.3)
                        inputs[1].fill(pwd);  time.sleep(0.3)
                        # 找登录按钮
                        submitted = False
                        for sel in ["button[type=submit]", "button:has-text('登录')",
                                    "button:has-text('确认')", "[class*=login-btn]", "[class*=loginBtn]"]:
                            try:
                                btn = page.query_selector(sel)
                                if btn and btn.is_visible():
                                    btn.click(timeout=3000); submitted = True; break
                            except: pass
                        if not submitted:
                            page.keyboard.press("Enter")
                        time.sleep(5)
                        break
                    time.sleep(2)

                body_txt = page.inner_text("body")
                print(f"  登录后: {body_txt[:80].replace(chr(10),' ')}")

            # 找体育/YB 入口
            for kw in ["体育", "企鹅体育", "YB", "YBTY", "滚球"]:
                try:
                    el = page.query_selector(f"text={kw}")
                    if el and el.is_visible():
                        el.click(timeout=5000)
                        print(f"  点击体育入口: {kw}")
                        time.sleep(6)
                        break
                except: pass

            # 检查是否进入了 YB 平台（可能在 iframe 里）
            for frame in page.frames:
                if "user-pc-new" in (frame.url or "") or "lvjida8" in (frame.url or ""):
                    print(f"  ✅ 找到 YB iframe: {frame.url[:80]}")
                    page = frame
                    yb_opened = True
                    break

            if not yb_opened:
                body_txt = page.inner_text("body")
                if any(k in body_txt for k in ["足球", "篮球", "结果", "赔率", "滚球"]):
                    print("  ✅ 直接进入体育页面")
                    yb_opened = True
                else:
                    print(f"  内容: {body_txt[:200].replace(chr(10),' ')}")
        except Exception as e:
            print(f"  ⚠ qiety1748 加载失败: {e}")

        # 若上面失败，尝试直接用 YB token URL
        if not yb_opened and yb_url:
            print(f"\n[Step1b] 尝试直接 YB token URL...")
            try:
                page.goto(yb_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(5)
                body_txt = page.inner_text("body")
                if any(k in body_txt for k in ["足球", "篮球", "结果", "赔率"]):
                    print("  ✅ YB URL 成功")
                    yb_opened = True
                else:
                    print(f"  内容: {body_txt[:100].replace(chr(10),' ')}")
            except Exception as e:
                print(f"  ⚠ YB URL 失败: {e}")

        if not yb_opened:
            # ── 步骤1c：多域名登录 ──────────────────────
            print("\n[Step1c] 尝试其它域名登录...")
            acct = acct_info.get("username") or os.environ.get("QIETY_ACCOUNT", "")
            pwd  = acct_info.get("password") or os.environ.get("QIETY_PASSWORD", "")
            domain = login_qiety(page, acct, pwd)
            if not domain:
                print("  ❌ 所有登录方式均失败，截图后退出")
                try: page.screenshot(path=os.path.join(_BASE_DIR, "_login_fail.png"))
                except: pass
                browser.close()
                return 0
            # 找并点击 YB 体育入口
            time.sleep(3)
            for kw in ["体育", "企鹅体育", "YBTY", "YB", "滚球", "足球"]:
                try:
                    el = page.query_selector(f"text={kw}")
                    if el and el.is_visible():
                        el.click(timeout=3000); time.sleep(5)
                        print(f"  点击 '{kw}'")
                        break
                except: pass
            # 切换到 iframe（如果有）
            for frame in page.frames[1:]:
                if "user-pc-new" in (frame.url or "") or "lvjida8" in (frame.url or ""):
                    print(f"  ✅ 进入 YB iframe: {frame.url[:60]}")
                    page = frame
                    break

        # ── 步骤2：找"结果"标签并点击 ──────────────────
        print('\n[Step2] 寻找"结果"标签...')
        result_tab_clicked = False
        for attempt in range(3):
            for selector in [
                "text=结果", "text=已结束", "text=赛果",
                "[class*=result]", "[class*=Result]",
                "li:has-text('结果')", "a:has-text('结果')",
                "span:has-text('结果')", "div:has-text('结果')",
            ]:
                try:
                    el = page.query_selector(selector)
                    if el and el.is_visible():
                        el.click(timeout=3000)
                        time.sleep(3)
                        print(f"  ✅ 点击: {selector}")
                        result_tab_clicked = True
                        break
                except: pass
            if result_tab_clicked:
                break
            print(f"  第{attempt+1}次未找到结果标签，等待...")
            time.sleep(2)

        if not result_tab_clicked:
            print("  ⚠ 未找到结果标签，截图保存后继续尝试...")
            try:
                page.screenshot(path=os.path.join(_BASE_DIR, "_qiety_history_debug.png"))
                print("  截图已保存: _qiety_history_debug.png")
            except: pass

        # ── 步骤3：按日期翻页抓取 ───────────────────────
        print(f"\n[Step3] 翻页抓取最近 {days} 天历史数据...")
        now_bj = datetime.now(TZ_BJ)

        for day_offset in range(1, days + 1):
            target_date = (now_bj - timedelta(days=day_offset)).strftime("%Y-%m-%d")
            print(f"\n  [{day_offset}/{days}] 抓取 {target_date}...")
            captured_responses.clear()

            # 找日期选择器或"前一天"按钮
            date_navigated = False

            # 策略A: 找日期输入框
            for sel in ["input[type=date]", "[class*=date-picker]", "[class*=datePicker]"]:
                try:
                    el = page.query_selector(sel)
                    if el and el.is_visible():
                        el.fill(target_date); time.sleep(0.5)
                        page.keyboard.press("Enter"); time.sleep(3)
                        date_navigated = True
                        print(f"    日期选择器: {target_date}")
                        break
                except: pass

            # 策略B: 找"前一天"箭头按钮（连点）
            if not date_navigated:
                # 先找"今日"或"昨天"重置
                if day_offset == 1:
                    for txt in ["昨天", "昨日", "yesterday"]:
                        try:
                            el = page.query_selector(f"text={txt}")
                            if el and el.is_visible():
                                el.click(timeout=2000); time.sleep(2)
                                date_navigated = True; break
                        except: pass

                if not date_navigated:
                    # 点"上一天"箭头
                    for arrow_sel in [
                        "button[class*=prev]", "button[class*=left]",
                        "[class*=arrow-left]", "[class*=prev-day]",
                        "i[class*=left]", "span[class*=prev]",
                        "[aria-label*=上一]", "[aria-label*=prev]",
                        "text=<", "text=‹", "text=←",
                    ]:
                        try:
                            btns = page.query_selector_all(arrow_sel)
                            if btns:
                                # 对每个 day_offset 点对应次数
                                clicks_needed = day_offset if day_offset == 1 else 1
                                for _ in range(clicks_needed):
                                    btns[0].click(timeout=2000)
                                    time.sleep(0.5)
                                date_navigated = True
                                print(f"    点击箭头 {arrow_sel}")
                                time.sleep(3)
                                break
                        except: pass

            # 等待数据加载
            time.sleep(4)

            # 滚动页面触发懒加载
            for _ in range(3):
                page.evaluate("window.scrollBy(0, 500)")
                time.sleep(1)
            page.evaluate("window.scrollTo(0, 0)")
            time.sleep(1)

            # 解析已捕获的响应
            if captured_responses:
                print(f"    捕获 {len(captured_responses)} 个API响应")
                for resp_info in captured_responses:
                    ep = resp_info["url"].split("/w/")[-1].split("?")[0]
                    data = resp_info["data"]

                    # 判断运动类型（根据请求URL或数据内容）
                    sport = "football"
                    if "sport=2" in resp_info["url"] or "euid=3020102" in resp_info["url"]:
                        sport = "basketball"

                    records = parse_result_matches(data, sport)
                    if records:
                        n = upsert_history(conn, records)
                        total_written += n
                        print(f"      {ep}: {len(records)} 场 → 写入 {n} 条")
            else:
                print(f"    ⚠ 无API响应捕获，尝试解析DOM...")
                # DOM 降级解析：提取页面中的比赛信息
                try:
                    dom_records = parse_dom_matches(page, target_date)
                    if dom_records:
                        n = upsert_history(conn, dom_records)
                        total_written += n
                        print(f"      DOM解析: {len(dom_records)} 场 → 写入 {n} 条")
                    else:
                        print("      DOM未提取到数据")
                except Exception as e:
                    print(f"      DOM解析失败: {e}")

        # ── 步骤4：直接调用API补充抓取 ──────────────────
        print(f"\n[Step4] API直接补充抓取（每运动每天）...")
        # 这里利用已知的 requestId 和 CUID 直接调用 API
        try:
            import urllib.request, ssl
            _SSL = ssl.create_default_context()
            _SSL.check_hostname = False
            _SSL.verify_mode = ssl.CERT_NONE

            rid  = tok["requestId"]
            cuid = tok["cuid"]

            def make_hdr():
                ts = int(time.time() * 1000)
                md5p = hashlib.md5(f"{cuid}-{ts}".encode()).hexdigest()
                return {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Origin": "https://user-pc-new.lvjida8.com",
                    "Referer": "https://user-pc-new.lvjida8.com/",
                    "User-Agent": "Mozilla/5.0",
                    "checkId": f"pc-{md5p}-{cuid}-{ts}",
                    "lang": "zh",
                    "request-code": '{"panda-bss-source":"2"}',
                    "requestId": rid,
                }, ts

            API_V2 = "https://api.fgqinxg.com/yewu11/v2/w"

            for sid, scfg in [("1", SPORTS["1"]), ("2", SPORTS["2"])]:
                if sid not in sport_ids:
                    continue

                # structureTournamentMatchesPB 在未开赛模式下，finisheddata 可能存在
                headers, ts = make_hdr()
                body = json.dumps({"cuid": cuid, "euid": scfg["euid"],
                                   "sportId": sid, "mi": scfg["mi"]}).encode()
                req = urllib.request.Request(f"{API_V2}/structureTournamentMatchesPB?t={ts}",
                                              data=body, headers=headers, method="POST")
                try:
                    with urllib.request.urlopen(req, timeout=20, context=_SSL) as r:
                        raw = decode_yb_response(r.read())
                    if raw:
                        # 检查是否有 finisheddata
                        fd = raw.get("finisheddata", [])
                        if fd:
                            print(f"  !! finisheddata 存在: {len(fd)} 条 [{scfg['name']}]")
                            records = parse_result_matches({"finisheddata": fd}, scfg["code"])
                            n = upsert_history(conn, records)
                            total_written += n
                            print(f"     写入 {n} 条")
                        else:
                            print(f"  [{scfg['name']}] 无 finisheddata（API 不开放历史）")
                except Exception as e:
                    print(f"  [{scfg['name']}] API 调用失败: {e}")

        except Exception as e:
            print(f"  步骤4失败: {e}")

        browser.close()

    conn.close()
    print(f"\n{'='*60}")
    print(f"  历史爬取完成: 共写入 {total_written} 条历史赛果")
    print(f"{'='*60}")
    return total_written


def parse_dom_matches(page, target_date):
    """从页面 DOM 提取比赛信息（降级方案）"""
    records = []
    try:
        # 尝试提取所有包含比分的行
        html = page.content()
        # 找比分模式 数字:数字
        score_pattern = re.compile(r'(\d{1,3})[：:]\s*(\d{1,3})')
        team_els = page.query_selector_all("[class*=team], [class*=match], [class*=event]")
        print(f"    DOM: 找到 {len(team_els)} 个比赛元素")
        for el in team_els[:100]:
            try:
                txt = el.inner_text()
                if not txt.strip():
                    continue
                m = score_pattern.search(txt)
                if m:
                    lines = [l.strip() for l in txt.splitlines() if l.strip()]
                    if len(lines) >= 2:
                        records.append({
                            "match_id": f"dom_{hashlib.md5(txt.encode()).hexdigest()[:12]}",
                            "sport": "football",
                            "league": "",
                            "home": lines[0] if lines else "",
                            "away": lines[-1] if lines else "",
                            "kickoff": target_date,
                            "hs": int(m.group(1)),
                            "as_": int(m.group(2)),
                            "status": "FT",
                        })
            except:
                pass
    except Exception as e:
        print(f"    DOM解析异常: {e}")
    return records


# ─── CLI ────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="qiety YB 历史赛果爬虫")
    ap.add_argument("--days",     type=int, default=7,      help="抓取最近N天 (默认7)")
    ap.add_argument("--headless", action="store_true",       help="无界面模式")
    ap.add_argument("--sport",    choices=["1","2","all"],   default="all", help="1=足球 2=篮球")
    args = ap.parse_args()

    sport_ids = ["1","2"] if args.sport == "all" else [args.sport]
    run_scraper(days=args.days, headless=args.headless, sport_ids=sport_ids)


if __name__ == "__main__":
    main()
