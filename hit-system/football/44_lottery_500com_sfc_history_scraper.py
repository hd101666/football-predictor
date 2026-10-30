#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
500彩票网 胜负彩(14场)/任选9场 历史开奖数据爬虫
=================================
数据源: kaijiang.500.com/shtml/sfc/{period}.shtml
    每期页面同时包含: 14场比赛队名+比分结果(0/1/3)、销量、奖池滚存、
    一等奖/二等奖(胜负彩)/任九奖 中奖注数+单注奖金——这是这两个玩法
    的真实"赔付"依据(彩票是奖池分摊制，没有传统赔率，单注奖金就是回报)。
    页面 period 格式: 年份后两位 + 3位序号(如 24185 = 2024年第185期)。
    不存在的 period 返回 HTTP 404 (body 153字节)，用作停止信号。

用法:
  python -X utf8 44_lottery_500com_sfc_history_scraper.py --start-year 2004 --end-year 2026
  python -X utf8 44_lottery_500com_sfc_history_scraper.py --period 24185   # 单期测试
"""

import sys, os, re, time, sqlite3, argparse
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import requests
from bs4 import BeautifulSoup

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_BASE_DIR, "data", "sports_data.db")
BASE_URL = "https://kaijiang.500.com/shtml/sfc/{period}.shtml"

HEADERS = {"User-Agent": "Mozilla/5.0"}

TIER_NAMES = {"一等奖", "二等奖", "任九"}


def _get_with_retry(url, retries=3, backoff=3.0, timeout=15):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return requests.get(url, headers=HEADERS, timeout=timeout)
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise last_err


class PeriodNotFound(Exception):
    """该period确认不存在(HTTP 404/极短应答)，是run()里唯一可信的"这年抓完了"信号"""
    pass


class PeriodParseError(Exception):
    """页面200且有实际内容，但解析失败(表格/td数量不对)——不代表该period不存在，
    实测同一period稍后单独重试就能解析成功，怀疑是持续高频请求下服务器偶尔吐出
    残缺/降级页面。这类异常必须跟PeriodNotFound分开处理，不能计入miss_streak，
    否则会把仅仅是这次解析失败的period误判成"年度已结束"，导致大量真实存在
    的period被跳过(实测2019-2026年因此只抓到个位数期数/年，应有150-200)。"""
    pass


def fetch_period(period: str):
    """抓取单期数据，返回 dict。该期确认不存在时抛PeriodNotFound；
    页面异常/解析失败时抛PeriodParseError(值得重试)。"""
    url = BASE_URL.format(period=period)
    resp = _get_with_retry(url)
    if resp.status_code == 404 or len(resp.content) < 500:
        raise PeriodNotFound(period)
    resp.encoding = "gbk"
    soup = BeautifulSoup(resp.text, "html.parser")

    tables = soup.select("table.kj_tablelist02")
    if not tables:
        raise PeriodParseError(f"{period}: 未找到kj_tablelist02表格")

    match_table = tables[0]
    rows = match_table.find_all("tr")
    if len(rows) < 3:
        raise PeriodParseError(f"{period}: 表格行数不足({len(rows)})")

    # 第2行: 14个 div_shupai td，title="Home VS Away"
    team_tds = rows[1].select("td.div_shupai")
    if len(team_tds) != 14:
        raise PeriodParseError(f"{period}: 队伍td数量异常({len(team_tds)})")
    matches = []
    for i, td in enumerate(team_tds, start=1):
        title = td.get("title", "")
        m = re.match(r"(.+?)\s*VS\s*(.+)", title)
        if m:
            home, away = m.group(1).strip(), m.group(2).strip()
        else:
            home, away = td.get_text(strip=True), ""
        if "{" in home or "{" in away:
            # 2004年及更早部分期号页面是未填充的模板占位符，非真实数据
            raise PeriodNotFound(f"{period}: 模板占位符(未填充真实数据)")
        matches.append({"seq": i, "home_team": home, "away_team": away})

    # 第3行: 14个 cfont5 span，结果 0/1/3
    result_spans = rows[2].select("span.cfont5")
    if len(result_spans) != 14:
        raise PeriodParseError(f"{period}: 结果span数量异常({len(result_spans)})")
    for i, span in enumerate(result_spans):
        txt = span.get_text(strip=True)
        try:
            matches[i]["result"] = int(txt)
        except ValueError:
            matches[i]["result"] = None

    # 开奖日期
    draw_date = None
    header_span = match_table.select_one("td.td_title01 span.span_right")
    if header_span:
        dm = re.search(r"开奖日期[：:]\s*(\d{4})年(\d{1,2})月(\d{1,2})日", header_span.get_text())
        if dm:
            draw_date = f"{dm.group(1)}-{int(dm.group(2)):02d}-{int(dm.group(3)):02d}"

    # 销量+滚存 (在 match_table 最后一个 colspan=14 的行里)
    sfc_sales = ren9_sales = rollover = None
    sales_text = ""
    for tr in rows:
        tds = tr.find_all("td")
        if len(tds) == 1 and tds[0].get("colspan") == "14":
            sales_text += tds[0].get_text(" ", strip=True)
    if sales_text:
        m1 = re.search(r"胜负彩销量[：:]\s*([\d,]+)元", sales_text)
        m2 = re.search(r"任九销量[：:]\s*([\d,]+)元", sales_text)
        m3 = re.search(r"奖池滚存[：:]\s*([\d,]+)元", sales_text)
        if m1: sfc_sales = float(m1.group(1).replace(",", ""))
        if m2: ren9_sales = float(m2.group(1).replace(",", ""))
        if m3: rollover = float(m3.group(1).replace(",", ""))

    # 奖级表 (第二个 table)
    prizes = []
    if len(tables) >= 2:
        prize_table = tables[1]
        for tr in prize_table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) == 3:
                tier = tds[0].get_text(strip=True)
                if tier not in TIER_NAMES:
                    continue
                try:
                    winning_count = int(tds[1].get_text(strip=True).replace(",", ""))
                    prize_amount = float(tds[2].get_text(strip=True).replace(",", ""))
                except ValueError:
                    continue
                prizes.append({
                    "tier": tier,
                    "winning_count": winning_count,
                    "prize_amount": prize_amount,
                })

    return {
        "period": period,
        "draw_date": draw_date,
        "matches": matches,
        "sfc_sales": sfc_sales,
        "ren9_sales": ren9_sales,
        "jackpot_rollover": rollover,
        "prizes": prizes,
    }


def init_tables(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS lottery_sfc_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period TEXT NOT NULL,
        seq INTEGER,
        home_team TEXT,
        away_team TEXT,
        result INTEGER,
        draw_date TEXT,
        fetch_date TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(period, seq)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS lottery_sfc_prizes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period TEXT NOT NULL,
        tier TEXT,
        winning_count INTEGER,
        prize_amount REAL,
        sfc_sales REAL,
        ren9_sales REAL,
        jackpot_rollover REAL,
        fetch_date TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(period, tier)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lottery_sfc_matches_period ON lottery_sfc_matches(period)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lottery_sfc_prizes_period ON lottery_sfc_prizes(period)")
    conn.commit()


def save_period(conn, data, fetch_date):
    period = data["period"]
    for m in data["matches"]:
        conn.execute("""
            INSERT OR REPLACE INTO lottery_sfc_matches
                (period, seq, home_team, away_team, result, draw_date, fetch_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (period, m["seq"], m["home_team"], m["away_team"], m.get("result"),
              data["draw_date"], fetch_date))
    for p in data["prizes"]:
        conn.execute("""
            INSERT OR REPLACE INTO lottery_sfc_prizes
                (period, tier, winning_count, prize_amount, sfc_sales, ren9_sales, jackpot_rollover, fetch_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (period, p["tier"], p["winning_count"], p["prize_amount"],
              data["sfc_sales"], data["ren9_sales"], data["jackpot_rollover"], fetch_date))
    conn.commit()


def run(start_year: int, end_year: int, delay: float = 0.6, resume: bool = True):
    fetch_date = datetime.now().strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB_PATH, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    init_tables(conn)

    done_periods = set()
    incomplete_periods = set()
    if resume:
        # FIX-016-2（2026-09-15）：断点续传只跳过"14场result全部非NULL"的完整期。
        # 旧逻辑按期是否存在跳过——而本爬虫对临近开奖/未开奖的期会先把fixture
        # 入库（result=NULL），此后每次续跑都把该期当"已完成"跳过，赛果永不回填
        # （26125实证：09-11抓fixture、09-14开奖、续跑仍跳过，最后靠人工录入）。
        done_periods = {r[0] for r in conn.execute(
            "SELECT period FROM lottery_sfc_matches GROUP BY period "
            "HAVING COUNT(*) >= 14 AND SUM(result IS NULL) = 0")}
        incomplete_periods = {r[0] for r in conn.execute(
            "SELECT DISTINCT period FROM lottery_sfc_matches WHERE result IS NULL")}
        if done_periods:
            print(f"  断点续传: 已有 {len(done_periods)} 期完整数据将跳过；"
                  f"{len(incomplete_periods)} 期 result 有空缺将重抓回填")

    total_periods = 0
    total_matches = 0
    for year in range(start_year, end_year + 1):
        yy = year % 100
        miss_streak = 0
        seq = 1
        year_periods = 0
        while seq <= 300:
            period = f"{yy:02d}{seq:03d}"

            if period in done_periods:
                year_periods += 1
                total_periods += 1
                seq += 1
                continue

            # 只有PeriodNotFound(真404/占位符)才是"该期不存在"的可信信号，
            # 计入miss_streak判断年度是否结束。网络异常和PeriodParseError
            # (页面200但解析失败，疑似持续高频请求下服务器偶尔吐出降级页面，
            # 实测同一period单独重试就能解析成功)都只是"这次没抓到"，重试
            # 几次仍失败也不计入miss_streak，只是跳过留到下次断点续传时再补，
            # 避免误判"年度已结束"导致大片真实存在的period被跳过(实测
            # 2019-2026年因此只抓到个位数期数/年，应有150-200)。
            data = None
            not_found = False
            for _attempt in range(3):
                try:
                    data = fetch_period(period)
                    break
                except PeriodNotFound:
                    not_found = True
                    break
                except Exception as e:
                    time.sleep(delay * (_attempt + 1))

            if not_found:
                # FIX-016-2：库里已有fixture的期被404，是"页面被撤/尚未上线"，
                # 该期客观存在，不能当作"年度已结束"的信号——否则 FIX-016-2 重抓
                # 回填机制会让历史空缺期把每个年度的扫描提前截断。
                if period in incomplete_periods:
                    print(f"  [{period}] 库内有fixture但源站404，保留空缺待下轮(不计入年度结束判断)")
                    seq += 1
                    time.sleep(delay)
                    continue
                miss_streak += 1
                if miss_streak >= 3:
                    break
                seq += 1
                time.sleep(delay)
                continue

            if data is None:
                print(f"  [{period}] 连续3次抓取/解析失败，跳过留待下次续跑(不计入年度结束判断)")
                seq += 1
                time.sleep(delay)
                continue

            miss_streak = 0
            save_period(conn, data, fetch_date)
            total_periods += 1
            year_periods += 1
            total_matches += len(data["matches"])
            if year_periods % 20 == 0:
                print(f"  {year}年 已抓 {year_periods} 期 (最新: {period}, 开奖日={data['draw_date']})")
            seq += 1
            time.sleep(delay)

        print(f"[{year}] 完成，共 {year_periods} 期")

    print(f"\n=== 全部完成: 共 {total_periods} 期, {total_matches} 场比赛 ===")
    conn.close()
    return total_periods


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-year", type=int, default=2005)
    ap.add_argument("--end-year", type=int, default=datetime.now().year)
    ap.add_argument("--period", type=str, default=None, help="单期测试")
    ap.add_argument("--delay", type=float, default=0.6)
    args = ap.parse_args()

    if args.period:
        try:
            d = fetch_period(args.period)
        except (PeriodNotFound, PeriodParseError) as e:
            d = None
            print(f"该期不存在或解析失败: {e}")
        if d is not None:
            print(f"period={d['period']} draw_date={d['draw_date']}")
            for m in d["matches"]:
                print(f"  {m['seq']:2d}. {m['home_team']} vs {m['away_team']}  结果={m.get('result')}")
            print(f"  销量: 胜负彩={d['sfc_sales']} 任九={d['ren9_sales']} 滚存={d['jackpot_rollover']}")
            for p in d["prizes"]:
                print(f"  {p['tier']}: 中奖{p['winning_count']}注, 单注{p['prize_amount']}元")
    else:
        run(args.start_year, args.end_year, args.delay)
