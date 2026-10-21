# -*- coding: utf-8 -*-
"""
命中系统·回测闭环引擎 v1.0
功能: 自动对比推荐 vs 赛果，计算命中率/ROI，分维度统计
"""
import sqlite3, sys, io, json, os
from datetime import datetime, timedelta
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DB_PATH = r'D:\cl\qqsj\data\sports_data.db'

from htft_settle import classify_ht_ft

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def american_to_decimal(amer):
    """美式赔率转十进制"""
    if amer is None: return None
    amer = int(amer)
    if amer > 0: return round(amer / 100 + 1, 3)
    elif amer < 0: return round(100 / abs(amer) + 1, 3)
    return 2.0

def outcome_matches(market, outcome, home_score, away_score, handicap=None, line=None,
                    home_score_ht=None, away_score_ht=None):
    """判断推荐方向是否命中"""
    if market in ('ht_ft', '半全场'):
        # 半全场：半场+全场结果须同时猜中，官方规则没有"push"（部分中奖）
        ht_r, ft_r = classify_ht_ft(home_score_ht, away_score_ht, home_score, away_score)
        if ht_r is None:
            return None  # 半场比分未到位，未完赛/无法判定
        return outcome == f"{ht_r}-{ft_r}"

    if home_score is None or away_score is None:
        return None  # 未完赛

    hs, as_ = int(home_score), int(away_score)

    if market in ('moneyline', '独赢', '1x2', 'matchup'):
        if outcome == 'home' and hs > as_: return True
        if outcome == 'away' and hs < as_: return True
        if outcome == 'draw' and hs == as_: return True
        return False
    
    elif market in ('spread', '让球', 'handicap', 'points'):
        if handicap is not None:
            try: hc = float(handicap)
            except: return None
        else: return None
        diff = hs - as_
        if outcome == 'home':
            return diff + hc > 0
        elif outcome == 'away':
            return diff + hc < 0
        return None
    
    elif market in ('total', '大小球', 'totals'):
        total = hs + as_
        if line is not None:
            try: ln = float(line)
            except: return None
        else: return None
        if outcome == 'over':
            return total > ln
        elif outcome == 'under':
            return total < ln
        return None
    
    return None

def run_backtest(target_date=None):
    """
    target_date: 'YYYY-MM-DD' 格式，对比该日推荐的命中情况
    如果不指定，自动对比最近一个有推荐但有赛果的日期
    """
    conn = get_conn()
    cur = conn.cursor()
    
    # 1. 获取有赛果的推荐
    # hit_recommendations 存了每日推荐
    # unified_matches 存了赛果
    # 需要通过队名+时间匹配
    
    if target_date:
        date_filter = f"AND date(h.kickoff_utc) = '{target_date}'"
    else:
        date_filter = ""
    
    # 获取所有推荐（有赔率的）
    cur.execute(f"""
        SELECT h.*, h.best_odds as used_odds
        FROM hit_recommendations h
        WHERE h.best_odds IS NOT NULL AND h.best_odds > 0
        {date_filter}
        ORDER BY h.hit_score DESC
    """)
    recs = [dict(r) for r in cur.fetchall()]
    
    if not recs:
        print(f"⚠️ 没有找到推荐记录" + (f" (日期: {target_date})" if target_date else ""))
        conn.close()
        return
    
    print(f"📊 回测引擎启动")
    print(f"推荐总数: {len(recs)}条")
    
    # 2. 获取赛果 - unified_matches
    cur.execute("""
        SELECT unified_id, sport_code, home_team_std, away_team_std,
               kickoff_utc, status, home_score, away_score,
               home_score_ht, away_score_ht
        FROM unified_matches
        WHERE status = 'FT'
        AND home_score IS NOT NULL
    """)
    results = {}
    for r in cur.fetchall():
        key = f"{r['home_team_std']}|{r['away_team_std']}|{r['kickoff_utc'][:10] if r['kickoff_utc'] else ''}"
        results[key] = dict(r)
    
    print(f"赛果库: {len(results)}场已完成比赛")
    
    # 3. 逐条匹配
    matched = 0
    pending = 0
    stats = {
        'total': 0, 'hit': 0, 'miss': 0, 'no_result': 0,
        'by_league': defaultdict(lambda: {'hit':0, 'miss':0, 'total':0, 'profit':0}),
        'by_market': defaultdict(lambda: {'hit':0, 'miss':0, 'total':0, 'profit':0}),
        'by_score_band': defaultdict(lambda: {'hit':0, 'miss':0, 'total':0, 'profit':0}),
        'by_odds_band': defaultdict(lambda: {'hit':0, 'miss':0, 'total':0, 'profit':0}),
        'total_profit': 0, 'total_stake': 0,
        'details': [],
    }
    
    for rec in recs:
        home = rec.get('home_team', '')
        away = rec.get('away_team', '')
        kickoff = rec.get('kickoff_utc', '')
        league = rec.get('league_name', '未知')
        market = rec.get('market', '未知')
        outcome = rec.get('outcome', '')
        odds = rec.get('used_odds') or rec.get('best_odds') or 0
        hit_score = rec.get('hit_score', 0)
        handicap = rec.get('line_value') or rec.get('handicap')
        
        if not odds or odds < 1:
            continue
        
        stats['total'] += 1
        
        # 尝试匹配赛果
        result = None
        # 方法1: unified_id 匹配
        if rec.get('unified_id'):
            for k, v in results.items():
                if str(v.get('unified_id')) == str(rec['unified_id']):
                    result = v
                    break
        
        # 方法2: 队名+日期匹配
        if not result:
            kdate = kickoff[:10] if kickoff else ''
            for k, v in results.items():
                if home and v['home_team_std'] and (
                    home in v['home_team_std'] or v['home_team_std'] in home
                ) and kdate in k:
                    result = v
                    break
        
        if not result:
            stats['no_result'] += 1
            continue
        
        matched += 1
        home_score = result['home_score']
        away_score = result['away_score']
        home_score_ht = result['home_score_ht']
        away_score_ht = result['away_score_ht']

        # 判断命中
        hit = outcome_matches(market, outcome, home_score, away_score, handicap,
                              home_score_ht=home_score_ht, away_score_ht=away_score_ht)
        
        if hit is None:
            pending += 1
            continue
        
        # 计算 ROI
        stake = 1.0  # 单位下注
        if hit:
            profit = (odds - 1) * stake
            stats['hit'] += 1
        else:
            profit = -stake
            stats['miss'] += 1
        
        stats['total_profit'] += profit
        stats['total_stake'] += stake
        
        # 分维度统计
        # 联赛
        lg = stats['by_league'][league]
        lg['total'] += 1
        lg['hit' if hit else 'miss'] += 1
        lg['profit'] += profit
        
        # 市场
        mk = stats['by_market'][market]
        mk['total'] += 1
        mk['hit' if hit else 'miss'] += 1
        mk['profit'] += profit
        
        # 命中分区
        if hit_score >= 0.75: band = 'S(>=0.75)'
        elif hit_score >= 0.65: band = 'A(0.65-0.75)'
        elif hit_score >= 0.55: band = 'B(0.55-0.65)'
        else: band = 'C(<0.55)'
        sb = stats['by_score_band'][band]
        sb['total'] += 1
        sb['hit' if hit else 'miss'] += 1
        sb['profit'] += profit
        
        # 赔率分区
        if odds < 1.8: ob = '低赔(<1.8)'
        elif odds < 2.5: ob = '中赔(1.8-2.5)'
        elif odds < 3.5: ob = '高赔(2.5-3.5)'
        else: ob = '冷门(>=3.5)'
        ob_s = stats['by_odds_band'][ob]
        ob_s['total'] += 1
        ob_s['hit' if hit else 'miss'] += 1
        ob_s['profit'] += profit
        
        # 详情记录
        stats['details'].append({
            'league': league, 'home': home, 'away': away,
            'market': market, 'outcome': outcome, 'odds': round(odds, 2),
            'hit_score': round(hit_score, 3),
            'score': f"{home_score}-{away_score}",
            'hit': hit, 'profit': round(profit, 2),
        })
    
    # 4. 输出统计
    total_decided = stats['hit'] + stats['miss']
    hit_rate = stats['hit'] / total_decided * 100 if total_decided > 0 else 0
    roi = stats['total_profit'] / stats['total_stake'] * 100 if stats['total_stake'] > 0 else 0
    
    print(f"\n{'='*60}")
    print(f"📊 回测结果总览")
    print(f"{'='*60}")
    print(f"推荐总数: {stats['total']} | 已匹配赛果: {matched} | 未完赛/无赛果: {stats['no_result']}")
    print(f"命中: {stats['hit']} | 未中: {stats['miss']} | 命中率: {hit_rate:.1f}%")
    print(f"总利润: {stats['total_profit']:+.2f} 单位 | ROI: {roi:+.1f}%")
    
    # 联赛排名
    print(f"\n{'='*60}")
    print(f"📈 按联赛统计（命中率 > 0 的）")
    print(f"{'='*60}")
    lg_sorted = sorted(stats['by_league'].items(), key=lambda x: x[1]['total'], reverse=True)
    for lg_name, lg in lg_sorted[:20]:
        if lg['total'] == 0: continue
        lg_hr = lg['hit'] / lg['total'] * 100
        print(f"  {lg_name[:25]:25s} | {lg['total']:3d}场 | 命中{lg['hit']:2d} | {lg_hr:5.1f}% | 利润{lg['profit']:+.1f}")
    
    # 市场统计
    print(f"\n{'='*60}")
    print(f"📈 按市场类型统计")
    print(f"{'='*60}")
    for mk_name, mk in sorted(stats['by_market'].items(), key=lambda x: x[1]['total'], reverse=True):
        if mk['total'] == 0: continue
        mk_hr = mk['hit'] / mk['total'] * 100
        print(f"  {mk_name[:20]:20s} | {mk['total']:3d}场 | 命中{mk['hit']:2d} | {mk_hr:5.1f}% | 利润{mk['profit']:+.1f}")
    
    # 命中分区统计
    print(f"\n{'='*60}")
    print(f"📈 按命中分等级统计")
    print(f"{'='*60}")
    for band in ['S(>=0.75)', 'A(0.65-0.75)', 'B(0.55-0.65)', 'C(<0.55)']:
        sb = stats['by_score_band'].get(band, {'total':0,'hit':0,'miss':0,'profit':0})
        if sb['total'] == 0: 
            print(f"  {band:18s} | 无数据")
            continue
        sb_hr = sb['hit'] / sb['total'] * 100
        print(f"  {band:18s} | {sb['total']:3d}场 | 命中{sb['hit']:2d} | {sb_hr:5.1f}% | 利润{sb['profit']:+.1f}")
    
    # 赔率分区统计
    print(f"\n{'='*60}")
    print(f"📈 按赔率区间统计")
    print(f"{'='*60}")
    for ob in ['低赔(<1.8)', '中赔(1.8-2.5)', '高赔(2.5-3.5)', '冷门(>=3.5)']:
        obs = stats['by_odds_band'].get(ob, {'total':0,'hit':0,'miss':0,'profit':0})
        if obs['total'] == 0: continue
        obs_hr = obs['hit'] / obs['total'] * 100
        print(f"  {ob:18s} | {obs['total']:3d}场 | 命中{obs['hit']:2d} | {obs_hr:5.1f}% | 利润{obs['profit']:+.1f}")
    
    # 命中详情（Top 20）
    print(f"\n{'='*60}")
    print(f"✅ 命中详情 (Top 20)")
    print(f"{'='*60}")
    hits = [d for d in stats['details'] if d['hit']]
    hits.sort(key=lambda x: x['profit'], reverse=True)
    for d in hits[:20]:
        print(f"  ✅ [{d['league'][:12]}] {d['home'][:12]} vs {d['away'][:12]} | {d['market']}/{d['outcome']} @ {d['odds']:.2f} | 比分{d['score']} | +{d['profit']:.2f}")
    
    # 未中详情 (Top 10)
    print(f"\n{'='*60}")
    print(f"❌ 未中详情 (Top 10)")
    print(f"{'='*60}")
    misses = [d for d in stats['details'] if not d['hit']]
    misses.sort(key=lambda x: x['profit'])
    for d in misses[:10]:
        print(f"  ❌ [{d['league'][:12]}] {d['home'][:12]} vs {d['away'][:12]} | {d['market']}/{d['outcome']} @ {d['odds']:.2f} | 比分{d['score']} | {d['profit']:.2f}")
    
    # 5. 保存到数据库
    print(f"\n{'='*60}")
    print(f"💾 保存回测结果到数据库")
    
    # 创建/更新 backtest_daily 表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS backtest_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_date TEXT,
            total_recs INTEGER,
            matched INTEGER,
            hit_count INTEGER,
            miss_count INTEGER,
            hit_rate REAL,
            total_profit REAL,
            roi REAL,
            by_league_json TEXT,
            by_market_json TEXT,
            by_score_band_json TEXT,
            by_odds_band_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    
    cur.execute("""
        INSERT INTO backtest_daily (test_date, total_recs, matched, hit_count, miss_count, 
            hit_rate, total_profit, roi, by_league_json, by_market_json, by_score_band_json, by_odds_band_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        target_date or 'all',
        stats['total'], matched, stats['hit'], stats['miss'],
        round(hit_rate, 2), round(stats['total_profit'], 2), round(roi, 2),
        json.dumps(dict(stats['by_league']), ensure_ascii=False),
        json.dumps(dict(stats['by_market']), ensure_ascii=False),
        json.dumps(dict(stats['by_score_band']), ensure_ascii=False),
        json.dumps(dict(stats['by_odds_band']), ensure_ascii=False),
    ))
    
    conn.commit()
    conn.close()
    print(f"✅ 回测结果已保存到 backtest_daily 表")
    
    return stats

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', help='回测日期 YYYY-MM-DD，不指定则回测全部')
    args = parser.parse_args()
    run_backtest(args.date)
