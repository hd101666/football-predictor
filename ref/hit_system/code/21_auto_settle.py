# -*- coding: utf-8 -*-
"""
21_auto_settle.py — 赛果自动回填脚本（v2）
双层回填：
  1. 通过 unified_id 直接 JOIN unified_matches（最快最准）
  2. 通过队名模糊匹配 match_results（补漏）

用法：
  python 21_auto_settle.py              # 回填所有待结算推荐
  python 21_auto_settle.py --date 2026-05-30  # 只回填指定日期
"""
import os, sys, re, logging, subprocess
from datetime import datetime, timedelta
from collections import defaultdict
from difflib import SequenceMatcher

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

os.environ['PYTHONUTF8'] = '1'
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from sqlalchemy import create_engine, text
from config import DB_ENGINE_URL, SLIP_OUTPUT_DIR, slip_output_dir, PAPER_WATERMARK, is_live_betting
from team_zh import team_zh as _team_zh_raw
from htft_settle import classify_ht_ft

# 2026-09-05性能修复：team_zh()精确/后缀匹配都找不到时会退化成遍历整个
# TEAM_ZH字典(数千条)做正则子串匹配，是重操作。本文件的第三/四层兜底要对
# 同一批fotmob_matches/qiumibao_match_results历史数据(上万行，队名大量重复——
# 同一支球队打了几十上百场比赛)反复调用_team_zh()，进程内用字典缓存住每个
# 队名第一次算出来的结果，后面同名队直接查缓存，不用每次都重新遍历字典。
# 缓存基于team_zh.py的静态映射表，进程生命周期内不会变，跨多次结算调用
# (同一次python进程里settle函数会被调好几次)也能一直复用，不用每次重置。
_TEAM_ZH_CACHE: dict[str, str] = {}


def _team_zh(name: str) -> str:
    if name not in _TEAM_ZH_CACHE:
        _TEAM_ZH_CACHE[name] = _team_zh_raw(name)
    return _TEAM_ZH_CACHE[name]


engine = create_engine(DB_ENGINE_URL, connect_args={'timeout': 60})
log = logging.getLogger("auto_settle")

# 市场/结果中文映射（与 00_命中系统.py 的 _MARKET_ZH/_OUTCOME_ZH 保持一致，
# 该文件名以数字开头无法被 import，这里维护一份小副本）
_MARKET_ZH = {
    "moneyline": "独赢", "spread": "让球", "total": "大小球",
    "team_total": "球队大小", "team_total_home": "主队大小", "team_total_away": "客队大小",
    "draw_no_bet": "平局无效",
    "corner_ou": "角球大小", "corner_hdp": "角球让球", "corner_total": "角球大小",
    "correct_score": "比分",
}
_OUTCOME_ZH = {
    "home": "主胜", "away": "客胜", "draw": "平局",
    "over": "大球", "under": "小球",
}


# ─── 队名标准化（用于 match_results 模糊匹配）─────────────────────────────

def _normalize(name: str) -> str:
    """标准化队名用于模糊匹配"""
    if not name:
        return ""
    n = name.lower().strip()
    # 去掉常见后缀/缩写：FC/CF/SC/AC/俱乐部、年份、FR/RJ/MG 等州名缩写
    for suffix in [" fc", " cf", " sc", " ac", " bc", " tk", " as",
                    " sv", " ag", " a/s", " 1920", " 1899", " 1903",
                    " 1905", " 1908", " 1910", " 1911", " 1913",
                    " club", " team", " city",
                    # 巴西/南美州名缩写（大小写已 lower）
                    " fr", " rj", " mg", " sp", " rs", " pr", " sc ",
                    " go", " ba", " ce", " pe", " rn", " pb", " al",
                    # 国家/地区括注会连同括号被后面的非字母数字正则清掉，
                    # 但裸后缀如 "kaz", "alb", "bih" 也得去
                    " kaz", " alb", " bih", " mne", " lux", " fai",
                    " blr", " nir", " mlt", " kos", " mkd", " az ",
                    " est", " wal", " hun", " lat", " isr", " cyp",
                    " gre", " slo", " svk", " cze", " pol", " bul",
                    " srb", " cro", " slo", " esp", " ita", " ger",
                    " fra", " ned", " bel", " den", " swe", " nor",
                    " fin", " isl", " aut", " sui", " rus", " ukr",
                    " geo", " arm", " aze", " kaz", " uzb", " tjk",
                    " kgz", " tur", " qaz", " rsa", " nga", " cmr"]:
        n = n.replace(suffix, "")
    n = re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", n)
    return n


def _layer2_fuzzy_scores(conn, unmatched_uids: set, uid_sport: dict) -> dict:
    """队名模糊匹配 match_results 兜底，为 unified_id 直连未命中的记录补比分。
    三个结算函数(主推荐单/小球影子/其他影子)共用同一套兜底逻辑，避免只有
    主推荐单能兜底、影子单永远卡在 unified_matches.home_score(只有
    00_命中系统.py 内部 ESPN 同步才会填)导致长期0结算的问题。
    返回 {unified_id: (home_score, away_score, home_score_ht, away_score_ht)}——
    match_results 表没有半场比分列，后两个恒为 None（半全场市场走这条兜底路径
    时会因缺半场分判 pending，不会误判，也不会崩）。"""
    if not unmatched_uids:
        return {}

    mr_results = conn.execute(text("""
        SELECT home_team, away_team, home_score, away_score,
               match_date, kickoff_utc, sport
        FROM match_results
        WHERE home_score IS NOT NULL
    """)).fetchall()

    by_date = defaultdict(list)
    for rh, ra, hs, aws, md, ko, sp in mr_results:
        date_str = md if md else (ko[:10] if ko else "")
        by_date[date_str].append((rh, ra, hs, aws, sp))

    uid_team_map = {}
    batch = list(unmatched_uids)
    placeholders = ','.join([f":u{j}" for j in range(len(batch))])
    params = {f"u{j}": uid for j, uid in enumerate(batch)}
    try:
        team_rows = conn.execute(text(f"""
            SELECT unified_id, home_team_std, away_team_std, fetch_date, kickoff_utc
            FROM unified_matches
            WHERE unified_id IN ({placeholders})
        """), params).fetchall()
        for uid, ht, at, fd, ko in team_rows:
            # Bug修复(2026-07-25)：锚定日期优先用kickoff_utc（真实开赛日期），
            # fetch_date只在没有kickoff_utc时兜底。推荐单窗口本身就是"今日+次日
            # 12:00前"（见CLAUDE.md永久规则），同一支球队/联赛背靠背两天各打一场
            # 时（实测墨西哥篮球LNBP），旧代码锚定fetch_date会让offset=0直接命中
            # "fetch_date当天"那场比赛的比分，即便真实kickoff是次日、真正对应的
            # 是另一场比赛——本该匹配次日那场，却误配到fetch_date当天那场，方向
            # 恰好没错纯属运气，遇到两场比分方向不同时会真实判错胜负。
            anchor_date = (ko[:10] if ko else fd)
            uid_team_map[uid] = (ht, at, anchor_date)
    except Exception as e:
        print(f"  队名查询失败: {e}")

    matched_scores = {}
    for uid in unmatched_uids:
        if uid not in uid_team_map:
            continue
        ht, at, fd = uid_team_map[uid]
        rec_sport = uid_sport.get(uid)
        matched = None
        for offset in [0, -1, 1, -2, 2]:
            try:
                d = datetime.strptime(fd, "%Y-%m-%d") + timedelta(days=offset)
                search_date = d.strftime("%Y-%m-%d")
            except:
                continue
            for rh, ra, hs, aws, sp in by_date.get(search_date, []):
                if rec_sport and sp and sp != rec_sport:
                    continue
                if _fuzzy_match(ht, at, rh, ra):
                    matched = (hs, aws, None, None)
                    break
            if matched:
                break
        if matched:
            matched_scores[uid] = matched

    return matched_scores


def _fuzzy_match(rec_home: str, rec_away: str,
                 res_home: str, res_away: str, threshold: float = 0.58) -> bool:
    """模糊匹配两对队名。
    三级匹配：
      1) 完全相等
      2) 任一方向子串包含（解决 "dinamo" ⊂ "dinamotirana"）
      3) SequenceMatcher 平均相似度 ≥ threshold（默认 0.58，旧值 0.65 偏严）
    """
    rh = _normalize(rec_home)
    ra = _normalize(rec_away)
    mh = _normalize(res_home)
    ma = _normalize(res_away)
    if not rh or not ra or not mh or not ma:
        return False
    if rh == mh and ra == ma:
        return True
    # 双向子串：任一方是另一方的子串即可
    if (rh in mh or mh in rh) and (ra in ma or ma in ra):
        return True
    # SequenceMatcher 模糊匹配
    s_h = SequenceMatcher(None, rh, mh).ratio()
    s_a = SequenceMatcher(None, ra, ma).ratio()
    return (s_h + s_a) / 2 >= threshold


# ─── 赛果判定逻辑 ──────────────────────────────────────────────────────────

def _settle_result(market: str, outcome: str, handicap,
                   home_score, away_score, best_odds: float = 0,
                   home_score_ht=None, away_score_ht=None) -> str:
    """
    根据市场/方向/盘口线/比分判定推荐结果
    返回 'win', 'lose', 'push', 'pending'
    """
    if market == "ht_ft":
        # 半全场：半场+全场结果须同时猜中才算赢，官方规则本身没有"push"（部分中奖）
        ht_r, ft_r = classify_ht_ft(home_score_ht, away_score_ht, home_score, away_score)
        if ht_r is None:
            return "pending"
        return "win" if outcome == f"{ht_r}-{ft_r}" else "lose"

    if home_score is None or away_score is None:
        return "pending"

    try:
        hs = int(home_score)
        aws = int(away_score)
    except (ValueError, TypeError):
        return "pending"

    total = hs + aws

    if market in ("moneyline", "1x2"):
        # Bug修复(2026-09-05)：market='1x2'跟'moneyline'语义完全相同(3选1胜平负)，
        # 但这个判定分支之前只认"moneyline"字符串，'1x2'这个market名走不到任何
        # 分支，直接落到函数末尾的return "pending"——不管前面第1-4层有没有查到
        # 真实比分，判定都会被丢弃。实测qiety_h2h/injury_impact两个影子桶全历史
        # 46条记录因此永久卡在pending，误以为是"赛果数据缺口"，实际比分很可能
        # 早就有了，只是市场名对不上判定分支。
        # Bug修复：home/away打平之前判成push(退回本金)，这只在"平局无效(draw_no_bet)"
        # 这种2选1市场里才对。本系统的football moneyline其实是标准3选1胜平负市场——
        # 只要平局本身是一个独立可下注的outcome("draw"跟"home"/"away"同一个market里
        # 共存，consensus_odds里三个方向都有各自赔率)，选home/away打平就是真实输钱，
        # 不该退款。篮球几乎不会打平(有加时赛)，这个分支对篮球实际不受影响。
        if outcome == "home":
            if hs > aws: return "win"
            else: return "lose"
        elif outcome == "away":
            if aws > hs: return "win"
            else: return "lose"
        elif outcome == "draw":
            if hs == aws: return "win"
            else: return "lose"

    elif market == "total":
        # Bug修复：之前 handicap 为空时默认按2.5线判，这个默认值只对足球合理——
        # 篮球总分线通常200+，用2.5线判会让"大球"恒定判赢、"小球"恒定判输，
        # 跟真实比分无关（实测已污染过历史数据，见 _backtest_totals_over.py 的
        # "handicap=NULL污染样本"分组）。没有真实盘口线就不判，留 pending。
        if handicap is None:
            return "pending"
        line = handicap
        if outcome == "over":
            if total > line: return "win"
            elif total < line: return "lose"
            else: return "push"
        elif outcome == "under":
            if total < line: return "win"
            elif total > line: return "lose"
            else: return "push"

    elif market in ("team_total", "team_total_home", "team_total_away"):
        # team_total: handicap 是进球线，outcome 是 over/under
        # market="team_total_home"/"team_total_away"：Pinnacle抓取端已修复主客队
        # 身份丢失问题（见12_pinnacle_scraper.py），能明确判定该用哪队比分。
        # 裸的"team_total"是历史遗留/未识别主客队来源，沿用旧的"默认主队"简化处理。
        # Bug修复：同上，handicap为空不再默认1.5线（篮球球队分远高于1.5，
        # 会让大小球方向恒定判赢/判输），没有真实线就留 pending。
        if handicap is None:
            return "pending"
        line = handicap
        team_score = aws if market == "team_total_away" else hs
        if outcome == "over":
            if team_score > line: return "win"
            elif team_score < line: return "lose"
            else: return "push"
        elif outcome == "under":
            if team_score < line: return "win"
            elif team_score > line: return "lose"
            else: return "push"

    elif market == "spread":
        # Bug修复(2026-07-22)：原来handicap=None时默认按0(pick'em)处理，等于假装
        # 这是一场没有让分的比赛去判胜负——spread市场的handicap本来就该是必填的
        # 真实盘口线，为None只可能是数据管道某处丢失了这个值(不是"真的没有让分")，
        # 跟total/team_total分支"没有真实盘口线就留pending"应该是同一个处理方式。
        # 实测发现202条历史spread推荐(全部集中在2026-05-28~05-30,系统早期)因这个
        # bug被当pick'em错判了92条win/lose/push，混进后续所有ROI/胜率统计里，
        # 2026-07-22已把这92条手动标记为status='invalid'排除出统计（历史数据，
        # 真实盘口线已不可考，无法重新正确判定，只能标记排除不能重判）。
        if handicap is None:
            return "pending"
        spread = handicap
        if outcome == "home":
            adjusted = hs + spread - aws
            if adjusted > 0: return "win"
            elif adjusted < 0: return "lose"
            else: return "push"
        elif outcome == "away":
            adjusted = aws + spread - hs
            if adjusted > 0: return "win"
            elif adjusted < 0: return "lose"
            else: return "push"

    elif market == "correct_score":
        # outcome 是 "H-A" 格式的精确比分字符串，跟实际比分完全一致才算命中
        return "win" if outcome == f"{hs}-{aws}" else "lose"

    return "pending"


# ─── 主回填逻辑 ──────────────────────────────────────────────────────────

def auto_settle(target_date: str = None):
    """双层自动结算所有待结算推荐"""

    # 建列保护：单独运行时数据库可能还没有 stake/profit_loss 列（00_命中系统.py 的迁移还没跑过）
    with engine.begin() as _mig_conn:
        for _ddl in ("ALTER TABLE hit_recommendations ADD COLUMN stake REAL",
                     "ALTER TABLE hit_recommendations ADD COLUMN profit_loss REAL"):
            try:
                _mig_conn.execute(text(_ddl))
            except Exception:
                pass

    with engine.connect() as conn:
        # 获取待结算推荐
        if target_date:
            recs = conn.execute(text("""
                SELECT id, unified_id, sport_code, home_team, away_team,
                       market, outcome, best_odds, handicap, status,
                       fetch_date, kickoff_utc, league_name, stake
                FROM hit_recommendations
                WHERE (status = 'pending' OR status IS NULL)
                  AND fetch_date = :fd
            """), {"fd": target_date}).fetchall()
        else:
            recs = conn.execute(text("""
                SELECT id, unified_id, sport_code, home_team, away_team,
                       market, outcome, best_odds, handicap, status,
                       fetch_date, kickoff_utc, league_name, stake
                FROM hit_recommendations
                WHERE status = 'pending' OR status IS NULL
            """)).fetchall()

        print(f"[auto_settle] 待结算推荐: {len(recs)} 条")

        if not recs:
            return []

        # ── 第一层：通过 unified_id 直接关联 unified_matches ──
        uid_scores = {}
        uids = list(set(r[1] for r in recs))
        if uids:
            # 分批查询（SQLite IN 子句限制）
            batch_size = 500
            for i in range(0, len(uids), batch_size):
                batch = uids[i:i+batch_size]
                placeholders = ','.join([f":u{j}" for j in range(len(batch))])
                params = {f"u{j}": uid for j, uid in enumerate(batch)}
                rows = conn.execute(text(f"""
                    SELECT unified_id, home_score, away_score, status,
                           home_score_ht, away_score_ht
                    FROM unified_matches
                    WHERE unified_id IN ({placeholders})
                      AND home_score IS NOT NULL
                """), params).fetchall()
                for uid, hs, aws, st, hs_ht, as_ht in rows:
                    uid_scores[uid] = (hs, aws, hs_ht, as_ht)

        print(f"  第一层(unified_id): 匹配到 {len(uid_scores)} 场比分")

        # ── 第二层：通过队名模糊匹配 match_results ──
        # 仅对第一层未匹配的推荐尝试
        unmatched_uids = set(r[1] for r in recs if r[1] not in uid_scores)
        # uid -> sport（一个 unified_id 只对应一场比赛，取自本轮待结算推荐即可）
        uid_sport = {r[1]: r[2] for r in recs}
        matched_scores = _layer2_fuzzy_scores(conn, unmatched_uids, uid_sport)
        uid_scores.update(matched_scores)
        print(f"  第二层(队名模糊): 额外匹配 {len(matched_scores)} 场")

        # ── 第三层：fotmob_matches 兜底(2026-08-25新增，见_apply_fotmob_goal_fallback)──
        # 正式推荐单(hit_recommendations)涉及真实资金盈亏，结算覆盖率必须严谨，
        # 不能有本可结算却因为数据源没接全而卡在pending的记录。
        uid_names = {r[1]: (r[10], r[3], r[4]) for r in recs}  # fd, home, away
        fm_matched = _apply_fotmob_goal_fallback(conn, uid_scores, uid_sport, uid_names)
        print(f"  第三层(fotmob_matches兜底): 额外匹配 {fm_matched} 场")
        qm_matched = _apply_qiumibao_goal_fallback(conn, uid_scores, uid_sport, uid_names)
        print(f"  第四层(qiumibao兜底): 额外匹配 {qm_matched} 场")

    # ── 执行结算 ──
    settled = {"win": 0, "lose": 0, "push": 0, "unmatched": 0, "no_handicap": 0}
    settled_detail = []  # 本次新结算的明细，供 D:\lucky 每日快照使用

    with engine.connect() as conn:
        for rec_id, uid, sport, home, away, market, outcome, odds, hc, status, fd, ko, league, stake in recs:
            if uid not in uid_scores:
                settled["unmatched"] += 1
                continue

            home_score, away_score, home_score_ht, away_score_ht = uid_scores[uid]
            result = _settle_result(market, outcome, hc, home_score, away_score, odds,
                                    home_score_ht, away_score_ht)

            if result == "pending":
                # 可能是 handicap=None 导致的无法判定
                if market in ("spread", "total", "team_total", "team_total_home", "team_total_away") and hc is None:
                    settled["no_handicap"] += 1
                else:
                    settled["unmatched"] += 1
                continue

            # 真实盈亏（元）：只有单注下过注(stake非空)才能算；串关/未入选单注的推荐 stake 为 NULL，盈亏留空
            profit_loss = None
            if stake is not None:
                profit_loss = round(stake * (odds - 1), 2) if result == "win" else (
                    round(-stake, 2) if result == "lose" else 0.0)

            conn.execute(text("""
                UPDATE hit_recommendations
                SET status = :result, profit_loss = :pnl
                WHERE id = :id
            """), {"result": result, "pnl": profit_loss, "id": rec_id})
            settled[result] += 1
            settled_detail.append({
                "sport": sport, "league": league, "home": home, "away": away,
                "market": market, "outcome": outcome, "handicap": hc, "odds": odds,
                "stake": stake, "result": result, "profit_loss": profit_loss,
                "fetch_date": fd, "kickoff_utc": ko,
                "home_score": home_score, "away_score": away_score,
            })

        conn.commit()

    total_settled = settled['win'] + settled['lose'] + settled['push']
    eff_settled   = settled['win'] + settled['lose']  # push 不计入命中率分母
    print(f"\n=== 结算结果 ===")
    print(f"  Win:  {settled['win']}")
    print(f"  Lose: {settled['lose']}")
    print(f"  Push: {settled['push']}")
    print(f"  未匹配: {settled['unmatched']}")
    print(f"  无盘口线(未判): {settled['no_handicap']}")
    if eff_settled:
        wr = settled['win'] / eff_settled * 100
        print(f"  命中率: {wr:.1f}% (有效{eff_settled}场，共{total_settled}场已结算)")

    return settled_detail


def auto_settle_under_shadow(target_date: str = None):
    """结算 under_shadow_bets 影子候选，打印命中率统计"""
    with engine.connect() as conn:
        query = """
            SELECT id, unified_id, sport_code, market, handicap, best_odds, fetch_date,
                   league_name, home_team, away_team, kickoff_utc
            FROM under_shadow_bets
            WHERE status = 'pending'
        """
        params = {}
        if target_date:
            query += " AND fetch_date = :fd"
            params["fd"] = target_date
        shadow_recs = conn.execute(text(query), params).fetchall()

    if not shadow_recs:
        print("[shadow_settle] 无待结算小球候选")
        return []

    uids = list(set(r[1] for r in shadow_recs))
    uid_sport = {r[1]: r[2] for r in shadow_recs}
    uid_scores = {}
    with engine.connect() as conn:
        for i in range(0, len(uids), 500):
            batch = uids[i:i+500]
            placeholders = ','.join([f":u{j}" for j in range(len(batch))])
            params2 = {f"u{j}": uid for j, uid in enumerate(batch)}
            rows = conn.execute(text(f"""
                SELECT unified_id, home_score, away_score, home_score_ht, away_score_ht
                FROM unified_matches
                WHERE unified_id IN ({placeholders}) AND home_score IS NOT NULL
            """), params2).fetchall()
            for uid, hs, aws, hs_ht, as_ht in rows:
                uid_scores[uid] = (hs, aws, hs_ht, as_ht)
        print(f"  第一层(unified_id): 匹配到 {len(uid_scores)} 场比分")

        unmatched_uids = set(uids) - set(uid_scores)
        matched_scores = _layer2_fuzzy_scores(conn, unmatched_uids, uid_sport)
        uid_scores.update(matched_scores)
        print(f"  第二层(队名模糊): 额外匹配 {len(matched_scores)} 场")

        uid_names = {r[1]: (r[6], r[8], r[9]) for r in shadow_recs}  # fd, home, away
        fm_matched = _apply_fotmob_goal_fallback(conn, uid_scores, uid_sport, uid_names)
        print(f"  第三层(fotmob_matches兜底): 额外匹配 {fm_matched} 场")
        qm_matched = _apply_qiumibao_goal_fallback(conn, uid_scores, uid_sport, uid_names)
        print(f"  第四层(qiumibao兜底): 额外匹配 {qm_matched} 场")

    settled = {"win": 0, "lose": 0, "push": 0, "unmatched": 0}
    settled_detail = []
    with engine.begin() as conn:
        for rec_id, uid, sport, market, hc, odds, fd, league, home, away, ko in shadow_recs:
            if uid not in uid_scores:
                settled["unmatched"] += 1
                continue
            hs, aws, hs_ht, as_ht = uid_scores[uid]
            result = _settle_result(market, "under", hc, hs, aws, odds, hs_ht, as_ht)
            if result == "pending":
                settled["unmatched"] += 1
                continue
            profit = (odds - 1) if result == "win" else (-1.0 if result == "lose" else 0.0)
            conn.execute(text("""
                UPDATE under_shadow_bets SET status=:r, profit_loss=:p WHERE id=:id
            """), {"r": result, "p": round(profit, 4), "id": rec_id})
            settled[result] += 1
            settled_detail.append({
                "league": league, "home": home, "away": away, "market": market,
                "outcome": "under", "handicap": hc, "odds": odds, "result": result,
                "profit_loss_u": round(profit, 4), "fetch_date": fd, "kickoff_utc": ko,
                "home_score": hs, "away_score": aws,
            })

    total = settled["win"] + settled["lose"] + settled["push"]
    eff   = settled["win"] + settled["lose"]  # push 不计入命中率分母
    print(f"\n=== 小球影子候选结算 ===")
    print(f"  Win:  {settled['win']}  Lose: {settled['lose']}  Push: {settled['push']}  未匹配: {settled['unmatched']}")
    if eff:
        wr = settled["win"] / eff * 100
        print(f"  命中率: {wr:.1f}% (有效{eff}场，共{total}场已结算)")

    # 累计统计（所有历史）
    with engine.connect() as conn:
        totals = conn.execute(text("""
            SELECT status, COUNT(*), SUM(COALESCE(profit_loss,0))
            FROM under_shadow_bets
            WHERE status IN ('win','lose','push')
            GROUP BY status
        """)).fetchall()
    if totals:
        t_w = next((r[1] for r in totals if r[0]=="win"), 0)
        t_l = next((r[1] for r in totals if r[0]=="lose"), 0)
        t_roi = sum(r[2] for r in totals)
        t_total = t_w + t_l + next((r[1] for r in totals if r[0]=="push"), 0)
        print(f"\n  [累计] {t_total} 场: 命中率={t_w/t_total*100:.1f}%  ROI={t_roi:.2f}u")

    return settled_detail


def auto_settle_over_shadow(target_date: str = None):
    """结算 over_shadow_bets 影子候选，打印命中率统计。2026-08-02新增，跟
    auto_settle_under_shadow结构完全对称，只是方向从"under"换成"over"。"""
    with engine.connect() as conn:
        query = """
            SELECT id, unified_id, sport_code, market, handicap, best_odds, fetch_date,
                   league_name, home_team, away_team, kickoff_utc
            FROM over_shadow_bets
            WHERE status = 'pending'
        """
        params = {}
        if target_date:
            query += " AND fetch_date = :fd"
            params["fd"] = target_date
        shadow_recs = conn.execute(text(query), params).fetchall()

    if not shadow_recs:
        print("[shadow_settle] 无待结算大球候选")
        return []

    uids = list(set(r[1] for r in shadow_recs))
    uid_sport = {r[1]: r[2] for r in shadow_recs}
    uid_scores = {}
    with engine.connect() as conn:
        for i in range(0, len(uids), 500):
            batch = uids[i:i+500]
            placeholders = ','.join([f":u{j}" for j in range(len(batch))])
            params2 = {f"u{j}": uid for j, uid in enumerate(batch)}
            rows = conn.execute(text(f"""
                SELECT unified_id, home_score, away_score, home_score_ht, away_score_ht
                FROM unified_matches
                WHERE unified_id IN ({placeholders}) AND home_score IS NOT NULL
            """), params2).fetchall()
            for uid, hs, aws, hs_ht, as_ht in rows:
                uid_scores[uid] = (hs, aws, hs_ht, as_ht)
        print(f"  第一层(unified_id): 匹配到 {len(uid_scores)} 场比分")

        unmatched_uids = set(uids) - set(uid_scores)
        matched_scores = _layer2_fuzzy_scores(conn, unmatched_uids, uid_sport)
        uid_scores.update(matched_scores)
        print(f"  第二层(队名模糊): 额外匹配 {len(matched_scores)} 场")

        uid_names = {r[1]: (r[6], r[8], r[9]) for r in shadow_recs}  # fd, home, away
        fm_matched = _apply_fotmob_goal_fallback(conn, uid_scores, uid_sport, uid_names)
        print(f"  第三层(fotmob_matches兜底): 额外匹配 {fm_matched} 场")
        qm_matched = _apply_qiumibao_goal_fallback(conn, uid_scores, uid_sport, uid_names)
        print(f"  第四层(qiumibao兜底): 额外匹配 {qm_matched} 场")

    settled = {"win": 0, "lose": 0, "push": 0, "unmatched": 0}
    settled_detail = []
    with engine.begin() as conn:
        for rec_id, uid, sport, market, hc, odds, fd, league, home, away, ko in shadow_recs:
            if uid not in uid_scores:
                settled["unmatched"] += 1
                continue
            hs, aws, hs_ht, as_ht = uid_scores[uid]
            result = _settle_result(market, "over", hc, hs, aws, odds, hs_ht, as_ht)
            if result == "pending":
                settled["unmatched"] += 1
                continue
            profit = (odds - 1) if result == "win" else (-1.0 if result == "lose" else 0.0)
            conn.execute(text("""
                UPDATE over_shadow_bets SET status=:r, profit_loss=:p WHERE id=:id
            """), {"r": result, "p": round(profit, 4), "id": rec_id})
            settled[result] += 1
            settled_detail.append({
                "league": league, "home": home, "away": away, "market": market,
                "outcome": "over", "handicap": hc, "odds": odds, "result": result,
                "profit_loss_u": round(profit, 4), "fetch_date": fd, "kickoff_utc": ko,
                "home_score": hs, "away_score": aws,
            })

    total = settled["win"] + settled["lose"] + settled["push"]
    eff   = settled["win"] + settled["lose"]  # push 不计入命中率分母
    print(f"\n=== 大球影子候选结算 ===")
    print(f"  Win:  {settled['win']}  Lose: {settled['lose']}  Push: {settled['push']}  未匹配: {settled['unmatched']}")
    if eff:
        wr = settled["win"] / eff * 100
        print(f"  命中率: {wr:.1f}% (有效{eff}场，共{total}场已结算)")

    # 累计统计（所有历史）
    with engine.connect() as conn:
        totals = conn.execute(text("""
            SELECT status, COUNT(*), SUM(COALESCE(profit_loss,0))
            FROM over_shadow_bets
            WHERE status IN ('win','lose','push')
            GROUP BY status
        """)).fetchall()
    if totals:
        t_w = next((r[1] for r in totals if r[0]=="win"), 0)
        t_l = next((r[1] for r in totals if r[0]=="lose"), 0)
        t_roi = sum(r[2] for r in totals)
        t_total = t_w + t_l + next((r[1] for r in totals if r[0]=="push"), 0)
        print(f"\n  [累计] {t_total} 场: 命中率={t_w/t_total*100:.1f}%  ROI={t_roi:.2f}u")

    return settled_detail


def settle_team_total_shadow_full(target_date: str = None):
    """结算 team_total_shadow_full 完整候选样本(大球+小球都收，不做每日Top10截断)，
    供 _team_total_validation_status() 的转正判断用真实结算数据。2026-07-22新增，
    见 00_命中系统.py 里 team_total_shadow_full 建表注释说明背景。"""
    with engine.begin() as _init_conn:
        _init_conn.execute(text("""CREATE TABLE IF NOT EXISTS team_total_shadow_full (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT, sport_code TEXT, league_name TEXT,
            home_team TEXT, away_team TEXT, kickoff_utc TEXT,
            market TEXT, outcome TEXT, handicap REAL,
            best_odds REAL, model_prob REAL, kelly_fraction REAL, hit_score REAL,
            status TEXT DEFAULT 'pending', profit_loss REAL, fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(unified_id, market, outcome, handicap, fetch_date)
        )"""))

    with engine.connect() as conn:
        query = """
            SELECT id, unified_id, sport_code, market, outcome, handicap, best_odds, fetch_date,
                   league_name, home_team, away_team, kickoff_utc
            FROM team_total_shadow_full
            WHERE status = 'pending'
        """
        params = {}
        if target_date:
            query += " AND fetch_date = :fd"
            params["fd"] = target_date
        recs = conn.execute(text(query), params).fetchall()

    if not recs:
        print("[team_total_full_settle] 无待结算球队大小完整候选")
        return []

    uids = list(set(r[1] for r in recs))
    uid_sport = {r[1]: r[2] for r in recs}
    uid_scores = {}
    with engine.connect() as conn:
        for i in range(0, len(uids), 500):
            batch = uids[i:i+500]
            placeholders = ','.join([f":u{j}" for j in range(len(batch))])
            params2 = {f"u{j}": uid for j, uid in enumerate(batch)}
            rows = conn.execute(text(f"""
                SELECT unified_id, home_score, away_score, home_score_ht, away_score_ht
                FROM unified_matches
                WHERE unified_id IN ({placeholders}) AND home_score IS NOT NULL
            """), params2).fetchall()
            for uid, hs, aws, hs_ht, as_ht in rows:
                uid_scores[uid] = (hs, aws, hs_ht, as_ht)
        print(f"  第一层(unified_id): 匹配到 {len(uid_scores)} 场比分")

        unmatched_uids = set(uids) - set(uid_scores)
        matched_scores = _layer2_fuzzy_scores(conn, unmatched_uids, uid_sport)
        uid_scores.update(matched_scores)
        print(f"  第二层(队名模糊): 额外匹配 {len(matched_scores)} 场")

        uid_names = {r[1]: (r[7], r[9], r[10]) for r in recs}  # fd, home, away
        fm_matched = _apply_fotmob_goal_fallback(conn, uid_scores, uid_sport, uid_names)
        print(f"  第三层(fotmob_matches兜底): 额外匹配 {fm_matched} 场")
        qm_matched = _apply_qiumibao_goal_fallback(conn, uid_scores, uid_sport, uid_names)
        print(f"  第四层(qiumibao兜底): 额外匹配 {qm_matched} 场")

    settled = {"win": 0, "lose": 0, "push": 0, "unmatched": 0}
    settled_detail = []
    with engine.begin() as conn:
        for rec_id, uid, sport, market, outcome, hc, odds, fd, league, home, away, ko in recs:
            if uid not in uid_scores:
                settled["unmatched"] += 1
                continue
            hs, aws, hs_ht, as_ht = uid_scores[uid]
            result = _settle_result(market, outcome, hc, hs, aws, odds, hs_ht, as_ht)
            if result == "pending":
                settled["unmatched"] += 1
                continue
            profit = (odds - 1) if result == "win" else (-1.0 if result == "lose" else 0.0)
            conn.execute(text("""
                UPDATE team_total_shadow_full SET status=:r, profit_loss=:p WHERE id=:id
            """), {"r": result, "p": round(profit, 4), "id": rec_id})
            settled[result] += 1
            settled_detail.append({
                "league": league, "home": home, "away": away, "market": market,
                "outcome": outcome, "handicap": hc, "odds": odds, "result": result,
                "profit_loss_u": round(profit, 4), "fetch_date": fd, "kickoff_utc": ko,
                "home_score": hs, "away_score": aws,
            })

    total = settled["win"] + settled["lose"] + settled["push"]
    eff   = settled["win"] + settled["lose"]
    print(f"\n=== 球队大小完整候选结算 ===")
    print(f"  Win:  {settled['win']}  Lose: {settled['lose']}  Push: {settled['push']}  未匹配: {settled['unmatched']}")
    if eff:
        wr = settled["win"] / eff * 100
        print(f"  命中率: {wr:.1f}% (有效{eff}场，共{total}场已结算)")

    return settled_detail


def settle_legacy_team_total_under(target_date: str = None):
    """结算足球球队大小/小球"老逻辑"平行线(legacy_team_total_under_recs)，
    2026-08-01新增，用户要求。跟settle_team_total_shadow_full()同一套结算逻辑，
    表结构/UNIQUE约束也一样，见00_命中系统.py里_generate_legacy_team_total_under()
    说明——这条线独立于正式推荐单，只是复用同一套_settle_result()判定+
    unified_matches比分匹配管道。"""
    with engine.begin() as _init_conn:
        _init_conn.execute(text("""CREATE TABLE IF NOT EXISTS legacy_team_total_under_recs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT, sport_code TEXT, league_name TEXT,
            home_team TEXT, away_team TEXT, kickoff_utc TEXT,
            market TEXT, outcome TEXT, handicap REAL,
            best_odds REAL, model_prob REAL, kelly_fraction REAL, hit_score REAL,
            status TEXT DEFAULT 'pending', profit_loss REAL, fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(unified_id, market, outcome, handicap, fetch_date)
        )"""))

    with engine.connect() as conn:
        query = """
            SELECT id, unified_id, sport_code, market, outcome, handicap, best_odds, fetch_date,
                   league_name, home_team, away_team, kickoff_utc
            FROM legacy_team_total_under_recs
            WHERE status = 'pending'
        """
        params = {}
        if target_date:
            query += " AND fetch_date = :fd"
            params["fd"] = target_date
        recs = conn.execute(text(query), params).fetchall()

    if not recs:
        print("[legacy_team_total_under_settle] 无待结算老逻辑候选")
        return []

    uids = list(set(r[1] for r in recs))
    uid_sport = {r[1]: r[2] for r in recs}
    uid_scores = {}
    with engine.connect() as conn:
        for i in range(0, len(uids), 500):
            batch = uids[i:i+500]
            placeholders = ','.join([f":u{j}" for j in range(len(batch))])
            params2 = {f"u{j}": uid for j, uid in enumerate(batch)}
            rows = conn.execute(text(f"""
                SELECT unified_id, home_score, away_score, home_score_ht, away_score_ht
                FROM unified_matches
                WHERE unified_id IN ({placeholders}) AND home_score IS NOT NULL
            """), params2).fetchall()
            for uid, hs, aws, hs_ht, as_ht in rows:
                uid_scores[uid] = (hs, aws, hs_ht, as_ht)
        print(f"  第一层(unified_id): 匹配到 {len(uid_scores)} 场比分")

        unmatched_uids = set(uids) - set(uid_scores)
        matched_scores = _layer2_fuzzy_scores(conn, unmatched_uids, uid_sport)
        uid_scores.update(matched_scores)
        print(f"  第二层(队名模糊): 额外匹配 {len(matched_scores)} 场")

        uid_names = {r[1]: (r[7], r[9], r[10]) for r in recs}  # fd, home, away
        fm_matched = _apply_fotmob_goal_fallback(conn, uid_scores, uid_sport, uid_names)
        print(f"  第三层(fotmob_matches兜底): 额外匹配 {fm_matched} 场")
        qm_matched = _apply_qiumibao_goal_fallback(conn, uid_scores, uid_sport, uid_names)
        print(f"  第四层(qiumibao兜底): 额外匹配 {qm_matched} 场")

    settled = {"win": 0, "lose": 0, "push": 0, "unmatched": 0}
    settled_detail = []
    with engine.begin() as conn:
        for rec_id, uid, sport, market, outcome, hc, odds, fd, league, home, away, ko in recs:
            if uid not in uid_scores:
                settled["unmatched"] += 1
                continue
            hs, aws, hs_ht, as_ht = uid_scores[uid]
            result = _settle_result(market, outcome, hc, hs, aws, odds, hs_ht, as_ht)
            if result == "pending":
                settled["unmatched"] += 1
                continue
            profit = (odds - 1) if result == "win" else (-1.0 if result == "lose" else 0.0)
            conn.execute(text("""
                UPDATE legacy_team_total_under_recs SET status=:r, profit_loss=:p WHERE id=:id
            """), {"r": result, "p": round(profit, 4), "id": rec_id})
            settled[result] += 1
            settled_detail.append({
                "league": league, "home": home, "away": away, "market": market,
                "outcome": outcome, "handicap": hc, "odds": odds, "result": result,
                "profit_loss_u": round(profit, 4), "fetch_date": fd, "kickoff_utc": ko,
                "home_score": hs, "away_score": aws,
            })

    total = settled["win"] + settled["lose"] + settled["push"]
    eff   = settled["win"] + settled["lose"]
    print(f"\n=== 老逻辑平行线(足球球队大小/小球)结算 ===")
    print(f"  Win:  {settled['win']}  Lose: {settled['lose']}  Push: {settled['push']}  未匹配: {settled['unmatched']}")
    if eff:
        wr = settled["win"] / eff * 100
        print(f"  命中率: {wr:.1f}% (有效{eff}场，共{total}场已结算)")

    return settled_detail


def _settle_fade_table(table_name: str, target_date: str, label: str):
    """篮球小球/独赢"反着买"转正平行线共用结算逻辑，2026-08-01新增。表里存的
    已经是翻转后的最终下注方向(不是原始候选)，直接按标准_settle_result()结算，
    不需要额外的fade结算逻辑——见00_命中系统.py里
    basketball_under_fade_recs/basketball_moneyline_fade_recs建表注释说明背景。"""
    with engine.begin() as _init_conn:
        _init_conn.execute(text(f"""CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT, sport_code TEXT, league_name TEXT,
            home_team TEXT, away_team TEXT, kickoff_utc TEXT,
            market TEXT, outcome TEXT, handicap REAL,
            best_odds REAL, model_prob REAL, kelly_fraction REAL, hit_score REAL,
            status TEXT DEFAULT 'pending', profit_loss REAL, fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(unified_id, market, outcome, handicap, fetch_date)
        )"""))

    with engine.connect() as conn:
        query = f"""
            SELECT id, unified_id, sport_code, market, outcome, handicap, best_odds, fetch_date,
                   league_name, home_team, away_team, kickoff_utc
            FROM {table_name}
            WHERE status = 'pending'
        """
        params = {}
        if target_date:
            query += " AND fetch_date = :fd"
            params["fd"] = target_date
        recs = conn.execute(text(query), params).fetchall()

    if not recs:
        print(f"[{table_name}] 无待结算候选")
        return []

    uids = list(set(r[1] for r in recs))
    uid_sport = {r[1]: r[2] for r in recs}
    uid_scores = {}
    with engine.connect() as conn:
        for i in range(0, len(uids), 500):
            batch = uids[i:i+500]
            placeholders = ','.join([f":u{j}" for j in range(len(batch))])
            params2 = {f"u{j}": uid for j, uid in enumerate(batch)}
            rows = conn.execute(text(f"""
                SELECT unified_id, home_score, away_score, home_score_ht, away_score_ht
                FROM unified_matches
                WHERE unified_id IN ({placeholders}) AND home_score IS NOT NULL
            """), params2).fetchall()
            for uid, hs, aws, hs_ht, as_ht in rows:
                uid_scores[uid] = (hs, aws, hs_ht, as_ht)
        print(f"  第一层(unified_id): 匹配到 {len(uid_scores)} 场比分")

        unmatched_uids = set(uids) - set(uid_scores)
        matched_scores = _layer2_fuzzy_scores(conn, unmatched_uids, uid_sport)
        uid_scores.update(matched_scores)
        print(f"  第二层(队名模糊): 额外匹配 {len(matched_scores)} 场")

        uid_names = {r[1]: (r[7], r[9], r[10]) for r in recs}  # fd, home, away
        fm_matched = _apply_fotmob_goal_fallback(conn, uid_scores, uid_sport, uid_names)
        print(f"  第三层(fotmob_matches兜底,仅足球生效): 额外匹配 {fm_matched} 场")
        qm_matched = _apply_qiumibao_goal_fallback(conn, uid_scores, uid_sport, uid_names)
        print(f"  第四层(qiumibao兜底,仅足球生效): 额外匹配 {qm_matched} 场")

    settled = {"win": 0, "lose": 0, "push": 0, "unmatched": 0}
    settled_detail = []
    with engine.begin() as conn:
        for rec_id, uid, sport, market, outcome, hc, odds, fd, league, home, away, ko in recs:
            if uid not in uid_scores:
                settled["unmatched"] += 1
                continue
            hs, aws, hs_ht, as_ht = uid_scores[uid]
            result = _settle_result(market, outcome, hc, hs, aws, odds, hs_ht, as_ht)
            if result == "pending":
                settled["unmatched"] += 1
                continue
            profit = (odds - 1) if result == "win" else (-1.0 if result == "lose" else 0.0)
            conn.execute(text(f"""
                UPDATE {table_name} SET status=:r, profit_loss=:p WHERE id=:id
            """), {"r": result, "p": round(profit, 4), "id": rec_id})
            settled[result] += 1
            settled_detail.append({
                "league": league, "home": home, "away": away, "market": market,
                "outcome": outcome, "handicap": hc, "odds": odds, "result": result,
                "profit_loss_u": round(profit, 4), "fetch_date": fd, "kickoff_utc": ko,
                "home_score": hs, "away_score": aws,
            })

    total = settled["win"] + settled["lose"] + settled["push"]
    eff   = settled["win"] + settled["lose"]
    print(f"\n=== {label}结算 ===")
    print(f"  Win:  {settled['win']}  Lose: {settled['lose']}  Push: {settled['push']}  未匹配: {settled['unmatched']}")
    if eff:
        wr = settled["win"] / eff * 100
        print(f"  命中率: {wr:.1f}% (有效{eff}场，共{total}场已结算)")

    return settled_detail


def settle_basketball_under_fade(target_date: str = None):
    return _settle_fade_table("basketball_under_fade_recs", target_date, "篮球小球反着买平行线")


def settle_basketball_moneyline_fade(target_date: str = None):
    return _settle_fade_table("basketball_moneyline_fade_recs", target_date, "篮球独赢反着买平行线")


def settle_moneyline_shadow_full(target_date: str = None):
    """结算 moneyline_shadow_full 完整候选样本(全部outcome，不做每日Top10截断)，
    供 _moneyline_validation_status() 按(sport_code,outcome)分开做转正判断用真实
    结算数据。2026-07-24新增，跟team_total_shadow_full同一套动机——原来的
    shadow_recommendations里moneyline桶按每日Top10截断，是有偏样本，见
    00_命中系统.py 里 moneyline_shadow_full 建表注释说明背景。"""
    with engine.begin() as _init_conn:
        _init_conn.execute(text("""CREATE TABLE IF NOT EXISTS moneyline_shadow_full (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT, sport_code TEXT, league_name TEXT,
            home_team TEXT, away_team TEXT, kickoff_utc TEXT,
            market TEXT, outcome TEXT,
            best_odds REAL, model_prob REAL, kelly_fraction REAL, hit_score REAL,
            status TEXT DEFAULT 'pending', profit_loss REAL, fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(unified_id, market, outcome, fetch_date)
        )"""))

    with engine.connect() as conn:
        query = """
            SELECT id, unified_id, sport_code, market, outcome, best_odds, fetch_date,
                   league_name, home_team, away_team, kickoff_utc
            FROM moneyline_shadow_full
            WHERE status = 'pending'
        """
        params = {}
        if target_date:
            query += " AND fetch_date = :fd"
            params["fd"] = target_date
        recs = conn.execute(text(query), params).fetchall()

    if not recs:
        print("[moneyline_full_settle] 无待结算独赢完整候选")
        return []

    uids = list(set(r[1] for r in recs))
    uid_sport = {r[1]: r[2] for r in recs}
    uid_scores = {}
    with engine.connect() as conn:
        for i in range(0, len(uids), 500):
            batch = uids[i:i+500]
            placeholders = ','.join([f":u{j}" for j in range(len(batch))])
            params2 = {f"u{j}": uid for j, uid in enumerate(batch)}
            rows = conn.execute(text(f"""
                SELECT unified_id, home_score, away_score, home_score_ht, away_score_ht
                FROM unified_matches
                WHERE unified_id IN ({placeholders}) AND home_score IS NOT NULL
            """), params2).fetchall()
            for uid, hs, aws, hs_ht, as_ht in rows:
                uid_scores[uid] = (hs, aws, hs_ht, as_ht)
        print(f"  第一层(unified_id): 匹配到 {len(uid_scores)} 场比分")

        unmatched_uids = set(uids) - set(uid_scores)
        matched_scores = _layer2_fuzzy_scores(conn, unmatched_uids, uid_sport)
        uid_scores.update(matched_scores)
        print(f"  第二层(队名模糊): 额外匹配 {len(matched_scores)} 场")

        uid_names = {r[1]: (r[6], r[8], r[9]) for r in recs}  # fd, home, away
        fm_matched = _apply_fotmob_goal_fallback(conn, uid_scores, uid_sport, uid_names)
        print(f"  第三层(fotmob_matches兜底): 额外匹配 {fm_matched} 场")
        qm_matched = _apply_qiumibao_goal_fallback(conn, uid_scores, uid_sport, uid_names)
        print(f"  第四层(qiumibao兜底): 额外匹配 {qm_matched} 场")

    settled = {"win": 0, "lose": 0, "push": 0, "unmatched": 0}
    settled_detail = []
    with engine.begin() as conn:
        for rec_id, uid, sport, market, outcome, odds, fd, league, home, away, ko in recs:
            if uid not in uid_scores:
                settled["unmatched"] += 1
                continue
            hs, aws, hs_ht, as_ht = uid_scores[uid]
            result = _settle_result(market, outcome, None, hs, aws, odds, hs_ht, as_ht)
            if result == "pending":
                settled["unmatched"] += 1
                continue
            profit = (odds - 1) if result == "win" else (-1.0 if result == "lose" else 0.0)
            conn.execute(text("""
                UPDATE moneyline_shadow_full SET status=:r, profit_loss=:p WHERE id=:id
            """), {"r": result, "p": round(profit, 4), "id": rec_id})
            settled[result] += 1
            settled_detail.append({
                "league": league, "home": home, "away": away, "market": market,
                "outcome": outcome, "handicap": None, "odds": odds, "result": result,
                "profit_loss_u": round(profit, 4), "fetch_date": fd, "kickoff_utc": ko,
                "home_score": hs, "away_score": aws,
            })

    total = settled["win"] + settled["lose"] + settled["push"]
    eff   = settled["win"] + settled["lose"]
    print(f"\n=== 独赢完整候选结算 ===")
    print(f"  Win:  {settled['win']}  Lose: {settled['lose']}  Push: {settled['push']}  未匹配: {settled['unmatched']}")
    if eff:
        wr = settled["win"] / eff * 100
        print(f"  命中率: {wr:.1f}% (有效{eff}场，共{total}场已结算)")

    return settled_detail


def settle_shadow_recommendations(target_date: str = None):
    """结算 shadow_recommendations 影子候选（独赢/让分/胜平负），打印命中率统计"""
    # 建表保护：单独运行时 DB 可能还没有此表
    with engine.begin() as _init_conn:
        _init_conn.execute(text("""CREATE TABLE IF NOT EXISTS shadow_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT, sport_code TEXT, league_name TEXT,
            home_team TEXT, away_team TEXT, kickoff_utc TEXT,
            shadow_type TEXT, market TEXT, outcome TEXT, handicap REAL,
            best_odds REAL, model_prob REAL, kelly_fraction REAL,
            hit_score REAL, predicted_score TEXT, fetch_date TEXT,
            status TEXT DEFAULT 'pending', profit_loss REAL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(unified_id, shadow_type, market, outcome, fetch_date)
        )"""))
    with engine.connect() as conn:
        query = """
            SELECT id, unified_id, sport_code, market, outcome, handicap, best_odds, shadow_type, fetch_date,
                   league_name, home_team, away_team, kickoff_utc
            FROM shadow_recommendations
            WHERE status = 'pending'
        """
        params = {}
        if target_date:
            query += " AND fetch_date = :fd"
            params["fd"] = target_date
        shadow_recs = conn.execute(text(query), params).fetchall()

    if not shadow_recs:
        print("[shadow_multi_settle] 无待结算影子候选")
        return []

    uids = list(set(r[1] for r in shadow_recs))
    uid_sport = {r[1]: r[2] for r in shadow_recs}
    uid_scores = {}
    with engine.connect() as conn:
        for i in range(0, len(uids), 500):
            batch = uids[i:i+500]
            placeholders = ','.join([f":u{j}" for j in range(len(batch))])
            params2 = {f"u{j}": uid for j, uid in enumerate(batch)}
            rows = conn.execute(text(f"""
                SELECT unified_id, home_score, away_score, home_score_ht, away_score_ht
                FROM unified_matches
                WHERE unified_id IN ({placeholders}) AND home_score IS NOT NULL
            """), params2).fetchall()
            for uid, hs, aws, hs_ht, as_ht in rows:
                uid_scores[uid] = (hs, aws, hs_ht, as_ht)
        print(f"  第一层(unified_id): 匹配到 {len(uid_scores)} 场比分")

        unmatched_uids = set(uids) - set(uid_scores)
        matched_scores = _layer2_fuzzy_scores(conn, unmatched_uids, uid_sport)
        uid_scores.update(matched_scores)
        print(f"  第二层(队名模糊): 额外匹配 {len(matched_scores)} 场")

        # ── 第三层：fotmob_matches 兜底(2026-08-25新增) ──────────────────────
        # Bug修复：第一层(unified_matches)/第二层(match_results模糊匹配)对
        # fotmob_totals/fotmob_team_total这两个影子桶的结算长期存在覆盖缺口——
        # 沙特超级联赛(Saudi Arabia - Pro League)在match_results里历史零覆盖，
        # 导致这类候选永久卡在status='pending'，从未计入胜率/ROI统计，跟
        # 角球结算(settle_fotmob_corner_shadow)2026-07-26就修过的同一类问题。
        # 只在这个通用影子桶结算函数上补(其余专用结算函数沿用原有两层，
        # 不扩大改动范围)。
        still_unmatched = set(uids) - set(uid_scores)
        if still_unmatched:
            uid_info = {}
            for r in shadow_recs:
                uid_i = r[1]
                if uid_i in still_unmatched and uid_i not in uid_info:
                    uid_info[uid_i] = (r[8], r[10], r[11])  # fd, home, away
            _fm_goal_buckets = _bucket_by_date(_get_fotmob_goal_scores(conn))
            fm_matched = 0
            for uid_i in list(still_unmatched):
                fd_i, home_i, away_i = uid_info.get(uid_i, (None, None, None))
                if home_i is None:
                    continue
                score = _match_fotmob_goal_score(home_i, away_i, fd_i, _fm_goal_buckets)
                if score is not None:
                    uid_scores[uid_i] = score
                    fm_matched += 1
            print(f"  第三层(fotmob_matches兜底): 额外匹配 {fm_matched} 场")

            # ── 第四层：qiumibao_match_results 兜底(2026-09-04新增) ──────────
            still_unmatched2 = set(uids) - set(uid_scores)
            _qm_goal_buckets = _bucket_by_date(_get_qiumibao_goal_scores(conn))
            qm_matched = 0
            for uid_i in list(still_unmatched2):
                fd_i, home_i, away_i = uid_info.get(uid_i, (None, None, None))
                if home_i is None:
                    continue
                score = _match_fotmob_goal_score(home_i, away_i, fd_i, _qm_goal_buckets)
                if score is not None:
                    uid_scores[uid_i] = score
                    qm_matched += 1
            print(f"  第四层(qiumibao兜底): 额外匹配 {qm_matched} 场")

    settled = {"win": 0, "lose": 0, "push": 0, "unmatched": 0}
    settled_detail = []
    by_type: dict = {}
    with engine.begin() as conn:
        for rec_id, uid, sport, market, outcome, hc, odds, stype, fd, league, home, away, ko in shadow_recs:
            if uid not in uid_scores:
                settled["unmatched"] += 1
                continue
            hs, aws, hs_ht, as_ht = uid_scores[uid]
            result = _settle_result(market, outcome, hc, hs, aws, odds, hs_ht, as_ht)
            if result == "pending":
                settled["unmatched"] += 1
                continue
            profit = (odds - 1) if result == "win" else (-1.0 if result == "lose" else 0.0)
            conn.execute(text("""
                UPDATE shadow_recommendations SET status=:r, profit_loss=:p WHERE id=:id
            """), {"r": result, "p": round(profit, 4), "id": rec_id})
            settled[result] += 1
            key = stype or market
            if key not in by_type:
                by_type[key] = {"win": 0, "lose": 0, "push": 0}
            by_type[key][result] = by_type[key].get(result, 0) + 1
            settled_detail.append({
                "shadow_type": stype, "league": league, "home": home, "away": away,
                "market": market, "outcome": outcome, "handicap": hc, "odds": odds,
                "result": result, "profit_loss_u": round(profit, 4),
                "fetch_date": fd, "kickoff_utc": ko,
                "home_score": hs, "away_score": aws,
            })

    total = settled["win"] + settled["lose"] + settled["push"]
    eff_total = settled["win"] + settled["lose"]
    print(f"\n=== 其他市场影子候选结算 ===")
    print(f"  Win:  {settled['win']}  Lose: {settled['lose']}  Push: {settled['push']}  未匹配: {settled['unmatched']}")
    if eff_total:
        wr = settled["win"] / eff_total * 100
        print(f"  命中率: {wr:.1f}% (有效{eff_total}场，共{total}场已结算)")
    for stype, counts in by_type.items():
        eff = counts.get("win", 0) + counts.get("lose", 0)  # push 不计入分母
        if eff:
            print(f"  [{stype}] 命中率: {counts.get('win',0)/eff*100:.1f}% (有效{eff}场)")

    return settled_detail


# ─── 角球推荐结算 ───────────────────────────────────────────────────────────
_CORNER_FINISHED_STATUS = {"FT", "ET", "4", "5", "AET", "PEN"}
_CORNER_KICKOFF_BUFFER_MIN = 130  # 开球后超过这个时长，才认为比赛大概率已结束

# 500.com 解析器目前 match_status 恒为 "live"、match_minute 恒为 None（未解析），
# 完全无法判断比赛是否结束，因此不能单纯依赖状态字段——改用"开球时间 + 缓冲时长"
# 兜底：一旦确认早该结束，取该场已抓到的最大角球数（角球单调递增，取最大值最接近终值）


def _bucket_by_date(rows, date_idx=2):
    """按行里date_idx位置的日期字符串分桶——2026-09-05性能审查发现的修复：
    第三层(fotmob)/第四层(qiumibao)兜底原来对每个候选都要把整张参考表(fotmob_matches
    14765行/qiumibao_match_results近万行)线性扫一遍才判断日期是否在窗口内，实测
    1422个候选×14765行要跑7分钟以上——同一个文件里第二层_layer2_fuzzy_scores()
    早就用了"先按日期分桶，候选只查自己窗口"这个正确做法，第三/四层当初复制的时候
    没照抄这部分，现在补上，跟第二层保持一致的设计。"""
    buckets = defaultdict(list)
    for row in rows:
        d = row[date_idx]
        if d:
            buckets[d].append(row)
    return buckets


def _lookup_date_window(buckets, fd, days=(0, -1, 1)):
    """从_bucket_by_date()结果按fd为中心取±1天窗口内的候选行(跟原来"d_gap<=1"
    语义一致)，只有fd缺失/格式非法时才退化成扫全部桶(保留原函数对这类边界情况
    的兜底行为，不改变语义，只优化"有正常日期"这个绝大多数场景的性能)。"""
    if fd:
        try:
            base = datetime.strptime(fd, "%Y-%m-%d")
            result = []
            for delta in days:
                key = (base + timedelta(days=delta)).strftime("%Y-%m-%d")
                result.extend(buckets.get(key, []))
            return result
        except ValueError:
            pass
    result = []
    for v in buckets.values():
        result.extend(v)
    return result


def _get_fotmob_corner_totals(conn):
    """从fotmob_matches+fotmob_match_team_stats取每场比赛的终场角球总数(home+away
    corners之和)。这是43_fotmob_match_data_scraper.py按match_id持久化抓取的数据，
    不像corner_stats_final/corner_live_odds那样只有"抓取时刻"的时效窗口——只要
    match_id对应的联赛在43号的LEAGUES配置里，比赛结束后任何时候都能查到，2026-07-26
    验证过(Degerfors vs Djurgarden、Sligo Rovers vs Drogheda United等此前判"未匹配"
    的比赛，实际FotMob早就抓到了角球数，只是没接入结算)。match_date原始格式是
    "Sat, Jul 25, 2026, 13:00 UTC"，需要解析成ISO日期才能跟fetch_date做日期窗口比对。
    返回 [(home_team, away_team, match_date_iso, total_corners), ...]。
    """
    try:
        rows = conn.execute(text("""
            SELECT fm.home_team, fm.away_team, fm.match_date, SUM(fts.corners) as total_corners,
                   COUNT(fts.corners) as n
            FROM fotmob_matches fm
            JOIN fotmob_match_team_stats fts ON fm.match_id = fts.match_id
            WHERE fts.corners IS NOT NULL
            GROUP BY fm.match_id
            HAVING n = 2
        """)).fetchall()
    except Exception:
        return []

    result = []
    for home, away, match_date_raw, total_corners, _n in rows:
        try:
            dt = datetime.strptime(match_date_raw, "%a, %b %d, %Y, %H:%M UTC")
            match_date_iso = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        result.append((home, away, match_date_iso, total_corners))
    return result


def _match_corner_from_fotmob(home, away, fd, buckets):
    """用队名模糊匹配，从_bucket_by_date(_get_fotmob_corner_totals())结果的
    ±1天窗口里找终场角球总数(不再线性扫全表，见_lookup_date_window)。"""
    for lh, la, match_date, total_c in _lookup_date_window(buckets, fd):
        if _fuzzy_match(home, away, lh, la):
            return total_c
    return None


def _get_fotmob_goal_scores(conn):
    """Bug修复(2026-08-25)：fotmob_totals/fotmob_team_total影子桶结算一直只查
    unified_matches(第一层)+match_results模糊匹配(第二层)，从没接入fotmob_matches——
    跟角球结算(_get_fotmob_corner_totals，2026-07-26修复同一类问题)完全一样的
    结构性缺口。实测沙特超级联赛(Saudi Arabia - Pro League)在match_results里
    历史至今零覆盖，但fotmob_matches有完整比分(43号爬虫抓的)，导致这批候选
    永久卡在pending，从未进入胜率/ROI统计——不是"数据不存在"，是结算没去查
    已经有的数据源。返回[(home_team, away_team, match_date_iso, home_score,
    away_score, home_score_ht, away_score_ht), ...]（不在这里预算zh译名——
    14765行里绝大多数从来不会被任何候选的±1天窗口触达，一次性全量翻译等于
    白白多付出一次O(全表)代价；改成在_match_fotmob_goal_score()里按需惰性
    翻译，靠模块级_team_zh()缓存(见文件头说明)让"同一队名被多个候选反复
    命中"这个真实场景变成只有第一次是冷启动，见2026-09-05性能修复说明）。"""
    try:
        rows = conn.execute(text("""
            SELECT home_team, away_team, match_date, home_score, away_score,
                   home_score_ht, away_score_ht
            FROM fotmob_matches
            WHERE home_score IS NOT NULL AND away_score IS NOT NULL
        """)).fetchall()
    except Exception:
        return []

    result = []
    for home, away, match_date_raw, hs, aws, hs_ht, as_ht in rows:
        try:
            dt = datetime.strptime(match_date_raw, "%a, %b %d, %Y, %H:%M UTC")
            match_date_iso = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
        result.append((home, away, match_date_iso, hs, aws, hs_ht, as_ht))
    return result


# qiumibao源队名专用译名补表(2026-09-09新增)：qiumibao_match_results存中文队名，
# 且译名习惯跟team_zh.py不一致或缺失(B队/II/U21后缀、奈梅亨/SBV精英/吉达联合等)。
# key用_normalize()后的小写英文(无空格标点)，value用qiumibao实际存储的中文名。
# 只用于结算第3/4层兜底的_rec_team_zh()，不参与全局展示译名，避免污染team_zh。
_QIUMIBAO_ZH_ALIAS = {
    "atlantaunitedii": "亚特兰大联II",
    "atlantaunited2": "亚特兰大联II",
    "necnijmegen": "奈梅亨",
    "excelsior": "SBV精英",
    "alittihad": "吉达联合",
    "alfayha": "费哈",
    "cowdenbeath": "考登比亚",
    "macclesfield": "麦克尔斯菲尔德",
    "scarboroughathletic": "史卡保罗夫",
    "connecticutunited": "康涅狄格州联合FC",
    "columbuscrewii": "哥伦布机员B队",
    "columbuscrew2": "哥伦布机员B队",
    "newyorkcityii": "纽约城B队",
    "newyorkcity2": "纽约城B队",
    "torontofcii": "多伦多FC B队",
    "torontofc2": "多伦多FC B队",
    "scunthorpeunited": "斯坎索普",
    "gateshead": "盖茨黑德",
    "wellingboroughtown": "威灵伯勒",
    "ketteringtown": "凯特林",
    "berwickrangers": "伯威克",
    "stirlingalbion": "斯特灵",
    "forfarathletic": "福法尔",
    "banksodee": "班克斯奥迪",
    "hibernian": "希伯尼安",
    "rangers": "流浪者",
    "internacionaldepalmira": "国际帕尔米拉",
    "internacionaldebogota": "波哥大国际",
    "internacionalbogota": "波哥大国际",
}


def _rec_team_zh(name: str) -> str:
    """推荐方队名→中文：先按_normalize后的小写key查qiumibao专用别名表，
    命中直接返回(别名表已用qiumibao实际中文名，避免team_zh译名不一致)；
    未命中退回_team_zh()(英文→中文全局字典，带模块级缓存)。2026-09-09新增，
    供_match_fotmob_goal_score()第三个匹配分支使用。"""
    if not name:
        return name
    key = _normalize(name)
    if key in _QIUMIBAO_ZH_ALIAS:
        return _QIUMIBAO_ZH_ALIAS[key]
    return _team_zh(name)


def _match_fotmob_goal_score(home, away, fd, buckets):
    """队名模糊匹配，从_bucket_by_date(_get_fotmob_goal_scores())结果的±1天
    窗口里找终场比分(不再线性扫全表，见_lookup_date_window)。先按原名匹配
    (覆盖英文联赛，如沙特联赛)，原名不中时再把源那一侧的英文队名转中文重试
    (覆盖00_命中系统.py用中文队名展示的联赛，如日职联"东京FC"，fotmob_matches
    存的是英文"FC Tokyo"，两者字符集不同，_fuzzy_match的SequenceMatcher桥不
    过去，必须先转译成同一种语言再比)——惰性翻译+模块级_team_zh()缓存(见
    文件头)，只有真正落进候选±1天窗口的行才会触发翻译，且同一队名跨候选
    只需要翻译一次，不会重复付出team_zh()找不到精确匹配时的O(字典大小)
    退化成本(2026-09-05性能修复：早期版本尝试过"取数据时一次性全量翻译"，
    实测因为14765行里绝大多数根本落不进任何候选的日期窗口，白白翻译了永远
    用不到的行，反而更慢，已放弃改回这个惰性方案)。

    Bug修复(2026-09-09)：qiumibao_match_results(第四层兜底源)存的是中文队名，
    且译名习惯跟team_zh.py不一致/缺失(多伦多FC B队/纽约城B队/奈梅亨/SBV精英/
    吉达联合等) —— 原逻辑只试了"把**存储名**翻成中文再跟推荐名比"(第二分支)，
    方向反了：推荐名是英文、存储名已是中文时，两个分支都跨不过字符集。补第三
    个分支：把**推荐名**经_rec_team_zh()(qiumibao专用别名表→team_zh兜底)翻成
    中文，再对存储名(中文)匹配；B队/II/U21这类后缀差异由_fuzzy_match的normalize
    子串/相似度容忍("多伦多fc"⊂"多伦多fcb队")。只加分支不改既有行为，fotmob源
    (存储英文名)下第三个分支翻成中文后对英文存储名不会误命中。"""
    h_zh = _rec_team_zh(home)
    a_zh = _rec_team_zh(away)
    for lh, la, match_date, hs, aws, hs_ht, as_ht in _lookup_date_window(buckets, fd):
        if _fuzzy_match(home, away, lh, la):
            return (hs, aws, hs_ht, as_ht)
        if _fuzzy_match(home, away, _team_zh(lh), _team_zh(la)):
            return (hs, aws, hs_ht, as_ht)
        if h_zh and a_zh and _fuzzy_match(h_zh, a_zh, lh, la):
            return (hs, aws, hs_ht, as_ht)
    return None


def _apply_fotmob_goal_fallback(conn, uid_scores: dict, uid_sport: dict, uid_names: dict) -> int:
    """Bug修复(2026-08-25)：第三层通用兜底，供本文件所有"两层结算"(unified_id直连+
    match_results模糊匹配)的函数在第二层之后统一调用，补上fotmob_matches这个已经
    在库里、但之前从没被结算查过的数据源(见_get_fotmob_goal_scores docstring)。
    只对足球(sport_code含football/soccer)生效——fotmob_matches存的是进球比分，
    篮球候选传进来也不会命中，但显式过滤更清楚、避免以后误用。

    uid_scores: 已匹配的{unified_id: (hs,aws,hs_ht,as_ht)}，原地补写。
    uid_sport : {unified_id: sport_code}。
    uid_names : {unified_id: (fetch_date, home_team, away_team)}，用于反查FotMob比分。
    返回本次新增匹配场数。"""
    still_unmatched = [u for u in uid_sport if u not in uid_scores]
    football_unmatched = [u for u in still_unmatched
                           if (uid_sport.get(u) or "").lower() in ("football", "soccer")]
    if not football_unmatched:
        return 0
    fm_rows = _get_fotmob_goal_scores(conn)
    if not fm_rows:
        return 0
    buckets = _bucket_by_date(fm_rows)  # 分桶一次，供下面循环里每个候选做O(1)窗口查找
    matched = 0
    for u in football_unmatched:
        info = uid_names.get(u)
        if not info:
            continue
        fd_i, home_i, away_i = info
        if not home_i or not away_i:
            continue
        score = _match_fotmob_goal_score(home_i, away_i, fd_i, buckets)
        if score is not None:
            uid_scores[u] = score
            matched += 1
    return matched


def _get_qiumibao_goal_scores(conn):
    """第四层兜底数据源(2026-09-04新增)：48_qiumibao_corner_scraper.py抓的
    qiumibao_match_results，跟_get_fotmob_goal_scores()同一个思路——fotmob_matches
    覆盖不到的比赛(联赛不在43号爬虫配置里、或FotMob本身没收录的偏门联赛/杯赛)，
    qiumibao有更广的低级别联赛覆盖面，2026-09-04用它实测补全过白俄超/乌拉圭杯/
    智利乙级等此前fotmob_matches和match_results两层都查不到的场次(见settle_20260903
    复盘)。qiumibao队名是中文，返回值跟fotmob版本保持同样的字段顺序，方便
    _apply_qiumibao_goal_fallback复用_match_fotmob_goal_score同一套匹配逻辑
    (该函数内部本来就会额外尝试_team_zh()翻译后再比一次，所以中文源直接复用不用
    另写一个匹配函数)。只取status_code='8'(完场)的行——爬虫本身已经在写库前过滤过，
    这里的WHERE只是双重保险。"""
    try:
        rows = conn.execute(text("""
            SELECT home_team, away_team, kickoff_utc, home_score, away_score,
                   home_score_ht, away_score_ht
            FROM qiumibao_match_results
            WHERE status_code='8' AND home_score IS NOT NULL AND away_score IS NOT NULL
        """)).fetchall()
    except Exception:
        return []

    result = []
    for home, away, kickoff_raw, hs, aws, hs_ht, as_ht in rows:
        try:
            match_date_iso = kickoff_raw[:10]
        except (TypeError, IndexError):
            continue
        result.append((home, away, match_date_iso, hs, aws, hs_ht, as_ht))
    return result


def _apply_qiumibao_goal_fallback(conn, uid_scores: dict, uid_sport: dict, uid_names: dict) -> int:
    """第四层通用兜底(2026-09-04新增)，跟_apply_fotmob_goal_fallback同一套结构，
    在第三层(fotmob)之后再补一次——qiumibao源是中文队名，_match_fotmob_goal_score
    内部已经会尝试把源队名转成中文再匹配一次，直接复用无需另写函数。同样只对
    足球生效(qiumibao_match_results的角球/半场字段目前只在足球行填充)。"""
    still_unmatched = [u for u in uid_sport if u not in uid_scores]
    football_unmatched = [u for u in still_unmatched
                           if (uid_sport.get(u) or "").lower() in ("football", "soccer")]
    if not football_unmatched:
        return 0
    qm_rows = _get_qiumibao_goal_scores(conn)
    if not qm_rows:
        return 0
    buckets = _bucket_by_date(qm_rows)
    matched = 0
    for u in football_unmatched:
        info = uid_names.get(u)
        if not info:
            continue
        fd_i, home_i, away_i = info
        if not home_i or not away_i:
            continue
        score = _match_fotmob_goal_score(home_i, away_i, fd_i, buckets)
        if score is not None:
            uid_scores[u] = score
            matched += 1
    return matched


def _get_qiumibao_corner_totals(conn):
    """角球版第四层兜底(2026-09-04新增)——跟_get_fotmob_corner_totals()同思路。
    **置信度提醒**：qiumibao_match_results.home_corners/away_corners是从JS bundle
    反推出的疑似字段位置，未找到官方文档/显式赋值代码100%确认(见
    48_qiumibao_corner_scraper.py文件头说明)，只是数值量级(个位数到十几)符合角球
    合理范围。角球正式推荐单(corner_recommendations)涉及真钱，这层兜底排在
    fotmob角球兜底之后最末位——fotmob角球数据(43号爬虫直接按官方match_id抓取)
    置信度更高，优先级应该在前面，qiumibao只在前两层都查不到时才用。"""
    try:
        rows = conn.execute(text("""
            SELECT home_team, away_team, kickoff_utc, home_corners, away_corners
            FROM qiumibao_match_results
            WHERE status_code='8' AND home_corners IS NOT NULL AND away_corners IS NOT NULL
        """)).fetchall()
    except Exception:
        return []

    result = []
    for home, away, kickoff_raw, hc, ac in rows:
        try:
            match_date_iso = kickoff_raw[:10]
        except (TypeError, IndexError):
            continue
        result.append((home, away, match_date_iso, (hc or 0) + (ac or 0)))
    return result


def _match_corner_from_qiumibao(home, away, fd, buckets):
    """跟_match_corner_from_fotmob()同一套匹配逻辑(±1天窗口查找，不再线性
    扫全表)，qiumibao是中文队名，额外尝试_team_zh()翻译后再比一次(源队名
    多为英文/qiety混合命名)。译名在循环外只算一次(2026-09-05性能修复：原来
    写在循环内部，同一个候选对窗口里每一行都要重新调用一次_team_zh()，
    而home/away在整次调用里其实是同一个值，没必要重复算)。"""
    zh_home, zh_away = _team_zh(home), _team_zh(away)
    for lh, la, match_date, total_c in _lookup_date_window(buckets, fd):
        if _fuzzy_match(home, away, lh, la):
            return total_c
        if _fuzzy_match(zh_home, zh_away, lh, la):
            return total_c
    return None


def _corner_is_finished(status, minute, kickoff_utc: str | None) -> bool:
    if status in _CORNER_FINISHED_STATUS:
        return True
    if minute is not None:
        try:
            if float(minute) >= 90:
                return True
        except (TypeError, ValueError):
            pass
    if kickoff_utc:
        try:
            ko = datetime.strptime(kickoff_utc[:19].replace("T", " "), "%Y-%m-%d %H:%M:%S")
            if datetime.utcnow() - ko >= timedelta(minutes=_CORNER_KICKOFF_BUFFER_MIN):
                return True
        except ValueError:
            pass
    return False


def settle_corner_recommendations(target_date: str = None):
    """结算 corner_recommendations（角球大小球），用模糊队名匹配 + 日期窗口对照角球终值数据。

    数据源优先级：
      1. corner_stats_final（37_corner_stats_scraper.py 抓的 corner-stats.com 终值，
         明确区分"已结束/未结束"，可信度最高）
      2. corner_live_odds（33_corner_odds_scraper.py 的实时快照兜底，scoremer 目前被
         403 封锁、500.com 的 match_status 恒为 "live" 无法判断比赛是否结束，
         只能靠"开球时间是否已过缓冲时长"来猜测，取抓到过的历史最大角球数当终值）

    局限：两个源都依赖"抓取时比赛还在源站的可见范围内"，已经过去很久、从未被
    任一源抓到过的老比赛会一直停留在 pending，计入"未匹配"，无法追溯。
    """
    with engine.begin() as conn:
        conn.execute(text("""CREATE TABLE IF NOT EXISTS corner_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_date TEXT, league_name TEXT, home_team TEXT, away_team TEXT,
            kickoff_utc TEXT, market TEXT DEFAULT 'corner_total', direction TEXT,
            line REAL, odds REAL, p_model REAL, p_fusion REAL, edge REAL, kelly REAL,
            hit_score REAL, mu_predicted REAL, src TEXT, status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(fetch_date, league_name, home_team, away_team, direction, line)
        )"""))
        try:
            conn.execute(text("ALTER TABLE corner_recommendations ADD COLUMN profit_loss REAL"))
        except Exception:
            pass

    with engine.connect() as conn:
        query = """
            SELECT id, home_team, away_team, direction, line, odds, fetch_date, kickoff_utc, league_name
            FROM corner_recommendations WHERE status = 'pending'
        """
        params = {}
        if target_date:
            query += " AND fetch_date = :fd"
            params["fd"] = target_date
        recs = conn.execute(text(query), params).fetchall()

    if not recs:
        print("[corner_settle] 无待结算角球推荐")
        return []

    with engine.connect() as conn:
        fotmob_rows = _bucket_by_date(_get_fotmob_corner_totals(conn))
        qiumibao_corner_rows = _bucket_by_date(_get_qiumibao_corner_totals(conn))
        try:
            final_rows = conn.execute(text("""
                SELECT home_team, away_team, total_corners, match_date
                FROM corner_stats_final
            """)).fetchall()
        except Exception:
            final_rows = []  # 表可能还没建（37_corner_stats_scraper.py 未跑过）
        live_rows = conn.execute(text("""
            SELECT home_team, away_team, match_status, match_minute, total_corners,
                   fetched_at, fetch_date
            FROM corner_live_odds
            -- Bug修复(2026-08-11)：不能只判 IS NOT NULL，0 会漏过去。500.com 对
            -- 没有技术统计的比赛照样把角球进度条渲染成 "0 角球 0"，跟真实的0在
            -- HTML上无法区分，历史上写进了730条这种假0(占该来源83%)。足球全场零
            -- 角球实际不存在，而下面取的是同场次快照的最大值——若某场只有假0快照，
            -- 终值就会被算成0，该场所有"小球"盘会被无条件判赢。33号爬虫已在写入端
            -- 拦截，这里再防一层，同时中和历史遗留的假0数据。
            WHERE total_corners IS NOT NULL AND total_corners > 0
            -- Bug修复(2026-08-11)：排除 scoremer 来源。33号解析器里 heh/haa/rcn
            -- 三个字段的含义是注释自认的"文档推断"，从未验证，实测全错：
            --   * status 其实是比赛分钟数(1-121)，不是状态码，原 status_map 映射错误
            --   * 1691行里 701 行是 NS(比赛根本没开踢)却存着角球数
            --   * heh+haa != rcn 占 1679/1691 = 99.3%，rcn 不是两队角球之和
            --   * 571 行 total_corners > 30(最高937)，单场不可能
            -- 无法区分哪些值碰巧是对的，且该源已被403封锁不再更新，整体排除。
            AND source <> 'scoremer'
        """)).fetchall()

    source_hits = {"fotmob_persistent": 0, "corner_stats_final": 0, "corner_live_odds": 0, "qiumibao": 0}
    settled = {"win": 0, "lose": 0, "push": 0, "unmatched": 0}
    settled_detail = []
    with engine.begin() as conn:
        for rec_id, home, away, direction, line, odds, fd, kickoff_utc, league in recs:
            if not _corner_is_finished(None, None, kickoff_utc):
                settled["unmatched"] += 1
                continue

            best_total = None

            # 最优先源：fotmob_matches/fotmob_match_team_stats（持久化，无时效窗口）
            best_total = _match_corner_from_fotmob(home, away, fd, fotmob_rows)
            if best_total is not None:
                source_hits["fotmob_persistent"] += 1

            # 次优先源：corner_stats_final（明确终值，按 match_date ±1 天窗口比对）
            for lh, la, total_c, match_date in (final_rows if best_total is None else []):
                if fd and match_date:
                    try:
                        d_gap = abs((datetime.strptime(match_date, "%Y-%m-%d")
                                     - datetime.strptime(fd, "%Y-%m-%d")).days)
                        if d_gap > 1:
                            continue
                    except ValueError:
                        pass
                if _fuzzy_match(home, away, lh, la):
                    best_total = total_c
                    source_hits["corner_stats_final"] += 1
                    break

            # 次优先兜底：corner_live_odds（取历史最大角球数近似终值）
            if best_total is None:
                for lh, la, status, minute, total_c, fetched_at, live_fd in live_rows:
                    if fd and live_fd:
                        try:
                            d_gap = abs((datetime.strptime(live_fd, "%Y-%m-%d")
                                         - datetime.strptime(fd, "%Y-%m-%d")).days)
                            if d_gap > 1:
                                continue
                        except ValueError:
                            pass
                    # Bug修复(2026-08-11)：corner_live_odds 的队名100%是中文
                    # （500.com/scoremer 都是中文站），而 corner_recommendations
                    # 里是英文队名，直接 _fuzzy_match 跨语言必然匹配不上——实测
                    # 历史日志里 corner_live_odds兜底 恒为0，这个兜底源从上线起
                    # 就没生效过。这里把推荐单的英文队名转成中文再比一次。
                    if not (_fuzzy_match(home, away, lh, la)
                            or _fuzzy_match(_team_zh(home), _team_zh(away), lh, la)):
                        continue
                    if best_total is None or total_c > best_total:
                        best_total = total_c
                if best_total is not None:
                    source_hits["corner_live_odds"] += 1

            # 末位兜底：qiumibao_match_results(2026-09-04新增，见_get_qiumibao_corner_totals
            # 置信度说明)——排在所有其它源之后，只在前面全部查不到时才用。
            if best_total is None:
                best_total = _match_corner_from_qiumibao(home, away, fd, qiumibao_corner_rows)
                if best_total is not None:
                    source_hits["qiumibao"] += 1

            if best_total is None:
                settled["unmatched"] += 1
                continue

            line_val = line if line is not None else 9.5
            if direction == "over":
                result = "win" if best_total > line_val else ("lose" if best_total < line_val else "push")
            elif direction == "under":
                result = "win" if best_total < line_val else ("lose" if best_total > line_val else "push")
            else:
                settled["unmatched"] += 1
                continue

            profit = (odds - 1) if result == "win" else (-1.0 if result == "lose" else 0.0)
            conn.execute(text("""
                UPDATE corner_recommendations SET status=:r, profit_loss=:p WHERE id=:id
            """), {"r": result, "p": round(profit, 4), "id": rec_id})
            settled[result] += 1
            settled_detail.append({
                "league": league, "home": home, "away": away, "market": "corner_total",
                "outcome": direction, "handicap": line, "odds": odds, "result": result,
                "profit_loss_u": round(profit, 4), "fetch_date": fd, "kickoff_utc": kickoff_utc,
                "total_corners": best_total,
            })

    total = settled["win"] + settled["lose"] + settled["push"]
    eff = settled["win"] + settled["lose"]
    print(f"\n=== 角球推荐结算 ===")
    print(f"  Win: {settled['win']}  Lose: {settled['lose']}  Push: {settled['push']}  "
          f"未匹配(暂无最终角球数): {settled['unmatched']}")
    print(f"  数据源命中: fotmob持久化={source_hits['fotmob_persistent']}  "
          f"corner_stats_final={source_hits['corner_stats_final']}  "
          f"corner_live_odds兜底={source_hits['corner_live_odds']}")
    if eff:
        print(f"  命中率: {settled['win']/eff*100:.1f}% (有效{eff}场，共{total}场已结算)")

    return settled_detail


def settle_fotmob_corner_shadow(target_date: str = None):
    """结算 shadow_recommendations 里 shadow_type='fotmob_corner' 的记录，跟
    settle_corner_recommendations() 用同一套ground truth源(corner_stats_final优先，
    corner_live_odds兜底)+同一套_fuzzy_match/_corner_is_finished判定逻辑，只是更新的
    表和shadow_type不同。2026-07-21新增，见00_命中系统.py的get_fotmob_corner_probs()说明。

    2026-09-06扩展：一并结算shadow_type='gated' AND market='corner_total'的记录——
    这是corner_model.generate_corner_slip()新增validated门控后，角球未转正时被
    转存的反事实候选(见00_命中系统.py generate_recommendations()里precomputed_corner_recs
    转shadow_multi['gated']的说明)。这批记录的outcome字段是裸的'over'/'under'
    （跟fotmob_corner的'corner_over'/'corner_under'不同后缀，但下面direction判定用
    .endswith('over'/'under')两种都能识别），handicap/best_odds字段语义完全一致，
    复用同一套corner计数匹配逻辑，不需要另写一个函数。"""
    with engine.connect() as conn:
        query = """
            SELECT id, home_team, away_team, outcome, handicap, best_odds, fetch_date, kickoff_utc, league_name
            FROM shadow_recommendations
            WHERE (shadow_type='fotmob_corner' OR (shadow_type='gated' AND market='corner_total'))
              AND status='pending'
        """
        params = {}
        if target_date:
            query += " AND fetch_date = :fd"
            params["fd"] = target_date
        recs = conn.execute(text(query), params).fetchall()

    if not recs:
        print("[fotmob_corner_settle] 无待结算角球影子记录(fotmob_corner+gated/corner_total)")
        return []

    with engine.connect() as conn:
        fotmob_rows = _bucket_by_date(_get_fotmob_corner_totals(conn))
        qiumibao_corner_rows = _bucket_by_date(_get_qiumibao_corner_totals(conn))
        try:
            final_rows = conn.execute(text("""
                SELECT home_team, away_team, total_corners, match_date FROM corner_stats_final
            """)).fetchall()
        except Exception:
            final_rows = []
        live_rows = conn.execute(text("""
            SELECT home_team, away_team, match_status, match_minute, total_corners,
                   fetched_at, fetch_date
            FROM corner_live_odds
            -- Bug修复(2026-08-11)：不能只判 IS NOT NULL，0 会漏过去。500.com 对
            -- 没有技术统计的比赛照样把角球进度条渲染成 "0 角球 0"，跟真实的0在
            -- HTML上无法区分，历史上写进了730条这种假0(占该来源83%)。足球全场零
            -- 角球实际不存在，而下面取的是同场次快照的最大值——若某场只有假0快照，
            -- 终值就会被算成0，该场所有"小球"盘会被无条件判赢。33号爬虫已在写入端
            -- 拦截，这里再防一层，同时中和历史遗留的假0数据。
            WHERE total_corners IS NOT NULL AND total_corners > 0
            -- Bug修复(2026-08-11)：排除 scoremer 来源。33号解析器里 heh/haa/rcn
            -- 三个字段的含义是注释自认的"文档推断"，从未验证，实测全错：
            --   * status 其实是比赛分钟数(1-121)，不是状态码，原 status_map 映射错误
            --   * 1691行里 701 行是 NS(比赛根本没开踢)却存着角球数
            --   * heh+haa != rcn 占 1679/1691 = 99.3%，rcn 不是两队角球之和
            --   * 571 行 total_corners > 30(最高937)，单场不可能
            -- 无法区分哪些值碰巧是对的，且该源已被403封锁不再更新，整体排除。
            AND source <> 'scoremer'
        """)).fetchall()

    source_hits = {"fotmob_persistent": 0, "corner_stats_final": 0, "corner_live_odds": 0, "qiumibao": 0}
    settled = {"win": 0, "lose": 0, "push": 0, "unmatched": 0}
    settled_detail = []
    with engine.begin() as conn:
        for rec_id, home, away, outcome, line, odds, fd, kickoff_utc, league in recs:
            if not _corner_is_finished(None, None, kickoff_utc):
                settled["unmatched"] += 1
                continue

            direction = "over" if outcome.endswith("over") else ("under" if outcome.endswith("under") else None)
            if direction is None:
                settled["unmatched"] += 1
                continue

            best_total = _match_corner_from_fotmob(home, away, fd, fotmob_rows)
            if best_total is not None:
                source_hits["fotmob_persistent"] += 1

            for lh, la, total_c, match_date in (final_rows if best_total is None else []):
                if fd and match_date:
                    try:
                        d_gap = abs((datetime.strptime(match_date, "%Y-%m-%d")
                                     - datetime.strptime(fd, "%Y-%m-%d")).days)
                        if d_gap > 1:
                            continue
                    except ValueError:
                        pass
                if _fuzzy_match(home, away, lh, la):
                    best_total = total_c
                    source_hits["corner_stats_final"] += 1
                    break

            if best_total is None:
                for lh, la, status, minute, total_c, fetched_at, live_fd in live_rows:
                    if fd and live_fd:
                        try:
                            d_gap = abs((datetime.strptime(live_fd, "%Y-%m-%d")
                                         - datetime.strptime(fd, "%Y-%m-%d")).days)
                            if d_gap > 1:
                                continue
                        except ValueError:
                            pass
                    # Bug修复(2026-08-11)：corner_live_odds 的队名100%是中文
                    # （500.com/scoremer 都是中文站），而 corner_recommendations
                    # 里是英文队名，直接 _fuzzy_match 跨语言必然匹配不上——实测
                    # 历史日志里 corner_live_odds兜底 恒为0，这个兜底源从上线起
                    # 就没生效过。这里把推荐单的英文队名转成中文再比一次。
                    if not (_fuzzy_match(home, away, lh, la)
                            or _fuzzy_match(_team_zh(home), _team_zh(away), lh, la)):
                        continue
                    if best_total is None or total_c > best_total:
                        best_total = total_c
                if best_total is not None:
                    source_hits["corner_live_odds"] += 1

            # 末位兜底：qiumibao_match_results(2026-09-04新增，见_get_qiumibao_corner_totals
            # 置信度说明)——排在所有其它源之后，只在前面全部查不到时才用。
            if best_total is None:
                best_total = _match_corner_from_qiumibao(home, away, fd, qiumibao_corner_rows)
                if best_total is not None:
                    source_hits["qiumibao"] += 1

            if best_total is None:
                settled["unmatched"] += 1
                continue

            line_val = line if line is not None else 9.5
            if direction == "over":
                result = "win" if best_total > line_val else ("lose" if best_total < line_val else "push")
            else:
                result = "win" if best_total < line_val else ("lose" if best_total > line_val else "push")

            profit = (odds - 1) if result == "win" else (-1.0 if result == "lose" else 0.0)
            conn.execute(text("""
                UPDATE shadow_recommendations SET status=:r, profit_loss=:p WHERE id=:id
            """), {"r": result, "p": round(profit, 4), "id": rec_id})
            settled[result] += 1
            settled_detail.append({
                "league": league, "home": home, "away": away, "market": "corner_ou",
                "outcome": outcome, "handicap": line, "odds": odds, "result": result,
                "profit_loss_u": round(profit, 4), "fetch_date": fd, "kickoff_utc": kickoff_utc,
                "total_corners": best_total,
            })

    total = settled["win"] + settled["lose"] + settled["push"]
    eff = settled["win"] + settled["lose"]
    print(f"\n=== 角球影子桶结算(FotMob角球+角球未转正反事实) ===")
    print(f"  Win: {settled['win']}  Lose: {settled['lose']}  Push: {settled['push']}  "
          f"未匹配(暂无最终角球数): {settled['unmatched']}")
    print(f"  数据源命中: fotmob持久化={source_hits['fotmob_persistent']}  "
          f"corner_stats_final={source_hits['corner_stats_final']}  "
          f"corner_live_odds兜底={source_hits['corner_live_odds']}")
    if eff:
        print(f"  命中率: {settled['win']/eff*100:.1f}% (有效{eff}场，共{total}场已结算)")

    return settled_detail


def write_daily_snapshot(target_date, main_detail, under_detail, shadow_detail, corner_detail):
    """把本次新结算的推荐单结果写一份人类可读快照到 slip_output_dir()
    （FIX-001：live模式=D:\lucky，paper模式=D:\lucky_paper 并带水印）。
    主推荐单用真实下注金额(元)算盈亏；影子观察单没有真实下注，按1单位(u)假设算。
    """
    if not any([main_detail, under_detail, shadow_detail, corner_detail]):
        print("  (本次无新结算，跳过快照)")
        return

    lines: list[str] = []
    def out(s: str = ""):
        lines.append(s)

    def _fmt_result(r):
        return {"win": "✅命中", "lose": "❌未中", "push": "➖走水"}.get(r, r)

    def _kickoff_str(ko: str) -> str:
        try:
            dt = datetime.fromisoformat((ko or "").replace("Z", "+00:00"))
            from datetime import timezone as _tz
            return dt.astimezone(_tz(timedelta(hours=8))).strftime("%m月%d日%H:%M")
        except Exception:
            return "--月--日--:--"

    def _score_str(d: dict) -> str:
        if d.get("total_corners") is not None:
            return f"角球{d['total_corners']}"
        hs, aws = d.get("home_score"), d.get("away_score")
        return f"{hs}-{aws}" if hs is not None and aws is not None else "-"

    def _direction_zh(d: dict) -> str:
        oc = _OUTCOME_ZH.get(d["outcome"], d["outcome"])
        return f"{oc}{d['handicap']}" if d.get("handicap") is not None else oc

    out("=" * 108)
    out(f"  📋 投注单结算快照  [{target_date or '全部日期'}]  生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    out("=" * 108)

    if main_detail:
        w = sum(1 for d in main_detail if d["result"] == "win")
        l = sum(1 for d in main_detail if d["result"] == "lose")
        p = sum(1 for d in main_detail if d["result"] == "push")
        pnl = sum(d["profit_loss"] for d in main_detail if d["profit_loss"] is not None)
        staked = sum(d["stake"] for d in main_detail if d["stake"] is not None)
        roi_s = f"  ROI {pnl/staked*100:+.1f}%" if staked else ""
        out(f"\n  💰 主推荐单（真实下注，元）  共{len(main_detail)}条  胜{w} 负{l} 走{p}  合计盈亏 {pnl:+.2f}元{roi_s}")
        out("  " + "-" * 106)
        out(f"  {'开赛时间':<12} {'主队':<14}vs{'客队':<14} {'市场':<8}{'方向':<10}{'赔率':>6} "
            f"{'下注':>6} {'赛果':>7} {'结果':<7}{'盈亏':>10}")
        for d in main_detail:
            h_zh, a_zh = _team_zh(d['home'])[:14], _team_zh(d['away'])[:14]
            direction = _direction_zh(d)
            mkt_zh = _MARKET_ZH.get(d['market'], d['market'])
            stake_s = f"{d['stake']:.0f}元" if d["stake"] is not None else "-"
            pnl_s = f"{d['profit_loss']:+.2f}元" if d["profit_loss"] is not None else "-"
            out(f"  {_kickoff_str(d['kickoff_utc']):<12} {h_zh:<14}vs{a_zh:<14} {mkt_zh:<8}{direction:<10}"
                f"{d['odds']:>6.2f} {stake_s:>6} {_score_str(d):>7} {_fmt_result(d['result']):<7}{pnl_s:>10}")

    def _shadow_section(title: str, detail: list):
        if not detail:
            return
        w = sum(1 for d in detail if d["result"] == "win")
        l = sum(1 for d in detail if d["result"] == "lose")
        p = sum(1 for d in detail if d["result"] == "push")
        pnl = sum(d["profit_loss_u"] for d in detail)
        out(f"\n  📊 {title}（观察单，未实际下注，按1单位u估算）  共{len(detail)}条  胜{w} 负{l} 走{p}  合计 {pnl:+.2f}u")
        out("  " + "-" * 106)
        for d in detail:
            h_zh, a_zh = _team_zh(d['home'])[:14], _team_zh(d['away'])[:14]
            direction = _direction_zh(d)
            mkt_zh = _MARKET_ZH.get(d['market'], d['market'])
            out(f"  {_kickoff_str(d['kickoff_utc']):<12} {h_zh:<14}vs{a_zh:<14} {mkt_zh:<8}{direction:<10}"
                f"@{d['odds']:<5.2f} {_score_str(d):>7} {_fmt_result(d['result']):<7}{d['profit_loss_u']:+.3f}u")

    _shadow_section("独赢/让球/胜平负 影子观察单", shadow_detail)
    _shadow_section("小球(under) 影子观察单", under_detail)
    _shadow_section("角球大小球 观察单", corner_detail)

    out("\n" + "=" * 108)

    try:
        # FIX-001(2026-09-12)：跟投注单同一套双开关——纸面模式(默认)写
        # D:\lucky_paper\ 并加水印；仅 live+ENABLE_LIVE_BETTING=1 才写 D:\lucky\。
        _out_dir = slip_output_dir()
        os.makedirs(_out_dir, exist_ok=True)
        fname = f"结算快照_{target_date or datetime.now().strftime('%Y-%m-%d')}_{datetime.now().strftime('%H%M')}.txt"
        path = os.path.join(_out_dir, fname)
        with open(path, "w", encoding="utf-8") as f:
            if not is_live_betting():
                f.write(f"{PAPER_WATERMARK} (BETTING_MODE=paper)\n\n")
            f.write("\n".join(lines) + "\n")
        print(f"  📄 结算快照已保存: {path}")
    except Exception as e:
        print(f"  ⚠ 结算快照保存失败: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=str, default=None)
    parser.add_argument("--shadow", action="store_true", help="只结算小球影子候选")
    args = parser.parse_args()
    if args.shadow:
        auto_settle_under_shadow(args.date)
    else:
        # 结算前先补抓一次角球终值/实时兜底数据(2026-07-26用户要求)：37号/33号
        # 这两个源都只有"比赛刚结束后不久"的时效窗口(见feedback_corner_data_source_timing
        # 记忆)，事后一两天再补抓大概率抓空。放在结算管道最前面跑一次，尽量在角球
        # 候选对应的比赛结束后较短时间内拿到数据，跟下面settle_corner_recommendations()/
        # settle_fotmob_corner_shadow()用的是同一批数据源，不重复抓两次。
        # 用subprocess独立进程而不是importlib(见feedback_scraper_launch记忆)，避免
        # sys.argv继承和SQLite锁冲突。
        # 48号(qiumibao)补的是半场/全场比分+角球第四层兜底(2026-09-04用户要求接入
        # 结算管道)，跟37/33号角球终值同一时机跑最合适——不像37/33只有赛后短暂
        # 时效窗口，48号还额外支持--date补抓历史日期(见48号文件头today_archive
        # 滚动窗口 vs 指定日期端点的坑点说明)，结算指定历史日期(args.date)时一并
        # 把该日期传进去，让它去查/mc/{date}_cn.htm兜底today_archive覆盖不到的场次。
        _corner_scraper_dir = os.path.dirname(os.path.abspath(__file__))
        _cs_scripts = ["37_corner_stats_scraper.py", "33_corner_odds_scraper.py",
                       "48_qiumibao_corner_scraper.py"]
        for _cs_script in _cs_scripts:
            try:
                print(f"  🏁 补抓角球数据: {_cs_script} ...")
                _cs_cmd = [sys.executable, "-X", "utf8", _cs_script]
                if _cs_script == "48_qiumibao_corner_scraper.py":
                    # 结算管道要的是完场比分/角球(--finished-only)，不是赔率快照——
                    # 后者是00_命中系统.py每日调度默认调用的，两个调用方分工见
                    # 48号文件头说明。
                    _cs_cmd += ["--finished-only"]
                    if args.date:
                        _cs_cmd += ["--date", args.date]
                _cs_result = subprocess.run(
                    _cs_cmd,
                    cwd=_corner_scraper_dir, timeout=300,
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                )
                _cs_tail = (_cs_result.stdout or "").strip().splitlines()[-3:]
                print(f"    {_cs_script} 完成(exit={_cs_result.returncode})：{' | '.join(_cs_tail)}")
            except Exception as _cs_e:
                print(f"    ⚠ {_cs_script} 补抓异常（跳过，不影响后续结算）: {_cs_e}")

        main_detail    = auto_settle(args.date) or []
        under_detail   = auto_settle_under_shadow(args.date) or []
        # 大球影子候选(over_shadow_bets)，2026-08-02新增，见00_命中系统.py里
        # over_shadow_bets建表说明——total/over此前是唯一没有影子追踪的市场
        auto_settle_over_shadow(args.date)
        shadow_detail  = settle_shadow_recommendations(args.date) or []
        corner_detail  = settle_corner_recommendations(args.date) or []
        # 球队大小完整候选样本(不做每日Top10截断)，供_team_total_validation_status()
        # 转正判断用真实数据，见00_命中系统.py里team_total_shadow_full建表说明
        settle_team_total_shadow_full(args.date)
        # 足球球队大小/小球"老逻辑"平行线(2026-08-01新增，用户要求)，独立于正式
        # 推荐单，见00_命中系统.py里_generate_legacy_team_total_under()说明
        settle_legacy_team_total_under(args.date)
        # 篮球小球/独赢"反着买"转正平行线(2026-08-01新增，用户要求)，见
        # 00_命中系统.py里_generate_basketball_under_fade()/
        # _generate_basketball_moneyline_fade()说明
        settle_basketball_under_fade(args.date)
        settle_basketball_moneyline_fade(args.date)
        # 独赢完整候选样本(不做每日Top10截断)，供_moneyline_validation_status()
        # 按(sport_code,outcome)转正判断用真实数据，见00_命中系统.py里
        # moneyline_shadow_full建表说明
        settle_moneyline_shadow_full(args.date)
        # FotMob角球影子桶(shadow_type='fotmob_corner')不走_settle_result()(该函数不认
        # corner_ou/corner_hdp市场)，需要单独结算，见settle_fotmob_corner_shadow()说明
        settle_fotmob_corner_shadow(args.date)
        # FIX-014-1（2026-09-14）：pending积压清理挂结算链尾部——>30天陈旧pending
        # 里比分源结构性无覆盖的标void（A类），源有覆盖的保留待三层结算补（B类）。
        # 幂等、失败不阻断结算主链；规则详见 _pending_sweep.py 文件头。
        try:
            import _pending_sweep
            _pending_sweep.run(dry_run=False)
        except Exception as _e:
            print(f"⚠️  pending积压清理异常（跳过，不影响结算）: {_e}")
        write_daily_snapshot(args.date, main_detail, under_detail, shadow_detail, corner_detail)
        # 结算完成后自动输出复盘报告
        try:
            import _review_report
            _review_report.run_report(days=90)
        except Exception as _e:
            print(f"⚠️  复盘报告异常（跳过）: {_e}")
        # 结算完成后自动生成全玩法结算报告到桌面（2026-07-25用户要求：每次跑完
        # 结算管道自动发送，不用每次手动跑_export_shadow_daily_report.py）
        try:
            import _export_shadow_daily_report
            _export_shadow_daily_report.main()
        except Exception as _e:
            print(f"⚠️  桌面结算报告生成异常（跳过）: {_e}")
