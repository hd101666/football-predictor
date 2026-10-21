#!/usr/bin/env python3
"""
企鹅体育 YB 全自动 Token 获取 + 赔率爬虫
===========================================
使用 Playwright 自动化登录 -> 获取 YB token -> 抓取赔率 -> 写入数据库

Usage:
  python qiety_auto.py                      # 全自动运行
  python qiety_auto.py --sport 1            # 只抓足球
  python qiety_auto.py --sport 2            # 只抓篮球
  python qiety_auto.py --token-only          # 只获取 token，不抓数据
  python qiety_auto.py --use-token <token>   # 用已有 token 直接抓
"""

import sys
import os
import json
import time
import base64
import gzip
import hashlib
import sqlite3
import re
import argparse
from datetime import datetime, timezone, timedelta
from typing import Optional

# ============ 配置 ============

QIETY_DOMAIN = "www.qiety1748.vip"
YB_API_BASE = "https://api.fgqinxg.com/yewu11/v1/w"
YB_API_BASE_V2 = "https://api.fgqinxg.com/yewu11/v2/w"
ACCOUNT = os.environ.get("QIETY_ACCOUNT", "")   # sanitized: 原为明文硬编码，现读环境变量
PASSWORD = os.environ.get("QIETY_PASSWORD", "")  # sanitized: 原为明文硬编码，现读环境变量
DB_PATH = r"F:\qqsj\data\sports_data.db"
TZ_BJ = timezone(timedelta(hours=8))

# Token 缓存文件
TOKEN_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".qiety_token.json")


# ============ Token 管理 ============

def load_token() -> Optional[dict]:
    """从文件加载缓存的 token"""
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE) as f:
                data = json.load(f)
            return data
        except:
            pass
    return None


def save_token(token_data: dict):
    """保存 token 到文件"""
    token_data["saved_at"] = datetime.now().isoformat()
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)
    print(f"  ✅ Token 已保存到 {TOKEN_FILE}")


def is_token_valid(token_data: dict) -> bool:
    """测试 token 是否有效"""
    import urllib.request
    
    request_id = token_data.get("requestId", "")
    cuid = token_data.get("cuid", "")
    euid = token_data.get("euid", "3020101")
    
    ts = int(time.time() * 1000)
    url = f"{YB_API_BASE}/getAddedOddsMatchesPB?t={ts}"
    
    raw_check = f"{cuid}-{ts}"
    md5_part = hashlib.md5(raw_check.encode()).hexdigest()
    check_id = f"pc-{md5_part}-{cuid}-{ts}"
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://user-pc-new.lvjida8.com",
        "Referer": "https://user-pc-new.lvjida8.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "checkId": check_id,
        "lang": "zh",
        "request-code": '{"panda-bss-source":"2"}',
        "requestId": request_id,
    }
    body = json.dumps({"cuid": cuid, "euid": euid, "sportId": "1"}).encode()
    
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode()
            d = json.loads(raw)
            if d.get("code") == "0000000":
                token_data["saved_at"] = datetime.now().isoformat()
                return True
            return False
    except:
        return False


# ============ Playwright 自动登录 ============

def get_token_via_playwright() -> Optional[dict]:
    """
    使用 Playwright 自动化登录企鹅体育，
    拦截 API 请求获取 token/requestId
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  ⚠️ 未安装 Playwright，请运行: pip install playwright && playwright install chromium")
        return None
    
    print("\n🌐 启动浏览器自动登录...")
    
    captured_data = {"requestId": None, "cuid": None, "apis": []}
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
        )
        ctx = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149 Safari/537.36',
            viewport={'width': 1280, 'height': 800},
            locale='zh-CN'
        )
        page = ctx.new_page()
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => false});
            window.chrome = {runtime: {}};
        """)
        
        # 拦截 YB API 的请求
        def on_request(request):
            url = request.url
            headers = request.headers
            
            # 找 YB API 请求中的 token（支持多个可能的域名）
            YB_API_DOMAINS = ('api.fgqinxg.com', 'api.apn5ptt.com', 'api.bvl8bs5.com')
            if any(d in url for d in YB_API_DOMAINS) and 'requestId' in headers:
                captured_data["requestId"] = headers.get("requestId", "")
                captured_data["cuid"] = headers.get("cuid", "")
                print("  📡 捕获 YB token: ***")
            
            # 记录所有请求
            captured_data["apis"].append({
                "url": url,
                "headers": dict(headers) if isinstance(headers, dict) else {},
                "method": request.method,
            })
        
        page.on("request", on_request)
        
        # 访问企鹅体育 YB 场馆
        yb_url = f"https://{QIETY_DOMAIN}:35531/app/venuesSport/YB/https%3A%2F%2Fuser-pc-new.lvjida8.com"
        
        print(f"  [1] 访问 {QIETY_DOMAIN}...")
        try:
            page.goto(f"https://{QIETY_DOMAIN}/", wait_until="domcontentloaded", timeout=30000)
        except:
            pass
        time.sleep(3)
        
        # 检查是否有登录按钮
        page_text = page.inner_text("body")
        
        # 尝试找到并点击"登录"按钮
        login_clicked = False
        for btn_text in ["登录", "登录/注册", "登录/注册后查看"]:
            try:
                btn = page.query_selector(f"text={btn_text}")
                if btn and btn.is_visible():
                    btn.click(timeout=5000)
                    print(f"  [2] 点击 '{btn_text}'")
                    time.sleep(2)
                    login_clicked = True
                    break
            except:
                pass
        
        # 查找输入框并登录
        if not login_clicked:
            # 可能已经登录了，检查页面状态
            print("  [2] 未找到登录按钮，可能已登录")
        
        # 尝试键盘输入账号密码
        try:
            # 先 Tab 到账号框
            page.keyboard.press("Tab")
            time.sleep(0.3)
            page.keyboard.type(ACCOUNT)
            print(f"  [3] 输入账号: {ACCOUNT}")
            time.sleep(0.3)
            page.keyboard.press("Tab")
            time.sleep(0.3)
            page.keyboard.type(PASSWORD)
            print(f"  [4] 输入密码")
            time.sleep(0.3)
            page.keyboard.press("Enter")
            print(f"  [5] 提交登录...")
            time.sleep(5)
        except Exception as e:
            print(f"  ⚠️ 键盘输入登录失败: {e}")
        
        # 导航到 YB 体育场馆
        print(f"  [6] 导航到 YB 体育场馆...")
        try:
            page.goto(yb_url, wait_until="domcontentloaded", timeout=30000)
        except:
            pass
        time.sleep(5)
        
        # 找体育/足球按钮点进去
        for sport_btn in ["体育", "足球", "篮球", "YB体育", "YB电竞"]:
            try:
                el = page.query_selector(f"text={sport_btn}")
                if el and el.is_visible():
                    el.click(timeout=3000)
                    print(f"  [7] 点击 '{sport_btn}'")
                    time.sleep(3)
                    break
            except:
                pass
        
        # 等 API 请求
        print(f"  [8] 等待 YB API 请求...")
        time.sleep(5)
        
        # 如果还没捕获到 token，从 API 请求历史中提取
        if not captured_data["requestId"]:
            print("  [9] 尝试从请求中提取 token...")
            
            # 检查 localStorage / sessionStorage
            try:
                storage_data = page.evaluate("""() => {
                    const items = {};
                    for (let i = 0; i < localStorage.length; i++) {
                        const k = localStorage.key(i);
                        items[k] = localStorage.getItem(k);
                    }
                    return items;
                }""")
                print(f"  localStorage keys: {list(storage_data.keys())[:10]}")
                
                # 找 token
                for k, v in storage_data.items():
                    if 'token' in k.lower() or 'requestId' in k.lower() or 'request_id' in k.lower():
                        print(f"  🔑 Found: {k} = {v[:50] if len(str(v))>50 else v}")
                        if len(str(v)) > 20 and 'requestId' not in k.lower():
                            captured_data["requestId"] = str(v)
            except Exception as e:
                print(f"  ⚠️ localStorage 提取失败: {e}")
        
        # Fallback: 如果还是没找到 token，从 URL 中尝试提取
        if not captured_data["requestId"]:
            current_url = page.url
            print(f"  Current URL: {current_url[:200]}")
            # URL 中有 token=xxx 参数
            m = re.search(r'token=([a-f0-9]+)', current_url)
            if m:
                captured_data["requestId"] = m.group(1)
                print("  🔑 从 URL 提取 token: ***")
            
            m2 = re.search(r'sessionId=(\d+)', current_url)
            if m2:
                captured_data["cuid"] = m2.group(1)
                print(f"  🔑 提取 cuid: {captured_data['cuid']}")
        
        browser.close()
    
    if captured_data["requestId"]:
        if not captured_data["cuid"]:
            captured_data["cuid"] = str(int(time.time() * 1000000))
        captured_data["euid"] = "3020101"
        save_token(captured_data)
        return captured_data
    
    print("  ❌ 无法获取 token")
    return None


# ============ YB API 客户端 ============

class YBApiClient:
    def __init__(self, token_data: dict):
        self.request_id = token_data.get("requestId", "")
        self.cuid = token_data.get("cuid", "")
        self.euid = token_data.get("euid", "3020101")
    
    def _gen_check_id(self) -> str:
        ts = int(time.time() * 1000)
        raw = f"{self.cuid}-{ts}"
        md5_part = hashlib.md5(raw.encode()).hexdigest()
        return f"pc-{md5_part}-{self.cuid}-{ts}"
    
    def _headers(self) -> dict:
        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": "https://user-pc-new.lvjida8.com",
            "Referer": "https://user-pc-new.lvjida8.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "checkId": self._gen_check_id(),
            "lang": "zh",
            "request-code": '{"panda-bss-source":"2"}',
            "requestId": self.request_id,
        }
    
    def _decode(self, raw: str) -> dict:
        d = json.loads(raw)
        if d.get("code") != "0000000":
            raise Exception(f"API错误 code={d.get('code')}: {d.get('msg','')}")
        decoded = base64.b64decode(d["data"])
        decompressed = gzip.decompress(decoded)
        return json.loads(decompressed)
    
    # ---- 热门比赛 (getAddedOddsMatchesPB) ----
    def get_match_list(self, sport_id: str = "1") -> list:
        import urllib.request
        ts = int(time.time() * 1000)
        url = f"{YB_API_BASE}/getAddedOddsMatchesPB?t={ts}"
        body = json.dumps({"cuid": self.cuid, "euid": self.euid, "sportId": sport_id}).encode()
        req = urllib.request.Request(url, data=body, headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return self._decode(resp.read().decode()).get("data", [])
    
    # ---- 全量比赛 (structureTournamentMatchesPB, v2 API) ----
    def get_full_match_list(self, sport_id: str, mi: str = None) -> dict:
        """获取全量比赛列表
        Returns: {'livedata': [...], 'nolive_data': [...]}
        """
        import urllib.request
        BASE_V2 = YB_API_BASE_V2  # use the global config
        sport_mi_map = {"1": "101201", "2": "102201"}
        sport_euid_map = {"1": "3020101", "2": "3020102"}
        if mi is None:
            mi = sport_mi_map.get(sport_id, "101201")
        euid = sport_euid_map.get(sport_id, self.euid)
        ts = int(time.time() * 1000)
        url = f"{BASE_V2}/structureTournamentMatchesPB?t={ts}"
        body = json.dumps({
            "cuid": self.cuid, 
            "euid": euid, 
            "sportId": sport_id, 
            "mi": mi
        }).encode()
        req = urllib.request.Request(url, data=body, headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=60) as resp:
            return self._decode(resp.read().decode())
    
    def get_match_odds(self, mid: str) -> list:
        import urllib.request
        ts = int(time.time() * 1000)
        params = f"mcid=0&mid={mid}&cuid={self.cuid}&newUser=0&isMr="
        url = f"{YB_API_BASE}/matchDetail/getMatchOddsInfo1PB?{params}&t={ts}"
        req = urllib.request.Request(url, headers=self._headers(), method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return self._decode(resp.read().decode())
    
    # ---- 全量盘口 (getMatchBaseInfoByOddsPB POST) ----
    def get_full_match_odds(self, mid: str, sport_id: str = "1") -> dict:
        """使用 POST 方法获取比赛盘口数据 (带有 playData) 
        这是全量爬虫推荐使用的盘口接口"""
        import urllib.request
        sport_euid_map = {"1": "3020101", "2": "3020102"}
        euid = sport_euid_map.get(sport_id, self.euid)
        ts = int(time.time() * 1000)
        url = f"{YB_API_BASE}/getMatchBaseInfoByOddsPB?t={ts}"
        body = json.dumps({
            "cuid": self.cuid, "cos": 0, "orpt": 7,
            "euid": euid, "mid": mid, "mcid": 0, "newUser": 0
        }).encode()
        req = urllib.request.Request(url, data=body, headers=self._headers(), method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return self._decode(resp.read().decode())


# ============ 数据写入 ============

def ov_to_dec(ov: int) -> float:
    return ov / 100000


def parse_and_write_full(client: YBApiClient, sport_id: str, sport_name: str, db_path: str):
    """
    使用全量 API 抓取并写入数据库
    步骤: structureTournamentMatchesPB -> 全量比赛列表 -> getMatchBaseInfoByOddsPB -> 盘口 -> DB
    """
    print(f"\n📊 开始全量抓取 {sport_name} ...")
    
    # 1. 获取全量比赛列表
    all_data = client.get_full_match_list(sport_id)
    
    matches = []
    for key in ['livedata', 'nolivedata', 'nolive_data']:
        for m in all_data.get(key, []):
            matches.append(m)
    
    print(f"  发现 {len(matches)} 场比赛 ({len(all_data.get('livedata',[]))} 直播 + {len(all_data.get('nolivedata',[]))} 未开赛)")
    
    if not matches:
        print("  ❌ 无比赛数据")
        return 0, 0
    
    match_rows = {}   # mid -> dict for qiety_matches
    odds_rows = []    # list of dicts for qiety_odds
    success = 0
    total_matches = len(matches)
    today = datetime.now(TZ_BJ).strftime("%Y-%m-%d")
    sport_code = "basketball" if sport_id == "2" else "football"

    for i, m in enumerate(matches):
        mid = m.get("mids", "")
        tn = m.get("tn", "")
        mgt = m.get("mgt", "")
        if not mid:
            continue

        # 过滤电竞/模拟比赛（PANDA独家、VS-、梦幻对垒）
        if any(k in tn for k in ['PANDA', 'VS-', '梦幻对垒', 'EAFC', 'NBA 2K', '电竞']):
            continue

        kickoff_time = ""
        if mgt:
            try:
                dt = datetime.fromtimestamp(int(mgt) / 1000, tz=TZ_BJ)
                kickoff_time = dt.strftime("%Y-%m-%d %H:%M")
            except:
                pass

        # 进度显示
        sys.stdout.write(f"\r  [{i+1}/{total_matches}] {mid} {tn[:20]}...")
        sys.stdout.flush()

        # 2. 获取盘口
        try:
            odds_data = client.get_full_match_odds(mid, sport_id)
        except Exception:
            continue

        if not odds_data or 'playData' not in odds_data:
            continue

        # 3. 从 data[0] 获取队名
        home = ""
        away = ""
        if 'data' in odds_data and len(odds_data['data']) > 0:
            d0 = odds_data['data'][0]
            home = d0.get("mhn", "")
            away = d0.get("man", "")

        match_rows[mid] = {
            "match_id": mid, "sport_code": sport_code, "league": tn,
            "home_team": home, "away_team": away,
            "kickoff_time": kickoff_time, "status": "pre",
            "fetch_date": today,
        }

        # 4. 解析盘口 (足球/篮球通用)
        # 足球 chpid: 1=1X2, 2=OU, 4=AH
        # 篮球 chpid: 37=moneyline, 38=total, 39=spread
        is_basketball = (sport_id == "2")
        new_odds = 0
        for item in odds_data['playData']:
            chpid_raw = item.get("chpid", "")
            chpid = int(chpid_raw) if str(chpid_raw).isdigit() else chpid_raw
            hlf = item.get("hlf", 0)

            if is_basketball:
                if chpid == 37:
                    market_type = "1x2"
                elif chpid == 39:
                    market_type = "ah"
                elif chpid == 38:
                    market_type = "ou"
                else:
                    continue
            else:
                if chpid == 1:
                    if hlf != 0:
                        continue
                    market_type = "1x2"
                elif chpid == 4:
                    market_type = "ah"
                elif chpid == 2:
                    market_type = "ou"
                else:
                    continue

            for h in item.get("hl", []):
                ol = h.get("ol", [])
                hv = h.get("hv")
                line = str(hv) if hv is not None else None

                if market_type == "1x2":
                    if is_basketball and len(ol) >= 2:
                        odds_rows.append({
                            "match_id": mid, "bookmaker": "qiety_yb",
                            "market_type": "1x2", "line": None,
                            "odds_home": ov_to_dec(ol[0].get("ov", 0)),
                            "odds_draw": None,
                            "odds_away": ov_to_dec(ol[1].get("ov", 0)),
                            "over_odds": None, "under_odds": None,
                            "fetch_date": today,
                        })
                        new_odds += 1
                    elif not is_basketball and len(ol) >= 3:
                        odds_rows.append({
                            "match_id": mid, "bookmaker": "qiety_yb",
                            "market_type": "1x2", "line": None,
                            "odds_home": ov_to_dec(ol[0].get("ov", 0)),
                            "odds_draw": ov_to_dec(ol[1].get("ov", 0)),
                            "odds_away": ov_to_dec(ol[2].get("ov", 0)),
                            "over_odds": None, "under_odds": None,
                            "fetch_date": today,
                        })
                        new_odds += 1
                elif market_type == "ah" and len(ol) >= 2:
                    odds_rows.append({
                        "match_id": mid, "bookmaker": "qiety_yb",
                        "market_type": "ah", "line": line,
                        "odds_home": ov_to_dec(ol[0].get("ov", 0)),
                        "odds_draw": None,
                        "odds_away": ov_to_dec(ol[1].get("ov", 0)),
                        "over_odds": None, "under_odds": None,
                        "fetch_date": today,
                    })
                    new_odds += 1
                elif market_type == "ou" and len(ol) >= 2:
                    odds_rows.append({
                        "match_id": mid, "bookmaker": "qiety_yb",
                        "market_type": "ou", "line": line,
                        "odds_home": None, "odds_draw": None, "odds_away": None,
                        "over_odds": ov_to_dec(ol[0].get("ov", 0)),
                        "under_odds": ov_to_dec(ol[1].get("ov", 0)),
                        "fetch_date": today,
                    })
                    new_odds += 1

        if new_odds > 0:
            success += 1

    print()  # newline after progress

    # 5. 写入数据库
    if not match_rows:
        print("  ⚠️ 无有效盘口数据")
        return 0, 0

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    # 确保 qiety_odds 有唯一索引以支持 INSERT OR REPLACE 去重
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_qiety_odds_uniq
        ON qiety_odds(match_id, bookmaker, market_type, line, fetch_date)
    """)

    # 写 qiety_matches
    match_inserted = 0
    for row in match_rows.values():
        try:
            cur.execute("""
                INSERT OR REPLACE INTO qiety_matches
                (match_id, sport_code, league, home_team, away_team,
                 kickoff_time, status, fetch_date)
                VALUES (:match_id, :sport_code, :league, :home_team, :away_team,
                        :kickoff_time, :status, :fetch_date)
            """, row)
            match_inserted += 1
        except Exception:
            pass

    # 写 qiety_odds
    odds_inserted = 0
    seen_odds = set()
    for row in odds_rows:
        dedup = (row["match_id"], row["market_type"], str(row["line"]), today)
        if dedup in seen_odds:
            continue
        seen_odds.add(dedup)
        try:
            cur.execute("""
                INSERT OR REPLACE INTO qiety_odds
                (match_id, bookmaker, market_type, line,
                 odds_home, odds_draw, odds_away, over_odds, under_odds, fetch_date)
                VALUES (:match_id, :bookmaker, :market_type, :line,
                        :odds_home, :odds_draw, :odds_away, :over_odds, :under_odds, :fetch_date)
            """, row)
            odds_inserted += 1
        except Exception:
            pass

    conn.commit()
    conn.close()
    print(f"  ✅ qiety_matches={match_inserted} 场, qiety_odds={odds_inserted} 条 ({success}/{total_matches} 场成功)")
    return success, odds_inserted


def parse_and_write(client: YBApiClient, sport_id: str, sport_name: str, db_path: str):
    """抓取热门比赛赔率并写入数据库（v1 API）"""
    print(f"\n📊 开始抓取 {sport_name} 赔率...")

    matches = client.get_match_list(sport_id)
    print(f"  发现 {len(matches)} 场比赛")

    if not matches:
        print("  ❌ 无比赛数据 (token 可能过期)")
        return 0, 0

    today = datetime.now(TZ_BJ).strftime("%Y-%m-%d")
    sport_code = "basketball" if sport_id == "2" else "football"
    match_rows = {}
    odds_rows = []
    success = 0

    for i, m in enumerate(matches):
        mid = m.get("mid", "")
        tn = m.get("tn", "")
        home = m.get("mhn", "")
        away = m.get("man", "")
        mgt = m.get("mgt", "")

        kickoff_time = ""
        if mgt:
            try:
                dt = datetime.fromtimestamp(int(mgt) / 1000, tz=TZ_BJ)
                kickoff_time = dt.strftime("%Y-%m-%d %H:%M")
            except:
                pass

        print(f"  [{i+1}/{len(matches)}] {home} vs {away}...", end=" ")
        sys.stdout.flush()

        try:
            odds_data = client.get_match_odds(mid)
        except Exception as e:
            print(f"❌ {e}")
            continue

        if not odds_data:
            print("⚠️ 无数据")
            continue

        match_rows[mid] = {
            "match_id": mid, "sport_code": sport_code, "league": tn,
            "home_team": home, "away_team": away,
            "kickoff_time": kickoff_time, "status": "pre",
            "fetch_date": today,
        }

        new_odds = 0
        for item in odds_data:
            chpid = str(item.get("chpid", ""))
            hlf = item.get("hlf", 0)
            if hlf != 0:
                continue

            for h in item.get("hl", []):
                ol = h.get("ol", [])
                hv = h.get("hv")
                line = str(hv) if hv is not None else None

                if chpid == "1" and len(ol) >= 3:
                    odds_rows.append({
                        "match_id": mid, "bookmaker": "qiety_yb",
                        "market_type": "1x2", "line": None,
                        "odds_home": ov_to_dec(ol[0].get("ov", 0)),
                        "odds_draw": ov_to_dec(ol[1].get("ov", 0)),
                        "odds_away": ov_to_dec(ol[2].get("ov", 0)),
                        "over_odds": None, "under_odds": None,
                        "fetch_date": today,
                    })
                    new_odds += 1
                elif chpid == "4" and len(ol) >= 2:
                    odds_rows.append({
                        "match_id": mid, "bookmaker": "qiety_yb",
                        "market_type": "ah", "line": line,
                        "odds_home": ov_to_dec(ol[0].get("ov", 0)),
                        "odds_draw": None,
                        "odds_away": ov_to_dec(ol[1].get("ov", 0)),
                        "over_odds": None, "under_odds": None,
                        "fetch_date": today,
                    })
                    new_odds += 1
                elif chpid == "2" and len(ol) >= 2:
                    odds_rows.append({
                        "match_id": mid, "bookmaker": "qiety_yb",
                        "market_type": "ou", "line": line,
                        "odds_home": None, "odds_draw": None, "odds_away": None,
                        "over_odds": ov_to_dec(ol[0].get("ov", 0)),
                        "under_odds": ov_to_dec(ol[1].get("ov", 0)),
                        "fetch_date": today,
                    })
                    new_odds += 1

        types_found = {r["market_type"] for r in odds_rows if r["match_id"] == mid}
        print(f"✅ {', '.join(sorted(types_found)) if types_found else '无盘口'}")
        if new_odds > 0:
            success += 1
        time.sleep(0.3)

    if not match_rows:
        print("\n⚠️ 无数据写入")
        return 0, 0

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_qiety_odds_uniq
        ON qiety_odds(match_id, bookmaker, market_type, line, fetch_date)
    """)

    match_inserted = 0
    for row in match_rows.values():
        try:
            cur.execute("""
                INSERT OR REPLACE INTO qiety_matches
                (match_id, sport_code, league, home_team, away_team,
                 kickoff_time, status, fetch_date)
                VALUES (:match_id, :sport_code, :league, :home_team, :away_team,
                        :kickoff_time, :status, :fetch_date)
            """, row)
            match_inserted += 1
        except Exception:
            pass

    odds_inserted = 0
    seen_odds = set()
    for row in odds_rows:
        dedup = (row["match_id"], row["market_type"], str(row["line"]), today)
        if dedup in seen_odds:
            continue
        seen_odds.add(dedup)
        try:
            cur.execute("""
                INSERT OR REPLACE INTO qiety_odds
                (match_id, bookmaker, market_type, line,
                 odds_home, odds_draw, odds_away, over_odds, under_odds, fetch_date)
                VALUES (:match_id, :bookmaker, :market_type, :line,
                        :odds_home, :odds_draw, :odds_away, :over_odds, :under_odds, :fetch_date)
            """, row)
            odds_inserted += 1
        except Exception:
            pass

    conn.commit()
    conn.close()
    print(f"\n✅ qiety_matches={match_inserted} 场, qiety_odds={odds_inserted} 条")
    return success, odds_inserted


# ============ 主逻辑 ============

def main():
    parser = argparse.ArgumentParser(description="企鹅体育YB全自动爬虫")
    parser.add_argument("--sport", type=str, default="all", 
                       choices=["1", "2", "all"], help="1=足球, 2=篮球, all=全部")
    parser.add_argument("--token-only", action="store_true", 
                       help="只获取 token，不抓数据")
    parser.add_argument("--headless", action="store_true",
                       help="使用无头浏览器（默认会弹出窗口）")
    parser.add_argument("--use-token", type=str, default=None,
                       help="使用已有 token 直接抓取")
    parser.add_argument("--db-path", type=str, default=DB_PATH)
    parser.add_argument("--full", action="store_true",
                        help="全量模式: 获取所有比赛 (不只是热门)")
    args = parser.parse_args()
    
    # Fix Windows-style paths from CLI (e.g., F:\qqsj\sports_data.db)
    import platform
    if platform.system() != "Windows":
        # Running on WSL/Linux - convert Windows paths
        dbp = args.db_path
        if ":" in dbp and "/mnt/" not in dbp and "\\" in dbp:
            # e.g. F:\qqsj\sports_data.db -> /mnt/f/qqsj/sports_data.db
            drive = dbp[0].lower()
            rest = dbp[2:].replace("\\", "/")
            args.db_path = f"/mnt/{drive}{rest}"
            print(f"🔄 转换 Windows 路径: {dbp} -> {args.db_path}")
    
    # 1. 获取 token
    token_data = None
    
    if args.use_token:
        token_data = {"requestId": args.use_token, "cuid": "", "euid": "3020101"}
        print("🔑 使用提供的 token: ***")
    else:
        # 先尝试缓存
        cached = load_token()
        if cached and is_token_valid(cached):
            print(f"🔑 使用缓存 token (有效期至 {cached.get('saved_at','?')})")
            token_data = cached
        else:
            if cached:
                print(f"🔄 缓存 token 可能已过期，尝试直连 API...")
            # Playwright 自动登录
            if args.headless:
                token_data = None
                print("  ⚠️ headless 模式无法登录浏览器")
            else:
                token_data = get_token_via_playwright()
            
            # 如果 Playwright 失败（代理问题），强制用缓存 token 再试一次
            if not token_data and cached:
                print("  ⚠️ 浏览器登录失败（可能被代理拦截），强制使用缓存 token 尝试...")
                token_data = cached
    
    if not token_data or not token_data.get("requestId"):
        print("❌ 无法获取 token，请检查网络和 Playwright 环境")
        sys.exit(1)
    
    print("✅ Token: ***")
    
    if args.token_only:
        print("✅ Token 获取完成")
        return
    
    # 2. 抓取赔率数据
    client = YBApiClient(token_data)
    
    total_matches = 0
    total_records = 0
    
    if args.sport in ("1", "all"):
        if args.full:
            m, r = parse_and_write_full(client, "1", "⚽ 足球", args.db_path)
        else:
            m, r = parse_and_write(client, "1", "⚽ 足球", args.db_path)
        total_matches += m
        total_records += r
    
    if args.sport in ("2", "all"):
        if args.full:
            m, r = parse_and_write_full(client, "2", "🏀 篮球", args.db_path)
        else:
            m, r = parse_and_write(client, "2", "🏀 篮球", args.db_path)
        total_matches += m
        total_records += r
    
    print(f"\n{'='*50}")
    print(f"✅ 完成! {total_matches} 场比赛, {total_records} 条赔率数据")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
