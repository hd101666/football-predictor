#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
任九/胜负彩 每日复盘脚本（通用，可复用）
=================================
对任意一期：抓 okooo 当期 14 场赔率 + 500 网开奖结果，
用「旧规则 vs 新规则」分别生成每场选号，比对实际结果算命中率，
写入复盘表 ren9_rule_review 长期攒数据，并飞书推送。

来源：土豆(OpenClaw) qqsj/ren9_daily_review.py，2026-08-17 从
E:\\potato_skills_backup 审查后原样移入本项目（依赖的 39/44 号爬虫
本项目已有且函数签名一致，未做改动）。飞书推送读取的是土豆自己的
凭证文件 C:\\Users\\cn\\.openclaw\\openclaw.json，本项目环境下不存在，
_push() 会打印"飞书凭证缺失"后跳过，不影响复盘计算和落库。
方法论见 RULES_任九胜负彩选号方法论.md。

用法:
  python ren9_daily_review.py --period 26103
  python ren9_daily_review.py --period 26103 --no-push   # 只写库不推送
"""
import sys, os, re, json, sqlite3, argparse, importlib.util, math
from datetime import datetime
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = r"D:\cl\qqsj"
sys.path.insert(0, BASE)
DB = os.path.join(BASE, "data", "sports_data.db")

# 复用两个现成脚本
def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

okooo = _load("okooo_ren9", os.path.join(BASE, "39_okooo_ren9_scraper.py"))
sfc   = _load("sfc44", os.path.join(BASE, "44_lottery_500com_sfc_history_scraper.py"))

RES = {3: "主胜", 1: "平局", 0: "客胜"}

# ── FIX-012（2026-09-14）：预警信号×赛果自动记分（把26124起的人工记分卡变自动）──
# 口径与 _warning_weakening.py 派生逻辑同标准：
#   时序走弱触发 = 澳客漂移≤-2.0pp 或 qiety同向≤-1.5pp → 热门向(fav_dir)未打出=命中1/打出=误报0
#   竞彩溢价触发 = 溢价>3.0pp → 溢价方向(fav_dir，被买爆项)未打出=命中1
#   跨源分歧触发 = |pin_diff|≥2.0pp → 不记单条命中，改记 okooo_top_right/pin_top_right
#                 （各家去水最高概率方向是否打出，比单记"谁对"更有分析价值）
# 赛果缺失=NULL。每条触发行独立记分（同期多run_ts=多次观测，各记一条）。
# 写回=ren9_warning_signals 首次允许UPDATE：仅限本行4个赛果补登列
# （outcome_hit/okooo_top_right/pin_top_right/note），信号原始pp值永不动。
_WW_OK_DRIFT, _WW_QY_DRIFT, _WW_PIN_DIV, _WW_JC_PREM = -2.0, -1.5, 2.0, 3.0


def _ws_init_cols(conn):
    for col, ct in [("outcome_hit", "INTEGER"), ("okooo_top_right", "INTEGER"),
                    ("pin_top_right", "INTEGER"), ("note", "TEXT")]:
        try:
            conn.execute(f"ALTER TABLE ren9_warning_signals ADD COLUMN {col} {ct}")
        except sqlite3.OperationalError:
            pass  # 列已存在（重跑幂等）


def _okooo_latest_tops(conn, period):
    """该期澳客最新批次的 {seq: (ho,dr,ao)}：snapshots 优先，老期次退回主表
    最新 fetch_date（与 _warning_weakening._okooo_batches 同一回退口径）。"""
    try:
        bts = conn.execute("SELECT MAX(batch_ts) FROM okooo_ren9_snapshots "
                           "WHERE lottery_no=?", (period,)).fetchone()[0]
    except sqlite3.OperationalError:
        bts = None
    if bts:
        return {int(s): (h, d, a) for s, h, d, a in conn.execute(
            "SELECT seq, odds_home, odds_draw, odds_away FROM okooo_ren9_snapshots "
            "WHERE lottery_no=? AND batch_ts=?", (period, bts))}
    fd = conn.execute("SELECT MAX(fetch_date) FROM okooo_ren9_matches "
                      "WHERE lottery_no=?", (period,)).fetchone()[0]
    if not fd:
        return {}
    return {int(s): (h, d, a) for s, h, d, a in conn.execute(
        "SELECT seq, odds_home, odds_draw, odds_away FROM okooo_ren9_matches "
        "WHERE lottery_no=? AND fetch_date=?", (period, fd))}


def _pin_tops(period):
    """该期 Pinnacle 截面的 {seq: (ho,dr,ao)}：比对臂产物，没有就空。
    _pin_live_*.json 是 ren9_live_slip 日常产物，_pin_odds_*.json 是手工一次性
    对比的兼容回退（与 _warning_weakening 同发现顺序）。"""
    for jname in (f"_pin_live_{period}.json", f"_pin_odds_{period}.json"):
        jpath = os.path.join(BASE, "scratch", jname)
        if not os.path.exists(jpath):
            jpath = os.path.join(BASE, jname)
        if os.path.exists(jpath):
            try:
                return {int(r["seq"]): (r["odds_home"], r["odds_draw"], r["odds_away"])
                        for r in json.load(open(jpath, encoding="utf-8")) if r.get("pinned")}
            except Exception:
                return {}
    return {}


def _top_dir(odds3):
    ho, dr, ao = odds3
    return min((("主胜", ho), ("平局", dr), ("客胜", ao)), key=lambda x: x[1])[0]


def _score_warning_signals(conn, period, rmap):
    """复盘该期时逐条读信号×赛果补登。返回汇总行列表（无信号表/无信号行返回[]）。"""
    _ws_init_cols(conn)
    try:
        rows = conn.execute(
            "SELECT id, seq, fav_dir, okooo_drift_pp, qiety_drift_pp, pin_diff_pp, "
            "jc_premium_pp FROM ren9_warning_signals WHERE period=? ORDER BY seq, run_ts",
            (period,)).fetchall()
    except sqlite3.OperationalError:
        return []
    if not rows:
        return []
    ok_tops = _okooo_latest_tops(conn, period)
    pin_tops = _pin_tops(period)
    n_hit = n_miss = n_und = n_div = 0
    ok_right = pin_right = 0
    for rid, seq, fav, okd, qyd, pind, jcp in rows:
        seq = int(seq)
        fired_w = (okd is not None and okd <= _WW_OK_DRIFT) or \
                  (qyd is not None and qyd <= _WW_QY_DRIFT)
        fired_d = pind is not None and abs(pind) >= _WW_PIN_DIV
        fired_p = jcp is not None and jcp > _WW_JC_PREM
        if not (fired_w or fired_d or fired_p):
            continue
        actual = RES.get(rmap.get(seq)) if rmap.get(seq) is not None else None
        hit = otr = ptr = None
        if actual is None:
            n_und += 1
        else:
            if fired_w or fired_p:
                hit = 0 if actual == fav else 1  # 热门/溢价向未打出=命中
                n_hit += hit; n_miss += (1 - hit)
            if fired_d:
                n_div += 1
                if seq in ok_tops and all(o and o > 1.0 for o in ok_tops[seq]):
                    otr = 1 if _top_dir(ok_tops[seq]) == actual else 0
                    ok_right += otr
                if seq in pin_tops:
                    ptr = 1 if _top_dir(pin_tops[seq]) == actual else 0
                    pin_right += ptr
        note = "；".join(t for t in (
            "时序走弱(澳客%spp%s)" % (okd, f"/qiety{qyd}" if qyd is not None else "")
            if fired_w else "",
            f"竞彩溢价({jcp:+.2f}pp)" if fired_p else "",
            f"跨源分歧(Pin{pind:+.2f}pp)" if fired_d else "") if t)
        # 只UPDATE本行4个赛果补登列，信号原始pp值永不动（本表唯一UPDATE例外）
        conn.execute("""UPDATE ren9_warning_signals
            SET outcome_hit=?, okooo_top_right=?, pin_top_right=?, note=?
            WHERE id=?""", (hit, otr, ptr, note, rid))
    conn.commit()
    n_fired = n_hit + n_miss + n_und
    lines = [f"【预警信号记分】本期触发 {n_fired} 条：命中{n_hit}/误报{n_miss}/未判定{n_und}"]
    if n_div:
        lines.append(f"  跨源分歧 {n_div} 条：澳客顶选对 {ok_right} ｜ Pin顶选对 {pin_right}")
    # 开季累计：信号表全量重算（不建新表，保持单一数据源）。
    # 未判定口径=触发了但4个补登列全NULL（赛果缺失）；分歧行有结果时otr/ptr
    # 必有值，不会被误计入未判定。
    acc = conn.execute("""SELECT COUNT(*),
            SUM(CASE WHEN outcome_hit=1 THEN 1 ELSE 0 END),
            SUM(CASE WHEN outcome_hit=0 THEN 1 ELSE 0 END),
            SUM(CASE WHEN outcome_hit IS NULL AND okooo_top_right IS NULL
                      AND pin_top_right IS NULL THEN 1 ELSE 0 END),
            SUM(okooo_top_right), SUM(pin_top_right),
            SUM(CASE WHEN pin_diff_pp IS NOT NULL AND ABS(pin_diff_pp)>=2.0 THEN 1 ELSE 0 END)
        FROM ren9_warning_signals WHERE note IS NOT NULL""").fetchone()
    a_n, a_hit, a_miss, a_und, a_okr, a_pinr, a_div = acc
    if a_n:
        lines.append(f"  开季累计（全量重算）：{a_n} 条触发：命中{a_hit or 0}/误报{a_miss or 0}"
                     f"/未判定{a_und or 0}；分歧 {a_div or 0} 条里澳客顶选对 {a_okr or 0}、"
                     f"Pin顶选对 {a_pinr or 0}")
    return lines

# ── 规则函数 ──
def apply_rules(ho, dr, ao, mode):
    """返回 picks 集合（子集 of {主胜,平局,客胜}）。
    mode='old' 旧规则；mode='new' 新规则（今日固化）"""
    odds = {"主胜": ho, "平局": dr, "客胜": ao}
    valid = {k: v for k, v in odds.items() if v and v > 1.0}
    if not valid:
        return set()
    hot = min(valid, key=valid.get)
    hot_odds = valid[hot]

    if mode == "old":
        if hot_odds < 1.3:
            return {hot}
        elif hot_odds < 1.5:
            return {hot}
        elif hot_odds < 1.9:
            return {hot, "平局"}   # 强队防平
        else:
            if 2.5 <= dr <= 3.5:
                return {hot, "平局"}
            return {hot, min([k for k in valid if k != hot], key=valid.get)}
    else:  # new
        if hot_odds < 1.5:
            return {hot}                    # 单选线 <1.5
        elif hot_odds < 1.9:
            return {hot, "平局"}            # 强队防平
        else:  # 势均力敌（热门 >=1.9）
            if dr < 3.5:
                return {"主胜", "客胜"}     # 平局黄金档→博分胜负
            # 平局赔率偏高，双选热门+第二热门
            second = min([k for k in valid if k != hot], key=valid.get)
            return {hot, second}


def init_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS ren9_rule_review (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period TEXT NOT NULL,
        seq INTEGER NOT NULL,
        home_team TEXT, away_team TEXT,
        odds_home REAL, odds_draw REAL, odds_away REAL,
        actual INTEGER,
        old_picks TEXT, new_picks TEXT,
        old_hit INTEGER, new_hit INTEGER,
        fetch_date TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        UNIQUE(period, seq)
    )""")
    # 2026-08-17新增：DP精确解(生产算法，见ren9_analysis.py)的样本外(未来真实
    # 期次)追踪列。old/new是2026-08-15固化的规则，DP是2026-08-17验证有效
    # (+6.2%相对提升，939个真实历史期次交叉验证)后已升级为生产逻辑的新算法，
    # 复盘表必须跟上，否则长期累积的只是过时算法的样本外数据，见CLAUDE.md
    # 项目规则"禁止删除表结构，只允许ADD COLUMN"
    for col, coltype in [("dp_mode", "TEXT"), ("dp_pick", "TEXT"), ("dp_hit", "INTEGER")]:
        try:
            conn.execute(f"ALTER TABLE ren9_rule_review ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass  # 列已存在
    # FIX-007-2（2026-09-13）新增：翻主规则A/B前向追踪列。
    # top2_hit=按去水赔率前两热门做双选是否虚拟命中（对照组）；
    # flip_hit=翻主规则触发档(弱客热门2.2~3.0)按"主+平"双选是否虚拟命中，
    # 未触发场次留NULL（A/B只在触发子集上对比，避免被未触发场次稀释）。
    # 只从26124期起记录（翻主规则出自历史回测，回填旧期=样本内污染，
    # 前向追踪必须样本外，见CLAUDE.md"前向追踪纪律"）。
    for col, coltype in [("top2_hit", "INTEGER"), ("flip_hit", "INTEGER")]:
        try:
            conn.execute(f"ALTER TABLE ren9_rule_review ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass  # 列已存在
    # FIX-007-7（2026-09-13）新增：临场单追踪列。live_dp_pick/live_dp_hit 从
    # ren9_live_slips(slip_type='live')读取"开奖日19:00临场单"的实际选号。
    # （FIX-016-1注：dp_pick/dp_hit 自2026-09-15起同为票面口径=live优先/early
    # 兜底；live_dp_* 列保留，专指"临场单"这一版，供与 early 单、pin 臂对账。）
    for col, coltype in [("live_dp_pick", "TEXT"), ("live_dp_hit", "INTEGER")]:
        try:
            conn.execute(f"ALTER TABLE ren9_rule_review ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass  # 列已存在
    # FIX-009-4（2026-09-14）新增：Pinnacle比对臂追踪列。
    # pin_diverge=当场 Pinnacle临场DP(ren9_live_slips slip_type='pin_live')与
    # 澳客临场DP(live_dp_pick)选号是否不同(1=分歧,0=一致,任一方未出单=NULL)；
    # pin_dp_hit=Pinnacle临场DP该场选号是否命中。两列都在复盘时（有actual后）
    # 由本脚本填充——19:00出单时赛果未知，不可能当场写hit。
    # 攒样本后回答"Pinnacle临场价驱动的DP是否比澳客临场DP更准"（周报
    # weekly_settlement_compare.py 有"分歧对账"页）。
    for col, coltype in [("pin_diverge", "INTEGER"), ("pin_dp_hit", "INTEGER")]:
        try:
            conn.execute(f"ALTER TABLE ren9_rule_review ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass  # 列已存在
    # FIX-016-1（2026-09-15）新增：dp_hit_recalc 列 + dp_hit 口径切换。
    # 原 dp_pick/dp_hit 是"复盘时点按最新库内赔率重算的DP"，与 as-bought 票面
    # （ren9_live_slips 归档）混为一谈——26125 实证票面 8/9、重算 9/9，
    # 头条"9/9🎉"造成"全中还亏钱"假象。现 dp_pick/dp_hit 只记票面口径
    # （live 临场单优先，无则 early 早场单），重算口径进 dp_hit_recalc。
    for col, coltype in [("dp_hit_recalc", "INTEGER")]:
        try:
            conn.execute(f"ALTER TABLE ren9_rule_review ADD COLUMN {col} {coltype}")
        except sqlite3.OperationalError:
            pass  # 列已存在
    # 一次性迁移：无票面归档的期次，旧 dp_hit（重算口径）挪到 dp_hit_recalc，
    # dp_hit 置 NULL，保证列语义统一（有归档的 26124/26125 由复盘重写，不动）。
    try:
        conn.execute("""UPDATE ren9_rule_review SET dp_hit_recalc = dp_hit, dp_hit = NULL
            WHERE dp_hit IS NOT NULL AND dp_hit_recalc IS NULL
              AND (period || '|' || seq) NOT IN (
                  SELECT period || '|' || seq FROM ren9_live_slips
                  WHERE slip_type IN ('live','early'))""")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # ren9_live_slips 不存在（老库）时跳过迁移


N_SINGLE, N_DOUBLE = 4, 5  # 任九64元复式 = 4单选+5双选(+5跳过)


def _devig(ho, dr, ao):
    ih, idr, ia = 1.0 / ho, 1.0 / dr, 1.0 / ao
    tot = ih + idr + ia
    return ih / tot, idr / tot, ia / tot


def dp_optimal(entries, n_single, n_double):
    """0/1背包式DP：在"恰好n_single个单选+n_double个双选(+其余跳过)"约束下，
    精确最大化P(全部选中场全中)连乘积。entries需含 single_val/double_val 字段。
    与 ren9_analysis.py 的 _ren9_dp_optimal() 同一套实现（generalized出
    n_single/n_double参数，供十四场板块复用，见_backtest_ren9_dp_optimal_0817.py）。
    返回 (single索引list, double索引list)"""
    n = len(entries)
    log_s = [math.log(max(e["single_val"], 1e-12)) for e in entries]
    log_d = [math.log(max(e["double_val"], 1e-12)) for e in entries]
    NEG = float("-inf")
    dp = [[[NEG] * (n_double + 1) for _ in range(n_single + 1)] for _ in range(n + 1)]
    dp[0][0][0] = 0.0
    choice = [[[None] * (n_double + 1) for _ in range(n_single + 1)] for _ in range(n + 1)]
    for i in range(1, n + 1):
        for s in range(n_single + 1):
            for d in range(n_double + 1):
                best, best_c = dp[i-1][s][d], "skip"
                if s > 0 and dp[i-1][s-1][d] > NEG:
                    v = dp[i-1][s-1][d] + log_s[i-1]
                    if v > best:
                        best, best_c = v, "single"
                if d > 0 and dp[i-1][s][d-1] > NEG:
                    v = dp[i-1][s][d-1] + log_d[i-1]
                    if v > best:
                        best, best_c = v, "double"
                dp[i][s][d] = best
                choice[i][s][d] = best_c
    if dp[n][n_single][n_double] == NEG:
        return None, None
    s, d = n_single, n_double
    singles, doubles = [], []
    for i in range(n, 0, -1):
        c = choice[i][s][d]
        if c == "single":
            singles.append(i - 1); s -= 1
        elif c == "double":
            doubles.append(i - 1); d -= 1
    return singles, doubles


def run(period, push=True):
    conn = sqlite3.connect(DB, timeout=60)
    init_table(conn)

    # 1) 抓赔率
    odds_data = okooo.fetch_ren9(period)
    omap = {}
    for m in odds_data.get("matches", []):
        try:
            seq = int(m["seq"])
        except Exception:
            continue
        omap[seq] = m
    if not omap:
        # okooo 页面下架后回退库内赔率（复盘不过期）
        for seq, hc, ac, ho, dr, ao in conn.execute(
                """SELECT seq, home_team, away_team, odds_home, odds_draw, odds_away
                   FROM okooo_ren9_matches WHERE lottery_no=?""", (period,)):
            try:
                seq = int(seq)
            except Exception:
                continue
            omap[seq] = {"seq": seq, "home_team": hc, "away_team": ac,
                         "odds_home": ho, "odds_draw": dr, "odds_away": ao}
        if omap:
            print("okooo 页面无数据，回退库内赔率")

    # 2) 抓开奖结果
    try:
        result_data = sfc.fetch_period(period)
    except Exception as e:
        print(f"开奖抓取失败: {e}")
        conn.close()
        return
    rmap = {m["seq"]: m.get("result") for m in result_data.get("matches", [])}

    if not rmap or all(v is None for v in rmap.values()):
        # FIX-009-3（2026-09-14）：500网开奖页未更新时回退库内结果（与上方赔率
        # 回退同一思路："复盘不过期"）。库内结果可能来自人工录入（如官方开奖后
        # 500网未同步的窗口期），后续44号抓到官方值会 INSERT OR REPLACE 覆盖校正。
        db_rmap = {}
        for _seq, _res in conn.execute(
                "SELECT seq, result FROM lottery_sfc_matches"
                " WHERE period=? AND result IS NOT NULL", (period,)):
            try:
                db_rmap[int(_seq)] = _res
            except (TypeError, ValueError):
                continue
        if db_rmap:
            rmap = db_rmap
            print("500网开奖页无结果，回退库内 lottery_sfc_matches 结果")

    if not omap or not rmap or all(v is None for v in rmap.values()):
        print(f"{period} 期尚未开奖或赔率缺失，跳过")
        conn.close()
        return

    lines = [f"🥔 任九/胜负彩 · 第{period}期 · 规则复盘", ""]

    # 官方开奖数据落库（比分+奖金+销量，INSERT OR REPLACE 幂等）+ 奖金入报
    # FIX-009-3：仅当开奖页真的带出结果时才落库——空结果的 REPLACE 会把
    # 库里已有结果（含人工录入的回退值）覆盖成 NULL。
    try:
        if any(m.get("result") is not None for m in result_data.get("matches", [])):
            sfc.save_period(conn, result_data, datetime.now().strftime("%Y-%m-%d"))
            pz = result_data.get("prizes") or []
            if pz:
                lines.append("官方奖金: " + " ｜ ".join(
                    f"{p['tier']} {p['winning_count']}注×{p['prize_amount']:.0f}元" for p in pz))
                lines.append("")
    except Exception as e:
        print(f"官方数据落库失败: {e}")
    old_hit = new_hit = old_tot = new_tot = 0
    diff = []

    # ── DP精确解·复盘时点重算口径（2026-08-17新增，生产算法，见ren9_analysis.py/RULES文档）──
    # old/new是逐场独立规则，DP是整期联合优化：在"恰好4单选+5双选(+其余跳过)"
    # 约束下精确最大化P(9场全中)。这里对当期全部有赔率+有赛果的场次跑一遍DP，
    # 记录每场被DP分到single/double/skip哪一类、DP选的方向、以及是否命中，
    # 供后续跟old/new做样本外(真实未来期次)对比，而不是只有backtest里的历史回测。
    # （FIX-016-1：本段是"复盘时点按最新库内赔率重算"的分析口径，进 dp_hit_recalc；
    #  as-bought 票面口径见下方 slip_by_seq，进 dp_pick/dp_hit，两者并列展示不混淆。）
    dp_seqs = sorted(seq for seq in omap.keys() if rmap.get(seq) is not None
                     and omap[seq].get("odds_home") and omap[seq].get("odds_draw")
                     and omap[seq].get("odds_away"))
    dp_entries = []
    for seq in dp_seqs:
        m = omap[seq]
        ho, dr, ao = m["odds_home"], m["odds_draw"], m["odds_away"]
        ph, pd_, pa = _devig(ho, dr, ao)
        probs = {"主胜": ph, "平局": pd_, "客胜": pa}
        ranked = sorted(probs, key=probs.get, reverse=True)
        dp_entries.append(dict(seq=seq, single_pick=ranked[0], single_val=probs[ranked[0]],
                               double_pick=set(ranked[:2]), double_val=probs[ranked[0]] + probs[ranked[1]]))
    dp_by_seq = {}
    if len(dp_entries) >= N_SINGLE + N_DOUBLE:
        s_idx, d_idx = dp_optimal(dp_entries, N_SINGLE, N_DOUBLE)
        if s_idx is not None:
            for i in s_idx:
                dp_by_seq[dp_entries[i]["seq"]] = ("single", dp_entries[i]["single_pick"])
            for i in d_idx:
                dp_by_seq[dp_entries[i]["seq"]] = ("double", "+".join(sorted(dp_entries[i]["double_pick"])))
    else:
        lines.append(f"【DP提示】本期仅{len(dp_entries)}场有完整赔率+赛果，不足9场无法求解DP复式，DP列留空")
        lines.append("")

    # FIX-007-7：读临场单实际选号（ren9_live_slips, slip_type='live'，
    # 开奖日19:00由 ren9_live_slip.py 生成）。该期没出临场单则为空dict，
    # live_dp_* 列留 NULL。
    live_by_seq = {}
    try:
        for _seq, _pick in conn.execute(
                "SELECT seq, pick FROM ren9_live_slips WHERE period=? AND slip_type='live'",
                (period,)):
            live_by_seq[int(_seq)] = _pick
    except sqlite3.OperationalError:
        pass  # 表不存在（老库）时视为无临场单

    # FIX-009-4：Pinnacle比对臂选号（slip_type='pin_live'，19:00临场任务里
    # 15号代理重抓Pinnacle后跑的第二套DP），用于跟澳客临场单逐场对账
    pin_by_seq = {}
    try:
        for _seq, _pick in conn.execute(
                "SELECT seq, pick FROM ren9_live_slips WHERE period=? AND slip_type='pin_live'",
                (period,)):
            pin_by_seq[int(_seq)] = _pick
    except sqlite3.OperationalError:
        pass

    # FIX-016-1：票面DP(as-bought)选号——live 临场单优先，该期无临场单则退
    # early 早场单。这是"实际买入的那张票"，与 dp_by_seq（复盘时点按最新库内
    # 赔率重算，仅供分析参考）严格分开（26125 实证分叉：票面8/9 vs 重算9/9）。
    slip_by_seq = {}
    try:
        for _seq, _pick, _st in conn.execute(
                "SELECT seq, pick, slip_type FROM ren9_live_slips "
                "WHERE period=? AND slip_type IN ('live','early')", (period,)):
            _seq = int(_seq)
            if _st == 'live' or _seq not in slip_by_seq:
                slip_by_seq[_seq] = (_pick, _st)
    except sqlite3.OperationalError:
        pass  # 表不存在（老库）时视为无票面归档

    for seq in sorted(omap.keys()):
        m = omap[seq]
        ho, dr, ao = m.get("odds_home"), m.get("odds_draw"), m.get("odds_away")
        actual_r = rmap.get(seq)
        if actual_r is None:
            continue
        actual = RES.get(actual_r, "?")
        op = apply_rules(ho, dr, ao, "old")
        np = apply_rules(ho, dr, ao, "new")
        o_hit = 1 if actual in op else 0
        n_hit = 1 if actual in np else 0
        old_tot += 1; new_tot += 1
        old_hit += o_hit; new_hit += n_hit
        if op != np:
            diff.append((seq, m["home_team"], m["away_team"], actual, op, np, o_hit, n_hit))

        # FIX-016-1：dp_pick/dp_hit=票面(as-bought)口径，dp_hit_recalc=复盘时点重算
        dp_mode, dp_pick, dp_hit = None, None, None
        if seq in slip_by_seq:
            dp_pick, _slip_type = slip_by_seq[seq]
            dp_mode = "double" if "+" in dp_pick else "single"
            dp_hit = 1 if actual in dp_pick.split("+") else 0
        dp_hit_recalc = None
        if seq in dp_by_seq:
            _rec_mode, _rec_pick = dp_by_seq[seq]
            dp_hit_recalc = 1 if actual in _rec_pick.split("+") else 0

        # ── FIX-007-2 翻主规则A/B（26124期起记录，样本外前向追踪）──
        # 目标：评估"弱客热门2.2~3.0翻主+平"相对top2双选对整期全中概率的影响，
        # 攒30-50期后按数据决定翻主规则去留（CLAUDE.md"前向追踪纪律"）。
        top2_hit, flip_hit = None, None
        if period >= "26124" and ho and dr and ao and ho > 1.0 and dr > 1.0 and ao > 1.0:
            _ph, _pd, _pa = _devig(ho, dr, ao)
            _probs = {"主胜": _ph, "平局": _pd, "客胜": _pa}
            _ranked = sorted(_probs, key=_probs.get, reverse=True)
            top2_hit = 1 if actual in set(_ranked[:2]) else 0
            # 翻主触发档：客胜是最低赔率(弱客热门)且落在2.2~3.0
            if min(ho, dr, ao) == ao and 2.2 <= ao <= 3.0:
                flip_hit = 1 if actual in ("主胜", "平局") else 0

        live_dp_pick, live_dp_hit = None, None
        if seq in live_by_seq:
            live_dp_pick = live_by_seq[seq]
            live_dp_hit = 1 if actual in live_dp_pick.split("+") else 0

        # FIX-009-4：Pinnacle比对臂对账。pin_diverge只在双方都有选号的场上
        # 判定（pin臂覆盖不足12场会整期跳过，或单队名映射失败会单场缺失）。
        pin_diverge, pin_dp_hit = None, None
        if seq in pin_by_seq:
            pin_dp_hit = 1 if actual in pin_by_seq[seq].split("+") else 0
            if seq in live_by_seq:
                pin_diverge = 0 if pin_by_seq[seq] == live_by_seq[seq] else 1

        conn.execute("""INSERT INTO ren9_rule_review
            (period, seq, home_team, away_team, odds_home, odds_draw, odds_away,
             actual, old_picks, new_picks, old_hit, new_hit, dp_mode, dp_pick, dp_hit,
             dp_hit_recalc, top2_hit, flip_hit, live_dp_pick, live_dp_hit, pin_diverge, pin_dp_hit,
             fetch_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now','localtime'))
            ON CONFLICT(period, seq) DO UPDATE SET
             actual=excluded.actual, old_picks=excluded.old_picks,
             new_picks=excluded.new_picks, old_hit=excluded.old_hit,
             new_hit=excluded.new_hit, dp_mode=excluded.dp_mode,
             dp_pick=excluded.dp_pick, dp_hit=excluded.dp_hit,
             dp_hit_recalc=excluded.dp_hit_recalc,
             top2_hit=excluded.top2_hit, flip_hit=excluded.flip_hit,
             live_dp_pick=excluded.live_dp_pick, live_dp_hit=excluded.live_dp_hit,
             pin_diverge=excluded.pin_diverge, pin_dp_hit=excluded.pin_dp_hit,
             fetch_date=excluded.fetch_date""",
            (period, seq, m["home_team"], m["away_team"], ho, dr, ao,
             actual_r, ",".join(sorted(op)), ",".join(sorted(np)), o_hit, n_hit,
             dp_mode, dp_pick, dp_hit, dp_hit_recalc, top2_hit, flip_hit, live_dp_pick, live_dp_hit,
             pin_diverge, pin_dp_hit))

        mark = "✅" if n_hit else "❌"
        if dp_hit is not None:
            dp_mark = f" 票面{'✅' if dp_hit else '❌'}"
            if dp_hit_recalc is not None and dp_hit_recalc != dp_hit:
                dp_mark += f"(重算{'✅' if dp_hit_recalc else '❌'})"
        elif dp_hit_recalc is not None:
            dp_mark = f" 重算{'✅' if dp_hit_recalc else '❌'}(无票面)"
        elif dp_by_seq:
            dp_mark = " DP跳过"
        else:
            dp_mark = ""
        lines.append(f"{seq:2d} {m['home_team']}vs{m['away_team']} → {actual} "
                     f"旧{('✅' if o_hit else '❌')} 新{mark}{dp_mark}")

    conn.commit()

    lines.append("")
    lines.append(f"旧规则 {old_hit}/{old_tot} ({old_hit/old_tot*100:.0f}%)")
    lines.append(f"新规则 {new_hit}/{new_tot} ({new_hit/new_tot*100:.0f}%)")
    # FIX-016-1：票面/重算两口径并列展示，🎉只属于票面（真实成绩）
    if slip_by_seq:
        _scored = [(s, p) for s, (p, _st) in slip_by_seq.items() if rmap.get(s) is not None]
        slip_hits = sum(1 for s, p in _scored if RES[rmap[s]] in p.split("+"))
        slip_full = len(_scored) == (N_SINGLE + N_DOUBLE) and slip_hits == len(_scored)
        lines.append(f"票面DP(as-bought，来自live/early归档) {slip_hits}/{len(_scored)} "
                     f"{'🎉本期任九票面全中！' if slip_full else ''}")
    else:
        lines.append("票面DP(as-bought)：本期无 live/early 归档单（早期期次或未出单）")
    if dp_by_seq:
        dp_hits = sum(1 for seq, (mode, pick) in dp_by_seq.items()
                     if RES.get(rmap.get(seq)) in pick.split("+"))
        lines.append(f"复盘时点重算DP {dp_hits}/{N_SINGLE+N_DOUBLE}（分析参考，非票面成绩）")
    if diff:
        lines.append("")
        lines.append("【新旧分歧场次】")
        for seq, h, a, actual, op, np, oh, nh in diff:
            verdict = "新对" if (nh and not oh) else ("旧对" if (oh and not nh) else ("都对" if (oh and nh) else "都错"))
            lines.append(f"  {seq} {h}vs{a} → {actual} | 旧{'/'.join(sorted(op))} 新{'/'.join(sorted(np))} → {verdict}")

    # 势均双选方向反事实累计（行动项④：热门≥1.9 档，主+平 vs 客+平，攒30期裁决）
    try:
        ev = conn.execute("""SELECT COUNT(*),
                SUM(CASE WHEN actual IN (3,1) THEN 1 ELSE 0 END),
                SUM(CASE WHEN actual IN (0,1) THEN 1 ELSE 0 END),
                COUNT(DISTINCT period),
                SUM(CASE WHEN actual=3 THEN 1 ELSE 0 END),
                SUM(CASE WHEN actual=1 THEN 1 ELSE 0 END),
                SUM(CASE WHEN actual=0 THEN 1 ELSE 0 END)
            FROM ren9_rule_review
            WHERE actual IS NOT NULL AND odds_home IS NOT NULL
              AND odds_draw IS NOT NULL AND odds_away IS NOT NULL
              AND MIN(odds_home, odds_draw, odds_away) >= 1.9""").fetchone()
        n, hp, ap, nper, nh, nd, na = ev
        if n:
            lines.append("")
            lines.append(f"【势均双选方向反事实累计】热门≥1.9档 {nper}期{n}场：")
            lines.append(f"  主+平 {hp}/{n}({hp/n*100:.0f}%) ｜ 客+平 {ap}/{n}({ap/n*100:.0f}%) ｜ 实际 主{nh}/平{nd}/客{na}")
            if nper < 30:
                lines.append("  （攒30期裁决中，样本不足不下结论）")
    except Exception as e:
        print(f"势均累计查询失败: {e}")

    # ── FIX-007-2 翻主规则A/B累计（触发档子集：flip_hit NOT NULL）──
    try:
        ab = conn.execute("""SELECT COUNT(*),
                SUM(top2_hit), SUM(flip_hit), COUNT(DISTINCT period)
            FROM ren9_rule_review
            WHERE flip_hit IS NOT NULL""").fetchone()
        ab_n, ab_top2, ab_flip, ab_per = ab
        if ab_n:
            lines.append("")
            lines.append(f"【翻主规则A/B累计】触发档(弱客热门2.2~3.0) {ab_per}期{ab_n}场：")
            lines.append(f"  top2双选 {ab_top2}/{ab_n}({ab_top2/ab_n*100:.0f}%) ｜ "
                         f"翻主+平 {ab_flip}/{ab_n}({ab_flip/ab_n*100:.0f}%)")
            if ab_per < 30:
                lines.append("  （攒30-50期裁决中，样本不足不下结论）")
    except Exception as e:
        print(f"翻主A/B累计查询失败: {e}")

    # ── FIX-007-7 临场单 vs 早场单累计（FIX-016-1起两版均为as-bought票面口径，
    # 直接读 ren9_live_slips 归档选号；早场不再用"复盘重算DP"近似）──
    try:
        _lv_rows = conn.execute("""
            SELECT e.period, e.pick, l.pick, r.actual
            FROM ren9_live_slips e
            JOIN ren9_live_slips l ON e.period=l.period AND e.seq=l.seq
            JOIN ren9_rule_review r ON r.period=e.period AND r.seq=e.seq
            WHERE e.slip_type='early' AND l.slip_type='live' AND r.actual IS NOT NULL""").fetchall()
        if _lv_rows:
            lv_n = len(_lv_rows)
            lv_early = sum(1 for _p, ep, lp, act in _lv_rows if RES.get(act) in ep.split("+"))
            lv_live = sum(1 for _p, ep, lp, act in _lv_rows if RES.get(act) in lp.split("+"))
            lv_per = len(set(r[0] for r in _lv_rows))
            lines.append("")
            lines.append(f"【临场单 vs 早场单累计（as-bought票面）】{lv_per}期{lv_n}场（同一批场次对照）：")
            lines.append(f"  早场单 {lv_early}/{lv_n}({lv_early/lv_n*100:.0f}%) ｜ "
                         f"临场单 {lv_live}/{lv_n}({lv_live/lv_n*100:.0f}%)")
            if lv_per < 30:
                lines.append("  （攒30-50期裁决中，样本不足不下结论）")
    except Exception as e:
        print(f"临场单累计查询失败: {e}")

    # ── FIX-009-4 Pinnacle比对臂：本期对账小结（累计周榜见 weekly_settlement_compare.py）──
    if pin_by_seq:
        pn = sum(1 for s in pin_by_seq if rmap.get(s) is not None)
        p_hit = sum(1 for s, p in pin_by_seq.items()
                    if RES.get(rmap.get(s)) in p.split("+"))
        n_div = sum(1 for s in pin_by_seq
                    if s in live_by_seq and pin_by_seq[s] != live_by_seq[s])
        lines.append("")
        lines.append(f"【Pinnacle临场DP】本期 {p_hit}/{pn} ｜ 与澳客临场单分歧 {n_div} 场")
        # PIN-COVER-001：臂出单但单场缺失 = generated_null（映射失败/三向不全）
        n_missing = sum(1 for s in omap if s not in pin_by_seq)
        if n_missing:
            lines.append(f"  pin_diverge=NULL 标注：generated_null——臂已出单，"
                         f"{n_missing} 场无 pin 选号（单场映射失败/三向不全），"
                         f"详见 pin_arm_runs.skip_reason")
    else:
        # PIN-COVER-001：pin_diverge=NULL 三义拆分——not_run / coverage_lt_12 等
        # 跳过类 / generated_null。溯源=pin_arm_runs 表（ren9_live_slip 落库）
        try:
            _run = conn.execute(
                "SELECT status, coverage_n, coverage_total, skip_reason, run_ts "
                "FROM pin_arm_runs WHERE period=?", (period,)).fetchone()
        except sqlite3.OperationalError:
            _run = None   # 表不存在（老库）时按 not_run 处理
        if _run is None:
            lines.append("")
            lines.append("【Pinnacle临场DP】本期无产物。pin_diverge=NULL 标注："
                         "not_run（pin_arm_runs 无本期记录=比对臂未执行/老库无表）")
        elif _run[0] == "generated":
            lines.append("")
            lines.append(f"【Pinnacle临场DP】本期无产物。pin_diverge=NULL 标注："
                         f"generated_null——臂出单（覆盖{_run[1]}/{_run[2]}）但"
                         f"ren9_live_slips 无 pin_live 行，需人工核查归档链")
        else:
            lines.append("")
            lines.append(f"【Pinnacle临场DP】本期无产物。pin_diverge=NULL 标注："
                         f"{_run[0]}（覆盖{_run[1]}/{_run[2]}，{_run[3]}，"
                         f"run_ts={_run[4]}）")

    # ── FIX-012（2026-09-14）：预警信号×赛果自动记分（人工记分卡变自动）──
    try:
        lines.append("")
        lines.extend(_score_warning_signals(conn, period, rmap))
    except Exception as e:
        print(f"预警信号记分失败: {e}")

    text = "\n".join(lines)
    print(text)
    conn.close()

    if push:
        _push(text)


def _push(text):
    try:
        cfg = json.load(open(r"C:\Users\cn\.openclaw\openclaw.json", encoding="utf-8"))
        feishu = cfg.get("channels", {}).get("feishu", {})
        app_id = feishu.get("appId", ""); app_secret = feishu.get("appSecret", "")
    except Exception as e:
        print(f"读飞书凭证失败: {e}"); return
    if not app_id or not app_secret:
        print("飞书凭证缺失，跳过推送"); return
    import requests
    tr = requests.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                       json={"app_id": app_id, "app_secret": app_secret}, timeout=20)
    token = (tr.json() or {}).get("tenant_access_token", "")
    if not token:
        print("飞书token获取失败"); return
    mr = requests.post("https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
                       headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                       json={"receive_id": os.environ.get("FEISHU_RECEIVE_ID", "REDACTED"),
                             "msg_type": "text",
                             "content": json.dumps({"text": text}, ensure_ascii=False)}, timeout=20)
    code = (mr.json() or {}).get("code")
    print("飞书推送:", "成功" if code == 0 else f"失败 code={code}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", required=True)
    ap.add_argument("--no-push", action="store_true")
    args = ap.parse_args()
    run(args.period, push=not args.no_push)
