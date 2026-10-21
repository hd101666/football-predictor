# -*- coding: utf-8 -*-
"""
雷速体育爬虫 v2 — 解析已渲染 DOM + 绕过滑块验证码
"""
import json, time, sys, sqlite3, re
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DB_PATH = r"F:\qqsj\data\sports_data.db"
BJTZ = timezone(timedelta(hours=8))
NOW = datetime.now(BJTZ)
TODAY = NOW.strftime("%Y-%m-%d")

def init_tables():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS leisu_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id TEXT,
            sport_code TEXT,
            league_name TEXT,
            home_team TEXT,
            away_team TEXT,
            home_rank TEXT,
            away_rank TEXT,
            kickoff_time TEXT,
            status TEXT,
            home_score INTEGER,
            away_score INTEGER,
            half_score TEXT,
            corner_score TEXT,
            fetch_date TEXT,
            UNIQUE(match_id, fetch_date)
        );
        CREATE TABLE IF NOT EXISTS leisu_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id TEXT,
            bookmaker TEXT,
            market_type TEXT,
            line TEXT,
            home_odds REAL,
            draw_odds REAL,
            away_odds REAL,
            fetch_date TEXT
        );
    """)
    conn.commit()
    conn.close()

def solve_slider(page):
    """尝试拖动滑块验证码"""
    try:
        slider = page.query_selector('.slider, .nc_iconfont, .btn_slide, [class*="slider"], [class*="slide"]')
        if not slider:
            slider = page.query_selector('text=请按住滑块')
        if slider:
            box = slider.bounding_box()
            if box:
                page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2)
                page.mouse.down()
                # 慢慢拖到右边
                for i in range(10):
                    page.mouse.move(box['x'] + box['width'] + (i+1)*30, box['y'] + box['height']/2, steps=5)
                    time.sleep(0.1)
                page.mouse.up()
                time.sleep(2)
                return True
    except Exception as e:
        print(f"  滑块失败: {e}")
    return False

def parse_dom_matches(page):
    """从渲染后的 DOM 提取比赛数据"""
    matches = []
    
    # 方案1: 通过常见选择器
    selectors = [
        '[class*="match-item"]', '[class*="matchItem"]',
        '[class*="live-item"]', '[class*="liveItem"]',
        '.match-list > div', '.live-list > div',
        '[class*="event-item"]', 
    ]
    
    for sel in selectors:
        items = page.query_selector_all(sel)
        if len(items) > 3:
            print(f"  选择器 {sel}: {len(items)} 个元素")
            for item in items:
                m = extract_match_from_element(item)
                if m:
                    matches.append(m)
            if matches:
                break
    
    return matches

def extract_match_from_element(el):
    """从单个 DOM 元素提取比赛信息"""
    try:
        text = el.inner_text()
        html = el.inner_html()
    except:
        return None
    
    # 必须有对阵信息
    if 'VS' not in text and 'vs' not in text and ' - ' not in text:
        return None
    
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if len(lines) < 4:
        return None
    
    m = {
        "sport": "football",
        "league": "",
        "home_team": "",
        "away_team": "",
        "home_rank": "",
        "away_rank": "",
        "time": "",
        "status": "NS",
        "home_score": 0,
        "away_score": 0,
        "half_score": "",
        "corner_score": "",
    }
    
    # 解析逻辑
    i = 0
    # 联赛名通常是第一行（不含比分/VIP/阵容等）
    if i < len(lines) and not re.search(r'\d+:\d+|\d+-\d+|VIP|阵容|情报|角:', lines[i]):
        m["league"] = lines[i]
        i += 1
    
    # 跳过热度数字
    while i < len(lines) and re.match(r'^\d+$', lines[i]):
        i += 1
    while i < len(lines) and lines[i] in ['VIP情报', '阵容', '情报']:
        i += 1
    
    if i >= len(lines):
        return None
    
    # 解析排名 [xxx] pattern
    rank_patterns = re.findall(r'\[(\d+)\]', '\n'.join(lines[i:]))
    
    # 找 VS 行和时间
    for j in range(i, len(lines)):
        line = lines[j]
        # 时间
        time_match = re.match(r'^(\d{2}:\d{2})$', line)
        if time_match:
            m["time"] = time_match.group(1)
            continue
        # 比分 (进行中)
        score_match = re.match(r'^(\d+)\s*-\s*(\d+)$', line)
        if score_match and j > 0 and lines[j-1] != 'VS':
            m["home_score"] = int(score_match.group(1))
            m["away_score"] = int(score_match.group(2))
            m["status"] = "LIVE"
            continue
        # 半场/角球
        if line.startswith('半:') or line.startswith('角:'):
            if '半:' in line:
                m["half_score"] = line
            if '角:' in line:
                m["corner_score"] = line
            continue
        # VS 标识
        if line == 'VS':
            if j > 0:
                m["home_team"] = lines[j-1]
            if j + 1 < len(lines):
                m["away_team"] = lines[j+1]
            break
    
    # 排名
    if rank_patterns:
        if len(rank_patterns) >= 1:
            m["home_rank"] = rank_patterns[0]
        if len(rank_patterns) >= 2:
            m["away_rank"] = rank_patterns[1]
    
    # 清理队名（去除排名标记）
    for key in ['home_team', 'away_team']:
        m[key] = re.sub(r'\[?\d+\]?', '', m[key] or '').strip()
    
    if not m["home_team"] or not m["away_team"]:
        return None
    
    # 生成唯一ID
    m["match_id"] = f"leisu_{m['league']}_{m['home_team']}_{m['away_team']}_{m['time']}"
    m["match_id"] = re.sub(r'[^\w]', '_', m["match_id"])[:80]
    
    return m

def scroll_page(page):
    """滚动页面加载更多比赛"""
    for i in range(5):
        page.evaluate("window.scrollBy(0, 800)")
        time.sleep(1.5)

def run():
    print(f"[leisu] 启动 {NOW.strftime('%Y-%m-%d %H:%M:%S')}")
    init_tables()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            '--no-sandbox', '--disable-blink-features=AutomationControlled'
        ])
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            viewport={'width': 412, 'height': 915},
            locale='zh-CN'
        )
        page = context.new_page()

        # 防止检测
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
        """)

        print("[leisu] 加载页面...")
        page.goto('https://m.leisu.com/', wait_until='networkidle', timeout=30000)
        time.sleep(5)

        # 尝试解决滑块
        print("[leisu] 检查验证码...")
        has_captcha = page.query_selector('text=请按住滑块') or page.query_selector('[class*="captcha"]')
        if has_captcha:
            print("  发现滑块，尝试拖动...")
            solved = solve_slider(page)
            if solved:
                time.sleep(3)
            else:
                print("  滑块未解决，使用已渲染数据")
        else:
            print("  无验证码")

        # 滚动加载更多
        scroll_page(page)

        # 解析比赛
        print("[leisu] 解析比赛数据...")
        matches = parse_dom_matches(page)

        browser.close()

    print(f"\n[leisu] 抓到 {len(matches)} 场比赛:")
    
    # 保存
    if matches:
        conn = sqlite3.connect(DB_PATH)
        for m in matches:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO leisu_matches 
                    (match_id, sport_code, league_name, home_team, away_team, home_rank, away_rank,
                     kickoff_time, status, home_score, away_score, half_score, corner_score, fetch_date)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    m["match_id"], m["sport"], m["league"], m["home_team"], m["away_team"],
                    m["home_rank"], m["away_rank"], m["time"], m["status"],
                    m["home_score"], m["away_score"], m["half_score"], m["corner_score"], TODAY
                ))
            except Exception as e:
                print(f"  DB err: {e}")
        conn.commit()
        conn.close()

    for m in matches[:30]:
        score = f"{m['home_score']}-{m['away_score']}" if m['status'] == 'LIVE' else 'VS'
        hr = f"[{m['home_rank']}]" if m.get('home_rank') else ''
        ar = f"[{m['away_rank']}]" if m.get('away_rank') else ''
        print(f"  [{m['sport'][:3]}] {m['league']} | {m['home_team']} {hr} {score} {m['away_team']} {ar} | {m['time']}")

    return matches

if __name__ == "__main__":
    run()
