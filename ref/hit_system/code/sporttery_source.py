"""
竞彩官网 (sporttery.cn) 数据源模块
替代已失效的 The Odds API，提供足球/篮球对阵+赔率
"""
import requests, time, json, logging
from datetime import datetime
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

SPORTTERY_BASE = "https://webapi.sporttery.cn/gateway"

# ─── 竞彩 API 端点 ───
SPORTTERY_FOOTBALL = f"{SPORTTERY_BASE}/jc/football/getMatchCalculatorV1.qry"
SPORTTERY_BASKETBALL = f"{SPORTTERY_BASE}/jc/basketball/getMatchCalculatorV1.qry"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.sporttery.cn/',
    'Accept': 'application/json',
}

# ─── 竞彩联赛ID → 我们的联赛代码 ───
SPORTTERY_LEAGUE_MAP = {
    # 足球
    37:  ('bundesliga', '德甲'),
    39:  ('premier_league', '英超'),
    140: ('laliga', '西甲'),
    135: ('serie_a', '意甲'),
    61:  ('ligue_1', '法甲'),
    51:  ('eliteserien', '挪超'),
    58:  ('allsvenskan', '瑞超'),
    88:  ('eredivisie', '荷甲'),
    94:  ('liga_portugal', '葡超'),
    40:  ('championship', '英冠'),
    203: ('super_lig', '土超'),
    144: ('pro_league_be', '比甲'),
    75:  ('j1', 'J1联赛'),
    169: ('csl', '中超'),
    71:  ('serie_a_br', '巴甲'),
    292: ('k_league_1', 'K联赛'),
    134: ('mls', '美职联'),
    # 篮球
    1:   ('nba', 'NBA'),
    2:   ('wnba', 'WNBA'),
    3:   ('euroleague', '欧篮联'),
    4:   ('cba', 'CBA'),
    7:   ('bbl', '日B联'),
}

# ─── 竞彩比赛状态映射 ───
SPORTTERY_STATUS_MAP = {
    'Selling': 'NS',       # 在售 — 未开赛
    'EndOfSale': 'NS',    # 停售 — 即将开赛
    'Playing': 'LIVE',    # 进行中
    'Finish': 'FT',       # 已结束
    'Cancel': 'CANCEL',
}

def _safe_get_odds(odds_dict: dict, key: str, default: float = None) -> Optional[float]:
    """安全获取赔率值"""
    v = odds_dict.get(key, '')
    if v and v != '-' and v != '--':
        try:
            return float(v)
        except:
            pass
    return default


def fetch_sporttery_fixtures(sport: str, date_from: str, date_to: str) -> List[dict]:
    """
    从竞彩API抓取对阵表
    
    Args:
        sport: 'football' or 'basketball'
        date_from: '2026-05-25'
        date_to: '2026-05-26'
    
    Returns:
        [{match_id, sport, league_code, league_name, league_name_cn,
          home_team, away_team, match_time, status, odds_data, market_types...}]
    """
    if sport == 'football':
        url = SPORTTERY_FOOTBALL
    else:
        url = SPORTTERY_BASKETBALL
    
    fixtures = []
    
    try:
        resp = requests.get(url, headers=HEADERS, params={
            'matchBeginDate': date_from,
            'matchEndDate': date_to,
            'pageNo': '1',
            'pageSize': '200',
        }, timeout=30)
        
        if resp.status_code != 200:
            logger.error(f"竞彩API {sport}: HTTP {resp.status_code}")
            return fixtures
        
        data = resp.json()
        val = data.get('value')
        if not val:
            return fixtures
        
        match_info_list = val.get('matchInfoList', [])
        
        for group in match_info_list:
            for sm in group.get('subMatchList', []):
                try:
                    status = sm.get('matchStatus', '')
                    
                    # 只抓未开赛/在售
                    if status not in ('Selling', 'EndOfSale', 'Playing'):
                        continue
                    
                    league_id = sm.get('leagueId')
                    league_code, league_cn = SPORTTERY_LEAGUE_MAP.get(league_id, (None, None))
                    if league_code is None:
                        league_code = sm.get('leagueAbbName', '').lower().replace(' ', '_')
                        league_cn = sm.get('leagueAllName', sm.get('leagueAbbName', ''))
                    
                    match_time = sm.get('matchTime', '')
                    match_date = sm.get('matchDate', '')
                    if match_time and match_date:
                        match_datetime = f"{match_date} {match_time}"
                    else:
                        match_datetime = match_date or ''
                    
                    fixture = {
                        'match_id': str(sm.get('matchId')),
                        'match_num': sm.get('matchNumStr', ''),
                        'sport': sport,
                        'league_code': league_code,
                        'league_name': sm.get('leagueAllName', ''),
                        'league_name_cn': league_cn or sm.get('leagueAllName', ''),
                        'league_id': league_id,
                        'home_team': sm.get('homeTeamAllName', ''),
                        'home_team_abbr': sm.get('homeTeamAbbName', ''),
                        'home_team_en': sm.get('homeTeamAbbEnName', ''),
                        'away_team': sm.get('awayTeamAllName', ''),
                        'away_team_abbr': sm.get('awayTeamAbbName', ''),
                        'away_team_en': sm.get('awayTeamAbbEnName', ''),
                        'match_datetime': match_datetime,
                        'match_date': match_date,
                        'match_time': match_time,
                        'status': SPORTTERY_STATUS_MAP.get(status, status),
                        'status_raw': status,
                    }
                    
                    # ─── 足球赔率 ───
                    if sport == 'football':
                        # 胜平负
                        had = sm.get('had', {})
                        fixture['odds_1x2_home'] = _safe_get_odds(had, 'h')
                        fixture['odds_1x2_draw'] = _safe_get_odds(had, 'd')
                        fixture['odds_1x2_away'] = _safe_get_odds(had, 'a')
                        
                        # 让球胜平负
                        hhad = sm.get('hhad', {})
                        fixture['odds_ah_home'] = _safe_get_odds(hhad, 'h')
                        fixture['odds_ah_draw'] = _safe_get_odds(hhad, 'd')
                        fixture['odds_ah_away'] = _safe_get_odds(hhad, 'a')
                        fixture['ah_line'] = _safe_get_odds(hhad, 'goalLineValue')
                        
                        # 总进球(TTG精确进球档位0/1/.../7+)不是大小球线，不能直接拿
                        # 某一档(如s3)的赔率冒充"大于2.5球"的赔率——s3只是"恰好3球"
                        # 这一档。这里用完整分布聚合出等价的2.5球大小线：under=s0+s1+s2
                        # (0/1/2球)，over=s3+s4+s5+s6+s7(3球及以上)，按隐含概率(1/odds)
                        # 累加再取倒数合成，任何一档缺失/异常都整体置空，不出半成品数据。
                        ttg = sm.get('ttg', {})
                        _under_p = _over_p = 0.0
                        _ttg_ok = True
                        for k in ('s0', 's1', 's2'):
                            v = _safe_get_odds(ttg, k)
                            if not v or v <= 1.0:
                                _ttg_ok = False
                                break
                            _under_p += 1.0 / v
                        if _ttg_ok:
                            for k in ('s3', 's4', 's5', 's6', 's7'):
                                v = _safe_get_odds(ttg, k)
                                if not v or v <= 1.0:
                                    _ttg_ok = False
                                    break
                                _over_p += 1.0 / v
                        if _ttg_ok and _under_p > 0 and _over_p > 0:
                            fixture['odds_under'] = round(1.0 / _under_p, 3)
                            fixture['odds_over'] = round(1.0 / _over_p, 3)
                            fixture['total_line'] = 2.5
                        else:
                            fixture['odds_over'] = fixture['odds_under'] = fixture['total_line'] = None
                        
                        # 比分 (存储原始数据供后用)
                        crs = sm.get('crs', {})
                        fixture['crs_odds'] = {k: v for k, v in crs.items() 
                                               if not k.endswith('f') and k not in ('goalLine', 'goalLineValue')}
                        
                        # 半全场
                        hafu = sm.get('hafu', {})
                        fixture['hafu_odds'] = {k: _safe_get_odds(hafu, k) for k in 
                                                ['hh', 'hd', 'ha', 'dh', 'dd', 'da', 'ah', 'ad', 'aa']}
                    
                    # ─── 篮球赔率 ───
                    else:
                        # 胜负
                        mnl = sm.get('mnl', {})
                        fixture['odds_moneyline_home'] = _safe_get_odds(mnl, 'h')
                        fixture['odds_moneyline_away'] = _safe_get_odds(mnl, 'a')
                        
                        # 让分胜负
                        hdc = sm.get('hdc', {})
                        fixture['odds_spread_home'] = _safe_get_odds(hdc, 'h')
                        fixture['odds_spread_away'] = _safe_get_odds(hdc, 'a')
                        fixture['spread_line'] = _safe_get_odds(hdc, 'goalLineValue')
                        
                        # 大小分
                        hilo = sm.get('hilo', {})
                        fixture['odds_over'] = _safe_get_odds(hilo, 'h')  # h=大分
                        fixture['odds_under'] = _safe_get_odds(hilo, 'l')  # l=小分
                        fixture['total_line'] = _safe_get_odds(hilo, 'goalLineValue')
                        
                        # 胜分差
                        wnm = sm.get('wnm', {})
                        fixture['wnm_odds'] = {k: v for k, v in wnm.items() 
                                               if not k.endswith('f') and k not in ('goalLine', 'goalLineValue')}
                    
                    fixtures.append(fixture)
                    
                except Exception as e:
                    logger.warning(f"竞彩解析单场失败: {e}")
                    continue
        
        logger.info(f"竞彩 {sport} {date_from}~{date_to}: {len(fixtures)} 场")
        
    except requests.RequestException as e:
        logger.error(f"竞彩API请求失败 {sport}: {e}")
    except Exception as e:
        logger.error(f"竞彩API解析失败 {sport}: {e}")
    
    return fixtures


def fetch_all_sporttery_odds(date_str: str, before_13: bool = True) -> Dict[str, List]:
    """
    一站式抓取竞彩足球+篮球对阵及赔率
    
    返回: {'football': [...fixtures...], 'basketball': [...fixtures...]}
    """
    result = {'football': [], 'basketball': []}
    
    for sport, url in [('football', SPORTTERY_FOOTBALL), ('basketball', SPORTTERY_BASKETBALL)]:
        fixtures = fetch_sporttery_fixtures(sport, date_str, date_str)
        
        # 如需筛选13:00前
        if before_13 and fixtures:
            filtered = []
            for f in fixtures:
                t = f.get('match_time', '')
                if t and t <= '13:00:00':
                    filtered.append(f)
                elif not t:
                    filtered.append(f)  # 无时间不筛
            fixtures = filtered
        
        result[sport] = fixtures
    
    return result


if __name__ == '__main__':
    # 测试
    data = fetch_all_sporttery_odds('2026-05-26', before_13=False)
    print(f"Football: {len(data['football'])} matches")
    print(f"Basketball: {len(data['basketball'])} matches")
    
    for f in data['football'][:2]:
        print(f"\n⚽ {f['league_name_cn']} | {f['home_team']} vs {f['away_team']}")
        print(f"  胜平负: {f.get('odds_1x2_home')}/{f.get('odds_1x2_draw')}/{f.get('odds_1x2_away')}")
        print(f"  让球: {f.get('ah_line')} {f.get('odds_ah_home')}/{f.get('odds_ah_draw')}/{f.get('odds_ah_away')}")
        hd = f.get('hafu_odds', {})
        if hd:
            print(f"  半全场: {json.dumps({k: v for k, v in hd.items() if v}, ensure_ascii=False)}")
    
    for f in data['basketball'][:2]:
        print(f"\n🏀 {f['league_name_cn']} | {f['home_team']} vs {f['away_team']}")
        print(f"  胜负: {f.get('odds_moneyline_home')}/{f.get('odds_moneyline_away')}")
        print(f"  让分: {f.get('spread_line')} {f.get('odds_spread_home')}/{f.get('odds_spread_away')}")
        print(f"  大小分: {f.get('total_line')} 大{f.get('odds_over')}/小{f.get('odds_under')}")
