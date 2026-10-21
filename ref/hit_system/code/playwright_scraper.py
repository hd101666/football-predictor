#!/usr/bin/env python3
"""用Playwright智能抓取角球数据"""
import sys, json, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from playwright.sync_api import sync_playwright

def scrape_scoremer():
    """抓取Scoremer角球数据"""
    print("=== 抓取 Scoremer 角球数据 ===")
    with sync_playwright() as p:
        # 用Chrome（有更好的CloudFlare兼容性）
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0',
            viewport={'width': 1920, 'height': 1080},
            locale='zh-CN',
        )
        page = context.new_page()
        
        # 监听网络请求，捕获XHR
        api_requests = []
        page.on('request', lambda req: api_requests.append({
            'url': req.url,
            'method': req.method,
            'type': req.resource_type,
        }) if 'api' in req.url.lower() or 'json' in req.url.lower() or 'data' in req.url.lower() else None)
        
        try:
            print("  正在加载页面...")
            page.goto('https://lv.scoremer.com/zh/corner', 
                      timeout=30000, wait_until='networkidle')
            print(f"  title: {page.title()}")
            
            # 等待数据加载
            time.sleep(3)
            
            # 打印API请求
            print(f"\n  网络请求({len(api_requests)}个):")
            for r in api_requests[:20]:
                print(f"    {r['method']} {r['url'][:120]}")
            
            # 尝试提取比赛列表
            # 看表格结构
            tables = page.query_selector_all('table')
            print(f"\n  表格数: {len(tables)}")
            
            trs = page.query_selector_all('tr')
            print(f"  行数: {len(trs)}")
            
            # 看body文本
            body_text = page.inner_text('body')
            # 找带vs的行
            for line in body_text.split('\n'):
                if 'vs' in line.lower().strip():
                    print(f"  vs行: {line.strip()}")
            
            # 找角球数据区
            corner_elements = page.query_selector_all('[class*="corner"]')
            print(f"  corner元素: {len(corner_elements)}")
            
            # 截图保存
            page.screenshot(path='scoremer_screenshot.png')
            print("  截图已保存")
            
        except Exception as e:
            print(f"  ❌ {e}")
        
        browser.close()

def scrape_nowgoals():
    """抓取Nowgoals角球数据"""
    print("\n=== 抓取 Nowgoals 角球数据 ===")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            viewport={'width': 1920, 'height': 1080},
        )
        page = context.new_page()
        
        api_requests = []
        page.on('request', lambda req: api_requests.append({
            'url': req.url,
            'method': req.method,
        }) if req.resource_type == 'xhr' or req.resource_type == 'fetch' else None)
        
        try:
            print("  正在加载页面...")
            page.goto('https://nowgoals.net/', 
                      timeout=30000, wait_until='networkidle')
            print(f"  title: {page.title()}")
            time.sleep(3)
            
            print(f"\n  XHR/Fetch请求({len(api_requests)}个):")
            for r in api_requests[:20]:
                print(f"    {r['method']} {r['url'][:120]}")
            
            body_text = page.inner_text('body')
            # 找比赛
            for line in body_text.split('\n'):
                line = line.strip()
                if line and ('vs' in line.lower().strip() or any(c.isdigit() for c in line) and len(line) > 10):
                    print(f"  数据行: {line}")
            
            page.screenshot(path='nowgoals_screenshot.png')
            print("  截图已保存")
            
        except Exception as e:
            print(f"  ❌ {e}")
        
        browser.close()

if __name__ == '__main__':
    scrape_scoremer()
    scrape_nowgoals()
