# -*- coding: utf-8 -*-
"""只跑爬虫阶段（不做分析），供"先爬→补爬→再分析"的分步流程使用。

用法: python -X utf8 _run_scrape_only.py <fetch_date> <轮次标签> [fast|all]
  fast = 只跑快速组(skip_slow=True)，慢速源另行拆独立进程并行跑
  all  = 全跑（会陷入慢速源死循环，不推荐，见下）

## 为什么要拆
00_命中系统.py 不加 --no-scrape 时会爬完立刻接着分析，中间插不进补爬轮次，
所以这里单独调 run_all_scrapers()。

## 为什么慢速组要单独拆出去（2026-08-11 教训）
后台任务约13~35分钟会被系统中止。调度器有断点续跑（今日status='ok'自动跳过），
所以**快速爬虫分段跑没问题**，进度单调向前。但**慢速爬虫会陷入死循环**：单个
耗时就超过被杀窗口，每次重启都要重新初始化+排队，还没跑完又被杀——实测连续
两段0完成。改成每个慢速爬虫一个独立进程并行跑，20分钟内全部完成。
"""
import sys
import importlib.util as u
from datetime import datetime

sys.path.insert(0, r"D:\cl\qqsj")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

FETCH_DATE = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
ROUND = sys.argv[2] if len(sys.argv) > 2 else "1"
MODE = sys.argv[3] if len(sys.argv) > 3 else "fast"

spec = u.spec_from_file_location("00_命中系统", r"D:\cl\qqsj\00_命中系统.py")
m = u.module_from_spec(spec)
# 注册成模块自己期望的名字，避免 predict_football 的 importlib.import_module
# 再加载一份副本（见 00_命中系统.py 顶部关于重复建缓存的说明）
sys.modules["00_命中系统"] = m
spec.loader.exec_module(m)

skip_slow = (MODE == "fast")
print(f"\n{'='*70}\n  爬虫阶段 第{ROUND}轮  fetch_date={FETCH_DATE}  "
      f"{'仅快速组' if skip_slow else '全部'}\n"
      f"  启动于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n{'='*70}", flush=True)

m.run_all_scrapers(skip_slow=skip_slow, fetch_date=FETCH_DATE)

print(f"\n第{ROUND}轮结束于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
