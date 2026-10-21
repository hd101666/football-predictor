# -*- coding: utf-8 -*-
"""雷速体育 + 企鹅体育 双爬虫"""
import sys, time, re, sqlite3, json
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DB = r"F:\qqsj\data\sports_data.db"
NOW = datetime.now(timezone(timedelta(hours=8)))
TODAY = NOW.strftime("%Y-%m-%d")

def init():
    c = sqlite3.connect(DB)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS leisu_matches(match_id TEXT,sport TEXT,league TEXT,home TEXT,away TEXT,hr TEXT,ar TEXT,kickoff TEXT,status TEXT,hs INT,as_ INT,href TEXT,date TEXT,UNIQUE(match_id,date));
        CREATE TABLE IF NOT EXISTS qiety_matches(match_id TEXT,sport TEXT,league TEXT,home TEXT,away TEXT,kickoff TEXT,status TEXT,hs INT,as_ INT,date TEXT,UNIQUE(match_id,date));
        CREATE TABLE IF NOT EXISTS qiety_odds(match_id TEXT,market TEXT,line TEXT,ho REAL,do REAL,ao REAL,oo REAL,uo REAL,src TEXT,date TEXT);
    """)
    c.commit(); c.close()

def parse_match_li(li_html, league_name, sport):
    try:
        tm = re.search(r'(今天|明天)?\s*(\d{2}:\d{2})', li_html)
        ts = (tm.group(1)if tm and tm.group(1)else'')+' '+(tm.group(2)if tm else'')
        st='NS'
        if '进行中' in li_html or 'live' in li_html.lower(): st='LIVE'
        elif '已结束' in li_html: st='FT'
        sm=re.search(r'team-score[^>]*>\s*(\d+)\s*[-:]\s*(\d+)\s*<',li_html)
        hs=as_=0
        if sm: hs,as_=int(sm.group(1)),int(sm.group(2)); st='LIVE'
        hm=re.search(r'team-name[^>]*>\s*([^<]+?)\s*</div>\s*</div>\s*<div[^>]*team-logo',li_html)
        if not hm: hm=re.search(r'team-name[^>]*>\s*([^<]+?)\s*<',li_html)
        home=hm.group(1).strip() if hm else''
        am=re.search(r'team-score[^>]*>.*?</div>\s*<div[^>]*team-logo.*?</div>\s*<div[^>]*team-name[^>]*>\s*([^<]+?)\s*<',li_html)
        if not am:
            names=re.findall(r'team-name[^>]*>\s*([^<]+?)\s*<',li_html)
            away=names[2] if len(names)>2 else(names[1] if len(names)>1 else'')
        else: away=am.group(1).strip()
        hr=re.search(r'team-name[^>]*>.*?\[(\d+)\]',li_html)
        href=re.search(r'href="([^"]*detail-\d+[^"]*)"',li_html)
        if not home or not away: return None
        mid=re.sub(r'[^\w]','_',f"ls_{league_name}_{home}_{away}_{ts}")[:80]
        return{'id':mid,'sport':sport,'league':league_name,'home':home,'away':away,'hr':hr.group(1)if hr else'','ar':'','time':ts,'status':st,'hs':hs,'as_':as_,'href':href.group(1)if href else''}
    except: return None

def run_leisu():
    print(f"\n{'='*50}\n[雷速体育] leisu.com\n{'='*50}")
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=['--no-sandbox','--disable-blink-features=AutomationControlled'])
        ctx = b.new_context(user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122 Safari/537.36',viewport={'width':1280,'height':900},locale='zh-CN')
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>false});")
        print("  加载...")
        page.goto('https://www.leisu.com/', wait_until='domcontentloaded', timeout=20000)
        time.sleep(6); page.evaluate("window.scrollBy(0,2000)"); time.sleep(2)
        html = page.content(); b.close()
    
    print(f"  HTML: {len(html)//1024}KB")
    
    # 收集联赛标签
    seen = {}
    for m in re.finditer(r"change_hotArea\('([^']+)',this\)[^>]*>([^<]+)</div>", html):
        aid, lg = m.group(1), m.group(2).strip()
        if aid not in seen: seen[aid] = lg
    print(f"  联赛标签: {len(seen)} 个")
    
    # 全局搜索 match-list
    matches = []
    for m in re.finditer(r'<li[^>]*class="[^"]*match-list[^"]*"[^>]*>(.*?)</li>', html, re.DOTALL):
        li_html = m.group(1); pos = m.start()
        before = html[max(0,pos-3000):pos]
        # 最近联赛标签
        lg_ms = list(re.finditer(r"change_hotArea\('([^']+)',this\)[^>]*>([^<]+)</div>", before))
        if lg_ms:
            lg = lg_ms[-1].group(2).strip()
        else:
            am = re.search(r'id="(foot_hots_\d+|bask_hots_\d+)"', before)
            lg = seen.get(am.group(1),'未知联赛') if am else '未知联赛'
        sport = 'basketball' if 'bask_hots' in before or '篮球' in before else 'football'
        m2 = parse_match_li(li_html, lg, sport)
        if m2: matches.append(m2)
    
    # 去重
    ids=set(); uniq=[]
    for m in matches:
        if m['id'] not in ids: ids.add(m['id']); uniq.append(m)
    
    print(f"  解析: {len(uniq)} 场比赛")
    
    if uniq:
        c=sqlite3.connect(DB)
        for m in uniq:
            try: c.execute("INSERT OR REPLACE INTO leisu_matches VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(m['id'],m['sport'],m['league'],m['home'],m['away'],m.get('hr',''),m.get('ar',''),m['time'],m['status'],m['hs'],m['as_'],m.get('href',''),TODAY))
            except: pass
        c.commit(); c.close()
    
    for m in uniq[:25]:
        hr=f"[{m['hr']}]" if m.get('hr') else ''; ar=f"[{m['ar']}]" if m.get('ar') else ''
        sc=f"{m['hs']}-{m['as_']}" if m['status']=='LIVE' else 'VS'
        print(f"  [{m['sport'][:3]}] {m['league'][:12]:<12} {m['home'][:12]:<12}{hr} {sc:<5} {m['away'][:12]:<12}{ar} {m['time']}")
    return uniq


def run_qiety():
    print(f"\n{'='*50}\n[企鹅体育] qiety.vip\n{'='*50}")
    
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=['--no-sandbox','--disable-blink-features=AutomationControlled'])
        ctx = b.new_context(user_agent='Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',viewport={'width':412,'height':915},locale='zh-CN')
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>false});")
        
        json_resps = []
        def on_resp(resp):
            ct=resp.headers.get('content-type','')
            if 'json' in ct:
                try:
                    body=resp.json()
                    if isinstance(body,(dict,list)) and len(str(body))>50: json_resps.append({'url':resp.url,'data':body})
                except: pass
        page.on('response', on_resp)
        
        urls = ['https://www.qiety1726.vip/']
        for url in urls:
            try:
                print(f"  访问 {url[:40]}...")
                page.goto(url, wait_until='domcontentloaded', timeout=15000)
                time.sleep(4)
            except: pass
        
        text=page.inner_text('body'); html=page.content(); b.close()
    
    print(f"  JSON:{len(json_resps)} | 页面:{len(text)}B | HTML:{len(html)//1024}KB")
    
    # 从JSON提取赔率
    odds=[]
    for r in json_resps: extract_odds(r['data'], odds)
    if odds:
        c=sqlite3.connect(DB)
        for o in odds:
            try: c.execute("INSERT INTO qiety_odds VALUES(?,?,?,?,?,?,?,?,?,?)",(o.get('mid',''),o.get('mt',''),o.get('line',''),o.get('ho'),o.get('do'),o.get('ao'),o.get('oo'),o.get('uo'),o.get('src','qiety'),TODAY))
            except: pass
        c.commit(); c.close()
    
    print(f"  赔率: {len(odds)} 条")
    
    # 显示页面文本(如果有)
    if len(text)>50: print(f"  文本: {text[:200]}")
    return odds

def extract_odds(obj, results):
    if isinstance(obj, dict):
        if any(k in obj for k in ['odds','oddsHome','homeOdds','h','matchId']):
            o={'mid':str(obj.get('matchId',obj.get('id',''))),'mt':obj.get('marketType',obj.get('market','h2h')),'line':str(obj.get('line',obj.get('handicap',''))),'ho':obj.get('oddsHome') or obj.get('homeOdds') or obj.get('h'),'do':obj.get('oddsDraw') or obj.get('drawOdds'),'ao':obj.get('oddsAway') or obj.get('awayOdds') or obj.get('a'),'oo':obj.get('overOdds') or obj.get('over'),'uo':obj.get('underOdds') or obj.get('under'),'src':'qiety'}
            if o['ho'] or o['ao']: results.append(o)
        for k in ('data','result','list','matches','games','oddsList','matchList','items'):
            if k in obj and isinstance(obj[k],(list,dict)): extract_odds(obj[k], results)
    elif isinstance(obj, list):
        for item in obj: extract_odds(item, results)


if __name__ == "__main__":
    init()
    m = run_leisu()
    o = run_qiety()
    print(f"\n✅ 雷速:{len(m)}场 | 企鹅赔率:{len(o)}条")
