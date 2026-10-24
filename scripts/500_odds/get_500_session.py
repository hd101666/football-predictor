# -*- coding: utf-8 -*-
"""人工过验证码 + 保存会话，供后续批量抓取复用。

流程：
  1. headless=False 打开 500.com 目标页（会弹出浏览器窗口）
  2. 提示用户手动勾选「验证复选框」
  3. 轮询检测验证是否通过（页面变成真实内容）
  4. 通过后把 storage_state（含 EO_Bot_Ssid 等 cookie）保存到 json
  5. 后续抓取直接 load storage_state，无需再过验证
"""
import asyncio
import os
import sys

URL = "https://odds.500.com/fenxi/ouzhi-1430753.shtml"
URL_HOME = "https://odds.500.com/"
STATE = r"D:\cl\qqsj_v2\out\500_session.json"
REAL_MIN = 100_000


async def main():
    from playwright.async_api import async_playwright

    os.makedirs(os.path.dirname(STATE), exist_ok=True)

    async with async_playwright() as pw:
        b = await pw.chromium.launch(headless=False, args=["--start-maximized"])
        ctx = await b.new_context(viewport=None, locale="zh-CN",
                                  timezone_id="Asia/Shanghai")
        p = await ctx.new_page()

        print("=" * 60)
        print("即将打开 500.com，请在浏览器窗口里【手动勾选验证复选框】")
        print("验证通过后本脚本会自动保存会话")
        print("=" * 60)
        await p.goto(URL, wait_until="domcontentloaded", timeout=60000)

        # 轮询等待人工验证（最多 10 分钟），单次异常不退出
        closed = False
        for i in range(120):
            try:
                await p.wait_for_timeout(5000)
            except Exception as e:
                print(f"  ⚠ 页面不可用: {type(e).__name__}（浏览器可能被关闭）")
                closed = True
                break
            try:
                h = await p.content()
                title = await p.title()
            except Exception:
                continue
            el = (i + 1) * 5
            print(f"  [{el}s] len={len(h)} title={title[:40]!r}")
            if len(h) > REAL_MIN:
                print("\n✅ 检测到真实页面，保存会话")
                await ctx.storage_state(path=STATE)
                print(f"  已保存: {STATE}")
                cookies = await ctx.cookies()
                print(f"  cookie 数: {len(cookies)}")
                for c in cookies:
                    print(f"    {c['name']} ({c['domain']}) len={len(c['value'])}")
                await b.close()
                return 0

        if closed:
            print("\n❌ 浏览器窗口被关闭，未完成验证")
        else:
            print("\n❌ 10 分钟内未检测到验证通过")
        print("  可能原因：没勾选复选框、验证失败、或窗口被关掉")
        try:
            await b.close()
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
