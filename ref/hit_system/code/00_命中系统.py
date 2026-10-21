# 00_命中系统.py — 全源数据整合 + 投注单生成主控
# 整合11个数据源：api-sports / sporttery / TheOddsAPI / RapidAPI /
#                 SofaScore / Flashscore / Soccerway / OddsPortal /
#                 BetExplorer / Pinnacle / Bet365
# 功能：
#   1. 调度所有爬虫（按优先级并发）
#   2. 跨源比赛匹配（模糊队名对齐）
#   3. 多源赔率共识计算（夏普权重）
#   4. 命中评分（数据源覆盖度 × 赔率一致性 × 模型置信度）
#   5. 生成投注推荐单写入 hit_recommendations 表

import sys, time, json, logging, re, hashlib
from datetime import datetime, timedelta, timezone
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 内存bug修复(2026-08-08)：predict_football.py用importlib.import_module("00_命中系统")
# 拿本文件的_fotmob_lambdas()/preload_xg_caches()（避免和本文件局部import
# predict_football.py形成模块级循环导入）。但本文件按脚本方式启动时注册在
# sys.modules["__main__"]下，不叫"00_命中系统"，导致importlib那次调用找不到
# 已加载的模块、把7800+行的本文件（含SQLAlchemy engine+xG缓存）当成全新模块
# 重新执行一遍——引擎、_MPS_CACHE/_US_CACHE/_FM_CACHE等全套缓存都被重复建了一份
# （stage2.5的predict_football建一份，stage3自己首次调用preload_xg_caches()时
# 因为是不同模块实例、_CACHES_LOADED还是False又建一份），实测是连续后台跑被系统
# 强制杀掉（内存不足）的主因之一。这里把当前__main__模块也注册成"00_命中系统"
# 别名，之后predict_football.py的importlib.import_module("00_命中系统")会直接
# 命中sys.modules缓存返回同一个模块对象，不会重复执行/重复建缓存。predict_football.py
# 被独立运行（非本文件调用）时__name__不是"__main__"，这行不生效，行为不变。
if __name__ == "__main__":
    sys.modules.setdefault("00_命中系统", sys.modules["__main__"])
from typing import Optional
from difflib import SequenceMatcher
from sqlalchemy import create_engine, text

from config import (DB_ENGINE_URL, KELLY_MAX_RATIO, MIN_RECOMMEND_ODDS,
                    MAX_RECOMMEND_ODDS,
                    CORRECT_SCORE_VALIDATION_MIN_SAMPLES, CORRECT_SCORE_VALIDATION_MIN_ROI,
                    UNDER_VALIDATION_MIN_SAMPLES, UNDER_VALIDATION_MIN_ROI,
                    MONEYLINE_VALIDATION_MIN_SAMPLES, MONEYLINE_VALIDATION_MIN_ROI,
                    BASKETBALL_MONEYLINE_FADE_MIN_ODDS,
                    LSTM_VALIDATION_MIN_SAMPLES, LSTM_VALIDATION_MIN_ROI,
                    TEAM_TOTAL_VALIDATION_MIN_SAMPLES, TEAM_TOTAL_VALIDATION_MIN_ROI,
                    FOTMOB_VALIDATION_MIN_SAMPLES, FOTMOB_VALIDATION_MIN_ROI,
                    CORNER_VALIDATION_MIN_SAMPLES, CORNER_VALIDATION_MIN_ROI,
                    VALIDATION_RECENT_MAX_AGE_DAYS,
                    is_shadow_write_stopped,
                    CORRECT_SCORE_MODEL_WEIGHT,
                    MARKET_BIAS, get_market_bias, LEAGUE_TIER_BOOST,
                    HIT_SCORE_GLOBAL_THRESHOLD, MAX_RECS_PER_MATCH,
                    MAX_DAILY_RECOMMENDATIONS, BANKROLL,
                    SINGLE_BET_PCT, SINGLE_BET_MAX,
                    DYNAMIC_KELLY_SCALE,
                    PARLAY_CONFIG, PARLAY_ELIGIBLE_MARKETS,
                    DAILY_LOSS_LIMIT_PCT, STOP_LOSS_STREAK, HALF_BANKROLL,
                    RECOMMEND_MIN_TIER, LEAGUE_BLACKLIST_KEYWORDS,
                    LEAGUE_CN_MAP, TEAM_CN_MAP,
                    POISSON_HOME_ADV_XG, POISSON_HOME_ADV_SOT,
                    KELLY_FRACTION, BBALL_SIGMA_BREF, BBALL_SIGMA_PACE,
                    NBA_HOME_ADV_PTS,
                    FUSION_W_BOOK, FUSION_W_POISSON, FUSION_W_ELO,
                    UNDER_MIN_HANDICAP, UNDER_MAX_DAILY,
                    HIT_SCORE_V2_THRESHOLD, SLIP_OUTPUT_DIR,
                    is_live_betting, slip_output_dir, PAPER_WATERMARK,
                    LEAGUE_WC_BOOST_KEYWORDS, LEAGUE_TIER_LOW_BBALL_KEYWORDS,
                    LEAGUE_TIER1_KEYWORDS, LEAGUE_TIER2_KEYWORDS,
                    LEAGUE_TIER1_QUALIFIED, LEAGUE_TIER2_QUALIFIED,
                    BBALL_TOTAL_CAP, BBALL_TOTAL_CAP_NZ_NBL, BBALL_TOTAL_CAP_DEFAULT,
                    CONSENSUS_MIN_SOURCES)
from db_utils import exec_ddl
from promotion_gate import check_promotion_gate  # FIX-003 转正闸门（预注册+季度额度）

import math as _math
import importlib.util as _iutil
import os as _os

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# 同一底层数据源的别名映射（值 = 规范化名称），用于来源计数去重
# theodds 是 15_pinnacle_oddsportal_scraper 的旧命名，实际爬的也是 Pinnacle Guest API
# 注意：theodds_api（api.the-odds-api.com 聚合 Bet365/Betfair/Unibet）是独立数据源，不去重
SOURCE_CANONICAL = {
    "theodds": "pinnacle",
}

engine = create_engine(
    DB_ENGINE_URL,
    connect_args={"timeout": 60},
    pool_pre_ping=True,
)

# 启用 WAL 模式，允许并发读写
from sqlalchemy import event as _sa_event
@_sa_event.listens_for(engine, "connect")
def _set_wal(dbapi_conn, _):
    dbapi_conn.execute("PRAGMA journal_mode=WAL")
    dbapi_conn.execute("PRAGMA synchronous=NORMAL")

# ─── xG 批量预加载缓存（stage3 提速 30-50x）────────────────────────────────────
_CACHES_LOADED  = False
_MPS_CACHE: dict = {}   # (home_std, away_std) → {sel: prob}
_US_CACHE:  dict = {}   # (us_league, norm6_team, side) → [(xgf, xga)]
_FB_CACHE:  dict = {}   # (fb_league, norm6_team, side) → [(xgf, xga)] — 已废弃，见下方FBref说明
_FM_CACHE:  dict = {}   # (fm_league, norm6_team, side) → [(xgf, xga)]  FotMob（fbref schedule页xG字段
                        # 已失效后的替代源，见43_fotmob_match_data_scraper.py）
_FD_CACHE:  dict = {}   # (fd_league, norm6_team, side) → [sot]
_FD_CONV:   dict = {}   # fd_league → conv_rate
_FM_SOT_CACHE: dict = {}  # (fm_league, norm6_team, side) → [shots_on_target]  FotMob射正模型
_FM_SOT_CONV:  dict = {}  # fm_league → conv_rate（进球/射正，同_FD_CONV口径）
_FXG_CACHE: dict = {}   # norm6_team → (xg_off, xg_def)
_NAT_ELO:   dict = {}   # norm6_team → elo
_NAT_XG:    dict = {}   # norm6_team → (avg_xg, avg_xga)
_TM_CACHE:  dict = {}   # norm6_team → total_value_eur（6/4字符截断，跨联赛globally共用，见_TM_CACHE_FULL的说明）
_TM_CACHE_FULL: dict = {}  # 完整队名(不截断) → total_value_eur，查身价时优先用这个避免撞车
_LSTM_CACHE: dict = {}  # norm6/7_team → state_score（04_1_LSTM_时序状态模型.py写入的team_lstm_state）


def _norm6(name: str, n: int = 6) -> str:
    """标准化队名为小写字母数字，取前n位用于快速索引"""
    return re.sub(r'[^a-z0-9]', '', (name or '').lower())[:n]


def _cache_lookup(cache: dict, league: str, team: str, side: str,
                  chars_list=(6, 4)) -> list:
    """
    在分层缓存 (league, norm_team, side) 中模糊查找队名，
    返回匹配到的数据列表；未命中返回空列表
    """
    for n in chars_list:
        k = (league, _norm6(team, n), side)
        if k in cache:
            return cache[k]
    # 最后尝试 SequenceMatcher 模糊匹配（仅限同联赛）
    best_val, best_score = [], 0.0
    prefix = f"{league}||"
    team_n = _norm6(team, 6)
    for key, val in cache.items():
        if key[0] != league or key[2] != side:
            continue
        sc = SequenceMatcher(None, team_n, key[1]).ratio()
        if sc > best_score and sc > 0.55:
            best_score, best_val = sc, val
    return best_val


def _fxg_lookup(team: str) -> tuple:
    """查 football_xg_stats 缓存，返回 (xg_off, xg_def) 或 (None, None)"""
    for n in (6, 4):
        k = _norm6(team, n)
        if k in _FXG_CACHE:
            return _FXG_CACHE[k]
    # 模糊匹配
    best, best_sc = (None, None), 0.0
    team_n = _norm6(team, 6)
    for k, v in _FXG_CACHE.items():
        sc = SequenceMatcher(None, team_n, k).ratio()
        if sc > best_sc and sc > 0.55:
            best_sc, best = sc, v
    return best


def _nat_lookup(cache: dict, team: str) -> object:
    """查国家队缓存（ELO 或 xG），返回值或 None"""
    for n in (7, 6, 5, 4):
        k = _norm6(team, n)
        if k in cache:
            return cache[k]
    return None


# LSTM(EMA+AR1，04_1_LSTM_时序状态模型.py) 主胜概率 logistic 校准系数：
# 2026-07-16用football_matches/basketball_matches真实历史赛果做严格walk-forward回测
# （每场比赛只用该场之前的数据，无未来信息）拟合，控制"累计胜率差"这个朴素基线后
# state_diff仍能多解释净胜分方差(足球R^2+0.0102/篮球+0.0157)，是真实增量信号。
# 但从未在实盘结算中验证过，暂不进主流程p_fusion，先只用于影子观察单
# （shadow_recommendations, shadow_type='lstm_moneyline'/'lstm_1x2'），
# 达标(LSTM_VALIDATION_MIN_SAMPLES/MIN_ROI，见config.py)后再考虑转正。
LSTM_LOGIT_FOOTBALL   = (-0.2282, 1.5372)   # logit(P_home_win) = a + b * state_diff
LSTM_LOGIT_BASKETBALL = (0.2028, 0.3745)

# 让球(spread)用：margin ~ Normal(a + b*state_diff, sigma)，同一批2026-07-16回测数据
# 上对 margin 做OLS拟合+残差标准差，用正态分布算"净胜分覆盖某条盘口线"的概率，
# 比直接复用主胜/负 logistic 更合理（让球关心的是覆盖幅度，不是简单输赢）。
LSTM_MARGIN_FOOTBALL   = (0.3188, 2.2767, 1.6881)    # (a, b, sigma)
LSTM_MARGIN_BASKETBALL = (1.8166, 3.1518, 14.4015)


def _lstm_home_win_prob(home: str, away: str, sport_code: str) -> float | None:
    """查_LSTM_CACHE取双方state_score差，套logistic校准返回主胜概率；缺数据返回None"""
    if not _CACHES_LOADED or not _LSTM_CACHE:
        return None
    sh = _nat_lookup(_LSTM_CACHE, home)
    sa = _nat_lookup(_LSTM_CACHE, away)
    if sh is None or sa is None:
        return None
    diff = sh - sa
    a, b = (LSTM_LOGIT_BASKETBALL if (sport_code or "").lower() in ("basketball", "basket")
            else LSTM_LOGIT_FOOTBALL)
    z = a + b * diff
    try:
        return float(1.0 / (1.0 + _math.exp(-z)))
    except OverflowError:
        return 0.01 if z < 0 else 0.99


def _lstm_spread_cover_prob(home: str, away: str, sport_code: str,
                            outcome: str, handicap: float | None) -> float | None:
    """用 margin ~ Normal(a+b*state_diff, sigma) 算让球覆盖概率，跟21_auto_settle.py
    的判负逻辑对齐：outcome='home'赢盘条件是 margin > -handicap，'away'是 margin < handicap。
    缺state数据或handicap为空时返回None。"""
    if not _CACHES_LOADED or not _LSTM_CACHE:
        return None
    sh = _nat_lookup(_LSTM_CACHE, home)
    sa = _nat_lookup(_LSTM_CACHE, away)
    if sh is None or sa is None or handicap is None:
        return None
    diff = sh - sa
    a, b, sigma = (LSTM_MARGIN_BASKETBALL if (sport_code or "").lower() in ("basketball", "basket")
                   else LSTM_MARGIN_FOOTBALL)
    mu = a + b * diff
    if sigma <= 0:
        return None

    def _norm_cdf(z: float) -> float:
        return 0.5 * (1.0 + _math.erf(z / (2 ** 0.5)))

    if outcome == "home":
        # P(margin > -handicap)
        return float(1.0 - _norm_cdf((-handicap - mu) / sigma))
    elif outcome == "away":
        # P(margin < handicap)
        return float(_norm_cdf((handicap - mu) / sigma))
    return None


def preload_xg_caches():
    """
    一次性批量加载所有 xG/ELO 数据到内存缓存。
    在 generate_recommendations() 开始时调用，把 stage3 的
    per-match DB 查询替换为纯内存查找，预计节省 60-80 分钟。
    """
    global _CACHES_LOADED, _MPS_CACHE, _US_CACHE, _FB_CACHE, _FM_CACHE, _FD_CACHE
    global _FD_CONV, _FM_SOT_CACHE, _FM_SOT_CONV, _FXG_CACHE, _NAT_ELO, _NAT_XG
    global _TM_CACHE, _TM_CACHE_FULL, _LSTM_CACHE
    if _CACHES_LOADED:
        return
    t0 = time.time()
    try:
        with engine.connect() as conn:
            # 1. market_prediction_snapshot（ELO 预测）
            rows = conn.execute(text("""
                SELECT home_team_name_std, away_team_name_std, selection_name, model_prob
                FROM market_prediction_snapshot
                WHERE run_tag IN ('poisson_elo_v1','bball_elo_v1','poisson_elo_v2')
            """)).fetchall()
            for h, a, sel, prob in rows:
                _MPS_CACHE.setdefault((h, a), {})[sel] = float(prob)
            log.info(f"    MPS: {len(_MPS_CACHE)} 对赛")

            # 2. Understat xG
            rows = conn.execute(text("""
                SELECT league, home_team, away_team, home_xg, away_xg
                FROM understat_matches WHERE is_result=1 AND home_xg IS NOT NULL
                ORDER BY match_datetime DESC
            """)).fetchall()
            for lg, h, a, hxg, axg in rows:
                _US_CACHE.setdefault((lg, _norm6(h), 'home'), []).append((float(hxg), float(axg)))
                _US_CACHE.setdefault((lg, _norm6(a), 'away'), []).append((float(axg), float(hxg)))
            log.info(f"    Understat: {len(_US_CACHE)} keys")

            # 3. FBref xG — 已废弃(2026-07-20)：fbref把schedule页xG列撤掉了，
            # home_xg历史6794行全部NULL，22_fbref_scraper.py已从调度停用，
            # 这条查询永远返回0行，保留只是不改这段历史注释，真正信号见下面FotMob。
            rows = conn.execute(text("""
                SELECT league_name, home_team, away_team, home_xg, away_xg
                FROM fbref_match_stats WHERE home_xg IS NOT NULL
                ORDER BY match_date DESC
            """)).fetchall()
            for lg, h, a, hxg, axg in rows:
                _FB_CACHE.setdefault((lg, _norm6(h), 'home'), []).append((float(hxg), float(axg)))
                _FB_CACHE.setdefault((lg, _norm6(a), 'away'), []).append((float(axg), float(hxg)))
            log.info(f"    FBref(已废弃): {len(_FB_CACHE)} keys")

            # 3.5 FotMob xG（fbref schedule页xG失效后的替代源，见43_fotmob_match_data_scraper.py，
            # 覆盖五大联赛之外50+联赛/国际赛事，实测逐一验证过shotmap.expectedGoals真实存在）
            rows = conn.execute(text("""
                SELECT league_name, home_team, away_team, home_xg, away_xg
                FROM fotmob_matches WHERE home_xg IS NOT NULL
                ORDER BY match_date DESC
            """)).fetchall()
            for lg, h, a, hxg, axg in rows:
                _FM_CACHE.setdefault((lg, _norm6(h), 'home'), []).append((float(hxg), float(axg)))
                _FM_CACHE.setdefault((lg, _norm6(a), 'away'), []).append((float(axg), float(hxg)))
            log.info(f"    FotMob: {len(_FM_CACHE)} keys")

            # 4. football-data.co.uk 射正
            rows = conn.execute(text("""
                SELECT league_name, home_team, away_team,
                       home_shots_target, away_shots_target
                FROM fd_matches WHERE home_shots_target IS NOT NULL
                ORDER BY match_date DESC
            """)).fetchall()
            for lg, h, a, hs, as_ in rows:
                _FD_CACHE.setdefault((lg, _norm6(h), 'home'), []).append(float(hs))
                _FD_CACHE.setdefault((lg, _norm6(a), 'away'), []).append(float(as_))
            conv_rows = conn.execute(text("""
                SELECT league_name,
                       AVG(fthg+ftag)/NULLIF(AVG(home_shots_target+away_shots_target),0)
                FROM fd_matches WHERE home_shots_target IS NOT NULL
                GROUP BY league_name
            """)).fetchall()
            for lg, cv in conv_rows:
                if cv:
                    _FD_CONV[lg] = float(cv)
            log.info(f"    FD: {len(_FD_CACHE)} keys, {len(_FD_CONV)} leagues")

            # 4.6 FotMob 射正模型（团队逐场统计，见43_fotmob_match_data_scraper.py；
            # 跟football-data.co.uk射正模型(来源5)是同一套思路，只是覆盖联赛不同、互相独立）
            rows = conn.execute(text("""
                SELECT m.league_name, m.home_team, m.away_team,
                       hs.shots_on_target, as_.shots_on_target
                FROM fotmob_matches m
                JOIN fotmob_match_team_stats hs ON hs.match_id=m.match_id AND hs.side='home'
                JOIN fotmob_match_team_stats as_ ON as_.match_id=m.match_id AND as_.side='away'
                WHERE hs.shots_on_target IS NOT NULL AND as_.shots_on_target IS NOT NULL
                ORDER BY m.match_date DESC
            """)).fetchall()
            for lg, h, a, hsot, asot in rows:
                _FM_SOT_CACHE.setdefault((lg, _norm6(h), 'home'), []).append(float(hsot))
                _FM_SOT_CACHE.setdefault((lg, _norm6(a), 'away'), []).append(float(asot))
            conv_rows = conn.execute(text("""
                SELECT m.league_name,
                       AVG(m.home_score+m.away_score)/NULLIF(AVG(hs.shots_on_target+as_.shots_on_target),0)
                FROM fotmob_matches m
                JOIN fotmob_match_team_stats hs ON hs.match_id=m.match_id AND hs.side='home'
                JOIN fotmob_match_team_stats as_ ON as_.match_id=m.match_id AND as_.side='away'
                WHERE hs.shots_on_target IS NOT NULL AND as_.shots_on_target IS NOT NULL
                GROUP BY m.league_name
            """)).fetchall()
            for lg, cv in conv_rows:
                if cv:
                    _FM_SOT_CONV[lg] = float(cv)
            log.info(f"    FotMob射正: {len(_FM_SOT_CACHE)} keys, {len(_FM_SOT_CONV)} leagues")

            # 5. football_xg_stats（三源融合：understat/fbref/sofascore 真实xG）
            # 2026-07-29修复：source='historical'是进失球均值兜底，不是真实xG，
            # 混进来会让"推荐单数据支撑规则"要求排除的兜底信号看起来像真实模型
            # 输出——之前只有篮球侧修过这个陷阱，足球侧一直没查，这次审查确认
            # 确实存在，按规则直接排除，不降权。
            rows = conn.execute(text("""
                SELECT team, xg_off, xg_def FROM football_xg_stats
                WHERE xg_off IS NOT NULL AND source != 'historical'
                ORDER BY rowid DESC
            """)).fetchall()
            for team, off, deff in rows:
                k = _norm6(team)
                if k and k not in _FXG_CACHE:
                    _FXG_CACHE[k] = (float(off), float(deff))
            log.info(f"    FXG: {len(_FXG_CACHE)} teams")

            # 6. 国家队 ELO
            rows = conn.execute(text("""
                SELECT team_name, elo_rating FROM national_team_elo
                ORDER BY fetch_date DESC
            """)).fetchall()
            for team, elo in rows:
                k = _norm6(team, 7)
                if k and k not in _NAT_ELO:
                    _NAT_ELO[k] = float(elo)

            # 7. StatsBomb 国家队 xG
            try:
                rows = conn.execute(text("""
                    SELECT team_name, avg_xg, avg_xga
                    FROM statsbomb_national_xg_teams
                """)).fetchall()
                for team, axg, axga in rows:
                    k = _norm6(team, 7)
                    if k and k not in _NAT_XG:
                        _NAT_XG[k] = (float(axg), float(axga))
            except Exception:
                pass
            log.info(f"    NatELO: {len(_NAT_ELO)}  NatXG: {len(_NAT_XG)}")

            # 8. Transfermarkt 身价
            rows = conn.execute(text("""
                SELECT team, total_value_eur FROM transfermarkt_squad_values
                WHERE total_value_eur IS NOT NULL
                ORDER BY season DESC
            """)).fetchall()
            for team, val in rows:
                # Bug修复：_TM_CACHE 只存6字符截断key，跨联赛全球共用同一个命名空间，
                # "Arsenal"(英格兰)和"Arsenal de Sarandi"(阿根廷)这类不同国家但截断后
                # 前6字符相同的队会互相顶替、静默用错身价数据。_TM_CACHE_FULL 存完整
                # 标准化队名(不截断)，查询时优先用它，基本不会有两支队全名完全一样却是
                # 不同队的情况，只有查不到完整名才退回截断版本兜底。
                kf = _norm6(team, 999)
                if kf and kf not in _TM_CACHE_FULL:
                    _TM_CACHE_FULL[kf] = float(val)
                k = _norm6(team)
                if k and k not in _TM_CACHE:
                    _TM_CACHE[k] = float(val)
            log.info(f"    TM: {len(_TM_CACHE)} teams")

            # 9. LSTM(EMA+AR1) 时序状态分——2026-07-16回测验证：控制累计胜率差后
            # 仍能对净胜分多解释8-9%的R²（足球+0.0102/篮球+0.0157），是真实增量信号，
            # 不是04_1文件名挂名的PyTorch LSTM，而是纯NumPy EMA+AR1近似实现，
            # 详见04_1_LSTM_时序状态模型.py
            try:
                rows = conn.execute(text(
                    "SELECT team, state_score FROM team_lstm_state"
                )).fetchall()
                for team, score in rows:
                    k = _norm6(team, 7)
                    if k and k not in _LSTM_CACHE:
                        _LSTM_CACHE[k] = float(score)
                log.info(f"    LSTM状态: {len(_LSTM_CACHE)} teams")
            except Exception:
                pass

        _CACHES_LOADED = True
        log.info(f"  ⚡ xG缓存预加载完成  耗时 {time.time()-t0:.1f}s")
    except Exception as e:
        log.warning(f"  ⚠ 缓存预加载失败（将回退DB查询）: {e}")


# ─── 足球1x2平局：等渗回归校准 ──────────────────────────────────────────────
# 背景：_backtest_draw_calibration_fix.py 用训练/测试集分开验证过，融合概率
# (book50%+poisson50%)在低概率区间系统性高估平局(见0708回测)，等渗回归校准后
# 样本外ROI从+2.8%提升到+4.7%。_fit_draw_calibration.py 是拟合器，本节是加载+应用。
_DRAW_CALIB_BP: list | None = None   # 分段起点(x)
_DRAW_CALIB_VL: list | None = None   # 对应校准值(y)
DRAW_CALIB_MAX_AGE_DAYS = 30  # 曲线超过30天未更新自动重新拟合，足球赛季节奏下每月更新足够


def _ensure_draw_calibration():
    """检查校准曲线是否过期，过期/缺失则自动重新拟合，并加载到内存。
    每次 generate_recommendations() 开始时调用一次，全程只做一次DB查询+必要时才重新拟合，
    不需要人工维护——这就是"定时维护"的落地方式：靠数据自身的新鲜度触发，而不是外部cron。"""
    global _DRAW_CALIB_BP, _DRAW_CALIB_VL
    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT fit_date, breakpoints_json, values_json, train_samples
                FROM draw_calibration_curve ORDER BY id DESC LIMIT 1
            """)).fetchone()
    except Exception:
        row = None  # 表还不存在（首次运行）

    need_refit = row is None
    if row is not None:
        try:
            fit_dt = datetime.strptime(row[0], "%Y-%m-%d")
            need_refit = (datetime.now() - fit_dt).days > DRAW_CALIB_MAX_AGE_DAYS
        except Exception:
            need_refit = True

    if need_refit:
        try:
            log.info("  🔧 平局校准曲线过期/缺失，自动重新拟合...")
            import _fit_draw_calibration as _fdc
            result = _fdc.fit_and_save()
            if result.get("ok"):
                log.info(f"    ✅ 重新拟合完成: {result['train_samples']}样本, "
                         f"{result['segments']}段, 耗时{result['elapsed']}s")
                with engine.connect() as conn:
                    row = conn.execute(text("""
                        SELECT fit_date, breakpoints_json, values_json, train_samples
                        FROM draw_calibration_curve ORDER BY id DESC LIMIT 1
                    """)).fetchone()
            else:
                log.warning(f"    ⚠ 重新拟合跳过: {result.get('reason')}（沿用旧曲线，若无旧曲线则本次不校准）")
        except Exception as e:
            log.warning(f"  ⚠ 平局校准曲线拟合失败: {e}（本次不校准，直接用原始融合概率）")

    if row is not None:
        try:
            _DRAW_CALIB_BP = json.loads(row[1])
            _DRAW_CALIB_VL = json.loads(row[2])
            log.info(f"  📐 平局校准曲线已加载: {row[0]}拟合, {row[3]}样本, {len(_DRAW_CALIB_BP)}段")
        except Exception:
            _DRAW_CALIB_BP = _DRAW_CALIB_VL = None


def _apply_draw_calibration(raw_prob: float) -> float:
    """把原始融合概率映射到等渗回归校准后的概率。曲线缺失时原样返回（不校准，不阻塞流程）。"""
    if not _DRAW_CALIB_BP or not _DRAW_CALIB_VL:
        return raw_prob
    import bisect as _bisect
    idx = _bisect.bisect_right(_DRAW_CALIB_BP, raw_prob) - 1
    idx = max(0, min(idx, len(_DRAW_CALIB_VL) - 1))
    return _DRAW_CALIB_VL[idx]


# ─── 公共 Poisson PMF & 概率计算 ─────────────────────────────────────────────
def _poisson_probs(lam_h: float, lam_a: float, n: int = 9) -> dict:
    """返回 {home, draw, away, over, under} 泊松概率（n×n 得分矩阵）"""
    hw = dr = aw = over25 = under25 = 0.0
    for i in range(n):
        pi = _math.exp(-lam_h) * (lam_h ** i) / _math.factorial(i)
        for j in range(n):
            pj = _math.exp(-lam_a) * (lam_a ** j) / _math.factorial(j)
            p = pi * pj
            if   i > j:  hw     += p
            elif i == j: dr     += p
            else:        aw     += p
            if i + j > 2: over25 += p
            else:          under25 += p
    tot = hw + dr + aw
    if tot < 0.01:
        return {}
    # Bug修复：OU分母应与1x2分母一致，用 tot 而不是 (over+under)
    # over25 + under25 ≈ tot 但因截断误差略小，直接用会导致 over+under 略>1
    return {
        'home':  round(hw / tot, 4),
        'draw':  round(dr / tot, 4),
        'away':  round(aw / tot, 4),
        'over':  round(over25 / tot, 4),
        'under': round(under25 / tot, 4),
    }


def _poisson_top_score(lam_h: float, lam_a: float, n: int = 9) -> str:
    """返回泊松模型最可能比分，格式 'H-A'"""
    best_p, best_score = 0.0, "1-1"
    for i in range(n):
        pi = _math.exp(-lam_h) * (lam_h ** i) / _math.factorial(i)
        for j in range(n):
            pj = _math.exp(-lam_a) * (lam_a ** j) / _math.factorial(j)
            p = pi * pj
            if p > best_p:
                best_p = p
                best_score = f"{i}-{j}"
    return best_score


# ─── 市场/结果/联赛中文映射（模块级常量） ────────────────────────────────────
_MARKET_ZH = {
    "moneyline": "独赢", "spread": "让球", "total": "大小球",
    "team_total": "球队大小", "team_total_home": "主队大小", "team_total_away": "客队大小",
    "draw_no_bet": "平局无效",
    "corner_ou": "角球大小", "corner_hdp": "角球让球",
    "correct_score": "比分",
    "ht_ft": "半全场",
}
_OUTCOME_ZH = {
    "home": "主胜", "away": "客胜", "draw": "平局",
    "over": "大球", "under": "小球",
    # 半全场(ht_ft)9选1组合——2026-08-31补充，此前_OUTCOME_ZH没有这9个key，
    # 半全场影子观察单"方向"列一直显示原始英文"home-home"这类值，见.get(x, x)
    # 兜底逻辑找不到key时原样返回。
    "home-home": "半场主胜+全场主胜", "home-draw": "半场主胜+全场平局", "home-away": "半场主胜+全场客胜",
    "draw-home": "半场平局+全场主胜", "draw-draw": "半场平局+全场平局", "draw-away": "半场平局+全场客胜",
    "away-home": "半场客胜+全场主胜", "away-draw": "半场客胜+全场平局", "away-away": "半场客胜+全场客胜",
}
_LEAGUE_ZH = [
    ("FIFA - World Cup",          "FIFA世界杯"),
    ("UEFA - Champions",          "UEFA欧冠"),
    ("UEFA - Europa",             "UEFA欧联"),
    ("England - Premier",         "英格兰超级联赛"),
    ("England - Championship",    "英格兰冠军联赛"),
    ("England - League 1",        "英格兰甲级联赛"),
    ("England - League 2",        "英格兰乙级联赛"),
    ("England - Southern Premier League", "英格兰南部超级联赛"),
    ("Spain - La Liga",           "西班牙甲级"),
    ("Spain - Segunda",           "西班牙乙级"),
    ("Spain - Primera",           "西班牙丙级"),
    ("Germany - Bundesliga 2",    "德国乙级"),
    ("Germany - Bundesliga",      "德国甲级"),
    ("Germany - Pro A",           "德国职业篮球甲级"),
    ("Germany - BBL",             "德国篮球联赛"),
    ("Italy - Serie A",           "意大利甲级"),
    ("Italy - Serie B",           "意大利乙级"),
    ("Italy - Serie B Nazionale", "意大利篮球乙级"),
    ("Italy - Serie B Old",       "意大利篮球乙级"),
    ("Italy - Lega A",            "意大利篮球甲级"),
    ("Italy - Lega Due",          "意大利篮球乙级"),
    ("France - Ligue 1",          "法国甲级"),
    ("France - Ligue 2",          "法国乙级"),
    ("France - LNB",              "法国篮球甲级"),
    ("Netherlands - Eredivisie",  "荷兰甲级"),
    ("Portugal - Primeira",       "葡萄牙超级"),
    ("Portugal - Proliga",        "葡萄牙篮球乙级"),
    ("Portugal - Liga Portuguesa de Basquet", "葡萄牙篮球甲级"),
    ("Portugal - LPB",            "葡萄牙篮球甲级"),
    ("Portugal - Campeonato",     "葡萄牙锦标"),
    ("Turkey - Super",            "土耳其超级"),
    ("Russia - Premier",          "俄罗斯超级"),
    ("Russia - VTB",              "俄罗斯VTB联赛"),
    ("China - Super League",      "中国超级联赛"),
    ("China - CBA",               "中国男篮CBA"),
    ("Japan - J League",          "日本J联赛"),
    ("Japan - J1",                "日本J1联赛"),
    ("Korea Republic - K League", "韩国K联赛"),
    # 2026-09-01新增：更具体的关键词必须排在("USA - MLS", ...)前面——substring匹配
    # 按列表顺序取第一个命中，"USA - MLS"本身就是"USA - MLS Next Pro League"的子串，
    # 顺序反了会把预备队/次级联赛(MLS Next Pro)误译成"美国职业足球大联盟"(真正的MLS)。
    ("USA - MLS Next Pro",        "美国职业大联盟次级联赛"),
    ("USA - MLS",                 "美国职业足球大联盟"),
    ("USA - National Women",      "美国女子职业足球"),
    ("USA - USL Championship",    "美国USL冠军联赛"),
    ("USA - USL League",          "美国USL联赛"),
    ("Brazil - Serie A",          "巴西甲级"),
    ("Brazil - Serie B",          "巴西乙级"),
    ("Brazil - NBB",              "巴西篮球联赛"),
    ("Argentina - Primera",       "阿根廷甲级"),
    ("Argentina - Liga",          "阿根廷职业联赛"),
    ("Argentina - Cup",           "阿根廷杯赛"),
    ("Australia - NBL",           "澳大利亚篮球联赛"),
    ("Australia - NBL1",          "澳大利亚篮球次级"),
    ("New Zealand - NBL",         "新西兰篮球联赛"),
    ("Puerto Rico - Superior",    "波多黎各篮球联赛"),
    ("Greece - Basket",           "希腊篮球甲级"),
    ("Israel - Super",            "以色列篮球超级"),
    ("Lithuania - LKL",           "立陶宛篮球联赛"),
    ("Poland - Basket",           "波兰篮球联赛"),
    ("Serbia - Super",            "塞尔维亚篮球超级"),
    ("Europe - Euroleague",       "欧洲冠军联赛"),
    ("Europe - ABA",              "亚得里亚海联赛"),
    ("Europe - VTB",              "欧洲VTB联赛"),
    ("Europe - BNXT",             "欧洲BNXT联赛"),
    ("Africa - BAL",              "非洲篮球联赛"),
    ("Lebanon",                   "黎巴嫩"),
    ("Norway - Eliteserien",      "挪威超级"),
    ("Sweden - Allsvenskan",      "瑞典超级"),
    ("Denmark - Superliga",       "丹麦超级"),
    ("Scotland - Premiership",    "苏格兰超级"),
    ("Belgium - Pro League",      "比利时甲级"),
    ("Jupiler Pro League",        "比利时甲级"),
    ("Ireland - Premier",         "爱尔兰超级"),
    ("Ireland - Division",        "爱尔兰乙级"),
    ("Uruguay - Primera",         "乌拉圭甲级"),
    ("Chile - Primera",           "智利甲级"),
    ("Colombia",                  "哥伦比亚"),
    ("Mexico",                    "墨西哥"),
    ("Egypt - Premier",           "埃及超级"),
    ("Austria - Bundesliga",      "奥地利甲级"),
    ("Saudi Arabia - Pro League", "沙特职业联赛"),
    ("Iceland - Premier",         "冰岛超级联赛"),
    ("Brazil - Cup",              "巴西杯"),
    ("China - FA Cup",            "中国足协杯"),
    ("Ecuador - Serie A",         "厄瓜多尔甲级"),
    ("Switzerland - Challenge",   "瑞士挑战联赛"),
    ("Switzerland - Super",       "瑞士超级联赛"),
    ("England - Northern Premier League", "英格兰北方超级联赛"),
    ("Ireland - Leinster",        "爱尔兰伦斯特联赛"),
    ("Russia - Cup",              "俄罗斯杯"),
    ("World - Club Friendlies",   "世界俱乐部热身赛"),
    ("Italy - Cup",               "意大利杯"),
    ("Romania - Liga",            "罗马尼亚联赛"),
    ("Bulgaria - First",          "保加利亚甲级"),
    ("International - Friend",    "国际友谊赛"),
    ("WNBA",                      "WNBA女子职业篮球"),
    ("NBA",                       "NBA男子职业篮球"),
]

# football-data.co.uk 历史赔率补充查询（静态 SQL 模板，模块级常量）
_FD_EXTRA_QUERIES = [
    ("fd_b365", "SELECT :uid,'fd_b365','moneyline_home',b365h,NULL FROM fd_matches WHERE home_team LIKE :ht AND away_team LIKE :at AND b365h IS NOT NULL ORDER BY match_date DESC LIMIT 1"),
    ("fd_b365", "SELECT :uid,'fd_b365','moneyline_draw',b365d,NULL FROM fd_matches WHERE home_team LIKE :ht AND away_team LIKE :at AND b365d IS NOT NULL ORDER BY match_date DESC LIMIT 1"),
    ("fd_b365", "SELECT :uid,'fd_b365','moneyline_away',b365a,NULL FROM fd_matches WHERE home_team LIKE :ht AND away_team LIKE :at AND b365a IS NOT NULL ORDER BY match_date DESC LIMIT 1"),
    ("fd_pinnacle", "SELECT :uid,'fd_pinnacle','moneyline_home',psh,NULL FROM fd_matches WHERE home_team LIKE :ht AND away_team LIKE :at AND psh IS NOT NULL ORDER BY match_date DESC LIMIT 1"),
    ("fd_pinnacle", "SELECT :uid,'fd_pinnacle','moneyline_draw',psd,NULL FROM fd_matches WHERE home_team LIKE :ht AND away_team LIKE :at AND psd IS NOT NULL ORDER BY match_date DESC LIMIT 1"),
    ("fd_pinnacle", "SELECT :uid,'fd_pinnacle','moneyline_away',psa,NULL FROM fd_matches WHERE home_team LIKE :ht AND away_team LIKE :at AND psa IS NOT NULL ORDER BY match_date DESC LIMIT 1"),
    # Bug修复：原来写的是 'totals_over'/'totals_under'（拆分后 market='totals' 复数），
    # 跟 MARKET_BIAS_FOOTBALL/BASKETBALL 的 key（单数 'total'）对不上，hit_score 被
    # 强制归零，2692条候选几乎全部静默丢弃从未参与评分。改成跟系统其余部分一致的单数。
    ("fd_b365", "SELECT :uid,'fd_b365','total_over',b365_over25,2.5 FROM fd_matches WHERE home_team LIKE :ht AND away_team LIKE :at AND b365_over25 IS NOT NULL ORDER BY match_date DESC LIMIT 1"),
    ("fd_b365", "SELECT :uid,'fd_b365','total_under',b365_under25,2.5 FROM fd_matches WHERE home_team LIKE :ht AND away_team LIKE :at AND b365_under25 IS NOT NULL ORDER BY match_date DESC LIMIT 1"),
    ("fd_wh", "SELECT :uid,'fd_wh','moneyline_home',whh,NULL FROM fd_matches WHERE home_team LIKE :ht AND away_team LIKE :at AND whh IS NOT NULL ORDER BY match_date DESC LIMIT 1"),
    ("fd_wh", "SELECT :uid,'fd_wh','moneyline_draw',whd,NULL FROM fd_matches WHERE home_team LIKE :ht AND away_team LIKE :at AND whd IS NOT NULL ORDER BY match_date DESC LIMIT 1"),
    ("fd_wh", "SELECT :uid,'fd_wh','moneyline_away',wha,NULL FROM fd_matches WHERE home_team LIKE :ht AND away_team LIKE :at AND wha IS NOT NULL ORDER BY match_date DESC LIMIT 1"),
    ("fd_iw", "SELECT :uid,'fd_iw','moneyline_home',iwh,NULL FROM fd_matches WHERE home_team LIKE :ht AND away_team LIKE :at AND iwh IS NOT NULL ORDER BY match_date DESC LIMIT 1"),
    ("fd_iw", "SELECT :uid,'fd_iw','moneyline_draw',iwd,NULL FROM fd_matches WHERE home_team LIKE :ht AND away_team LIKE :at AND iwd IS NOT NULL ORDER BY match_date DESC LIMIT 1"),
    ("fd_iw", "SELECT :uid,'fd_iw','moneyline_away',iwa,NULL FROM fd_matches WHERE home_team LIKE :ht AND away_team LIKE :at AND iwa IS NOT NULL ORDER BY match_date DESC LIMIT 1"),
]

# ─── 各数据源权重（基于历史准确度/封盘权威性） ──────────────────────────────
SOURCE_WEIGHTS = {
    "pinnacle":    1.00,   # 最锐利，权重最高
    "theodds":     1.00,   # ≡ Pinnacle（15_pinnacle_oddsportal_scraper 实际爬的是 Pinnacle Guest API）
    "bet365":      0.90,
    "betfair":     0.95,   # 交易所真实市场价，仅次于 Pinnacle
    "oddsportal":  0.85,
    "betexplorer": 0.80,
    "sofascore":   0.75,
    "flashscore":  0.70,
    "draftkings":  0.78,
    "fanduel":     0.78,
    "william_hill":0.75,
    "unibet":      0.72,
    "bovada":      0.70,
    "soccerway":   0.65,
    "sporttery":   0.60,   # 保留：SOURCE_WEIGHTS历史配置，实际链路已死(见调度列表说明)，不再产生数据
    "okooo_jingcai": 0.55, # 2026-07-29新接入：澳客网竞彩赔率，真实可用但尚未经实盘验证，权重先保守设置
    "qiety_yb":    0.80,   # 主力覆盖源：亚洲联赛全覆盖，与 Pinnacle 交叉校验效果极佳
    "fd_b365":     0.72,   # football-data.co.uk 历史 B365 赔率（历史参考）
    "fd_pinnacle": 0.78,   # football-data.co.uk 历史 Pinnacle 赔率（历史参考）
    "fd_wh":       0.72,   # football-data.co.uk 历史 William Hill 赔率
    "fd_iw":       0.68,   # football-data.co.uk 历史 Interwetten 赔率
    "theodds_api": 0.90,   # api.the-odds-api.com 聚合（Bet365+Betfair+Unibet 共识均值）
    "apisports":   0.50,
    "rapidapi":    0.45,
    "pinnacle_corner": 1.00,  # Pinnacle角球赔率（同等权威）
    "scoremer":    0.80,      # Scoremer实时角球数据
    "fd_corner":   0.65,      # football-data.co.uk 历史角球统计
}

# 命中阈值（已被 HIT_SCORE_GLOBAL_THRESHOLD 替代，此值保留兼容）
HIT_SCORE_THRESHOLD   = 0.50   # 旧全局门槛（不再使用，由 config 控制）
VALUE_BET_THRESHOLD   = 0.05   # 期望值 > 5% 才推荐
CONFIDENCE_THRESHOLD  = 0.55   # 模型预测概率 > 55%


# ─── DDL ─────────────────────────────────────────────────────────────────────
def init_tables():
    ddls = [
        """CREATE TABLE IF NOT EXISTS unified_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT UNIQUE,
            sport_code TEXT,
            league_code TEXT,
            league_name TEXT,
            home_team_std TEXT,
            away_team_std TEXT,
            kickoff_utc TEXT,
            status TEXT,
            home_score INTEGER,
            away_score INTEGER,
            home_score_ht INTEGER,
            away_score_ht INTEGER,
            source_count INTEGER DEFAULT 0,
            sources_json TEXT,
            last_updated TEXT,
            fetch_date TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS unified_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT,
            source TEXT,
            market TEXT,
            outcome TEXT,
            odds_value REAL,
            weight REAL,
            fetch_date TEXT,
            handicap REAL,
            UNIQUE(unified_id, source, market, outcome)
        )""",
        """CREATE TABLE IF NOT EXISTS consensus_odds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT,
            market TEXT,
            outcome TEXT,
            consensus_odds REAL,
            max_odds REAL,
            min_odds REAL,
            sharp_odds REAL,
            implied_prob REAL,
            source_count INTEGER,
            fetch_date TEXT,
            handicap REAL,
            UNIQUE(unified_id, market, outcome)
        )""",
        """CREATE TABLE IF NOT EXISTS hit_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT,
            sport_code TEXT,
            league_name TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            market TEXT,
            outcome TEXT,
            best_odds REAL,
            best_source TEXT,
            model_prob REAL,
            implied_prob REAL,
            value_edge REAL,
            kelly_fraction REAL,
            hit_score REAL,
            confidence TEXT,
            reason TEXT,
            handicap REAL,
            status TEXT DEFAULT 'pending',
            fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            closing_odds REAL,
            clv REAL,
            clv_status TEXT DEFAULT 'pending'
        )""",
        """CREATE TABLE IF NOT EXISTS odds_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT,
            source TEXT,
            market TEXT,
            outcome TEXT,
            odds_value REAL,
            snapshot_time TEXT,
            fetch_date TEXT
        )""",
        """CREATE INDEX IF NOT EXISTS idx_odds_snapshots_uid
            ON odds_snapshots(unified_id, market, outcome, snapshot_time)""",
        """CREATE TABLE IF NOT EXISTS scraper_run_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scraper TEXT,
            run_at TEXT,
            status TEXT,
            records_written INTEGER DEFAULT 0,
            error_msg TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS corner_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_date TEXT,
            league_name TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            market TEXT DEFAULT 'corner_total',
            direction TEXT,
            line REAL,
            odds REAL,
            p_model REAL,
            p_fusion REAL,
            edge REAL,
            kelly REAL,
            hit_score REAL,
            mu_predicted REAL,
            src TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(fetch_date, league_name, home_team, away_team, direction, line)
        )""",
        """CREATE TABLE IF NOT EXISTS under_shadow_bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT,
            sport_code TEXT,
            league_name TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            market TEXT,
            handicap REAL,
            best_odds REAL,
            model_prob REAL,
            kelly_fraction REAL,
            hit_score REAL,
            status TEXT DEFAULT 'pending',
            profit_loss REAL,
            fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(unified_id, market, handicap, fetch_date)
        )""",
        # 2026-08-02新增：全场大小球"大球"(total/over)影子观察单。排查发现total/over
        # 是CLAUDE.md标注"唯一真正在跑真钱的市场"，07-19起被_in_scope()动态验证收紧，
        # 但跟其他市场(小球有under_shadow_bets/独赢有moneyline_shadow_full/球队大小有
        # team_total_shadow_full)不同，它从未接入过任何影子追踪——验证不通过的候选
        # 直接从recommendations列表丢弃，用户完全看不到"如果没被卡掉会推荐什么"。
        # 镜像under_shadow_bets结构(同样implicit outcome='over'，不需要outcome列)。
        # 用户要求(2026-08-02)全部推荐单/观察单统一按Top7截断，跟其余几张shadow表
        # 同批处理，直接从建表起就是Top7口径，不存在"改回"的历史包袱。
        """CREATE TABLE IF NOT EXISTS over_shadow_bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT,
            sport_code TEXT,
            league_name TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            market TEXT,
            handicap REAL,
            best_odds REAL,
            model_prob REAL,
            kelly_fraction REAL,
            hit_score REAL,
            status TEXT DEFAULT 'pending',
            profit_loss REAL,
            fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(unified_id, market, handicap, fetch_date)
        )""",
        # handicap为NULL时UNIQUE约束不生效(2026-08-02同批修复的已知坑，见
        # basketball_moneyline_fade_recs同类注释)，total/over盘口线一般不为NULL但
        # 保险起见同样加COALESCE表达式唯一索引。
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_uniq_over_shadow_bets
            ON over_shadow_bets(unified_id, market, COALESCE(handicap,-99999), fetch_date)""",
        # 2026-07-22新增：球队大小(team_total)完整候选样本表，大球+小球都收集、
        # 不做每日Top10截断，供_team_total_validation_status()做转正判断用——见
        # generate_recommendations()里"球队大小(team_total)完整样本收集"那段说明。
        # 不复用under_shadow_bets：那张表UNIQUE约束没有outcome字段，同一场比赛
        # 同一天大球小球都命中会被撞掉一条，新建表规避这个问题。
        """CREATE TABLE IF NOT EXISTS team_total_shadow_full (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT,
            sport_code TEXT,
            league_name TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            market TEXT,
            outcome TEXT,
            handicap REAL,
            best_odds REAL,
            model_prob REAL,
            kelly_fraction REAL,
            hit_score REAL,
            status TEXT DEFAULT 'pending',
            profit_loss REAL,
            fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(unified_id, market, outcome, handicap, fetch_date)
        )""",
        # 2026-08-01新增：足球球队大小/小球"老逻辑"平行线——用户要求单独恢复
        # 2026-07-19"策略收窄"(_in_scope()引入)之前的准入规则(只看
        # HIT_SCORE_GLOBAL_THRESHOLD门槛+每场最多1条，没有市场类型限制、没有
        # 今天新加的显著性+近期窗口双重检验)，只对football/team_total/under这一个
        # 市场生效，跟当前(07-19+)的正式推荐单/_in_scope()逻辑完全独立、互不影响、
        # 不共用表。数据源直接读team_total_shadow_full(已经是完整无截断候选池，
        # 每天都会正常populate，不需要重新跑一遍预测)，见_generate_legacy_team_total_under()。
        """CREATE TABLE IF NOT EXISTS legacy_team_total_under_recs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT,
            sport_code TEXT,
            league_name TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            market TEXT,
            outcome TEXT,
            handicap REAL,
            best_odds REAL,
            model_prob REAL,
            kelly_fraction REAL,
            hit_score REAL,
            status TEXT DEFAULT 'pending',
            profit_loss REAL,
            fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(unified_id, market, outcome, handicap, fetch_date)
        )""",
        # handicap为NULL时SQL的UNIQUE约束不生效(NULL永不等于NULL)，同批修复见
        # basketball_moneyline_fade_recs同类注释(2026-08-02)。
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_uniq_legacy_team_total_under
            ON legacy_team_total_under_recs(unified_id, market, outcome, COALESCE(handicap,-99999), fetch_date)""",
        # 2026-08-01新增：篮球小球"反着买"转正平行线，用户要求。背景：2026-08-01
        # 审查发现"篮球小球(under)"策略本身长期显著为负，反过来买大球(over)在
        # 3次独立测量(完整无偏池n=44/p=0.005、Top7截断第1次n=50/p=0.058、Top7截断
        # 干净版n=55/p=0.057——中间一次n=45/p=0.119被证实是后台重跑循环并发改写
        # consensus_odds导致的数据污染，已剔除)里都测出单尾95%置信区间下界>0。
        # **重要说明：p值集中在0.05-0.06，严格没过常规0.05门槛；3次测量之间样本
        # 高度重叠(同一份底层数据的不同截断方式，不是3批完全独立新数据)，多重
        # 比较风险依然存在，不是确凿无疑的edge，只是这次会话里证据相对最扎实的
        # 一个候选。**
        #
        # 机制：读under_shadow_bets(sport_code='basketball')里模型原本判定为
        # "小球(under)"的候选，按每日hit_score降序取前7条(Top7截断)，把方向翻转
        # 成"大球(over)"，用对面方向consensus_odds真实赔率写入本表——这里存的已经
        # 是翻转后的最终下注方向(market='total', outcome='over')，不是原始小球候选，
        # 结算时按正常total/over规则判定，不需要额外的fade结算逻辑。
        # 见_generate_basketball_under_fade()。跟正式推荐单/_in_scope()逻辑完全
        # 独立、互不影响。
        """CREATE TABLE IF NOT EXISTS basketball_under_fade_recs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT,
            sport_code TEXT,
            league_name TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            market TEXT,
            outcome TEXT,
            handicap REAL,
            best_odds REAL,
            model_prob REAL,
            kelly_fraction REAL,
            hit_score REAL,
            status TEXT DEFAULT 'pending',
            profit_loss REAL,
            fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(unified_id, market, outcome, handicap, fetch_date)
        )""",
        # handicap为NULL时SQL的UNIQUE约束不生效(NULL永不等于NULL)，total/team_total
        # 市场部分行handicap也可能为NULL，导致同一场比赛在fetch_date内被pipeline
        # 重跑多次时INSERT OR IGNORE無法去重、产生重复行。用COALESCE把NULL归一化
        # 成哨兵值再建唯一索引修复(2026-08-02，与basketball_moneyline_fade_recs
        # 同一批修复，见下方同类注释)。
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_uniq_basketball_under_fade
            ON basketball_under_fade_recs(unified_id, market, outcome, COALESCE(handicap,-99999), fetch_date)""",
        # 2026-08-01新增：篮球独赢(旧口径shadow_recommendations桶)"反着买"转正平行线，
        # 用户要求，跟上面篮球小球反着买同一批审查。旧口径反着买两次测量：第1次
        # n=42/ROI+45.35%/p=0.034，本次(干净版)n=36/ROI+51.13%/p=0.035，方向和量级
        # 一致但同样只有2次高度重叠的测量，**不是确凿无疑的edge，证据强度比篮球
        # 小球反着买更薄弱(少一次独立测量)**。
        #
        # 机制：读shadow_recommendations(shadow_type='moneyline', sport_code='basketball')
        # 里模型原本判定的独赢方向(home/away二选一)，按每日hit_score降序取前7条，
        # 翻转成对面方向，用对面方向consensus_odds真实赔率写入本表(存的是翻转后的
        # 最终下注方向)。见_generate_basketball_moneyline_fade()。
        """CREATE TABLE IF NOT EXISTS basketball_moneyline_fade_recs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT,
            sport_code TEXT,
            league_name TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            market TEXT,
            outcome TEXT,
            handicap REAL,
            best_odds REAL,
            model_prob REAL,
            kelly_fraction REAL,
            hit_score REAL,
            status TEXT DEFAULT 'pending',
            profit_loss REAL,
            fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(unified_id, market, outcome, handicap, fetch_date)
        )""",
        # handicap为NULL时SQL的UNIQUE约束不生效(NULL永不等于NULL)，moneyline市场
        # handicap恒为NULL，导致同一场比赛在fetch_date内被pipeline重跑多次时
        # INSERT OR IGNORE無法去重、产生重复行(2026-08-02排查发现，Sagesse vs
        # Al Riyadi被写入2次)。用COALESCE把NULL归一化成哨兵值再建唯一索引修复。
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_uniq_basketball_moneyline_fade
            ON basketball_moneyline_fade_recs(unified_id, market, outcome, COALESCE(handicap,-99999), fetch_date)""",
        # 2026-07-24新增：独赢(moneyline)完整候选样本表，跟team_total_shadow_full
        # 同一套动机——shadow_recommendations里的moneyline/1x2桶也做每日Top10截断
        # (同一个sorted(...)[:10])，实测这个截断样本算出的ROI和真实进入hit_recommendations
        # 的记录方向相反(篮球主胜在截断样本里+19.7%，真实结算却是-24.9%)，不能拿来做
        # 转正判断。这张表大小球两个方向/胜平负三个结果全收集、不截断，供
        # _moneyline_validation_status()按(sport_code,outcome)分开判断用。
        """CREATE TABLE IF NOT EXISTS moneyline_shadow_full (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT,
            sport_code TEXT,
            league_name TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            market TEXT,
            outcome TEXT,
            best_odds REAL,
            model_prob REAL,
            kelly_fraction REAL,
            hit_score REAL,
            status TEXT DEFAULT 'pending',
            profit_loss REAL,
            fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(unified_id, market, outcome, fetch_date)
        )""",
        """CREATE TABLE IF NOT EXISTS football_score_predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT,
            home_team TEXT,
            away_team TEXT,
            league_name TEXT,
            kickoff_utc TEXT,
            top_score TEXT,
            lambda_home REAL,
            lambda_away REAL,
            engine TEXT,
            fetch_date TEXT,
            created_at TEXT,
            UNIQUE(unified_id, fetch_date)
        )""",
        """CREATE TABLE IF NOT EXISTS shadow_recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT,
            sport_code TEXT,
            league_name TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            shadow_type TEXT,
            market TEXT,
            outcome TEXT,
            handicap REAL,
            best_odds REAL,
            model_prob REAL,
            kelly_fraction REAL,
            hit_score REAL,
            predicted_score TEXT,
            fetch_date TEXT,
            status TEXT DEFAULT 'pending',
            profit_loss REAL,
            created_at TEXT DEFAULT (datetime('now')),
            UNIQUE(unified_id, shadow_type, market, outcome, fetch_date)
        )""",
        # 2026-08-27新增：让球盘客队+方向联赛级市场edge，用户提议+回测验证。
        # 背景见_generate_league_ah_edge()docstring——不是p_fusion模型信号，是纯
        # 市场结构性错价规律，走人工批准通道(同fade_manual)，不经算法验证门槛。
        """CREATE TABLE IF NOT EXISTS league_ah_edge_recs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unified_id TEXT,
            sport_code TEXT,
            league_name TEXT,
            home_team TEXT,
            away_team TEXT,
            kickoff_utc TEXT,
            market TEXT,
            outcome TEXT,
            handicap REAL,
            best_odds REAL,
            model_prob REAL,
            kelly_fraction REAL,
            hit_score REAL,
            status TEXT DEFAULT 'pending',
            profit_loss REAL,
            fetch_date TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(unified_id, market, outcome, handicap, fetch_date)
        )""",
    ]
    for sql in ddls:
        exec_ddl(engine, sql)

    # 存量表补列迁移（新增列若已存在则静默忽略报错）
    # 注意：ADD COLUMN 不带 DEFAULT——MySQL 8.0.13 之前的版本不允许给 TEXT/BLOB 列加非NULL DEFAULT，
    # 旧值改用下面的 UPDATE 补齐，兼容 SQLite 和各版本 MySQL
    migrations = [
        "ALTER TABLE hit_recommendations ADD COLUMN formula_version TEXT",
        "ALTER TABLE hit_recommendations ADD COLUMN hit_score_v2 REAL",
        "ALTER TABLE hit_recommendations ADD COLUMN stake REAL",
        "ALTER TABLE hit_recommendations ADD COLUMN profit_loss REAL",
        # Bug修复(2026-07-19)：records_written 之前永远只存 1/0（成功/失败布尔值），
        # 不是真实抓取条数——爬虫子进程 stdout 被 DEVNULL 丢弃，完全看不出"成功但
        # 其实只抓到几条"这种情况。补一列存爬虫自己打印的原始输出尾部，供人工核查。
        "ALTER TABLE scraper_run_log ADD COLUMN stdout_tail TEXT",
        # 半全场(HT/FT)市场结算需要半场比分——之前 unified_matches 只存全场比分
        "ALTER TABLE unified_matches ADD COLUMN home_score_ht INTEGER",
        "ALTER TABLE unified_matches ADD COLUMN away_score_ht INTEGER",
    ]
    for sql in migrations:
        try:
            exec_ddl(engine, sql)
        except Exception:
            pass
    try:
        with engine.begin() as conn:
            conn.execute(text(
                "UPDATE hit_recommendations SET formula_version='v1' WHERE formula_version IS NULL"
            ))
    except Exception:
        pass

    log.info("✅ 命中系统数据表初始化完成")


# ─── 1. 调度爬虫 ──────────────────────────────────────────────────────────────
def run_all_scrapers(skip_slow: bool = False, fetch_date: str | None = None):
    """按优先级依次运行所有爬虫，写入运行日志"""
    if fetch_date is None:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    # 断点续跑按本轮运行而不是当天判定：checkpoint存在=恢复上一轮；不存在=新一轮。
    _checkpoint_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), 'data', f'.scraper_checkpoint_{fetch_date}.txt')
    if _os.path.isfile(_checkpoint_path):
        try:
            with open(_checkpoint_path, 'r', encoding='utf-8') as _cfp:
                _run_started_at = _cfp.read().strip()
            if not _run_started_at:
                raise ValueError('empty checkpoint')
            log.info(f'♻ 断点续跑：恢复本轮爬虫任务（起点 {_run_started_at}）')
        except Exception:
            _run_started_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
            with open(_checkpoint_path, 'w', encoding='utf-8') as _cfp:
                _cfp.write(_run_started_at)
    else:
        _run_started_at = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        with open(_checkpoint_path, 'w', encoding='utf-8') as _cfp:
            _cfp.write(_run_started_at)
        log.info('🆕 新一轮爬虫任务：本轮全部重新执行')

    # 爬虫列表：(模块名, 函数名, 优先级, 是否慢速, 调用kwargs)
    scrapers = [
        ("15_pinnacle_oddsportal_scraper", "run",                  1, False, {}),
        ("35_theoddsapi_multi_scraper",    "run",                  1, False, {}),  # api.the-odds-api.com: Bet365/Betfair/Unibet
        # 2026-07-29移除：sporttery_source.fetch_all_sporttery_odds()只返回内存dict，
        # 不写任何数据库表，子进程调用完返回值直接被扔掉——审查发现这条调度从来没有
        # 产生过任何持久化数据，是纯粹的无效调用（唯一真实消费者run_today_prediction.py
        # 已经停跑7周+，不是这条调度的问题）。竞彩信号改由已验证真实可用的
        # 42_okooo_jingcai_scraper.run 提供，见下方okooo_jingcai来源接入。
        # Pinnacle角球赔率：独立调用 fetch_all_corner_odds（不走 run()，避免重复拉主赛事数据）
        ("12_pinnacle_scraper",       "fetch_all_corner_odds",   1, True,  {"fetch_date": fetch_date}),
        # Pinnacle比分盘口：逐场调用/matchups/{id}/related，耗时不可控归为慢速
        ("15_pinnacle_oddsportal_scraper", "fetch_all_correct_score_odds", 1, True, {"fetch_date": fetch_date}),
        # 实时角球赔率（scoremer + live.500.com）
        ("33_corner_odds_scraper",    "main",                    2, False, {}),
        # 角球终值（corner_recommendations 结算主数据源，优先级高于33号的实时快照兜底）
        ("37_corner_stats_scraper",   "run",                     2, False, {"fetch_date": fetch_date}),
        # football-data.co.uk 历史CSV（含角球字段，赛季级别慢速更新）
        ("16_footballdata_scraper",   "run",                     3, True,  {}),
        # ("12_pinnacle_scraper",     "run",                      1, False, {}),  # 已被 15_theodds 覆盖
        # ("07_sofascore_scraper",      "run",                      2, False, {}),  # 【已死勿复活 FIX-008-3 确认】Cloudflare IP 封锁，api.sofascore.com 403，已从调度移除；IP层限制非反爬技巧可解，不要再接回
        ("08_flashscore_scraper",     "run",                      2, False, {}),
        # Bug修复(2026-07-20)：900s超时连续2轮(全量+补爬)都100%失败。已排查——不是
        # 0719修过的空联赛误重试回归（该修复仍生效），是联赛列表长期扩张到132个
        # (110足球+22篮球，序请求)后900s预算没跟上，跟29_qiety/30_flashscore_basketball
        # 是同一类"规模涨了但is_slow分类没跟上"的老问题，同样调is_slow=True→1800s。
        ("16_flashscore_results_scraper", "run",                  2, True,  {}),  # 赛果抓取 → match_results（自动结算依赖）
        ("03_实时赔率抓取",             "run_all",                 2, False, {}),
        # Bug修复(2026-07-19)：原900s超时(is_slow=False)今日连续两次(正式跑+补爬)都
        # 100%超时——"全量"逐场抓取(足球+篮球全部比赛，每场0.4s间隔+最多3次网络重试+
        # 两项目间固定等10s)，赛事多的日子900s本来就不够用，不是当天新引入的代码bug。
        # 参照30_flashscore_basketball_scraper同类问题的修法，标记is_slow=True把
        # 超时提到1800s，留够margin。
        # Bug修复(2026-08-02)：单条目("run",串行足球+篮球两个sport)连续3次1800s超时
        # 失败——排查stdout_tail发现不是卡死/挂起，是真的处理不完：单个sport的比赛
        # 数就有363-373场，严格串行(0.4s/场+SSL错误重试5s/10s退避)跑完足球就已经
        # 逼近1800s上限(最好一次跑到355/363=98%)，篮球根本轮不到，10s等待间隔还要
        # 再占预算。拆成两个独立子进程(football/basketball各自的--sport参数)，让
        # Priority2的ThreadPoolExecutor(并行度4)真正并行跑，每个子任务各自独立拿到
        # 完整1800s预算，不再互相挤占——这是从"加大超时"这种治标不治本的做法改成
        # "去掉不必要的内部串行"的根因修复。脚本自身已用WAL模式+60s busy timeout
        # 处理并发写库(见29_qiety_yb_full_scraper.py"逐场抓赔率"段注释)，两个子
        # 进程同时写同一个sqlite文件是安全的。
        ("29_qiety_yb_full_scraper",   "run_football",             2, True,  {"sport": "1", "_timeout": 2700}),
        ("29_qiety_yb_full_scraper",   "run_basketball",           2, True,  {"sport": "2"}),  # 替换v2，正确解析篮球nolivedata
        # 比分盘口(chpid=7)：依赖29号已写好的qiety_matches，放priority3保证29号(priority2)先跑完
        # Bug修复(2026-08-15)：默认is_slow=1800s，实测2026-08-15当天候选场次从16:52的
        # 624场涨到23:29的964场（筛选窗口"今日+次日12:00前"随时间推进不断吸收新比赛），
        # 964场×单场约1.8s(含30s请求超时兜底但脚本本身无重试退避，正常场次很快)已逼近
        # 1735s，跟1800s上限只剩极小余量，当天连续3次超时。脚本本身没有卡死/死锁证据
        # （stdout_tail显示只有起始候选数打印，脚本for循环内部原本就不打印逐场进度，
        # 不是新问题），是跟29号同一类"量涨了但超时预算没跟上"，同样加_timeout覆盖到
        # 2700s，留出安全余量。
        # FIX-013-2 裁决（2026-09-14）：38号保留——比分市场虽永久关闭生产（FIX-007增补），
        # 但本爬虫同时喂"比分玩法影子观察线"（仍在自动结算记账，已结算128期，属
        # report_jc_closure 遗留观察资产），断粮会让影子样本断更；实测约1分钟出10588条，
        # 2700s只是超时上限。仅喂影子观察线，禁止接回生产；季度复盘重估（影子线连续
        # 两季无分析价值则释放槽位）。
        ("38_qiety_correct_score_scraper", "run",                  3, True,  {"fetch_date": fetch_date, "_timeout": 2700}),
        # 阵容/伤病/积分榜/交锋历史(2026-07-30新增)：同样依赖29号已写好的qiety_matches，
        # 放priority3保证29号(priority2)先跑完，供get_qiety_h2h_probs()影子桶信号使用
        # Bug修复(2026-08-02)：单条目(全部459场比赛×4次请求/场，无sport过滤)从07-30起
        # 反复1800s超时(8次记录里6次超时)，跟29号同一类"单进程预算不够"问题——脚本自身
        # 已有逐match_id断点续跑(qiety_lineup_scrape_log)所以每次重跑没有从0开始，但
        # 单次仍跑不完。同样拆成football/basketball两个独立子进程并行跑，见
        # 46_qiety_lineup_scraper.py --sport 参数说明。
        ("46_qiety_lineup_scraper",   "run_football",             3, True,  {"fetch_date": fetch_date, "sport": "football", "_timeout": 2700}),
        ("46_qiety_lineup_scraper",   "run_basketball",           3, True,  {"fetch_date": fetch_date, "sport": "basketball"}),
        # ── 澳客网(okooo) 数据源（2026-07-14新增，2026-08-01起40号伤停已接入get_model_probs
        #    信号融合，见get_injury_impact_probs()；39/41/42号仍只落库原始数据） ──
        ("39_okooo_ren9_scraper",     "run",                      2, False, {"fetch_date": fetch_date}),  # 传统足彩任九对阵表+赔率
        ("40_okooo_injury_scraper",   "run",                      2, False, {"fetch_date": fetch_date}),  # 伤停名单，已接入injury_impact影子桶
        ("41_okooo_betflow_scraper",  "run",                      2, False, {"fetch_date": fetch_date}),  # 必发盈亏/资金流向快照，需逐日累积才能看走势
        ("42_okooo_jingcai_scraper",  "run",                      2, False, {"fetch_date": fetch_date}),  # 竞彩足球/篮球核心市场，sporttery_source被限流时的备份
        # 2026-09-04新增：qiumibao(球迷宝，188bifen.com镜像)赛前赔率快照，只存
        # 数据攒样本供未来跟titan007同思路的跨源赔率分歧信号回测用，见
        # 48_qiumibao_corner_scraper.py的qiumibao_odds_snapshot建表注释——
        # **不接入get_model_probs()/推荐单生成，纯攒样本**，样本积累到能回测的
        # 量级(参考任九DP那条线至少百期以上)之前不评估是否有用。
        ("48_qiumibao_corner_scraper", "run_odds_snapshot",        2, False, {"fetch_date": fetch_date}),
        ("09_flashscore_schedule_scraper", "run",                  3, True,  {}),
        ("10_oddsportal_scraper",     "run",                      3, True,  {}),
        # ("11_betexplorer_scraper",    "run",                      3, True,  {}),  # 【已死勿复活 FIX-008-3 确认】赔率 API 404，历史数据停更，已从调度移除；不要再接回
        # ("13_bet365_scraper",         "run",                      3, True,  {}),  # 【已死勿复活 FIX-011-4 验尸】bet365_fixtures/odds/inplay 三表全历史0行（缺API key，非网络问题），每天白烧慢速调度槽一个；下游 bet365 读表SQL保留无害（读空表而已），不要再接回调度
        # ("24_betfair_scraper",        "run",                      2, False, {}),  # 【已死勿复活 FIX-013-1 钉棺】betfair_exchange_odds 全历史0行（缺API key，与13号Bet365同型，非网络问题），下游读空表SQL保留不动，不要再接回调度
        ("26_multi_bookmaker_scraper","run",                      2, False, {}),
        # 22_fbref_scraper 已停用(2026-07-20)——排查发现fbref把schedule页的
        # home_xg/away_xg列整个撤掉了(实测该表现在的表头只有gameweek/dayofweek/
        # date/start_time/home_team/score/away_team/attendance/venue/referee/
        # match_report/notes，没有xG字段)，跟/stats/页付费墙(见feedback_fbref_xg_paywall)
        # 是独立的两个问题：那边是被挡，这边是页面上压根不存在这列了。历史6794行
        # fbref_match_stats的home_xg全部是NULL，此前"已验证380场真实xG数据"的记录
        # 只验证了比赛记录数，没验证xG字段本身非空，是误判。现在这个爬虫只能拿到
        # 跟其他源重复的比赛比分，且需要人工点Cloudflare验证码+有nodriver异步竞态
        # 卡死bug，不值得每天人工陪跑，先从调度移除。如果fbref以后恢复xG数据或找到
        # 免费替代来源，可参考fetch_match_xg()重新接入。
        # ("22_fbref_scraper",          "run",                      3, True,  {}),
        # 【已死勿复活 FIX-008-3 确认】fbref主run：schedule页xG列被fbref整列撤掉
        # （不是被挡，是页面上不存在了）+需人工点Cloudflare验证码+nodriver竞态卡死，
        # 不要再接回；xG需求走FotMob(43号)/Understat(17号)替代源。
        # FotMob替代源(2026-07-20新增)：无需浏览器/无Cloudflare拦截，curl_cffi直连即可，
        # 覆盖Understat已有五大联赛+俄超之外的50+联赛/国际赛事真实xG+逐场高阶统计+射门+
        # 球员数据+阵容(见43_fotmob_match_data_scraper.py头部注释)。首次全量回填耗时较长，
        # 已在调度外单独后台跑过一次；日常调度靠_already_have()跳过已入库比赛，增量很快。
        ("43_fotmob_match_data_scraper", "run",                    3, True,  {"fetch_date": fetch_date}),
        ("23_football_data_scraper",  "run",                      3, True,  {}),
        ("23_bball_ref_scraper",      "run",                      3, True,  {}),
        ("25_transfermarkt_scraper",  "run",                      3, True,  {}),
        ("_elo_scraper",             "run",                      3, False, {}),
        # LSTM(EMA+AR1)时序状态分——纯本地计算(读basketball_matches/football_matches
        # 算EMA+AR1，不联网)，刷新team_lstm_state供get_model_probs()的影子观察单用，
        # 见 _lstm_home_win_prob() 说明。不依赖04_高阶指标分析.py先跑。
        ("04_1_LSTM_时序状态模型",     "run",                      3, False, {}),
        # Bug修复(2026-08-26)：角球正式推荐单(corner_recommendations)的主数据源
        # corner_team_stats/corner_league_baseline之前只由这个脚本手动跑一次
        # (2026-06-13)算好，从没排进每日调度，冻结了2.5个月不更新，直接影响真钱
        # 推荐——跟04_1_LSTM同一类"纯本地重算、不联网"的脚本，排在43号FotMob
        # 爬虫(本Priority3更靠前)之后，让每天写入的最新fotmob_match_team_stats.corners
        # 当季数据也能喂给角球统计（脚本内部新增的FotMob当季补充源，见
        # import_corner_stats.py的2026-08-26修复说明）。
        ("import_corner_stats",       "run",                      3, False, {}),
        ("19_whoscored_scraper",      "run",                      3, True,  {}),
        # ── xG 专项数据源（每日更新赛季级 xG，供预测模型使用） ──
        ("10_understat_xg_scraper",   "run",                      3, True,  {}),
        ("11_fbref_xg_scraper",       "run",                      3, True,  {}),
        ("12_statsbomb_national_xg_scraper", "run",               3, True,  {"latest": True}),
        ("04_2_Football_xG_Module",   "calc_and_save",            3, True,  {}),
        # ── 欧洲篮球专项数据源（27-30，需配置对应 API Key 才会实际运行） ──
        ("27_euroleague_feeds_scraper",    "run",                  2, False, {}),  # EuroLeague官方Feeds(feeds.incrowdsports.com)
        ("28_livescore_basketball_scraper","run",                  2, False, {}),  # LiveScore.com公开API
        ("29_betexplorer_basketball_scraper","run",                2, False, {}),  # BetExplorer篮球赔率
        # Bug修复：原900s超时(is_slow=False)长期100%超时失败——实测SofaScore阶段
        # 18个联赛几乎全被403/TLS拦截，重试轮换指纹耗时巨大，完整跑完实测需1542s。
        # 标记is_slow=True把超时提到1800s，留够margin。（注：fs_bball_matches/
        # sofa_bball_matches两张表目前还没接入unified_matches跨源匹配，调超时只让
        # 这个爬虫本身不再报错，不代表Euroleague/ACB数据已经能进推荐候选池——集成
        # 是后续单独的工作）
        ("30_flashscore_basketball_scraper","run",                 2, True,  {}),  # FlashScore篮球频道
        ("18_espn_scores_scraper",         "run",                  2, False, {"fetch_date": fetch_date}),  # ESPN比分/节次(含NBA夏季联赛)，供后续结算回填espn_scores
        ("31_nba_official_scraper",        "run",                  3, True,  {"fetch_date": fetch_date}),  # NBA官方(stats.nba.com)，当前网络对该域名封锁会自动跳过
    ]

    import concurrent.futures as _cf
    import subprocess as _sp

    base_dir = _os.path.dirname(_os.path.abspath(__file__))

    # Bug修复(2026-07-19)：抽出统一的"记录数写入"提取正则——调查发现项目内约30个
    # 爬虫脚本几乎都用"N 条/场/行 ... 写入"或"写入 ... N 条/场/行"这个惯例打印结果。
    # 取全部匹配数字加总（不是只取最后一条）——实测有的爬虫会分类打印多行汇总
    # （如"竞彩足球:11场写入"+"竞彩篮球:0场写入"），只取最后一行会把真实有数据的
    # 情况显示成误导性的0。加总策略可能对"中间过程数+最终汇总数"重复计的场景
    # (如"[X]:15条待写入"+"完成:写入47条")算出偏高的数字，但这个用途主要是发现
    # "报告成功但其实没抓到东西"的静默异常，偏高比偏低（尤其偏低到0）更安全——
    # 具体真实明细以 stdout_tail 里的原始输出为准，这里只是一个粗略信号。
    _REC_COUNT_PATTERNS = [
        re.compile(r"写入[^\d\n]{0,40}(\d+)\s*[条场行]"),
        re.compile(r"(\d+)\s*[条场行][^\d\n]{0,40}写入"),
    ]

    def _extract_record_count(stdout_text: str):
        """从爬虫子进程的stdout里提取所有"N条/场/行...写入"数字并加总，
        找不到时返回 None（调用方据此判断是否要降级用旧的1/0占位）。"""
        seen_positions = set()
        total = 0
        found = False
        for pat in _REC_COUNT_PATTERNS:
            for m in pat.finditer(stdout_text):
                pos = m.start(1)  # 按捕获组(数字本身)的位置去重，避免两条pattern重复计同一个数字
                if pos in seen_positions:
                    continue
                seen_positions.add(pos)
                try:
                    total += int(m.group(1))
                    found = True
                except (ValueError, IndexError):
                    continue
        return total if found else None

    def _launch_scraper(mod_name, func_name, is_slow, kwargs):
        """以独立子进程运行爬虫，返回 (ok, error_msg, records, stdout_tail)。
        records 是从stdout解析出的真实抓取/写入条数，解析不到时为 None。
        stdout_tail 是子进程输出的最后一段（不管成功失败都存），供人工核查
        "退出码是0但实际没抓到什么东西"这类静默异常。"""
        mod_file = mod_name if mod_name.endswith(".py") else mod_name + ".py"
        mod_path = _os.path.join(base_dir, mod_file)
        if not _os.path.isfile(mod_path):
            return False, f"模块文件不存在: {mod_path}", None, None

        # 允许单条目通过 kwargs["_timeout"] 覆盖默认预算——29/46号qiety爬虫
        # 联赛/比赛规模大(300+场逐场请求)时1800s常压线超时(2026-08-09连续
        # 两轮验证)，给这两项单独放宽，不影响其他"慢速"档爬虫的默认1800s上限。
        timeout_s = kwargs.get("_timeout") or (1800 if is_slow else 900)

        # 构造命令：优先直接运行脚本（run/main 函数 = 标准 __main__ 入口）
        # 非标准函数名（如 calc_and_save）用 -c 内联调用
        # func_name 允许 "run_xxx"/"main_xxx" 前缀变体（2026-08-02新增）——单个
        # 脚本内部要拆成多个可并行子任务(如29号qiety按sport拆football/basketball)
        # 时，用不同func_name区分_today_ok断点续跑key和scraper_run_log记录，
        # 避免两个子任务共用同一个key互相误判"今天已成功"。子进程实际执行的
        # 还是同一个脚本的标准__main__入口，func_name前缀只影响这里的分支判断
        # 和外层的日志/去重key，不影响脚本内部调用哪个函数。
        if func_name in ("run", "main") or func_name.startswith(("run_", "main_")):
            cmd = [sys.executable, "-X", "utf8", mod_path]
            # 将 kwargs 转为 CLI 参数
            date_val = kwargs.get("date_str") or kwargs.get("fetch_date")
            if date_val:
                cmd.extend(["--date", date_val])
            if kwargs.get("latest_only") or kwargs.get("latest"):
                cmd.append("--latest")
            if kwargs.get("sport"):
                cmd.extend(["--sport", str(kwargs["sport"])])
        else:
            # 非标准入口：用 -c 内联调用指定函数
            kw_repr = ", ".join(
                f"{k}={repr(v)}" for k, v in kwargs.items()
            )
            cmd = [
                "python", "-X", "utf8", "-c",
                f"import sys; sys.path.insert(0,r'{base_dir}'); "
                f"import importlib.util as u; "
                f"spec=u.spec_from_file_location('_m',r'{mod_path}'); "
                f"m=u.module_from_spec(spec); spec.loader.exec_module(m); "
                f"m.{func_name}({kw_repr})"
            ]

        try:
            result = _sp.run(
                cmd, timeout=timeout_s, cwd=base_dir,
                stdout=_sp.PIPE, stderr=_sp.PIPE
            )
            out_text = (result.stdout or b"").decode("utf-8", errors="replace")
            out_tail = out_text[-2000:].strip()
            records = _extract_record_count(out_text)
            if result.returncode != 0:
                err_tail = (result.stderr or b"")[-300:].decode("utf-8", errors="replace").strip()
                return False, f"exit {result.returncode}: {err_tail}", records, out_tail
            return True, None, records, out_tail
        except _sp.TimeoutExpired as e:
            # 超时被杀掉前的部分输出仍有诊断价值（比如卡在第几个联赛/第几场）
            partial = (e.stdout or b"") if isinstance(e.stdout, (bytes, bytearray)) else b""
            partial_text = partial.decode("utf-8", errors="replace")
            return False, f"timeout after {timeout_s}s", _extract_record_count(partial_text), partial_text[-2000:].strip()
        except Exception as e:
            return False, str(e)[:500], None, None

    # 断点续跑：今天已经成功跑过的爬虫直接跳过（scraper_run_log 里查 status='ok'），
    # 避免整轮被中途杀掉重跑时，把已经成功抓到数据的爬虫再白跑一遍
    # Bug修复(2026-07-19)：之前只按 mod_name 判重，同一脚本挂多个不同函数的调度项
    # （如 15_pinnacle_oddsportal_scraper 同时有 .run 和 .fetch_all_correct_score_odds
    # 两条）会互相误判"今天已成功"——.run 成功过一次，.fetch_all_correct_score_odds
    # 哪怕从没成功过也会被跳过。改成 "{mod_name}.{func_name}" 复合key判重，
    # scraper_run_log.scraper 列同步存复合key（下面INSERT处一并改）。
    _today_ok: set = set()
    if fetch_date:
        try:
            with engine.connect() as _rc:
                _rows = _rc.execute(text("""
                    SELECT DISTINCT scraper FROM scraper_run_log
                    WHERE status='ok' AND run_at >= :run_start
                """), {"run_start": _run_started_at}).fetchall()
            _today_ok = {r[0] for r in _rows}
        except Exception:
            pass

    # 按优先级分组，同组并行执行（priority 1 串行，2 并行4，3 并行3）
    _GROUP_WORKERS = {1: 1, 2: 4, 3: 3}
    from itertools import groupby as _gb

    priority_groups: dict = {}
    for item in scrapers:
        mod_name, func_name, priority, is_slow, kwargs = item
        if skip_slow and is_slow:
            log.info(f"  跳过慢速爬虫: {mod_name}")
            continue
        if f"{mod_name}.{func_name}" in _today_ok:
            log.info(f"  跳过（今日已成功）: {mod_name}.{func_name}")
            continue
        priority_groups.setdefault(priority, []).append(item)

    for priority in sorted(priority_groups.keys()):
        group  = priority_groups[priority]
        n_work = _GROUP_WORKERS.get(priority, 2)
        log.info(f"\n🚀 Priority {priority} — {len(group)} 个爬虫，并行度 {n_work}")

        with _cf.ThreadPoolExecutor(max_workers=n_work) as ex:
            fut_map = {
                ex.submit(_launch_scraper, mod_name, func_name, is_slow, kwargs):
                    (mod_name, func_name)
                for mod_name, func_name, _, is_slow, kwargs in group
            }
            for fut in _cf.as_completed(fut_map):
                mod_name, func_name = fut_map[fut]
                run_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                try:
                    ok, error, records, stdout_tail = fut.result()
                except Exception as e:
                    ok, error, records, stdout_tail = False, str(e)[:500], None, None

                status = "ok" if ok else "error"
                # records 解析不到时降级用旧的1/0占位（至少还能区分成功/失败），
                # 解析到时用真实数字——不再是"成功就固定填1"这种看不出真实抓取量的做法
                rec_val = records if records is not None else (1 if ok else 0)
                rec_note = f"（{records}条）" if records is not None else "（条数未知，见stdout_tail）"
                if ok:
                    log.info(f"  ✅ {mod_name}.{func_name} {rec_note}")
                else:
                    log.warning(f"  ❌ {mod_name}.{func_name} — {error} {rec_note}")

                # Bug修复(2026-08-11)：这条日志写入原先没有任何异常保护，一次
                # "database is locked" 就会把**整个爬虫调度**打断——实测当天因为
                # 外部有并发查询占着库，Priority 2 才跑到第2个爬虫就抛
                # sqlite3.OperationalError 整轮中止，82个爬虫只完成6个。
                # 记一条运行日志失败绝不该终止抓取本身：这里加重试+兜底吞异常，
                # 最坏情况只是少一条日志，不影响已经抓到的数据。
                for _attempt in range(3):
                    try:
                        with engine.begin() as conn:
                            conn.execute(text("""
                                INSERT INTO scraper_run_log (scraper,run_at,status,records_written,error_msg,stdout_tail)
                                VALUES (:s,:r,:st,:rec,:err,:out)
                            """), {
                                "s": f"{mod_name}.{func_name}", "r": run_at,
                                "st": status, "rec": rec_val, "err": error, "out": stdout_tail,
                            })
                        break
                    except Exception as _le:
                        if _attempt == 2:
                            log.warning(f"  ⚠ 运行日志写入失败(不影响抓取): {str(_le)[:100]}")
                        else:
                            time.sleep(2 * (_attempt + 1))


    # 爬虫调度完整结束：清除本轮checkpoint；下次启动视为全新一轮。
    # 若进程在到达这里之前中断，文件会保留，下次自动按本轮成功记录断点续跑。
    try:
        if _os.path.isfile(_checkpoint_path):
            _os.remove(_checkpoint_path)
            log.info("✅ 本轮爬虫调度完成，断点checkpoint已清除")
    except Exception as _ce:
        log.warning(f"⚠ checkpoint清除失败: {str(_ce)[:100]}")

# ─── 2. 跨源比赛匹配 ─────────────────────────────────────────────────────────
def _normalize_team(name: str) -> str:
    """队名标准化：去标点、转小写、移除常见后缀"""
    name = name.lower().strip()
    name = re.sub(r"['\-\.\(\)&,]", " ", name)
    name = re.sub(r"\b(fc|cf|sc|ac|afc|bfc|united|city|town|sporting|club|de|del|el|la|le|les|'s)\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name



def _match_key(home: str, away: str, kickoff: str) -> str:
    """生成跨源唯一键"""
    date_part = kickoff[:10] if kickoff else "unknown"
    hn = _normalize_team(home)
    an = _normalize_team(away)
    return hashlib.md5(f"{date_part}|{hn}|{an}".encode()).hexdigest()[:12]


# 2026-09-12 新增（中文队名→模型断链修复）：
# qiety源队名是中文，直接传给 compute_advanced_poisson()/get_fotmob_*_probs()
# 这些按英文队名查 match_results/fotmob 统计表的函数时，全部查不到 → 静默摔到
# 联赛兜底/全局均值，甚至被当成"无模型信号"。修复：进模型查询层前做一次
# **精确命中限定**的中文→英文翻译（team_mapping.TEAM_CN_TO_EN，含2956条自动配对
# +12条手工覆盖）。不用 team_mapping.team_en() 的模糊回退——它曾把"塞维利亚"
# 错译成国家队"serbia"。翻译不到就保持原名，让下游自然走"无真实信号→排除"，
# 绝不伪造数字。ELO 的 _MPS_CACHE 查询（跨源池，含中文名）不经过这里，保持原名。
def _model_team_en(name: str) -> str:
    """模型查询用队名：中文名只做词典精确翻译，无模糊回退；无命中保持原名"""
    if not name:
        return name
    if re.search(r'[一-鿿]', name):
        from team_mapping import TEAM_CN_TO_EN
        _hit = TEAM_CN_TO_EN.get(name.strip())
        if _hit is None:
            # FIX-008-1（2026-09-13）：无法映射的中文队名不能只保持原名了之——
            # 收集起来在跑批收尾批量写 data_quality_issue_log（同日同队幂等），
            # 让"模型无信号"从哑巴亏变成可见的映射缺口清单，供补词典。
            # 这里只收集不写库：本函数在逐场热路径上被调用，不能每次都开连接。
            _UNMAPPED_CN_TEAMS.add(name.strip())
            return name
        return _hit
    return name


# FIX-008-1：本次运行中未能精确映射的中文队名（_model_team_en 收集，
# run() 收尾时 _flush_unmapped_cn_teams() 批量落 dqil）
_UNMAPPED_CN_TEAMS: set = set()


def _flush_unmapped_cn_teams(fetch_date: str):
    """把本次运行收集到的未映射中文队名批量写 data_quality_issue_log
    （issue_code=QIETY_CN_TEAM_UNMAPPED，同日同队幂等——同日已存在则跳过）。
    只新增不删改，失败显式 log 不静默。"""
    if not _UNMAPPED_CN_TEAMS:
        return
    written = 0
    try:
        with engine.begin() as _c:
            for _name in sorted(_UNMAPPED_CN_TEAMS):
                _exists = _c.execute(text(
                    "SELECT COUNT(*) FROM data_quality_issue_log "
                    "WHERE issue_code='QIETY_CN_TEAM_UNMAPPED' AND entity_key=:k "
                    "AND substr(created_at,1,10)=:d"
                ), {"k": _name, "d": fetch_date}).scalar()
                if _exists:
                    continue
                _c.execute(text(
                    "INSERT INTO data_quality_issue_log "
                    "(entity_type, entity_key, issue_code, message, level, source_name, created_at) "
                    "VALUES ('team', :k, 'QIETY_CN_TEAM_UNMAPPED', :m, 'warning', "
                    "'00_命中系统/_model_team_en', datetime('now','localtime'))"
                ), {"k": _name,
                    "m": f"中文队名'{_name}'在TEAM_CN_TO_EN无精确映射，"
                         f"模型查询保持原名(下游按无真实信号排除)，待补词典"})
                written += 1
    except Exception as _e:
        log.warning(f"  ⚠ 未映射中文队名落dqil失败: {type(_e).__name__}: {_e}")
    if written:
        log.info(f"  📝 未映射中文队名 {written} 个已记 data_quality_issue_log"
                 f"（共收集 {len(_UNMAPPED_CN_TEAMS)} 个）")


_scrape_date_cache: dict = {}   # {fetch_date: scrape_date}  跨调用复用

def _discover_scrape_date(fetch_date: str) -> str:
    """返回 fetch_date 当日或最近一次爬取日期（用于跨日 --no-scrape 场景）"""
    if fetch_date in _scrape_date_cache:
        return _scrape_date_cache[fetch_date]
    _probe_tables = [
        "flashscore_matches", "theodds_fixtures",
        "soccerway_matches",  "oddsportal_matches", "pinnacle_fixtures",
    ]
    best: str | None = None
    try:
        with engine.connect() as _c:
            for _tbl in _probe_tables:
                try:
                    _r = _c.execute(text(
                        f"SELECT MAX(fetch_date) FROM {_tbl} WHERE fetch_date <= :fd"
                    ), {"fd": fetch_date}).scalar()
                    if _r and (best is None or _r > best):
                        best = _r
                except Exception:
                    pass
    except Exception:
        pass
    result = best or fetch_date
    _scrape_date_cache[fetch_date] = result
    return result


def build_unified_matches(fetch_date: str):
    """从各源表汇聚比赛，去重合并"""
    log.info("🔗 构建统一比赛表...")

    # ── 确定实际数据日期（支持 --no-scrape 跨日分析）────────────────────────
    scrape_date = _discover_scrape_date(fetch_date)
    if scrape_date != fetch_date:
        log.info(f"  数据回退模式: fetch_date={fetch_date} 无数据，使用 scrape_date={scrape_date}")
    # 跨日时只保留目标日及之后开赛的比赛（kickoff_utc >= fetch_date）
    cross_day = (scrape_date != fetch_date)

    # 收集各源比赛（:fd 传入 scrape_date，kickoff 由 Python 层过滤）
    # 半全场(HT/FT)结算需要半场比分：目前只信 sofascore_matches 的 home_score_ht/
    # away_score_ht（对应 Sofascore 官方 API 文档化的 period1 字段）。soccerway_matches
    # 同名列本应来自 09_flashscore_schedule_scraper.py，但2026-07-24排查确认它读的
    # AG/AT 字段代号是猜错的（30_flashscore_basketball_scraper.py 证实 AG 在同一套
    # 协议里实际是"主队最终比分"，且足球赛程列表页原始数据里根本不带半场分节字段），
    # 53%样本出现半场>全场的不可能组合——不是噪声是系统性读错，在09号脚本修好前
    # 整列不接，统一补 NULL,NULL，避免把看似合理实则巧合通过校验的假数据混进来。
    # 其余源没有半场分概念，同样补 NULL,NULL 占位，保持每个源 SELECT 都是相同的
    # 11 列，下面按位置解包不用按源分支处理。
    sources = [
        ("sofascore",   "SELECT event_id, sport_code, league_name, home_team_name, away_team_name, kickoff_utc, status_code, home_score, away_score, home_score_ht, away_score_ht FROM sofascore_matches WHERE fetch_date=:fd"),
        ("flashscore",  "SELECT flash_id, sport_code, league_code, home_team, away_team, kickoff_utc, status, home_score, away_score, NULL, NULL FROM flashscore_matches WHERE fetch_date=:fd AND kickoff_utc >= datetime(:kd) AND kickoff_utc < datetime(:kd, '+3 days')"),
        ("soccerway",   "SELECT sw_match_id, 'football', league_name, home_team, away_team, kickoff_utc, status, home_score, away_score, NULL, NULL FROM soccerway_matches WHERE fetch_date=:fd"),
        ("oddsportal",  "SELECT op_match_id, sport_code, league_name, home_team, away_team, kickoff_utc, status, home_score, away_score, NULL, NULL FROM oddsportal_matches WHERE fetch_date=:fd"),
        ("betexplorer", "SELECT be_match_id, sport_code, league_code, home_team, away_team, kickoff_utc, status, home_score, away_score, NULL, NULL FROM betexplorer_matches WHERE fetch_date=:fd"),
        ("pinnacle",    "SELECT matchup_id, sport_code, league_name, home_team, away_team, kickoff_utc, status, home_score, away_score, NULL, NULL FROM pinnacle_fixtures WHERE fetch_date=:fd"),
        ("bet365",      "SELECT b365_event_id, sport_code, league_name, home_team, away_team, kickoff_utc, status, home_score, away_score, NULL, NULL FROM bet365_fixtures WHERE fetch_date=:fd"),
        ("theodds",     "SELECT id, sport_code, league_name, home_team, away_team, kickoff_utc, status, NULL, NULL, NULL, NULL FROM theodds_fixtures WHERE fetch_date=:fd"),
        # theodds_api: 商业API (api.the-odds-api.com) — sport字段 'soccer'→'football'
        ("theodds_api", "SELECT DISTINCT event_id, CASE sport WHEN 'soccer' THEN 'football' WHEN 'basketball' THEN 'basketball' ELSE sport END, league_name, home_team, away_team, commence_time, 'pre', NULL, NULL, NULL, NULL FROM theodds_api_odds WHERE fetch_date=:fd"),
        # qiety_yb: 企鹅体育 YB 中文赔率源 — JOIN qiety_matches 获取真实开赛时间
        # 注意: match_date 用目标日期 :kd（跨日时也匹配未来赛事）
        # Bug修复(2026-07-13): 原来 qm.fetch_date = :fd 要求当天必须重新抓到该场比赛的
        # qiety_matches 记录，一旦该场比赛今天没被重新抓到（临近开赛/已开赛的场次常被
        # qiety接口挪出"待开赛列表"），JOIN不上就退化成 mo.match_date||'T12:00:00' 这个
        # 假占位时间——不仅展示错误，还污染了"是否未开赛"的筛选逻辑，导致已结束的比赛
        # （如实测的两场WNBA，真实开赛07:00/09:00，早已FT）被当成未开赛塞进正式推荐单。
        # 改为取该match_id历史上最近一次抓到的真实kickoff_time（不要求等于今天），
        # 真正查不到任何记录时才退化到占位时间。
        # 第二个Bug(同一天发现): qiety_matches.kickoff_time 由 29_qiety_yb_full_scraper.py
        # 用 tz=TZ_BJ（北京时区）转换写入，是北京本地时间的裸字符串，没带时区标记；但这里
        # 直接塞进 kickoff_utc 字段参与 "kickoff_utc > now_utc"（真UTC）的未开赛过滤比较，
        # 导致企鹅体育源比赛整体判断偏差8小时——已开赛不到8小时的比赛仍会被判定为"未开赛"。
        # 用 SQLite datetime(...,'-8 hours') 转换成真UTC再格式化为与其他源一致的 T 分隔格式。
        # 2026-09-11修复: 原来 WHERE 里 match_date=:kd 只取当天场次,次日0点~12点(北京)
        # 的比赛 qiety 明明抓到了(match_date=次日)却被整体排除——平时靠 Pinnacle(theodds)
        # 源带次日场次盖住这个缺口,2026-09-11 Pinnacle 足球源返回0场,窗口内足球直接真空,
        # FotMob/LSTM胜平负等 piggyback 在足球独赢候选上的桶全空。改为当天+次日,下游
        # generate_recommendations 的"未开赛+次日12:00前"窗口会自然裁掉超范围场次。
        # 教训: 注释不能写进三引号SQL字符串内部(#不是SQL注释,会直接报语法错),
        # 而该查询的异常被 try/except 捕获后只 log.debug,表现为"qiety源静默贡献0行"。
        ("qiety_yb",    """SELECT mo.match_id,
            CASE WHEN mo.sport='football' THEN 'football' ELSE 'basketball' END,
            mo.league, mo.home_team, mo.away_team,
            COALESCE(REPLACE(datetime(qm.kickoff_time, '-8 hours'), ' ', 'T'), mo.match_date || 'T12:00:00'),
            'NS', NULL, NULL, NULL, NULL
            FROM multisource_odds mo
            LEFT JOIN qiety_matches qm ON qm.match_id = mo.match_id
                AND qm.fetch_date = (
                    SELECT MAX(qm2.fetch_date) FROM qiety_matches qm2
                    WHERE qm2.match_id = mo.match_id
                )
            WHERE mo.source LIKE 'qiety_yb%' AND mo.match_date IN (:kd, date(:kd, '+1 day')) AND mo.odds_type='1X2'
            GROUP BY mo.match_id"""),
        # okooo_jingcai: 澳客网竞彩赔率(42号爬虫)，中文队名，直接读原始表不需要
        # 桥接表——2026-07-29接入：之前sporttery_source调度是无效死代码(见上方
        # 说明)，这张表此前抓了但从未被消费，现在补上真正的比赛匹配+赔率读取。
        # kickoff是北京时间裸字符串(跟qiety_yb同一类已知bug，见CLAUDE.md"企鹅
        # 体育开赛时间处理规则")，必须-8小时转真UTC再取日期做匹配key，否则
        # 跨零点的比赛会被判定成不同日期，匹配不到其他源(实测发现)。
        ("okooo_jingcai", """SELECT match_id, 'football', league, home_team, away_team,
            REPLACE(datetime(kickoff, '-8 hours'), ' ', 'T'), 'NS', NULL, NULL, NULL, NULL
            FROM okooo_football_odds
            WHERE fetch_date=:fd"""),
    ]

    # unified_id → {sources, home_team_std, ...}
    match_map = {}

    from team_mapping import team_en

    for source_name, sql in sources:
        try:
            with engine.connect() as conn:
                rows = conn.execute(text(sql), {"fd": scrape_date, "kd": fetch_date}).fetchall()
        except Exception as e:
            log.debug(f"  源 {source_name} 查询失败: {e}")
            continue

        for row in rows:
            src_id, sport, league, home, away, kickoff, status, hs, as_, hs_ht, as_ht = row
            # 防御性校验：半场进球数不能超过全场（已知全场比分时才能核验）。
            # 09_flashscore_schedule_scraper.py 的半场比分字段代号曾被证实猜错
            # （2026-07-24 排查：AG/AT 实际不是半场分，53%数据出现半场>全场的
            # 不可能组合），这里做兜底过滤，不管哪个源以后出现同类解析错误，
            # 都不会把物理上不可能的数据写进 unified_matches。
            if hs_ht is not None and as_ht is not None:
                if hs_ht < 0 or as_ht < 0 or (hs is not None and hs_ht > hs) or (as_ is not None and as_ht > as_):
                    hs_ht, as_ht = None, None
            # 质量过滤：league 和 kickoff 同时为空 → 数据源无法定位赛事，跳过
            # 避免 OddsPortal 足球盘因队名相似误混入篮球统一表
            if not (league or "").strip() and not (kickoff or "").strip():
                continue
            # 跨日模式：只保留目标日期及之后开赛的比赛
            if cross_day and kickoff and kickoff < fetch_date:
                continue
            # qiety_yb/okooo_jingcai: 中文队名转英文后再匹配，确保与其他源同一比赛对齐
            if source_name in ("qiety_yb", "okooo_jingcai"):
                home_en = team_en(home)
                away_en = team_en(away)
                uid = _match_key(home_en, away_en, kickoff)
                # 仍保存中文队名用于展示
                qiety_home = home
                qiety_away = away
            else:
                home_en = away_en = None
                qiety_home = qiety_away = None
                uid = _match_key(home, away, kickoff)

            # okooo_jingcai安全防护(2026-07-29)：实测发现okooo原始数据里队名被
            # 截断成2个汉字("阿拉"/"奥莫"这种)，team_en()字典是按qiety的完整
            # 队名建的，2字符截断名几乎不可能命中，导致_match_key算出来的uid
            # 跟其他源真实是同一场比赛却对不上——如果放任它单独建新条目，会往
            # unified_matches里塞入大量看不懂、跟真实比赛脱节的孤儿单源条目。
            # 在队名匹配问题解决前，okooo_jingcai只允许给已存在的条目补充来源，
            # 不允许单独建新条目。
            if source_name == "okooo_jingcai" and uid not in match_map:
                continue

            if uid not in match_map:
                # Bug修复：统一 sport_code 为小写（各源返回大小写不一致）
                _sport_norm = (sport or "football").lower()
                if _sport_norm == "soccer":
                    _sport_norm = "football"
                # qiety_yb 中文队名优先作为统一展示名
                std_home = qiety_home or home
                std_away = qiety_away or away
                match_map[uid] = {
                    "unified_id": uid,
                    "sport_code": _sport_norm,
                    "league_name": league or "",
                    "home_team_std": std_home,
                    "away_team_std": std_away,
                    "kickoff_utc": kickoff or "",
                    "status": status or "NS",
                    "home_score": hs,
                    "away_score": as_,
                    "home_score_ht": hs_ht,
                    "away_score_ht": as_ht,
                    "sources": {source_name: str(src_id)},
                }
            else:
                match_map[uid]["sources"][source_name] = str(src_id)
                # 如果已有记录，用中文队名覆盖英文（前提是这次是qiety_yb）
                if qiety_home:
                    match_map[uid]["home_team_std"] = qiety_home
                    match_map[uid]["away_team_std"] = qiety_away
                # 用有赔率的源更新比分
                if hs is not None and match_map[uid]["home_score"] is None:
                    match_map[uid]["home_score"] = hs
                    match_map[uid]["away_score"] = as_
                # 半场比分同理，独立于全场比分更新（sofascore/soccerway 才有半场分，
                # 可能和最先写入全场比分的源不是同一个源）
                if hs_ht is not None and match_map[uid]["home_score_ht"] is None:
                    match_map[uid]["home_score_ht"] = hs_ht
                    match_map[uid]["away_score_ht"] = as_ht

    # 批量写入 unified_matches（单事务）
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    batch = [
        {
            "uid": uid, "sport": m["sport_code"],
            "lc": m.get("league_code", ""), "ln": m["league_name"],
            "home": m["home_team_std"], "away": m["away_team_std"],
            "kickoff": m["kickoff_utc"], "status": m["status"],
            "hs": m["home_score"], "as_": m["away_score"],
            "hs_ht": m["home_score_ht"], "as_ht": m["away_score_ht"],
            # source_count 按规范化来源去重（theodds 与 pinnacle 同源，避免虚增覆盖度）
            "sc": len({SOURCE_CANONICAL.get(s, s) for s in m["sources"]}),
            "sj": json.dumps(m["sources"], ensure_ascii=False),
            "now": now, "fd": fetch_date,
        }
        for uid, m in match_map.items()
    ]
    if batch:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT OR REPLACE INTO unified_matches
                (unified_id,sport_code,league_code,league_name,home_team_std,away_team_std,
                 kickoff_utc,status,home_score,away_score,home_score_ht,away_score_ht,
                 source_count,sources_json,last_updated,fetch_date)
                VALUES
                (:uid,:sport,:lc,:ln,:home,:away,:kickoff,:status,:hs,:as_,:hs_ht,:as_ht,:sc,:sj,:now,:fd)
            """), batch)

    log.info(f"  统一比赛表: {len(match_map)} 场（{fetch_date}）")
    return match_map, scrape_date


# ─── 3. 跨源赔率汇聚 ─────────────────────────────────────────────────────────
def _market_capture_result(status, rows=(), reason=None):
    # Never qualify partial rows on failure.
    return {"status": status, "rows": tuple(dict(r) for r in rows) if status == "SUCCESS" else (),
            "failure_reason": reason}


def _merge_frozen_unified(captured, rows, *, replace):
    """Mirror the production UNIQUE key; NULL keys fail closed, never dict-coalesce."""
    for row in rows:
        key = tuple(row[k] for k in ("uid", "src", "market", "outcome"))
        if any(v is None for v in key):
            raise ValueError("NULL unified conflict key cannot qualify frozen input")
        if replace:
            captured.pop(key, None)
        if key not in captured:
            captured[key] = dict(row)


def _write_frozen_ignore(conn, sql, rows, *, frozen):
    if not frozen:
        conn.execute(sql, rows)
        return ()
    accepted = []
    for row in rows:
        result = conn.execute(sql, row)
        if result.rowcount == 1:
            accepted.append(row)
        elif result.rowcount != 0:
            raise ValueError("Cannot prove INSERT OR IGNORE delivery")
    return accepted


def build_unified_odds(unified_id: str, sources: dict, fetch_date: str,
                       scrape_date: str | None = None, *, frozen=False):
    """Legacy writes are unchanged; frozen mode additionally returns qualified run rows."""
    try:
        result = _build_unified_odds_impl(unified_id, sources, fetch_date, scrape_date, frozen=frozen)
    except Exception as exc:
        if not frozen:
            raise
        result = _market_capture_result("FAILURE", reason="unified: " + type(exc).__name__)
    if frozen and result["status"] == "FAILURE":
        log.warning("Frozen market input WARNING uid=%s: %s", unified_id, result["failure_reason"])
    return result


def _build_unified_odds_impl(unified_id: str, sources: dict, fetch_date: str, scrape_date: str | None = None, *, frozen=False):
    """从各源抓取该场比赛的赔率写入 unified_odds

    fetch_date  : 分析目标日期，用于写入 unified_odds（generate_recommendations 按此查询）
    scrape_date : 实际爬取日期（--no-scrape 跨日时 != fetch_date），用于从源表读取赔率
    """
    # 跨日 --no-scrape 模式：源表数据在 scrape_date，unified_odds 写入 fetch_date
    # scrape_date=None 时自动探测（standalone 调用场景）
    failures = []
    captured = {}
    sd = scrape_date if scrape_date is not None else _discover_scrape_date(fetch_date)

    # Bug修复(2026-07-19，同consensus_odds那处一并发现)：本函数下面所有INSERT都是
    # OR REPLACE/OR IGNORE，从不清理该unified_id名下已不再由本次source数据产出的旧
    # (source,market,outcome)组合——比如某源的market命名方式变化(如team_total拆分
    # 成team_total_home/away)后，旧key的行会永久残留在unified_odds里，反过来污染
    # compute_consensus_odds()每次的重算结果(它读的是unified_odds全部现存行，不知道
    # 哪些是"当次真实来源"哪些是死数据)。本函数每次都会完整重新查询全部source重建
    # 该unified_id的赔率(main_batch/yb_corner/pinnacle_corner/scoremer四块下面都是
    # 无条件从源表重算，不是增量更新)，所以先清空再重建是安全的。
    # 注意：必须带 fetch_date 限定——unified_id 由 kickoff 日期算出，同一场未来比赛
    # 会在不同自然日被反复抓取，unified_odds 按设计要跨 fetch_date 保留每天的历史
    # 快照供 compute_consensus_odds()/CLV 计算按 fetch_date 回溯查询；不限定 fetch_date
    # 会把这场比赛之前几天的赔率快照也一并删掉，那是另一个更大的数据丢失bug。
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM unified_odds WHERE unified_id=:uid AND fetch_date=:fd"),
                     {"uid": unified_id, "fd": fetch_date})

    # 赔率查询：pinnacle/theodds 表（实际均为 Pinnacle Guest API 数据）有 handicap
    # :fd → 用 scrape_date（sd）查源表，:wd → 用 fetch_date 写 unified_odds
    odds_queries = [
        ("sofascore",   "SELECT :uid, 'sofascore', outcome, odds_value, NULL FROM sofascore_odds WHERE event_id=:sid AND fetch_date=:fd"),
        ("oddsportal",  "SELECT :uid, 'oddsportal', market||'_'||outcome, odds_value, NULL FROM oddsportal_odds WHERE op_match_id=:sid AND fetch_date=:fd"),
        ("betexplorer", "SELECT :uid, 'betexplorer', market||'_'||outcome, odds_close, NULL FROM betexplorer_odds WHERE be_match_id=:sid AND fetch_date=:fd"),
        # period=0 = 全场; 过滤半场/节盘(period>=1)避免盘口混入全场共识
        ("pinnacle",    "SELECT :uid, 'pinnacle', market_type||'_'||side, price, handicap FROM pinnacle_odds WHERE matchup_id=:sid AND fetch_date=:fd AND period=0"),
        ("bet365",      "SELECT :uid, 'bet365', market||'_'||outcome, odds_value, handicap FROM bet365_odds WHERE b365_event_id=:sid AND fetch_date=:fd"),
        ("flashscore",  "SELECT :uid, 'flashscore', market||'_'||outcome, odds_close, NULL FROM flashscore_odds_history WHERE flash_id=:sid AND fetch_date=:fd"),
        ("theodds",     "SELECT :uid, 'theodds', market||'_'||outcome, price, handicap FROM theodds_odds WHERE fixture_id=:sid AND fetch_date=:fd AND period=0"),
        # theodds_api: 商业API聚合 — 过滤 h2h_lay 卖盘，多庄家 AVG 形成共识赔率
        ("theodds_api", """
            SELECT :uid,'theodds_api',market||'_'||outcome,AVG(odds),point
            FROM theodds_api_odds
            WHERE event_id=:sid AND fetch_date=:fd
              AND market != 'h2h_lay'
              AND bookmaker IN ('bet365','betfair_ex_eu','betfair_ex_uk','unibet_eu','unibet')
            GROUP BY market, outcome, point HAVING COUNT(*)>=1
        """),
        # qiety_yb: match_date 是比赛日期（= fetch_date），不受 scrape_date 影响
        ("qiety_yb", """
            SELECT :uid, 'qiety_yb', 'moneyline_home', odds_home, NULL FROM multisource_odds
            WHERE match_id=:sid AND source LIKE 'qiety_yb%' AND match_date=:qd AND odds_type='1X2'
            UNION ALL
            SELECT :uid, 'qiety_yb', 'moneyline_draw', odds_draw, NULL FROM multisource_odds
            WHERE match_id=:sid AND source LIKE 'qiety_yb%' AND match_date=:qd AND odds_type='1X2' AND odds_draw IS NOT NULL
            UNION ALL
            SELECT :uid, 'qiety_yb', 'moneyline_away', odds_away, NULL FROM multisource_odds
            WHERE match_id=:sid AND source LIKE 'qiety_yb%' AND match_date=:qd AND odds_type='1X2'
            UNION ALL
            SELECT :uid, 'qiety_yb', 'spread_home', odds_home, CAST(handicap_line AS REAL) FROM multisource_odds
            WHERE match_id=:sid AND source LIKE 'qiety_yb%' AND match_date=:qd AND odds_type='asian_handicap'
            UNION ALL
            SELECT :uid, 'qiety_yb', 'spread_away', odds_away, CAST(handicap_line AS REAL) FROM multisource_odds
            WHERE match_id=:sid AND source LIKE 'qiety_yb%' AND match_date=:qd AND odds_type='asian_handicap'
            UNION ALL
            SELECT :uid, 'qiety_yb', 'total_over', over_odds, CAST(total_line AS REAL) FROM multisource_odds
            WHERE match_id=:sid AND source LIKE 'qiety_yb%' AND match_date=:qd AND odds_type='over_under' AND over_odds IS NOT NULL
            UNION ALL
            SELECT :uid, 'qiety_yb', 'total_under', under_odds, CAST(total_line AS REAL) FROM multisource_odds
            WHERE match_id=:sid AND source LIKE 'qiety_yb%' AND match_date=:qd AND odds_type='over_under' AND under_odds IS NOT NULL
        """),
        # okooo_jingcai: 直接读原始表，match_id是okooo自己的match_id(=上面
        # match_map[uid]["sources"]["okooo_jingcai"]存的src_id)，:fd=scrape_date
        # (跟sofascore/bet365等直接读原始表的源用同一个绑定，不用:qd)
        ("okooo_jingcai", """
            SELECT :uid, 'okooo_jingcai', 'moneyline_home', odds_1x2_home, NULL FROM okooo_football_odds
            WHERE match_id=:sid AND fetch_date=:fd
            UNION ALL
            SELECT :uid, 'okooo_jingcai', 'moneyline_draw', odds_1x2_draw, NULL FROM okooo_football_odds
            WHERE match_id=:sid AND fetch_date=:fd AND odds_1x2_draw IS NOT NULL
            UNION ALL
            SELECT :uid, 'okooo_jingcai', 'moneyline_away', odds_1x2_away, NULL FROM okooo_football_odds
            WHERE match_id=:sid AND fetch_date=:fd
            UNION ALL
            SELECT :uid, 'okooo_jingcai', 'spread_home', odds_ah_home, ah_line FROM okooo_football_odds
            WHERE match_id=:sid AND fetch_date=:fd AND odds_ah_home IS NOT NULL
            UNION ALL
            SELECT :uid, 'okooo_jingcai', 'spread_away', odds_ah_away, ah_line FROM okooo_football_odds
            WHERE match_id=:sid AND fetch_date=:fd AND odds_ah_away IS NOT NULL
        """),
    ]

    _SKIP_KW = ["booking", "card", "offside", "throw", "foul", "penalty_shootout", "lay"]

    # ── 主赔率来源：批量收集后单事务写入 ──
    main_batch = []
    for source_name, sql in odds_queries:
        src_id = sources.get(source_name)
        if not src_id:
            continue
        try:
            with engine.connect() as conn:
                # :fd = scrape_date（查源表），:qd = fetch_date（qiety_yb 用比赛日期）
                rows = conn.execute(text(sql), {"uid": unified_id, "sid": src_id, "fd": sd, "qd": fetch_date}).fetchall()
            weight = SOURCE_WEIGHTS.get(source_name, 0.5)
            for row in rows:
                uid, src, market_outcome, val, hc = row
                if val is None:
                    continue
                if source_name in ("pinnacle", "theodds"):
                    v = float(val)
                    if v > 0:
                        val = round(v / 100 + 1, 4)
                    elif v < 0:
                        val = round(100 / abs(v) + 1, 4)
                    else:
                        continue
                    # 极端美式赔率(如-1145/+5000)转换后是畸形十进制(<1.05或>50)，
                    # 这些不是真实可下注赔率，直接丢弃避免污染共识
                    if val < 1.05 or val > 50:
                        continue
                parts = market_outcome.rsplit("_", 1) if "_" in market_outcome else [market_outcome, ""]
                market  = parts[0]
                outcome = parts[1] if len(parts) > 1 else market_outcome
                if any(kw in market.lower() for kw in _SKIP_KW):
                    continue
                main_batch.append({
                    "uid": unified_id, "src": source_name,
                    "market": market, "outcome": outcome,
                    "val": float(val), "w": weight, "fd": fetch_date,
                    "hc": hc,
                })
        except Exception as e:
            if frozen:
                failures.append("source query/conversion failed")
            log.debug(f"  unified_odds写入异常[{source_name}]: {e}")

    # ── yb_corner: YB角球赔率 (chpid=114 大小球, 113 让球) ──
    # 主路径: sources["qiety_yb"] 直接对应 yb_corner_odds.match_id
    # 备用路径: 通过开赛时间关联（处理长/短 match_id 不一致）
    try:
        yb_mid = sources.get("qiety_yb")
        with engine.connect() as conn:
            if yb_mid:
                _crn_rows = conn.execute(text("""
                    SELECT chpid, hv, ott, odds FROM yb_corner_odds
                    WHERE match_id=:mid AND chpid IN ('113','114')
                """), {"mid": str(yb_mid)}).fetchall()
            else:
                _crn_rows = conn.execute(text("""
                    SELECT c.chpid, c.hv, c.ott, c.odds
                    FROM yb_corner_odds c
                    JOIN qiety_matches q ON q.match_id = c.match_id
                    JOIN unified_matches um ON um.unified_id = :uid
                    WHERE ABS(CAST(strftime('%s', q.kickoff_time) AS INTEGER)
                             - CAST(strftime('%s', um.kickoff_utc) AS INTEGER)) < 3600
                      AND q.sport_code = 'football'
                      AND c.chpid IN ('113','114')
                """), {"uid": unified_id}).fetchall()
        for _chpid, _hv, _ott, _odds in _crn_rows:
            if not _odds or _odds <= 1 or not _hv:
                continue
            _hv_safe = str(_hv).replace(".", "_")
            if _chpid == "114":
                _dir = "over" if _ott in ("大", "Over", "over", "O") else "under"
                _mkt = "corner_ou"
            else:
                _dir = "home" if _ott in ("主", "Home", "home") else "away"
                _mkt = "corner_hdp"
            main_batch.append({
                "uid": unified_id, "src": "yb_corner",
                "market": _mkt, "outcome": f"corner_{_dir}_{_hv_safe}",
                "val": float(_odds), "w": 0.85, "fd": fetch_date,
                "hc": float(_hv),
            })
    except Exception as e:
        if frozen:
            failures.append("yb corner query/conversion failed")
        log.debug(f"  yb_corner写入异常: {e}")

    # ── pinnacle_corner: Pinnacle角球赔率（通过 parent_matchup_id 关联主赛事） ──
    try:
        pinn_mid = sources.get("pinnacle")
        if pinn_mid:
            with engine.connect() as conn:
                _pc_rows = conn.execute(text("""
                    SELECT market_type, side, team_side, line, price_dec
                    FROM pinnacle_corner_odds
                    WHERE parent_matchup_id=CAST(:mid AS INTEGER)
                      AND fetch_date=:fd AND period=0 AND is_alternate=0
                      AND price_dec IS NOT NULL AND price_dec > 1.0
                """), {"mid": str(pinn_mid), "fd": sd}).fetchall()
            for _mtype, _side, _tside, _line, _price in _pc_rows:
                _mkt = "corner_ou" if _mtype == "total" else "corner_hdp"
                _outcome = f"corner_{_tside}_{_side}" if _tside else f"corner_{_side}"
                main_batch.append({
                    "uid": unified_id, "src": "pinnacle_corner",
                    "market": _mkt, "outcome": _outcome,
                    "val": float(_price), "w": SOURCE_WEIGHTS.get("pinnacle_corner", 1.00),
                    "fd": fetch_date, "hc": float(_line) if _line is not None else None,
                })
    except Exception as e:
        if frozen:
            failures.append("pinnacle corner query/conversion failed")
        log.debug(f"  pinnacle_corner写入异常: {e}")

    # ── scoremer: 实时角球赔率（按队名+日期匹配） ──
    try:
        with engine.connect() as conn:
            _sm_row = conn.execute(text("""
                SELECT home_team_std, away_team_std FROM unified_matches
                WHERE unified_id=:uid LIMIT 1
            """), {"uid": unified_id}).fetchone()
        if _sm_row:
            _ht6, _at6 = _sm_row[0][:6], _sm_row[1][:6]
            with engine.connect() as conn:
                _sm_rows = conn.execute(text("""
                    SELECT 'over' as dir, odds_over as odds, ft_corner_line as line
                    FROM corner_live_odds
                    WHERE home_team LIKE :ht AND away_team LIKE :at
                      AND fetch_date=:fd AND odds_over IS NOT NULL AND odds_over > 1.0
                    UNION ALL
                    SELECT 'under', odds_under, ft_corner_line
                    FROM corner_live_odds
                    WHERE home_team LIKE :ht AND away_team LIKE :at
                      AND fetch_date=:fd AND odds_under IS NOT NULL AND odds_under > 1.0
                """), {"ht": f"%{_ht6}%", "at": f"%{_at6}%", "fd": sd}).fetchall()
            for _dir, _odds, _line in _sm_rows:
                main_batch.append({
                    "uid": unified_id, "src": "scoremer",
                    "market": "corner_ou", "outcome": f"corner_{_dir}",
                    "val": float(_odds), "w": SOURCE_WEIGHTS.get("scoremer", 0.80),
                    "fd": fetch_date, "hc": float(_line) if _line is not None else None,
                })
    except Exception as e:
        if frozen:
            failures.append("scoremer corner query/conversion failed")
        log.debug(f"  scoremer_corner写入异常: {e}")

    if main_batch:
        try:
            with engine.begin() as conn:
                conn.execute(text("""
                    INSERT OR REPLACE INTO unified_odds
                    (unified_id,source,market,outcome,odds_value,weight,fetch_date,handicap)
                    VALUES (:uid,:src,:market,:outcome,:val,:w,:fd,:hc)
                """), main_batch)
            if frozen:
                _merge_frozen_unified(captured, main_batch, replace=True)
        except Exception as e:
            if frozen:
                failures.append("main write/commit or conflict key failed")
            log.debug(f"  unified_odds批量写入异常: {e}")

    # ── football-data.co.uk 历史赔率补充（只在无 b365/pinnacle 覆盖时） ──
    if frozen:
        existing_sources = {r["src"] for r in captured.values()}
    else:
        existing_sources = set()
        try:
            with engine.connect() as conn:
                ex_rows = conn.execute(text("""
                    SELECT DISTINCT source FROM unified_odds
                    WHERE unified_id=:uid AND fetch_date=:fd
                """), {"uid": unified_id, "fd": fetch_date}).fetchall()
            existing_sources = {r[0] for r in ex_rows}
        except Exception:
            pass

    # theodds 也是 Pinnacle Guest API，视为已有 pinnacle 覆盖
    _has_pinnacle = existing_sources & {"pinnacle", "theodds"}
    if "bet365" not in existing_sources and not _has_pinnacle:
        # 查 unified_matches 获取主客队名
        try:
            with engine.connect() as conn:
                m_row = conn.execute(text("""
                    SELECT home_team_std, away_team_std FROM unified_matches
                    WHERE unified_id=:uid LIMIT 1
                """), {"uid": unified_id}).fetchone()
            if m_row:
                # 2026-07-29修复：home_team_std/away_team_std可能是qiety_yb/
                # okooo_jingcai覆盖后的中文展示名，fd_matches存英文队名，
                # 先转英文再截取前6字符，见get_fotmob_shots_probs()同一处说明
                from team_mapping import team_en
                ht, at = team_en(m_row[0])[:6], team_en(m_row[1])[:6]
                fd_batch = []
                for fd_src, fd_sql in _FD_EXTRA_QUERIES:
                    try:
                        with engine.connect() as conn:
                            fd_rows = conn.execute(text(fd_sql),
                                {"uid": unified_id, "ht": f"%{ht}%", "at": f"%{at}%"}).fetchall()
                        weight = SOURCE_WEIGHTS.get(fd_src, 0.60)
                        for row in fd_rows:
                            _, src, market_outcome, val, hc = row
                            if val is None or float(val) <= 1.0:
                                continue
                            parts = market_outcome.rsplit("_", 1)
                            market, outcome = (parts[0], parts[1]) if len(parts) == 2 else (market_outcome, "")
                            fd_batch.append({"uid": unified_id, "src": src, "market": market,
                                             "outcome": outcome, "val": float(val), "w": weight,
                                             "fd": fetch_date, "hc": hc})
                    except Exception:
                        if frozen:
                            failures.append("FD query/conversion failed")
                        pass
                if fd_batch:
                    try:
                        with engine.begin() as conn:
                            _accepted = _write_frozen_ignore(conn, text("""
                                INSERT OR IGNORE INTO unified_odds
                                (unified_id,source,market,outcome,odds_value,weight,fetch_date,handicap)
                                VALUES (:uid,:src,:market,:outcome,:val,:w,:fd,:hc)
                            """), fd_batch, frozen=frozen)
                        if frozen:
                            _merge_frozen_unified(captured, _accepted, replace=False)
                    except Exception:
                        if frozen:
                            failures.append("FD write/commit or conflict key failed")
                        pass
        except Exception:
            if frozen:
                failures.append("FD supplement failed")
            pass

    # ── 多庄家赔率补充（multi_bookie_odds + betfair_exchange_odds，按队名匹配） ──
    try:
        with engine.connect() as conn:
            nm_row = conn.execute(text("""
                SELECT home_team_std, away_team_std FROM unified_matches
                WHERE unified_id=:uid LIMIT 1
            """), {"uid": unified_id}).fetchone()
        if nm_row:
            # 2026-07-29修复：multi_bookie_odds/betfair_exchange_odds存英文队名
            # (WH/DK/FD/Unibet/Bovada/Betfair都是英文语境书商)，中文展示名先
            # 转英文再截取，见get_fotmob_shots_probs()同一处说明
            from team_mapping import team_en
            ht6, at6 = team_en(nm_row[0])[:6], team_en(nm_row[1])[:6]
            # multi_bookie_odds — WH/DK/FD/Unibet/Bovada
            with engine.connect() as conn:
                mb_rows = conn.execute(text("""
                    SELECT source, market, selection, odds, handicap
                    FROM multi_bookie_odds
                    WHERE home_team LIKE :ht AND away_team LIKE :at
                      AND fetch_date=:fd AND odds > 1.0
                """), {"ht": f"%{ht6}%", "at": f"%{at6}%", "fd": sd}).fetchall()
            mb_batch = [
                {"uid": unified_id, "src": src, "market": mkt, "outcome": sel,
                 "val": float(val), "w": SOURCE_WEIGHTS.get(src, 0.70),
                 "fd": fetch_date, "hc": hc}
                for src, mkt, sel, val, hc in mb_rows
            ]
            # betfair_exchange_odds — 交易所背价
            with engine.connect() as conn:
                bf_rows = conn.execute(text("""
                    SELECT market_type, selection, back_price
                    FROM betfair_exchange_odds
                    WHERE (event_name LIKE :ht OR event_name LIKE :at)
                      AND fetch_date=:fd AND back_price > 1.0
                    LIMIT 50
                """), {"ht": f"%{ht6}%", "at": f"%{at6}%", "fd": sd}).fetchall()
            bf_batch = [
                {"uid": unified_id, "src": "betfair", "market": mkt or "moneyline",
                 "outcome": sel, "val": float(bp),
                 "w": SOURCE_WEIGHTS.get("betfair", 0.95), "fd": fetch_date, "hc": None}
                for mkt, sel, bp in bf_rows
            ]
            extra_batch = mb_batch + bf_batch
            if extra_batch:
                try:
                    with engine.begin() as conn:
                        _accepted = _write_frozen_ignore(conn, text("""
                            INSERT OR IGNORE INTO unified_odds
                            (unified_id,source,market,outcome,odds_value,weight,fetch_date,handicap)
                            VALUES (:uid,:src,:market,:outcome,:val,:w,:fd,:hc)
                        """), extra_batch, frozen=frozen)
                    if frozen:
                        _merge_frozen_unified(captured, _accepted, replace=False)
                except Exception:
                    if frozen:
                        failures.append("multi-bookmaker write/commit or conflict key failed")
                    pass
    except Exception as e:
        if frozen:
            failures.append("multi-bookmaker query/conversion failed")
        log.debug(f"  multi_bookie/betfair写入异常: {e}")
    if frozen:
        if failures:
            return _market_capture_result("FAILURE", reason="; ".join(failures))
        return _market_capture_result("SUCCESS" if captured else "EMPTY", captured.values())



# ─── 4. 共识赔率计算（加权调和平均 = 夏普权重） ──────────────────────────────

# FIX-016-5（2026-09-15）单源共识底线统计：source_count < CONSENSUS_MIN_SOURCES
# 的共识行实为一家赔率原样照抄、并非真正"共识"。逐行 source_count 已落库（标注），
# 此处仅做全阶段汇总计数（6线程并行调用，锁保护），阶段末统一打 WARNING——
# 不逐场报：历史数据显示约97%共识行天然单源，逐场 WARNING 会刷屏淹没真问题。
import threading as _threading
_CONSENSUS_SS_LOCK = _threading.Lock()
_CONSENSUS_SS_STATS = {"rows_total": 0, "rows_ss": 0, "uids": 0, "uids_all_ss": 0,
                       "sample_all_ss": []}


def _consensus_ss_reset():
    with _CONSENSUS_SS_LOCK:
        _CONSENSUS_SS_STATS.update(rows_total=0, rows_ss=0, uids=0, uids_all_ss=0)
        _CONSENSUS_SS_STATS["sample_all_ss"] = []


def _round_line(hc) -> float | None:
    """将盘口线规整到 0.25 的整数倍（消除浮点差异）"""
    if hc is None:
        return None
    return round(float(hc) * 4) / 4.0


def compute_consensus_odds(unified_id: str, fetch_date: str, *, unified_rows=None):
    """None keeps legacy SQL; an explicit empty sequence clears stale consensus."""
    try:
        result = _compute_consensus_odds_impl(unified_id, fetch_date, unified_rows)
    except Exception as exc:
        if unified_rows is None:
            raise
        result = _market_capture_result("FAILURE", reason="consensus: " + type(exc).__name__)
        log.warning("Frozen market input WARNING uid=%s: %s", unified_id, result["failure_reason"])
    return result if unified_rows is not None else None


def _compute_consensus_odds_impl(unified_id: str, fetch_date: str, unified_rows=None):
    """
    计算多源加权共识赔率并存储（含盘口线 handicap）。
    修复：让球/大小球必须按盘口线分组，不同盘口线不能合并平均。
    source_count 使用规范化来源去重：pinnacle 与 theodds 均为 Pinnacle Guest API，
    计为同一来源，避免双重计数导致分数虚高。
    """
    if unified_rows is None:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT market, outcome, odds_value, weight, handicap, source
                FROM unified_odds
                WHERE unified_id=:uid AND fetch_date=:fd
                  AND odds_value BETWEEN 1.01 AND 15.0
            """), {"uid": unified_id, "fd": fetch_date}).fetchall()

    else:
        if any(r["uid"] != unified_id or r["fd"] != fetch_date for r in unified_rows):
            raise ValueError("Mismatched frozen unified input")
        rows = [(r["market"], r["outcome"], r["val"], r["w"], r["hc"], r["src"])
                for r in unified_rows
                if r["uid"] == unified_id and r["fd"] == fetch_date
                and r["val"] is not None and 1.01 <= r["val"] <= 15.0]

    # 按 (market, outcome, 盘口线分组) 分组，同一规范化来源只保留权重最高的一条
    LINE_MARKETS = {"spread", "total", "team_total", "team_total_home", "team_total_away",
                    "handicap", "totals", "ah", "ou"}
    groups     = {}   # key → [(val, w)]
    src_groups = {}   # key → set of canonical source names (用于 source_count 去重)

    # 先按 key 聚合，同一 canonical source 保留权重最高的行
    _best_by_src = {}  # (key, canonical_src) → (val, w)
    for market, outcome, val, w, hc, src in rows:
        line = _round_line(hc) if market in LINE_MARKETS else None
        key  = (market, outcome, line)
        csrc = SOURCE_CANONICAL.get(src, src)  # 规范化来源名
        prev = _best_by_src.get((key, csrc))
        if prev is None or w > prev[1]:
            _best_by_src[(key, csrc)] = (val, w)

    for (key, csrc), (val, w) in _best_by_src.items():
        groups.setdefault(key, []).append((val, w))
        src_groups.setdefault(key, set()).add(csrc)

    # 对同一 (market, outcome) 如有多个盘口线，只保留来源数最多的一条（主盘口）
    # Bug修复：应比较规范化来源数 len(src_groups[key])，而非样本条数 len(vals)
    # 同源数时，有盘口线的优先于 None（Pinnacle 足球让球盘口字段未提取时为 None）
    best_per_mo = {}  # (market, outcome) → best_key
    for key in groups:
        mo = (key[0], key[1])
        prev = best_per_mo.get(mo)
        cur_nsrc  = len(src_groups.get(key, set()))
        if prev is None:
            best_per_mo[mo] = key
        else:
            prev_nsrc = len(src_groups.get(prev, set()))
            if cur_nsrc > prev_nsrc:
                best_per_mo[mo] = key
            elif cur_nsrc == prev_nsrc and key[2] is not None and prev[2] is None:
                best_per_mo[mo] = key  # 同源数：有盘口线的覆盖 None

    # 批量计算后单事务写入
    consensus_batch = []
    for key in set(best_per_mo.values()):
        market, outcome, consensus_hc = key
        vals = groups[key]
        if not vals:
            continue

        odds_list = [v for v, _ in vals]
        weights   = [w for _, w in vals]
        total_w   = sum(weights)
        consensus = sum(v * w for v, w in zip(odds_list, weights)) / total_w if total_w else sum(odds_list) / len(odds_list)
        sharp_odds   = odds_list[weights.index(max(weights))]
        implied_prob = round(1 / consensus, 4) if consensus else None
        # 用规范化来源去重后的数量（pinnacle + theodds = 1，不是 2）
        unique_src_count = len(src_groups.get(key, set()))

        consensus_batch.append({
            "uid": unified_id, "market": market, "outcome": outcome,
            "consensus": round(consensus, 4),
            "max_o": max(odds_list), "min_o": min(odds_list),
            "sharp": sharp_odds, "prob": implied_prob,
            "sc": unique_src_count, "fd": fetch_date, "hc": consensus_hc,
        })

    # FIX-016-5: 单源共识计数（阶段末统一汇总WARNING；source_count逐行落库即标注）
    _n_rows = len(consensus_batch)
    if _n_rows:
        _n_ss = sum(1 for r in consensus_batch if r["sc"] < CONSENSUS_MIN_SOURCES)
        with _CONSENSUS_SS_LOCK:
            _CONSENSUS_SS_STATS["rows_total"] += _n_rows
            _CONSENSUS_SS_STATS["rows_ss"] += _n_ss
            _CONSENSUS_SS_STATS["uids"] += 1
            if _n_ss == _n_rows:
                _CONSENSUS_SS_STATS["uids_all_ss"] += 1
                if len(_CONSENSUS_SS_STATS["sample_all_ss"]) < 8:
                    _CONSENSUS_SS_STATS["sample_all_ss"].append(unified_id)

    # Bug修复(2026-07-19)：以前只 INSERT OR REPLACE，从不清理该 unified_id 名下
    # 已不再由本次 unified_odds 产出的旧 (market,outcome) 组合——比如 team_total
    # 拆分成 team_total_home/away 后，旧的裸"team_total"行在 unified_odds 里已被
    # 清空，但 consensus_odds 里对应的旧行从未被删除，会永久残留成"看似有数据"
    # 的死数据，下游"球队大小"打分/展示逻辑还在读这个市场名，实际读到的是永远
    # 不会再刷新的陈旧值。改成每次先清空该 unified_id 的全部旧行，再整体重建，
    # 保证 consensus_odds 任何时候都是当次 unified_odds 的忠实重算结果。
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM consensus_odds WHERE unified_id=:uid"), {"uid": unified_id})
        if consensus_batch:
            conn.execute(text("""
                INSERT OR REPLACE INTO consensus_odds
                (unified_id,market,outcome,consensus_odds,max_odds,min_odds,
                 sharp_odds,implied_prob,source_count,fetch_date,handicap)
                VALUES
                (:uid,:market,:outcome,:consensus,:max_o,:min_o,
                 :sharp,:prob,:sc,:fd,:hc)
            """), consensus_batch)
    return _market_capture_result("SUCCESS" if consensus_batch else "EMPTY", consensus_batch)



# ─── 5. 命中评分 ─────────────────────────────────────────────────────────────
def compute_hit_score(unified_id: str, source_count: int,
                      model_prob: float, consensus_odds: float,
                      sharp_odds: float, source_count_odds: int,
                      market: str = "", outcome: str = "",
                      league_tier: str = "",
                      sport_code: str = "",
                      ignore_bias: bool = False) -> dict:
    """
    命中评分 = 数据覆盖度(30%) × 赔率一致性(30%) × 模型置信度(40%)
    P5增强：叠加市场偏置（按运动类型分流）和联赛Tier加成
    """
    # 数据覆盖度：分母2（系统最多2个实时赔率源，4要求不现实）
    # theodds=Pinnacle是最锐利赔率源，单源即可视为2档可信度
    coverage_score = 0.5 + min(source_count / 2.0, 1.0) * 0.5

    # 赔率一致性：分母2（同上，2源即满分）
    odds_consistency = 0.5 + min(source_count_odds / 2.0, 1.0) * 0.5

    # 模型置信度
    confidence_score = min(max(model_prob, 0.0), 1.0)

    hit_score = (
        coverage_score    * 0.30 +
        odds_consistency  * 0.30 +
        confidence_score  * 0.40
    )

    # ─── 校准惩罚：高隐含概率（热门）实测严重偏低 ───
    # 回测：隐含P=0.5-0.7 → 实际胜率仅21-24%（应为50-70%），庄家大幅高估热门
    # 通过 model_prob 近似隐含概率；>0.55时施加递增惩罚
    if model_prob > 0.55:
        calib_penalty = min(0.25, (model_prob - 0.55) * 1.0)
        hit_score *= (1.0 - calib_penalty)

    # ─── P5: 市场偏置（按运动类型分流）───
    bias_mult, market_min_threshold = get_market_bias(sport_code, market, outcome)
    # 小球转正：MARKET_BIAS里小球默认bias=0.0（策略锁定"只推大球"），但一直在
    # under_shadow_bets里结算追踪真实命中率/ROI，达标后动态改回中性倍率1.00，
    # 不用手动改MARKET_BIAS配置——用真实结算数据自动转正，是bias表以外的独立开关
    if outcome == "under" and (market in ("total", "team_total") or (market or "").startswith("team_total")) and bias_mult == 0.0:
        if _under_validation_status(sport_code)["validated"]:
            bias_mult = 1.00
    # 独赢转正：同一套思路，按(sport_code, outcome)分开判断——2026-07-24修复：
    # 之前只按sport聚合会让"篮球主胜"(真实结算-24.9%ROI)搭"篮球客胜"(+74.6%ROI)的车
    # 一起被放行，现在拆开后篮球主胜样本量/ROI不达标会自动保持bias=0（不进正式单，
    # 继续留在moneyline_shadow_full里观察），不需要额外硬编码排除。
    if market == "moneyline" and bias_mult == 0.0:
        if _moneyline_validation_status(sport_code, outcome)["validated"]:
            bias_mult = 1.00
    if not ignore_bias:
        hit_score *= bias_mult

    # ─── P5: 联赛 Tier 加成 ───
    tier_boost = LEAGUE_TIER_BOOST.get(league_tier, 1.00)
    hit_score *= tier_boost

    # 截断到 [0, 1]
    hit_score = round(min(max(hit_score, 0.0), 1.0), 4)

    # 价值边际（实际赔率 vs 公平赔率）
    fair_odds    = 1 / model_prob if model_prob > 0 else 999
    value_edge   = (consensus_odds / fair_odds) - 1.0 if fair_odds < 999 else 0.0

    # 凯利比例
    if model_prob > 0 and consensus_odds > 1:
        kelly = (model_prob * consensus_odds - 1) / (consensus_odds - 1)
        kelly = max(0.0, min(kelly * KELLY_FRACTION, KELLY_MAX_RATIO))
    else:
        kelly = 0.0

    # Bug3修复：Kelly=0 时 hit_score 折减 30%，使其难以越过推荐门槛
    # 避免"高覆盖度但无价值边际"的推荐堆积
    if kelly <= 0:
        hit_score = round(hit_score * 0.70, 4)

    confidence_label = (
        "高" if hit_score >= 0.75 else
        "中" if hit_score >= 0.60 else "低"
    )

    return {
        "hit_score":      hit_score,
        "value_edge":     round(value_edge, 4),
        "kelly_fraction": round(kelly, 4),
        "confidence":     confidence_label,
        "market_min_threshold": market_min_threshold,  # P5: 市场级门槛
    }


def compute_hit_score_v2(model_prob: float, implied_prob: float,
                          kelly_fraction: float, source_count: int) -> float:
    """
    V2公式（价值边际驱动，与 v1 并行运行用于对比复盘）：
      edge_score(50%)  = max(0, model_prob - implied_prob) / 0.20
      kelly_score(30%) = min(kelly_fraction / 0.05, 1.0)
      quality_score(20%) = min(source_count / 2.0, 1.0)  [无下限基底]
    阈值: HIT_SCORE_V2_THRESHOLD = 0.55
    """
    edge_score    = min(max(0.0, model_prob - implied_prob) / 0.20, 1.0)
    kelly_score   = min(kelly_fraction / 0.05, 1.0) if kelly_fraction > 0 else 0.0
    quality_score = min(source_count / 2.0, 1.0)
    hs = edge_score * 0.50 + kelly_score * 0.30 + quality_score * 0.20
    return round(min(max(hs, 0.0), 1.0), 4)


# ─── 6. 从已有预测模型读取概率 ───────────────────────────────────────────────
def _get_league_tier(league_name: str, sport_code: str = "") -> str:
    """根据联赛名称判断 Tier 等级（用于 P5 偏置加成）。关键词表集中在 config.py 管理。"""
    # 顶级国际赛事：专属 wc_boost（×1.10，移除普通联赛 tier3 的 ×0.88 惩罚，并额外加成）
    # 关键词表（FIFA/UEFA Euro/Copa America 等）均为足球赛事名，篮球同名赛事
    # （如 "FIBA - World Cup Africa Qualification"）不应被误判为顶级国际赛事
    name_lower_early = (league_name or "").lower()
    if (sport_code or "").lower() not in ("basketball", "basket") and \
       any(kw.lower() in name_lower_early for kw in LEAGUE_WC_BOOST_KEYWORDS):
        return "wc_boost"

    # 低流动性篮球联赛：名称含 "NBL" 但实为州级/低级联赛，必须在 tier2 匹配前拦截
    # 否则 "New Zealand - NBL" / "NBL1 North" 等会被 tier2 关键词 "NBL" 误捞起得到 ×1.03 加成
    if any(kw in name_lower_early for kw in LEAGUE_TIER_LOW_BBALL_KEYWORDS):
        return "tier3"

    name_lower = (league_name or "").lower()
    # Bug修复(2026-07-22)：审查_FOTMOB_LEAGUE_MAP假阳性问题时(见项目记忆
    # project_hit_rate_roi_audit_0722)发现同样的过宽关键词问题也存在于联赛tier
    # 分类里——"championship"/"mls"/裸国家名这类关键词会把杯赛/预备队/国际邀请赛
    # 误判成对应俱乐部联赛的tier，而tier_boost直接参与hit_score计算，误判会放大
    # 这些比赛的推荐权重。实测："USA - USL Championship"(美国低级别联赛，非英冠)、
    # "ASEAN Championship Women"(国际女足邀请赛)被误判tier2；"USA - MLS Next Pro
    # League"(美职联预备队)被'mls'关键词误判tier2；"Portugal - Taca de Portugal"/
    # "Ireland - FAI Cup"(葡萄牙杯/爱尔兰杯，杯赛不是联赛本身)被裸国家名关键词
    # "Portugal"/"Ireland"误判tier2。命中下面任一排除词就跳过tier1/tier2匹配，
    # 落到tier3/tier4判断（杯赛/预备队/青年队/女足邀请赛没有理由拿联赛本体的tier）。
    # 裸"championship"关键词跟_FOTMOB_LEAGUE_MAP同款问题(子串误配"USA - USL
    # Championship"这类完全不相关的联赛)，改成只认已验证的真实拼写(england -
    # championship这个完整短语，或数据源直接存字面量"championship"这个精确值)。
    if name_lower == "championship" or "england - championship" in name_lower:
        return "tier2"
    # "primera b"(2026-07-26新增排除)：阿根廷Primera B Metropolitana/Nacional两个
    # 联赛大样本回测(market=total,outcome=over真实下注方向)平注ROI分别是
    # -73.9%/-18.2%(各n=7)，不该拿tier1/tier2待遇。只从LEAGUE_TIER2_KEYWORDS删掉
    # "Primera B"不够——"...Nacional"这个变体名字里还带着"Nacional"关键词，会绕过
    # 删除继续命中tier2。必须在这里加排除，让两个变体都跳过tier1/tier2判断，
    # 落到下面的tier3默认档（不能删"Nacional"关键词本身，Puerto Rico - Superior
    # Nacional的真实数据显示tier2待遇对它是合适的，两个联赛不能共用同一把尺子）。
    if not any(kw in name_lower for kw in ("cup", "taca", "reserve", "next pro",
                                            " u19", " u20", " u21", " u23", "youth", "women",
                                            "primera b")):
        # "Premier League"/"Serie A"这类被全球地区级/低级联赛广泛借用命名的通用词，
        # 必须国家名也同时出现才算数(见config.py里LEAGUE_TIER1_QUALIFIED的说明)，
        # 不能只查联赛类型词本身——防止"Ecuador - Serie A"/"Australia - NorZone
        # Premier League"这类完全不相关的联赛蹭到英超/意甲的tier1待遇。
        for country_kw, league_kw in LEAGUE_TIER1_QUALIFIED:
            if country_kw in name_lower and league_kw in name_lower:
                return "tier1"
        for kw in LEAGUE_TIER1_KEYWORDS:
            if kw.lower() in name_lower:
                return "tier1"
        # 同上，"NBL"是被多国低级别篮球联赛借用的缩写，只有"australia"+"nbl"同时
        # 出现才算(见config.py里LEAGUE_TIER2_QUALIFIED)，防止"Uganda NBL"这类
        # 完全不相关的联赛蹭到tier2待遇。
        for country_kw, league_kw in LEAGUE_TIER2_QUALIFIED:
            if country_kw in name_lower and league_kw in name_lower:
                return "tier2"
        for kw in LEAGUE_TIER2_KEYWORDS:
            if kw.lower() in name_lower:
                return "tier2"
    # Tier3/Tier4: 根据是否有 "Division" / "Region" 等字样
    if any(k in name_lower for k in ["division", "region", "reserve", "youth", "u19", "u21", "u23"]):
        return "tier4"
    return "tier3"


def _get_bball_total_cap(league_name: str) -> float:
    """各篮球联赛大小球总分线合理上限（异常预警用），阈值表集中在 config.py 的 BBALL_TOTAL_CAP 管理。
    超过 cap × 1.05 的线视为定价异常，跳过大球改推反手小球。"""
    ln = (league_name or "").lower()
    if "new zealand" in ln and "nbl" in ln:
        return BBALL_TOTAL_CAP_NZ_NBL
    for kw, cap in BBALL_TOTAL_CAP.items():
        if kw in ln:
            return cap
    return BBALL_TOTAL_CAP_DEFAULT


def get_xg_model_probs(home: str, away: str, league_name: str = "") -> dict:
    """Understat xG → Poisson 胜平负+大小球概率（6大足球联赛，缓存加速）"""
    # 2026-07-29修复：understat_matches存英文队名，qiety_yb/okooo_jingcai中文
    # 展示名直接LIKE匹配永远配不上，见get_fotmob_shots_probs()同一处说明
    from team_mapping import team_en
    home, away = _model_team_en(home), _model_team_en(away)
    US_LEAGUE_MAP = [
        ('premier league', 'EPL'), ('england - premier', 'EPL'),
        ('la liga', 'La_Liga'), ('spain - la liga', 'La_Liga'),
        ('bundesliga', 'Bundesliga'), ('germany - bundesliga', 'Bundesliga'),
        ('serie a', 'Serie_A'), ('italy - serie a', 'Serie_A'),
        ('ligue 1', 'Ligue_1'), ('france - ligue 1', 'Ligue_1'),
        ('rfpl', 'RFPL'), ('russia - premier', 'RFPL'),
    ]
    lg_lower = (league_name or '').lower()
    us_league = next((code for kw, code in US_LEAGUE_MAP if kw in lg_lower), None)
    if not us_league:
        return {}

    def _team_xg(team: str, side: str):
        # 优先走缓存
        rows = _cache_lookup(_US_CACHE, us_league, team, side) if _CACHES_LOADED else []
        if not rows:
            # 回退 DB 查询
            col_for  = 'home_xg' if side == 'home' else 'away_xg'
            col_ag   = 'away_xg' if side == 'home' else 'home_xg'
            col_team = 'home_team' if side == 'home' else 'away_team'
            for chars in [6, 4]:
                try:
                    with engine.connect() as conn:
                        db_rows = conn.execute(text(f"""
                            SELECT {col_for}, {col_ag} FROM understat_matches
                            WHERE league=:lg AND is_result=1 AND {col_team} LIKE :t
                            ORDER BY match_datetime DESC LIMIT 15
                        """), {"lg": us_league, "t": f"%{team[:chars]}%"}).fetchall()
                    if db_rows:
                        rows = [(float(r[0]), float(r[1])) for r in db_rows
                                if r[0] is not None]
                        break
                except Exception:
                    pass
        if not rows:
            return None, None
        rows = rows[:15]
        xgf = [r[0] for r in rows]; xga = [r[1] for r in rows]
        return (sum(xgf)/len(xgf) if xgf else None,
                sum(xga)/len(xga) if xga else None)

    h_xgf, h_xga = _team_xg(home, 'home')
    a_xgf, a_xga = _team_xg(away, 'away')
    if h_xgf is None or a_xgf is None:
        return {}

    lam_h = (h_xgf + a_xga) / 2 * POISSON_HOME_ADV_XG
    lam_a = (a_xgf + h_xga) / 2
    return _poisson_probs(lam_h, lam_a)  # 含 home/draw/away/over/under


def get_national_team_probs(home: str, away: str, league_name: str = "") -> dict:
    """
    国家队 ELO + StatsBomb xG → Poisson 胜平负 + 大小球概率
    适用于: FIFA World Cup, UEFA Euro, Copa America, Nations League 等
    中立场地（无主场优势）
    """
    import math as _m2
    # 2026-07-29修复：national_team_elo/statsbomb_national_xg_teams存英文国家名，
    # 中文展示名(qiety_yb/okooo_jingcai)直接匹配配不上，见get_fotmob_shots_probs()
    from team_mapping import team_en
    home, away = _model_team_en(home), _model_team_en(away)

    # Bug修复：原来 LIKE '%team[:chars]%' 模糊子串匹配 + ORDER BY ... LIMIT 1，
    # 国家队名字大量共享子串（Korea北/南、Guinea/Guinea-Bissau/Equatorial Guinea/
    # Papua New Guinea、Congo/DR Congo、Sudan/South Sudan、Ireland/Northern Ireland
    # 实测都在 national_team_elo 里同时存在），搜"Guinea"这种短词会连带命中另外3个
    # 完全不同的国家，取到哪一个是SQL任意行序决定，等于经常算错对手实力。
    # 改为：先精确匹配，模糊匹配命中多国时用字符串相似度选最像的。
    def _elo(team: str):
        v = _nat_lookup(_NAT_ELO, team)
        if v is not None:
            return v
        try:
            with engine.connect() as conn:
                r = conn.execute(text("""
                    SELECT elo_rating FROM national_team_elo
                    WHERE LOWER(team_name) = LOWER(:t) ORDER BY fetch_date DESC LIMIT 1
                """), {"t": team}).fetchone()
            if r:
                return float(r[0])
        except Exception:
            pass
        for chars in [7, 6, 5, 4]:
            try:
                with engine.connect() as conn:
                    rows = conn.execute(text("""
                        SELECT team_name, elo_rating, fetch_date FROM national_team_elo
                        WHERE LOWER(team_name) LIKE LOWER(:t)
                    """), {"t": f"%{team[:chars]}%"}).fetchall()
                if not rows:
                    continue
                distinct = {r[0] for r in rows}
                if len(distinct) > 1:
                    best = max(distinct, key=lambda t: SequenceMatcher(None, t.lower(), team.lower()).ratio())
                    rows = [r for r in rows if r[0] == best]
                row = max(rows, key=lambda r: r[2])
                if row:
                    return float(row[1])
            except Exception:
                pass
        return None

    def _sb_xg(team: str):
        v = _nat_lookup(_NAT_XG, team)
        if v is not None:
            return v
        try:
            with engine.connect() as conn:
                r = conn.execute(text("""
                    SELECT avg_xg, avg_xga FROM statsbomb_national_xg_teams
                    WHERE LOWER(team_name) = LOWER(:t) ORDER BY rowid DESC LIMIT 1
                """), {"t": team}).fetchone()
            if r:
                return float(r[0]), float(r[1])
        except Exception:
            pass
        for chars in [7, 6, 5, 4]:
            try:
                with engine.connect() as conn:
                    rows = conn.execute(text("""
                        SELECT team_name, avg_xg, avg_xga, rowid FROM statsbomb_national_xg_teams
                        WHERE LOWER(team_name) LIKE LOWER(:t)
                    """), {"t": f"%{team[:chars]}%"}).fetchall()
                if not rows:
                    continue
                distinct = {r[0] for r in rows}
                if len(distinct) > 1:
                    best = max(distinct, key=lambda t: SequenceMatcher(None, t.lower(), team.lower()).ratio())
                    rows = [r for r in rows if r[0] == best]
                row = max(rows, key=lambda r: r[3])
                if row:
                    return float(row[1]), float(row[2])
            except Exception:
                pass
        return None, None

    elo_h = _elo(home)
    elo_a = _elo(away)
    xg_h, xga_h = _sb_xg(home)
    xg_a, xga_a = _sb_xg(away)

    if not elo_h and not xg_h:
        return {}

    result = {}

    # ELO → WDL（中立场地，无主场优势）
    if elo_h and elo_a:
        exp_h = 1.0 / (1.0 + 10.0 ** ((elo_a - elo_h) / 400.0))
        exp_a = 1.0 - exp_h
        # 平局概率：0.22~0.30，战力越接近平局越多
        draw_p = 0.24 + 0.08 * (1 - abs(exp_h - 0.5) * 2)
        result['home'] = round(exp_h * (1 - draw_p), 4)
        result['draw'] = round(draw_p, 4)
        result['away'] = round(exp_a * (1 - draw_p), 4)

    # StatsBomb xG → Poisson（攻防lambda）
    if xg_h is not None and xg_a is not None:
        lam_h = max(0.2, (xg_h + (xga_a if xga_a else xg_h)) / 2)
        lam_a = max(0.2, (xg_a + (xga_h if xga_h else xg_a)) / 2)
        p = _poisson_probs(lam_h, lam_a)
        if p:
            for k in ('over', 'under'):
                result.setdefault(k, p.get(k))
            # 若无ELO则补WDL
            for k in ('home', 'draw', 'away'):
                result.setdefault(k, p.get(k))
    elif elo_h and elo_a:
        # ELO无xG：用WC历史均值 1.25 进球/队 估算大小球
        avg_goals_wc = 1.25
        lam_h = max(0.2, avg_goals_wc * (1 + (elo_h - elo_a) / 2000.0))
        lam_a = max(0.2, avg_goals_wc * (1 - (elo_h - elo_a) / 2000.0))
        p = _poisson_probs(lam_h, lam_a)
        if p:
            result.setdefault('over',  p.get('over'))
            result.setdefault('under', p.get('under'))

    return {k: v for k, v in result.items() if v is not None}


def get_model_probs(unified_id: str, home: str, away: str,
                    league_name: str = "", sport_code: str = "",
                    book_probs: dict | None = None,
                    total_line: float | None = None,
                    team_total_line: float | None = None,
                    team_total_home_line: float | None = None,
                    team_total_away_line: float | None = None) -> dict:
    """
    标准K值融合概率口径：
        p_fusion = FUSION_W_BOOK × P_book
                 + FUSION_W_POISSON × P_poisson
                 + FUSION_W_ELO × P_elo

    - P_book    : 庄家隐含概率（1/consensus_odds），由调用方通过 book_probs 传入
    - P_poisson : 泊松/xG/射正多源融合模型概率（来源2-6.5）
    - P_elo     : ELO快照模型概率（来源1，market_prediction_snapshot）

    total_line/team_total_line: 该场比赛真实盘口的大小球/球队大小盘口线（来自
    consensus_odds.handicap）。不传时旧行为不变（大小球概率永远按固定2.5线/篮球
    "接近公平赔率2.0"的线计算）。传入时会按这条真实盘口线重新计算 over/under，
    避免P_book(真实线隐含概率)和P_poisson(固定线概率)对不上号——实测当日大小球
    盘口线里65%都不是2.5，这个错位过去一直存在。

    未命中分量时降级策略：
    - 缺 P_book：(W_POISSON + W_ELO) 按比例重新分配给 P_poisson / P_elo
    - 缺 P_elo ：(W_POISSON + W_ELO) 全给 P_poisson
    - 缺 P_poisson：(W_POISSON + W_ELO) 全给 P_elo
    - 三者全缺：返回空 dict
    """
    book_probs = book_probs or {}

    # ── P_elo：来源1 ELO快照（market_prediction_snapshot，缓存加速） ──
    elo_probs: dict = {}
    try:
        if _CACHES_LOADED:
            # O(1) 内存查找
            elo_probs = dict(_MPS_CACHE.get((home, away), {}))
            if not elo_probs:
                # 标准化队名后再试一次
                elo_probs = dict(_MPS_CACHE.get(
                    (home.lower().strip(), away.lower().strip()), {}))
        if not elo_probs:
            with engine.connect() as conn:
                rows = conn.execute(text("""
                    SELECT selection_name, model_prob
                    FROM market_prediction_snapshot
                    WHERE home_team_name_std = :home
                      AND away_team_name_std = :away
                      AND run_tag IN ('poisson_elo_v1', 'bball_elo_v1', 'poisson_elo_v2')
                    ORDER BY created_at DESC LIMIT 20
                """), {"home": home, "away": away}).fetchall()
                if rows:
                    elo_probs = {r[0]: float(r[1]) for r in rows}
    except Exception:
        pass

    # elo_probs 里的 "over"/"under" 也是不带盘口线的裸key（同一个"对不上真实线"的问题），
    # 但它同时存了 "over_1_5"/"over_2_5" 这种带线的key（_ou_from_lambdas() 写入的），
    # 有真实盘口线时找最接近的那个替换掉裸key，而不是放着不管
    if total_line is not None and elo_probs:
        _elo_lines = []
        for _k in elo_probs:
            if _k.startswith("over_"):
                try:
                    _elo_lines.append(float(_k[5:].replace("_", ".")))
                except ValueError:
                    pass
        if _elo_lines:
            _nearest = min(_elo_lines, key=lambda x: abs(x - total_line))
            _nk = f"over_{_nearest}".replace(".", "_")
            _nk_u = f"under_{_nearest}".replace(".", "_")
            if _nk in elo_probs:
                elo_probs["over"] = elo_probs[_nk]
            if _nk_u in elo_probs:
                elo_probs["under"] = elo_probs[_nk_u]

    # ── P_poisson：来源2-6.5 各泊松/xG模型，内部加权融合为单一概率 ──
    poisson_probs: dict = {}

    # 来源2: V2 泊松模型（足球）
    _football_totals_no_team_data = False  # 泊松无真实球队级信号（compute_advanced_poisson返回probs=None）时不算真实模型信号
    if sport_code in ("Soccer", "football", "soccer") and home and away:
        try:
            from poisson_model_v2 import compute_advanced_poisson, total_prob_at_line, _poisson_pmf as _poisson_pmf_v2
            # 2026-09-06曾尝试给这里接market_odds融合(思路同predict_football.py)，
            # 451场真实样本回测证实对这个模型是负面的，已撤销，见
            # poisson_model_v2.compute_advanced_poisson()docstring里的说明。
            r = compute_advanced_poisson(_model_team_en(home), _model_team_en(away), league_name)
            p = r["probs"]
            # 2026-08-24修改（用户明确要求，永久规则）：compute_advanced_poisson()
            # 不再用联赛均值给样本不足的球队兜底——球队自己主场/客场样本数不够时
            # 直接返回probs=None，这里如实按"泊松无真实信号"处理，不伪造数字
            # （旧逻辑靠"home_sample==0 and away_sample==0 and 联赛tier==2"这个
            # 更窄的条件判断，跟新的_compute_lambda()门槛已经对不上，改成直接看
            # probs是否为None，语义更准确）。
            if p is None:
                _football_totals_no_team_data = True
            else:
                for threshold in [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]:
                    poisson_probs[f"over_{threshold}"]  = p["over"][threshold]
                    poisson_probs[f"under_{threshold}"] = p["under"][threshold]
                # 按真实盘口线算：不再永远用固定2.5线（实测当日65%的真实盘口线不是2.5，
                # 硬编码2.5会导致P_book和P_poisson对不上号，见 total_prob_at_line 的说明）
                if total_line is not None and p.get("p_total"):
                    _po, _pu = total_prob_at_line(p["p_total"], total_line)
                    poisson_probs["over"], poisson_probs["under"] = _po, _pu
                else:
                    poisson_probs.setdefault("over",  p["over"][2.5])
                    poisson_probs.setdefault("under", p["under"][2.5])
                # team_total：主客队分开算，各自用自己的lambda + 各自的真实盘口线
                # （Pinnacle的team_total对主客队是两条独立market各自带线，见
                # 12_pinnacle_scraper.py的side修复，不再假设team_total永远是主队）
                _lam_h, _lam_a = r.get("lambda_home"), r.get("lambda_away")
                if team_total_home_line is not None and _lam_h is not None:
                    _th_p_total = {g: _poisson_pmf_v2(_lam_h, g) for g in range(11)}
                    _tpo, _tpu = total_prob_at_line(_th_p_total, team_total_home_line)
                    poisson_probs["team_total_home_over"], poisson_probs["team_total_home_under"] = _tpo, _tpu
                if team_total_away_line is not None and _lam_a is not None:
                    _ta_p_total = {g: _poisson_pmf_v2(_lam_a, g) for g in range(11)}
                    _tpo2, _tpu2 = total_prob_at_line(_ta_p_total, team_total_away_line)
                    poisson_probs["team_total_away_over"], poisson_probs["team_total_away_under"] = _tpo2, _tpu2
                # 裸 team_total_line（旧数据/未识别主客队来源）：向后兼容，仍按主队算
                if team_total_line is not None and _lam_h is not None:
                    _th_p_total2 = {g: _poisson_pmf_v2(_lam_h, g) for g in range(11)}
                    _tpo3, _tpu3 = total_prob_at_line(_th_p_total2, team_total_line)
                    poisson_probs["team_total_over"], poisson_probs["team_total_under"] = _tpo3, _tpu3
                for k in ("home", "draw", "away"):
                    poisson_probs.setdefault(k, p["1x2"][k])
                poisson_probs.setdefault("btts_yes", p["btts_yes"])
        except Exception:
            pass

    # 来源3: V2 正态模型（篮球）
    _bball_totals_tier = None  # 供下游排除逻辑用：篮球大小球这局是否有真实模型支撑
    if sport_code in ("Basketball", "basketball") and home and away:
        try:
            from basketball_normal_model import compute_basketball_probs, basketball_total_probs, compute_team_total_probs
            with engine.connect() as conn:
                fd_row = conn.execute(text("""
                    SELECT MAX(fetch_date) FROM unified_matches WHERE unified_id = :uid
                """), {"uid": unified_id}).fetchone()
                best_fd = fd_row[0] if fd_row and fd_row[0] else ""
            if best_fd:
                r = compute_basketball_probs(unified_id, best_fd)
                if r and "probs" in r:
                    _bball_totals_tier = r.get("tier")
                    # tier==3：country_hint是league_name整串误当country解析出来的畸形值，
                    # 查不到该联赛/该国家的真实样本，摔到"全球跨联赛混合均值"兜底——
                    # 这个数字对任何具体联赛都没有代表性（NBA夏季联赛实测country_hint=
                    # "nba 夏季联赛"，命中2515场全球混合样本，avg_total=178.5，既不是
                    # NBA真实水平也不是夏季联赛真实水平），不能当模型信号用，让来源3b
                    # (Basketball-Reference ORtg/DRtg，真实球队级数据)有机会通过.setdefault
                    # 接管，接管不了就彻底没有P_poisson，下游按"无模型支撑"直接排除
                    # （用户明确要求：无pace数据支撑、纯市场共识驱动的篮球大小球直接排除，
                    # 不要只是降权——2026-07-12 NBA夏季联赛"大球"推荐排查发现）
                    if _bball_totals_tier != 3:
                        # 按真实盘口线算：不再用"离公平赔率2.0最近"的那条自选线兜底
                        # （那条线跟真实下注的line大概率对不上，同样是P_book/P_poisson错位）
                        if total_line is not None:
                            _exact = basketball_total_probs(r["avg_total"], r["std_total"], thresholds=[total_line])
                            poisson_probs["over"]  = _exact["over"][total_line]
                            poisson_probs["under"] = _exact["under"][total_line]
                        else:
                            fair = r["probs"].get("fair_odds", {})
                            if fair:
                                best_line = min(fair.keys(), key=lambda x: abs(fair[x][0] - 2.0))
                                poisson_probs.setdefault("over",  r["probs"]["over"][best_line])
                                poisson_probs.setdefault("under", r["probs"]["under"][best_line])
            # team_total：主客队各自用自己近40场历史得分的均值/标准差单独建模，
            # 不再借用整场总分模型的分布（那是两队合计，口径对不上单队得分），
            # 也不再永远假设是主队（Pinnacle主客队team_total是两条独立market各自带线）
            if team_total_home_line is not None:
                _tt_h = compute_team_total_probs(home, team_total_home_line)
                if _tt_h:
                    poisson_probs["team_total_home_over"]  = _tt_h["over"]
                    poisson_probs["team_total_home_under"] = _tt_h["under"]
            if team_total_away_line is not None:
                _tt_a = compute_team_total_probs(away, team_total_away_line)
                if _tt_a:
                    poisson_probs["team_total_away_over"]  = _tt_a["over"]
                    poisson_probs["team_total_away_under"] = _tt_a["under"]
            # 裸 team_total_line（旧数据/未识别主客队来源）：向后兼容，仍按主队算
            if team_total_line is not None:
                _tt = compute_team_total_probs(home, team_total_line)
                if _tt:
                    poisson_probs["team_total_over"]  = _tt["over"]
                    poisson_probs["team_total_under"] = _tt["under"]
        except Exception:
            pass

    # 来源3b: Basketball-Reference ORtg/DRtg / 全联赛 offense_eff 模型
    if sport_code in ("Basketball", "basketball") and home and away:
        bb_p = get_bballref_model_probs(home, away, league_name)
        if bb_p:
            for k in ('home', 'away'):
                if k not in poisson_probs:
                    poisson_probs[k] = bb_p[k]
                else:
                    poisson_probs[k] = round(poisson_probs[k] * 0.60 + bb_p[k] * 0.40, 4)
            if 'exp_total' in bb_p:
                total     = bb_p['exp_total']
                lg_avg    = bb_p.get('league_avg_total', total)
                lg_std    = bb_p.get('league_std_total', BBALL_SIGMA_PACE)
                # 动态 O/U 线：以联赛场均总分为中心，±5/10/15 各档
                base_line = round(lg_avg / 5) * 5
                ou_lines  = sorted({base_line - 10, base_line - 5, base_line,
                                    base_line + 5, base_line + 10}) if base_line > 50 else []
                ou_lines  = [l + 0.5 for l in ou_lines]
                for line in ou_lines:
                    z = (line - total) / (lg_std * _math.sqrt(2))
                    u = round(0.5 * (1 + _math.erf(z)), 4)
                    poisson_probs.setdefault(f'over_{line}',  round(1 - u, 4))
                    poisson_probs.setdefault(f'under_{line}', u)
                if 'over' not in poisson_probs and total > 0:
                    best_line = round(total / 5) * 5 + 0.5
                    z0 = (best_line - total) / (lg_std * _math.sqrt(2))
                    u0 = round(0.5 * (1 + _math.erf(z0)), 4)
                    poisson_probs['over']  = round(1 - u0, 4)
                    poisson_probs['under'] = u0

    # 来源4: Understat xG（6大联赛，与泊松混合；含 over/under）
    if sport_code in ("Soccer", "football", "soccer") and home and away:
        xg_p = get_xg_model_probs(home, away, league_name)
        if xg_p:
            for k in ('home', 'draw', 'away', 'over', 'under'):
                if k not in xg_p:
                    continue
                if k in poisson_probs:
                    poisson_probs[k] = round(poisson_probs[k] * 0.60 + xg_p[k] * 0.40, 4)
                else:
                    poisson_probs[k] = xg_p[k]

    # 来源4.5: 国家队 ELO + StatsBomb xG（FIFA WC/UEFA Euro/Copa America 等国际赛事）
    _nat_kw = ['world cup', 'fifa', 'euro', 'copa america', 'nations league',
               'african cup', 'afcon', 'asian cup', 'gold cup', 'international']
    if (sport_code in ("Soccer", "football", "soccer") and home and away
            and any(kw in (league_name or '').lower() for kw in _nat_kw)):
        nat_p = get_national_team_probs(home, away, league_name)
        if nat_p:
            for k in ('home', 'draw', 'away'):
                if k in poisson_probs:
                    poisson_probs[k] = round(poisson_probs[k] * 0.50 + nat_p.get(k, 0) * 0.50, 4)
                elif k in nat_p:
                    poisson_probs[k] = nat_p[k]
            for k in ('over', 'under'):
                if k in nat_p:
                    poisson_probs.setdefault(k, nat_p[k])

    # 来源5: football-data.co.uk 射正 Poisson（18大联赛）
    if sport_code in ("Soccer", "football", "soccer") and home and away:
        fd_p = get_fd_stats_model_probs(home, away, league_name)
        if fd_p:
            for k in ('home', 'draw', 'away'):
                if k in poisson_probs:
                    poisson_probs[k] = round(poisson_probs[k] * 0.70 + fd_p[k] * 0.30, 4)
                else:
                    poisson_probs[k] = fd_p[k]
            # 射正模型 OU 精度低于 xG，仅作兜底（setdefault）
            for k in ('over', 'under'):
                if k in fd_p:
                    poisson_probs.setdefault(k, fd_p[k])

    # 来源6/6.2 FotMob xG + 射正模型：2026-07-20新增数据源，当天刚开始回填、
    # 零结算历史，按北极星原则（改动价值要能用历史回测证明，不能拍脑袋直接进正式
    # 融合）暂不直接混入 poisson_probs，改成跟LSTM信号同样的处理方式——只在Pass3
    # 影子桶(fotmob_1x2)里用blend后的概率单独打分、单独结算，见 get_fotmob_xg_probs()/
    # get_fotmob_shots_probs() 定义处的说明。真实结算证明有正向ROI后再考虑转正混入这里。

    # 来源6.5: football_xg_stats 三源融合（40+联赛兜底）
    if sport_code in ("Soccer", "football", "soccer") and home and away:
        if not poisson_probs.get('home'):
            fxg_p = get_football_xg_stats_probs(home, away, league_name)
            if fxg_p:
                for k in ('home', 'draw', 'away', 'over', 'under'):
                    poisson_probs.setdefault(k, fxg_p[k]) if k in fxg_p else None

    # 来源7: Transfermarkt 身价修正（±4%，缓存加速）
    if sport_code in ("Soccer", "football") and home and away and poisson_probs.get('home'):
        try:
            if _CACHES_LOADED:
                # 完整队名(不截断)优先，截断key跨联赛全球共用容易撞车(见_TM_CACHE_FULL的说明)
                hv = (_TM_CACHE_FULL.get(_norm6(home, 999))
                      or _TM_CACHE.get(_norm6(home)) or _TM_CACHE.get(_norm6(home, 4)))
                av = (_TM_CACHE_FULL.get(_norm6(away, 999))
                      or _TM_CACHE.get(_norm6(away)) or _TM_CACHE.get(_norm6(away, 4)))
            else:
                with engine.connect() as conn:
                    _hv = conn.execute(text("""
                        SELECT total_value_eur FROM transfermarkt_squad_values
                        WHERE team = :t ORDER BY season DESC LIMIT 1
                    """), {"t": home}).fetchone() or conn.execute(text("""
                        SELECT total_value_eur FROM transfermarkt_squad_values
                        WHERE team LIKE :t ORDER BY season DESC LIMIT 1
                    """), {"t": f"%{home[:6]}%"}).fetchone()
                    _av = conn.execute(text("""
                        SELECT total_value_eur FROM transfermarkt_squad_values
                        WHERE team = :t ORDER BY season DESC LIMIT 1
                    """), {"t": away}).fetchone() or conn.execute(text("""
                        SELECT total_value_eur FROM transfermarkt_squad_values
                        WHERE team LIKE :t ORDER BY season DESC LIMIT 1
                    """), {"t": f"%{away[:6]}%"}).fetchone()
                hv = float(_hv[0]) if _hv and _hv[0] else None
                av = float(_av[0]) if _av and _av[0] else None
            if hv and av and av > 0:
                adj = max(-0.04, min(0.04, _math.log(hv / av) * 0.06))
                poisson_probs['home'] = round(min(0.95, max(0.02, poisson_probs['home'] + adj)), 4)
                poisson_probs['away'] = round(min(0.95, max(0.02, poisson_probs['away'] - adj)), 4)
                # Bug修复：先 clamp draw 到 [0.02, 0.50]，再归一化
                # 避免 home/away 都被 max(0.02,…) 拉高后 sum > 1，导致 draw 算成负数
                if 'draw' in poisson_probs:
                    poisson_probs['draw'] = round(min(0.50, max(0.02, poisson_probs['draw'])), 4)
                    s = poisson_probs['home'] + poisson_probs['draw'] + poisson_probs['away']
                    if s > 0:
                        poisson_probs['home'] = round(poisson_probs['home'] / s, 4)
                        poisson_probs['draw'] = round(poisson_probs['draw'] / s, 4)
                        poisson_probs['away'] = round(poisson_probs['away'] / s, 4)
        except Exception:
            pass

    # 来源7.5: 角球负二项模型（football only）
    if sport_code in ("Soccer", "football", "soccer") and home and away:
        try:
            from corner_model import predict_corners
            _lc = ""
            for _bkw, _blc in [
                ("premier", "E0"), ("bundesliga 2", "D2"), ("bundesliga", "D1"),
                ("la liga", "SP1"), ("serie a", "I1"), ("ligue 1", "F1"),
                ("eredivisie", "N1"), ("primeira", "P1"), ("super lig", "T1"),
            ]:
                if _bkw in (league_name or "").lower():
                    _lc = _blc
                    break
            crn = predict_corners(home, away, league_code=_lc, league_name=league_name)
            if crn:
                for _line in [8.5, 9.5, 10.5, 11.5, 12.5]:
                    _lk = str(_line).replace(".", "_")
                    _ov = crn.get(f"over_{_lk}")
                    _un = crn.get(f"under_{_lk}")
                    if _ov is not None:
                        poisson_probs[f"corner_over_{_lk}"]  = _ov
                        poisson_probs[f"corner_under_{_lk}"] = _un
        except Exception:
            pass

    # ── 三分量 K值融合：p_fusion = W_BOOK×P_book + W_POISSON×P_poisson + W_ELO×P_elo ──
    all_keys = set(book_probs) | set(poisson_probs) | set(elo_probs)
    fused: dict = {}
    # 大小球(over/under)如果没有真实模型支撑、只剩P_book，记下来供下游"无独立模型
    # 支撑、纯市场共识驱动直接排除"用（CLAUDE.md"推荐单数据支撑规则"永久规则，
    # 2026-07-12 NBA夏季联赛"大球"推荐排查后用户明确要求，同日扩展到足球）：
    #   篮球：P_poisson/P_elo 两个模型分量全缺（basketball_normal_model.py 摔到tier=3
    #        全局兜底时不再写入poisson_probs，见来源3的处理）
    #   足球：球队级(home_sample/away_sample)和联赛基线级(league_baseline tier)
    #        两级都没有真实样本支撑（_football_totals_no_team_data），且没有P_elo兜底
    _totals_book_only: set = set()
    for k in all_keys:
        pb  = book_probs.get(k)      # P_book
        pp  = poisson_probs.get(k)   # P_poisson
        pe  = elo_probs.get(k)       # P_elo

        has_b = pb is not None and pb > 0
        has_p = pp is not None and pp > 0
        has_e = pe is not None and pe > 0

        if not (has_b or has_p or has_e):
            continue

        # Bug修复(2026-07-19)：这里只检查裸key(="over"/"under")，team_total家族的
        # key是"team_total_over"/"team_total_home_over"/"team_total_away_under"这种
        # 带前缀的形式，永远匹配不上"k in ('over','under')"，导致CLAUDE.md"推荐单数据
        # 支撑规则"永久规则实际只对全场大小球(total)生效，球队大小(team_total及其
        # home/away变体)完全没有这道"纯market-only直接排除"的检查——两个模型分量都
        # 缺失、p_fusion等于纯P_book的球队大小候选会悄悄混进推荐池，跟规则原意矛盾。
        _is_totals_key = k in ("over", "under") or (
            k.startswith("team_total") and k.rsplit("_", 1)[-1] in ("over", "under"))
        if _is_totals_key and has_b and not has_e:
            if sport_code in ("Basketball", "basketball") and not has_p:
                _totals_book_only.add(k)
            elif (sport_code in ("Soccer", "football", "soccer")
                    and _football_totals_no_team_data):
                _totals_book_only.add(k)

        if has_b and has_p and has_e:
            # 标准三分量融合
            val = FUSION_W_BOOK * pb + FUSION_W_POISSON * pp + FUSION_W_ELO * pe
        elif has_b and (has_p or has_e):
            # 缺一个模型分量：将剩余权重合并
            model_val = (pp if has_p else 0) * FUSION_W_POISSON + (pe if has_e else 0) * FUSION_W_ELO
            model_w   = (FUSION_W_POISSON if has_p else 0) + (FUSION_W_ELO if has_e else 0)
            val = FUSION_W_BOOK * pb + model_val / model_w * (1 - FUSION_W_BOOK) if model_w else pb
        elif has_p or has_e:
            # 无 P_book：纯模型融合
            if has_p and has_e:
                w_total = FUSION_W_POISSON + FUSION_W_ELO
                val = (FUSION_W_POISSON * pp + FUSION_W_ELO * pe) / w_total
            else:
                val = pp if has_p else pe
        else:
            val = pb  # 仅有庄家概率

        fused[k] = round(min(0.99, max(0.01, val)), 4)

    if _totals_book_only:
        fused["_totals_book_only"] = _totals_book_only

    return fused


def get_fd_stats_model_probs(home: str, away: str, league_name: str = "") -> dict:
    """基于 football-data.co.uk 射正数据 → Poisson 胜平负 + 大小球概率（18大欧洲联赛）"""
    import math
    # 2026-07-29修复：fd_matches存英文队名，见get_fotmob_shots_probs()同一处说明
    from team_mapping import team_en
    home, away = _model_team_en(home), _model_team_en(away)

    FD_LEAGUE_KEYWORDS = {
        'premier league':       'England - Premier League',
        'england - premier':    'England - Premier League',
        'championship':         'England - Championship',
        'england - championship': 'England - Championship',
        'league one':           'England - League One',
        'league two':           'England - League Two',
        'bundesliga 2':         'Germany - Bundesliga 2',
        'bundesliga':           'Germany - Bundesliga',
        'germany - bundesliga': 'Germany - Bundesliga',
        'la liga':              'Spain - La Liga',
        'segunda':              'Spain - Segunda',
        'spain - segunda':      'Spain - Segunda',
        'serie a':              'Italy - Serie A',
        'italy - serie a':      'Italy - Serie A',
        'serie b':              'Italy - Serie B',
        'ligue 1':              'France - Ligue 1',
        'france - ligue 1':     'France - Ligue 1',
        'ligue 2':              'France - Ligue 2',
        'eredivisie':           'Netherlands - Eredivisie',
        'jupiler':              'Belgium - Jupiler Pro League',
        'primeira liga':        'Portugal - Primeira Liga',
        'liga portugal':        'Portugal - Primeira Liga',
        'portugal - primeiro':  'Portugal - Primeira Liga',
        'scotland - premier':   'Scotland - Premiership',
        'premiership':          'Scotland - Premiership',
        'super lig':            'Turkey - Super Lig',
        'turkey - super':       'Turkey - Super Lig',
        'super league':         'Greece - Super League',
        'greece - super':       'Greece - Super League',
    }

    lg_lower = (league_name or '').lower()
    fd_league = next((v for kw, v in FD_LEAGUE_KEYWORDS.items() if kw in lg_lower), None)
    if not fd_league:
        return {}

    conv = _FD_CONV.get(fd_league, 0.32) if _CACHES_LOADED else 0.32

    def _team_lambda(team: str, side: str):
        # 缓存优先
        sot_list = _cache_lookup(_FD_CACHE, fd_league, team, side) if _CACHES_LOADED else []
        if sot_list:
            sot = sot_list[:20]
            avg_sot = sum(sot) / len(sot)
            return avg_sot * conv

        col_sot  = 'home_shots_target' if side == 'home' else 'away_shots_target'
        col_team  = 'home_team' if side == 'home' else 'away_team'
        for chars in [6, 4]:
            try:
                with engine.connect() as conn:
                    rows = conn.execute(text(f"""
                        SELECT {col_sot} FROM fd_matches
                        WHERE league_name=:lg AND {col_team} LIKE :t
                          AND {col_sot} IS NOT NULL
                        ORDER BY match_date DESC LIMIT 20
                    """), {"lg": fd_league, "t": f"%{team[:chars]}%"}).fetchall()
                    if rows:
                        sot = [float(r[0]) for r in rows if r[0] is not None]
                        if sot:
                            c = _FD_CONV.get(fd_league) or 0.32
                            return sum(sot) / len(sot) * c
            except Exception:
                pass
        return None

    lam_h = _team_lambda(home, 'home')
    lam_a = _team_lambda(away, 'away')
    if lam_h is None or lam_a is None:
        return {}

    lam_h = max(0.1, min(lam_h * POISSON_HOME_ADV_SOT, 5.0))
    lam_a = max(0.1, min(lam_a, 5.0))
    return _poisson_probs(lam_h, lam_a)


# FotMob联赛名映射：项目内league_name关键词 → 43_fotmob_match_data_scraper.py的LEAGUES标准名。
# 提到模块级供 get_fotmob_xg_probs / get_fotmob_shots_probs 共用，避免重复维护两份。
# 优先匹配"国家 - 联赛"这种项目内常见完整格式，再退到宽泛关键词，
# 避免"serie a/serie b/super league"这类词跨国家撞车。
_FOTMOB_LEAGUE_MAP = [
    ('argentina - copa de la liga',  'Argentina - Copa de la Liga Profesional'),
    ('argentina - liga profesional', 'Argentina - Liga Profesional'),
    ('argentina - primera',          'Argentina - Liga Profesional'),
    ('australia - a-league women',   'Australia - A-League Women'),
    ('australia - a-league',         'Australia - A-League'),
    ('austria',                      'Austria - Bundesliga'),
    ('belgium - first division a',   'Belgium - First Division A'),
    ('belgium - first division b',   'Belgium - First Division B'),
    ('brazil - paulista',            'Brazil - Paulista A1'),
    ('brazil - serie a',             'Brazil - Serie A'),
    ('brazil - serie b',             'Brazil - Serie B'),
    ('brasileirao',                  'Brazil - Serie A'),
    ('colombia - primera',           'Colombia - Primera A'),
    ('denmark',                      'Denmark - Superligaen'),
    ('egypt',                        'Egypt - Premier League'),
    ('england - championship',       'England - Championship'),
    ('england - league one',         'England - League One'),
    ('england - league two',         'England - League Two'),
    ('wsl',                          'England - WSL'),
    ('france - ligue 2',             'France - Ligue 2'),
    ('france - premiere ligue',      'France - Premiere Ligue Feminine'),
    ('germany - 2-bundesliga',       'Germany - 2. Bundesliga'),
    ('germany - 2. bundesliga',      'Germany - 2. Bundesliga'),
    ('greece',                       'Greece - Super League 1'),
    ('india - super league',         'India - Super League'),
    ('champions league',             'Europe - Champions League'),
    ('conference league',            'Europe - Conference League'),
    ('libertadores',                 'International - Copa Libertadores'),
    ('europa league',                'Europe - Europa League'),
    ('nations league',               'International - UEFA Nations League B'),
    ('women - euro',                 "International - Women's EURO"),
    ('ireland',                      'Ireland - Premier Division'),
    ('italy - serie b',              'Italy - Serie B'),
    ('japan',                        'Japan - J1 League'),
    ('j1 league',                    'Japan - J1 League'),
    ('mexico',                       'Mexico - Liga MX'),
    ('liga mx',                      'Mexico - Liga MX'),
    ('eredivisie',                   'Netherlands - Eredivisie'),
    ('norway',                       'Norway - Eliteserien'),
    ('eliteserien',                  'Norway - Eliteserien'),
    ('poland',                       'Poland - Ekstraklasa'),
    ('ekstraklasa',                  'Poland - Ekstraklasa'),
    ('portugal',                     'Portugal - Primeira Liga'),
    ('primeira liga',                'Portugal - Primeira Liga'),
    ('saudi',                        'Saudi Arabia - Pro League'),
    ('scotland - swpl',              'Scotland - SWPL 1'),
    ('scotland',                     'Scotland - Premiership'),
    ('south africa',                 'South Africa - Premier Soccer League'),
    ('laliga2',                      'Spain - LaLiga2'),
    ('la liga2',                     'Spain - LaLiga2'),
    ('allsvenskan',                  'Sweden - Allsvenskan'),
    ('switzerland',                  'Switzerland - Super League'),
    ('thailand',                     'Thailand - Thai League'),
    ('turkey',                       'Turkey - Super Lig'),
    ('super lig',                    'Turkey - Super Lig'),
    ('mls',                          'USA - MLS'),
    ('nwsl',                         'USA - NWSL'),
    ('china',                        'China - Super League'),
    ('k league',                     'South Korea - K League 1'),
    ('k-league',                     'South Korea - K League 1'),
    # 五大联赛+俄超(2026-07-21新增，见43_fotmob_match_data_scraper.py头部说明)。
    # 特意追加在列表末尾（不是开头）：_fotmob_league_lookup()用next()取第一个匹配，
    # 放末尾保证不会跟上面已存在的更具体条目(如'laliga2'/'la liga2')抢先匹配，
    # 关键词照抄_LEAGUE_ZH里对应这几个联赛的真实league_name前缀写法，不是凭空猜测。
    ('england - premier',            'England - Premier League'),
    ('spain - la liga',              'Spain - LaLiga'),
    ('italy - serie a',              'Italy - Serie A'),
    ('germany - bundesliga',         'Germany - Bundesliga'),
    ('france - ligue 1',             'France - Ligue 1'),
    ('russia - premier',             'Russia - Premier League'),
    # Bug修复(2026-07-22)：排查角球影子桶为何对美职联(MLS)/五大联赛完全打不到信号时
    # 发现，unified_matches.league_name 因数据源不同存在好几套完全不重叠的拼写
    # 惯例——除了上面已覆盖的"England - Premier League"这套，实测同一天数据库里
    # 还同时存在"USA - Major League Soccer"(Pinnacle惯例，跟已有关键词'mls'不
    # 匹配)、"Bundesliga - Germany"/"La Liga - Spain"/"Ligue 1 - France"/
    # "Serie A - Italy"(倒序拼写)、以及"bundesliga"/"csl"/"j1"/"k_league_1"/
    # "laliga"/"liga_argentina"/"ligue_1"/"premier_league"/"rpl"/"serie_a"/
    # "serie_a_br"/"super_lig"/"ucl"/"uecl"/"uel"(纯小写短代码，另一数据源惯例)。
    # 逐条用今日真实unified_matches数据核对过对应的都是真实五大联赛/欧战/MLS等
    # FotMob覆盖的顶级联赛比赛（如"bundesliga"→Bayern Munich vs Stuttgart），
    # 不是巧合命中别的联赛。'serie_a_br'必须排在'serie_a'前面（next()取第一个
    # 匹配，'serie_a_br'包含'serie_a'子串，顺序反了会把巴甲错判成意甲）。
    ('usa - major league soccer',    'USA - MLS'),
    ('bundesliga - germany',         'Germany - Bundesliga'),
    ('la liga - spain',              'Spain - LaLiga'),
    ('ligue 1 - france',             'France - Ligue 1'),
    ('serie a - italy',              'Italy - Serie A'),
    ('serie_a_br',                   'Brazil - Serie A'),
    ('bundesliga',                   'Germany - Bundesliga'),
    ('csl',                          'China - Super League'),
    ('j1',                           'Japan - J1 League'),
    ('k_league_1',                   'South Korea - K League 1'),
    ('laliga',                       'Spain - LaLiga'),
    ('liga_argentina',               'Argentina - Liga Profesional'),
    ('ligue_1',                      'France - Ligue 1'),
    ('premier_league',               'England - Premier League'),
    ('rpl',                          'Russia - Premier League'),
    ('serie_a',                      'Italy - Serie A'),
    ('super_lig',                    'Turkey - Super Lig'),
    ('ucl',                          'Europe - Champions League'),
    ('uecl',                         'Europe - Conference League'),
    ('uel',                          'Europe - Europa League'),
]


# Bug修复(2026-07-22)：排查_FOTMOB_LEAGUE_MAP假阳性时发现好几个宽泛的国家名/
# 短语关键词会连带匹配到该国的杯赛/次级梯队/女足变体，误配到FotMob完全不同的
# 联赛（实测当天真实unified_matches数据）：'china'→"China - FA Cup"、'colombia'→
# "Colombia - Cup"/"Copa Colombia"、'scotland'→"Scotland - League Cup"、'india'→
# "India - Calcutta Premier Division"、'argentina - primera'→"Argentina - Primera
# Division Women"、'champions league'→"Champions League Women"、'mls'→"USA - MLS
# Next Pro League"、'championship'→"ASEAN Championship Women"/"USA - USL
# Championship"。FotMob的LEAGUES字典（43_fotmob_match_data_scraper.py）里没有任何
# 杯赛/预备队/青年队联赛，这些变体不该匹配到任何FotMob联赛；女足变体只能匹配
# FotMob本身也是女足的联赛。'india - super league'/'colombia - primera'已经改成
# 更精确的短语避免命中对应国家的杯赛；'championship'裸关键词改成精确相等匹配
# （已有'england - championship'短语条目覆盖完整拼写，裸'championship'只用来兜底
# 某些数据源直接存字面量"championship"这个短代码，不该再用子串方式命中"USA - USL
# Championship"/"ASEAN Championship Women"这类不相关的更长字符串）。
_FOTMOB_LEAGUE_EXACT_MAP = {
    "championship": "England - Championship",
}
_FOTMOB_LEAGUE_EXCLUDE_SUBSTR = ("cup", "reserve", "next pro", " u20", " u23", "youth")
_FOTMOB_WOMEN_LEAGUES = {
    "Australia - A-League Women", "England - WSL",
    "France - Premiere Ligue Feminine", "International - Women's EURO",
}


def _fotmob_league_lookup(league_name: str):
    lg_lower = (league_name or '').lower()
    if lg_lower in _FOTMOB_LEAGUE_EXACT_MAP:
        return _FOTMOB_LEAGUE_EXACT_MAP[lg_lower]
    if any(kw in lg_lower for kw in _FOTMOB_LEAGUE_EXCLUDE_SUBSTR):
        return None
    for kw, code in _FOTMOB_LEAGUE_MAP:
        if kw in lg_lower:
            if "women" in lg_lower and code not in _FOTMOB_WOMEN_LEAGUES:
                continue
            return code
    return None


def get_fotmob_shots_probs(home: str, away: str, league_name: str = "") -> dict:
    """FotMob 射正数据 → Poisson 胜平负 + 大小球概率（跟get_fd_stats_model_probs思路一致，
    只是数据源/覆盖联赛不同，两者互相独立、都是"来源6"xG信号之外的补充信号，
    见43_fotmob_match_data_scraper.py）"""
    # 2026-07-29修复：fotmob_matches/fotmob_match_team_stats存的是英文队名，
    # 但qiety_yb/okooo_jingcai接入的比赛home/away是中文展示名优先——不转英文
    # 直接LIKE匹配永远配不上，这类比赛会静默拿不到FotMob信号。
    # 2026-09-12改为_model_team_en()(精确词典命中才翻译，无模糊回退)：
    # team_en()的模糊回退曾把"塞维利亚"错译成国家队"serbia"，
    # 错队的统计比"无信号"危害更大(违反推荐单数据支撑永久规则)。
    from team_mapping import team_en
    home, away = _model_team_en(home), _model_team_en(away)
    fm_league = _fotmob_league_lookup(league_name)
    if not fm_league:
        return {}

    conv = _FM_SOT_CONV.get(fm_league, 0.32) if _CACHES_LOADED else 0.32

    def _team_lambda(team: str, side: str):
        sot_list = _cache_lookup(_FM_SOT_CACHE, fm_league, team, side) if _CACHES_LOADED else []
        if sot_list:
            sot = sot_list[:20]
            return sum(sot) / len(sot) * conv

        col_team = 'home_team' if side == 'home' else 'away_team'
        try:
            for chars in [6, 4]:
                with engine.connect() as conn:
                    rows = conn.execute(text(f"""
                        SELECT s.shots_on_target
                        FROM fotmob_match_team_stats s
                        JOIN fotmob_matches m ON m.match_id=s.match_id
                        WHERE m.league_name=:lg AND s.side=:side AND m.{col_team} LIKE :t
                          AND s.shots_on_target IS NOT NULL
                        ORDER BY m.match_date DESC LIMIT 20
                    """), {"lg": fm_league, "side": side, "t": f"%{team[:chars]}%"}).fetchall()
                if rows:
                    sot = [float(r[0]) for r in rows if r[0] is not None]
                    if sot:
                        c = _FM_SOT_CONV.get(fm_league) or 0.32
                        return sum(sot) / len(sot) * c
        except Exception:
            pass
        return None

    lam_h = _team_lambda(home, 'home')
    lam_a = _team_lambda(away, 'away')
    if lam_h is None or lam_a is None:
        return {}

    lam_h = max(0.1, min(lam_h * POISSON_HOME_ADV_SOT, 5.0))
    lam_a = max(0.1, min(lam_a, 5.0))
    return _poisson_probs(lam_h, lam_a)


def get_fotmob_xg_probs(home: str, away: str, league_name: str = "") -> dict:
    """FotMob xG → Poisson 胜平负 + 大小球（fbref schedule页xG字段2026-07-20确认失效后的
    替代源，覆盖Understat已有的五大联赛+俄超之外的50+联赛/国际赛事，见43_fotmob_match_data_scraper.py）"""
    # 2026-07-29修复：见get_fotmob_shots_probs()同一处说明，中文队名转英文再匹配
    from team_mapping import team_en
    home, away = _model_team_en(home), _model_team_en(away)
    fb_league = _fotmob_league_lookup(league_name)
    if not fb_league:
        return {}

    def _team_xg(team, side):
        # 缓存优先
        rows = _cache_lookup(_FM_CACHE, fb_league, team, side) if _CACHES_LOADED else []
        if not rows:
            col_f = 'home_xg' if side == 'home' else 'away_xg'
            col_a = 'away_xg' if side == 'home' else 'home_xg'
            col_t = 'home_team' if side == 'home' else 'away_team'
            for chars in [6, 4]:
                try:
                    with engine.connect() as conn:
                        db_rows = conn.execute(text(f"""
                            SELECT {col_f}, {col_a} FROM fotmob_matches
                            WHERE league_name=:lg AND {col_t} LIKE :t
                              AND {col_f} IS NOT NULL
                            ORDER BY match_date DESC LIMIT 15
                        """), {"lg": fb_league, "t": f"%{team[:chars]}%"}).fetchall()
                    if db_rows:
                        rows = [(float(r[0]), float(r[1])) for r in db_rows if r[0]]
                        break
                except Exception:
                    pass
        if not rows:
            return None, None
        rows = rows[:15]
        xgf = [r[0] for r in rows]; xga = [r[1] for r in rows]
        return (sum(xgf)/len(xgf) if xgf else None,
                sum(xga)/len(xga) if xga else None)

    h_xgf, h_xga = _team_xg(home, 'home')
    a_xgf, a_xga = _team_xg(away, 'away')
    if h_xgf is None or a_xgf is None:
        return {}

    lam_h = max(0.1, (h_xgf + a_xga) / 2 * POISSON_HOME_ADV_SOT)
    lam_a = max(0.1, (a_xgf + h_xga) / 2)
    return _poisson_probs(lam_h, lam_a)


def get_qiety_h2h_probs(qiety_mid: str, sport_code: str, fetch_date: str, next_date: str) -> dict:
    """企鹅体育两队历史交锋(46_qiety_lineup_scraper.py写入的qiety_h2h_history，
    relation='h2h') → 经验胜率信号。用sources["qiety_yb"]给的match_id直接关联，
    不做队名模糊匹配——qiety_matches.home_team/away_team和qiety_h2h_history里的
    队名都来自企鹅体育同一个接口，字符串精确相等即可判断是不是当前这两队的交锋记录，
    避免team_mapping那类跨数据源撞名风险([[feedback_team_name_collision]])。
    样本<2场历史交锋时返回{}（数据不足，不用50/50兜底冒充信号，
    符合CLAUDE.md推荐单数据支撑规则）。"""
    if not qiety_mid:
        return {}
    try:
        with engine.connect() as conn:
            m = conn.execute(text("""
                SELECT home_team, away_team FROM qiety_matches
                WHERE match_id=:mid ORDER BY fetch_date DESC LIMIT 1
            """), {"mid": str(qiety_mid)}).fetchone()
            if not m:
                return {}
            qhome, qaway = m[0], m[1]

            rows = conn.execute(text("""
                SELECT home_team_name, away_team_name, home_team_score, away_team_score
                FROM qiety_h2h_history
                WHERE match_id=:mid AND relation='h2h' AND fetch_date IN (:fd,:nd)
            """), {"mid": str(qiety_mid), "fd": fetch_date, "nd": next_date}).fetchall()
    except Exception:
        return {}

    home_win = away_win = draw = 0
    n = 0
    for htn, atn, hs, aws in rows:
        try:
            hs, aws = float(hs), float(aws)
        except (TypeError, ValueError):
            continue
        if htn == qhome and atn == qaway:
            cur_h, cur_a = hs, aws
        elif htn == qaway and atn == qhome:
            cur_h, cur_a = aws, hs
        else:
            continue  # 队名跟当前这场对不上（历史记录混进了别的队），跳过不瞎猜
        n += 1
        if cur_h > cur_a:
            home_win += 1
        elif cur_h < cur_a:
            away_win += 1
        else:
            draw += 1

    if n < 2:
        return {}

    # Laplace平滑，避免2-3场小样本就100%/0%过度自信
    if sport_code and sport_code.lower() == "basketball":
        tot = home_win + away_win + 2
        return {"home": (home_win + 1) / tot, "away": (away_win + 1) / tot}
    tot = home_win + away_win + draw + 3
    return {"home": (home_win + 1) / tot, "away": (away_win + 1) / tot, "draw": (draw + 1) / tot}


def get_injury_impact_probs(home: str, away: str, sport_code: str, injury_cache: dict) -> dict:
    """澳客网伤停名单(40_okooo_injury_scraper.py写入的okooo_injuries) → 伤病信号，
    2026-08-01新增。okooo_injuries不直接存home_team/away_team(只有按match_id分组
    的(side,team))，用team_zh()把home/away转中文后跟injury_cache里记录的team做
    子串模糊匹配(同_backtest_ren9_combo_fdcouk.py的find_fdcouk_for_game手法)。

    用"缺阵球员本赛季累计出场分钟数之和"衡量伤病严重程度——分钟数是最直接的
    "这个球员平时有多重要"代理指标，缺一个常年主力比缺一个替补影响大得多，
    比单纯数缺阵人数更合理。

    这是一个全新、尚未经过任何真实结算数据验证的启发式信号(okooo_injuries
    2026-08-01时只有218行/12天数据，远不够回测出可信的系数)。转成绝对概率的
    幅度刻意保守(±12个百分点封顶，用一个明确写在代码里的粗略换算尺度，不是
    拟合出来的精确数字)——按CLAUDE.md推荐单数据支撑规则，这个信号只能先进
    影子观察单积累真实结算样本，用_injury_validation_status()跟其他信号同一套
    单尾95%置信区间+近期窗口显著性检验门槛决定要不要真的转正，不能因为讲得通
    道理就当成验证过的edge直接影响正式推荐。
    双方都没有可用伤停数据时返回{}，不用中性概率冒充信号。"""
    from team_zh import team_zh as _tz
    home_zh, away_zh = _tz(home), _tz(away)
    hl, al = home_zh.lower(), away_zh.lower()

    home_missing = away_missing = None
    for _slot in injury_cache.values():
        _h, _a = _slot.get("home"), _slot.get("away")
        if not (_h and _a):
            continue
        ch, ca = (_h["team"] or "").lower(), (_a["team"] or "").lower()
        if (hl in ch or ch in hl) and (al in ca or ca in al):
            home_missing, away_missing = _h["missing_minutes"], _a["missing_minutes"]
            break
    if home_missing is None or (home_missing == 0 and away_missing == 0):
        return {}

    diff = away_missing - home_missing  # 正数：客队伤缺更严重，利好主队
    diff_norm = max(-1.0, min(1.0, diff / 3000.0))  # 3000分钟≈2-3名主力赛季分钟数量级，粗略尺度
    shift = diff_norm * 0.12  # 最大±12个百分点，未验证信号，幅度刻意保守

    if sport_code and sport_code.lower() == "basketball":
        base_home, base_away = 0.58, 0.42  # 篮球主场优势基准线（跟其他篮球模块量级一致）
        home_p = max(0.05, min(0.90, base_home + shift))
        away_p = max(0.05, min(0.90, base_away - shift))
        tot = home_p + away_p
        return {"home": home_p / tot, "away": away_p / tot}

    base_home, base_draw, base_away = 0.455, 0.232, 0.324  # 全局基准，同_backtest_ren9_combo_fdcouk.py的GLOBAL_BASE_RATE
    home_p = max(0.05, min(0.85, base_home + shift))
    away_p = max(0.05, min(0.85, base_away - shift))
    draw_p = max(0.05, 1.0 - home_p - away_p)
    tot = home_p + draw_p + away_p
    return {"home": home_p / tot, "draw": draw_p / tot, "away": away_p / tot}


def _fotmob_lambdas(home: str, away: str, league_name: str) -> tuple:
    """FotMob 双方进球λ：跟get_fotmob_shots_probs/get_fotmob_xg_probs同一套来源优先级
    (射正模型优先，样本积累快；缺失退到xG模型)，抽出来给下面的大小球/球队大小函数共用，
    避免第三次复制整段DB兜底查询逻辑。跟原两个函数的clamp/主场优势乘数位置完全一致，
    不是重新设计的新口径。返回 (lam_h, lam_a)，两者任一取不到时返回 (None, None)。"""
    # 2026-07-29修复：见get_fotmob_shots_probs()同一处说明，中文队名转英文再匹配
    from team_mapping import team_en
    home, away = _model_team_en(home), _model_team_en(away)
    fm_league = _fotmob_league_lookup(league_name)
    if not fm_league:
        return None, None

    conv = _FM_SOT_CONV.get(fm_league, 0.32) if _CACHES_LOADED else 0.32

    def _sot_lambda(team: str, side: str):
        sot_list = _cache_lookup(_FM_SOT_CACHE, fm_league, team, side) if _CACHES_LOADED else []
        if sot_list:
            sot = sot_list[:20]
            return sum(sot) / len(sot) * conv
        col_team = 'home_team' if side == 'home' else 'away_team'
        try:
            for chars in [6, 4]:
                with engine.connect() as conn:
                    rows = conn.execute(text(f"""
                        SELECT s.shots_on_target
                        FROM fotmob_match_team_stats s
                        JOIN fotmob_matches m ON m.match_id=s.match_id
                        WHERE m.league_name=:lg AND s.side=:side AND m.{col_team} LIKE :t
                          AND s.shots_on_target IS NOT NULL
                        ORDER BY m.match_date DESC LIMIT 20
                    """), {"lg": fm_league, "side": side, "t": f"%{team[:chars]}%"}).fetchall()
                if rows:
                    sot = [float(r[0]) for r in rows if r[0] is not None]
                    if sot:
                        c = _FM_SOT_CONV.get(fm_league) or 0.32
                        return sum(sot) / len(sot) * c
        except Exception:
            pass
        return None

    lam_h_sot = _sot_lambda(home, 'home')
    lam_a_sot = _sot_lambda(away, 'away')
    if lam_h_sot is not None and lam_a_sot is not None:
        return (max(0.1, min(lam_h_sot * POISSON_HOME_ADV_SOT, 5.0)),
                max(0.1, min(lam_a_sot, 5.0)))

    def _team_xg(team, side):
        rows = _cache_lookup(_FM_CACHE, fm_league, team, side) if _CACHES_LOADED else []
        if not rows:
            col_f = 'home_xg' if side == 'home' else 'away_xg'
            col_a = 'away_xg' if side == 'home' else 'home_xg'
            col_t = 'home_team' if side == 'home' else 'away_team'
            for chars in [6, 4]:
                try:
                    with engine.connect() as conn:
                        db_rows = conn.execute(text(f"""
                            SELECT {col_f}, {col_a} FROM fotmob_matches
                            WHERE league_name=:lg AND {col_t} LIKE :t
                              AND {col_f} IS NOT NULL
                            ORDER BY match_date DESC LIMIT 15
                        """), {"lg": fm_league, "t": f"%{team[:chars]}%"}).fetchall()
                    if db_rows:
                        rows = [(float(r[0]), float(r[1])) for r in db_rows if r[0]]
                        break
                except Exception:
                    pass
        if not rows:
            return None, None
        rows = rows[:15]
        xgf = [r[0] for r in rows]; xga = [r[1] for r in rows]
        return (sum(xgf)/len(xgf) if xgf else None,
                sum(xga)/len(xga) if xga else None)

    h_xgf, h_xga = _team_xg(home, 'home')
    a_xgf, a_xga = _team_xg(away, 'away')
    if h_xgf is None or a_xgf is None:
        return None, None
    return (max(0.1, (h_xgf + a_xga) / 2 * POISSON_HOME_ADV_SOT),
            max(0.1, (a_xgf + h_xga) / 2))


def _single_poisson_dist(lam: float, n: int = 12) -> dict:
    """单变量泊松分布 {进球数: 概率}，截断到n场(默认12，覆盖真实球队大小盘口线
    0.5~6.5的全部区间，尾部截断误差可忽略)，供 total_prob_at_line() 在任意线上积分。"""
    return {k: _math.exp(-lam) * (lam ** k) / _math.factorial(k) for k in range(n)}


def get_fotmob_totals_probs(home: str, away: str, league_name: str = "", line: float = 2.5) -> dict:
    """FotMob xG/射正 → 整场大小球(totals)在真实盘口线上的精确概率。
    跟 get_fotmob_xg_probs/get_fotmob_shots_probs 用同一套 _fotmob_lambdas() 来源，
    区别是这里不用 _poisson_probs() 里硬编码的2.5线，改用 poisson_model_v2.py 的
    match_total_probs()+total_prob_at_line() 在真实line上算——原理跟 get_model_probs()
    里主流程"total_line修复"(2026-07-XX)同一套道理：P_book是真实线隐含概率，
    P_poisson如果永远按2.5线算，65%的场次会跟真实线对不上号。"""
    lam_h, lam_a = _fotmob_lambdas(home, away, league_name)
    if lam_h is None:
        return {}
    from poisson_model_v2 import match_total_probs, total_prob_at_line
    p_total = match_total_probs(lam_h, lam_a)["p_total"]
    p_over, p_under = total_prob_at_line(p_total, line)
    return {"over": p_over, "under": p_under}


def get_fotmob_team_total_probs(home: str, away: str, league_name: str, side: str, line: float) -> dict:
    """FotMob xG/射正 → 球队大小(team_total)单队进球数在真实盘口线上的概率。
    side='home'用该场home队自己的λ，side='away'用away队自己的λ（仍需要双方数据算，
    因为_fotmob_lambdas()里xG来源是对手调整后的期望值，不是队伍自己数据的孤立平均）。
    单变量泊松分布直接喂给通用的 total_prob_at_line()，同一个函数既能积分双变量
    联合分布(match_total_probs的p_total)也能积分单变量分布，不需要另外写一套CDF。"""
    lam_h, lam_a = _fotmob_lambdas(home, away, league_name)
    if lam_h is None:
        return {}
    lam = lam_h if side == 'home' else lam_a
    from poisson_model_v2 import total_prob_at_line
    p_dist = _single_poisson_dist(lam)
    p_over, p_under = total_prob_at_line(p_dist, line)
    return {"over": p_over, "under": p_under}


def _fotmob_corner_lambdas(home: str, away: str, league_name: str) -> tuple:
    """FotMob 双方角球λ：跟 _fotmob_lambdas() 同一套来源优先级/DB兜底结构，只是统计字段从
    shots_on_target换成corners。角球没有xG那种"进球期望"概念，只有一层信号(球队自己
    场均角球数)，没有射正/xG两级优先级，缺失就直接返回None，不伪造第二信号源。"""
    # 2026-07-29修复：见get_fotmob_shots_probs()同一处说明，中文队名转英文再匹配
    from team_mapping import team_en
    home, away = _model_team_en(home), _model_team_en(away)
    fm_league = _fotmob_league_lookup(league_name)
    if not fm_league:
        return None, None

    def _corner_lambda(team: str, side: str):
        col_team = 'home_team' if side == 'home' else 'away_team'
        try:
            for chars in [6, 4]:
                with engine.connect() as conn:
                    rows = conn.execute(text(f"""
                        SELECT s.corners
                        FROM fotmob_match_team_stats s
                        JOIN fotmob_matches m ON m.match_id=s.match_id
                        WHERE m.league_name=:lg AND s.side=:side AND m.{col_team} LIKE :t
                          AND s.corners IS NOT NULL
                        ORDER BY m.match_date DESC LIMIT 20
                    """), {"lg": fm_league, "side": side, "t": f"%{team[:chars]}%"}).fetchall()
                if rows:
                    crn = [float(r[0]) for r in rows if r[0] is not None]
                    if crn:
                        return sum(crn) / len(crn)
        except Exception:
            pass
        return None

    lam_h = _corner_lambda(home, 'home')
    lam_a = _corner_lambda(away, 'away')
    if lam_h is None or lam_a is None:
        return None, None
    return max(0.5, lam_h), max(0.5, lam_a)


def get_fotmob_corner_probs(home: str, away: str, league_name: str = "", line: float = 9.5) -> dict:
    """FotMob角球数据(fotmob_match_team_stats.corners) → 整场角球大小(corner_ou)
    在真实盘口线上的概率。跟get_fotmob_totals_probs同一套total_prob_at_line()积分方式，
    只是λ来源换成双方球队场均角球数(不是进球xG)，见_fotmob_corner_lambdas()说明。
    2026-07-21新增：现有corner_model.py只覆盖20个欧洲主流联赛白名单(football-data.co.uk
    历史角球统计)，FotMob角球数据覆盖58个联赛，跟角球模型现有白名单几乎不重叠，
    是真正的增量覆盖，不是重复信号。"""
    lam_h, lam_a = _fotmob_corner_lambdas(home, away, league_name)
    if lam_h is None:
        return {}
    from poisson_model_v2 import total_prob_at_line
    p_dist = _single_poisson_dist(lam_h + lam_a, n=25)  # 角球总数量级远高于进球，截断上限相应放大
    p_over, p_under = total_prob_at_line(p_dist, line)
    # exp_total(2026-08-10新增)：corner_model.py合并FotMob信号成为新版角球正式
    # 投注单时需要预期总角球数(mu)用于展示"预测均角"，向后兼容——原有调用方
    # 只读over/under两个键，多这一个键不影响任何现有行为。
    return {"over": p_over, "under": p_under, "exp_total": round(lam_h + lam_a, 2)}


def _margin_dist(lam_h: float, lam_a: float, n: int = 12) -> dict:
    """净胜球(主-客)分布 {margin: prob}，供让球(spread)覆盖概率积分用。"""
    dist: dict = {}
    for i in range(n):
        pi = _math.exp(-lam_h) * (lam_h ** i) / _math.factorial(i)
        for j in range(n):
            pj = _math.exp(-lam_a) * (lam_a ** j) / _math.factorial(j)
            m = i - j
            dist[m] = dist.get(m, 0.0) + pi * pj
    return dist


def _spread_cover_prob(margin_dist: dict, handicap: float, outcome: str) -> tuple:
    """给定净胜球分布、某一行的handicap/outcome，按_settle_result('spread',...)
    (21_auto_settle.py)同一套符号约定算(win_prob, push_prob)：
        outcome=='home': adjusted = margin + handicap，>0赢，==0走盘
        outcome=='away': adjusted = handicap - margin，>0赢，==0走盘
    这样保证FotMob信号跟正式结算用的是同一套盘口方向定义，不会号反。"""
    win = push = 0.0
    for m, p in margin_dist.items():
        adj = (m + handicap) if outcome == "home" else (handicap - m)
        if adj > 1e-9:
            win += p
        elif abs(adj) < 1e-9:
            push += p
    return win, push


def get_fotmob_spread_probs(home: str, away: str, league_name: str, outcome: str, handicap: float) -> dict:
    """FotMob xG/射正 → 让球(亚洲盘口/spread)覆盖概率，真实盘口线(含1/4线)。
    2026-07-21新增：诊断发现足球让球市场目前完全没有泊松类P_poisson分量(只有LSTM的
    margin~Normal校准法，见_lstm_spread_cover_prob())，这里用跟大小球/球队大小同一套
    _fotmob_lambdas()真实xG/射正λ，走标准联合泊松矩阵积分覆盖概率，是这个市场第一个
    真正的"进球分布"类模型信号，不是又一个跟LSTM同构的近似替代。
    1/4线(如-0.25/-0.75)不是标准整数/半球线，真实赔付是两笔注平摊在相邻两条线上，
    这里用相邻两条线覆盖概率的平均值近似(标准处理方式，见Asian handicap定义)。"""
    lam_h, lam_a = _fotmob_lambdas(home, away, league_name)
    if lam_h is None:
        return {}
    dist = _margin_dist(lam_h, lam_a)

    is_quarter = abs((handicap * 4) % 2) > 1e-6 and abs((handicap * 4) % 2 - 2) > 1e-6
    if is_quarter:
        h_lo, h_hi = handicap - 0.25, handicap + 0.25
        w_lo, _ = _spread_cover_prob(dist, h_lo, outcome)
        w_hi, _ = _spread_cover_prob(dist, h_hi, outcome)
        return {outcome: round((w_lo + w_hi) / 2, 4)}
    win, push = _spread_cover_prob(dist, handicap, outcome)
    denom = max(1e-9, 1.0 - push)  # 走盘不计入胜负概率分母，跟真实赔付口径一致
    return {outcome: round(win / denom, 4)}


def get_football_xg_stats_probs(home: str, away: str, league_name: str = "") -> dict:
    """
    从 football_xg_stats（三源融合: Understat/FBref/SofaScore）查队伍场均 xG，
    用泊松计算胜平负 + 大小球概率。覆盖 40+ 联赛，是 get_xg_model_probs 和
    get_fotmob_xg_probs 的扩展兜底（两者都无数据时启用）。
    """
    # 2026-07-29修复：football_xg_stats存英文队名，见get_fotmob_shots_probs()同一处说明
    from team_mapping import team_en
    home, away = _model_team_en(home), _model_team_en(away)

    def _lookup(team: str):
        # 缓存优先（O(1) 内存查找）
        if _CACHES_LOADED:
            v = _fxg_lookup(team)
            if v[0] is not None:
                return v
        for chars in [6, 4]:
            try:
                with engine.connect() as conn:
                    r = conn.execute(text("""
                        SELECT xg_off, xg_def FROM football_xg_stats
                        WHERE LOWER(league) LIKE LOWER(:lg)
                          AND LOWER(team) LIKE LOWER(:t)
                          AND source != 'historical'
                        ORDER BY rowid DESC LIMIT 1
                    """), {"lg": f"%{league_name[:8]}%" if league_name else "%",
                           "t": f"%{team[:chars]}%"}).fetchone()
                if r:
                    return float(r[0]), float(r[1])
            except Exception:
                pass
        return None, None

    h_off, h_def = _lookup(home)
    a_off, a_def = _lookup(away)
    if h_off is None or a_off is None:
        return {}

    # football_xg_stats 是 xG 数据（非射正），用 POISSON_HOME_ADV_XG，与 _get_football_top_score 一致
    lam_h = max(0.1, (h_off + a_def) / 2 * POISSON_HOME_ADV_XG)
    lam_a = max(0.1, (a_off + h_def) / 2)
    return _poisson_probs(lam_h, lam_a)


def _get_football_top_score(home: str, away: str, league_name: str = "") -> str:
    """用 football_xg_stats + StatsBomb 国家队数据计算泊松最可能比分，找不到数据返回 '?'

    Bug修复：
    1. 优先走内存缓存（_FXG_CACHE），减少 DB 查询
    2. xG 数据用 POISSON_HOME_ADV_XG 而非 POISSON_HOME_ADV_SOT（后者是射正换算系数，不适用于 xG）
    """
    _nat_alias = {
        "usa": "United States", "united states": "United States",
        "south korea": "South Korea", "korea republic": "South Korea",
        "czech republic": "Czech Republic", "czechia": "Czech Republic",
        "türkiye": "Turkey", "turkiye": "Turkey",
        "ir iran": "Iran", "ivory coast": "Ivory Coast",
        "cabo verde": "Cape Verde", "bosnia and herzegovina": "Bosnia",
    }
    def _norm_team(t): return _nat_alias.get(t.lower(), t)

    # 2026-07-29修复：football_xg_stats/statsbomb_national_xg_teams存英文队名，
    # 中文展示名转英文后再走_norm_team的别名归一化，见get_fotmob_shots_probs()说明
    from team_mapping import team_en
    home, away = _model_team_en(home), _model_team_en(away)

    def _lookup(team: str):
        # Bug修复：缓存优先，避免重复 DB 查询（之前是先 SQL 后 cache）
        if _CACHES_LOADED:
            v = _fxg_lookup(team)
            if v[0] is not None:
                return v
        for chars in [6, 4]:
            try:
                with engine.connect() as conn:
                    r = conn.execute(text("""
                        SELECT xg_off, xg_def FROM football_xg_stats
                        WHERE LOWER(team) LIKE LOWER(:t)
                          AND source != 'historical'
                        ORDER BY rowid DESC LIMIT 1
                    """), {"t": f"%{team[:chars]}%"}).fetchone()
                if r:
                    return float(r[0]), float(r[1])
            except Exception:
                pass
        # StatsBomb 国家队 xG 兜底（过滤异常值，取正常范围内均值）
        for chars in [7, 6, 5, 4]:
            try:
                with engine.connect() as conn:
                    r = conn.execute(text("""
                        SELECT AVG(avg_xg), AVG(avg_xga)
                        FROM statsbomb_national_xg_teams
                        WHERE LOWER(team_name) LIKE LOWER(:t)
                          AND avg_xg BETWEEN 0.3 AND 3.0
                          AND avg_xga BETWEEN 0.3 AND 3.0
                    """), {"t": f"%{team[:chars]}%"}).fetchone()
                if r and r[0] is not None:
                    return float(r[0]), float(r[1])
            except Exception:
                pass
        return None, None

    h_off, h_def = _lookup(_norm_team(home))
    a_off, a_def = _lookup(_norm_team(away))

    # 双边都有真实数据才计算，否则返回 "?" 表示数据不足
    if h_off is None or a_off is None:
        return "?"
    # Bug修复：xG 数据用 POISSON_HOME_ADV_XG，不用 POISSON_HOME_ADV_SOT
    lam_h = max(0.1, (h_off + (a_def if a_def else 1.25)) / 2 * POISSON_HOME_ADV_XG)
    lam_a = max(0.1, (a_off + (h_def if h_def else 1.25)) / 2)
    return _poisson_top_score(lam_h, lam_a)


def _persist_xg_score(uid: str, home: str, away: str, league_name: str,
                      kickoff: str, top_score: str, fetch_date: str) -> None:
    """把 xG 兜底算出的比分预测写入 football_score_predictions（engine='xG'），
    使其和 predict_football.py 写入的 elo/poisson/poisson_global 一样可回测比对命中率。
    此前 xG 预测只在控制台/txt 展示，从不落库，历史上无法追溯评估。"""
    if not top_score or top_score == "?":
        return
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT OR REPLACE INTO football_score_predictions
                (unified_id, home_team, away_team, league_name, kickoff_utc,
                 top_score, lambda_home, lambda_away, engine, fetch_date, created_at)
                VALUES (:uid, :home, :away, :league, :kickoff,
                        :score, NULL, NULL, 'xG', :fd, :now)
            """), {
                "uid": uid, "home": home, "away": away, "league": league_name,
                "kickoff": kickoff, "score": top_score, "fd": fetch_date,
                "now": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            })
    except Exception as e:
        log.debug(f"_persist_xg_score({uid}) 写入失败: {e}")


def get_bballref_model_probs(home: str, away: str, league_name: str = "") -> dict:
    """Basketball-Reference ORtg/DRtg/Pace → NBA / 国际篮球胜负 + 大小球概率
    优先级: bballref_team_stats(NBA ORtg/DRtg) → basketball_team_stats(offense_eff/defense_eff)
    """
    # 2026-07-29修复：bballref_team_stats存英文NBA队名，中文展示名(qiety_yb/
    # okooo_jingcai)直接匹配配不上，见get_fotmob_shots_probs()同一处说明
    from team_mapping import team_en
    home, away = _model_team_en(home), _model_team_en(away)

    # ── 路径1: bballref_team_stats（NBA精确 ORtg/DRtg/pace）──────────────────
    # Bug修复：原来直接 LIKE team[:5]/team[:3] 前缀模糊匹配，同城多队(如 Los Angeles
    # Lakers/Clippers 前5个字符都是"Los A")会命中错误球队的数据，且 ORDER BY season
    # DESC LIMIT 1 在多队都匹配时是按SQL任意行序挑一个，完全可能挑到对手的评分。
    # 改为：先精确匹配(含末尾*号变体)，模糊匹配命中多支不同球队时用字符串相似度选最像的。
    def _ratings(team):
        try:
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT ortg, drtg, pace, nrtg FROM bballref_team_stats
                    WHERE team = :t OR team = :t2
                    ORDER BY season DESC LIMIT 1
                """), {"t": team, "t2": f"{team}*"}).fetchone()
            if row and row[0]:
                return {'ortg': float(row[0]), 'drtg': float(row[1]),
                        'pace': float(row[2]) if row[2] else 100.0,
                        'nrtg': float(row[3]) if row[3] else 0.0}
        except Exception:
            pass

        for chars in [5, 3]:
            try:
                with engine.connect() as conn:
                    rows = conn.execute(text("""
                        SELECT team, ortg, drtg, pace, nrtg, season FROM bballref_team_stats
                        WHERE team LIKE :t
                    """), {"t": f"%{team[:chars]}%"}).fetchall()
                if not rows:
                    continue
                distinct_teams = {r[0].rstrip("*") for r in rows}
                if len(distinct_teams) > 1:
                    # 模糊匹配命中了不止一支球队，用字符串相似度挑最像的那支，
                    # 而不是信任SQL任意行序（否则同城多队必错）
                    best_team = max(distinct_teams,
                                     key=lambda t: SequenceMatcher(None, t.lower(), team.lower()).ratio())
                    rows = [r for r in rows if r[0].rstrip("*") == best_team]
                row = max(rows, key=lambda r: r[5])  # 同队取最新season
                if row and row[1]:
                    return {'ortg': float(row[1]), 'drtg': float(row[2]),
                            'pace': float(row[3]) if row[3] else 100.0,
                            'nrtg': float(row[4]) if row[4] else 0.0}
            except Exception:
                pass
        return None

    hr = _ratings(home)
    ar = _ratings(away)
    if hr and ar:
        avg_pace = (hr['pace'] + ar['pace']) / 2
        exp_home = (hr['ortg'] + ar['drtg']) / 2 * avg_pace / 100
        exp_away = (ar['ortg'] + hr['drtg']) / 2 * avg_pace / 100
        margin   = (exp_home - exp_away) + NBA_HOME_ADV_PTS
        z        = margin / (BBALL_SIGMA_BREF * _math.sqrt(2))
        home_win = round(min(0.95, max(0.05, 0.5 * (1 + _math.erf(z)))), 4)
        return {
            'home': home_win, 'away': round(1 - home_win, 4),
            'exp_total': round(exp_home + exp_away, 1),
            'league_avg_total': 228.6,  # NBA近2季基准
            'league_std_total': 20.0,
        }

    # ── 路径2: basketball_team_stats（NBA+14国际联赛，基于 import_basketball_stats）──
    # 同路径1的修复：先精确匹配，模糊匹配命中多队时用字符串相似度选最像的，不信任SQL任意行序
    def _bts(team):
        try:
            with engine.connect() as conn:
                r = conn.execute(text("""
                    SELECT offense_eff, defense_eff FROM basketball_team_stats
                    WHERE LOWER(team) = LOWER(:t) ORDER BY total_games DESC LIMIT 1
                """), {"t": team}).fetchone()
            if r and r[0]:
                return float(r[0]), float(r[1])
        except Exception:
            pass

        for chars in [5, 4, 3]:
            try:
                with engine.connect() as conn:
                    rows = conn.execute(text("""
                        SELECT team, offense_eff, defense_eff, total_games FROM basketball_team_stats
                        WHERE LOWER(team) LIKE LOWER(:t)
                    """), {"t": f"%{team[:chars]}%"}).fetchall()
                if not rows:
                    continue
                distinct_teams = {r[0] for r in rows}
                if len(distinct_teams) > 1:
                    best_team = max(distinct_teams,
                                     key=lambda t: SequenceMatcher(None, t.lower(), team.lower()).ratio())
                    rows = [r for r in rows if r[0] == best_team]
                r = max(rows, key=lambda r: r[3])  # 同队取total_games最多的一条
                if r and r[1]:
                    return float(r[1]), float(r[2])
            except Exception:
                pass
        return None, None

    # 从 basketball_league_ou 获取联赛基准总分和标准差
    def _ou_baseline(lg: str):
        _kw_map = [
            ('nba',        'nba'),        ('euroleague',  'euroleague'),
            ('eurocup',    'eurocup'),    ('acb',         'spain-liga-acb'),
            ('lnb',        'france-lnb-pro-a'), ('cba',   'cba-china'),
            ('nbl',        'nbl-australia'), ('vtb',      'vtb-united'),
            ('bsl',        'turkey-super-league'), ('aba', 'aba-adriatic'),
            ('israel',     'israel-super-league'), ('greek', 'greek-basket-league'),
            ('serie',      'italy-basket-serie-a'), ('fiba', 'fiba-world-cup'),
            ('olympic',    'mens-olympics'), ('olimpic',  'mens-olympics'),
        ]
        lg_l = lg.lower()
        league_key = 'nba'
        for kw, key in _kw_map:
            if kw in lg_l:
                league_key = key
                break
        try:
            with engine.connect() as conn:
                r = conn.execute(text(
                    "SELECT avg_total, std_total FROM basketball_league_ou WHERE league=:lg LIMIT 1"
                ), {"lg": league_key}).fetchone()
            if r:
                return float(r[0]), float(r[1])
        except Exception:
            pass
        return 220.0, 20.0

    h_off, h_def = _bts(home)
    a_off, a_def = _bts(away)
    if h_off is None or a_off is None:
        return {}

    league_avg, league_std = _ou_baseline(league_name)
    home_adv = NBA_HOME_ADV_PTS if 'nba' in league_name.lower() else 2.5
    exp_home = (h_off + a_def) / 2 + home_adv * 0.5
    exp_away = (a_off + h_def) / 2 - home_adv * 0.5
    margin   = exp_home - exp_away
    z        = margin / (BBALL_SIGMA_BREF * _math.sqrt(2))
    home_win = round(min(0.95, max(0.05, 0.5 * (1 + _math.erf(z)))), 4)

    return {
        'home': home_win, 'away': round(1 - home_win, 4),
        'exp_total':       round(exp_home + exp_away, 1),
        'league_avg_total': round(league_avg, 1),
        'league_std_total': round(league_std, 1),
    }


# ─── 7. 自动投注分配（单注 + 串关） ──────────────────────────────────────────
def _generate_bet_plan(recommendations: list, fetch_date: str):
    """
    根据 config 中的资金管理参数，自动分配：
    - 单注（精选推荐）
    - 2~8串1（精选市场组合，以小博大）
    """
    from itertools import combinations
    import random
    from team_zh import team_zh as _team_zh

    bankroll = BANKROLL
    halved = bankroll < HALF_BANKROLL
    if halved:
        log.info(f"  ⚠ 本金 {bankroll} < {HALF_BANKROLL}，投注减半")

    # ── P3: 动态Kelly辅助函数 ──
    def _kelly_scale(hit_score: float) -> float:
        """根据命中分返回动态投注系数"""
        for (lo, hi), scale in DYNAMIC_KELLY_SCALE.items():
            if lo <= hit_score < hi:
                return scale
        return 1.0

    # ── 单注分配（P3: 动态Kelly） ──
    # 比分玩法(correct_score) 转正门槛：已结算样本量+ROI达标才进单注分配，
    # 没达标之前只在"足球比分预测单"区块展示+写入hit_recommendations供结算统计命中率，
    # 不占用单注名额、不实际建议下注金额（串关白名单 PARLAY_ELIGIBLE_MARKETS 更严格，
    # 单独判断，不会因为这里转正就自动进串关）
    base_bet = bankroll * SINGLE_BET_PCT * (0.5 if halved else 1.0)
    _cs_ok = _correct_score_validation_status()["validated"]
    _single_pool = recommendations if _cs_ok else [r for r in recommendations if r["market"] != "correct_score"]
    single_recs = _single_pool[:SINGLE_BET_MAX]

    # 计算每条推荐的实际投注额
    single_bet_map = []  # [(rec, bet_amount, scale)]
    for rec in single_recs:
        scale = _kelly_scale(rec.get("hit_score", 0.5))
        bet = round(base_bet * scale, 1)
        single_bet_map.append((rec, bet, scale))

    # 把实际下注额落库，供 21_auto_settle.py 结算真实盈亏（元）用；
    # 只覆盖单注部分——串关下注额不与单条 hit_recommendations 一一对应，不在此处记录
    if single_bet_map:
        with engine.begin() as _stake_conn:
            for rec, bet, _scale in single_bet_map:
                _stake_conn.execute(text("""
                    UPDATE hit_recommendations SET stake=:stake
                    WHERE fetch_date=:fd AND unified_id=:uid AND market=:mkt
                      AND outcome=:oc AND formula_version='v1'
                """), {
                    "stake": bet, "fd": fetch_date, "uid": rec.get("unified_id"),
                    "mkt": rec.get("market"), "oc": rec.get("outcome"),
                })

    # ── 串关候选（精选市场 + K>0 + kickoff 必须在当前时刻之后） ──
    _now_utc_parlay = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    parlay_candidates = sorted(
        [r for r in recommendations
         if (r["market"], r["outcome"]) in PARLAY_ELIGIBLE_MARKETS
         and r.get("kelly_fraction", 0) > 0
         and r.get("kickoff_utc", "9999") > _now_utc_parlay],
        key=lambda x: x["hit_score"], reverse=True
    )

    def _is_independent(combo):
        seen = set()
        for rec in combo:
            uid = rec.get("unified_id", "")
            if uid in seen:
                return False
            seen.add(uid)
        return True

    # ── 生成 2~8 串关 ──
    parlay_results = {}  # {n: (bet_amount, combos_list)}

    for n in sorted(PARLAY_CONFIG.keys()):
        pct, max_combos = PARLAY_CONFIG[n]
        bet_per_combo = bankroll * pct * (0.5 if halved else 1.0)

        if len(parlay_candidates) < n:
            continue

        pool_size = min(n * 3, len(parlay_candidates))
        pool = parlay_candidates[:pool_size]

        if n >= 6 and len(pool) < n:
            pool = parlay_candidates
            if len(pool) < n:
                continue

        all_combos = [c for c in combinations(pool, n) if _is_independent(c)]

        # 候选不够（过滤后）则跳过
        if not all_combos:
            continue

        # 随机采样避免每天都一样（保留第一个最高分组合）
        if len(all_combos) > max_combos:
            top_combo = all_combos[0]
            rest = random.sample(all_combos[1:], min(len(all_combos) - 1, max_combos - 1))
            selected = [top_combo] + rest
        else:
            selected = all_combos

        parlay_results[n] = (bet_per_combo, selected[:max_combos])

    # ── 输出投注计划 ──
    PARLAY_ICON  = {2: "🔗", 3: "🎰", 4: "🎯", 5: "🚀", 6: "💫", 7: "🌟", 8: "💎"}
    PARLAY_LABEL = {2: "稳健", 3: "进取", 4: "博取", 5: "高博",
                    6: "以小博大", 7: "以小博大", 8: "以小博大"}

    total_stake  = 0.0
    W = 108
    SEP = "─" * W
    out: list[str] = []

    out.append("\n" + "=" * W)
    out.append(f"  💰 今日投注计划  [{fetch_date}]  本金 {bankroll}元" + (" 【减半模式】" if halved else ""))
    out.append(f"  📐 K₁/₄ = (p融合×赔率-1)/(赔率-1)×0.25")
    out.append("=" * W)

    # ── 单注明细 ──
    single_total = sum(b for _, b, _ in single_bet_map)
    total_stake += single_total
    out.append(f"\n  ┌─ 📌 单注（共{len(single_bet_map)}注，合计 {single_total:.0f}元）")
    out.append(f"  │  基准单注 {base_bet:.0f}元，按命中分动态调整")
    out.append(f"  ├─" + SEP[3:])
    out.append(f"  │  {'序':>2}  {'开赛时间':<12} {'主队':^10} vs {'客队':^10}  {'玩法/方向':<14} {'赔率':>5}  {'p融合':>6}  {'K₁/₄':>6}  {'投注':>5}  命中分")
    out.append(f"  ├─" + SEP[3:])
    for i, (rec, bet, scale) in enumerate(single_bet_map, 1):
        h_zh   = _team_zh(rec['home_team'])[:10]
        a_zh   = _team_zh(rec['away_team'])[:10]
        mkt_zh = _MARKET_ZH.get(rec['market'], rec['market'])
        out_zh = _OUTCOME_ZH.get(rec['outcome'], rec['outcome'])
        hc     = rec.get("handicap")
        if hc is not None:
            out_zh = f"{out_zh}{hc}"
        direction = f"{mkt_zh}/{out_zh}"
        try:
            from datetime import timedelta as _td
            dt = datetime.fromisoformat(rec.get("kickoff_utc","").replace("Z","+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            t_str = dt.astimezone(timezone(_td(hours=8))).strftime("%m月%d日%H:%M")
        except Exception:
            t_str = "--月--日--:--"
        scale_tag = "🔥" if scale >= 1.5 else ("✅" if scale >= 1.0 else "⬇")
        out.append(f"  │  {i:>2}. {t_str:<12} {h_zh:^10} vs {a_zh:^10}  {direction:<14} "
              f"{rec['best_odds']:>5.2f}  {rec['model_prob']:>6.3f}  {rec['kelly_fraction']:>6.4f}  "
              f"{scale_tag}{bet:>3.0f}元  {rec['hit_score']:.3f}")
    out.append(f"  └─" + SEP[3:])

    # ── 串关明细 ──
    for n in sorted(parlay_results.keys()):
        bet_per, combos = parlay_results[n]
        icon  = PARLAY_ICON.get(n, "🎲")
        label = PARLAY_LABEL.get(n, "")
        combo_stake = bet_per * len(combos)
        total_stake += combo_stake

        out.append(f"\n  ┌─ {icon} {n}串1·{label}（每单 {bet_per:.0f}元 × {len(combos)}单 = {combo_stake:.0f}元）")
        out.append(f"  ├─" + SEP[3:])

        for i, combo in enumerate(combos, 1):
            combo_odds = 1.0
            for rec in combo:
                combo_odds *= rec['best_odds']
            win_amt = bet_per * (combo_odds - 1)
            win_tag = f"💰{win_amt:.0f}元" if win_amt >= 100 else f"{win_amt:.1f}元"

            legs = []
            for rec in combo:
                h  = _team_zh(rec['home_team'])[:8]
                a  = _team_zh(rec['away_team'])[:8]
                mz = _MARKET_ZH.get(rec['market'], rec['market'])
                oz = _OUTCOME_ZH.get(rec['outcome'], rec['outcome'])
                hc = rec.get("handicap")
                oz = f"{oz}{hc}" if hc is not None else oz
                try:
                    dt  = datetime.fromisoformat(rec.get("kickoff_utc","").replace("Z","+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    ts  = dt.astimezone(timezone(timedelta(hours=8))).strftime("%m/%d %H:%M")
                except Exception:
                    ts  = "--/-- --:--"
                legs.append(f"{ts} {h}vs{a} {mz}/{oz} @{rec['best_odds']:.2f}")

            out.append(f"  │  [{i}] 组合赔率 {combo_odds:.1f}  中奖可赢 {win_tag}")
            for leg in legs:
                out.append(f"  │      ✦ {leg}")

        out.append(f"  └─" + SEP[3:])

    # ── 汇总 ──
    loss_limit   = bankroll * DAILY_LOSS_LIMIT_PCT
    parlay_count = sum(len(c) for _, c in parlay_results.items())
    out.append(f"\n  ╔{'═'*(W-2)}╗")
    out.append(f"  ║  📊 资金汇总：单注 {len(single_bet_map)}注（{single_total:.0f}元）"
          f" + 串关 {parlay_count}单（{total_stake-single_total:.0f}元）"
          f" = 总投注 {total_stake:.0f}元 / {bankroll}元本金（占 {total_stake/bankroll*100:.0f}%）")
    out.append(f"  ║  🛡 风控：日亏上限 {loss_limit:.0f}元 | 连亏{STOP_LOSS_STREAK}注停手 | 本金<{HALF_BANKROLL}元减半")
    out.append(f"  ╚{'═'*(W-2)}╝")

    for ln in out:
        print(ln)

    return out, {
        "single_bets": single_recs,
        "parlays": {n: combos for n, (_, combos) in parlay_results.items()},
        "total_stake": total_stake,
    }


# ─── 7.3 ESPN 比赛结果同步 ───────────────────────────────────────────────────
def sync_espn_results(fetch_date: str) -> int:
    """将 espn_scores 已结束比赛的比分同步回 unified_matches（更新无比分记录）"""
    DONE = {'Full Time', 'Final', 'FT', 'After Extra Time', 'After Penalties', 'AET'}
    try:
        with engine.connect() as conn:
            espn_rows = conn.execute(text("""
                SELECT home_team, away_team, home_score, away_score, status, sport_code,
                       match_date, home_score_ht, away_score_ht
                FROM espn_scores
                WHERE fetch_date=:fd
            """), {"fd": fetch_date}).fetchall()
    except Exception as e:
        log.debug(f"sync_espn_results: {e}")
        return 0

    finished = [r for r in espn_rows if any(s in (r[4] or '') for s in DONE)]
    if not finished:
        return 0

    try:
        with engine.connect() as conn:
            u_rows = conn.execute(text("""
                SELECT unified_id, home_team_std, away_team_std
                FROM unified_matches
                WHERE fetch_date=:fd AND home_score IS NULL
            """), {"fd": fetch_date}).fetchall()
    except Exception as e:
        log.debug(f"sync_espn_results query: {e}")
        return 0

    def _sim(a, b):
        return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

    updated = 0
    for uid, uh, ua in u_rows:
        best_score, best_match = 0.0, None
        for eh, ea, hs, as_, st, sp, md, hs_ht, as_ht in finished:
            s = (_sim(uh, eh) + _sim(ua, ea)) / 2
            if s > best_score:
                best_score, best_match = s, (hs, as_, st, hs_ht, as_ht)
        if best_score >= 0.70 and best_match:
            hs, as_, st, hs_ht, as_ht = best_match
            try:
                with engine.begin() as conn:
                    conn.execute(text("""
                        UPDATE unified_matches
                        SET home_score=:hs, away_score=:as_, status=:st,
                            home_score_ht=:hs_ht, away_score_ht=:as_ht,
                            last_updated=:now
                        WHERE unified_id=:uid
                    """), {"hs": hs, "as_": as_, "st": st,
                           "hs_ht": hs_ht, "as_ht": as_ht,
                           "now": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                           "uid": uid})
                updated += 1
            except Exception:
                pass

    if updated:
        log.info(f"  ESPN结果同步: {updated} 场比分已更新")
    return updated


def sync_fotmob_ht_results(fetch_date: str, days_back: int = 3) -> int:
    """把 fotmob_matches 反推出的半场比分同步回 unified_matches（2026-07-24新增，
    半全场市场需要半场比分，FotMob没有Cloudflare拦截、爬虫本来就在正常跑，比
    09_flashscore_schedule_scraper.py猜错字段代号、sofascore被墙都更现实，见
    43_fotmob_match_data_scraper.py的_extract_ht_score()）。
    只补 home_score_ht 缺失、但 home_score 已经有值的记录——不拿FotMob的全场比分
    覆盖其他更早写入的来源，只借它独有的半场比分这一块。
    不按 fotmob_matches.fetch_date=今天 硬过滤（match_date回溯窗口±days_back天），
    这是CLAUDE.md永久规则明确要求的写法：09_qiety_yb同类bug就是JOIN条件写死当天
    导致查不到就退化成假数据，这里改成按真实比赛日期回溯匹配。"""
    import re as _re
    from collections import defaultdict
    try:
        with engine.connect() as conn:
            u_rows = conn.execute(text("""
                SELECT unified_id, home_team_std, away_team_std, fetch_date
                FROM unified_matches
                WHERE fetch_date=:fd AND home_score IS NOT NULL AND home_score_ht IS NULL
            """), {"fd": fetch_date}).fetchall()
    except Exception as e:
        log.debug(f"sync_fotmob_ht_results query: {e}")
        return 0
    if not u_rows:
        return 0

    try:
        base = datetime.strptime(fetch_date, "%Y-%m-%d")
        date_candidates = [(base - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_back + 1)]
    except Exception:
        date_candidates = [fetch_date]

    try:
        with engine.connect() as conn:
            fm_rows = conn.execute(text("""
                SELECT home_team, away_team, match_date, home_score_ht, away_score_ht
                FROM fotmob_matches
                WHERE home_score_ht IS NOT NULL AND away_score_ht IS NOT NULL
            """)).fetchall()
    except Exception as e:
        log.debug(f"sync_fotmob_ht_results: {e}")
        return 0
    if not fm_rows:
        return 0

    # fotmob match_date 是 "Wed, Jul 22, 2026, 22:30 UTC" 这种人类可读格式，
    # 转成 YYYY-MM-DD 才能跟 unified_matches 的 fetch_date 比对
    def _fm_date(md: str):
        try:
            return datetime.strptime(md, "%a, %b %d, %Y, %H:%M UTC").strftime("%Y-%m-%d")
        except Exception:
            m = _re.search(r'(\d{4})-(\d{2})-(\d{2})', md or '')
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None

    fm_by_date = defaultdict(list)
    for fh, fa, md, hs_ht, as_ht in fm_rows:
        d = _fm_date(md)
        if d:
            fm_by_date[d].append((fh, fa, hs_ht, as_ht))

    def _sim(a, b):
        return SequenceMatcher(None, (a or '').lower().strip(), (b or '').lower().strip()).ratio()

    updated = 0
    for uid, uh, ua, fd in u_rows:
        best_score, best_match = 0.0, None
        for d in date_candidates:
            for fh, fa, hs_ht, as_ht in fm_by_date.get(d, []):
                s = (_sim(uh, fh) + _sim(ua, fa)) / 2
                if s > best_score:
                    best_score, best_match = s, (hs_ht, as_ht)
        if best_score >= 0.70 and best_match:
            hs_ht, as_ht = best_match
            try:
                with engine.begin() as conn:
                    conn.execute(text("""
                        UPDATE unified_matches
                        SET home_score_ht=:hs_ht, away_score_ht=:as_ht, last_updated=:now
                        WHERE unified_id=:uid AND home_score_ht IS NULL
                    """), {"hs_ht": hs_ht, "as_ht": as_ht,
                           "now": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                           "uid": uid})
                updated += 1
            except Exception:
                pass

    if updated:
        log.info(f"  FotMob半场比分同步: {updated} 场已更新")
    return updated


# ─── 7.5 P2: 赔率快照 & CLV 计算 ───────────────────────────────────────────
def save_odds_snapshots(fetch_date: str):
    """
    每次爬虫运行后调用，把当前 consensus_odds 快照存入 odds_snapshots。
    用于追踪赔率变化时间线，计算 CLV。
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT unified_id, market, outcome, consensus_odds, source_count
            FROM consensus_odds WHERE fetch_date = :fd
        """), {"fd": fetch_date}).fetchall()

    if not rows:
        log.info("  无共识赔率可快照")
        return 0

    snap_batch = [
        {"uid": uid, "mkt": mkt, "out": out, "odds": odds, "now": now, "fd": fetch_date}
        for uid, mkt, out, odds, sc in rows
    ]
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO odds_snapshots (unified_id, source, market, outcome,
                                        odds_value, snapshot_time, fetch_date)
            VALUES (:uid, 'consensus', :mkt, :out, :odds, :now, :fd)
        """), snap_batch)

    log.info(f"  ✅ 赔率快照: {len(rows)} 条 @ {now}")
    return len(rows)


def compute_clv(fetch_date: str):
    """
    计算推荐单的 CLV（Closing Line Value）。
    CLV = 推荐时赔率 / 开赛时最新赔率
    CLV > 1.0 表示我们拿到了比收盘更好的赔率 → 长期赢钱信号
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    updated = 0
    _updated_ids: list = []  # 本次实际写入clv的记录id，供下方汇总统计用

    # Bug修复：fetch_date 之前被静默忽略（_ = fetch_date），现在优先查当日，
    # 再补查近7日内仍 pending 的历史记录（比赛开赛后当日未计算完的）
    # Bug修复(2026-08-27)：查询条件之前没有排除 status='invalid'/'void' 的记录——
    # 这些是入库前清洗环节判定为"越界/缺线"(如赔率范围异常、handicap缺失)而被标记
    # 无效的候选，从未参与真实结算，但compute_clv()一样会给它们算CLV并写入closing_odds/clv
    # 字段，脏odds(如2026-05-29那批262条美式赔率未转换十进制、best_odds=103~820的历史
    # 数据事故)会算出clv=57~80这种荒谬值，污染 clv_report() 的全局平均。这类无效行的
    # best_odds本身就不代表真实推荐，不应该出现在CLV统计里。
    with engine.connect() as conn:
        recs = conn.execute(text("""
            SELECT id, unified_id, market, outcome, best_odds, kickoff_utc
            FROM hit_recommendations
            WHERE clv_status = 'pending'
              AND status NOT IN ('invalid', 'void')
              AND fetch_date >= date(:fd, '-7 days')
            ORDER BY kickoff_utc DESC
            LIMIT 500
        """), {"fd": fetch_date}).fetchall()

    for rec_id, uid, mkt, out, rec_odds, kickoff in recs:
        # 只计算已开赛的推荐
        try:
            ko = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
            if now < ko:
                continue  # 还没开赛，跳过
        except Exception:
            continue

        # 找收盘赔率：该比赛该市场最新的 odds_snapshot
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT odds_value FROM odds_snapshots
                WHERE unified_id = :uid AND market = :mkt AND outcome = :out
                ORDER BY snapshot_time DESC LIMIT 1
            """), {"uid": uid, "mkt": mkt, "out": out}).fetchone()

        if not row:
            continue

        closing_odds = row[0]
        if closing_odds and closing_odds > 0:
            clv = round(rec_odds / closing_odds, 4)
        else:
            clv = None

        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE hit_recommendations
                SET closing_odds = :co, clv = :clv, clv_status = 'done'
                WHERE id = :rid
            """), {"co": closing_odds, "clv": clv, "rid": rec_id})
        updated += 1
        _updated_ids.append(rec_id)

    if updated > 0:
        # Bug修复(2026-07-19)：上面的UPDATE循环处理的是"近7日内所有pending记录"
        # (fetch_date >= date(:fd,'-7 days'))，但这里汇总统计一直卡死用fetch_date=:fd
        # (仅今天)去重新查——如果这次更新的记录大多是前几天的历史pending单(今天才
        # 开赛/才有收盘价可查)，会出现"updated=26条"但汇总"cnt=0/avg_clv=0.000"这种
        # 自相矛盾的日志(2026-07-19当次真实跑出过这个现象)。改成直接按本次实际更新
        # 的record id集合汇总，口径与上面UPDATE循环完全一致，不再依赖fetch_date猜测。
        with engine.connect() as conn:
            stats = conn.execute(text(f"""
                SELECT
                    COUNT(*) as cnt,
                    AVG(clv) as avg_clv,
                    SUM(CASE WHEN clv > 1.0 THEN 1 ELSE 0 END) as above_1
                FROM hit_recommendations
                WHERE id IN ({','.join(str(i) for i in _updated_ids)}) AND clv IS NOT NULL
            """)).fetchone()

        cnt, avg_clv, above_1 = stats
        avg_clv_val = avg_clv if avg_clv is not None else 0.0
        cnt = cnt or 0
        above_1 = above_1 or 0
        log.info(f"  📊 CLV计算完成: {updated} 条更新, 平均CLV={avg_clv_val:.3f}, "
                 f"优于收盘线 {above_1}/{cnt} ({above_1/max(cnt,1)*100:.0f}%)")

    return updated


def clv_report(fetch_date: str = None):
    """输出 CLV 总报告，评估推荐质量"""
    with engine.connect() as conn:
        stats = conn.execute(text("""
            SELECT
                fetch_date,
                COUNT(*) as total,
                AVG(clv) as avg_clv,
                MIN(clv) as min_clv,
                MAX(clv) as max_clv,
                SUM(CASE WHEN clv > 1.0 THEN 1 ELSE 0 END) as above_1,
                SUM(CASE WHEN clv > 1.05 THEN 1 ELSE 0 END) as above_105,
                AVG(CASE WHEN clv > 1.0 THEN clv ELSE NULL END) as avg_clv_wins
            FROM hit_recommendations
            WHERE clv IS NOT NULL
            GROUP BY fetch_date
            ORDER BY fetch_date DESC
            LIMIT 30
        """)).fetchall()

    if not stats:
        print("  暂无 CLV 数据（需等比赛开赛后计算）")
        return

    W = 90
    print("\n" + "=" * W)
    print("  📈 CLV（收盘线价值）报告")
    print("=" * W)
    print(f"  {'日期':12} {'总数':>5} {'均CLV':>7} {'CLV>1':>6} {'CLV>1.05':>9} {'赢面均CLV':>10}")
    print("  " + "-" * (W - 4))
    for row in stats:
        fd, total, avg_clv, min_c, max_c, above1, above105, avg_wins = row
        avg_clv = avg_clv or 0
        above1 = above1 or 0
        above105 = above105 or 0
        avg_wins = avg_wins or 0
        mark = "✅" if avg_clv > 1.0 else "⚠️"
        print(f"  {fd:12} {total:>5} {avg_clv:>7.3f} {f'{above1}/{total}':>6} "
              f"{f'{above105}/{total}':>9} {avg_wins:>10.3f} {mark}")
    print("=" * W)
    print("  CLV>1.0 = 推荐赔率优于收盘 → 长期正EV信号")


# ─── 7.5 比分玩法（correct_score）───────────────────────────────────────────
# 独立于其他10个玩法：有真实盘口(Pinnacle/qiety)才生成推荐，无盘口的比赛直接跳过，
# 不用模型概率当虚拟赔率兜底。名额独立于 MAX_RECS_PER_MATCH（每场比赛的比分推荐
# 走自己单独的1条/场配额，不与独赢/让球等其他玩法抢占那唯一名额）。
#
# 命中分不能直接复用 compute_hit_score()：那套公式里"模型置信度"= model_prob 本身，
# 是给独赢/让球/大小球这种2-3选1、model_prob正常在30%-70%的玩法设计的。比分玩法
# 有20+种可能结果，随便哪个具体比分的 model_prob 天然只有5%-20%（哪怕模型完全准、
# 哪怕edge很大也是如此），直接套用会导致比分玩法几乎永远过不了门槛。
# 这里"置信度"改用相对edge（模型概率相对市场隐含概率高出多少），才是这个市场真正
# 该衡量的信号——多选一市场里"离谱地看好某个冷门比分"和"轻微看好热门比分"，
# 只要edge比例相近，应该给相近的置信度，而不是被绝对概率压低。
CORRECT_SCORE_EDGE_SCALE = 0.35  # 2026-09-06起不再被_compute_correct_score_hit()使用
# （置信度改成绝对model_prob，见该函数docstring）；仍保留常量本身供
# _backtest_fixed_correct_score.py等历史回测脚本引用，不删除。
CORRECT_SCORE_PICKS_PER_MATCH = 3  # 每场比赛最多出几个比分推荐：1个首选+最多2个次选（都要独立过门槛，凑不够3个就有几个出几个）


def _compute_correct_score_hit(model_prob: float, cons_odds: float, implied_prob: float,
                                per_source_odds: list, league_tier: str = "") -> dict:
    """比分玩法专用命中分：覆盖度(30%) × 源一致性(30%) × 模型置信度(40%)。

    2026-09-06修复：置信度此前用"相对edge比率"(model_prob/implied_prob-1，
    CORRECT_SCORE_EDGE_SCALE=0.35封顶1.0)，跟全系统其他市场共用的
    compute_hit_score()置信度定义(=绝对model_prob本身)完全不是同一套逻辑——
    比分玩法是20-30个结果的市场，绝对概率天然就低(通常2%~20%)，但只要模型
    概率比市场隐含高出35%以上就能把置信度拉满1.0，哪怕绝对概率只有5%~15%。
    复盘37条真实结算候选(shadow_type='gated',market='correct_score')发现
    model_prob均值只有6.6%，hit_score却经常算到0.75~0.83（比让球/独赢进正式
    单的0.70门槛还高），且这37条里"每场命中分最高的那个"真实结算是0/23——
    命中分完全没有反映"这个比分到底有多大概率发生"，只反映了"模型跟市场差了
    多少"，这两件事在比分玩法这种低绝对概率的市场里几乎脱钩。改成跟
    compute_hit_score()同一套定义：置信度直接=绝对model_prob。比分玩法的
    model_prob天花板本身就远低于独赢/让球(最热门比分很少超过25%~30%)，这个
    改动会让比分玩法的hit_score整体大幅下降、能过HIT_SCORE_GLOBAL_THRESHOLD
    门槛的候选大幅减少——这是预期内的结果，是让门槛真正对应"这个比分有多大
    概率发生"，不是bug。edge(相对市场的边际)仍然算出来放进value_edge字段
    供参考，只是不再驱动置信度分量。"""
    n_src = len(per_source_odds)
    coverage_score = 0.5 + min(n_src / 2.0, 1.0) * 0.5

    if n_src >= 2:
        lo, hi = min(per_source_odds), max(per_source_odds)
        consistency_score = 1.0 - min(abs(hi - lo) / hi, 1.0) if hi > 0 else 0.5
    else:
        consistency_score = 0.60  # 单源无法交叉验证，给中性偏低分

    edge = (model_prob / implied_prob - 1.0) if implied_prob > 0 else 0.0
    confidence_score = min(max(model_prob, 0.0), 1.0)

    hit_score = coverage_score * 0.30 + consistency_score * 0.30 + confidence_score * 0.40
    hit_score *= LEAGUE_TIER_BOOST.get(league_tier, 1.0)
    hit_score = round(min(max(hit_score, 0.0), 1.0), 4)

    kelly = 0.0
    if model_prob > 0 and cons_odds > 1:
        kelly = (model_prob * cons_odds - 1) / (cons_odds - 1)
        kelly = max(0.0, min(kelly * KELLY_FRACTION, KELLY_MAX_RATIO))
    if kelly <= 0:
        hit_score = round(hit_score * 0.70, 4)

    confidence_label = "高" if hit_score >= 0.75 else "中" if hit_score >= 0.60 else "低"
    return {
        "hit_score": hit_score,
        "value_edge": round(edge, 4),
        "kelly_fraction": round(kelly, 4),
        "confidence": confidence_label,
    }


def _validation_result(rows, min_samples: int, min_roi: float, recent_n: int = 30,
                       gate_key: str | None = None) -> dict:
    """全部"转正"判定函数共用的统计口径。2026-08-01之前，全部10处判定只看点估计
    符号（n>=min_samples and roi>=min_roi），不做显著性检验——真实结算数据审计发现
    这个口径会把噪音当真实edge：n=95/平注ROI+18.7%这种案例算出来单尾t=1.14/p=0.25，
    完全不显著（95%置信区间下界是负的），但按旧口径(n>=30 and roi>=0)早就"转正"
    放行真实资金了。现在追加"单尾95%置信区间下界>0"这个条件（等价于单尾t检验
    p<0.05下拒绝"真实ROI<=0"的原假设）——单尾而非双尾，因为业务问题本身是单向的
    "能不能确认这个方向显著地比0好"，不关心"显著地比0差"（那种情形roi>=min_roi
    点估计条件本身就会先挡掉，不需要额外检验）。

    用正态z临界值1.645近似t分布临界值（min_samples=30时t_0.95,29≈1.699，跟1.645
    差距很小，标准做法，n>=30时够准，不额外引入scipy依赖）。n<2时方差算不出来，
    退化成只看点估计（样本太小任何显著性检验都没意义，维持原行为）。

    2026-08-01再次升级——追加"近期窗口"检验：审计football total/over时发现全历史
    显著性检验有个真实盲区：这个市场全历史ROI仍是+8.7%（样本够大，噪音被摊薄），
    但按周拆开看已经连续4周单调衰减到0%胜率，纯粹的全历史检验完全捕捉不到正在
    发生的真实衰减，因为老的好样本把新的坏样本稀释掉了。现在按fetch_date取最近
    recent_n条(默认30)单独算一次平注ROI点估计，必须也>=min_roi才放行——近期窗口
    只要求点估计不要求显著性(recent_n=30这么小的样本几乎不可能单独测出显著结果，
    要求"显著转正"等于直接判死；只要求"没有转负"是合理的最低限度过滤，用来当
    及时止损的哨兵，不是用来单独证明edge)。

    rows: (status, best_odds, fetch_date) 三元组列表。fetch_date用于内部按时间排序
    取最近窗口，调用方不需要预先排序；fetch_date缺失(None)的记录视为最旧、排最前。

    gate_key(FIX-003, 2026-09-12追加)：转正闸门桶标识（如 'total_over:football'）。
    统计检验通过后还要过 promotion_gate.check_promotion_gate() 两道结构性防护：
    ①预注册——promotion_registry.json 必须有该桶条目且 registered_at 早于本次样本
    的观察窗口末端（注册前积累的数据不能给注册后定义的假设做转正证明，堵住
    "先看到数据再定义候选"的事后挑选）；②多重比较防护——每自然季度最多放行
    QUARTERLY_PROMOTION_QUOTA(=1) 个新转正（14个桶各做α=0.05检验，滚动等于
    稳定地漏假阳性进真钱通道）。被闸门拦截时 validated=False 且返回 dict 带
    gate_blocked=拦截原因；已转正桶(registry status='promoted')直接放行不受影响。
    不传 gate_key 保持原行为（向后兼容）。"""
    n = len(rows)
    if n == 0:
        return {"validated": False, "n": 0, "roi": None, "win_rate": None,
                "ci_lower": None, "t_stat": None, "recent_roi": None, "recent_n": 0,
                "max_drawdown": None, "gate_blocked": None}
    rows_sorted = sorted(rows, key=lambda r: r[2] or "")
    pnl_list = [(r[1] - 1.0) if r[0] == "win" else -1.0 for r in rows_sorted]
    roi = sum(pnl_list) / n
    win_rate = sum(1 for r in rows_sorted if r[0] == "win") / n

    # FIX-008-5（2026-09-13）：最大回撤——按结算时间序（fetch_date升序）累计平注
    # 盈亏曲线的峰谷最大回落，单位=注。只作展示/风控参考，不参与转正判定
    # （判定口径不变：样本量+平注ROI+单尾CI下界+近30注哨兵+闸门）。
    _cum = _peak = 0.0
    max_drawdown = 0.0
    for _p in pnl_list:
        _cum += _p
        if _cum > _peak:
            _peak = _cum
        if _peak - _cum > max_drawdown:
            max_drawdown = _peak - _cum

    recent_pnl = pnl_list[-recent_n:]
    recent_n_actual = len(recent_pnl)
    recent_roi = sum(recent_pnl) / recent_n_actual if recent_n_actual else None
    recent_ok = (recent_roi is not None and recent_roi >= min_roi)

    # Bug修复(2026-08-11)：近期哨兵加时效性保护，破解自锁死循环。
    # 6个转正门槛里有3个(_total_over/_correct_score/_corner)读的是**生产表**
    # (hit_recommendations/corner_recommendations)而不是影子桶，一旦门槛关闭就
    # 不再产生新推荐 → 没有新结算样本 → "最近30注"窗口永远冻结在那批失败样本上
    # → 门槛永远打不开。实测：football total/over 的近30注窗口停在
    # 2026-07-10~07-18已冻结24天，07-19后只新增6条(需30条才能刷新窗口)，
    # 而该市场全历史 n=136/roi=+14.42%/ci_lower=+0.0075/t=1.73 **显著性其实是
    # 通过的**，纯粹被这个冻结窗口否决——推荐单因此从07-19起近乎停产一个月。
    # 处理：最新样本若已超过 VALIDATION_RECENT_MAX_AGE_DAYS 天，视为"无近期数据"，
    # 哨兵不再否决，退回只看全历史显著性。理由——基于24天前数据算出来的"近期
    # ROI"在任何定义下都不叫近期，它不具备"反映当前是否正在衰减"这个哨兵本职。
    # 注意这只解除**过期**哨兵的否决权，样本新鲜时哨兵照常生效。
    recent_stale = False
    _newest = rows_sorted[-1][2] if rows_sorted else None
    if _newest:
        try:
            _age = (datetime.now() - datetime.strptime(str(_newest)[:10], "%Y-%m-%d")).days
            recent_stale = _age > VALIDATION_RECENT_MAX_AGE_DAYS
        except (ValueError, TypeError):
            recent_stale = False
    if recent_stale:
        recent_ok = True

    if n < min_samples:
        validated, ci_lower, t_stat = False, None, None
    elif n < 2:
        validated, ci_lower, t_stat = (roi >= min_roi and recent_ok), None, None
    else:
        var = sum((x - roi) ** 2 for x in pnl_list) / (n - 1)
        se = (var / n) ** 0.5
        if se == 0:
            validated, ci_lower, t_stat = (roi >= min_roi and recent_ok), roi, None
        else:
            t_stat = roi / se
            ci_lower = roi - 1.645 * se
            validated = (roi >= min_roi) and (ci_lower > 0) and recent_ok
    # FIX-003 转正闸门：统计检验通过≠放行，还要过预注册+季度额度两道结构性防护
    gate_blocked = None
    if validated and gate_key:
        _we = rows_sorted[-1][2] if rows_sorted else None
        _ok, _reason = check_promotion_gate(gate_key, str(_we)[:10] if _we else None,
                                            logger=log)
        if not _ok:
            validated = False
            gate_blocked = _reason
            log.info(f"[promotion_gate] {gate_key} 统计检验通过但被闸门拦截: {_reason}")
    return {"validated": validated, "n": n, "roi": round(roi, 4), "win_rate": round(win_rate, 4),
            "ci_lower": round(ci_lower, 4) if ci_lower is not None else None,
            "t_stat": round(t_stat, 2) if t_stat is not None else None,
            "recent_roi": round(recent_roi, 4) if recent_roi is not None else None,
            "recent_n": recent_n_actual, "gate_blocked": gate_blocked,
            "max_drawdown": round(max_drawdown, 2)}


def _correct_score_validation_status() -> dict:
    """查已结算的比分玩法记录，判断样本量/ROI是否达标可以转正（进单注/主推荐单）。
    平注ROI：每条按 best_odds 计算（win=odds-1的净收益，lose=-1），不用实际Kelly注额，
    这样才能跟其他玩法历史上用同一把尺子判断"这个玩法本身有没有价值"，不受资金管理干扰。

    闭环结论（report_jc_closure.md，2026-09-12，竞彩视角1587期+31487场回测）：
    比分玩法水位37~49%（远超预估15~30%），DC泊松尾部对极端比分系统性高估
    （实测命中仅为模型implied的37%），整体ROI -38.9%，无sharp参照——
    该玩法的转正门槛应保持高位（当前MIN_ROI=5%），任何"比分edge"主张都必须
    先解释如何跨越这个量级的水位+尾部高估双重障碍。"""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT status, best_odds, fetch_date FROM hit_recommendations
                WHERE market='correct_score' AND status IN ('win','lose')
            """)).fetchall()
    except Exception:
        rows = []
    return _validation_result(rows, CORRECT_SCORE_VALIDATION_MIN_SAMPLES, CORRECT_SCORE_VALIDATION_MIN_ROI,
                              gate_key="correct_score")


def _corner_validation_status() -> dict:
    """查角球投注单(corner_model.py)已结算记录，判断是否达标可以转正为正式推荐单。
    2026-08-09新增——此前该玩法绕开了_validation_result()统一检验直接以正式身份
    上线，唯一依据是corner_model.py里一行没有样本量支撑的历史回测注释，违反北极星
    原则，现补上跟其他市场一致的双重检验门槛，达标前在推荐单里降级为影子观察单。

    注意（FIX-006）：report_jc_closure.md 的闭环结论不覆盖角球市场（该报告是竞彩
    1X2/比分/半全场视角），角球的证据链以本函数的结算样本检验为准，不能借
    closure报告的结论为角球转正/降级背书。"""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT status, odds, fetch_date FROM corner_recommendations
                WHERE status IN ('win','lose')
            """)).fetchall()
    except Exception:
        rows = []
    return _validation_result(rows, CORNER_VALIDATION_MIN_SAMPLES, CORNER_VALIDATION_MIN_ROI,
                              gate_key="corner")


def _sport_code_aliases(sport_code: str) -> tuple:
    """football/soccer 是同一个运动的两种拼写——unified_matches.sport_code 因数据源
    不同同时存在这两个字面值（实测：unified_matches/hit_recommendations/under_shadow_bets
    三张表都同时有'football'和'soccer'两种值），下游所有按sport_code精确匹配的转正
    判断函数(_under_validation_status/_moneyline_validation_status/
    _team_total_validation_status/_lstm_validation_status)如果只查其中一个字面值，
    会把本该合并的同一个真实样本人为拆成两份，既削弱统计功效，也可能让其中一份
    (更小、更容易被短期噪音带过门槛的)子样本先达标转正——2026-07-22核查
    team_total/under真实结算发现-41.5%ROI(58注)后，追查到这个数据不统一问题，
    这类转正判断必须把两个字面值合并当同一份样本查，不能各查各的。篮球没有这个
    问题，原样返回。"""
    sc = (sport_code or "").lower()
    if sc in ("football", "soccer"):
        return ("football", "soccer")
    return (sport_code, sport_code)


_UNDER_VALIDATION_CACHE: dict = {}  # sport_code -> status dict，进程内缓存，避免每条候选都查一次DB


def _under_validation_status(sport_code: str = "") -> dict:
    """查 under_shadow_bets 里已结算的小球影子记录，判断样本量/ROI是否达标可以转正。
    跟比分玩法用同一套逻辑：平注ROI(按best_odds算)，不用实际Kelly注额。
    按 sport_code 分开判断（足球小球和篮球小球是两回事，数据源、进球/得分分布完全不同，
    不能因为足球小球积累够了就连带放开篮球小球，反之亦然）。"""
    if sport_code in _UNDER_VALIDATION_CACHE:
        return _UNDER_VALIDATION_CACHE[sport_code]
    try:
        with engine.connect() as conn:
            if sport_code:
                _sp1, _sp2 = _sport_code_aliases(sport_code)
                rows = conn.execute(text("""
                    SELECT status, best_odds, fetch_date FROM under_shadow_bets
                    WHERE status IN ('win','lose') AND sport_code IN (:sp1, :sp2)
                """), {"sp1": _sp1, "sp2": _sp2}).fetchall()
            else:
                rows = conn.execute(text("""
                    SELECT status, best_odds, fetch_date FROM under_shadow_bets
                    WHERE status IN ('win','lose')
                """)).fetchall()
    except Exception:
        rows = []
    result = _validation_result(rows, UNDER_VALIDATION_MIN_SAMPLES, UNDER_VALIDATION_MIN_ROI,
                                gate_key=f"under:{sport_code or 'all'}")
    _UNDER_VALIDATION_CACHE[sport_code] = result
    return result


_MONEYLINE_VALIDATION_CACHE: dict = {}  # (sport_code, outcome) -> status dict


def _moneyline_validation_status(sport_code: str, outcome: str | None = None) -> dict:
    """查 moneyline_shadow_full 里已结算的独赢(moneyline)完整候选，判断样本量/ROI
    是否达标可以放行。足球篮球分开判断（3选1 vs 2选1结构不同，不能互相带动转正）。
    注意 market 字段固定存的是 'moneyline'（足球胜平负和篮球独赢底层market码是同一个
    字符串，靠 sport_code 区分，展示层的"胜平负"/"独赢"标签是按sport分流的，见 Pass3
    里 shadow_type 的分类逻辑）。

    outcome参数(2026-07-24追加)：复盘发现按方向拆开后表现分裂严重——篮球客胜(away)
    真实结算ROI+74.6%(hit_recommendations,n=20)，主胜(home)反而-24.9%(n=20，亏钱)，
    原来只按sport聚合判断会让主胜跟着客胜的达标状态一起被放行，是本函数的真实bug，
    用户已确认要求把篮球主胜降级为只留影子观察、不再拿真实资金下注。传outcome时只
    统计该方向；不传(None)保留旧的合并统计口径供展示区块"整体候选池"部分参考。

    数据源修复(同日，跟_team_total_validation_status()当初绕开截断偏差的思路一致)：
    原来查shadow_recommendations，这张表跟其他所有shadow_multi桶一样，每天只保留
    按hit_score排序的前10条(见generate_recommendations()"其他市场影子写库"那段
    sorted(...)[:10])——这个截断对来对moneyline算出的ROI和真实hit_recommendations
    记录方向相反(实测篮球home在截断样本里+19.7%，真实结算却是-24.9%)，不能拿来做
    转正判断。改查moneyline_shadow_full——这张表专门为本函数新建，全部outcome完整
    收集、不做任何截断，是无偏样本。"""
    _ck = (sport_code, outcome)
    if _ck in _MONEYLINE_VALIDATION_CACHE:
        return _MONEYLINE_VALIDATION_CACHE[_ck]
    try:
        with engine.connect() as conn:
            _sp1, _sp2 = _sport_code_aliases(sport_code)
            if outcome:
                rows = conn.execute(text("""
                    SELECT status, best_odds, fetch_date FROM moneyline_shadow_full
                    WHERE market='moneyline' AND status IN ('win','lose')
                      AND sport_code IN (:sp1, :sp2) AND outcome=:oc
                """), {"sp1": _sp1, "sp2": _sp2, "oc": outcome}).fetchall()
            else:
                rows = conn.execute(text("""
                    SELECT status, best_odds, fetch_date FROM moneyline_shadow_full
                    WHERE market='moneyline' AND status IN ('win','lose') AND sport_code IN (:sp1, :sp2)
                """), {"sp1": _sp1, "sp2": _sp2}).fetchall()
    except Exception:
        rows = []
    result = _validation_result(rows, MONEYLINE_VALIDATION_MIN_SAMPLES, MONEYLINE_VALIDATION_MIN_ROI,
                                gate_key=f"moneyline:{sport_code}:{outcome or 'all'}")
    _MONEYLINE_VALIDATION_CACHE[_ck] = result
    return result


_TOTAL_OVER_VALIDATION_CACHE: dict = {}  # sport_code -> status dict


def _total_over_validation_status(sport_code: str) -> dict:
    """查 hit_recommendations 里已结算的全场大小球/大球(market='total', outcome='over')
    记录，判断样本量/ROI是否达标可以转正。2026-08-01新增——此前这是全系统唯一一个
    "转正"判定完全不存在的市场：_in_scope()对它是硬编码 `if market=='total' and
    outcome=='over': return True`，零验证、无条件放行，是当前唯一真正在跑、拿真实
    资金下注的市场，却是审查覆盖最薄弱的一个。真实数据审计(2026-08-01)显示这个市场
    足球方向已经连续4周单调衰减(周胜率62.5%→45.5%→35.7%→0%)，但全历史ROI仍有
    +8.7%(全历史显著性检验也测不出来，因为老样本把近期衰减稀释掉了)——这正是
    _validation_result()追加"近期窗口"检验要堵的漏洞，本函数是第一个使用该功能
    的调用方。跟其他所有转正函数一样，直接查hit_recommendations是安全的，这个
    市场从未受到shadow_recommendations那种top-10每日截断的影响(它是_in_scope()
    唯一放行的市场，population本身就是它的全部候选，不存在"被截断"的问题)。"""
    if sport_code in _TOTAL_OVER_VALIDATION_CACHE:
        return _TOTAL_OVER_VALIDATION_CACHE[sport_code]
    try:
        with engine.connect() as conn:
            _sp1, _sp2 = _sport_code_aliases(sport_code)
            rows = conn.execute(text("""
                SELECT status, best_odds, fetch_date FROM hit_recommendations
                WHERE market='total' AND outcome='over' AND status IN ('win','lose')
                  AND sport_code IN (:sp1, :sp2)
            """), {"sp1": _sp1, "sp2": _sp2}).fetchall()
    except Exception:
        rows = []
    result = _validation_result(rows, UNDER_VALIDATION_MIN_SAMPLES, UNDER_VALIDATION_MIN_ROI,
                                gate_key=f"total_over:{sport_code}")
    _TOTAL_OVER_VALIDATION_CACHE[sport_code] = result
    return result


_TEAM_TOTAL_VALIDATION_CACHE: dict = {}  # (sport_code, outcome) -> status dict


def _team_total_validation_status(sport_code: str, outcome: str | None = None) -> dict:
    """查 team_total_shadow_full 里已结算的球队大小(team_total及其home/away变体)
    完整候选样本，判断样本量/ROI是否达标可以转正。2026-07-19新增——此前球队大小市场
    完全没有影子观察单/转正判断，是唯一没有历史证据支撑的市场（用户核对
    hit_recommendations发现球队大小/大球只有25场结算样本，太小不足以下结论，
    暴露出这个缺口）。跟小球一样按 sport_code 分开判断（足球单队进球0-3分布
    和篮球单队得分80-120分布完全不是一回事，样本不能混）。market字段是
    'team_total'/'team_total_home'/'team_total_away'三种都算（同一市场家族，
    合并统计避免样本过于稀疏）。

    outcome参数(2026-07-19追加)：用_backtest_team_total_shadow.py回测169场历史
    真实数据后，足球over/under合并虽有51场(过30场门槛)，但拆开看差异明显——
    over 24场70.8%胜率/单均ROI+43.3%，under 27场59.3%胜率/单均ROI+4.7%，用户
    明确要求只放行大球(over)方向转正，小球方向证据不够强不能跟着搭车。传
    outcome='over'/'under' 时只统计该方向；不传(None)时保留旧的合并统计口径
    供展示区块的"整体候选池"部分参考。

    数据源修复(2026-07-22)：原来查shadow_recommendations，这张表所有shadow_type
    (包括team_total)都在generate_recommendations()结尾按hit_score每天只保留前10条
    (见"其他市场影子写库"那段sorted(...)[:10])——这个截断对"仅供人工浏览"的展示
    区块没问题，但本函数的football/over结果同时被_in_scope()用来决定"足球球队大小
    (大球)"能不能真正进正式推荐单、拿真实资金下注，用一个每天只留最自信10条的小样本
    (天然偏向模型高置信度，可能重演"小球"当初小样本看着好、真实放量后血亏的same坑)
    做真实资金放行判断，风险/严谨性都不够。改成查team_total_shadow_full——这张表
    专门为本函数新建，大球+小球都完整收集、不做任何截断，是无偏样本。"""
    _ck = (sport_code, outcome)
    if _ck in _TEAM_TOTAL_VALIDATION_CACHE:
        return _TEAM_TOTAL_VALIDATION_CACHE[_ck]
    try:
        with engine.connect() as conn:
            _sp1, _sp2 = _sport_code_aliases(sport_code)
            if outcome:
                rows = conn.execute(text("""
                    SELECT status, best_odds, fetch_date FROM team_total_shadow_full
                    WHERE market IN ('team_total','team_total_home','team_total_away')
                      AND status IN ('win','lose') AND sport_code IN (:sp1, :sp2) AND outcome=:oc
                """), {"sp1": _sp1, "sp2": _sp2, "oc": outcome}).fetchall()
            else:
                rows = conn.execute(text("""
                    SELECT status, best_odds, fetch_date FROM team_total_shadow_full
                    WHERE market IN ('team_total','team_total_home','team_total_away')
                      AND status IN ('win','lose') AND sport_code IN (:sp1, :sp2)
                """), {"sp1": _sp1, "sp2": _sp2}).fetchall()
    except Exception:
        rows = []
    result = _validation_result(rows, TEAM_TOTAL_VALIDATION_MIN_SAMPLES, TEAM_TOTAL_VALIDATION_MIN_ROI,
                                gate_key=f"team_total:{sport_code}:{outcome or 'all'}")
    _TEAM_TOTAL_VALIDATION_CACHE[_ck] = result
    return result


def _display_parallel_lines(fetch_date: str, desk_file: str | None) -> None:
    """打印+追加保存"独立平行线"区块(目前只有legacy_team_total_under_recs)。

    Bug修复(2026-08-02)：这块展示代码原来在generate_recommendations()内部，
    但它读的legacy_team_total_under_recs要靠_generate_legacy_team_total_under()
    生成，而后者在_run_one_date()里排在generate_recommendations()**之后**调用
    (原因：_generate_legacy_team_total_under读的team_total_shadow_full是
    generate_recommendations()这次运行刚写好的，必须等它跑完)。这导致展示代码
    永远读到"这次运行开始前"的旧数据(比如今天8个多小时前另一次运行留下的)，
    实测完整跑一轮后文件里这个区块完全消失(0行)——不是查询逻辑错，是执行顺序
    的先有鸡还是先有蛋问题。拆成独立函数，在_run_one_date()里挪到
    _generate_legacy_team_total_under()调用之后再执行，解决执行顺序问题。"""
    def _league_zh_local(name: str, sport: str = "") -> str:
        _is_women = "women" in name.lower()
        for keyword, zh in _LEAGUE_ZH:
            if keyword.lower() in name.lower():
                return zh if not _is_women or "女" in zh else zh + "(女)"
        return name

    def _fmt_time_local(kickoff_utc: str) -> str:
        try:
            dt = datetime.fromisoformat((kickoff_utc or "").replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            bj = dt.astimezone(timezone(timedelta(hours=8)))
            return bj.strftime("%m月%d日%H:%M")
        except Exception:
            return "--月--日--:--"

    def _tw_local(name: str, width: int) -> str:
        result, w = "", 0
        for ch in name:
            cw = 2 if ord(ch) > 127 else 1
            if w + cw > width:
                break
            result += ch
            w += cw
        return result + " " * (width - w)

    from team_zh import team_zh as _team_zh_local

    W = 143
    _PARALLEL_LINE_TABLES = [
        ("legacy_team_total_under_recs", "足球球队大小/小球「老逻辑」平行线（非反着买，原方向下注）"),
    ]
    out_lines: list[str] = []
    for _tbl, _tbl_title in _PARALLEL_LINE_TABLES:
        try:
            with engine.connect() as _pl_conn:
                _pl_rows = _pl_conn.execute(text(f"""
                    SELECT home_team, away_team, league_name, kickoff_utc, market, outcome,
                           handicap, best_odds, model_prob, kelly_fraction, hit_score
                    FROM {_tbl} WHERE fetch_date=:fd ORDER BY hit_score DESC
                """), {"fd": fetch_date}).fetchall()
        except Exception as _pl_e:
            log.warning(f"  {_tbl_title}读取异常（跳过展示）: {_pl_e}")
            continue
        if not _pl_rows:
            continue
        out_lines.append("")
        out_lines.append("─" * W)
        out_lines.append(f"  🔀  {_tbl_title}  [仅数据追踪，独立于正式推荐单，见_generate_*函数说明]")
        out_lines.append("─" * W)
        out_lines.append(f"  {'开赛时间':<12} {'联赛':<14} {'主队':<14}{'客队':<14} {'市场':<6} {'方向':<10} {'赔率':<6} {'p融合':<7} {'K₁/₄':<7} {'命中分':<8}")
        out_lines.append("-" * W)
        for (_pl_home, _pl_away, _pl_league, _pl_ko, _pl_market, _pl_outcome, _pl_hc,
             _pl_odds, _pl_mp, _pl_kf, _pl_hs) in _pl_rows:
            _pl_t = _tw_local(_fmt_time_local(_pl_ko or ""), 14)
            _pl_lg = _tw_local(_league_zh_local(_pl_league or "", ""), 14)
            _pl_h = _tw_local(f"[主]{_team_zh_local(_pl_home)}", 14)
            _pl_a = _tw_local(f"[客]{_team_zh_local(_pl_away)}", 14)
            _pl_mk_zh = _MARKET_ZH.get(_pl_market, _pl_market)
            _pl_out_zh = _OUTCOME_ZH.get(_pl_outcome, _pl_outcome)
            if _pl_hc is not None:
                _pl_out_zh = f"{_pl_out_zh}{_pl_hc}"
            out_lines.append(f"  {_pl_t}{_pl_lg}{_pl_h}{_pl_a} "
                         f"{_pl_mk_zh:<6} {_pl_out_zh:<10} {_pl_odds:<6.2f} {_pl_mp:<7.3f} {_pl_kf:<7.4f} {_pl_hs:<8.3f}")
        out_lines.append("─" * W)
        out_lines.append(f"  共 {len(_pl_rows)} 条（Top7截断口径，非正式推荐单，样本证据强度见项目记忆说明）")

    if not out_lines:
        return
    for ln in out_lines:
        print(ln)
    if desk_file:
        try:
            with open(desk_file, "a", encoding="utf-8") as _f:
                _f.write("\n".join(out_lines) + "\n")
        except Exception as _e:
            log.warning(f"  平行线区块追加保存失败: {_e}")


def _generate_fotmob_parlay(fetch_date: str, desk_file: str | None) -> None:
    """FotMob三桶(角球/球队大小/大小球)串关推荐——2026-08-20用户要求的永久规则：
    每天从 FotMob角球影子观察单 / FotMob球队大小影子观察单 / FotMob大小球影子观察单
    各随机挑选2场比赛，组成6串1（串关原则：同一场比赛只能选一种玩法，三个桶
    之间按队名去重，不看unified_id——fotmob_corner桶的unified_id是"corner_联赛_
    主队_客队_线"这种合成字符串，不是标准unified_matches体系的id，用unified_id
    去重会漏判"其实是同一场比赛"）。某个桶当天候选不足2场时"有多少算多少"，
    不强行凑数，凑不出任何候选就整个跳过不生成。

    只从当天(fetch_date)已经落库的shadow_recommendations读取候选，因此必须在
    generate_recommendations()跑完之后调用（此时当天三个FotMob桶才是这次运行
    写好的新数据）——跟_display_parallel_lines()/_generate_and_display_fade_manual()
    同一套"读库→格式化→打印+追加保存到desk_file"模式，见CLAUDE.md"FotMob串关
    推荐规则"永久规则。"""
    import random as _random

    _POOL_ORDER = [
        ("fotmob_corner", "FotMob角球", 2),
        ("fotmob_team_total", "FotMob球队大小", 2),
        ("fotmob_totals", "FotMob大小球", 2),
    ]

    def _match_key(home: str, away: str) -> tuple:
        return ((home or "").lower().strip(), (away or "").lower().strip())

    try:
        with engine.connect() as _fp_conn:
            _fp_rows = _fp_conn.execute(text("""
                SELECT shadow_type, unified_id, league_name, home_team, away_team, kickoff_utc,
                       market, outcome, handicap, best_odds, model_prob, hit_score
                FROM shadow_recommendations
                WHERE fetch_date=:fd AND shadow_type IN ('fotmob_corner','fotmob_team_total','fotmob_totals')
            """), {"fd": fetch_date}).fetchall()
    except Exception as _fp_e:
        log.warning(f"  FotMob串关推荐读取候选异常（跳过）: {_fp_e}")
        return

    _by_type: dict = {}
    for _row in _fp_rows:
        _by_type.setdefault(_row[0], []).append(_row)

    used_matches: set = set()
    legs: list = []
    for _stype, _label, _n in _POOL_ORDER:
        _rows = _by_type.get(_stype, [])
        _by_match: dict = {}
        for _row in _rows:
            _k = _match_key(_row[3], _row[4])
            if _k in used_matches:
                continue
            _by_match.setdefault(_k, []).append(_row)
        _matches = list(_by_match.keys())
        _pick_n = min(_n, len(_matches))
        for _m in _random.sample(_matches, _pick_n):
            _chosen = _random.choice(_by_match[_m])
            legs.append((_label, _chosen))
            used_matches.add(_m)

    if not legs:
        log.info("  🎲 FotMob串关推荐: 今日三个桶均无候选，跳过")
        return

    from team_zh import team_zh as _team_zh_local

    def _league_zh_local(name: str) -> str:
        for keyword, zh in _LEAGUE_ZH:
            if keyword.lower() in (name or "").lower():
                return zh
        return name or ""

    def _fmt_time_local(kickoff_utc: str) -> str:
        try:
            dt = datetime.fromisoformat((kickoff_utc or "").replace(" ", "T").replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            bj = dt.astimezone(timezone(timedelta(hours=8)))
            return bj.strftime("%m月%d日%H:%M")
        except Exception:
            return "--月--日--:--"

    def _tw_local(name: str, width: int) -> str:
        result, w = "", 0
        for ch in name:
            cw = 2 if ord(ch) > 127 else 1
            if w + cw > width:
                break
            result += ch
            w += cw
        return result + " " * (width - w)

    W = 130
    out_lines: list[str] = [
        "",
        "═" * W,
        f"  🎲  FotMob串关推荐单  [{fetch_date}]  {len(legs)}串1"
        f"（角球/球队大小/大小球各随机挑2场，同场只选一种玩法，凑不够就有多少算多少）",
        "═" * W,
        f"  {'序':>3}  {'开赛时间':<12} {'联赛':<16} {'主队':<16} {'客队':<16} {'来源桶':<14} {'市场':<8} {'方向':<12} {'赔率':<6} {'p融合'}",
        "─" * W,
    ]
    _combined_odds = 1.0
    for _i, (_label, _row) in enumerate(legs, 1):
        (_stype, _uid, _league, _home, _away, _ko, _market, _outcome, _hc, _odds, _mp, _hs) = _row
        _combined_odds *= _odds
        _t   = _tw_local(_fmt_time_local(_ko), 14)
        _lg  = _tw_local(_league_zh_local(_league), 16)
        _hm  = _tw_local(f"[主]{_team_zh_local(_home)}", 16)
        _aw  = _tw_local(f"[客]{_team_zh_local(_away)}", 16)
        _mkt_zh = _MARKET_ZH.get(_market, _market)
        _out_zh = _OUTCOME_ZH.get(_outcome, _outcome)
        if _hc is not None:
            _out_zh = f"{_out_zh}{_hc}"
        out_lines.append(
            f"  {_i:>3}.  {_t}{_lg}{_hm}{_aw}"
            f" {_label:<14} {_mkt_zh:<8} {_out_zh:<12} {_odds:<6.2f} {_mp:<7.3f}"
        )
    out_lines.append("─" * W)
    out_lines.append(f"  共{len(legs)}串1  组合总赔率(连乘) = {_combined_odds:.2f}")
    out_lines.append("  ⚠️ 三个来源桶均未转正为正式推荐（转正状态见上方各自影子观察单区块），本串关属仅观察/试验性质，非正式推荐单")
    out_lines.append("═" * W)

    for _ln in out_lines:
        print(_ln)
    if desk_file:
        try:
            with open(desk_file, "a", encoding="utf-8") as _f:
                _f.write("\n".join(out_lines) + "\n")
        except Exception as _e:
            log.warning(f"  FotMob串关推荐追加保存失败: {_e}")


def _safe_delete_hit_recs(conn, fetch_date: str, fv_clause: str, n_new_picks: int, tag: str) -> set:
    """FIX-016-3（2026-09-15）重跑删历史防护——hit_recommendations 的 DELETE+INSERT
    重写模式有两条铁律：
    ① DELETE 只限未结算行 status IN ('pending','in_slip')——已结算行
      (win/lose/push/void) 是真实盈亏档案，分析流程永远不许触碰；
    ② 本轮新候选为空时跳过 DELETE 并显式 WARNING——历史日期重跑分析时投注窗口
      锚真实墙钟必然 0 候选（FIX-015-3 已定性），不挡的话当日推荐会被静默清空
      （09-13 v1×2+v2×2 四行被删实证，FIX-015 已人工重建）。
    返回已结算行的 (unified_id, market, outcome) 键集合——调用方 INSERT 前必须
    跳过这些键，否则"已结算行保留+同候选重插"会产生重复计账行（FIX-016-3b，
    09-13 league_ah_edge Mantova 两行 lose 实证：①留下旧 lose 行后新候选又插了
    一条同场同方向 pending，被结算成第二条 lose）。
    注意后果：候选为空的同日重跑会留下上一轮的 pending 旧行（不再自动清理），
    这是刻意的"宁可多留不可误删"，WARNING 会提醒人工核对。
    """
    if n_new_picks == 0:
        log.warning(f"  🛡 FIX-016-3防护: {tag} 本轮候选为空，跳过清空 {fetch_date} 旧推荐行"
                    f"（历史日期重跑/全量被拦时旧行原样保留，请人工核对）")
        return set()
    settled_keys = {(r[0], r[1], r[2]) for r in conn.execute(text(
        f"SELECT unified_id, market, outcome FROM hit_recommendations "
        f"WHERE fetch_date=:fd AND {fv_clause} AND status NOT IN ('pending','in_slip')"),
        {"fd": fetch_date})}
    conn.execute(text(f"DELETE FROM hit_recommendations WHERE fetch_date=:fd AND {fv_clause} "
                      "AND status IN ('pending','in_slip')"), {"fd": fetch_date})
    return settled_keys


def _generate_and_display_fade_manual(fetch_date: str, desk_file: str | None) -> int:
    """反着买人工批准转正(fade_manual)——2026-08-02用户明确批准写入正式推荐单的
    2个市场：篮球独赢旧口径反着买(basketball_moneyline_fade_recs)、篮球小球反着买
    (basketball_under_fade_recs)。原来这段逻辑在generate_recommendations()内部，
    2026-08-03排查"今天fade_manual完全消失"时发现根因：它读的两张fade表要靠
    _generate_basketball_under_fade()/_generate_basketball_moneyline_fade()生成，
    而这两个函数在_run_one_date()里排在generate_recommendations()**之后**调用
    (依赖generate_recommendations()写的shadow_recommendations/under_shadow_bets)。
    跨天时新一天的fade表在generate_recommendations()运行时还是空的(还没触发生成)，
    导致本函数(当时在旧位置)永远读到"运行开始前"的旧数据，跟_display_parallel_lines()
    此前修的展示顺序bug是同一类问题。现拆成独立函数，在_run_one_date()里排在三个
    _generate_*_fade()调用之后运行，此时两张源表才是这次运行的新数据。

    职责：读两张fade表当天数据→写入hit_recommendations(formula_version='fade_manual')
    →打印+追加保存到desk_file一段详细说明(市场/依据/反着买前后方向+概率+赔率，
    2026-08-03用户要求必须在正式投注单里能直接看到，不能只存在DB reason字段里)。
    """
    def _league_zh_local(name: str, sport: str = "") -> str:
        _is_women = "women" in name.lower()
        for keyword, zh in _LEAGUE_ZH:
            if keyword.lower() in name.lower():
                return zh if not _is_women or "女" in zh else zh + "(女)"
        return name

    from team_zh import team_zh as _team_zh_local

    _FADE_MANUAL_SOURCES = [
        ("basketball_moneyline_fade_recs",
         "篮球独赢(旧口径)反着买——用户人工批准转正(2026-08-02)，未通过算法_in_scope()验证，"
         "统计依据n=36/ROI+51.13%/p=0.035(另一次测量n=42/+45.35%/p=0.034)，p值未稳定过0.05门槛，"
         "样本量小且多次测量高度重叠，非确凿edge"),
        # 篮球小球反着买(basketball_under_fade_recs)已于2026-09-02暂停转正——批准时
        # 依据是n=55/ROI+23.16%/p=0.057的薄弱回测，2026-08-02批准至今一个月生产实盘
        # 复核：n=24已结算，真实flat-unit ROI=-29.2%(命中率37.5%)，跟批准时的回测结论
        # 方向相反，印证了当初"p值未稳定过0.05门槛"的担忧。同期篮球独赢反着买(上面
        # 那条，home+away合计n=15)生产ROI仍为正(+22.5%)，故只暂停这一条，独赢反着买
        # 继续保留。_generate_basketball_under_fade()仍照常运行、继续写
        # basketball_under_fade_recs表做纯观察追踪，只是不再从这里promote进
        # hit_recommendations——如果后续样本转正为正ROI可以重新加回来。
        # ("basketball_under_fade_recs",
        #  "篮球小球反着买——用户人工批准转正(2026-08-02)，未通过算法_in_scope()验证，"
        #  "统计依据n=55/ROI+23.16%/p=0.057(另一次测量n=50/p=0.058)，p值未稳定过0.05门槛，"
        #  "样本量小且多次测量高度重叠，非确凿edge"),
    ]
    _FADE_OPPOSITE_OUTCOME = {"home": "away", "away": "home", "over": "under", "under": "over"}
    _fade_manual_recs = []
    with engine.connect() as _fm_conn:
        for _fm_tbl, _fm_reason in _FADE_MANUAL_SOURCES:
            _fm_rows = _fm_conn.execute(text(f"""
                SELECT unified_id, sport_code, league_name, home_team, away_team, kickoff_utc,
                       market, outcome, handicap, best_odds, model_prob, kelly_fraction, hit_score
                FROM {_fm_tbl} WHERE fetch_date=:fd
            """), {"fd": fetch_date}).fetchall()
            for (uid, sport, league, home, away, kickoff, market, outcome, hc, odds, mp, kf, hs) in _fm_rows:
                if not odds or odds <= 1.0:
                    continue
                _implied = round(1.0 / odds, 4) if odds else None
                _orig_outcome = _FADE_OPPOSITE_OUTCOME.get(outcome, "?")
                _orig_zh = _OUTCOME_ZH.get(_orig_outcome, _orig_outcome)
                _disp_prob = round(1.0 - mp, 4) if mp is not None else None
                _orig_odds = _fade_opposite_odds(market, _orig_outcome, hc, uid, fetch_date)
                _fade_manual_recs.append({
                    "unified_id": uid, "sport_code": sport, "league_name": league,
                    "home_team": home, "away_team": away, "kickoff_utc": kickoff,
                    "market": market, "outcome": outcome, "handicap": hc,
                    "best_odds": odds, "best_source": "consensus_fade",
                    "model_prob": _disp_prob, "implied_prob": _implied,
                    "value_edge": None, "kelly_fraction": kf,
                    "hit_score": hs, "hit_score_v2": hs,
                    "confidence": "人工批准(反着买)",
                    "reason": f"{_fm_reason}；原始模型判断：{_orig_zh} {mp:.1%}（本行p融合={_disp_prob:.1%}是"
                              f"1-原始概率的二元互补近似，不是重新拟合的模型输出）",
                    "fetch_date": fetch_date, "predicted_score": "-",
                    "_fade_orig_outcome": _orig_outcome, "_fade_orig_prob": mp,
                    "_fade_orig_odds": _orig_odds, "_fade_basis": _fm_reason,
                })

    _now_fm = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with engine.begin() as conn:
        _skip_fm = _safe_delete_hit_recs(conn, fetch_date, "formula_version='fade_manual'", len(_fade_manual_recs), "fade_manual")
        for rec in _fade_manual_recs:
            if (rec["unified_id"], rec["market"], rec["outcome"]) in _skip_fm:
                log.info(f"  🛡 FIX-016-3防护: fade_manual {rec['home_team']} vs {rec['away_team']} "
                         f"{rec['market']}/{rec['outcome']} 已有已结算行，跳过重插（防重复计账）")
                continue
            conn.execute(text("""
                INSERT INTO hit_recommendations
                (unified_id,sport_code,league_name,home_team,away_team,kickoff_utc,
                 market,outcome,best_odds,best_source,model_prob,implied_prob,
                 value_edge,kelly_fraction,hit_score,hit_score_v2,confidence,reason,
                 status,fetch_date,created_at,handicap,formula_version)
                VALUES
                (:unified_id,:sport_code,:league_name,:home_team,:away_team,:kickoff_utc,
                 :market,:outcome,:best_odds,:best_source,:model_prob,:implied_prob,
                 :value_edge,:kelly_fraction,:hit_score,:hit_score_v2,:confidence,:reason,
                 'pending',:fetch_date,:now,:handicap,'fade_manual')
            """), {**rec, "now": _now_fm})
    if _fade_manual_recs:
        log.info(f"  ✅ 反着买人工批准转正: {len(_fade_manual_recs)} 条 → hit_recommendations(formula_version='fade_manual')")
    else:
        return 0

    out_lines: list[str] = []
    _FW = 143
    out_lines.append("")
    out_lines.append("=" * _FW)
    out_lines.append("  📋 反着买正式推荐（追加，formula_version=fade_manual，人工批准非算法验证）")
    out_lines.append("=" * _FW)
    out_lines.append(f"  {'开赛时间':<12} {'联赛':<14} {'主队':<14}{'客队':<14} {'市场':<6} {'方向':<10} {'赔率':<6} {'p融合':<7} {'K₁/₄':<7} {'命中分':<8}")
    out_lines.append("-" * _FW)
    for _fr in _fade_manual_recs:
        _t = _fr.get("kickoff_utc") or ""
        try:
            _dt = datetime.fromisoformat(_t.replace("Z", "+00:00"))
            if _dt.tzinfo is None:
                _dt = _dt.replace(tzinfo=timezone.utc)
            _t_disp = _dt.astimezone(timezone(timedelta(hours=8))).strftime("%m月%d日%H:%M")
        except Exception:
            _t_disp = "--月--日--:--"
        _mkt_zh = _MARKET_ZH.get(_fr["market"], _fr["market"])
        _out_zh = _OUTCOME_ZH.get(_fr["outcome"], _fr["outcome"])
        if _fr.get("handicap") is not None:
            _out_zh = f"{_out_zh}{_fr['handicap']}"
        out_lines.append(f"  {_t_disp:<14}{_league_zh_local(_fr['league_name'], _fr.get('sport_code','')):<16}"
                         f"[主]{_team_zh_local(_fr['home_team'])[:12]:<12}[客]{_team_zh_local(_fr['away_team'])[:12]:<12} "
                         f"{_mkt_zh:<6} {_out_zh:<10} {_fr['best_odds']:<6.2f} {_fr['model_prob']:<7.3f} "
                         f"{_fr['kelly_fraction']:<7.4f} {_fr['hit_score']:<8.3f}")
    out_lines.append("=" * _FW)
    out_lines.append(f"  共 {len(_fade_manual_recs)} 条（人工批准转正，见项目记忆project_fade_strategy_promotion_0802）")
    out_lines.append("")
    out_lines.append("─" * _FW)
    out_lines.append("  🔀  反着买详细说明")
    out_lines.append("─" * _FW)
    for _fi, _fr in enumerate(_fade_manual_recs, 1):
        _fmkt_zh = _MARKET_ZH.get(_fr["market"], _fr["market"])
        _fdisp_zh = _OUTCOME_ZH.get(_fr["outcome"], _fr["outcome"])
        _forig_zh = _OUTCOME_ZH.get(_fr["_fade_orig_outcome"], _fr["_fade_orig_outcome"])
        if _fr.get("handicap") is not None:
            _fdisp_zh = f"{_fdisp_zh}{_fr['handicap']}"
            _forig_zh = f"{_forig_zh}{_fr['handicap']}"
        _forig_odds_str = f"{_fr['_fade_orig_odds']:.2f}" if _fr.get("_fade_orig_odds") else "未查到"
        out_lines.append(f"  [{_fi}] {_team_zh_local(_fr['home_team'])} vs {_team_zh_local(_fr['away_team'])}"
                         f"（{_league_zh_local(_fr['league_name'], _fr.get('sport_code',''))}）")
        out_lines.append(f"      市场：{_fmkt_zh}")
        out_lines.append(f"      反着买依据：{_fr['_fade_basis']}")
        out_lines.append(f"      反着买之前（模型原判）：{_forig_zh}  概率{_fr['_fade_orig_prob']:.1%}  赔率{_forig_odds_str}")
        out_lines.append(f"      反着买之后（实际下注）：{_fdisp_zh}  概率{1-_fr['_fade_orig_prob']:.1%}(二元互补近似)  赔率{_fr['best_odds']:.2f}")
    out_lines.append("─" * _FW)

    for ln in out_lines:
        print(ln)
    if desk_file:
        try:
            with open(desk_file, "a", encoding="utf-8") as _f:
                _f.write("\n".join(out_lines) + "\n")
        except Exception as _e:
            log.warning(f"  反着买正式推荐追加保存失败: {_e}")

    return len(_fade_manual_recs)


# 2026-08-27新增：让球盘客队+方向联赛级市场edge。见_generate_league_ah_edge()。
# 联赛名用本系统unified_matches.league_name的实际写法(跟fd_matches历史回测库
# 命名不是一回事——回测时用的是fd_matches自己的裸联赛名Serie B/Championship，
# 已用country字段核实分别对应意大利/英格兰，不是同名的巴西甲乙级联赛/
# 苏格兰锦标赛等假阳性)。
# model_prob是回测算出的"买客队+让球"在主胜赔率2.1-2.5这个子区间的胜率
# (decided-only，push不计入分母)，来源 _test_ah_plus_side_0827.py。
#
# 2026-08-27复核修正：用户追问"是否只有4个联赛能用"后，做了一次不预设候选、
# 覆盖全部225个(联赛,赔率区间)组合的独立扫描(而不是只在原13个组合里挑)，
# Bonferroni校正阈值随测试量变严(|z|>=3.69，比原13组合的2.89更严)。结果：
#   意乙(Italy Serie B，不是意甲) n=661/290(两种命名合计) EV+14.8%~+20.7% z=4.01/3.76 ✅稳健存活
#   英冠(Championship) z=3.05，过不了这次更严的3.69门槛，但比另外两个候选证据强，
#          用户明确决定保留(2026-08-27)
#   比甲(First Division A/Jupiler) z=2.96，同样过不了3.69，用户决定删除
#   英甲(League One) z=1.98，本来就没过原13组合的Bonferroni线，用户决定删除
# 全联赛扫描新发现的其余6个显著组合全部是负向(别买信号)，且都落在1.5-1.8/
# 3.0-4.0区间，不在本规则2.1-2.5的触发范围内，不影响这里的候选池。
_LEAGUE_AH_EDGE_CONFIG = {
    "Italy - Serie B":        0.6055,
    "Serie B - Italy":        0.6055,
    "England - Championship": 0.5574,
}


def _generate_league_ah_edge(fetch_date: str) -> int:
    """让球盘客队+方向联赛级市场edge——2026-08-27用户提议+回测验证新增。

    背景：优先级2系统扫描244个(联赛,主胜赔率区间)组合，发现13个组合主队在
    主胜赔率1.5-2.5区间被显著高估(Bonferroni校正+前后半段时间切分双重验证)。
    用户提议"换成买让球盘客队+方向"——回测验证发现只在主胜赔率**2.1-2.5**这个
    子区间成立(1.5-1.8/2.5-3.0两个区间该策略实测显著为负，不适用，已排除)。
    最终只保留意乙(Serie B)+英冠这2个联赛(比甲/英甲证据强度不够，用户2026-08-27
    复核后决定删除)，见上方_LEAGUE_AH_EDGE_CONFIG注释的完整统计依据。

    这不是p_fusion模型信号，是纯市场结构性错价规律，跟fade_manual一样走人工
    批准通道，不经过_moneyline_validation_status()/_in_scope()等算法验证门槛，
    直接写入league_ah_edge_recs候选表，由_generate_and_display_league_ah_edge()
    转正进hit_recommendations(formula_version='league_ah_edge')。
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    _leagues = tuple(_LEAGUE_AH_EDGE_CONFIG.keys())
    with engine.connect() as conn:
        matches = conn.execute(text(f"""
            SELECT unified_id, sport_code, league_name, home_team_std, away_team_std, kickoff_utc
            FROM unified_matches
            WHERE fetch_date = :fd
              AND league_name IN ({','.join(':lg' + str(i) for i in range(len(_leagues)))})
              AND status IN ('NS','Selling','EndOfSale','pending','scheduled','pre')
              AND kickoff_utc > :now_utc
              -- 排除预订球/角球等衍生盘"假比赛"行(如"Southampton (Bookings) vs
              -- Stoke City (Bookings)"，本身是card/corner总数market被上游写成
              -- 独立unified_matches行，不是真实比赛，直接下场会误配到不相关的
              -- 让球盘价格)
              AND home_team_std NOT LIKE '%(Bookings)%'
              AND home_team_std NOT LIKE '%(Corners)%'
              AND away_team_std NOT LIKE '%(Bookings)%'
              AND away_team_std NOT LIKE '%(Corners)%'
        """), {"fd": fetch_date, "now_utc": now_utc,
               **{f"lg{i}": lg for i, lg in enumerate(_leagues)}}).fetchall()

    if not matches:
        log.info("  📐 联赛让球盘客队+方向市场edge: 今日无候选联赛比赛")
        return 0

    n_written = 0
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM league_ah_edge_recs WHERE fetch_date=:fd"), {"fd": fetch_date})
        for uid, sport, league, home, away, kickoff in matches:
            row_ml = conn.execute(text("""
                SELECT consensus_odds FROM consensus_odds
                WHERE unified_id=:uid AND market='moneyline' AND outcome='home' AND fetch_date=:fd
            """), {"uid": uid, "fd": fetch_date}).fetchone()
            if not row_ml or row_ml[0] is None or not (2.1 <= row_ml[0] <= 2.5):
                continue
            row_sp = conn.execute(text("""
                SELECT consensus_odds, handicap FROM consensus_odds
                WHERE unified_id=:uid AND market='spread' AND outcome='away' AND fetch_date=:fd
                  AND handicap IS NOT NULL
            """), {"uid": uid, "fd": fetch_date}).fetchone()
            if not row_sp or row_sp[0] is None:
                continue
            away_odds, handicap = row_sp
            if away_odds <= 1.0:
                continue
            mp = _LEAGUE_AH_EDGE_CONFIG.get(league)
            if mp is None:
                continue
            implied = round(1.0 / away_odds, 4)
            kf = round(max(0.0, (mp * away_odds - 1) / (away_odds - 1)) * 0.25, 4)
            hs = compute_hit_score_v2(mp, implied, kf, 2)
            conn.execute(text("""
                INSERT OR IGNORE INTO league_ah_edge_recs
                (unified_id, sport_code, league_name, home_team, away_team, kickoff_utc,
                 market, outcome, handicap, best_odds, model_prob, kelly_fraction, hit_score,
                 status, fetch_date, created_at)
                VALUES
                (:unified_id, :sport_code, :league_name, :home_team, :away_team, :kickoff_utc,
                 'spread', 'away', :handicap, :best_odds, :model_prob, :kelly_fraction, :hit_score,
                 'pending', :fetch_date, :now)
            """), {"unified_id": uid, "sport_code": sport, "league_name": league,
                    "home_team": home, "away_team": away, "kickoff_utc": kickoff,
                    "handicap": handicap, "best_odds": away_odds,
                    "model_prob": mp, "kelly_fraction": kf, "hit_score": hs,
                    "fetch_date": fetch_date, "now": now_str})
            n_written += 1
    log.info(f"  📐 联赛让球盘客队+方向市场edge: {n_written} 条 → league_ah_edge_recs")
    return n_written


def _generate_and_display_league_ah_edge(fetch_date: str, desk_file: str | None) -> int:
    """把league_ah_edge_recs当天候选转正进hit_recommendations(formula_version=
    'league_ah_edge')，打印+追加保存详细说明，模式仿照_generate_and_display_
    fade_manual()，但这条不是"反着买模型原判"，是直接的市场结构性错价规律，
    没有"原始模型方向"可对比，说明文案相应简化。"""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT unified_id, sport_code, league_name, home_team, away_team, kickoff_utc,
                   market, outcome, handicap, best_odds, model_prob, kelly_fraction, hit_score
            FROM league_ah_edge_recs WHERE fetch_date=:fd
        """), {"fd": fetch_date}).fetchall()

    if not rows:
        return 0

    def _league_zh_local(name: str, sport: str = "") -> str:
        for keyword, zh in _LEAGUE_ZH:
            if keyword.lower() in name.lower():
                return zh
        return name

    from team_zh import team_zh as _team_zh_local

    _recs = []
    for (uid, sport, league, home, away, kickoff, market, outcome, hc, odds, mp, kf, hs) in rows:
        _recs.append({
            "unified_id": uid, "sport_code": sport, "league_name": league,
            "home_team": home, "away_team": away, "kickoff_utc": kickoff,
            "market": market, "outcome": outcome, "handicap": hc,
            "best_odds": odds, "best_source": "league_ah_edge",
            "model_prob": mp, "implied_prob": round(1.0/odds, 4) if odds else None,
            "value_edge": None, "kelly_fraction": kf,
            "hit_score": hs, "hit_score_v2": hs,
            "confidence": "人工批准(联赛市场edge)",
            "reason": f"让球盘客队+方向联赛级市场edge——主胜赔率2.1-2.5区间{league}"
                      f"买客队+让球历史决胜局胜率{mp:.1%}，回测n=326~1543不等，"
                      f"Bonferroni多重比较校正+前后半段时间切分双重验证(详见"
                      f"_LEAGUE_AH_EDGE_CONFIG注释)，不是p_fusion模型信号，"
                      f"人工批准转正，非算法验证",
            "fetch_date": fetch_date, "predicted_score": "-",
        })

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with engine.begin() as conn:
        _skip_ah = _safe_delete_hit_recs(conn, fetch_date, "formula_version='league_ah_edge'", len(_recs), "league_ah_edge")
        for rec in _recs:
            if (rec["unified_id"], rec["market"], rec["outcome"]) in _skip_ah:
                log.info(f"  🛡 FIX-016-3防护: league_ah_edge {rec['home_team']} vs {rec['away_team']} "
                         f"{rec['market']}/{rec['outcome']} 已有已结算行，跳过重插（防重复计账）")
                continue
            conn.execute(text("""
                INSERT INTO hit_recommendations
                (unified_id,sport_code,league_name,home_team,away_team,kickoff_utc,
                 market,outcome,best_odds,best_source,model_prob,implied_prob,
                 value_edge,kelly_fraction,hit_score,hit_score_v2,confidence,reason,
                 status,fetch_date,created_at,handicap,formula_version)
                VALUES
                (:unified_id,:sport_code,:league_name,:home_team,:away_team,:kickoff_utc,
                 :market,:outcome,:best_odds,:best_source,:model_prob,:implied_prob,
                 :value_edge,:kelly_fraction,:hit_score,:hit_score_v2,:confidence,:reason,
                 'pending',:fetch_date,:now,:handicap,'league_ah_edge')
            """), {**rec, "now": now})
    log.info(f"  ✅ 联赛让球盘客队+方向edge人工批准转正: {len(_recs)} 条 → hit_recommendations(formula_version='league_ah_edge')")

    _FW = 143
    out_lines: list[str] = []
    out_lines.append("")
    out_lines.append("=" * _FW)
    out_lines.append("  📋 联赛让球盘客队+方向市场edge（追加，formula_version=league_ah_edge，人工批准非算法验证）")
    out_lines.append("=" * _FW)
    out_lines.append(f"  {'开赛时间':<12} {'联赛':<14} {'主队':<14}{'客队':<14} {'市场':<6} {'方向':<10} {'赔率':<6} {'p融合':<7} {'K₁/₄':<7} {'命中分':<8}")
    out_lines.append("-" * _FW)
    for _r in _recs:
        _t = _r.get("kickoff_utc") or ""
        try:
            _dt = datetime.fromisoformat(_t.replace("Z", "+00:00"))
            if _dt.tzinfo is None:
                _dt = _dt.replace(tzinfo=timezone.utc)
            _t_disp = _dt.astimezone(timezone(timedelta(hours=8))).strftime("%m月%d日%H:%M")
        except Exception:
            _t_disp = "--月--日--:--"
        _mkt_zh = _MARKET_ZH.get(_r["market"], _r["market"])
        _out_zh = _OUTCOME_ZH.get(_r["outcome"], _r["outcome"])
        if _r.get("handicap") is not None:
            _out_zh = f"{_out_zh}{_r['handicap']}"
        out_lines.append(f"  {_t_disp:<14}{_league_zh_local(_r['league_name'], _r.get('sport_code','')):<16}"
                         f"[主]{_team_zh_local(_r['home_team'])[:12]:<12}[客]{_team_zh_local(_r['away_team'])[:12]:<12} "
                         f"{_mkt_zh:<6} {_out_zh:<10} {_r['best_odds']:<6.2f} {_r['model_prob']:<7.3f} "
                         f"{_r['kelly_fraction']:<7.4f} {_r['hit_score']:<8.3f}")
    out_lines.append("=" * _FW)
    out_lines.append(f"  共 {len(_recs)} 条（人工批准转正，纯市场结构性错价规律，非p_fusion模型信号）")
    out_lines.append("=" * _FW)

    for ln in out_lines:
        print(ln)
    if desk_file:
        try:
            with open(desk_file, "a", encoding="utf-8") as _f:
                _f.write("\n".join(out_lines) + "\n")
        except Exception as _e:
            log.warning(f"  联赛让球盘客队+方向edge追加保存失败: {_e}")

    return len(_recs)


def _generate_legacy_team_total_under(fetch_date: str) -> int:
    """足球球队大小/小球"07-17规则"平行线，2026-08-01新增，用户要求。

    背景(排查过程，2026-08-01)：team_total/under在MARKET_BIAS_FOOTBALL里从来
    没配过静态系数(取默认bias=0.0，本该被hit_score*=0过滤掉)，它历史上能进
    正式推荐单，靠的是compute_hit_score()里一段动态覆盖逻辑——只要
    _under_validation_status('football')(整体足球小球/total-under市场，不是
    team_total专属)当时判定为已转正，team_total/under的bias就会被动态拉到
    1.00放行。查证过2026-07-17那天配置(git show faa6d4e:config.py)，
    MARKET_BIAS_FOOTBALL同样没有team_total/under的静态项，说明07-17那57条
    真实推荐单也是靠这条动态覆盖放行的，当时"整体小球市场"必然是validated=True。
    截至2026-08-01用同一函数现查，"整体小球市场"已经变成validated=False
    (ROI-12.89%，n=1008，显著为负)——如果用今天的真实动态状态去复刻，这条线
    会持续0产出，不是我们想要的。

    因此本函数**不查today的_under_validation_status()**，而是直接固定假设
    "07-17规则成立"(小球市场视为已转正，等效bias=1.00恒定)，这也是
    team_total_shadow_full表本身的口径——该表收集候选时hit_score用
    compute_hit_score(..., ignore_bias=True)算，天然跳过bias乘法这一步，
    效果上等价于恒定bias=1.00。所以本函数直接读team_total_shadow_full、
    不用再额外套用bias逻辑，这个"07-17规则视为已转正"的假设已经隐含在
    数据源里了，需要在结果展示/文档层面显式标注清楚(不是"验证过的真实转正"，
    是"假设07-17那天的转正状态一直成立"这个反事实假设)。

    跟当前(07-19+)正式推荐单的_in_scope()逻辑完全独立、互不影响，两条线
    各自产出各自的表，不共用。

    老规则复刻：hit_score >= HIT_SCORE_GLOBAL_THRESHOLD，每场(unified_id)最多
    1条(保留hit_score最高的那条)，不设每日总量上限(这条线只服务单一市场，
    07-19之前的MAX_DAILY_RECOMMENDATIONS=20是全市场共享的每日上限，套用在
    单一窄市场上没有意义，改为全量收集以尽快积累可用于显著性检验的样本)。"""
    try:
        with engine.connect() as conn:
            _sp1, _sp2 = _sport_code_aliases("football")
            rows = conn.execute(text("""
                SELECT unified_id, sport_code, league_name, home_team, away_team, kickoff_utc,
                       market, outcome, handicap, best_odds, model_prob, kelly_fraction, hit_score
                FROM team_total_shadow_full
                WHERE outcome='under' AND sport_code IN (:sp1, :sp2) AND fetch_date=:fd
                  AND hit_score >= :thr
                ORDER BY hit_score DESC
            """), {"sp1": _sp1, "sp2": _sp2, "fd": fetch_date, "thr": HIT_SCORE_GLOBAL_THRESHOLD}).fetchall()
    except Exception as e:
        log.warning(f"  老逻辑平行线(足球球队大小/小球)读取候选异常: {e}")
        return 0

    seen_uid = set()
    picks = []
    for r in rows:
        uid = r[0]
        if uid in seen_uid:
            continue  # 每场最多1条，保留hit_score最高的(已按hit_score DESC排序)
        seen_uid.add(uid)
        picks.append(r)

    if not picks:
        log.info("  🕰 老逻辑平行线(足球球队大小/小球): 今日无候选达标")
        return 0

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with engine.begin() as conn:
        # Bug修复(2026-08-02)：之前只有INSERT OR IGNORE没有DELETE，pipeline当天
        # 每重跑一次(--no-scrape反复验证/重试是这个项目的常规操作)，上一轮不再
        # 是候选的旧记录永远留在表里清不掉，新旧数据混在一起——跟under_shadow_bets/
        # over_shadow_bets等其他所有同类表的写法不一致，是本函数独有的疏漏。
        conn.execute(text("DELETE FROM legacy_team_total_under_recs WHERE fetch_date=:fd"), {"fd": fetch_date})
        for r in picks:
            (uid, sport, league, home, away, kickoff, market, outcome, hc, odds, mp, kf, hs) = r
            conn.execute(text("""
                INSERT OR IGNORE INTO legacy_team_total_under_recs
                (unified_id, sport_code, league_name, home_team, away_team, kickoff_utc,
                 market, outcome, handicap, best_odds, model_prob, kelly_fraction, hit_score,
                 status, fetch_date, created_at)
                VALUES
                (:unified_id, :sport_code, :league_name, :home_team, :away_team, :kickoff_utc,
                 :market, :outcome, :handicap, :best_odds, :model_prob, :kelly_fraction, :hit_score,
                 'pending', :fetch_date, :now)
            """), {"unified_id": uid, "sport_code": sport, "league_name": league,
                    "home_team": home, "away_team": away, "kickoff_utc": kickoff,
                    "market": market, "outcome": outcome, "handicap": hc,
                    "best_odds": odds, "model_prob": mp, "kelly_fraction": kf, "hit_score": hs,
                    "fetch_date": fetch_date, "now": now})
    log.info(f"  🕰 老逻辑平行线(足球球队大小/小球): {len(picks)} 条 → legacy_team_total_under_recs")
    return len(picks)


def _fade_opposite_odds(market: str, opp_outcome: str, handicap, unified_id: str, fetch_date: str):
    """查consensus_odds里对面方向的真实赔率，Top7截断反着买转正函数共用。
    先按精确handicap匹配，查不到再退化成不限定handicap(见spread市场handicap
    符号不统一的教训，00_命中系统.py同类查询一律用这个兜底顺序)。"""
    try:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT consensus_odds FROM consensus_odds
                WHERE unified_id=:uid AND market=:mk AND outcome=:oc AND fetch_date=:fd AND handicap=:hc
                ORDER BY id DESC LIMIT 1
            """), {"uid": unified_id, "mk": market, "oc": opp_outcome, "fd": fetch_date, "hc": handicap}).fetchone()
            if not row:
                row = conn.execute(text("""
                    SELECT consensus_odds FROM consensus_odds
                    WHERE unified_id=:uid AND market=:mk AND outcome=:oc AND fetch_date=:fd
                    ORDER BY id DESC LIMIT 1
                """), {"uid": unified_id, "mk": market, "oc": opp_outcome, "fd": fetch_date}).fetchone()
    except Exception:
        return None
    return row[0] if row and row[0] else None


def _generate_basketball_under_fade(fetch_date: str) -> int:
    """篮球小球"反着买"转正平行线，2026-08-01新增，用户要求。见建表注释
    (basketball_under_fade_recs)说明背景/证据强度/局限。

    数据源：under_shadow_bets(sport_code='basketball')里当天全部小球候选，按
    hit_score降序取前7条(Top7截断，跟这次会话的分析口径一致)，每条查对面方向
    (大球/over)的真实consensus_odds，能查到才写入——写入的是翻转后的最终下注
    方向(market='total', outcome='over')，不是原始小球候选，后续按标准
    total/over规则结算，不需要额外的fade结算逻辑。"""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT unified_id, sport_code, league_name, home_team, away_team, kickoff_utc,
                       market, handicap, model_prob, kelly_fraction, hit_score
                FROM under_shadow_bets
                WHERE sport_code='basketball' AND fetch_date=:fd AND hit_score IS NOT NULL
                ORDER BY hit_score DESC
            """), {"fd": fetch_date}).fetchall()
    except Exception as e:
        log.warning(f"  篮球小球反着买平行线读取候选异常: {e}")
        return 0

    top7 = rows[:7]
    if not top7:
        log.info("  🔄 篮球小球反着买平行线: 今日无候选")
        return 0

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    n_written = 0
    with engine.begin() as conn:
        # Bug修复(2026-08-02)：同legacy_team_total_under_recs同一处疏漏，重跑不清旧数据
        conn.execute(text("DELETE FROM basketball_under_fade_recs WHERE fetch_date=:fd"), {"fd": fetch_date})
        for (uid, sport, league, home, away, kickoff, market, hc, mp, kf, hs) in top7:
            opp_odds = _fade_opposite_odds(market, "over", hc, uid, fetch_date)
            if not opp_odds:
                continue
            conn.execute(text("""
                INSERT OR IGNORE INTO basketball_under_fade_recs
                (unified_id, sport_code, league_name, home_team, away_team, kickoff_utc,
                 market, outcome, handicap, best_odds, model_prob, kelly_fraction, hit_score,
                 status, fetch_date, created_at)
                VALUES
                (:unified_id, :sport_code, :league_name, :home_team, :away_team, :kickoff_utc,
                 :market, 'over', :handicap, :best_odds, :model_prob, :kelly_fraction, :hit_score,
                 'pending', :fetch_date, :now)
            """), {"unified_id": uid, "sport_code": sport, "league_name": league,
                    "home_team": home, "away_team": away, "kickoff_utc": kickoff,
                    "market": market, "handicap": hc, "best_odds": opp_odds,
                    "model_prob": mp, "kelly_fraction": kf, "hit_score": hs,
                    "fetch_date": fetch_date, "now": now})
            n_written += 1
    log.info(f"  🔄 篮球小球反着买平行线: {n_written} 条(候选{len(top7)}条,{len(top7)-n_written}条查不到对面赔率) → basketball_under_fade_recs")
    return n_written


def _generate_basketball_moneyline_fade(fetch_date: str) -> int:
    """篮球独赢(旧口径)"反着买"转正平行线，2026-08-01新增，用户要求。见建表注释
    (basketball_moneyline_fade_recs)说明背景/证据强度/局限——比篮球小球反着买
    少一次独立测量，证据更薄弱。

    数据源：shadow_recommendations(shadow_type='moneyline', sport_code='basketball')
    里当天全部独赢候选，按hit_score降序取前7条，每条翻转成对面方向(home<->away)，
    查对面方向真实consensus_odds，能查到才写入——写入的是翻转后的最终下注方向，
    后续按标准moneyline规则结算。

    赔率下限过滤(2026-08-03新增，见BASKETBALL_MONEYLINE_FADE_MIN_ODDS说明)：翻转后
    赔率低于该阈值的候选直接跳过，不写入——这类候选的赔率区间从未被历史回测样本
    覆盖过，套用整体ROI结论属于外推，且低赔本身也没有投注意义。"""
    OPPOSITE = {"home": "away", "away": "home"}
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT unified_id, sport_code, league_name, home_team, away_team, kickoff_utc,
                       market, outcome, handicap, model_prob, kelly_fraction, hit_score
                FROM shadow_recommendations
                WHERE shadow_type='moneyline' AND sport_code='basketball' AND fetch_date=:fd
                  AND hit_score IS NOT NULL
                ORDER BY hit_score DESC
            """), {"fd": fetch_date}).fetchall()
    except Exception as e:
        log.warning(f"  篮球独赢反着买平行线读取候选异常: {e}")
        return 0

    top7 = rows[:7]
    if not top7:
        log.info("  🔄 篮球独赢反着买平行线: 今日无候选")
        return 0

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    n_written = 0
    with engine.begin() as conn:
        # Bug修复(2026-08-02)：同上两个函数同一处疏漏，重跑不清旧数据——今天实测
        # 已经被这个bug污染过一次(basketball_moneyline_fade_recs攒了5条，其中4条是
        # 早几轮round6留下的过期候选，真正当次有效候选只有1条)，用户复核时发现
        # 全部outcome='away'看着反常才顺藤摸瓜查出这个根因。
        conn.execute(text("DELETE FROM basketball_moneyline_fade_recs WHERE fetch_date=:fd"), {"fd": fetch_date})
        for (uid, sport, league, home, away, kickoff, market, outcome, hc, mp, kf, hs) in top7:
            opp = OPPOSITE.get(outcome)
            if not opp:
                continue
            opp_odds = _fade_opposite_odds(market, opp, hc, uid, fetch_date)
            if not opp_odds:
                continue
            if opp_odds < BASKETBALL_MONEYLINE_FADE_MIN_ODDS:
                continue
            conn.execute(text("""
                INSERT OR IGNORE INTO basketball_moneyline_fade_recs
                (unified_id, sport_code, league_name, home_team, away_team, kickoff_utc,
                 market, outcome, handicap, best_odds, model_prob, kelly_fraction, hit_score,
                 status, fetch_date, created_at)
                VALUES
                (:unified_id, :sport_code, :league_name, :home_team, :away_team, :kickoff_utc,
                 :market, :outcome, :handicap, :best_odds, :model_prob, :kelly_fraction, :hit_score,
                 'pending', :fetch_date, :now)
            """), {"unified_id": uid, "sport_code": sport, "league_name": league,
                    "home_team": home, "away_team": away, "kickoff_utc": kickoff,
                    "market": market, "outcome": opp, "handicap": hc, "best_odds": opp_odds,
                    "model_prob": mp, "kelly_fraction": kf, "hit_score": hs,
                    "fetch_date": fetch_date, "now": now})
            n_written += 1
    log.info(f"  🔄 篮球独赢反着买平行线: {n_written} 条(候选{len(top7)}条) → basketball_moneyline_fade_recs")
    return n_written


_LSTM_VALIDATION_CACHE: dict = {}  # sport_code -> status dict


def _lstm_validation_status(sport_code: str) -> dict:
    """查 shadow_recommendations 里已结算的 lstm_moneyline/lstm_1x2 影子记录，判断
    LSTM(EMA+AR1)信号+现有model_prob按0.85/0.15融合后的样本量/ROI是否达标可以转正
    并入 get_model_probs() 的 p_fusion。按 shadow_type（不是 market）过滤，因为这两个
    桶写入时 market 字段固定存 'moneyline'，跟原始独赢影子桶用同一个 market 值，
    只有 shadow_type 能区分开，避免把两套桶的结算样本混在一起算。"""
    if sport_code in _LSTM_VALIDATION_CACHE:
        return _LSTM_VALIDATION_CACHE[sport_code]
    try:
        with engine.connect() as conn:
            _sp1, _sp2 = _sport_code_aliases(sport_code)
            rows = conn.execute(text("""
                SELECT status, best_odds, fetch_date FROM shadow_recommendations
                WHERE shadow_type IN ('lstm_moneyline','lstm_1x2')
                  AND status IN ('win','lose') AND sport_code IN (:sp1, :sp2)
            """), {"sp1": _sp1, "sp2": _sp2}).fetchall()
    except Exception:
        rows = []
    result = _validation_result(rows, LSTM_VALIDATION_MIN_SAMPLES, LSTM_VALIDATION_MIN_ROI,
                                gate_key=f"lstm_moneyline:{sport_code}")
    _LSTM_VALIDATION_CACHE[sport_code] = result
    return result


_LSTM_SPREAD_VALIDATION_CACHE: dict = {}  # sport_code -> status dict


def _lstm_spread_validation_status(sport_code: str) -> dict:
    """跟 _lstm_validation_status() 同一套逻辑，查 shadow_type='lstm_spread'
    （让球LSTM blend桶，用margin~Normal校准算覆盖概率，见_lstm_spread_cover_prob()），
    同样复用 LSTM_VALIDATION_MIN_SAMPLES/ROI。2026-08-24新增——此前这个shadow桶
    只用来展示"⏳尚未转正"提示，从没真正接回model_probs给正式推荐单用，见项目
    记忆project_poisson_global_fallback_lead_0824衍生出的让球市场接线修复。"""
    if sport_code in _LSTM_SPREAD_VALIDATION_CACHE:
        return _LSTM_SPREAD_VALIDATION_CACHE[sport_code]
    try:
        with engine.connect() as conn:
            _sp1, _sp2 = _sport_code_aliases(sport_code)
            rows = conn.execute(text("""
                SELECT status, best_odds, fetch_date FROM shadow_recommendations
                WHERE shadow_type = 'lstm_spread'
                  AND status IN ('win','lose') AND sport_code IN (:sp1, :sp2)
            """), {"sp1": _sp1, "sp2": _sp2}).fetchall()
    except Exception:
        rows = []
    result = _validation_result(rows, LSTM_VALIDATION_MIN_SAMPLES, LSTM_VALIDATION_MIN_ROI,
                                gate_key=f"lstm_spread:{sport_code}")
    _LSTM_SPREAD_VALIDATION_CACHE[sport_code] = result
    return result


_INJURY_VALIDATION_CACHE: dict = {}  # sport_code -> status dict


def _injury_validation_status(sport_code: str) -> dict:
    """查 shadow_recommendations 里已结算的 injury_impact 影子记录，判断伤停信号+
    现有model_prob按0.85/0.15融合后的样本量/ROI是否达标可以转正，逻辑同
    _lstm_validation_status()。2026-08-01新增——这是get_injury_impact_probs()
    的转正判断，跟其他所有信号一样必须过_validation_result()的单尾95%置信区间
    +近期窗口双重检验，不能因为"伤病应该有用"这种直觉就绕过验证直接影响正式
    推荐（这正是本次[[feedback_validation_significance_test]]审查要堵住的漏洞）。"""
    if sport_code in _INJURY_VALIDATION_CACHE:
        return _INJURY_VALIDATION_CACHE[sport_code]
    try:
        with engine.connect() as conn:
            _sp1, _sp2 = _sport_code_aliases(sport_code)
            rows = conn.execute(text("""
                SELECT status, best_odds, fetch_date FROM shadow_recommendations
                WHERE shadow_type = 'injury_impact' AND status IN ('win','lose')
                  AND sport_code IN (:sp1, :sp2)
            """), {"sp1": _sp1, "sp2": _sp2}).fetchall()
    except Exception:
        rows = []
    result = _validation_result(rows, LSTM_VALIDATION_MIN_SAMPLES, LSTM_VALIDATION_MIN_ROI,
                                gate_key=f"injury_impact:{sport_code}")
    _INJURY_VALIDATION_CACHE[sport_code] = result
    return result


_FOTMOB_VALIDATION_CACHE: dict = {}  # 固定只有一个key（足球，FotMob无篮球数据）


def _fotmob_validation_status() -> dict:
    """查 shadow_recommendations 里已结算的 fotmob_1x2 影子记录，判断FotMob信号+
    现有model_prob按0.85/0.15融合后的样本量/ROI是否达标可以转正并入
    get_model_probs() 的 p_fusion，逻辑同 _lstm_validation_status()。FotMob目前
    只有足球数据，不需要像LSTM那样按sport_code分桶。"""
    if "football" in _FOTMOB_VALIDATION_CACHE:
        return _FOTMOB_VALIDATION_CACHE["football"]
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT status, best_odds, fetch_date FROM shadow_recommendations
                WHERE shadow_type = 'fotmob_1x2' AND status IN ('win','lose')
            """)).fetchall()
    except Exception:
        rows = []
    result = _validation_result(rows, FOTMOB_VALIDATION_MIN_SAMPLES, FOTMOB_VALIDATION_MIN_ROI,
                                gate_key="fotmob_1x2")
    _FOTMOB_VALIDATION_CACHE["football"] = result
    return result


_FOTMOB_TOTALS_VALIDATION_CACHE: dict = {}
_FOTMOB_TEAM_TOTAL_VALIDATION_CACHE: dict = {}


def _fotmob_totals_validation_status(outcome: str | None = None) -> dict:
    """跟 _fotmob_validation_status() 同一套逻辑，查 shadow_type='fotmob_totals'（整场
    大小球FotMob blend桶，2026-07-21新增），复用同一组 FOTMOB_VALIDATION_MIN_SAMPLES/ROI
    门槛（同一数据源，不另开一套阈值）。

    2026-09-06按outcome拆分(over/under)——此前over+under合并统计，实测under单独
    n=116/ROI+14.0%/ci_lower=-0.48%（几乎压线），被over单独-12.0%拖累后合并数字
    只有+4.8%，完全掩盖了under已经非常接近转正这件事，跟lstm_spread被WNBA拖累
    是同一类问题（见项目记忆）。FotMob目前只有足球数据，不需要像lstm_spread那样
    再按sport_code拆——只拆outcome。不传outcome时保留原有合并口径(向后兼容)。"""
    _ck = outcome or "football"
    if _ck in _FOTMOB_TOTALS_VALIDATION_CACHE:
        return _FOTMOB_TOTALS_VALIDATION_CACHE[_ck]
    try:
        with engine.connect() as conn:
            if outcome:
                rows = conn.execute(text("""
                    SELECT status, best_odds, fetch_date FROM shadow_recommendations
                    WHERE shadow_type = 'fotmob_totals' AND status IN ('win','lose') AND outcome=:oc
                """), {"oc": outcome}).fetchall()
            else:
                rows = conn.execute(text("""
                    SELECT status, best_odds, fetch_date FROM shadow_recommendations
                    WHERE shadow_type = 'fotmob_totals' AND status IN ('win','lose')
                """)).fetchall()
    except Exception:
        rows = []
    result = _validation_result(rows, FOTMOB_VALIDATION_MIN_SAMPLES, FOTMOB_VALIDATION_MIN_ROI,
                                gate_key=f"fotmob_totals:{outcome or 'all'}")
    _FOTMOB_TOTALS_VALIDATION_CACHE[_ck] = result
    return result


def _fotmob_team_total_validation_status(outcome: str | None = None) -> dict:
    """跟 _fotmob_validation_status() 同一套逻辑，查 shadow_type='fotmob_team_total'
    （球队大小FotMob blend桶，2026-07-21新增），同样复用 FOTMOB_VALIDATION_MIN_SAMPLES/ROI。

    2026-09-06按outcome拆分(over/under)，跟_fotmob_totals_validation_status()同一次
    审查加的——under单独n=97/ROI+12.0%/ci_lower=-5.06%/近30注ROI+13.5%，是全站
    第三接近转正的信号(仅次于已跨线的lstm_spread足球和fotmob_totals/under)，且
    近期窗口是正的，趋势比fotmob_totals/under更健康。不传outcome时保留合并口径。"""
    _ck = outcome or "football"
    if _ck in _FOTMOB_TEAM_TOTAL_VALIDATION_CACHE:
        return _FOTMOB_TEAM_TOTAL_VALIDATION_CACHE[_ck]
    try:
        with engine.connect() as conn:
            if outcome:
                rows = conn.execute(text("""
                    SELECT status, best_odds, fetch_date FROM shadow_recommendations
                    WHERE shadow_type = 'fotmob_team_total' AND status IN ('win','lose') AND outcome=:oc
                """), {"oc": outcome}).fetchall()
            else:
                rows = conn.execute(text("""
                    SELECT status, best_odds, fetch_date FROM shadow_recommendations
                    WHERE shadow_type = 'fotmob_team_total' AND status IN ('win','lose')
                """)).fetchall()
    except Exception:
        rows = []
    result = _validation_result(rows, FOTMOB_VALIDATION_MIN_SAMPLES, FOTMOB_VALIDATION_MIN_ROI,
                                gate_key=f"fotmob_team_total:{outcome or 'all'}")
    _FOTMOB_TEAM_TOTAL_VALIDATION_CACHE[_ck] = result
    return result


_FOTMOB_SPREAD_VALIDATION_CACHE: dict = {}
_FOTMOB_CORNER_VALIDATION_CACHE: dict = {}


def _fotmob_spread_validation_status(outcome: str | None = None) -> dict:
    """跟 _fotmob_validation_status() 同一套逻辑，查 shadow_type='fotmob_spread'
    （让球FotMob blend桶，2026-07-21新增），同样复用 FOTMOB_VALIDATION_MIN_SAMPLES/ROI。

    2026-09-06按outcome拆分(home/away)，同一次审查加的——away单独n=23/ROI+28.6%/
    ci_lower=-10.3%看着不错但样本太小，home单独n=95/ROI+0.45%/ci_lower=-16.1%，
    两个都还没接近转正，拆分主要是为了跟其他FotMob桶保持一致的展示粒度，避免
    未来其中一侧样本积累起来后又被合并统计掩盖。不传outcome时保留合并口径。"""
    _ck = outcome or "football"
    if _ck in _FOTMOB_SPREAD_VALIDATION_CACHE:
        return _FOTMOB_SPREAD_VALIDATION_CACHE[_ck]
    try:
        with engine.connect() as conn:
            if outcome:
                rows = conn.execute(text("""
                    SELECT status, best_odds, fetch_date FROM shadow_recommendations
                    WHERE shadow_type = 'fotmob_spread' AND status IN ('win','lose') AND outcome=:oc
                """), {"oc": outcome}).fetchall()
            else:
                rows = conn.execute(text("""
                    SELECT status, best_odds, fetch_date FROM shadow_recommendations
                    WHERE shadow_type = 'fotmob_spread' AND status IN ('win','lose')
                """)).fetchall()
    except Exception:
        rows = []
    result = _validation_result(rows, FOTMOB_VALIDATION_MIN_SAMPLES, FOTMOB_VALIDATION_MIN_ROI,
                                gate_key=f"fotmob_spread:{outcome or 'all'}")
    _FOTMOB_SPREAD_VALIDATION_CACHE[_ck] = result
    return result


def _fotmob_corner_validation_status(outcome: str | None = None) -> dict:
    """跟 _fotmob_validation_status() 同一套逻辑，查 shadow_type='fotmob_corner'
    （角球FotMob blend桶，2026-07-21新增），同样复用 FOTMOB_VALIDATION_MIN_SAMPLES/ROI。

    2026-09-06按outcome拆分(corner_over/corner_under)，同一次审查加的——corner_over
    单独n=35/ROI+14.1%/ci_lower=-12.2%，corner_under单独n=53/ROI-5.2%/ci_lower=-26.5%，
    两个都还没接近转正，拆分主要是为了统一展示粒度，避免未来样本积累后被合并统计
    掩盖。不传outcome时保留合并口径。"""
    _ck = outcome or "football"
    if _ck in _FOTMOB_CORNER_VALIDATION_CACHE:
        return _FOTMOB_CORNER_VALIDATION_CACHE[_ck]
    try:
        with engine.connect() as conn:
            if outcome:
                rows = conn.execute(text("""
                    SELECT status, best_odds, fetch_date FROM shadow_recommendations
                    WHERE shadow_type = 'fotmob_corner' AND status IN ('win','lose') AND outcome=:oc
                """), {"oc": outcome}).fetchall()
            else:
                rows = conn.execute(text("""
                    SELECT status, best_odds, fetch_date FROM shadow_recommendations
                    WHERE shadow_type = 'fotmob_corner' AND status IN ('win','lose')
                """)).fetchall()
    except Exception:
        rows = []
    result = _validation_result(rows, FOTMOB_VALIDATION_MIN_SAMPLES, FOTMOB_VALIDATION_MIN_ROI,
                                gate_key=f"fotmob_corner:{outcome or 'all'}")
    _FOTMOB_CORNER_VALIDATION_CACHE[_ck] = result
    return result


def _get_dc_rho() -> float:
    """读取 predict_football.py 落库的最新 Dixon-Coles rho（跨进程持久化，取不到用默认值）"""
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                "SELECT rho FROM dc_rho_state ORDER BY id DESC LIMIT 1"
            )).fetchone()
        if row and row[0] is not None:
            return float(row[0])
    except Exception:
        pass
    return -0.10


def _generate_correct_score_recs(match_data: dict, fetch_date: str, next_date: str) -> list:
    """遍历已通过Pass1过滤的足球赛事，凡是能拿到真实比分盘口（Pinnacle和/或qiety）的，
    用 Dixon-Coles 修正后的联合概率 vs 真实盘口隐含概率(去水位归一化) 算 edge/Kelly/命中分，
    复用现有 compute_hit_score()。每场比赛只保留命中分最高的一条比分推荐。"""
    from predict_football import _dc_score_grid
    rho = _get_dc_rho()

    football_uids = [uid for uid, d in match_data.items()
                      if (d["row"][1] or "").lower() in ("football", "soccer")]
    if not football_uids:
        return []

    # 批量读取 lambda_home/lambda_away（predict_football.py 已算好写入 football_score_predictions）
    lam_map: dict = {}
    with engine.connect() as conn:
        _rows = conn.execute(text("""
            SELECT unified_id, lambda_home, lambda_away FROM football_score_predictions
            WHERE fetch_date IN (:fd, :nd) AND lambda_home IS NOT NULL AND lambda_away IS NOT NULL
        """), {"fd": fetch_date, "nd": next_date}).fetchall()
    for uid, lh, la in _rows:
        lam_map[uid] = (float(lh), float(la))

    out = []
    for uid in football_uids:
        d = match_data[uid]
        row = d["row"]
        (_, sport, league, home, away, kickoff, src_cnt, sources_json) = row
        lam = lam_map.get(uid)
        if not lam:
            continue
        lam_h, lam_a = lam
        sources = json.loads(sources_json or "{}")

        # ── 汇总真实盘口（Pinnacle + qiety，能拿到几个算几个）──
        # 注意：sources["pinnacle"] 来自早已停更的 pinnacle_fixtures 表（旧爬虫已被
        # 15_pinnacle_oddsportal_scraper 取代），不能直接用。真正每日活跃维护的是
        # sources["theodds"]（对应 theodds_fixtures.id），该表的 pinn_id 字段才是
        # 真实的 Pinnacle matchupId，需要先用它反查出 pinn_id 再去 join 比分盘口表。
        cs_odds_by_source: dict = {}  # source -> {"H-A": odds}
        theodds_id = sources.get("theodds")
        pinn_mid = None
        if theodds_id:
            try:
                with engine.connect() as conn:
                    _pid_row = conn.execute(text(
                        "SELECT pinn_id FROM theodds_fixtures WHERE id=:tid"
                    ), {"tid": str(theodds_id)}).fetchone()
                if _pid_row and _pid_row[0]:
                    pinn_mid = _pid_row[0]
            except Exception:
                pass
        if pinn_mid:
            try:
                with engine.connect() as conn:
                    _pr = conn.execute(text("""
                        SELECT correct_score, decimal_odds FROM pinnacle_correct_score_odds
                        WHERE parent_matchup_id=CAST(:mid AS INTEGER) AND fetch_date IN (:fd, :nd)
                    """), {"mid": str(pinn_mid), "fd": fetch_date, "nd": next_date}).fetchall()
                if _pr:
                    cs_odds_by_source["pinnacle"] = {r[0]: float(r[1]) for r in _pr if r[1]}
            except Exception:
                pass
        qiety_mid = sources.get("qiety_yb")
        if qiety_mid:
            try:
                with engine.connect() as conn:
                    _qr = conn.execute(text("""
                        SELECT correct_score, decimal_odds FROM yb_correct_score_odds
                        WHERE match_id=:mid AND fetch_date IN (:fd, :nd)
                    """), {"mid": str(qiety_mid), "fd": fetch_date, "nd": next_date}).fetchall()
                if _qr:
                    cs_odds_by_source["qiety_yb"] = {r[0]: float(r[1]) for r in _qr if r[1]}
            except Exception:
                pass

        if not cs_odds_by_source:
            continue  # 无真实盘口，跳过（不用模型概率兜底）

        # ── 跨源取平均，得到每个比分的共识赔率 ──
        all_scores = set()
        for m in cs_odds_by_source.values():
            all_scores.update(m.keys())
        consensus_cs: dict = {}
        for cs_key in all_scores:
            vals = [m[cs_key] for m in cs_odds_by_source.values() if cs_key in m]
            if vals:
                consensus_cs[cs_key] = sum(vals) / len(vals)
        if not consensus_cs:
            continue

        # ── 去水位归一化：implied_prob 除以该场全部已捕获比分的隐含概率之和 ──
        total_implied = sum(1.0 / o for o in consensus_cs.values() if o > 1.0)
        if total_implied <= 0:
            continue

        grid = _dc_score_grid(lam_h, lam_a, rho=rho)
        n_src = len(cs_odds_by_source)
        league_tier = d["league_tier"]

        match_candidates = []
        for cs_key, cons_odds in consensus_cs.items():
            try:
                hs, as_ = cs_key.split("-")
                hs, as_ = int(hs), int(as_)
            except (ValueError, AttributeError):
                continue
            if hs >= len(grid) or as_ >= len(grid[0]):
                continue
            raw_model_prob = float(grid[hs][as_])
            implied_prob = round((1.0 / cons_odds) / total_implied, 4) if cons_odds > 1.0 else 0.0
            if raw_model_prob <= 0:
                continue
            # 2026-07-16校准修复：raw_model_prob(Dixon-Coles格子概率)复盘111个已结算
            # 样本发现均值9.1%，实际胜率只有4.5%(2.02倍虚高)；implied_prob(赔率去水位)
            # 均值4.9%几乎完美吻合实际胜率(1.08倍)。之前直接拿raw_model_prob去算edge/
            # 凯利仓位，等于系统性地把"模型算错"当成"市场错了"，是ROI持续为负的主因。
            # 现在跟其他市场一样做model×market融合，且明显更偏向已证明校准准的market。
            model_prob = (CORRECT_SCORE_MODEL_WEIGHT * raw_model_prob
                          + (1 - CORRECT_SCORE_MODEL_WEIGHT) * implied_prob)

            per_source_odds = [m[cs_key] for m in cs_odds_by_source.values() if cs_key in m]
            score_data = _compute_correct_score_hit(
                model_prob, cons_odds, implied_prob, per_source_odds, league_tier=league_tier,
            )
            # Bug修复(2026-09-07)：此前在这里对hit_score/kelly_fraction不达标的候选
            # 直接continue丢弃，导致它们连"比分候选观察单"（8161行附近，专门读本函数
            # 未过_in_scope()的原始返回值）都看不到——候选没了，观察单自然是空的。
            # 这跟设计注释("跟其他所有影子观察单转正判断前取数、标注仅观察的设计原则
            # 一致")矛盾：total/over等市场的"策略收窄"是候选先全部生成，门槛判断在
            # 外层做，未达标的还会转存shadow_type='gated'继续可见；比分玩法这里门槛
            # 判断在生成函数内部做，未达标的连"存在过"都不会被记录。改为不在这里过滤，
            # 全部候选原样返回，是否达标只影响下面call site要不要计入真钱推荐单。
            rec = {
                "unified_id": uid, "sport_code": "football", "league_name": league,
                "home_team": home, "away_team": away, "kickoff_utc": kickoff,
                "market": "correct_score", "outcome": cs_key,
                "best_odds": round(cons_odds, 4), "best_source": "+".join(cs_odds_by_source.keys()),
                "model_prob": round(model_prob, 4), "implied_prob": implied_prob,
                "value_edge": score_data["value_edge"], "kelly_fraction": score_data["kelly_fraction"],
                "hit_score": score_data["hit_score"], "hit_score_v2": score_data["hit_score"],
                "confidence": score_data["confidence"], "reason": "Dixon-Coles模型+真实比分盘口",
                "fetch_date": fetch_date, "handicap": None, "predicted_score": cs_key,
                "qualified": (score_data["hit_score"] >= HIT_SCORE_GLOBAL_THRESHOLD
                              and score_data["kelly_fraction"] > 0),
            }
            match_candidates.append(rec)

        # 每场最多出 CORRECT_SCORE_PICKS_PER_MATCH 个：命中分最高的是首选，其余是次选，
        # 不再要求独立过门槛——是否达标(threshold+kelly>0)由"qualified"字段标注，
        # call site据此决定进真钱推荐单还是只进比分候选观察单，凑不够就有几个出几个
        match_candidates.sort(key=lambda r: r["hit_score"], reverse=True)
        for _rank, _rec in enumerate(match_candidates[:CORRECT_SCORE_PICKS_PER_MATCH], 1):
            _rec["pick_rank"] = _rank
            _rec["pick_label"] = "首选" if _rank == 1 else "次选"
            out.append(_rec)

    return out


# ─── 8. 生成投注推荐单 ───────────────────────────────────────────────────────
def generate_recommendations(fetch_date: str, precomputed: bool = False,
                              precomputed_corner_shadow: dict | None = None,
                              precomputed_htft_shadow: dict | None = None,
                              precomputed_htft_nofilter_shadow: dict | None = None,
                              precomputed_corner_recs: list | None = None):
    """
    推荐窗口：当前时刻 → 次日12:00（北京）的未开赛足球/篮球比赛
    precomputed=True 时跳过 build_unified_odds/compute_consensus_odds（run() 已预处理）
    precomputed_htft_shadow: _run_one_date()读market_prediction_snapshot(market_group=
    'HTFT'，predict_football.py写入)算好的半全场影子桶（{dedup_key: entry_dict}），
    跟precomputed_corner_shadow同一个道理——半全场9格联合概率不在本函数遍历的
    unified_odds/consensus_odds范围内，没法在这里现算，由调用方读快照表转换好传入。
    precomputed_htft_nofilter_shadow: 2026-09-01新增，跟precomputed_htft_shadow同一批
    原始候选、同一个函数算出来，唯一区别是不过滤"_HTFT_LEAGUE_WHITELIST"联赛白名单——
    用户要求做两个平行版本每天对比命中率/ROI，验证联赛过滤到底有没有用，见
    shadow_multi["htft_nofilter"]说明。
    precomputed_corner_shadow: _run_one_date()在角球分析阶段算好的fotmob_corner影子桶
    （{dedup_key: entry_dict}），角球盘口(pinnacle_corner_odds)不在本函数遍历的
    unified_odds/consensus_odds范围内，没法在这里现算，只能由调用方提前算好传进来，
    塞进shadow_multi统一走下面的打印/保存/写库逻辑（2026-07-22修复：此前fotmob_corner
    完全靠_run_one_date()自己单独INSERT进shadow_recommendations表，从不进shadow_multi，
    导致它虽然被列在打印/保存的_stype遍历元组里，实际上永远是空的——控制台、保存的
    投注单txt文件都看不到，只能自己去查表）。
    precomputed_corner_recs: _run_one_date()在角球分析阶段调用corner_model.generate_corner_slip()
    算出的角球正式推荐单（corner_recommendations表数据源，跟precomputed_corner_shadow是两码事——
    后者是FotMob影子观察桶，前者是真正进正式投注单的角球候选）。generate_corner_slip()自己会print
    一份控制台格式，但那只是print，从不进本函数的desk_file写入内容，导致2026-07-31发现角球正式
    推荐一直没出现在保存的投注单txt文件里（只在DB corner_recommendations表和控制台日志能看到）。
    这里单独渲染一份文件用的文本块，跟_shadow_txt/_multi_txt同一个套路。
    """
    log.info("\n🎯 生成投注推荐单...")

    # ⚡ 批量预加载 xG/ELO 缓存（把 stage3 的 ~10k 次 DB 查询压缩为纯内存访问）
    preload_xg_caches()
    # 📐 足球1x2平局校准曲线：过期(>30天)自动重新拟合，全程无需人工维护
    _ensure_draw_calibration()

    from datetime import timezone, timedelta
    bj_tz = timezone(timedelta(hours=8))
    base = datetime.strptime(fetch_date, "%Y-%m-%d")

    # 次日12:00 北京 → UTC（推荐上界：今日全部未开赛 + 明日12:00前赛事，不推第三日）
    win_end_bj  = (base + timedelta(days=1)).replace(hour=12, minute=0, second=0, tzinfo=bj_tz)
    win_end_utc = win_end_bj.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    next_date   = (base + timedelta(days=1)).strftime("%Y-%m-%d")
    prev_date   = (base + timedelta(days=-1)).strftime("%Y-%m-%d")  # 回退一天：爬虫可能在前一天跑，打的fetch_date标签是昨天

    # 当前 UTC（推荐下界：只推未开赛）
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    # 查今日 + 次日未开赛的足球/篮球，kickoff 在 (now, 次日23:00北京) 内
    with engine.connect() as conn:
        matches = conn.execute(text("""
            SELECT unified_id, sport_code, league_name, home_team_std, away_team_std,
                   kickoff_utc, source_count, sources_json
            FROM unified_matches
            WHERE (
                fetch_date IN (:fd, :nd, :pd)
                OR (
                    -- 世界杯/重要赛事：忽略 fetch_date，只要时间窗口+数据源符合即可
                    (league_name LIKE '%World Cup%' OR league_name LIKE '%FIFA%'
                     OR league_name LIKE '%Euro%' OR league_name LIKE '%Copa America%')
                    AND (sources_json LIKE '%pinnacle%' OR sources_json LIKE '%theodds%')
                )
            )
              -- Bug修复(2026-08-11)：补上 'pre'。theodds_api 源用的未开赛字面值是
              -- 'pre'，不在原白名单里，这批比赛被静默丢弃（实测库里760行status='pre'、
              -- 有比分的0行、284场开赛时间在未来，语义确认就是未开赛）。跟
              -- football/soccer 双标签是同一类问题：数据源换了字面值、消费端的硬编码
              -- 白名单没跟上，且失败方式是"少了数据"而不是报错，极难察觉。
              AND status IN ('NS','Selling','EndOfSale','pending','scheduled','pre')
              AND kickoff_utc >  :now_utc
              AND kickoff_utc <= :t_end
              AND sport_code IN ('football','Football','soccer','Soccer','basketball','Basketball')
              AND (sources_json LIKE '%qiety_yb%' OR sources_json LIKE '%theodds%' OR sources_json LIKE '%pinnacle%' OR sources_json LIKE '%bet365%')
              AND league_name NOT LIKE '%PANDA%'
              AND league_name NOT LIKE '%VS-%'
              AND league_name NOT LIKE '%NBA 2K%'
              AND league_name NOT LIKE '%EAFC%'
              AND league_name NOT LIKE '%梦幻对垒%'
              AND league_name NOT LIKE '%模拟%'
              AND home_team_std != ''
              AND away_team_std != ''
            ORDER BY
              CASE WHEN league_name LIKE '%World Cup%' OR league_name LIKE '%FIFA%'
                   THEN 0 ELSE 1 END,
              CASE WHEN sources_json LIKE '%theodds%' OR sources_json LIKE '%pinnacle%'
                   THEN 1 ELSE 2 END,
              source_count DESC, kickoff_utc
        """), {"fd": fetch_date, "nd": next_date, "pd": prev_date,
               "now_utc": now_utc, "t_end": win_end_utc}).fetchall()

    log.info(f"  投注窗口：当前 → {next_date} 12:00（北京），足球+篮球，符合: {len(matches)} 场")

    recommendations = []
    recommendations_v2 = []   # V2公式并行推荐列表（价值边际驱动）
    shadow_candidates = []  # 小球影子候选（bypass MARKET_BIAS，仅用于命中率追踪）
    over_shadow_candidates = []  # 大球影子候选（2026-08-02新增，见over_shadow_bets建表注释）
    team_total_shadow_full = []  # 球队大小完整候选(大球+小球，不做每日Top10截断)
    moneyline_shadow_full = []  # 独赢完整候选(全部outcome，不做每日Top10截断，见建表注释)
    # 其他市场影子：用 dict 去重，key=(uid,market,outcome)，保留 hit_score 最高的一条
    shadow_multi: dict[str, dict] = {
        "moneyline": {}, "spread": {}, "1x2": {},
        # 被转正门槛拦下的候选（反事实观察，2026-08-11新增）——用来破解
        # "门槛关闭→无新样本→门槛永远打不开"的自锁，见下方 _gated_out 说明
        "gated": {},
        # V2公式被同一道_in_scope()拦下的候选（反事实观察，2026-09-06新增）——
        # 此前V1有_gated_out追踪、V2完全没有，V2从2026-07-19起基本被同一次策略
        # 收窄锁死(formula_version='v2'最新一条停在07-18，之后再无新增)，但被拦
        # 的候选从未被记录，没有任何数据能判断"V2这套价值边际打分逻辑如果放开
        # 会不会有用"。单独开一个shadow_type(不跟V1的'gated'混在一起)，因为V1/V2
        # 是两套不同的打分公式，混在同一个桶里会让"这条候选到底是哪套逻辑选出来的"
        # 变得没法区分，污染两边各自的反事实分析。
        "gated_v2": {},
        # LSTM(EMA+AR1)信号影子观察桶——独立于上面三个桶，用现有model_prob和
        # LSTM校准概率的融合值单独打分，不影响主流程，见 _lstm_home_win_prob() 说明
        "lstm_moneyline": {}, "lstm_1x2": {},
        "lstm_spread": {},
        # 球队大小(team_total及home/away变体)影子观察桶——2026-07-19新增，此前该
        # 市场完全没有影子追踪/转正判断，见 _team_total_validation_status() 说明
        "team_total": {},
        # FotMob xG/射正信号影子观察桶——2026-07-20新增，跟LSTM桶同样的处理方式：
        # 不直接混入主流程p_fusion，先用blend后的概率单独打分/单独结算，见
        # get_fotmob_xg_probs()/get_fotmob_shots_probs() 说明
        "fotmob_1x2": {},
        # FotMob 整场大小球/球队大小影子观察桶——2026-07-21新增（深度审查FotMob数据源
        # 能支撑哪些玩法后补上，回测已验证get_fotmob_totals_probs()/
        # get_fotmob_team_total_probs()在真实历史比赛上概率合理，见_backtest_fotmob_shadow.py），
        # 跟fotmob_1x2同一套0.85/0.15 blend口径，只是市场换成整场大小球/球队大小。
        "fotmob_totals": {}, "fotmob_team_total": {},
        # FotMob让球影子观察桶——2026-07-21新增，见get_fotmob_spread_probs()说明
        "fotmob_spread": {},
        # FotMob角球影子观察桶——角球候选/概率在corner_model.py的独立数据源(pinnacle_
        # corner_odds)里，不在本函数遍历的match_map范围内，由_run_one_date()在角球
        # 分析阶段预先算好通过precomputed_corner_shadow传入，见本函数docstring说明。
        "fotmob_corner": dict(precomputed_corner_shadow) if precomputed_corner_shadow else {},
        # 半全场(HT/FT)信号影子观察桶——2026-07-24新增，见precomputed_htft_shadow说明。
        # FIX-006 闭环结论（report_jc_closure.md）：半全场水位实测22~32%，无HT模型、
        # 无sharp参照，"不建议立项"——本桶保持纯影子观察性质，任何转正主张都必须先
        # 解决"半场进球率模型+sharp参照"两个前置缺口，不能靠累计影子样本自然转正。
        "htft": dict(precomputed_htft_shadow) if precomputed_htft_shadow else {},
        # 半全场无联赛过滤平行线——2026-09-01新增，见precomputed_htft_nofilter_shadow说明，
        # 跟"htft"是同一批原始候选，唯一区别是不套用联赛白名单，用户要求每天对比两边
        # 命中率/ROI，验证过滤是否真的有效（跟team_total市场的"老逻辑平行线"同一个思路）
        "htft_nofilter": dict(precomputed_htft_nofilter_shadow) if precomputed_htft_nofilter_shadow else {},
        # 企鹅体育两队历史交锋信号影子观察桶——2026-07-30新增，见get_qiety_h2h_probs()说明
        "qiety_h2h": {},
        # 伤停信号影子观察桶——2026-08-01新增，见get_injury_impact_probs()说明
        "injury_impact": {},
    }

    # Bug修复：预加载比分预测从 football_score_predictions 表（predict_football.py 写入）
    # 之前从 basketball_prediction WHERE sport_type='football' 读取，该表由篮球模块维护，逻辑错乱
    _top_score_cache: dict = {}
    try:
        with engine.connect() as conn:
            _ts_rows = conn.execute(text("""
                SELECT home_team, away_team, top_score
                FROM football_score_predictions
                WHERE fetch_date IN (:fd, :nd) AND top_score IS NOT NULL
            """), {"fd": fetch_date, "nd": next_date}).fetchall()
        for _r in _ts_rows:
            _top_score_cache[(_r[0].lower(), _r[1].lower())] = _r[2]
        log.info(f"  ⚽ 比分预测预加载: {len(_top_score_cache)} 场（football_score_predictions）")
    except Exception:
        pass

    # 伤停信号预加载(2026-08-01新增)：okooo_injuries(40_okooo_injury_scraper.py写入)
    # 按match_id分组记录双方队名+缺阵球员本赛季累计分钟数，供get_injury_impact_probs()
    # 做队名模糊匹配用，一次性加载不逐场查库(okooo_injuries当前才218行，全表扫描
    # 每场比赛都能接受，量大了再考虑索引优化)。
    _injury_cache: dict = {}  # match_id -> {"home": {"team":str,"missing_minutes":int}, "away": {...}}
    try:
        with engine.connect() as conn:
            _inj_rows = conn.execute(text("""
                SELECT match_id, side, team, minutes, will_miss
                FROM okooo_injuries
                WHERE fetch_date IN (:fd, :nd) AND will_miss='是'
            """), {"fd": fetch_date, "nd": next_date}).fetchall()
        for _mid, _side, _team, _mins, _wm in _inj_rows:
            try:
                _mins_i = int(_mins) if _mins else 0
            except (TypeError, ValueError):
                _mins_i = 0
            _slot = _injury_cache.setdefault(_mid, {})
            _e = _slot.setdefault(_side, {"team": _team, "missing_minutes": 0})
            _e["missing_minutes"] += _mins_i
        log.info(f"  🩹 伤停信号预加载: {len(_injury_cache)} 场（okooo_injuries）")
    except Exception:
        pass

    # 比分预测覆盖所有分析赛事（不仅限于通过推荐门槛的），供"比分预测单"输出
    _score_all: dict = {}  # uid → {home, away, league, kickoff, top_score, lam_h, lam_a}

    # ─── 三段式并行架构 ──────────────────────────────────────────────────────────
    # Pass1(串行): 过滤+DB预读 → Pass2(4线程并行): get_model_probs → Pass3(串行): 评分写入
    import concurrent.futures as _cf_gen
    _skip_team_kw    = ["(bookings)", "(corners)", "(cards)", "(offside)"]
    _tier_order_pre  = {"wc_boost": 1, "tier1": 1, "tier2": 2, "tier3": 3, "tier4": 4}
    _wc_kw_odds      = ['world cup', 'fifa', 'euro', 'copa america', 'nations league']
    _wc_kw_best      = ['world cup', 'fifa', 'euro', 'copa america']

    # ── Pass 1: 过滤 + DB预读（串行，SQLite WAL 读并发安全但写序列化）──
    _match_data: dict = {}
    for _p1_row in matches:
        (_p1_uid, _p1_spt, _p1_lg, _p1_hm, _p1_aw,
         _p1_ko, _p1_sc, _p1_srcj) = _p1_row
        _p1_srcs = json.loads(_p1_srcj or "{}")
        if any(kw in f"{_p1_hm} {_p1_aw}".lower() for kw in _skip_team_kw):
            continue
        _p1_tier  = _get_league_tier(_p1_lg, sport_code=_p1_spt)
        if any(re.search(kw.lower(), (_p1_lg or "").lower()) for kw in LEAGUE_BLACKLIST_KEYWORDS):
            continue
        if _tier_order_pre.get(_p1_tier, 4) > _tier_order_pre.get(RECOMMEND_MIN_TIER, 3):
            continue
        if not precomputed:
            build_unified_odds(_p1_uid, _p1_srcs, fetch_date)
            compute_consensus_odds(_p1_uid, fetch_date)
        with engine.connect() as _c1:
            _p1_odds = _c1.execute(text("""
                SELECT market, outcome, consensus_odds, sharp_odds, implied_prob, source_count, handicap
                FROM consensus_odds
                WHERE unified_id=:uid AND fetch_date=:fd
                  AND consensus_odds >= :mn AND consensus_odds <= :mx
            """), {"uid": _p1_uid, "fd": fetch_date,
                   "mn": MIN_RECOMMEND_ODDS, "mx": MAX_RECOMMEND_ODDS}).fetchall()
            if not _p1_odds and any(kw in _p1_lg.lower() for kw in _wc_kw_odds):
                _p1_odds = _c1.execute(text("""
                    SELECT market, outcome, consensus_odds, sharp_odds, implied_prob, source_count, handicap
                    FROM consensus_odds
                    WHERE unified_id=:uid AND fetch_date >= date(:fd, '-7 days')
                      AND consensus_odds >= :mn AND consensus_odds <= :mx
                    ORDER BY fetch_date DESC
                """), {"uid": _p1_uid, "fd": fetch_date,
                       "mn": MIN_RECOMMEND_ODDS, "mx": MAX_RECOMMEND_ODDS}).fetchall()
        if not _p1_odds:
            continue
        # Bug修复：原来 book_probs 只按 outcome("over"/"under") 建key，total 和 team_total
        # 两个市场的 over/under 会互相覆盖（同一场比赛既有大小球又有球队大小时，谁在SQL结果
        # 里排后面谁的隐含概率就把前面的顶掉）。team_total 单独加前缀隔开，避免混淆。
        # 顺带把真实盘口线(handicap)取出来，供 get_model_probs() 按真实线算模型概率用
        # （而不是永远按固定2.5线/篮球"最接近公平赔率2.0"的线算，那是另一个已修复的bug）。
        _p1_book = {}
        _p1_total_line = None
        _p1_team_total_line = None
        _p1_team_total_home_line = None
        _p1_team_total_away_line = None
        for _bm, _bo, _bco, _, _, _, _bhc in _p1_odds:
            if not (_bco and _bco > 1.0):
                continue
            # team_total_home/team_total_away: Pinnacle对同一场比赛的主客队team_total
            # 是两条独立market各自带线（见12_pinnacle_scraper.py的side修复），分开存key。
            # 裸的"team_total"是历史遗留/未识别主客队来源，保留兼容旧行为。
            if _bm == "team_total_home":
                _p1_book[f"team_total_home_{_bo}"] = round(1.0 / _bco, 4)
                if _bhc is not None:
                    _p1_team_total_home_line = float(_bhc)
            elif _bm == "team_total_away":
                _p1_book[f"team_total_away_{_bo}"] = round(1.0 / _bco, 4)
                if _bhc is not None:
                    _p1_team_total_away_line = float(_bhc)
            elif _bm == "team_total":
                _p1_book[f"team_total_{_bo}"] = round(1.0 / _bco, 4)
                if _bhc is not None:
                    _p1_team_total_line = float(_bhc)
            else:
                _p1_book[_bo] = round(1.0 / _bco, 4)
                if _bm == "total" and _bhc is not None:
                    _p1_total_line = float(_bhc)
        with engine.connect() as _c2:
            _p1_best_rows = _c2.execute(text("""
                SELECT source, market, outcome, odds_value FROM unified_odds
                WHERE unified_id=:uid AND fetch_date=:fd AND odds_value BETWEEN 1.20 AND 15.0
                ORDER BY odds_value DESC LIMIT 10
            """), {"uid": _p1_uid, "fd": fetch_date}).fetchall()
            if not _p1_best_rows and any(kw in _p1_lg.lower() for kw in _wc_kw_best):
                _p1_best_rows = _c2.execute(text("""
                    SELECT source, market, outcome, odds_value FROM unified_odds
                    WHERE unified_id=:uid AND fetch_date >= date(:fd, '-7 days')
                      AND odds_value BETWEEN 1.20 AND 15.0
                    ORDER BY fetch_date DESC, odds_value DESC LIMIT 10
                """), {"uid": _p1_uid, "fd": fetch_date}).fetchall()
        _p1_best: dict = {}
        for _bs, _bm, _bo, _bv in _p1_best_rows:
            _bk = (_bm, _bo)
            if _bk not in _p1_best or _bv > _p1_best[_bk][1]:
                _p1_best[_bk] = (_bs, _bv)
        _match_data[_p1_uid] = {
            "row": _p1_row, "league_tier": _p1_tier,
            "odds_rows": _p1_odds, "book_probs": _p1_book, "best_by_market": _p1_best,
            "total_line": _p1_total_line, "team_total_line": _p1_team_total_line,
            "team_total_home_line": _p1_team_total_home_line,
            "team_total_away_line": _p1_team_total_away_line,
        }
        # 为所有足球赛事预填 _score_all（含未通过推荐门槛的）
        if _p1_spt.lower() in ("football", "soccer"):
            _score_all[_p1_uid] = {
                "home": _p1_hm, "away": _p1_aw, "league": _p1_lg, "kickoff": _p1_ko,
                "top_score": _top_score_cache.get((_p1_hm.lower(), _p1_aw.lower())),
            }

    log.info(f"  Pass1预收集: {len(_match_data)}/{len(matches)} 场通过过滤")

    # ── Pass 2: 并行计算 get_model_probs（4线程；DB读各自独立连接，ML推理线程安全）──
    def _run_model_parallel(uid):
        d = _match_data[uid]
        _, _sp, _lg, _hm, _aw, *_ = d["row"]
        try:
            return uid, get_model_probs(uid, _hm, _aw,
                                        league_name=_lg, sport_code=_sp,
                                        book_probs=d["book_probs"],
                                        total_line=d.get("total_line"),
                                        team_total_line=d.get("team_total_line"),
                                        team_total_home_line=d.get("team_total_home_line"),
                                        team_total_away_line=d.get("team_total_away_line"))
        except Exception as _me:
            log.warning(f"  get_model_probs({uid}) 并行异常: {_me}")
            return uid, {}

    _t0_model = time.time()
    with _cf_gen.ThreadPoolExecutor(max_workers=4) as _pool_gen:
        _model_results: dict = dict(_pool_gen.map(_run_model_parallel,
                                                   list(_match_data.keys())))
    log.info(f"  Pass2并行模型: {len(_model_results)} 场，耗时 {time.time()-_t0_model:.1f}s")

    # ── Pass 3: 串行评分（推荐写入共享状态，不可并行）──
    for row in matches:
        (uid, sport, league, home, away, kickoff, src_cnt, sources_json) = row
        if uid not in _match_data:
            continue
        _d3           = _match_data[uid]
        league_tier   = _d3["league_tier"]
        odds_rows     = _d3["odds_rows"]
        best_by_market = _d3["best_by_market"]
        model_probs   = _model_results.get(uid, {})
        _qiety_mid    = json.loads(sources_json or "{}").get("qiety_yb")
        _qh_p_raw     = get_qiety_h2h_probs(_qiety_mid, sport, fetch_date, next_date) if _qiety_mid else {}
        _inj_p_raw    = get_injury_impact_probs(home, away, sport, _injury_cache)

        for market, outcome, consensus, sharp, implied, sc_odds, row_handicap in odds_rows:
            _skip_kw = ["booking", "card", "offside", "throw", "foul", "penalty_shootout"]
            if any(kw in market.lower() for kw in _skip_kw):
                continue

            # 篮球总分线异常预警：线 > 联赛历史上限 × 1.05
            # 低流动性联赛定线虚高 → 大球方向价值消失，反手小球可能有隐性价值
            # 策略：跳过 over（大球），放行 under（小球）并用 "total_flip" 绕过 0.03 惩罚
            _is_anomaly_flip = False
            if (sport in ("basketball", "Basketball")
                    and market.lower() in ("total", "totals")
                    and row_handicap):
                _cap = _get_bball_total_cap(league)
                if row_handicap > _cap * 1.05:
                    if outcome == "over":
                        log.warning(
                            f"  ⚠️ 总分线虚高，跳过大球: {home} vs {away} "
                            f"line={row_handicap} > cap={_cap}×1.05={_cap*1.05:.0f}"
                        )
                        continue
                    else:
                        _is_anomaly_flip = True
                        log.info(
                            f"  🔄 总分线虚高，反手小球候选: {home} vs {away} "
                            f"line={row_handicap} (cap={_cap})"
                        )
            # 大小球无独立模型支撑、纯市场共识驱动直接排除（CLAUDE.md"推荐单数据支撑
            # 规则"永久规则）：篮球是P_poisson(正态模型摔到跨联赛全局兜底)和P_elo
            # (Basketball-Reference数据缺失)两个模型分量全缺；足球是球队级+联赛基线级
            # 两级都没有真实样本、且无P_elo兜底。p融合等于纯P_book时不进候选池
            # （2026-07-12，NBA夏季联赛"大球182.5"等推荐排查发现，用户明确要求排除而非降权，
            # 同日要求扩展到足球）
            # 融合概率：已含 P_book，不再需要 implied fallback 兜底
            # team_total 单独查 "team_total_over/under"（跟 book_probs/poisson_probs 的
            # key保持一致，避免跟market="total"的over/under互相覆盖，见上面的bug修复说明）
            # team_total_home/team_total_away：主客队各自独立盘口线，各自查专属key
            # （见team_total主客队身份修复），裸"team_total"仍是旧口径(默认主队)
            _is_team_total = market == "team_total" or market.startswith("team_total_")
            _lookup_key = f"{market}_{outcome}" if _is_team_total else outcome

            # Bug修复(2026-07-19)：无独立模型支撑排除规则(CLAUDE.md"推荐单数据支撑规则"
            # 永久规则)以前只检查 market in ("total","totals")，team_total及其home/away
            # 变体完全没走这道检查——现在 _totals_book_only 集合(get_model_probs()里)已
            # 扩展到覆盖team_total家族的key，这里同步用_lookup_key(而不是裸outcome)去匹配，
            # 让球队大小市场也受同一条规则约束。
            _book_only_check_key = _lookup_key if _is_team_total else outcome
            if ((market.lower() in ("total", "totals") or _is_team_total)
                    and outcome in ("over", "under")
                    and _book_only_check_key in model_probs.get("_totals_book_only", set())):
                log.info(
                    f"  🚫 无独立模型支撑，纯市场共识驱动，排除: {home} vs {away} "
                    f"{market}/{outcome} line={row_handicap}"
                )
                continue
            _valid_markets = ["total", "team_total", "spread", "moneyline", "over", "under",
                              "match_winner", "1x2", "handicap", "asian_handicap", "ah",
                              "totals", "ou", "h1", "h2", "full_time",
                              "corner_ou", "corner_hdp"]
            if market.lower() not in [v.lower() for v in _valid_markets]:
                if not any(market.lower().startswith(v) for v in ["total", "team_total", "spread", "moneyline"]):
                    continue
            # Bug修复(2026-08-11)：让球(spread)市场以前直接拿 model_probs[outcome]
            # 当模型概率——那是"直接获胜"概率(moneyline口径)，不是"打赢这个盘口"
            # 的概率，两者在让分大的时候差着十万八千里。实测确证：同场同方向的
            # spread 与 moneyline 候选，model_prob **99/99 组完全相同**(精确到1e-6)；
            # |盘口|与model_prob相关系数仅+0.03(真正的让分模型必须显著为负)；篮球
            # 让分盘51注模型均值0.6535 vs 实际命中0.3922(高估26个百分点)，ROI-27.8%、
            # 亏14.19u。项目里其实已有正确的覆盖概率函数(_spread_cover_prob/
            # _lstm_spread_cover_prob/get_fotmob_spread_probs)，但只接在影子观察桶上，
            # 主推荐单一直没用。这里按CLAUDE.md"推荐单数据支撑规则"永久规则处理：
            # 该市场拿不到**让球口径**的真实模型概率就直接排除，不允许用独赢概率冒充。
            # 注意：这里只打标记不 continue。影子观察桶(shadow_multi，含用
            # _lstm_spread_cover_prob/get_fotmob_spread_probs 算的**正确**让球概率的
            # 那几个桶)在本循环更靠后的位置填充，提前 continue 会连影子记录一起掐掉，
            # 而那些桶正是将来判断"接了正确让球模型后到底行不行"的唯一数据来源。
            # 真正的拦截放在 recommendations/recommendations_v2 的 append 处。
            #
            # 2026-08-24补完(用户明确要求)：2026-08-11那次修复只加了上面这道"拿不到
            # 让球口径概率就排除"的检查，但从没有代码真正往model_probs里写
            # "spread_{outcome}"这个key——导致让球市场从那天起就是100%排除，不区分
            # 数据好坏（不是"有数据支撑的候选能通过、没有的被挡"，是全部候选一律被挡）。
            # 现在把这道线接上：用跟下面影子观察桶(lstm_spread/fotmob_spread)完全
            # 相同的0.85/0.15混合公式算真实覆盖概率，但只有对应信号源已经通过
            # _validation_result()显著性检验(跟项目里其他所有"转正"判定同一套标准，
            # 不因为"应该有用"就绕过验证)才允许写进model_probs。2026-08-24当天两个
            # 信号源都未过(LSTM ci_lower=-11.6%/FotMob ci_lower=-34%)，这次接线本身
            # 不会让今天多出任何让球正式推荐，是往后哪天信号真正达标时自动生效的
            # 基础设施，不是当天生效的功能。
            if (market.lower() in ("spread", "handicap", "asian_handicap", "ah")
                    and outcome in ("home", "away") and row_handicap is not None
                    and f"spread_{outcome}" not in model_probs):
                _sp_base_p = model_probs.get(outcome)
                if _sp_base_p is not None:
                    _sp_cover_p = None
                    _sp_cover_from_fotmob = False
                    if _lstm_spread_validation_status(sport).get("validated"):
                        _sp_cover_p = _lstm_spread_cover_prob(home, away, sport, outcome, row_handicap)
                    if (_sp_cover_p is None and sport.lower() in ("football", "soccer")
                            and _fotmob_spread_validation_status().get("validated")):
                        _sp_fm_r = get_fotmob_spread_probs(home, away, league, outcome, row_handicap)
                        _sp_cover_p = _sp_fm_r.get(outcome) if _sp_fm_r else None
                        _sp_cover_from_fotmob = _sp_cover_p is not None
                    if _sp_cover_p is not None:
                        model_probs[f"spread_{outcome}"] = 0.85 * _sp_base_p + 0.15 * _sp_cover_p
                        # Bug修复(2026-08-25)：预防性修复——fotmob_totals/fotmob_team_total
                        # 曾经出现过同一路FotMob信号被计入两次的bug(那两处P_elo回填逻辑
                        # 2026-08-25已回滚，见CLAUDE.md/项目记忆)，这里提前避免同款问题：
                        # 这条cover_p若来自FotMob，下面第6753行附近的fotmob_spread影子桶会
                        # 再用同一个get_fotmob_spread_probs()结果按0.85/0.15二次混合，等于
                        # 同一路信号计入两次。目前_fotmob_spread_validation_status()还没转正
                        # (2026-08-24未过)，这条分支实际还没被触发过，属于抢在它转正之前
                        # 先堵上，不是修复已发生的损失。
                        if _sp_cover_from_fotmob:
                            model_probs.setdefault("_fotmob_spread_fill_keys", set()).add(f"spread_{outcome}")

            _spread_no_cover_model = False
            if market.lower() in ("spread", "handicap", "asian_handicap", "ah"):
                if f"spread_{outcome}" in model_probs:
                    _lookup_key = f"spread_{outcome}"
                else:
                    _spread_no_cover_model = True
            has_model = _lookup_key in model_probs
            model_prob = model_probs.get(_lookup_key)
            if model_prob is None and _is_team_total:
                # 没有team_total专属概率时，退回旧行为（可能跟total的线不一致，但好过没有）
                has_model = outcome in model_probs
                model_prob = model_probs.get(outcome)
            if model_prob is None:
                # 融合失败（三个来源均缺）：用 implied 降级并标记为弱预测
                model_prob = (implied or 0.33) * 0.50
            if model_prob <= 0:
                continue

            # 足球三选一(1x2)的平局：概率天然被封顶在 ~0.50（多数场次 0.22~0.30），
            # 跟主胜/客胜这种"二选一里挑赢家"用同一条 model_prob>=0.50 门槛不公平——
            # 凯利公式本身不要求概率过半才有正期望值。改为单独给平局降低概率门槛，
            # 同时提高 value_edge 要求作为补偿，避免单纯放宽标准导致弱边际平局涌入。
            _is_football_draw = (sport.lower() in ("football", "soccer")
                                  and market.lower() in ("moneyline", "match_winner", "1x2")
                                  and outcome == "draw")
            # 门槛演进：_backtest_draw_threshold_full.py 全量回测(0708)先定出 prob>=0.28&edge>=0.03
            # （原始融合概率下的最优区间）。随后 _backtest_draw_calibration_fix.py 用训练/测试集
            # 分开验证发现原始融合概率在低概率区间系统性高估平局，做等渗回归校准有帮助——
            # 但第一版PAVA没做最小样本量约束，高概率尾部几场比赛就能把值顶到1.0这种不可信
            # 极端值，_fit_draw_calibration.py 修复为"先按分位数分桶(每桶>=200场)再PAVA"后
            # 重新验证，样本外ROI从原来虚高的+4.7%修正为更可信的+1.6%（prob>=0.20&edge>=0.03，
            # n=388），效果比第一版结论温和，但门槛选择本身更稳，不是建立在虚假极端值上。
            # model_prob 在下面会被 _apply_draw_calibration() 原地替换成校准值，
            # 后续所有判断(门槛/hit_score/K¼/展示的p融合)统一用校准后的数字，不是新旧混用。
            if _is_football_draw:
                model_prob = _apply_draw_calibration(model_prob)
            _min_prob_gate = 0.20 if _is_football_draw else 0.50

            # ── 小球影子收集（MARKET_BIAS封禁前捕获，独立追踪命中率）──
            # _is_anomaly_flip=True 时已作为 total_flip 进主推荐，不重复写 shadow_bets
            _is_under = outcome == "under" and (market.lower() in ("total", "team_total", "totals")
                                                or market.lower().startswith("team_total_"))
            if _is_under and not _is_anomaly_flip:
                _raw_kelly = 0.0
                if model_prob > 0 and (consensus or 0) > 1:
                    _raw_kelly = (model_prob * consensus - 1) / (consensus - 1)
                    _raw_kelly = max(0.0, min(_raw_kelly * KELLY_FRACTION, KELLY_MAX_RATIO))
                if _raw_kelly > 0 and model_prob >= 0.50:
                    # 用正式函数计算，再反向补回 under 的 MARKET_BIAS(0.0) 和 league_tier 分
                    # Bug修复：影子小球用 ignore_bias=True 绕过 under 的 0.0 惩罚
                    # 不能传 outcome="over"（会误用 over 的 bias 乘数影响命中分语义）
                    _sd = compute_hit_score(uid, src_cnt, model_prob, consensus, sharp,
                                            sc_odds, market=market, outcome=outcome,
                                            league_tier=league_tier, sport_code=sport,
                                            ignore_bias=True)
                    _rhs = _sd["hit_score"]
                    _best_src, _best_val = best_by_market.get((market, outcome), ("consensus", consensus))
                    shadow_candidates.append({
                        "unified_id":     uid,
                        "sport_code":     sport,
                        "league_name":    league,
                        "home_team":      home,
                        "away_team":      away,
                        "kickoff_utc":    kickoff,
                        "market":         market,
                        "handicap":       row_handicap,
                        "best_odds":      round(_best_val or consensus, 4),
                        "model_prob":     round(model_prob, 4),
                        "kelly_fraction": round(_raw_kelly, 4),
                        "hit_score":      round(_rhs, 4),
                        "fetch_date":     fetch_date,
                    })

            # ── 大球影子收集（2026-08-02新增，见over_shadow_bets建表注释）──────────
            # 镜像上面小球影子收集的写法。_is_anomaly_flip=True的场次over在更上游
            # (总分线虚高预警那段)已经continue跳过，不会走到这里，不需要额外排除。
            _is_total_over = outcome == "over" and market.lower() in ("total", "totals")
            if _is_total_over:
                _raw_kelly_ov = 0.0
                if model_prob > 0 and (consensus or 0) > 1:
                    _raw_kelly_ov = (model_prob * consensus - 1) / (consensus - 1)
                    _raw_kelly_ov = max(0.0, min(_raw_kelly_ov * KELLY_FRACTION, KELLY_MAX_RATIO))
                if _raw_kelly_ov > 0 and model_prob >= 0.50:
                    _sd_ov = compute_hit_score(uid, src_cnt, model_prob, consensus, sharp,
                                               sc_odds, market=market, outcome=outcome,
                                               league_tier=league_tier, sport_code=sport,
                                               ignore_bias=True)
                    _rhs_ov = _sd_ov["hit_score"]
                    _best_src_ov, _best_val_ov = best_by_market.get((market, outcome), ("consensus", consensus))
                    over_shadow_candidates.append({
                        "unified_id":     uid,
                        "sport_code":     sport,
                        "league_name":    league,
                        "home_team":      home,
                        "away_team":      away,
                        "kickoff_utc":    kickoff,
                        "market":         market,
                        "handicap":       row_handicap,
                        "best_odds":      round(_best_val_ov or consensus, 4),
                        "model_prob":     round(model_prob, 4),
                        "kelly_fraction": round(_raw_kelly_ov, 4),
                        "hit_score":      round(_rhs_ov, 4),
                        "fetch_date":     fetch_date,
                    })

            # ── 球队大小(team_total)完整样本收集，大球+小球都收，不做每日Top10截断 ──
            # 2026-07-22新增：排查"影子观察单team_total桶(+15.6%ROI,n=32)"跟
            # "under_shadow_bets(-36.4%ROI,n=262)"结论对不上时发现，_team_total_
            # validation_status()原来查的shadow_recommendations表，跟其他所有
            # shadow_multi桶一样，每天只保留命中分最高的前10条(见generate_recommendations()
            # 结尾"其他市场影子写库"那段sorted(...)[:10])——这个截断对"仅供人工浏览的
            # 展示区块"没问题，但_team_total_validation_status('football','over')同时
            # 还被5308行左右的_in_scope()用来决定"football球队大小(大球)"能不能真正进
            # 正式推荐单、拿真实资金下注，用一个每天只留最自信10条的小样本(且天然偏向
            # 模型高置信度、可能跟小球当初"小样本看着不错、真实放量后血亏"是同一个坑)
            # 做真实资金放行判断，风险跟严谨性都不够。改成跟under_shadow_bets同样思路——
            # 完整无截断地收集全部team_total候选(大球+小球都要，不止小球)，落进新表
            # team_total_shadow_full，_team_total_validation_status()改查这张表。
            # 不改动/复用under_shadow_bets本身(该表UNIQUE约束没有outcome字段，同一场
            # 比赛同一天大球小球都命中会被UNIQUE撞掉一条；新建表规避这个问题，也不碰
            # 已经工作正常的"小球"转正判断，零回归风险)。
            if _is_team_total and outcome in ("over", "under") and not _is_anomaly_flip:
                _raw_kelly_tt = 0.0
                if model_prob > 0 and (consensus or 0) > 1:
                    _raw_kelly_tt = (model_prob * consensus - 1) / (consensus - 1)
                    _raw_kelly_tt = max(0.0, min(_raw_kelly_tt * KELLY_FRACTION, KELLY_MAX_RATIO))
                if _raw_kelly_tt > 0 and model_prob >= 0.50:
                    _sd_tt_full = compute_hit_score(uid, src_cnt, model_prob, consensus, sharp,
                                                     sc_odds, market=market, outcome=outcome,
                                                     league_tier=league_tier, sport_code=sport,
                                                     ignore_bias=True)
                    _best_src_tt, _best_val_tt = best_by_market.get((market, outcome), ("consensus", consensus))
                    team_total_shadow_full.append({
                        "unified_id":     uid,
                        "sport_code":     sport,
                        "league_name":    league,
                        "home_team":      home,
                        "away_team":      away,
                        "kickoff_utc":    kickoff,
                        "market":         market,
                        "outcome":        outcome,
                        "handicap":       row_handicap,
                        "best_odds":      round(_best_val_tt or consensus, 4),
                        "model_prob":     round(model_prob, 4),
                        "kelly_fraction": round(_raw_kelly_tt, 4),
                        "hit_score":      round(_sd_tt_full["hit_score"], 4),
                        "fetch_date":     fetch_date,
                    })

            # ── 其他市场影子收集（独赢/让分/胜平负，MARKET_BIAS封禁前，ignore_bias=True）──
            # Bug修复：真实数据里足球3选1胜平负和篮球2选1独赢在consensus_odds里都叫
            # market="moneyline"（scraper从来不写"1x2"这个标签，实测全库market='1x2'
            # 的行数=0），之前不分运动类型统一归进"独赢"桶，导致"胜平负观察单"这个桶
            # 虽然代码/展示逻辑都写好了却永远是空的死代码，足球真正的3选1盘口被错误
            # 标成"独赢"（容易让人以为是2选1）。现在按运动类型分流到各自的桶。
            _shadow_type = None
            if market.lower() in ("moneyline", "match_winner"):
                _shadow_type = "1x2" if sport.lower() in ("football", "soccer") else "moneyline"
            elif market.lower() in ("spread", "handicap", "asian_handicap", "ah"):
                _shadow_type = "spread"
            elif market.lower() == "1x2":
                _shadow_type = "1x2"
            elif _is_team_total:
                # 球队大小(team_total及home/away变体)影子观察——2026-07-19新增，
                # 见 _team_total_validation_status() 说明。market字段原样写入
                # (不像moneyline/spread那样要归一化)，_settle_result()已原生
                # 支持team_total/team_total_home/team_total_away三种market值。
                _shadow_type = "team_total"
            if _shadow_type:
                _raw_k_sh = 0.0
                if model_prob > 0 and (consensus or 0) > 1:
                    _raw_k_sh = (model_prob * consensus - 1) / (consensus - 1)
                    _raw_k_sh = max(0.0, min(_raw_k_sh * KELLY_FRACTION, KELLY_MAX_RATIO))
                _sd_sh = None
                if _raw_k_sh > 0 and model_prob >= _min_prob_gate:
                    _sd_sh = compute_hit_score(uid, src_cnt, model_prob, consensus, sharp,
                                               sc_odds, market=market, outcome=outcome,
                                               league_tier=league_tier, sport_code=sport,
                                               ignore_bias=True)
                    # edge门槛同样来自全量历史回测网格扫描结果（见上方_min_prob_gate注释）
                    if _is_football_draw and _sd_sh["value_edge"] < 0.03:
                        _sd_sh = None
                if _sd_sh is not None:
                    _bsrc_sh, _bval_sh = best_by_market.get((market, outcome), ("consensus", consensus))
                    # 独赢完整候选收集(不做每日Top10截断，见moneyline_shadow_full建表注释)——
                    # 跟shadow_multi的去重/截断逻辑各走各的，允许同一(uid,outcome)多次append，
                    # 落库时靠 UNIQUE(unified_id,market,outcome,fetch_date) + INSERT OR IGNORE
                    # 自然去重，跟team_total_shadow_full同样的处理方式。
                    if _shadow_type in ("moneyline", "1x2"):
                        moneyline_shadow_full.append({
                            "unified_id":     uid,
                            "sport_code":     sport,
                            "league_name":    league,
                            "home_team":      home,
                            "away_team":      away,
                            "kickoff_utc":    kickoff,
                            "market":         "moneyline",
                            "outcome":        outcome,
                            "best_odds":      round(_bval_sh or consensus, 4),
                            "model_prob":     round(model_prob, 4),
                            "kelly_fraction": round(_raw_k_sh, 4),
                            "hit_score":      round(_sd_sh["hit_score"], 4),
                            "fetch_date":     fetch_date,
                        })
                    _dedup_key = (uid, market, outcome)
                    _new_score = round(_sd_sh["hit_score"], 4)
                    _existing  = shadow_multi[_shadow_type].get(_dedup_key)
                    if _existing is None or _new_score > _existing["hit_score"]:
                        # market 规范化：_settle_result 只认 "moneyline"/"spread"/team_total家族
                        # "match_winner"/"1x2" → "moneyline"；"asian_handicap"/"handicap"/"ah" → "spread"；
                        # team_total 原样保留（"team_total"/"team_total_home"/"team_total_away"
                        # _settle_result 本来就原生支持这三种，不需要归一化，见上面_shadow_type分类注释）
                        if _shadow_type in ("moneyline", "1x2"):
                            _norm_market = "moneyline"
                        elif _shadow_type == "team_total":
                            _norm_market = market
                        else:
                            _norm_market = "spread"
                        shadow_multi[_shadow_type][_dedup_key] = {
                            "unified_id":     uid,
                            "sport_code":     sport,
                            "league_name":    league,
                            "home_team":      home,
                            "away_team":      away,
                            "kickoff_utc":    kickoff,
                            "shadow_type":    _shadow_type,
                            "market":         _norm_market,
                            "outcome":        outcome,
                            "handicap":       row_handicap,
                            "best_odds":      round(_bval_sh or consensus, 4),
                            "model_prob":     round(model_prob, 4),
                            "kelly_fraction": round(_raw_k_sh, 4),
                            "hit_score":      _new_score,
                            "predicted_score": _top_score_cache.get((home.lower(), away.lower())) or "-",
                            "fetch_date":     fetch_date,
                        }
                        # 首次 DB 查询后回写缓存，避免同场多 outcome 重复查
                        if (home.lower(), away.lower()) not in _top_score_cache and sport and sport.lower() in ("football", "soccer"):
                            _fs = _get_football_top_score(home, away, league)
                            if _fs:
                                _top_score_cache[(home.lower(), away.lower())] = _fs
                                shadow_multi[_shadow_type][_dedup_key]["predicted_score"] = _fs
                                _persist_xg_score(uid, home, away, league, kickoff, _fs, fetch_date)

            # ── LSTM(EMA+AR1)信号影子观察（独立分桶，不影响上面的正式 model_prob）──
            # 只对独赢/胜平负的 home/away 两个方向做（LSTM校准只回归过主胜概率，没有
            # 单独建过平局分量，见 _lstm_home_win_prob() 说明），blend比例0.85/0.15
            # 对应将来若转正时 p_fusion 计划分给 P_lstm 的权重，先在影子桶里跑真实
            # 结算验证这个比例是否真的比现有三分量融合更准，不是先接进主流程再看。
            if _shadow_type in ("moneyline", "1x2") and outcome in ("home", "away"):
                _lstm_p_home = _lstm_home_win_prob(home, away, sport)
                if _lstm_p_home is not None:
                    _lstm_p = _lstm_p_home if outcome == "home" else (1.0 - _lstm_p_home)
                    _blended_p = 0.85 * model_prob + 0.15 * _lstm_p
                    _raw_k_lstm = 0.0
                    if _blended_p > 0 and (consensus or 0) > 1:
                        _raw_k_lstm = (_blended_p * consensus - 1) / (consensus - 1)
                        _raw_k_lstm = max(0.0, min(_raw_k_lstm * KELLY_FRACTION, KELLY_MAX_RATIO))
                    if _raw_k_lstm > 0 and _blended_p >= _min_prob_gate:
                        _sd_lstm = compute_hit_score(uid, src_cnt, _blended_p, consensus, sharp,
                                                      sc_odds, market=market, outcome=outcome,
                                                      league_tier=league_tier, sport_code=sport,
                                                      ignore_bias=True)
                        _lstm_bucket = "lstm_1x2" if sport.lower() in ("football", "soccer") else "lstm_moneyline"
                        _bsrc_l, _bval_l = best_by_market.get((market, outcome), ("consensus", consensus))
                        _dedup_key_l = (uid, market, outcome)
                        _new_score_l = round(_sd_lstm["hit_score"], 4)
                        _existing_l = shadow_multi[_lstm_bucket].get(_dedup_key_l)
                        if _existing_l is None or _new_score_l > _existing_l["hit_score"]:
                            shadow_multi[_lstm_bucket][_dedup_key_l] = {
                                "unified_id":     uid,
                                "sport_code":     sport,
                                "league_name":    league,
                                "home_team":      home,
                                "away_team":      away,
                                "kickoff_utc":    kickoff,
                                "shadow_type":    _lstm_bucket,
                                "market":         "moneyline",
                                "outcome":        outcome,
                                "handicap":       row_handicap,
                                "best_odds":      round(_bval_l or consensus, 4),
                                "model_prob":     round(_blended_p, 4),
                                "kelly_fraction": round(_raw_k_lstm, 4),
                                "hit_score":      _new_score_l,
                                "predicted_score": _top_score_cache.get((home.lower(), away.lower())) or "-",
                                "fetch_date":     fetch_date,
                            }

            # ── FotMob xG/射正信号影子观察（独立分桶，不影响上面的正式 model_prob）──
            # 只对独赢/胜平负的 home/away 两个方向做，blend比例0.85/0.15跟LSTM桶
            # 保持一致口径，方便横向比较两个新信号谁的转正证据更强。优先用射正模型
            # (样本积累更快)，缺失时退到xG模型，两者都缺失则跳过（不当作0处理）。
            if sport.lower() in ("football", "soccer") and _shadow_type in ("moneyline", "1x2") \
                    and outcome in ("home", "away"):
                _fm_p_raw = get_fotmob_shots_probs(home, away, league) or get_fotmob_xg_probs(home, away, league)
                if _fm_p_raw and outcome in _fm_p_raw:
                    _fm_p = _fm_p_raw[outcome]
                    _blended_p_fm = 0.85 * model_prob + 0.15 * _fm_p
                    _raw_k_fm = 0.0
                    if _blended_p_fm > 0 and (consensus or 0) > 1:
                        _raw_k_fm = (_blended_p_fm * consensus - 1) / (consensus - 1)
                        _raw_k_fm = max(0.0, min(_raw_k_fm * KELLY_FRACTION, KELLY_MAX_RATIO))
                    if _raw_k_fm > 0 and _blended_p_fm >= _min_prob_gate:
                        _sd_fm = compute_hit_score(uid, src_cnt, _blended_p_fm, consensus, sharp,
                                                    sc_odds, market=market, outcome=outcome,
                                                    league_tier=league_tier, sport_code=sport,
                                                    ignore_bias=True)
                        _bsrc_fm, _bval_fm = best_by_market.get((market, outcome), ("consensus", consensus))
                        _dedup_key_fm = (uid, market, outcome)
                        _new_score_fm = round(_sd_fm["hit_score"], 4)
                        _existing_fm = shadow_multi["fotmob_1x2"].get(_dedup_key_fm)
                        if _existing_fm is None or _new_score_fm > _existing_fm["hit_score"]:
                            shadow_multi["fotmob_1x2"][_dedup_key_fm] = {
                                "unified_id":     uid,
                                "sport_code":     sport,
                                "league_name":    league,
                                "home_team":      home,
                                "away_team":      away,
                                "kickoff_utc":    kickoff,
                                "shadow_type":    "fotmob_1x2",
                                "market":         "moneyline",
                                "outcome":        outcome,
                                "handicap":       row_handicap,
                                "best_odds":      round(_bval_fm or consensus, 4),
                                "model_prob":     round(_blended_p_fm, 4),
                                "kelly_fraction": round(_raw_k_fm, 4),
                                "hit_score":      _new_score_fm,
                                "predicted_score": _top_score_cache.get((home.lower(), away.lower())) or "-",
                                "fetch_date":     fetch_date,
                            }

            # ── 企鹅体育两队历史交锋信号影子观察（独立分桶，2026-07-30新增） ──
            # 数据源: 46_qiety_lineup_scraper.py写入的qiety_h2h_history。用match_id
            # 精确关联(见get_qiety_h2h_probs)，不是队名模糊匹配。跟LSTM/FotMob桶
            # 同一套blend口径(0.85/0.15)，先进影子观察单攒结算样本，不直接进正式
            # 推荐单——符合CLAUDE.md推荐单数据支撑规则+[[feedback_north_star_hit_rate]]
            # (改动要有回测支撑，这批数据刚落库，还没有任何结算证据)。足球+篮球都覆盖
            # (qiety接口本身不分运动)，跟fotmob_1x2不同、不限制sport。
            if _shadow_type in ("moneyline", "1x2") and outcome in ("home", "away", "draw") \
                    and outcome in _qh_p_raw:
                _qh_p = _qh_p_raw[outcome]
                _blended_p_qh = 0.85 * model_prob + 0.15 * _qh_p
                _raw_k_qh = 0.0
                if _blended_p_qh > 0 and (consensus or 0) > 1:
                    _raw_k_qh = (_blended_p_qh * consensus - 1) / (consensus - 1)
                    _raw_k_qh = max(0.0, min(_raw_k_qh * KELLY_FRACTION, KELLY_MAX_RATIO))
                if _raw_k_qh > 0 and _blended_p_qh >= _min_prob_gate:
                    _sd_qh = compute_hit_score(uid, src_cnt, _blended_p_qh, consensus, sharp,
                                                sc_odds, market=market, outcome=outcome,
                                                league_tier=league_tier, sport_code=sport,
                                                ignore_bias=True)
                    _bsrc_qh, _bval_qh = best_by_market.get((market, outcome), ("consensus", consensus))
                    _dedup_key_qh = (uid, market, outcome)
                    _new_score_qh = round(_sd_qh["hit_score"], 4)
                    _existing_qh = shadow_multi["qiety_h2h"].get(_dedup_key_qh)
                    if _existing_qh is None or _new_score_qh > _existing_qh["hit_score"]:
                        shadow_multi["qiety_h2h"][_dedup_key_qh] = {
                            "unified_id":     uid,
                            "sport_code":     sport,
                            "league_name":    league,
                            "home_team":      home,
                            "away_team":      away,
                            "kickoff_utc":    kickoff,
                            "shadow_type":    "qiety_h2h",
                            "market":         "moneyline" if sport.lower() not in ("football", "soccer") else "1x2",
                            "outcome":        outcome,
                            "handicap":       row_handicap,
                            "best_odds":      round(_bval_qh or consensus, 4),
                            "model_prob":     round(_blended_p_qh, 4),
                            "kelly_fraction": round(_raw_k_qh, 4),
                            "hit_score":      _new_score_qh,
                            "predicted_score": _top_score_cache.get((home.lower(), away.lower())) or "-",
                            "fetch_date":     fetch_date,
                        }

            # ── 伤停信号影子观察（独立分桶，2026-08-01新增） ──
            # 数据源: 40_okooo_injury_scraper.py写入的okooo_injuries，见
            # get_injury_impact_probs()说明。跟qiety_h2h同一套0.85/0.15 blend口径，
            # 先进影子观察单攒结算样本，不直接进正式推荐单——这批信号刚落地，
            # 还没有任何结算证据，符合CLAUDE.md推荐单数据支撑规则+
            # [[feedback_north_star_hit_rate]]（改动要有回测支撑，不能拍脑袋）。
            if _shadow_type in ("moneyline", "1x2") and outcome in ("home", "away", "draw") \
                    and outcome in _inj_p_raw:
                _inj_p = _inj_p_raw[outcome]
                _blended_p_inj = 0.85 * model_prob + 0.15 * _inj_p
                _raw_k_inj = 0.0
                if _blended_p_inj > 0 and (consensus or 0) > 1:
                    _raw_k_inj = (_blended_p_inj * consensus - 1) / (consensus - 1)
                    _raw_k_inj = max(0.0, min(_raw_k_inj * KELLY_FRACTION, KELLY_MAX_RATIO))
                if _raw_k_inj > 0 and _blended_p_inj >= _min_prob_gate:
                    _sd_inj = compute_hit_score(uid, src_cnt, _blended_p_inj, consensus, sharp,
                                                 sc_odds, market=market, outcome=outcome,
                                                 league_tier=league_tier, sport_code=sport,
                                                 ignore_bias=True)
                    _bsrc_inj, _bval_inj = best_by_market.get((market, outcome), ("consensus", consensus))
                    _dedup_key_inj = (uid, market, outcome)
                    _new_score_inj = round(_sd_inj["hit_score"], 4)
                    _existing_inj = shadow_multi["injury_impact"].get(_dedup_key_inj)
                    if _existing_inj is None or _new_score_inj > _existing_inj["hit_score"]:
                        shadow_multi["injury_impact"][_dedup_key_inj] = {
                            "unified_id":     uid,
                            "sport_code":     sport,
                            "league_name":    league,
                            "home_team":      home,
                            "away_team":      away,
                            "kickoff_utc":    kickoff,
                            "shadow_type":    "injury_impact",
                            "market":         "moneyline" if sport.lower() not in ("football", "soccer") else "1x2",
                            "outcome":        outcome,
                            "handicap":       row_handicap,
                            "best_odds":      round(_bval_inj or consensus, 4),
                            "model_prob":     round(_blended_p_inj, 4),
                            "kelly_fraction": round(_raw_k_inj, 4),
                            "hit_score":      _new_score_inj,
                            "predicted_score": _top_score_cache.get((home.lower(), away.lower())) or "-",
                            "fetch_date":     fetch_date,
                        }

            # ── FotMob xG/射正信号影子观察：整场大小球(totals)，真实盘口线 ──
            # 2026-07-21新增。直接用market/outcome判断，不依赖_shadow_type（"total"/"totals"
            # 市场目前不走上面"其他市场影子收集"那套_shadow_type路由，本来就没有base桶，
            # 这里独立判断更安全，不会改动total市场原有的候选/排除逻辑）。真实线来自
            # row_handicap，跟get_model_probs()里total_line参数用的是同一条线，
            # 保证P_book/P_fotmob/P_poisson三者对齐同一个盘口，不是各算各的线。
            if sport.lower() in ("football", "soccer") and market.lower() in ("total", "totals") \
                    and outcome in ("over", "under") and row_handicap is not None:
                _fm_p_tot_raw = get_fotmob_totals_probs(home, away, league, line=row_handicap)
                if _fm_p_tot_raw and outcome in _fm_p_tot_raw:
                    _fm_p_tot = _fm_p_tot_raw[outcome]
                    _blended_p_tot = 0.85 * model_prob + 0.15 * _fm_p_tot
                    _raw_k_tot = 0.0
                    if _blended_p_tot > 0 and (consensus or 0) > 1:
                        _raw_k_tot = (_blended_p_tot * consensus - 1) / (consensus - 1)
                        _raw_k_tot = max(0.0, min(_raw_k_tot * KELLY_FRACTION, KELLY_MAX_RATIO))
                    if _raw_k_tot > 0 and _blended_p_tot >= _min_prob_gate:
                        _sd_tot = compute_hit_score(uid, src_cnt, _blended_p_tot, consensus, sharp,
                                                     sc_odds, market=market, outcome=outcome,
                                                     league_tier=league_tier, sport_code=sport,
                                                     ignore_bias=True)
                        _bsrc_tot, _bval_tot = best_by_market.get((market, outcome), ("consensus", consensus))
                        _dedup_key_tot = (uid, market, outcome)
                        _new_score_tot = round(_sd_tot["hit_score"], 4)
                        _existing_tot = shadow_multi["fotmob_totals"].get(_dedup_key_tot)
                        if _existing_tot is None or _new_score_tot > _existing_tot["hit_score"]:
                            shadow_multi["fotmob_totals"][_dedup_key_tot] = {
                                "unified_id":     uid,
                                "sport_code":     sport,
                                "league_name":    league,
                                "home_team":      home,
                                "away_team":      away,
                                "kickoff_utc":    kickoff,
                                "shadow_type":    "fotmob_totals",
                                "market":         "total",
                                "outcome":        outcome,
                                "handicap":       row_handicap,
                                "best_odds":      round(_bval_tot or consensus, 4),
                                "model_prob":     round(_blended_p_tot, 4),
                                "kelly_fraction": round(_raw_k_tot, 4),
                                "hit_score":      _new_score_tot,
                                "predicted_score": _top_score_cache.get((home.lower(), away.lower())) or "-",
                                "fetch_date":     fetch_date,
                            }

            # ── FotMob xG/射正信号影子观察：球队大小(team_total及home/away变体) ──
            # 2026-07-21新增，同样独立判断market/_is_team_total，不依赖_shadow_type=="team_total"
            # 这条路径本身已存在(2026-07-19)，这里只是追加一个并行的FotMob blend桶，
            # 不改动team_total原有的正式model_prob生成逻辑。side按market后缀决定，
            # 裸"team_total"(未识别主客队来源)沿用旧口径按主队算，跟get_fotmob_team_total_probs()
            # 的home侧一致。
            if sport.lower() in ("football", "soccer") and _is_team_total \
                    and outcome in ("over", "under") and row_handicap is not None:
                _tt_side_fm = "away" if market == "team_total_away" else "home"
                _fm_p_tt_raw = get_fotmob_team_total_probs(home, away, league, side=_tt_side_fm, line=row_handicap)
                if _fm_p_tt_raw and outcome in _fm_p_tt_raw:
                    _fm_p_tt = _fm_p_tt_raw[outcome]
                    _blended_p_tt = 0.85 * model_prob + 0.15 * _fm_p_tt
                    _raw_k_tt = 0.0
                    if _blended_p_tt > 0 and (consensus or 0) > 1:
                        _raw_k_tt = (_blended_p_tt * consensus - 1) / (consensus - 1)
                        _raw_k_tt = max(0.0, min(_raw_k_tt * KELLY_FRACTION, KELLY_MAX_RATIO))
                    if _raw_k_tt > 0 and _blended_p_tt >= _min_prob_gate:
                        _sd_tt = compute_hit_score(uid, src_cnt, _blended_p_tt, consensus, sharp,
                                                    sc_odds, market=market, outcome=outcome,
                                                    league_tier=league_tier, sport_code=sport,
                                                    ignore_bias=True)
                        _bsrc_tt, _bval_tt = best_by_market.get((market, outcome), ("consensus", consensus))
                        _dedup_key_tt = (uid, market, outcome)
                        _new_score_tt = round(_sd_tt["hit_score"], 4)
                        _existing_tt = shadow_multi["fotmob_team_total"].get(_dedup_key_tt)
                        if _existing_tt is None or _new_score_tt > _existing_tt["hit_score"]:
                            shadow_multi["fotmob_team_total"][_dedup_key_tt] = {
                                "unified_id":     uid,
                                "sport_code":     sport,
                                "league_name":    league,
                                "home_team":      home,
                                "away_team":      away,
                                "kickoff_utc":    kickoff,
                                "shadow_type":    "fotmob_team_total",
                                "market":         market,
                                "outcome":        outcome,
                                "handicap":       row_handicap,
                                "best_odds":      round(_bval_tt or consensus, 4),
                                "model_prob":     round(_blended_p_tt, 4),
                                "kelly_fraction": round(_raw_k_tt, 4),
                                "hit_score":      _new_score_tt,
                                "predicted_score": _top_score_cache.get((home.lower(), away.lower())) or "-",
                                "fetch_date":     fetch_date,
                            }

            # ── LSTM(EMA+AR1)让球(spread)信号影子观察——用margin~Normal校准算覆盖概率，
            # 跟独赢用的是同一份state_diff，只是概率转换方式换成正态分布覆盖盘口线，
            # 而不是简单的主胜/负二元 logistic，见 _lstm_spread_cover_prob() 说明 ──
            if _shadow_type == "spread" and outcome in ("home", "away"):
                _lstm_p_sp = _lstm_spread_cover_prob(home, away, sport, outcome, row_handicap)
                if _lstm_p_sp is not None:
                    _blended_p_sp = 0.85 * model_prob + 0.15 * _lstm_p_sp
                    _raw_k_sp = 0.0
                    if _blended_p_sp > 0 and (consensus or 0) > 1:
                        _raw_k_sp = (_blended_p_sp * consensus - 1) / (consensus - 1)
                        _raw_k_sp = max(0.0, min(_raw_k_sp * KELLY_FRACTION, KELLY_MAX_RATIO))
                    if _raw_k_sp > 0 and _blended_p_sp >= _min_prob_gate:
                        _sd_sp = compute_hit_score(uid, src_cnt, _blended_p_sp, consensus, sharp,
                                                    sc_odds, market=market, outcome=outcome,
                                                    league_tier=league_tier, sport_code=sport,
                                                    ignore_bias=True)
                        _bsrc_sp, _bval_sp = best_by_market.get((market, outcome), ("consensus", consensus))
                        _dedup_key_sp = (uid, market, outcome)
                        _new_score_sp = round(_sd_sp["hit_score"], 4)
                        _existing_sp = shadow_multi["lstm_spread"].get(_dedup_key_sp)
                        if _existing_sp is None or _new_score_sp > _existing_sp["hit_score"]:
                            shadow_multi["lstm_spread"][_dedup_key_sp] = {
                                "unified_id":     uid,
                                "sport_code":     sport,
                                "league_name":    league,
                                "home_team":      home,
                                "away_team":      away,
                                "kickoff_utc":    kickoff,
                                "shadow_type":    "lstm_spread",
                                "market":         "spread",
                                "outcome":        outcome,
                                "handicap":       row_handicap,
                                "best_odds":      round(_bval_sp or consensus, 4),
                                "model_prob":     round(_blended_p_sp, 4),
                                "kelly_fraction": round(_raw_k_sp, 4),
                                "hit_score":      _new_score_sp,
                                "predicted_score": _top_score_cache.get((home.lower(), away.lower())) or "-",
                                "fetch_date":     fetch_date,
                            }

            # ── FotMob xG/射正信号影子观察：让球(spread)，2026-07-21新增 ──
            # 跟上面LSTM让球桶并列、独立打分，见get_fotmob_spread_probs()说明——这是
            # 让球市场第一个基于真实进球分布(联合泊松矩阵)的信号，只对足球生效
            # (篮球让分分布跟足球进球分布形态完全不同，不能共用同一套泊松矩阵)。
            if _shadow_type == "spread" and sport.lower() in ("football", "soccer") \
                    and outcome in ("home", "away") and row_handicap is not None:
                _fm_p_sp_raw = get_fotmob_spread_probs(home, away, league, outcome, row_handicap)
                _fm_p_sp = _fm_p_sp_raw.get(outcome) if _fm_p_sp_raw else None
                if _fm_p_sp is not None:
                    # Bug修复(2026-08-25)：见上面model_probs[f"spread_{outcome}"]赋值处
                    # _fotmob_spread_fill_keys的说明，跟fotmob_totals/fotmob_team_total
                    # 同一处理——避免同一路FotMob信号被计入两次。
                    if f"spread_{outcome}" in model_probs.get("_fotmob_spread_fill_keys", set()):
                        _blended_p_fsp = model_prob
                    else:
                        _blended_p_fsp = 0.85 * model_prob + 0.15 * _fm_p_sp
                    _raw_k_fsp = 0.0
                    if _blended_p_fsp > 0 and (consensus or 0) > 1:
                        _raw_k_fsp = (_blended_p_fsp * consensus - 1) / (consensus - 1)
                        _raw_k_fsp = max(0.0, min(_raw_k_fsp * KELLY_FRACTION, KELLY_MAX_RATIO))
                    if _raw_k_fsp > 0 and _blended_p_fsp >= _min_prob_gate:
                        _sd_fsp = compute_hit_score(uid, src_cnt, _blended_p_fsp, consensus, sharp,
                                                     sc_odds, market=market, outcome=outcome,
                                                     league_tier=league_tier, sport_code=sport,
                                                     ignore_bias=True)
                        _bsrc_fsp, _bval_fsp = best_by_market.get((market, outcome), ("consensus", consensus))
                        _dedup_key_fsp = (uid, market, outcome)
                        _new_score_fsp = round(_sd_fsp["hit_score"], 4)
                        _existing_fsp = shadow_multi["fotmob_spread"].get(_dedup_key_fsp)
                        if _existing_fsp is None or _new_score_fsp > _existing_fsp["hit_score"]:
                            shadow_multi["fotmob_spread"][_dedup_key_fsp] = {
                                "unified_id":     uid,
                                "sport_code":     sport,
                                "league_name":    league,
                                "home_team":      home,
                                "away_team":      away,
                                "kickoff_utc":    kickoff,
                                "shadow_type":    "fotmob_spread",
                                "market":         "spread",
                                "outcome":        outcome,
                                "handicap":       row_handicap,
                                "best_odds":      round(_bval_fsp or consensus, 4),
                                "model_prob":     round(_blended_p_fsp, 4),
                                "kelly_fraction": round(_raw_k_fsp, 4),
                                "hit_score":      _new_score_fsp,
                                "predicted_score": _top_score_cache.get((home.lower(), away.lower())) or "-",
                                "fetch_date":     fetch_date,
                            }

            # 融合概率已含 P_book 分量，三来源全缺时已在上方降级（×0.50）
            # has_model 仅用于 reason 标记，不再额外惩罚
            # 反手小球场景：用 "total_flip" 市场名，绕过 total/under 的 0.03 全局惩罚
            _score_market = "total_flip" if _is_anomaly_flip else market
            score_data = compute_hit_score(
                uid, src_cnt, model_prob, consensus, sharp, sc_odds,
                market=_score_market, outcome=outcome,
                league_tier=league_tier, sport_code=sport
            )

            # ── V2 并行评分（不受 v1 market_bias 门控影响，独立评估）──
            _imp_v2 = implied if implied else (1.0/consensus if consensus else 0.5)
            _hs_v2 = compute_hit_score_v2(
                model_prob=model_prob,
                implied_prob=_imp_v2,
                kelly_fraction=score_data["kelly_fraction"],
                source_count=sc_odds,
            )
            if (_hs_v2 >= HIT_SCORE_V2_THRESHOLD
                    and score_data["kelly_fraction"] > 0
                    and model_prob >= 0.50
                    # 让球市场无"打赢盘口"口径概率时同样排除（见下方主推荐单同一处
                    # 说明），否则V2单会继续用独赢概率冒充让球概率下注
                    and not _spread_no_cover_model):
                _best_src_v2, _best_val_v2 = best_by_market.get(
                    (market, outcome), ("consensus", consensus))
                recommendations_v2.append({
                    "unified_id":    uid,
                    "sport_code":    sport,
                    "league_name":   league,
                    "home_team":     home,
                    "away_team":     away,
                    "kickoff_utc":   kickoff,
                    "market":        market,
                    "outcome":       outcome,
                    "best_odds":     round(_best_val_v2, 4) if _best_val_v2 else consensus,
                    "best_source":   _best_src_v2,
                    "model_prob":    round(model_prob, 4),
                    "implied_prob":  round(_imp_v2, 4),
                    "value_edge":    score_data["value_edge"],
                    "kelly_fraction": score_data["kelly_fraction"],
                    "hit_score":     _hs_v2,
                    "hit_score_v2":  _hs_v2,
                    "confidence":    "高" if _hs_v2 >= 0.75 else ("中" if _hs_v2 >= 0.55 else "低"),
                    "reason":        f"V2价值边际{score_data['value_edge']*100:+.1f}%",
                    "fetch_date":    fetch_date,
                    "handicap":      row_handicap,
                    "predicted_score": _top_score_cache.get((home.lower(), away.lower())) or "-",
                })

            # 小球盘口门槛：盘口 < UNDER_MIN_HANDICAP 的 under 不推荐（高进球风险）
            if outcome == "under" and (market.lower() in ("total", "team_total", "totals")
                                       or market.lower().startswith("team_total_")):
                if (row_handicap or 0) < UNDER_MIN_HANDICAP:
                    continue

            # P5: 使用市场级门槛和全局门槛取较高者
            effective_threshold = max(
                score_data.get("market_min_threshold", HIT_SCORE_GLOBAL_THRESHOLD),
                HIT_SCORE_GLOBAL_THRESHOLD
            )
            # hit_score 必须达标（AND 条件，不再允许 value_edge 单独通过）
            if score_data["hit_score"] < effective_threshold:
                continue

            # Bug1修复：Kelly=0 表示无正期望价值，不推荐
            if score_data["kelly_fraction"] <= 0:
                continue

            # Bug2修复：model_prob < 0.50 表示模型认为该方向不占优，方向与概率矛盾
            # （足球1x2平局例外：_min_prob_gate=0.28，见上方判定，用value_edge补偿，
            #  两个数字都来自 _backtest_draw_threshold_full.py 的全量历史回测，非人工估）
            if model_prob < _min_prob_gate:
                continue

            # edge门槛同样来自全量历史回测网格扫描结果
            if _is_football_draw and score_data["value_edge"] < 0.03:
                continue

            # p融合 0.60~0.70 区间校准：实测该区间命中率28.6%（远低于0.50~0.60的49.2%）
            # 原因：庄家已将此区间充分定价，价值边际极薄，要求额外10%边际才推荐
            if 0.60 <= model_prob < 0.70 and score_data["value_edge"] < 0.10:
                continue

            best_src, best_val = best_by_market.get((market, outcome), ("consensus", consensus))

            # 缓存预取比分预测（同场多条推荐只查一次 DB，结果回写缓存）
            _pred_key = (home.lower(), away.lower())
            if _pred_key not in _top_score_cache and sport and sport.lower() in ("football", "soccer"):
                _fs_main = _get_football_top_score(home, away, league)
                if _fs_main:
                    _top_score_cache[_pred_key] = _fs_main
                    _persist_xg_score(uid, home, away, league, kickoff, _fs_main, fetch_date)

            reason_parts = []
            if src_cnt >= 4:
                reason_parts.append(f"{src_cnt}源覆盖")
            # FIX-016-5: 该市场方向的共识源数底线标注——单源"共识"实为一家赔率照抄，
            # 复盘可按本标签分组对照单源推荐命中表现（sc_odds=该market/outcome共识源数）
            if sc_odds is not None and sc_odds < CONSENSUS_MIN_SOURCES:
                reason_parts.append(f"⚠共识仅{sc_odds}源")
            if score_data["value_edge"] > 0.05:
                reason_parts.append(f"价值边际+{score_data['value_edge']*100:.1f}%")
            if sharp and consensus and abs(sharp - consensus) / consensus < 0.03:
                reason_parts.append("夏普/共识吻合")
            if model_prob > 0.60:
                reason_parts.append(f"模型概率{model_prob*100:.0f}%")
            # P5: 标记市场偏置和联赛Tier（用实际参与打分的 _score_market，反手小球走 total_flip 偏置）
            bm, _ = get_market_bias(sport, _score_market, outcome)
            if bm != 1.00:
                if bm >= 1.10:
                    reason_parts.append(f"🔥P5加码({bm:.0%})")
                elif bm <= 0.50:
                    reason_parts.append(f"❌P5淘汰({bm:.0%})")
                elif bm < 1.00:
                    reason_parts.append(f"⚠P5抑制({bm:.0%})")
            if league_tier and LEAGUE_TIER_BOOST.get(league_tier, 1.0) != 1.0:
                tb = LEAGUE_TIER_BOOST[league_tier]
                reason_parts.append(f"Tier={league_tier}({tb:.0%})")

            rec = {
                "unified_id": uid,
                "sport_code": sport,
                "league_name": league,
                "home_team": home,
                "away_team": away,
                "kickoff_utc": kickoff,
                "market": market,
                "outcome": outcome,
                "best_odds": round(best_val, 4) if best_val else consensus,
                "best_source": best_src,
                "model_prob": round(model_prob, 4),
                "implied_prob": round(implied or 0, 4),
                "value_edge": score_data["value_edge"],
                "kelly_fraction": score_data["kelly_fraction"],
                "hit_score": score_data["hit_score"],
                "hit_score_v2": _hs_v2,
                "confidence": score_data["confidence"],
                "reason": "；".join(reason_parts) if reason_parts else "模型筛选",
                "fetch_date": fetch_date,
                "handicap": row_handicap,
                "predicted_score": _top_score_cache.get((home.lower(), away.lower())) or "-",
            }
            # Bug修复(2026-08-11)：让球市场拿不到"打赢盘口"口径的模型概率时不进
            # 正式推荐单。详见上面 _spread_no_cover_model 的说明——此前该市场直接
            # 复用 model_probs[outcome]（"直接获胜"概率，moneyline口径），实测同场
            # 同方向的 spread 与 moneyline 候选 model_prob **99/99 组完全相同**
            # (精确到1e-6)，|盘口|与model_prob相关系数仅+0.03（真让球模型必须显著
            # 为负），篮球让分盘51注模型均值0.6535 vs 实际命中0.3922、ROI-27.8%、
            # 亏14.19u。按 CLAUDE.md"推荐单数据支撑规则"永久规则，无本市场口径的
            # 真实模型支撑者直接排除，不允许用别的市场的概率冒充。
            if _spread_no_cover_model:
                log.info(
                    f"  🚫 让球市场无'打赢盘口'口径模型概率(不可用独赢概率冒充)，排除: "
                    f"{home} vs {away} {market}/{outcome} line={row_handicap}"
                )
                continue
            recommendations.append(rec)

    # 比分玩法：独立于上面10个玩法的评分循环，只在有真实盘口(Pinnacle/qiety)时才生成，
    # 名额独立于 MAX_RECS_PER_MATCH（见下方去重循环里对 market=="correct_score" 的特判）
    _cs_all_candidates: list = []  # 2026-08-20新增：留一份_in_scope()过滤前的原始候选，
    # 供"比分候选观察单"展示用——_in_scope()(7011行附近)之后会把没转正的市场从
    # recommendations里整个删掉，如果展示区块从那之后的recommendations取数，市场
    # 没转正时会一条命中分都看不到(即使candidate本身真的算出过≥0.70的命中分)，
    # 跟其他所有影子观察单"转正判断前取数，标注仅观察"的设计原则不一致。
    # Bug修复(2026-09-07)：上面这条注释描述的问题只解决了一半——_generate_correct_
    # score_recs()自己内部还有一道hit_score/kelly门槛，未达标的候选从不进它的返回值，
    # 所以_cs_all_candidates哪怕这里原样照抄也仍然是空的（2026-09-06实测：命中分
    # 门槛内候选全灭时，"比分候选观察单"整块连"0条"都不显示，直接消失）。现在
    # _generate_correct_score_recs()改为不再内部过滤、全部候选原样返回并用"qualified"
    # 字段标注是否达标——这里按该字段拆分：达标的才计入recommendations(真钱候选池)，
    # 全部(不管达标与否)都留给_cs_all_candidates供观察单展示。
    try:
        _cs_recs = _generate_correct_score_recs(_match_data, fetch_date, next_date)
        _cs_qualified = [r for r in _cs_recs if r.get("qualified")]
        recommendations.extend(_cs_qualified)
        _cs_all_candidates = list(_cs_recs)
        log.info(f"  ⚽ 比分玩法(真实盘口): {len(_cs_qualified)} 条候选"
                 f"（另有 {len(_cs_recs) - len(_cs_qualified)} 条未达命中分/凯利门槛，"
                 f"进比分候选观察单）")
    except Exception as _cs_e:
        log.warning(f"  比分玩法生成异常（跳过）: {_cs_e}")

    # 写入推荐单
    # P5: 每场比赛限 MAX_RECS_PER_MATCH 条（按命中分取前N）
    # Bug修复：去重键应为 (market类别, outcome)，而非仅 outcome
    # 这样 spread/home 和 moneyline/home 不会互相阻塞（属于不同市场）
    # 但 total/over 和 team_total/over 均属于 "size/over" 类别，仍去重
    def _dir_key(rec):
        mkt = rec["market"].lower()
        out = rec["outcome"]
        if mkt in ("total", "team_total", "totals", "ou") or mkt.startswith("team_total_"):
            return ("size", out)    # total市场：按方向去重
        if mkt in ("spread", "handicap", "asian_handicap", "ah"):
            return ("spread", out)  # 让球市场：按方向去重
        if mkt in ("moneyline", "match_winner", "1x2", "full_time", "h1", "h2"):
            return ("win", out)     # 独赢/1x2：按方向去重
        return (mkt, out)           # 其他市场：精确去重

    match_rec_count = {}
    match_score_count = {}  # 比分玩法独立计数，不占用 MAX_RECS_PER_MATCH 名额
    match_directions = {}  # uid -> set of dir_keys
    final_recs = []
    for rec in sorted(recommendations, key=lambda x: x["hit_score"], reverse=True):
        uid = rec["unified_id"]
        _is_score = rec["market"] == "correct_score"
        if _is_score:
            if match_score_count.get(uid, 0) >= CORRECT_SCORE_PICKS_PER_MATCH:
                continue
        elif match_rec_count.get(uid, 0) >= MAX_RECS_PER_MATCH:
            continue
        direction = _dir_key(rec)
        used_dirs = match_directions.get(uid, set())
        if direction in used_dirs:
            continue
        if _is_score:
            match_score_count[uid] = match_score_count.get(uid, 0) + 1
        else:
            match_rec_count[uid] = match_rec_count.get(uid, 0) + 1
        used_dirs.add(direction)
        match_directions[uid] = used_dirs
        final_recs.append(rec)

    # 市场多样性控制：每种市场最多占 MAX_DAILY_RECOMMENDATIONS 的 40%
    max_per_market = max(3, int(MAX_DAILY_RECOMMENDATIONS * 0.4))
    market_count = {}
    diversified = []
    overflow = []
    for rec in final_recs:
        mkt_key = rec["market"]  # total, team_total, spread, moneyline
        # team_total_home/team_total_away 合并计入同一个"team_total"多样性桶，
        # 否则主客队分开算各自40%配额，两个加起来能占掉全天80%的名额
        if mkt_key.startswith("team_total_"):
            mkt_key = "team_total"
        if market_count.get(mkt_key, 0) < max_per_market:
            diversified.append(rec)
            market_count[mkt_key] = market_count.get(mkt_key, 0) + 1
        else:
            overflow.append(rec)
    # 剩余名额用溢出的补
    remaining = MAX_DAILY_RECOMMENDATIONS - len(diversified)
    if remaining > 0 and overflow:
        diversified.extend(overflow[:remaining])
    final_recs = diversified
    # P5: 每日上限
    final_recs = final_recs[:MAX_DAILY_RECOMMENDATIONS]

    # 小球每日上限（条件解封期保守控制）
    under_count = 0
    capped = []
    for rec in final_recs:
        _rm = rec["market"].lower()
        if rec["outcome"] == "under" and (_rm in ("total", "team_total", "totals")
                                          or _rm.startswith("team_total_")):
            if under_count >= UNDER_MAX_DAILY:
                continue
            under_count += 1
        capped.append(rec)
    final_recs = capped

    recommendations = final_recs

    # ── 入库前最终清洗：拦截越界赔率 + 缺失盘口线 ──────────────────────────────
    # Bug修复(2026-07-18): consensus_odds 查询虽过滤了 1.75-3.50，但 best_odds
    # 取的是 unified_odds 单源最佳值(_best_val)，没二次过滤，导致离谱赔率(如530.0、
    # 美式转换溢出的1.0864)泄漏进推荐。同时 handicap 缺失的 total/spread 无法判定
    # 输赢。这里在写入前统一拦截。
    _pre_clean_n = len(recommendations)
    _cleaned_recs = []
    for _rc in recommendations:
        _bo = _rc.get("best_odds")
        _mk = (_rc.get("market") or "").lower()
        # 赔率范围检查（correct_score 比分赔率天然高，放宽到 50）
        _odds_max = 50.0 if _mk == "correct_score" else MAX_RECOMMEND_ODDS
        if _bo is None or _bo < MIN_RECOMMEND_ODDS or _bo > _odds_max:
            continue
        # 盘口线检查：total/spread/team_total 必须有 handicap
        if _mk in ("total", "spread", "team_total") and _rc.get("handicap") is None:
            continue
        _cleaned_recs.append(_rc)
    _dropped = _pre_clean_n - len(_cleaned_recs)
    if _dropped > 0:
        log.warning(f"  ⚠ 入库前清洗: 丢弃 {_dropped} 条越界/缺线推荐 (赔率范围或handicap缺失)")
    recommendations = _cleaned_recs

    # 策略收窄，2026-08-01重构：2026-07-19定下"只放行全场大小球大球+已转正的足球
    # 球队大小"这个范围后，market='total'&outcome='over'一直是硬编码`return True`
    # ——零验证、无条件放行，从未被任何转正函数检查过，是全系统审查覆盖最薄弱的
    # 一个市场，却是唯一真正在跑真钱的市场。2026-08-01真实数据审计发现它的足球
    # 方向已经连续4周单调衰减(周胜率62.5%→45.5%→35.7%→0%)但全历史ROI仍有+8.7%
    # (老样本稀释掉了近期衰减，见_validation_result()的"近期窗口"检验)。同时
    # 发现config.py MARKET_BIAS给独赢(moneyline)配置的静态加权、以及控制台"已通过
    # 固定加权放行...已进入正式候选池"的展示文案，从2026-07-19这条硬编码收窄生效
    # 起就已经是从未真正生效的假象(_in_scope()对moneyline一律return False)——
    # 展示层"已进入候选池"的claim和这里的真实gate对不上号。
    #
    # 现在统一改成：每种市场类型都走对应的_X_validation_status()动态判断(全部已
    # 升级为单尾95%置信区间+近期窗口双重检验)，不再有任何硬编码的无条件True/False。
    # config.py的MARKET_BIAS只影响get_model_probs()里hit_score计算环节的排序权重，
    # 不再能绕过这里的真实验证——是否进正式推荐单完全由真实结算数据的显著性决定。
    # 注意：按现在(2026-08-01)的真实数据，total/over(两个运动)和moneyline(全部
    # sport/outcome组合)都测不出显著性，这次改动生效后正式推荐单会暂时清零，直到
    # 某个市场重新积累出经得起双重检验的样本——这是预期内的结果，不是bug。
    _n_before_scope = len(recommendations)
    # Bug修复(2026-08-11)：被转正门槛拦下的候选要留下**反事实**记录。
    # 否则 _total_over/_correct_score/_corner 这三个读生产表的门槛会自锁：
    # 门槛关闭 → 不产推荐 → 无新结算样本 → "近30注"窗口永久冻结 → 门槛再也
    # 打不开（实测推荐单因此从07-19起近乎停产一个月）。把"本该下注但被拦"的
    # 这批记进影子桶(shadow_type='gated')，它们会被 21_auto_settle.py 的
    # settle_shadow_recommendations() 正常结算（该函数按 status='pending' 全收，
    # 不按 shadow_type 白名单），于是即使闸门关着，判断"该不该重新打开"所需的
    # 数据仍在持续积累——这正是需要的counterfactual，且不花一分钱。
    # 注意 over_shadow_bets 不能替代这份数据：它绕过 MARKET_BIAS 过滤，是更宽
    # 也更差的候选集(实测足球n=23/ROI-41.8%)，跟生产候选不是同一个population。
    def _in_scope(r):
        sport = (r.get("sport_code") or "").lower()
        market = r.get("market") or ""
        outcome = r.get("outcome") or ""
        if market == "total" and outcome == "over":
            return _total_over_validation_status(sport)["validated"]
        if (market == "team_total" or market.startswith("team_total")) and outcome == "over":
            _tt_sport = "football" if sport in ("football", "soccer") else sport
            return _team_total_validation_status(_tt_sport, "over")["validated"]
        if market == "moneyline":
            return _moneyline_validation_status(sport, outcome)["validated"]
        # Bug修复(2026-08-20)：比分玩法(correct_score)此前完全没有分支，无条件走到
        # 下面return False——_generate_correct_score_recs()每天正常产出候选(实测
        # 2026-08-20当天20条)，但100%在这里被拦截，不是因为_correct_score_validation_
        # status()判定不通过，是这个函数压根不认识market='correct_score'这个值。
        # 后果：①"比分预测单"🎯真实盘口推荐列永远显示0，跟_correct_score_validation_
        # status()是否验证通过完全无关；②即使这个市场未来真的积累出显著正ROI，也没有
        # 任何代码路径能让它"转正"进recommendations——promotion pathway从一开始就是
        # 断的。修复：跟其他三个已接线市场保持同一套模式，检查真实转正状态而不是硬编码
        # 拒绝。截至修复时全历史(n=128,ROI-30.6%)和gated桶里07-16模型重新校准后的新
        # 样本(n=14,ROI-100%)都远未达标，这条分支接上后短期内仍会返回False，不会立刻
        # 产生新推荐——修复的是"转正通道打通"，不是"今天变得能出票"。
        if market == "correct_score":
            return _correct_score_validation_status()["validated"]
        return False
    _gated_out = [r for r in recommendations if not _in_scope(r)]
    recommendations = [r for r in recommendations if _in_scope(r)]
    for _g in _gated_out:
        _gk = f"{_g.get('unified_id')}|{_g.get('market')}|{_g.get('outcome')}"
        _prev = shadow_multi["gated"].get(_gk)
        if _prev and _prev.get("hit_score", 0) >= (_g.get("hit_score") or 0):
            continue
        shadow_multi["gated"][_gk] = {
            "unified_id": _g.get("unified_id"), "sport_code": _g.get("sport_code"),
            "league_name": _g.get("league_name"), "home_team": _g.get("home_team"),
            "away_team": _g.get("away_team"), "kickoff_utc": _g.get("kickoff_utc"),
            "shadow_type": "gated", "market": _g.get("market"), "outcome": _g.get("outcome"),
            "handicap": _g.get("handicap"), "best_odds": _g.get("best_odds"),
            "model_prob": _g.get("model_prob"), "kelly_fraction": _g.get("kelly_fraction"),
            "hit_score": _g.get("hit_score"),
            "predicted_score": _g.get("predicted_score") or "-",
            "fetch_date": _g.get("fetch_date") or fetch_date,
        }
    log.info(f"  🎯 策略收窄(显著性+近期窗口双重检验): {len(recommendations)}/{_n_before_scope} 条"
             f"（被拦 {len(_gated_out)} 条已记入 shadow_type='gated' 反事实观察）")

    # 反着买人工批准转正(fade_manual)已挪到_generate_and_display_fade_manual()，
    # 由_run_one_date()在三个_generate_*_fade()调用之后再执行，见该函数docstring
    # 说明的执行顺序bug修复(2026-08-03)。

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    with engine.begin() as conn:
        _skip_v1 = _safe_delete_hit_recs(conn, fetch_date, "(formula_version='v1' OR formula_version IS NULL)", len(recommendations), "v1")
        for rec in recommendations:
            if (rec["unified_id"], rec["market"], rec["outcome"]) in _skip_v1:
                log.info(f"  🛡 FIX-016-3防护: v1 {rec['home_team']} vs {rec['away_team']} "
                         f"{rec['market']}/{rec['outcome']} 已有已结算行，跳过重插（防重复计账）")
                continue
            conn.execute(text("""
                INSERT INTO hit_recommendations
                (unified_id,sport_code,league_name,home_team,away_team,kickoff_utc,
                 market,outcome,best_odds,best_source,model_prob,implied_prob,
                 value_edge,kelly_fraction,hit_score,hit_score_v2,confidence,reason,
                 status,fetch_date,created_at,handicap,formula_version)
                VALUES
                (:unified_id,:sport_code,:league_name,:home_team,:away_team,:kickoff_utc,
                 :market,:outcome,:best_odds,:best_source,:model_prob,:implied_prob,
                 :value_edge,:kelly_fraction,:hit_score,:hit_score_v2,:confidence,:reason,
                 'pending',:fetch_date,:now,:handicap,'v1')
            """), {**rec, "now": now})

    log.info(f"  ✅ 推荐单生成(v1): {len(recommendations)} 条（门槛 ≥ {HIT_SCORE_GLOBAL_THRESHOLD}）")

    # ── V2公式推荐去重 + 写库 ──────────────────────────────────────────────────
    _v2_match_cnt  = {}
    _v2_match_dirs = {}
    _final_v2      = []
    for _rv in sorted(recommendations_v2, key=lambda x: -x["hit_score"]):
        _uid2 = _rv["unified_id"]
        if _v2_match_cnt.get(_uid2, 0) >= MAX_RECS_PER_MATCH:
            continue
        _dk2 = _dir_key(_rv)
        if _dk2 in _v2_match_dirs.get(_uid2, set()):
            continue
        _v2_match_cnt[_uid2] = _v2_match_cnt.get(_uid2, 0) + 1
        _v2_match_dirs.setdefault(_uid2, set()).add(_dk2)
        _final_v2.append(_rv)
    _final_v2 = _final_v2[:MAX_DAILY_RECOMMENDATIONS]
    # 策略收窄：同v1(全场大小球大球 + 已转正的足球球队大小)
    # 2026-09-06修复：此前只过滤、被拦的候选完全没有像V1的_gated_out那样记进
    # 反事实观察桶——V2从2026-07-19这次策略收窄起基本被锁死(formula_version='v2'
    # 最新一条停在07-18)，但从没有任何数据能验证"V2这套价值边际打分逻辑如果
    # 放开会不会有用"，现在补上，写进shadow_multi['gated_v2']（单独开一个
    # shadow_type，不跟V1的'gated'混在一起，见shadow_multi初始化处的说明）。
    _v2_gated_out = [r for r in _final_v2 if not _in_scope(r)]
    _final_v2 = [r for r in _final_v2 if _in_scope(r)]
    for _gv2 in _v2_gated_out:
        _gv2k = f"{_gv2.get('unified_id')}|{_gv2.get('market')}|{_gv2.get('outcome')}"
        _gv2_prev = shadow_multi["gated_v2"].get(_gv2k)
        if _gv2_prev and _gv2_prev.get("hit_score", 0) >= (_gv2.get("hit_score") or 0):
            continue
        shadow_multi["gated_v2"][_gv2k] = {
            "unified_id": _gv2.get("unified_id"), "sport_code": _gv2.get("sport_code"),
            "league_name": _gv2.get("league_name"), "home_team": _gv2.get("home_team"),
            "away_team": _gv2.get("away_team"), "kickoff_utc": _gv2.get("kickoff_utc"),
            "shadow_type": "gated_v2", "market": _gv2.get("market"), "outcome": _gv2.get("outcome"),
            "handicap": _gv2.get("handicap"), "best_odds": _gv2.get("best_odds"),
            "model_prob": _gv2.get("model_prob"), "kelly_fraction": _gv2.get("kelly_fraction"),
            "hit_score": _gv2.get("hit_score"),
            "predicted_score": _gv2.get("predicted_score") or "-",
            "fetch_date": _gv2.get("fetch_date") or fetch_date,
        }

    with engine.begin() as conn:
        _skip_v2 = _safe_delete_hit_recs(conn, fetch_date, "formula_version='v2'", len(_final_v2), "v2")
        for _rv in _final_v2:
            if (_rv["unified_id"], _rv["market"], _rv["outcome"]) in _skip_v2:
                log.info(f"  🛡 FIX-016-3防护: v2 {_rv['home_team']} vs {_rv['away_team']} "
                         f"{_rv['market']}/{_rv['outcome']} 已有已结算行，跳过重插（防重复计账）")
                continue
            conn.execute(text("""
                INSERT INTO hit_recommendations
                (unified_id,sport_code,league_name,home_team,away_team,kickoff_utc,
                 market,outcome,best_odds,best_source,model_prob,implied_prob,
                 value_edge,kelly_fraction,hit_score,hit_score_v2,confidence,reason,
                 status,fetch_date,created_at,handicap,formula_version)
                VALUES
                (:unified_id,:sport_code,:league_name,:home_team,:away_team,:kickoff_utc,
                 :market,:outcome,:best_odds,:best_source,:model_prob,:implied_prob,
                 :value_edge,:kelly_fraction,:hit_score,:hit_score_v2,:confidence,:reason,
                 'pending',:fetch_date,:now,:handicap,'v2')
            """), {**_rv, "now": now})
    log.info(f"  ✅ 推荐单生成(v2): {len(_final_v2)} 条（门槛 ≥ {HIT_SCORE_V2_THRESHOLD}）")

    # ─── 小球影子写库 ────────────────────────────────────────────────────────
    # 2026-08-02由"完整不截断"改回按hit_score降序Top7截断——用户明确要求全部
    # 正式推荐单/影子观察单统一走Top7规则，即使这会让_under_validation_status()
    # 以后验证时用到偏向模型高置信度的样本(2026-07-22曾为修复这个偏差改成过
    # 不截断，此次是用户已知情后的明确取舍，不是走回头路的疏忽)。
    if shadow_candidates:
        shadow_candidates = sorted(shadow_candidates, key=lambda x: -x["hit_score"])[:7]
        _now_shadow = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        with engine.begin() as _sc:
            _sc.execute(text("DELETE FROM under_shadow_bets WHERE fetch_date=:fd"), {"fd": fetch_date})
            for _sh in shadow_candidates:
                try:
                    _sc.execute(text("""
                        INSERT OR IGNORE INTO under_shadow_bets
                        (unified_id,sport_code,league_name,home_team,away_team,kickoff_utc,
                         market,handicap,best_odds,model_prob,kelly_fraction,hit_score,
                         status,fetch_date,created_at)
                        VALUES
                        (:unified_id,:sport_code,:league_name,:home_team,:away_team,:kickoff_utc,
                         :market,:handicap,:best_odds,:model_prob,:kelly_fraction,:hit_score,
                         'pending',:fetch_date,:now)
                    """), {**_sh, "now": _now_shadow})
                except Exception:
                    pass
        log.info(f"  📊 小球影子候选: {len(shadow_candidates)} 条 → under_shadow_bets")

    # ─── 大球影子写库（2026-08-02新增，见over_shadow_bets建表注释）─────────────
    if over_shadow_candidates:
        over_shadow_candidates = sorted(over_shadow_candidates, key=lambda x: -x["hit_score"])[:7]
        _now_over = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        with engine.begin() as _oc:
            _oc.execute(text("DELETE FROM over_shadow_bets WHERE fetch_date=:fd"), {"fd": fetch_date})
            for _ov in over_shadow_candidates:
                try:
                    _oc.execute(text("""
                        INSERT OR IGNORE INTO over_shadow_bets
                        (unified_id,sport_code,league_name,home_team,away_team,kickoff_utc,
                         market,handicap,best_odds,model_prob,kelly_fraction,hit_score,
                         status,fetch_date,created_at)
                        VALUES
                        (:unified_id,:sport_code,:league_name,:home_team,:away_team,:kickoff_utc,
                         :market,:handicap,:best_odds,:model_prob,:kelly_fraction,:hit_score,
                         'pending',:fetch_date,:now)
                    """), {**_ov, "now": _now_over})
                except Exception:
                    pass
        log.info(f"  📊 大球影子候选: {len(over_shadow_candidates)} 条 → over_shadow_bets")

    # ─── 球队大小样本写库（2026-08-02改回Top7截断，同上小球影子写库的说明）──────
    if team_total_shadow_full:
        team_total_shadow_full = sorted(team_total_shadow_full, key=lambda x: -x["hit_score"])[:7]
        _now_tt_full = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        with engine.begin() as _ttc:
            _ttc.execute(text("DELETE FROM team_total_shadow_full WHERE fetch_date=:fd"), {"fd": fetch_date})
            for _tt in team_total_shadow_full:
                try:
                    _ttc.execute(text("""
                        INSERT OR IGNORE INTO team_total_shadow_full
                        (unified_id,sport_code,league_name,home_team,away_team,kickoff_utc,
                         market,outcome,handicap,best_odds,model_prob,kelly_fraction,hit_score,
                         status,fetch_date,created_at)
                        VALUES
                        (:unified_id,:sport_code,:league_name,:home_team,:away_team,:kickoff_utc,
                         :market,:outcome,:handicap,:best_odds,:model_prob,:kelly_fraction,:hit_score,
                         'pending',:fetch_date,:now)
                    """), {**_tt, "now": _now_tt_full})
                except Exception:
                    pass
        log.info(f"  📊 球队大小完整候选: {len(team_total_shadow_full)} 条 → team_total_shadow_full")

    # ─── 独赢样本写库（2026-08-02改回Top7截断，同上小球影子写库的说明）──────────
    if moneyline_shadow_full:
        moneyline_shadow_full = sorted(moneyline_shadow_full, key=lambda x: -x["hit_score"])[:7]
        _now_ml_full = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        _ml_stopped = 0
        with engine.begin() as _mlc:
            _mlc.execute(text("DELETE FROM moneyline_shadow_full WHERE fetch_date=:fd"), {"fd": fetch_date})
            for _ml in moneyline_shadow_full:
                # FIX-007-3 影子桶瘦身：停写清单内的桶跳过（存量保留，见config.SHADOW_WRITE_STOP）
                if is_shadow_write_stopped("moneyline", _ml.get("sport_code"), _ml.get("outcome")):
                    _ml_stopped += 1
                    continue
                try:
                    _mlc.execute(text("""
                        INSERT OR IGNORE INTO moneyline_shadow_full
                        (unified_id,sport_code,league_name,home_team,away_team,kickoff_utc,
                         market,outcome,best_odds,model_prob,kelly_fraction,hit_score,
                         status,fetch_date,created_at)
                        VALUES
                        (:unified_id,:sport_code,:league_name,:home_team,:away_team,:kickoff_utc,
                         :market,:outcome,:best_odds,:model_prob,:kelly_fraction,:hit_score,
                         'pending',:fetch_date,:now)
                    """), {**_ml, "now": _now_ml_full})
                except Exception:
                    pass
        log.info(f"  📊 独赢完整候选: {len(moneyline_shadow_full) - _ml_stopped} 条 → moneyline_shadow_full")
        if _ml_stopped:
            log.info(f"  🛑 影子桶瘦身(FIX-007-3)：独赢桶停写 {_ml_stopped} 条(moneyline:basketball:away)")

    # ─── 其他市场影子写库（shadow_recommendations）────────────────────────────
    # Bug修复(2026-09-07)：原来"except Exception: pass"会把INSERT失败完全静默吞掉——
    # 2026-09-06真实发生过一次：日志打印"FotMob角球影子观察: 2条"，但这2条最终一条
    # 都没进shadow_recommendations表，排查时翻遍日志找不到任何Traceback/Error痕迹，
    # 才追到是这里吞的异常。"INSERT OR IGNORE"本身已经处理了唯一键冲突这种正常情况
    # (冲突时静默跳过，不会走到这个except分支)，所以任何真的落到这里的异常都是需要
    # 被看见的真实问题(字段类型不对/字符串拼出畸形unified_id等)，不应该被无声吞掉。
    # 只加日志，不改写库逻辑本身，行为完全不变，只是失败不再是哑巴亏。
    _total_shadow_written = 0
    _total_shadow_failed = 0
    _total_shadow_stopped = 0
    _shadow_stop_detail = {}
    _now_multi = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    with engine.begin() as _msc:
        _msc.execute(text("DELETE FROM shadow_recommendations WHERE fetch_date=:fd"), {"fd": fetch_date})
        for _stype, _sdict in shadow_multi.items():
            _top10 = sorted(_sdict.values(), key=lambda x: -x["hit_score"])[:7]  # 2026-08-02: Top10→Top7
            for _sm in _top10:
                # FIX-007-3 影子桶瘦身：n<50且ci_lower<0的桶停写（存量保留，
                # 清单见config.SHADOW_WRITE_STOP，判据见FIX_REPORT.md附录B）
                if is_shadow_write_stopped(_stype, _sm.get("sport_code"), _sm.get("outcome")):
                    _total_shadow_stopped += 1
                    _shadow_stop_detail[_stype] = _shadow_stop_detail.get(_stype, 0) + 1
                    continue
                try:
                    _msc.execute(text("""
                        INSERT OR IGNORE INTO shadow_recommendations
                        (unified_id,sport_code,league_name,home_team,away_team,kickoff_utc,
                         shadow_type,market,outcome,handicap,best_odds,model_prob,
                         kelly_fraction,hit_score,predicted_score,fetch_date,created_at)
                        VALUES
                        (:unified_id,:sport_code,:league_name,:home_team,:away_team,:kickoff_utc,
                         :shadow_type,:market,:outcome,:handicap,:best_odds,:model_prob,
                         :kelly_fraction,:hit_score,:predicted_score,:fetch_date,:now)
                    """), {**_sm, "now": _now_multi})
                    _total_shadow_written += 1
                except Exception as _shadow_write_err:
                    _total_shadow_failed += 1
                    log.warning(f"  ⚠️ 影子候选写库失败(shadow_type={_stype}, "
                               f"unified_id={_sm.get('unified_id')}): {_shadow_write_err}")
    if _total_shadow_written:
        log.info(f"  📊 其他市场影子: {_total_shadow_written} 条 → shadow_recommendations")
    if _total_shadow_failed:
        log.warning(f"  ⚠️ 其他市场影子写库失败 {_total_shadow_failed} 条，详见上方各条warning")
    if _total_shadow_stopped:
        log.info(f"  🛑 影子桶瘦身(FIX-007-3)：停写 {_total_shadow_stopped} 条，"
                 f"分桶: {_shadow_stop_detail}")

    # ─── P5: 自动生成投注分配（单注 + 串关） ──────────────────────────────────
    plan_lines, _ = _generate_bet_plan(recommendations, fetch_date)

    def _league_zh(name: str, sport: str = "") -> str:
        # Bug修复(2026-07-19)：_LEAGUE_ZH 用 substring 匹配（如"Argentina - Primera"
        # 命中"Argentina - Primera Division Women"），女子联赛会被静默匹配成同前缀的
        # 男子联赛译名，丢失性别信息——用户核对投注单时会去男子赛程表里找，永远找不到。
        # 源联赛名含"women"但译名里没有"女"字样时，补上"(女)"后缀。
        _is_women = "women" in name.lower()
        if sport and sport.lower() in ("basketball", "basket"):
            # Bug修复(2026-08-02)："LEB"(西班牙篮球乙级缩写)是纯substring匹配，
            # 会命中"Lebanon"/"Lebanese"里的"leb"（如黎巴嫩篮球联赛Sagesse vs
            # Al Riyadi被误译成"西班牙篮球乙级"），跟上面2026-07-19修的女子联赛
            # 前缀撞车是同一类bug。显式排除黎巴嫩，不让"LEB"关键字命中它。
            _is_lebanon = "lebanon" in name.lower() or "lebanese" in name.lower()
            _bball = [
                ("Serie B", "意大利篮球乙级"), ("Serie A", "意大利篮球甲级"),
                ("Liga EBA", "西班牙篮球乙级"), ("LEB", "西班牙篮球乙级"),
            ]
            for kw, zh in _bball:
                if kw == "LEB" and _is_lebanon:
                    continue
                if kw.lower() in name.lower():
                    return zh if not _is_women or "女" in zh else zh + "(女)"
        for keyword, zh in _LEAGUE_ZH:
            if keyword == "Serbia - Super" and (sport or "").lower() not in ("basketball", "basket"):
                continue
            if keyword.lower() in name.lower():
                return zh if not _is_women or "女" in zh else zh + "(女)"
        return name

    def _fmt_time(kickoff_utc: str) -> str:
        try:
            from datetime import timezone, timedelta
            dt = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
            # kickoff_utc若不带'Z'/偏移量(如pinnacle_corner_odds存的裸字符串)会解析成
            # naive datetime，此时astimezone()会把它当成"已经是系统本地时区"直接贴标签、
            # 不做真正的时间平移——本机系统时区恰好是北京时间(+8)，会导致UTC时间被
            # 误当成已经是北京时间直接显示，差8小时(2026-07-26发现，FotMob角球影子
            # 观察单把12:00/14:30这些UTC时刻直接显示成北京时间，应为20:00/22:30)。
            # 必须显式声明naive datetime是UTC，再转换到北京时间。
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            bj = dt.astimezone(timezone(timedelta(hours=8)))
            return bj.strftime("%m月%d日%H:%M")
        except Exception:
            return "--月--日--:--"

    from team_zh import team_zh as _team_zh

    def _tw(name: str, width: int) -> str:
        """截断中文名到指定显示宽度（中文字符宽度=2）"""
        result, w = "", 0
        for ch in name:
            cw = 2 if ord(ch) > 127 else 1
            if w + cw > width:
                break
            result += ch
            w += cw
        return result + " " * (width - w)

    W = 143
    lines: list[str] = []
    lines.append("\n" + "=" * W)
    lines.append(f"  📋 今日投注推荐单  [{fetch_date}]  （北京时间）")
    lines.append(f"  📐 概率口径：p融合 = 0.50×P庄家 + 0.30×P泊松 + 0.20×P_ELO  |  K值 = (p×赔率-1)/(赔率-1)×0.25（1/4 Kelly）  |  比分：泊松最可能比分")
    lines.append("=" * W)
    # 标准表头（与示例完全对齐）
    lines.append(f"  {'开赛时间':<12} {'联赛':<14} {'主队':<14}{'客队':<14} {'市场':<6} {'方向':<10} {'赔率':<6} {'p融合':<7} {'K₁/₄':<7} {'命中分':<8} {'比分预测'}")
    lines.append("-" * W)
    # 比分玩法(correct_score) 转正门槛：已结算样本量+ROI达标（config.py 的
    # CORRECT_SCORE_VALIDATION_MIN_SAMPLES/MIN_ROI）才进这张主推荐单，
    # 没达标之前只在"足球比分预测单"区块展示+结算统计，见下方 _score_sorted 循环
    # 注意：反着买人工批准转正(fade_manual)的行不在这里合并进_main_slip_recs——
    # 它读的basketball_moneyline_fade_recs/basketball_under_fade_recs要靠
    # _generate_basketball_*_fade()生成，而后者在_run_one_date()里排在
    # generate_recommendations()(本函数)**之后**调用，此时读到的必然是上一轮
    # 运行的旧数据(2026-08-03发现：跨天时上一轮数据是空的，导致fade_manual
    # 完全消失，跟_display_parallel_lines()此前的执行顺序bug是同一类问题)。
    # 已改为_generate_and_display_fade_manual()独立处理，在_run_one_date()里
    # 三个_generate_*调用之后运行，见该函数说明。
    _cs_status = _correct_score_validation_status()
    if _cs_status["validated"]:
        _main_slip_recs = recommendations
    else:
        _main_slip_recs = [r for r in recommendations if r["market"] != "correct_score"]
    for rec in _main_slip_recs[:20]:
        t          = _fmt_time(rec.get("kickoff_utc") or "")
        league_zh  = _tw(_league_zh(rec["league_name"], rec.get("sport_code", "")), 14)
        home       = _tw(f"[主]{_team_zh(rec['home_team'])}", 14)
        away       = _tw(f"[客]{_team_zh(rec['away_team'])}", 14)
        market_zh  = _MARKET_ZH.get(rec["market"],  rec["market"])
        # corner market: outcome="corner_over_9_5" → "大球9.5"
        if rec["outcome"].startswith("corner_"):
            _cparts = rec["outcome"].split("_", 2)
            if len(_cparts) == 3:
                _dir_zh = "大球" if _cparts[1] == "over" else ("小球" if _cparts[1] == "under" else ("主" if _cparts[1] == "home" else "客"))
                outcome_zh = f"{_dir_zh}{_cparts[2].replace('_', '.')}"
            else:
                outcome_zh = rec["outcome"]
        else:
            outcome_zh = _OUTCOME_ZH.get(rec["outcome"], rec["outcome"])
            hc = rec.get("handicap")
            if hc is not None:
                outcome_zh = f"{outcome_zh}{hc}"
        p_str      = f"{rec['model_prob']:.3f}"
        k_str      = f"{rec['kelly_fraction']:.4f}"
        score_str  = rec.get("predicted_score") or "-"
        # 开赛时间用 _tw 修正中文字符宽度（月/日各占2格）
        t_padded   = _tw(t, 14)
        lines.append(f"  {t_padded}{league_zh}{home}{away} "
                     f"{market_zh:<6} {outcome_zh:<10} {rec['best_odds']:<6.2f} {p_str:<7} {k_str:<7} {rec['hit_score']:<8.3f} {score_str}")
    lines.append("=" * W)
    lines.append(f"  共 {len(_main_slip_recs)} 条推荐（门槛 ≥ {HIT_SCORE_GLOBAL_THRESHOLD}，每场 ≤ {MAX_RECS_PER_MATCH} 条，日限 {MAX_DAILY_RECOMMENDATIONS}）"
                 + (f"  ｜另有比分玩法见下方比分预测单" if any(r["market"] == "correct_score" for r in recommendations) else ""))

    # 反着买详细说明区块已挪到_generate_and_display_fade_manual()，理由同上。

    # 平行线展示(legacy_team_total_under_recs)已挪到_display_parallel_lines()，
    # 由_run_one_date()在_generate_legacy_team_total_under()写完数据之后再调用，
    # 见该函数docstring说明的执行顺序bug修复(2026-08-02)。

    for ln in lines:
        print(ln)

    # ─── 小球候选观察单（独立输出，不含在正式推荐单中）──────────────────────
    _SW = 100  # 影子观察单宽度（在桌面保存区块也会用到）
    if shadow_candidates:
        _sh_sorted = sorted(shadow_candidates, key=lambda x: -x["hit_score"])
        shadow_lines = [
            "",
            "─" * _SW,
            "  📊  小球候选观察单  [仅数据追踪，未正式启用]",
            "─" * _SW,
            f"  {'序':>3}  {'开赛时间':<12} {'主队':<14} {'客队':<14} {'玩法':<6} {'线':<5} {'赔率':<6} {'p融合':<7} {'K₁/₄':<7} {'命中分':<8}",
            "─" * _SW,
        ]
        for _si, _sh in enumerate(_sh_sorted, 1):
            _t = _fmt_time(_sh["kickoff_utc"])
            _hc_str = f"{_sh['handicap']:.1f}" if _sh["handicap"] is not None else "-"
            # Bug修复(2026-09-01)：跟shadow_multi那几处同一类问题——直接截取
            # home_team/away_team原始值，从没调用_team_zh()，小球候选观察单
            # 队名一直是英文。这个桶没有联赛列，只补队名翻译。
            _home_short = _tw(_team_zh(_sh["home_team"])[:10], 14)
            _away_short = _tw(_team_zh(_sh["away_team"])[:10], 14)
            shadow_lines.append(
                f"  {_si:>3}.  {_t:<12} {_home_short}{_away_short}"
                f" {'小球':<6} {_hc_str:<5} {_sh['best_odds']:<6.2f}"
                f" {_sh['model_prob']:<7.3f} {_sh['kelly_fraction']:<7.4f} {_sh['hit_score']:<8.3f}"
            )
        shadow_lines.append("─" * _SW)
        shadow_lines.append(f"  共 {len(_sh_sorted)} 条候选  命中率统计见 under_shadow_bets 表（自动结算后查看）")
        for _sp_code in ("football", "basketball"):
            _u_stat = _under_validation_status(_sp_code)
            _sp_zh = "足球" if _sp_code == "football" else "篮球"
            if _u_stat["validated"]:
                shadow_lines.append(f"  ✅ {_sp_zh}小球已转正（已结算{_u_stat['n']}场，胜率{_u_stat['win_rate']:.1%}，"
                                    f"平注ROI{_u_stat['roi']:+.1%}）——本轮起进入主推荐单")
            else:
                _roi_txt = f"{_u_stat['roi']:+.1%}" if _u_stat["roi"] is not None else "暂无"
                shadow_lines.append(f"  ⏳ {_sp_zh}小球尚未转正（已结算{_u_stat['n']}/{UNDER_VALIDATION_MIN_SAMPLES}场，"
                                    f"平注ROI{_roi_txt}，需≥{UNDER_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
        for _sl in shadow_lines:
            print(_sl)

    # ─── 大球候选观察单（独立输出，不含在正式推荐单中，2026-08-02新增）──────────
    # 转正判断复用_total_over_validation_status()——该函数查hit_recommendations里
    # 07-19前"total/over硬编码放行"时期的真实结算历史，population本身就对，不受
    # over_shadow_bets这里Top7截断影响，不需要另建一套validation函数。
    over_shadow_lines: list[str] = []
    if over_shadow_candidates:
        _ov_sorted = sorted(over_shadow_candidates, key=lambda x: -x["hit_score"])
        over_shadow_lines = [
            "",
            "─" * _SW,
            "  📊  大球候选观察单  [仅数据追踪，未正式启用]",
            "─" * _SW,
            f"  {'序':>3}  {'开赛时间':<12} {'主队':<14} {'客队':<14} {'玩法':<6} {'线':<5} {'赔率':<6} {'p融合':<7} {'K₁/₄':<7} {'命中分':<8}",
            "─" * _SW,
        ]
        for _oi, _ov in enumerate(_ov_sorted, 1):
            _to = _fmt_time(_ov["kickoff_utc"])
            _hco_str = f"{_ov['handicap']:.1f}" if _ov["handicap"] is not None else "-"
            # Bug修复(2026-09-01)：同上，大球候选观察单也补队名翻译
            _home_o = _tw(_team_zh(_ov["home_team"])[:10], 14)
            _away_o = _tw(_team_zh(_ov["away_team"])[:10], 14)
            over_shadow_lines.append(
                f"  {_oi:>3}.  {_to:<12} {_home_o}{_away_o}"
                f" {'大球':<6} {_hco_str:<5} {_ov['best_odds']:<6.2f}"
                f" {_ov['model_prob']:<7.3f} {_ov['kelly_fraction']:<7.4f} {_ov['hit_score']:<8.3f}"
            )
        over_shadow_lines.append("─" * _SW)
        over_shadow_lines.append(f"  共 {len(_ov_sorted)} 条候选  命中率统计见 over_shadow_bets 表（自动结算后查看）")
        for _sp_code in ("football", "basketball"):
            _o_stat = _total_over_validation_status(_sp_code)
            _sp_zh = "足球" if _sp_code == "football" else "篮球"
            if _o_stat["validated"]:
                over_shadow_lines.append(f"  ✅ {_sp_zh}大球已转正（已结算{_o_stat['n']}场，胜率{_o_stat['win_rate']:.1%}，"
                                          f"平注ROI{_o_stat['roi']:+.1%}）——本轮起进入主推荐单")
            else:
                _roi_txt_o = f"{_o_stat['roi']:+.1%}" if _o_stat["roi"] is not None else "暂无"
                over_shadow_lines.append(f"  ⏳ {_sp_zh}大球尚未转正（已结算{_o_stat['n']}/{UNDER_VALIDATION_MIN_SAMPLES}场，"
                                          f"平注ROI{_roi_txt_o}，需≥{UNDER_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
        for _osl in over_shadow_lines:
            print(_osl)

    # ─── 其他市场影子观察单（独赢/让分/胜平负） ──────────────────────────────
    _SHADOW_TYPE_ZH = {"moneyline": "独赢", "spread": "让分", "1x2": "胜平负",
                       "lstm_moneyline": "LSTM独赢", "lstm_1x2": "LSTM胜平负",
                       "lstm_spread": "LSTM让球", "team_total": "球队大小",
                       "fotmob_1x2": "FotMob胜平负",
                       "fotmob_totals": "FotMob大小球", "fotmob_team_total": "FotMob球队大小",
                       "fotmob_spread": "FotMob让球", "fotmob_corner": "FotMob角球",
                       "qiety_h2h": "企鹅交锋", "injury_impact": "伤停信号", "htft": "半全场",
                       "htft_nofilter": "半全场(无联赛过滤平行线)"}
    _SW2 = 110
    # Bug修复(2026-08-31)：htft桶自2026-07-24创建以来就正确写进了shadow_multi["htft"]
    # （见上方precomputed_htft_shadow注入逻辑），但这个打印/保存投注单txt的遍历元组
    # 一直没把"htft"加进来——跟fotmob_corner/qiety_h2h/injury_impact当年各自的接入
    # 提交对比，htft是唯一一个"数据算好了、传进来了，却从没进这个循环"的桶，导致
    # 半全场候选每天都在正常生成(shadow_recommendations表里能查到)，但用户从没在
    # 控制台或D:\lucky保存的投注单里见过它，属于从创建起就存在的结构性缺口，不是
    # 近期回归。
    _TOTALS_FAMILY_SPLIT = {"team_total", "fotmob_totals", "fotmob_team_total"}
    for _stype in ("moneyline", "spread", "1x2", "lstm_moneyline", "lstm_1x2", "lstm_spread", "team_total",
                   "fotmob_1x2", "fotmob_totals", "fotmob_team_total", "fotmob_spread", "fotmob_corner",
                   "qiety_h2h", "injury_impact", "htft", "htft_nofilter"):
        _type_zh = _SHADOW_TYPE_ZH.get(_stype, _stype)
        if _stype in _TOTALS_FAMILY_SPLIT:
            # 2026-09-06：大小球/球队大小的大球、小球两个方向历史edge差异很大（见
            # _fotmob_totals_validation_status()等函数的outcome拆分说明），混在一张
            # 按hit_score排序的Top7表里会导致表现更好的方向被另一方向的候选挤掉
            # 展示名额——改成大球/小球各自独立一张Top7表，互不占用对方名额。
            _all_cands = list(shadow_multi.get(_stype, {}).values())
            if not _all_cands:
                continue
            _smlines = []
            for _oc_key, _oc_zh in (("over", "大球"), ("under", "小球")):
                _oc_list = sorted([c for c in _all_cands if c.get("outcome") == _oc_key],
                                   key=lambda x: -x["hit_score"])[:7]
                if not _oc_list:
                    continue
                _smlines += [
                    "",
                    "─" * _SW2,
                    f"  📊  {_type_zh}/{_oc_zh}候选观察单  [仅数据追踪，未正式启用]",
                    "─" * _SW2,
                    f"  {'序':>3}  {'开赛时间':<12} {'联赛':<14} {'主队':<14}{'客队':<14} {'市场':<8} {'方向':<10} {'赔率':<6} {'p融合':<7} {'K₁/₄':<7} {'命中分':<8} {'比分预测'}",
                    "─" * _SW2,
                ]
                for _si2, _sm2 in enumerate(_oc_list, 1):
                    _t2       = _fmt_time(_sm2["kickoff_utc"])
                    _lg2      = _tw(_league_zh(_sm2["league_name"], _sm2.get("sport_code", "")), 14)
                    _home2    = _tw(f"[主]{_team_zh(_sm2['home_team'])}", 14)
                    _away2    = _tw(f"[客]{_team_zh(_sm2['away_team'])}", 14)
                    _mkt2_zh  = _MARKET_ZH.get(_sm2["market"], _sm2["market"])
                    _out2     = _OUTCOME_ZH.get(_sm2["outcome"], _sm2["outcome"])
                    _hc2      = _sm2.get("handicap")
                    if _hc2 is not None:
                        _out2 = f"{_out2}{_hc2}"
                    _score2   = _sm2.get("predicted_score") or "-"
                    _smlines.append(
                        f"  {_si2:>3}.  {_tw(_t2, 14)}{_lg2}{_home2}{_away2}"
                        f" {_mkt2_zh:<8} {_out2:<10} {_sm2['best_odds']:<6.2f}"
                        f" {_sm2['model_prob']:<7.3f} {_sm2['kelly_fraction']:<7.4f}"
                        f" {_sm2['hit_score']:<8.3f} {_score2}"
                    )
                _smlines.append("─" * _SW2)
                _smlines.append(f"  共 {len(_oc_list)} 条候选  命中率统计见 shadow_recommendations 表（自动结算后查看）")
        else:
            _slist_top = sorted(shadow_multi.get(_stype, {}).values(), key=lambda x: -x["hit_score"])[:7]  # 2026-08-02: Top10→Top7
            if not _slist_top:
                continue
            _smlines = [
                "",
                "─" * _SW2,
                f"  📊  {_type_zh}影子观察单  [仅数据追踪，未正式启用]",
                "─" * _SW2,
                f"  {'序':>3}  {'开赛时间':<12} {'联赛':<14} {'主队':<14}{'客队':<14} {'市场':<8} {'方向':<10} {'赔率':<6} {'p融合':<7} {'K₁/₄':<7} {'命中分':<8} {'比分预测'}",
                "─" * _SW2,
            ]
            for _si2, _sm2 in enumerate(_slist_top, 1):
                _t2       = _fmt_time(_sm2["kickoff_utc"])
                _lg2      = _tw(_league_zh(_sm2["league_name"], _sm2.get("sport_code", "")), 14)
                _home2    = _tw(f"[主]{_team_zh(_sm2['home_team'])}", 14)
                _away2    = _tw(f"[客]{_team_zh(_sm2['away_team'])}", 14)
                _mkt2_zh  = _MARKET_ZH.get(_sm2["market"], _sm2["market"])
                _out2     = _OUTCOME_ZH.get(_sm2["outcome"], _sm2["outcome"])
                _hc2      = _sm2.get("handicap")
                if _hc2 is not None:
                    _out2 = f"{_out2}{_hc2}"
                _score2   = _sm2.get("predicted_score") or "-"
                _smlines.append(
                    f"  {_si2:>3}.  {_tw(_t2, 14)}{_lg2}{_home2}{_away2}"
                    f" {_mkt2_zh:<8} {_out2:<10} {_sm2['best_odds']:<6.2f}"
                    f" {_sm2['model_prob']:<7.3f} {_sm2['kelly_fraction']:<7.4f}"
                    f" {_sm2['hit_score']:<8.3f} {_score2}"
                )
            _smlines.append("─" * _SW2)
            _smlines.append(f"  共 {len(_slist_top)} 条候选  命中率统计见 shadow_recommendations 表（自动结算后查看）")
        if _stype in ("moneyline", "1x2"):
            # 2026-07-24起按(sport,outcome)分开判断/展示——复盘发现按sport聚合会让
            # 表现分裂的两个方向互相搭车(篮球主胜-24.9% vs 客胜+74.6%)，见
            # _moneyline_validation_status()说明。用户已确认篮球主胜降级为仅观察。
            _ml_sport = "football" if _stype == "1x2" else "basketball"
            _ml_outcomes = [("home", "主胜"), ("away", "客胜"), ("draw", "平局")] if _stype == "1x2" \
                else [("home", "主胜"), ("away", "客胜")]
            _ml_zh_base = "足球胜平负" if _stype == "1x2" else "篮球独赢"
            for _ml_oc, _ml_oc_zh in _ml_outcomes:
                _ml_zh = f"{_ml_zh_base}/{_ml_oc_zh}"
                # Bug修复(2026-08-01)：原来这段先查get_market_bias()是否有非0静态倍率，
                # 有就直接展示"已通过固定加权放行...已进入正式候选池"、跳过真实转正
                # 判断——但_in_scope()(真正决定进不进hit_recommendations的gate)从
                # 2026-07-19"策略收窄"起就只认_moneyline_validation_status()的结果，
                # MARKET_BIAS静态倍率只影响hit_score排序，从未真正让moneyline绕过
                # _in_scope()。这段展示文案从2026-07-24起就在撒谎(声称"已进入候选池"
                # 但实际每次都被_in_scope()挡掉，hit_recommendations里moneyline最新
                # 记录停在2026-07-18，7月24日后再没有一条)。现在统一只展示真实转正
                # 状态，MARKET_BIAS倍率只作为附注信息展示，不再影响判断逻辑。
                _ml_bias, _ = get_market_bias(_ml_sport, "moneyline", _ml_oc)
                _ml_stat = _moneyline_validation_status(_ml_sport, _ml_oc)
                _bias_note = f"（另：config.py配置了{_ml_bias:.2f}x静态加权，仅影响排序不影响是否进正式单）" if _ml_bias and _ml_bias != 0.0 else ""
                if _ml_stat["validated"]:
                    _smlines.append(f"  ✅ {_ml_zh}已转正（已结算{_ml_stat['n']}场，胜率{_ml_stat['win_rate']:.1%}，"
                                     f"平注ROI{_ml_stat['roi']:+.1%}，近{_ml_stat['recent_n']}场ROI{_ml_stat['recent_roi']:+.1%}）"
                                     f"——本轮起进入主推荐单{_bias_note}")
                else:
                    _roi_txt2 = f"{_ml_stat['roi']:+.1%}" if _ml_stat["roi"] is not None else "暂无"
                    _smlines.append(f"  ⏳ {_ml_zh}尚未转正（已结算{_ml_stat['n']}/{MONEYLINE_VALIDATION_MIN_SAMPLES}场，"
                                     f"平注ROI{_roi_txt2}，需≥{MONEYLINE_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
        elif _stype in ("lstm_moneyline", "lstm_1x2"):
            # LSTM(EMA+AR1)信号shadow桶：现有model_prob和LSTM校准概率按0.85/0.15融合
            # 后单独结算追踪，达标转正的是这个"融合后"权重，不是LSTM信号单独的表现
            _lz_sport = "football" if _stype == "lstm_1x2" else "basketball"
            _lz_zh = "LSTM足球胜平负" if _stype == "lstm_1x2" else "LSTM篮球独赢"
            _lz_stat = _lstm_validation_status(_lz_sport)
            if _lz_stat["validated"]:
                _smlines.append(f"  ✅ {_lz_zh}已转正（已结算{_lz_stat['n']}场，胜率{_lz_stat['win_rate']:.1%}，"
                                 f"平注ROI{_lz_stat['roi']:+.1%}）——建议并入p_fusion正式启用")
            else:
                _roi_txt3 = f"{_lz_stat['roi']:+.1%}" if _lz_stat["roi"] is not None else "暂无"
                _smlines.append(f"  ⏳ {_lz_zh}尚未转正（已结算{_lz_stat['n']}/{LSTM_VALIDATION_MIN_SAMPLES}场，"
                                 f"平注ROI{_roi_txt3}，需≥{LSTM_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
        elif _stype == "injury_impact":
            # 伤停信号足球/篮球混在同一个"injury_impact"桶里(不像LSTM拆两个shadow_type)，
            # 展示时按sport分别查转正状态。
            for _inj_sport, _inj_zh in (("football", "伤停信号/足球"), ("basketball", "伤停信号/篮球")):
                _inj_stat = _injury_validation_status(_inj_sport)
                if _inj_stat["validated"]:
                    _smlines.append(f"  ✅ {_inj_zh}已转正（已结算{_inj_stat['n']}场，胜率{_inj_stat['win_rate']:.1%}，"
                                     f"平注ROI{_inj_stat['roi']:+.1%}）——建议并入p_fusion正式启用")
                else:
                    _roi_txt_inj = f"{_inj_stat['roi']:+.1%}" if _inj_stat["roi"] is not None else "暂无"
                    _smlines.append(f"  ⏳ {_inj_zh}尚未转正（已结算{_inj_stat['n']}/{LSTM_VALIDATION_MIN_SAMPLES}场，"
                                     f"平注ROI{_roi_txt_inj}，需≥{LSTM_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
        elif _stype == "team_total":
            # 球队大小不像独赢那样按shadow_type分football/basketball两个桶（这里两种
            # 运动的候选混在同一个"team_total"桶里展示）。2026-07-19用户拍板：只有
            # 足球球队大小的"大球"方向能转正进正式单，小球方向和篮球继续观察——
            # 转正判断按(sport,outcome)分开打印，不再只按sport笼统汇报。
            _tt_fo = _team_total_validation_status("football", "over")
            if _tt_fo["validated"]:
                _smlines.append(f"  ✅ 足球球队大小/大球已转正（已结算{_tt_fo['n']}场，胜率{_tt_fo['win_rate']:.1%}，"
                                 f"平注ROI{_tt_fo['roi']:+.1%}）——本轮起进入主推荐单")
            else:
                _roi_txt4 = f"{_tt_fo['roi']:+.1%}" if _tt_fo["roi"] is not None else "暂无"
                _smlines.append(f"  ⏳ 足球球队大小/大球尚未转正（已结算{_tt_fo['n']}/{TEAM_TOTAL_VALIDATION_MIN_SAMPLES}场，"
                                 f"平注ROI{_roi_txt4}，需≥{TEAM_TOTAL_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
            _tt_fu = _team_total_validation_status("football", "under")
            _roi_txt5 = f"{_tt_fu['roi']:+.1%}" if _tt_fu["roi"] is not None else "暂无"
            _smlines.append(f"  ⏳ 足球球队大小/小球不参与转正（用户明确要求只放行大球方向，"
                             f"已结算{_tt_fu['n']}场，平注ROI{_roi_txt5}，仅供参考）——继续仅观察+结算")
            _tt_b = _team_total_validation_status("basketball")
            _roi_txt6 = f"{_tt_b['roi']:+.1%}" if _tt_b["roi"] is not None else "暂无"
            _smlines.append(f"  ⏳ 篮球球队大小尚未转正（已结算{_tt_b['n']}/{TEAM_TOTAL_VALIDATION_MIN_SAMPLES}场，"
                             f"平注ROI{_roi_txt6}，需≥{TEAM_TOTAL_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
        elif _stype == "fotmob_1x2":
            # FotMob xG/射正信号shadow桶：现有model_prob和FotMob信号按0.85/0.15融合
            # 后单独结算追踪，达标转正的是这个"融合后"权重，不是FotMob信号单独的表现
            _fm_stat = _fotmob_validation_status()
            if _fm_stat["validated"]:
                _smlines.append(f"  ✅ FotMob胜平负已转正（已结算{_fm_stat['n']}场，胜率{_fm_stat['win_rate']:.1%}，"
                                 f"平注ROI{_fm_stat['roi']:+.1%}）——建议并入p_fusion正式启用")
            else:
                _roi_txt7 = f"{_fm_stat['roi']:+.1%}" if _fm_stat["roi"] is not None else "暂无"
                _smlines.append(f"  ⏳ FotMob胜平负尚未转正（已结算{_fm_stat['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                 f"平注ROI{_roi_txt7}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
        elif _stype == "fotmob_totals":
            # 2026-09-06按outcome拆分展示（over/under合并统计会互相掩盖，见
            # _fotmob_totals_validation_status()说明）——under单独实测已经非常
            # 接近转正门槛，over单独明显是负edge，不再只打印一条合并汇总。
            _fmt_o = _fotmob_totals_validation_status("over")
            if _fmt_o["validated"]:
                _smlines.append(f"  ✅ FotMob大小球/大球已转正（已结算{_fmt_o['n']}场，胜率{_fmt_o['win_rate']:.1%}，"
                                 f"平注ROI{_fmt_o['roi']:+.1%}）——建议并入p_fusion正式启用")
            else:
                _roi_txt8o = f"{_fmt_o['roi']:+.1%}" if _fmt_o["roi"] is not None else "暂无"
                _smlines.append(f"  ⏳ FotMob大小球/大球尚未转正（已结算{_fmt_o['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                 f"平注ROI{_roi_txt8o}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
            _fmt_u = _fotmob_totals_validation_status("under")
            if _fmt_u["validated"]:
                _smlines.append(f"  ✅ FotMob大小球/小球已转正（已结算{_fmt_u['n']}场，胜率{_fmt_u['win_rate']:.1%}，"
                                 f"平注ROI{_fmt_u['roi']:+.1%}）——建议并入p_fusion正式启用")
            else:
                _roi_txt8u = f"{_fmt_u['roi']:+.1%}" if _fmt_u["roi"] is not None else "暂无"
                _ci_txt8u = f"，ci_lower={_fmt_u['ci_lower']:+.1%}" if _fmt_u["ci_lower"] is not None else ""
                _smlines.append(f"  ⏳ FotMob大小球/小球尚未转正（已结算{_fmt_u['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                 f"平注ROI{_roi_txt8u}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}{_ci_txt8u}）——继续仅观察+结算")
        elif _stype == "fotmob_team_total":
            # 2026-09-06按outcome拆分展示，理由同fotmob_totals同名分支
            _fmtt_o = _fotmob_team_total_validation_status("over")
            if _fmtt_o["validated"]:
                _smlines.append(f"  ✅ FotMob球队大小/大球已转正（已结算{_fmtt_o['n']}场，胜率{_fmtt_o['win_rate']:.1%}，"
                                 f"平注ROI{_fmtt_o['roi']:+.1%}）——建议并入p_fusion正式启用")
            else:
                _roi_txt9o = f"{_fmtt_o['roi']:+.1%}" if _fmtt_o["roi"] is not None else "暂无"
                _smlines.append(f"  ⏳ FotMob球队大小/大球尚未转正（已结算{_fmtt_o['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                 f"平注ROI{_roi_txt9o}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
            _fmtt_u = _fotmob_team_total_validation_status("under")
            if _fmtt_u["validated"]:
                _smlines.append(f"  ✅ FotMob球队大小/小球已转正（已结算{_fmtt_u['n']}场，胜率{_fmtt_u['win_rate']:.1%}，"
                                 f"平注ROI{_fmtt_u['roi']:+.1%}）——建议并入p_fusion正式启用")
            else:
                _roi_txt9u = f"{_fmtt_u['roi']:+.1%}" if _fmtt_u["roi"] is not None else "暂无"
                _ci_txt9u = f"，ci_lower={_fmtt_u['ci_lower']:+.1%}" if _fmtt_u["ci_lower"] is not None else ""
                _smlines.append(f"  ⏳ FotMob球队大小/小球尚未转正（已结算{_fmtt_u['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                 f"平注ROI{_roi_txt9u}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}{_ci_txt9u}）——继续仅观察+结算")
        elif _stype == "fotmob_spread":
            # 2026-09-06按outcome拆分展示(home/away)，理由同fotmob_totals同名分支
            _fmsp_h = _fotmob_spread_validation_status("home")
            if _fmsp_h["validated"]:
                _smlines.append(f"  ✅ FotMob让球/主队已转正（已结算{_fmsp_h['n']}场，胜率{_fmsp_h['win_rate']:.1%}，"
                                 f"平注ROI{_fmsp_h['roi']:+.1%}）——建议并入p_fusion正式启用")
            else:
                _roi_txt13h = f"{_fmsp_h['roi']:+.1%}" if _fmsp_h["roi"] is not None else "暂无"
                _smlines.append(f"  ⏳ FotMob让球/主队尚未转正（已结算{_fmsp_h['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                 f"平注ROI{_roi_txt13h}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
            _fmsp_a = _fotmob_spread_validation_status("away")
            if _fmsp_a["validated"]:
                _smlines.append(f"  ✅ FotMob让球/客队已转正（已结算{_fmsp_a['n']}场，胜率{_fmsp_a['win_rate']:.1%}，"
                                 f"平注ROI{_fmsp_a['roi']:+.1%}）——建议并入p_fusion正式启用")
            else:
                _roi_txt13a = f"{_fmsp_a['roi']:+.1%}" if _fmsp_a["roi"] is not None else "暂无"
                _smlines.append(f"  ⏳ FotMob让球/客队尚未转正（已结算{_fmsp_a['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                 f"平注ROI{_roi_txt13a}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
        elif _stype == "fotmob_corner":
            # 2026-09-06按outcome拆分展示(corner_over/corner_under)，理由同fotmob_totals同名分支
            _fmc_o = _fotmob_corner_validation_status("corner_over")
            if _fmc_o["validated"]:
                _smlines.append(f"  ✅ FotMob角球/大球已转正（已结算{_fmc_o['n']}场，胜率{_fmc_o['win_rate']:.1%}，"
                                 f"平注ROI{_fmc_o['roi']:+.1%}）——建议并入p_fusion正式启用")
            else:
                _roi_txt14o = f"{_fmc_o['roi']:+.1%}" if _fmc_o["roi"] is not None else "暂无"
                _smlines.append(f"  ⏳ FotMob角球/大球尚未转正（已结算{_fmc_o['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                 f"平注ROI{_roi_txt14o}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
            _fmc_u = _fotmob_corner_validation_status("corner_under")
            if _fmc_u["validated"]:
                _smlines.append(f"  ✅ FotMob角球/小球已转正（已结算{_fmc_u['n']}场，胜率{_fmc_u['win_rate']:.1%}，"
                                 f"平注ROI{_fmc_u['roi']:+.1%}）——建议并入p_fusion正式启用")
            else:
                _roi_txt14u = f"{_fmc_u['roi']:+.1%}" if _fmc_u["roi"] is not None else "暂无"
                _smlines.append(f"  ⏳ FotMob角球/小球尚未转正（已结算{_fmc_u['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                 f"平注ROI{_roi_txt14u}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
        for _sl2 in _smlines:
            print(_sl2)

    # ─── ⚽ 比分预测单（独立区块，覆盖全部分析赛事）────────────────────────────
    # 补全 _score_all 中尚未有比分的赛事（未被 predict_football.py 覆盖时 fallback）
    for _sa_uid, _sa_info in _score_all.items():
        if not _sa_info.get("top_score"):
            _sa_key = (_sa_info["home"].lower(), _sa_info["away"].lower())
            if _sa_key in _top_score_cache:
                _sa_info["top_score"] = _top_score_cache[_sa_key]
            else:
                _fs_fallback = _get_football_top_score(
                    _sa_info["home"], _sa_info["away"], _sa_info["league"])
                if _fs_fallback and _fs_fallback != "?":
                    _sa_info["top_score"] = _fs_fallback
                    _top_score_cache[_sa_key] = _fs_fallback
                    _persist_xg_score(_sa_uid, _sa_info["home"], _sa_info["away"],
                                      _sa_info["league"], _sa_info.get("kickoff", ""),
                                      _fs_fallback, fetch_date)

    # 将比分结果回写推荐单（Pass3 时可能未查到，现在 _top_score_cache 更完整）
    for _r in recommendations:
        if _r.get("predicted_score") in ("-", None, "?", ""):
            _rk = (_r["home_team"].lower(), _r["away_team"].lower())
            _new_sc = _top_score_cache.get(_rk)
            if _new_sc and _new_sc != "?":
                _r["predicted_score"] = _new_sc

    # 输出比分预测单：展示真实盘口支撑的比分候选(有真实命中分)，按命中分降序，最多Top7
    # （比分玩法不进主推荐单/单注/串关，专门在这里展示，同时已写入 hit_recommendations
    #  供 21_auto_settle.py 结算，统计命中率/盈亏；见 [[project_correct_score_market]]）
    #
    # 2026-08-20用户要求重构：此前这个区块混杂了70-97场纯泊松参考预测(无盘口支撑，
    # 不是推荐)，按开赛时间排序展示，标题也没有像其他"仅数据追踪"区块那样标注清楚，
    # 结果被误认成正式比分投注单。改成只保留有真实盘口支撑、算出过命中分的候选，
    # 按命中分降序取前7场——诚实反映"今天有没有真正的比分候选"，是CLAUDE.md"推荐单
    # 数据支撑规则"在展示层的对应体现。
    #
    # 数据源修复(同日二次修复)：取数源头必须是_cs_all_candidates(_generate_correct_
    # score_recs()的原始返回值，_in_scope()过滤*之前*)，不能用下面被_in_scope()过滤
    # 后的recommendations——市场没转正时_in_scope()会把correct_score从recommendations
    # 里整个删掉，如果从那之后取数，会导致哪怕候选真的算出过命中分(≥0.70，这是能
    # 进_generate_correct_score_recs()返回值的前提)，本区块也会一条都看不到，跟其他
    # 所有"转正判断前取数、标注仅观察"的影子观察单设计原则不一致——第一版重构漏了
    # 这一环，2026-08-20当天复盘时发现"为什么没有命中分"才补上。
    _SC_W = 133
    _cs_final_by_match: dict = {}
    for r in _cs_all_candidates:
        _k = (r["home_team"].lower(), r["away_team"].lower())
        _cs_final_by_match.setdefault(_k, []).append(r)
    for _v in _cs_final_by_match.values():
        _v.sort(key=lambda r: r.get("pick_rank", 1))

    _score_all_by_match = {(v["home"].lower(), v["away"].lower()): v for v in _score_all.values()}
    _cs_top7 = sorted(
        _cs_final_by_match.items(),
        key=lambda kv: kv[1][0]["hit_score"],
        reverse=True,
    )[:7]

    if _cs_top7:
        _cs_stat = _correct_score_validation_status()
        _title = ("  ⚽ 比分投注单  [真实盘口比分推荐，命中分降序Top7]" if _cs_stat["validated"]
                   else "  📊 比分候选观察单  [真实盘口比分推荐，命中分降序Top7]  [仅数据追踪，未正式启用]")
        _sc_lines = [
            "",
            "─" * _SC_W,
            _title,
            "─" * _SC_W,
            f"  {'序':>3}  {'开赛时间':<12} {'联赛':<16} {'主队':<16} {'客队':<16} {'预测比分':<10} {'引擎':<14} {'推荐比分':<8} {'赔率':<6} {'命中分'}",
            "─" * _SC_W,
        ]
        # 批量预取 engine 标签（同场多次查询 -> 一次性查询），查不到的按 xG 兜底处理
        # （football_score_predictions 只在 predict_football.py 算出真实 lam_h/lam_a 时才写入，
        #  查不到说明两队都无 ELO/泊松历史数据，00_命中系统.py 自己的 xG 兜底函数才是真实来源，
        #  标 "xG" 是准确的，不是兜底占位）
        _sc_eng_map: dict = {}
        try:
            with engine.connect() as _sc_conn:
                for _h, _a, _eng in _sc_conn.execute(text("""
                    SELECT LOWER(home_team), LOWER(away_team), engine
                    FROM football_score_predictions
                    WHERE fetch_date IN (:fd, :nd)
                """), {"fd": fetch_date, "nd": next_date}).fetchall():
                    _sc_eng_map[(_h, _a)] = _eng
        except Exception:
            pass

        _cs_reco_pick_count = 0
        for _sci, (_k, _cs_picks) in enumerate(_cs_top7, 1):
            _sv = _score_all_by_match.get(_k, {})
            _sc_t   = _fmt_time(_sv.get("kickoff") or "")
            _sc_lg  = _tw(_league_zh(_sv.get("league") or ""), 16)
            _sc_hm  = _tw(f"[主]{_team_zh(_sv.get('home') or _k[0])}", 16)
            _sc_aw  = _tw(f"[客]{_team_zh(_sv.get('away') or _k[1])}", 16)
            _sc_s   = _sv.get("top_score") or "-"
            _sc_eng = _sc_eng_map.get(_k, "xG")
            _cs_reco_pick_count += len(_cs_picks)
            _first, _rest = _cs_picks[0], _cs_picks[1:]
            _reco_str = f"🎯{_first['outcome']}({_first['pick_label']})"
            _odds_str = f"{_first['best_odds']:.2f}"
            _hs_str   = f"{_first['hit_score']:.3f}"
            _sc_lines.append(
                f"  {_sci:>3}.  {_tw(_sc_t, 14)}{_sc_lg}{_sc_hm}{_sc_aw} {_sc_s:<10} {_sc_eng:<14} "
                f"{_reco_str:<8} {_odds_str:<6} {_hs_str}"
            )
            # 次选另起一行，缩进对齐到"推荐比分"这一列，不重复打印开赛时间/联赛/队名
            # 缩进长度 = 序号+时间+联赛+主客队+预测比分+引擎列的总宽度（跟上面那行的格式串严格对应）
            _indent = " " * (2 + 3 + 1 + 2 + 14 + 16 + 16 + 16 + 1 + 10 + 1 + 14 + 1)
            for _pk in _rest:
                _pk_str = f"🎯{_pk['outcome']}({_pk['pick_label']})"
                _sc_lines.append(f"{_indent}{_pk_str:<8} {_pk['best_odds']:<6.2f} {_pk['hit_score']:.3f}")
        _sc_lines.append("─" * _SC_W)
        _sc_lines.append(f"  共 {len(_cs_final_by_match)} 场有真实盘口支撑的比分候选，按命中分降序展示前{len(_cs_top7)}场"
                         f"（共{_cs_reco_pick_count}个🎯标记，1首选+最多2次选，已计入结算统计）  "
                         f"引擎: poisson=联赛历史泊松 / poisson_global=跨联赛泊松 / elo=ELO降级 / xG=xG融合")
        if _cs_stat["validated"]:
            _sc_lines.append(f"  ✅ 比分玩法已转正（已结算{_cs_stat['n']}场，胜率{_cs_stat['win_rate']:.1%}，平注ROI{_cs_stat['roi']:+.1%}）"
                              f"——本轮起进入单注分配/主推荐单")
        else:
            _n, _need = _cs_stat["n"], CORRECT_SCORE_VALIDATION_MIN_SAMPLES
            _roi_txt = f"{_cs_stat['roi']:+.1%}" if _cs_stat["roi"] is not None else "暂无"
            _sc_lines.append(f"  ⏳ 比分玩法尚未转正（已结算{_n}/{_need}场，平注ROI{_roi_txt}，需≥{CORRECT_SCORE_VALIDATION_MIN_ROI:.0%}）"
                              f"——继续仅在本区块观察+结算，不进单注/主推荐单")
        _score_section_lines = _sc_lines
        for _scl in _sc_lines:
            print(_scl)
    else:
        _score_section_lines = []
        log.info("  ⚽ 比分预测：今日无真实盘口支撑的比分候选")

    # 保存到桌面
    # FIX-001(2026-09-12)：真钱通道冻结。纸面模式(默认)写 D:\lucky_paper\ 并在
    # 文件头加水印；只有 BETTING_MODE=live 且 ENABLE_LIVE_BETTING=1 双开关同时
    # 成立才写 D:\lucky\。历史 D:\lucky\ 文件不动。
    desk_file = None
    _paper_mode = not is_live_betting()
    try:
        import os as _os2
        desktop = slip_output_dir()
        _os2.makedirs(desktop, exist_ok=True)
        ts = datetime.now().strftime("%H%M")
        desk_file = _os2.path.join(desktop, f"投注单_{fetch_date}_{ts}.txt")

        # 角球投注单（corner_model.generate_corner_slip()算好传入）
        # 2026-08-09修复：此前不论转正状态，一律以"正式推荐单"格式写入文件，绕开了
        # _validation_result()统一检验（唯一依据是corner_model.py里一行没有样本量/
        # 显著性支撑的历史回测注释），违反北极星原则和2026-08-01确立的双重检验规则。
        # 现改为按_corner_validation_status()门控：未转正时降级为"仅观察"格式并附
        # 转正进度提示，行为跟其他所有市场的影子观察单保持一致。
        _corner_official_lines = []
        if precomputed_corner_recs:
            _corner_stat = _corner_validation_status()
            _CW = 110
            if _corner_stat["validated"]:
                _corner_title = (f"  ⚽ 角球投注单  [{fetch_date}]  混合分布(正态≤10.5/负二项≥11.5) "
                                  f"| EV≥10% | 偏差修正+0.25")
                _corner_footer = (f"  共推荐 {len(precomputed_corner_recs)} 注角球 | 前15注已列出 "
                                   f"| μ=预测均角 | EV门槛=10%")
            else:
                _corner_title = (f"  📊 角球候选观察单  [{fetch_date}]  混合分布(正态≤10.5/负二项≥11.5) "
                                  f"| EV≥10% | 偏差修正+0.25  [仅数据追踪，未正式启用]")
                _corner_roi_txt = f"{_corner_stat['roi']:+.1%}" if _corner_stat["roi"] is not None else "暂无"
                _corner_footer = (f"  共 {len(precomputed_corner_recs)} 条候选 | 前15条已列出 | μ=预测均角\n"
                                   f"  ⏳ 角球尚未转正（已结算{_corner_stat['n']}/{CORNER_VALIDATION_MIN_SAMPLES}场，"
                                   f"平注ROI{_corner_roi_txt}，需≥{CORNER_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
                # 2026-09-06：corner_model.generate_corner_slip()现在validated=False时
                # 已经不写corner_recommendations了（见该函数docstring），这里补上跟
                # _in_scope()同一套"反事实"记录——转存进shadow_multi['gated']，这样
                # settle_shadow_recommendations()仍会正常结算这批候选，判断"该不该
                # 转正"所需的数据不会因为门槛关闭而停止积累。
                for _cg in precomputed_corner_recs:
                    _cg_uid = f"corner_{_cg['league']}_{_cg['home']}_{_cg['away']}_{_cg['line']}"
                    _cg_key = f"{_cg_uid}|corner_total|{_cg['direction']}"
                    _cg_prev = shadow_multi["gated"].get(_cg_key)
                    if _cg_prev and _cg_prev.get("hit_score", 0) >= _cg["hit_score"]:
                        continue
                    shadow_multi["gated"][_cg_key] = {
                        "unified_id": _cg_uid, "sport_code": "football",
                        "league_name": _cg["league"], "home_team": _cg["home"],
                        "away_team": _cg["away"], "kickoff_utc": _cg["kickoff_utc"],
                        "shadow_type": "gated", "market": "corner_total", "outcome": _cg["direction"],
                        "handicap": _cg["line"], "best_odds": _cg["odds"],
                        "model_prob": _cg["p_fusion"], "kelly_fraction": _cg["kelly"],
                        "hit_score": _cg["hit_score"], "predicted_score": "-",
                        "fetch_date": fetch_date,
                    }
            _corner_official_lines = ["\n", "=" * _CW, _corner_title, "=" * _CW,
                (f"  {'开赛时间':<14}{'联赛':<18}{'主队':<17}{'客队':<17}"
                 f"{'市场':<6}{'方向':<12}{'赔率':>6}{'p融合':>7}{'K₁/₄':>7}{'命中分':>8}  数据源"),
                "  " + "-" * 107]
            for _cr in sorted(precomputed_corner_recs, key=lambda x: -x["hit_score"])[:15]:
                _cr_bj = _cr["bj"].strftime("%m月%d日%H:%M")
                _cr_lg = (_cr["league"].replace("FIFA - ", "FIFA-")
                                        .replace("Spain - ", "西班牙-")
                                        .replace("Brazil - ", "巴西-")
                                        .replace("Iceland - ", "冰岛-")
                                        .replace("Sweden - ", "瑞典-")
                                        .replace("Chile - ", "智利-")
                                        .replace("Argentina - ", "阿根廷-"))[:16]
                _cr_h = f"[主]{_cr['home'][:12]}"
                _cr_a = f"[客]{_cr['away'][:12]}"
                _cr_src = {"team_stats": "队伍统计", "wc_model": "WC模型",
                           "fotmob_team_stats": "FotMob统计"}.get(_cr["src"], _cr["src"])
                _corner_official_lines.append(
                    f"  {_cr_bj:<14}{_cr_lg:<18}{_cr_h:<17}{_cr_a:<17}"
                    f"{'角球':<6}{_cr['dir_label']:<12}{_cr['odds']:>6.2f}"
                    f"{_cr['p_fusion']:>7.3f}{_cr['kelly']:>7.4f}{_cr['hit_score']:>8.3f}  {_cr_src}")
            _corner_official_lines += ["  " + "-" * 107, _corner_footer, "=" * _CW]

        # 合并正式推荐+影子候选（追加到文件末尾）
        # 2026-08-05修复：原来这里重新拼了一遍小球/大球候选表格，但漏掉了console版
        # shadow_lines/over_shadow_lines末尾追加的"共N条候选"+转正ROI统计行，导致
        # 保存到磁盘的txt文件比日志/控制台少了这几行——跟下面7-19号那次team_total桶
        # 记录的是同一种"两套渲染逻辑各改各的"bug模式。直接复用上面已经完整构建好
        # (含ROI统计)的shadow_lines/over_shadow_lines，不再重复拼表格，避免再次分叉。
        _shadow_txt = ["\n"] + shadow_lines if shadow_candidates else []
        _over_shadow_txt = ["\n"] + over_shadow_lines if over_shadow_candidates else []
        # 其他市场影子也写入文件
        # Bug修复(2026-07-19)：这里是跟上面print(_smlines)完全独立、复制粘贴出来的
        # 第二套渲染逻辑，专门给保存文件用——今天新增"team_total"影子桶时只改了print
        # 那一套的_SHADOW_TYPE_ZH/for循环元组，这里的_SHADOW_TYPE_ZH2/元组没同步，
        # 导致控制台/日志能看到球队大小影子观察单，保存的txt文件里却没有。
        _SHADOW_TYPE_ZH2 = {"moneyline": "独赢", "spread": "让分", "1x2": "胜平负",
                           "lstm_moneyline": "LSTM独赢", "lstm_1x2": "LSTM胜平负",
                           "lstm_spread": "LSTM让球", "team_total": "球队大小",
                           "fotmob_1x2": "FotMob胜平负",
                           "fotmob_totals": "FotMob大小球", "fotmob_team_total": "FotMob球队大小",
                           "fotmob_spread": "FotMob让球", "fotmob_corner": "FotMob角球",
                       "qiety_h2h": "企鹅交锋", "injury_impact": "伤停信号", "htft": "半全场",
                       "htft_nofilter": "半全场(无联赛过滤平行线)"}
        # Bug修复(2026-08-31)：跟本文件2026-07-19"team_total"那次同一类坑——这里是
        # 跟上面print(_smlines)那套完全独立、复制粘贴出来的第二套渲染逻辑，专门给
        # 保存文件用。htft桶2026-07-24创建时两套元组都没同步加，导致控制台和保存
        # 文件都看不到；这次只同步了print那一套，保存文件这套漏了，用户反馈"两天
        # 没看到半全场推荐"后才发现——本质原因是两套重复实现没有单一数据源，以后
        # 新增influencer/桶类型必须同时改这两处元组，或者干脆把这段重构成公共函数。
        _multi_txt: list[str] = []
        for _st2 in ("moneyline", "spread", "1x2", "lstm_moneyline", "lstm_1x2", "lstm_spread", "team_total",
                     "fotmob_1x2", "fotmob_totals", "fotmob_team_total", "fotmob_spread", "fotmob_corner",
                     "qiety_h2h", "injury_impact", "htft", "htft_nofilter"):
            _tzh = _SHADOW_TYPE_ZH2.get(_st2, _st2)

            def _append_bucket_table(_cands, _title):
                """渲染一张候选表追加进_multi_txt——2026-09-06为大小球/球队大小
                拆分大球/小球两张独立表复用，跟上面print(_smlines)那套保持同一份
                字段/翻译逻辑（宽度13是这套V2渲染自己的既有约定，跟V1的14不同，
                维持各自原状，不在这次改动里顺带统一，降低无关改动的风险）。"""
                _multi_txt.append("")
                _multi_txt.append("─" * _SW2)
                _multi_txt.append(f"  📊 {_title}影子观察单（仅数据追踪，未正式启用）")
                _multi_txt.append("─" * _SW2)
                _multi_txt.append(f"  {'序':>3}  {'开赛时间':<12} {'联赛':<14} {'主队':<14}{'客队':<14}"
                                   f" {'市场':<8} {'方向':<10} {'赔率':<6} {'p融合':<7} {'K₁/₄':<7} {'命中分':<8} {'比分预测'}")
                _multi_txt.append("─" * _SW2)
                for _i2, _e2 in enumerate(_cands, 1):
                    _lg2f   = _tw(_league_zh(_e2["league_name"], _e2.get("sport_code", "")), 13)
                    _home2f = _tw(f"[主]{_team_zh(_e2['home_team'])}", 13)
                    _away2f = _tw(f"[客]{_team_zh(_e2['away_team'])}", 13)
                    _out2f = _OUTCOME_ZH.get(_e2["outcome"], _e2["outcome"])
                    _hc2f  = _e2.get("handicap")
                    if _hc2f is not None:
                        _out2f = f"{_out2f}{_hc2f}"
                    _multi_txt.append(
                        f"  {_i2:>3}.  {_fmt_time(_e2['kickoff_utc']):<12}"
                        f" {_lg2f}"
                        f" {_home2f}{_away2f}"
                        f" {_MARKET_ZH.get(_e2['market'],_e2['market']):<8} {_out2f:<10}"
                        f" {_e2['best_odds']:<6.2f} {_e2['model_prob']:<7.3f}"
                        f" {_e2['kelly_fraction']:<7.4f} {_e2['hit_score']:<8.3f}"
                        f" {_e2.get('predicted_score') or '-'}"
                    )
                _multi_txt.append(f"  共 {len(_cands)} 条候选")

            if _st2 in _TOTALS_FAMILY_SPLIT:
                # 大球/小球edge差异很大，混合Top7会互相挤占名额，跟上面_smlines
                # 那套是同一次(2026-09-06)拆分，理由见那边的注释。
                _all_cands2 = list(shadow_multi.get(_st2, {}).values())
                if not _all_cands2:
                    continue
                _has_any2 = False
                for _oc_key2, _oc_zh2 in (("over", "大球"), ("under", "小球")):
                    _oc_list2 = sorted([c for c in _all_cands2 if c.get("outcome") == _oc_key2],
                                        key=lambda x: -x["hit_score"])[:7]
                    if not _oc_list2:
                        continue
                    _has_any2 = True
                    _append_bucket_table(_oc_list2, f"{_tzh}/{_oc_zh2}")
                if not _has_any2:
                    continue
            else:
                _sl2 = sorted(shadow_multi.get(_st2, {}).values(), key=lambda x: -x["hit_score"])[:7]  # 2026-08-02: Top10→Top7
                if not _sl2:
                    continue
                _append_bucket_table(_sl2, _tzh)
            if _st2 == "team_total":
                _tt_fo2 = _team_total_validation_status("football", "over")
                if _tt_fo2["validated"]:
                    _multi_txt.append(f"  ✅ 足球球队大小/大球已转正（已结算{_tt_fo2['n']}场，胜率{_tt_fo2['win_rate']:.1%}，"
                                       f"平注ROI{_tt_fo2['roi']:+.1%}）——本轮起进入主推荐单")
                else:
                    _roi_txt7 = f"{_tt_fo2['roi']:+.1%}" if _tt_fo2["roi"] is not None else "暂无"
                    _multi_txt.append(f"  ⏳ 足球球队大小/大球尚未转正（已结算{_tt_fo2['n']}/{TEAM_TOTAL_VALIDATION_MIN_SAMPLES}场，"
                                       f"平注ROI{_roi_txt7}，需≥{TEAM_TOTAL_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
                _tt_fu2 = _team_total_validation_status("football", "under")
                _roi_txt8 = f"{_tt_fu2['roi']:+.1%}" if _tt_fu2["roi"] is not None else "暂无"
                _multi_txt.append(f"  ⏳ 足球球队大小/小球不参与转正（用户明确要求只放行大球方向，"
                                   f"已结算{_tt_fu2['n']}场，平注ROI{_roi_txt8}，仅供参考）——继续仅观察+结算")
                _tt_b2 = _team_total_validation_status("basketball")
                _roi_txt9 = f"{_tt_b2['roi']:+.1%}" if _tt_b2["roi"] is not None else "暂无"
                _multi_txt.append(f"  ⏳ 篮球球队大小尚未转正（已结算{_tt_b2['n']}/{TEAM_TOTAL_VALIDATION_MIN_SAMPLES}场，"
                                   f"平注ROI{_roi_txt9}，需≥{TEAM_TOTAL_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
            elif _st2 == "fotmob_1x2":
                _fm_stat2 = _fotmob_validation_status()
                if _fm_stat2["validated"]:
                    _multi_txt.append(f"  ✅ FotMob胜平负已转正（已结算{_fm_stat2['n']}场，胜率{_fm_stat2['win_rate']:.1%}，"
                                       f"平注ROI{_fm_stat2['roi']:+.1%}）——建议并入p_fusion正式启用")
                else:
                    _roi_txt10 = f"{_fm_stat2['roi']:+.1%}" if _fm_stat2["roi"] is not None else "暂无"
                    _multi_txt.append(f"  ⏳ FotMob胜平负尚未转正（已结算{_fm_stat2['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                       f"平注ROI{_roi_txt10}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
            elif _st2 == "fotmob_totals":
                # 2026-09-06按outcome拆分展示，理由同上方_display_parallel_lines()同名分支
                _fmt_o2 = _fotmob_totals_validation_status("over")
                if _fmt_o2["validated"]:
                    _multi_txt.append(f"  ✅ FotMob大小球/大球已转正（已结算{_fmt_o2['n']}场，胜率{_fmt_o2['win_rate']:.1%}，"
                                       f"平注ROI{_fmt_o2['roi']:+.1%}）——建议并入p_fusion正式启用")
                else:
                    _roi_txt11o = f"{_fmt_o2['roi']:+.1%}" if _fmt_o2["roi"] is not None else "暂无"
                    _multi_txt.append(f"  ⏳ FotMob大小球/大球尚未转正（已结算{_fmt_o2['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                       f"平注ROI{_roi_txt11o}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
                _fmt_u2 = _fotmob_totals_validation_status("under")
                if _fmt_u2["validated"]:
                    _multi_txt.append(f"  ✅ FotMob大小球/小球已转正（已结算{_fmt_u2['n']}场，胜率{_fmt_u2['win_rate']:.1%}，"
                                       f"平注ROI{_fmt_u2['roi']:+.1%}）——建议并入p_fusion正式启用")
                else:
                    _roi_txt11u = f"{_fmt_u2['roi']:+.1%}" if _fmt_u2["roi"] is not None else "暂无"
                    _ci_txt11u = f"，ci_lower={_fmt_u2['ci_lower']:+.1%}" if _fmt_u2["ci_lower"] is not None else ""
                    _multi_txt.append(f"  ⏳ FotMob大小球/小球尚未转正（已结算{_fmt_u2['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                       f"平注ROI{_roi_txt11u}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}{_ci_txt11u}）——继续仅观察+结算")
            elif _st2 == "fotmob_team_total":
                _fmtt_o2 = _fotmob_team_total_validation_status("over")
                if _fmtt_o2["validated"]:
                    _multi_txt.append(f"  ✅ FotMob球队大小/大球已转正（已结算{_fmtt_o2['n']}场，胜率{_fmtt_o2['win_rate']:.1%}，"
                                       f"平注ROI{_fmtt_o2['roi']:+.1%}）——建议并入p_fusion正式启用")
                else:
                    _roi_txt12o = f"{_fmtt_o2['roi']:+.1%}" if _fmtt_o2["roi"] is not None else "暂无"
                    _multi_txt.append(f"  ⏳ FotMob球队大小/大球尚未转正（已结算{_fmtt_o2['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                       f"平注ROI{_roi_txt12o}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
                _fmtt_u2 = _fotmob_team_total_validation_status("under")
                if _fmtt_u2["validated"]:
                    _multi_txt.append(f"  ✅ FotMob球队大小/小球已转正（已结算{_fmtt_u2['n']}场，胜率{_fmtt_u2['win_rate']:.1%}，"
                                       f"平注ROI{_fmtt_u2['roi']:+.1%}）——建议并入p_fusion正式启用")
                else:
                    _roi_txt12u = f"{_fmtt_u2['roi']:+.1%}" if _fmtt_u2["roi"] is not None else "暂无"
                    _ci_txt12u = f"，ci_lower={_fmtt_u2['ci_lower']:+.1%}" if _fmtt_u2["ci_lower"] is not None else ""
                    _multi_txt.append(f"  ⏳ FotMob球队大小/小球尚未转正（已结算{_fmtt_u2['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                       f"平注ROI{_roi_txt12u}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}{_ci_txt12u}）——继续仅观察+结算")
            elif _st2 == "fotmob_spread":
                _fmsp_h2 = _fotmob_spread_validation_status("home")
                if _fmsp_h2["validated"]:
                    _multi_txt.append(f"  ✅ FotMob让球/主队已转正（已结算{_fmsp_h2['n']}场，胜率{_fmsp_h2['win_rate']:.1%}，"
                                       f"平注ROI{_fmsp_h2['roi']:+.1%}）——建议并入p_fusion正式启用")
                else:
                    _roi_txt15h = f"{_fmsp_h2['roi']:+.1%}" if _fmsp_h2["roi"] is not None else "暂无"
                    _multi_txt.append(f"  ⏳ FotMob让球/主队尚未转正（已结算{_fmsp_h2['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                       f"平注ROI{_roi_txt15h}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
                _fmsp_a2 = _fotmob_spread_validation_status("away")
                if _fmsp_a2["validated"]:
                    _multi_txt.append(f"  ✅ FotMob让球/客队已转正（已结算{_fmsp_a2['n']}场，胜率{_fmsp_a2['win_rate']:.1%}，"
                                       f"平注ROI{_fmsp_a2['roi']:+.1%}）——建议并入p_fusion正式启用")
                else:
                    _roi_txt15a = f"{_fmsp_a2['roi']:+.1%}" if _fmsp_a2["roi"] is not None else "暂无"
                    _multi_txt.append(f"  ⏳ FotMob让球/客队尚未转正（已结算{_fmsp_a2['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                       f"平注ROI{_roi_txt15a}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
            elif _st2 == "fotmob_corner":
                _fmc_o2 = _fotmob_corner_validation_status("corner_over")
                if _fmc_o2["validated"]:
                    _multi_txt.append(f"  ✅ FotMob角球/大球已转正（已结算{_fmc_o2['n']}场，胜率{_fmc_o2['win_rate']:.1%}，"
                                       f"平注ROI{_fmc_o2['roi']:+.1%}）——建议并入p_fusion正式启用")
                else:
                    _roi_txt16o = f"{_fmc_o2['roi']:+.1%}" if _fmc_o2["roi"] is not None else "暂无"
                    _multi_txt.append(f"  ⏳ FotMob角球/大球尚未转正（已结算{_fmc_o2['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                       f"平注ROI{_roi_txt16o}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
                _fmc_u2 = _fotmob_corner_validation_status("corner_under")
                if _fmc_u2["validated"]:
                    _multi_txt.append(f"  ✅ FotMob角球/小球已转正（已结算{_fmc_u2['n']}场，胜率{_fmc_u2['win_rate']:.1%}，"
                                       f"平注ROI{_fmc_u2['roi']:+.1%}）——建议并入p_fusion正式启用")
                else:
                    _roi_txt16u = f"{_fmc_u2['roi']:+.1%}" if _fmc_u2["roi"] is not None else "暂无"
                    _multi_txt.append(f"  ⏳ FotMob角球/小球尚未转正（已结算{_fmc_u2['n']}/{FOTMOB_VALIDATION_MIN_SAMPLES}场，"
                                       f"平注ROI{_roi_txt16u}，需≥{FOTMOB_VALIDATION_MIN_ROI:.0%}）——继续仅观察+结算")
        # ── V2公式推荐区块 ──────────────────────────────────────────────────
        _v2_txt: list[str] = []
        if _final_v2:
            _SW3 = 110
            _v2_txt += ["", "─" * _SW3,
                        "  🔬 【V2替换公式推荐单】（价值边际驱动，并行对比，仅数据追踪）",
                        "  📐 V2公式: edge(50%) + kelly(30%) + quality(20%)   阈值≥0.55",
                        "─" * _SW3,
                        f"  {'序':>3}  {'开赛时间':<12} {'联赛':<14} {'主队':<14}{'客队':<14}"
                        f" {'市场':<8} {'方向':<12} {'赔率':<6} {'p融合':<7} {'K₁/₄':<7} {'V2分':<7} {'V1对比'}",
                        "─" * _SW3]
            for _vi, _vr in enumerate(_final_v2, 1):
                _vt   = _fmt_time(_vr["kickoff_utc"])
                _vlg  = (_vr["league_name"] or "")[:13]
                _vhm  = ("[主]" + _vr["home_team"])[:13]
                _vaw  = ("[客]" + _vr["away_team"])[:13]
                _vmk  = _MARKET_ZH.get(_vr["market"], _vr["market"])
                _vout = _OUTCOME_ZH.get(_vr["outcome"], _vr["outcome"])
                _vhcp = _vr.get("handicap")
                if _vhcp is not None:
                    _vout = f"{_vout}{_vhcp}"
                # v1 대비: check if same match/market is in v1 recommendations
                _v1_hs = next((r["hit_score"] for r in recommendations
                                if r["unified_id"] == _vr["unified_id"]
                                and r["market"] == _vr["market"]
                                and r["outcome"] == _vr["outcome"]), None)
                _v1_tag = (f"v1={_v1_hs:.3f}{'✅' if _v1_hs and _v1_hs>=HIT_SCORE_GLOBAL_THRESHOLD else '❌未推'}"
                           if _v1_hs is not None else "v1:❌未推")
                _v2_txt.append(
                    f"  {_vi:>3}.  {_vt:<12} {_vlg:<14} {_vhm:<14}{_vaw:<14}"
                    f" {_vmk:<8} {_vout:<12} {_vr['best_odds']:<6.2f}"
                    f" {_vr['model_prob']:<7.3f} {_vr['kelly_fraction']:<7.4f}"
                    f" {_vr['hit_score']:<7.3f} {_v1_tag}"
                )
            _v2_txt += ["─" * _SW3, f"  共 {len(_final_v2)} 条 V2推荐（门槛 ≥ {HIT_SCORE_V2_THRESHOLD}，已落库 formula_version='v2'）"]
        else:
            _v2_txt = ["", "─" * 60, "  🔬 V2替换公式推荐单：本期无达标推荐（门槛≥0.55）", "─" * 60]

        with open(desk_file, "w", encoding="utf-8") as _f:
            if _paper_mode:
                _f.write(f"{PAPER_WATERMARK} 本单为纸面观察单，不构成真钱投注建议 "
                         f"(BETTING_MODE=paper, 生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M')})\n\n")
            _f.write("\n".join(_corner_official_lines + plan_lines + lines + _shadow_txt + _over_shadow_txt + _multi_txt
                               + _v2_txt + _score_section_lines) + "\n")
        log.info(f"  📄 推荐单已保存: {desk_file}" + ("（纸面模式）" if _paper_mode else ""))
    except Exception as _e:
        log.warning(f"  投注单保存失败: {_e}")

    return recommendations, desk_file


# ─── 主流程 ───────────────────────────────────────────────────────────────────
def _frozen_market_failure(uid, fetch_date, reason):
    log.warning("Frozen market input WARNING uid=%s: %s", uid, reason)
    return {"uid": uid, "fetch_date": fetch_date, "unified_status": "FAILURE",
            "consensus_status": "FAILURE", "unified_rows": (), "consensus_rows": (),
            "failure_reason": reason}


def _build_frozen_market_one(uid, match, fetch_date, scrape_date):
    try:
        unified = build_unified_odds(uid, match.get("sources", {}), fetch_date,
                                     scrape_date=scrape_date, frozen=True)
        if unified["status"] == "FAILURE":
            return uid, _frozen_market_failure(uid, fetch_date, unified["failure_reason"])
        consensus = compute_consensus_odds(uid, fetch_date, unified_rows=unified["rows"])
        return uid, {"uid": uid, "fetch_date": fetch_date,
                     "unified_status": unified["status"], "consensus_status": consensus["status"],
                     "unified_rows": unified["rows"], "consensus_rows": consensus["rows"],
                     "failure_reason": consensus["failure_reason"]}
    except Exception as exc:
        return uid, _frozen_market_failure(uid, fetch_date, "worker: " + type(exc).__name__)


def _freeze_market_input(expected_uids, results, fetch_date):
    from types import MappingProxyType
    collected = {}
    for uid, result in results:
        if uid in collected:
            result = _frozen_market_failure(uid, fetch_date, "duplicate worker result")
        collected[uid] = result
    frozen = {}
    for uid in expected_uids:
        result = collected.get(uid)
        if result is None or result.get("uid") != uid or result.get("fetch_date") != fetch_date:
            result = _frozen_market_failure(uid, fetch_date, "missing/mismatched worker result")
        entry = dict(result)
        for prefix in ("unified", "consensus"):
            status = entry.get(prefix + "_status")
            if status not in ("SUCCESS", "EMPTY", "FAILURE"):
                entry = _frozen_market_failure(uid, fetch_date, "invalid worker status")
                break
        for prefix in ("unified", "consensus"):
            rows = entry[prefix + "_rows"] if entry[prefix + "_status"] == "SUCCESS" else ()
            entry[prefix + "_rows"] = tuple(MappingProxyType(dict(r)) for r in rows)
        frozen[uid] = MappingProxyType(entry)
    return MappingProxyType(frozen)


def _run_one_date(fetch_date: str, run_scrapers: bool, skip_slow_scrapers: bool) -> list:
    """单日完整流程：爬虫（可选）→ 匹配 → 赔率 → 预测 → 推荐 → CLV → 结算"""
    init_tables()

    if run_scrapers:
        log.info("\n📡 第一阶段：运行全量爬虫...")
        run_all_scrapers(skip_slow=skip_slow_scrapers, fetch_date=fetch_date)

    log.info("\n🔗 第二阶段：跨源比赛匹配...")
    match_map, scrape_date = build_unified_matches(fetch_date)

    log.info("\n⚽ 第二点二阶段：同步ESPN比赛结果...")
    sync_espn_results(fetch_date)
    sync_fotmob_ht_results(fetch_date)

    log.info("\n📊 第二点五阶段：赔率汇聚 & 共识计算（全量，6线程并行）...")
    import concurrent.futures as _cf_p3
    _consensus_ss_reset()  # FIX-016-5
    def _build_odds_one(args):
        uid, match = args
        return _build_frozen_market_one(uid, match, fetch_date, scrape_date)
    with _cf_p3.ThreadPoolExecutor(max_workers=6) as _pool_p3:
        _market_results = list(_pool_p3.map(_build_odds_one, list(match_map.items())))
    frozen_market_input = _freeze_market_input(match_map, _market_results, fetch_date)

    # FIX-016-5: 单源共识底线汇总（CONSENSUS_MIN_SOURCES，config可配）——
    # 单源行/全场单源比赛意味着这些"共识"实为一家赔率照抄，复盘可按 source_count
    # 或推荐reason里的"⚠共识仅N源"标签分组对照命中表现。只标注不拦截。
    with _CONSENSUS_SS_LOCK:
        _ss = dict(_CONSENSUS_SS_STATS)
    if _ss["rows_total"]:
        log.warning(
            f"  ⚠ 共识源数底线(<{CONSENSUS_MIN_SOURCES}源): 单源共识行 {_ss['rows_ss']}/{_ss['rows_total']}"
            f"（{_ss['rows_ss']*100//_ss['rows_total']}%），全场单源比赛 {_ss['uids_all_ss']}/{_ss['uids']} 场"
            + (f"，示例: {', '.join(_ss['sample_all_ss'][:4])}" if _ss["sample_all_ss"] else "")
            + "——已逐行落 source_count 标注，下游谨慎采信")

    log.info("\n🔮 第三阶段：运行独立预测模型...")
    try:
        from predict_football import run_predictions as run_football_pred
        nf = run_football_pred(fetch_date, frozen_market_input=frozen_market_input)
        log.info(f"  足球预测: {nf} 场")
    except Exception as _e:
        log.warning(f"  足球预测模型异常（跳过）: {_e}")
    try:
        from predict_basketball import run_predictions as run_bball_pred
        nb = run_bball_pred(fetch_date, frozen_market_input=frozen_market_input)
        log.info(f"  篮球预测: {nb} 场")
    except Exception as _e:
        log.warning(f"  篮球预测模型异常（跳过）: {_e}")

    log.info("\n⚽ 第三点五阶段：角球投注分析...")
    # 2026-07-22调整：挪到generate_recommendations()（第四阶段）之前执行——原来
    # 角球分析排在第四点五阶段（推荐单生成之后），FotMob角球影子桶算出来的结果
    # 只能自己单独INSERT进shadow_recommendations表，没法并入generate_recommendations()
    # 内部统一的shadow_multi打印/保存/写库逻辑，导致控制台、保存的投注单txt文件
    # 都看不到这些影子记录（只在数据库里，等于是"哑巴"信号）。现在提前算好，通过
    # precomputed_corner_shadow参数传给generate_recommendations()，让它跟fotmob_1x2/
    # fotmob_totals等其他影子桶一样走同一套打印/保存/写库通道。
    try:
        from corner_model import generate_corner_slip, get_corner_odds_candidates
        # 2026-09-06修复：转正门控要真正拦截DB写入，不能只改展示文字（见
        # corner_model.generate_corner_slip()新增validated参数的docstring说明）。
        _corner_is_validated = _corner_validation_status()["validated"]
        corner_recs = generate_corner_slip(fetch_date, validated=_corner_is_validated)
        log.info(f"  角球推荐: {len(corner_recs)} 注" + ("" if _corner_is_validated else "（未转正，仅观察不入正式表）"))
    except Exception as _e:
        corner_recs = []
        log.warning(f"  角球分析异常（跳过）: {_e}")

    # ── FotMob角球信号影子观察（独立分桶，不影响上面的正式角球推荐）──
    # 2026-07-22重构（原2026-07-21版有结构性缺口）：原写法直接遍历corner_recs
    # （只挂在主推荐结果下面），本意是"FotMob覆盖58个联赛、跟corner_model.py的
    # corner_team_stats覆盖的22个football-data.co.uk联赛代码重叠很小，能补增量
    # 样本"，但嵌套在corner_recs下面导致它只能给主模型已推荐的比赛追加一条FotMob
    # 信号，从来没机会独立评估corner_recs覆盖不到的联赛——恰恰是FotMob本该补足
    # 增量的那部分（实测美职联/巴西乙/韩K联/挪超这些corner_team_stats零覆盖的
    # 联赛，fotmob_match_team_stats.corners字段完整覆盖）。现在改成从
    # get_corner_odds_candidates()取全部有角球盘口的候选比赛独立判断：
    # 跟corner_recs重叠的比赛沿用原有0.85/0.15 blend口径；corner_recs没覆盖到
    # （主模型无团队数据）但FotMob有数据的比赛，用FotMob概率单独打分（无主模型
    # 基底可blend，属于纯观察信号，同样只进shadow_recommendations不进正式推荐单）。
    try:
        _corner_candidates = get_corner_odds_candidates(fetch_date)
    except Exception as _e:
        _corner_candidates = []
        log.warning(f"  角球候选比赛读取异常（FotMob影子桶跳过）: {_e}")

    _corner_recs_by_key = {(r["league"], r["home"], r["away"]): r for r in corner_recs}

    def _corner_implied_fair(odds_o: float, odds_u: float):
        ro, ru = 1.0 / odds_o, 1.0 / odds_u
        t = ro + ru
        return ro / t, ru / t

    _corner_shadow_multi: dict = {}
    for _cand in _corner_candidates:
        _existing = _corner_recs_by_key.get((_cand["league"], _cand["home"], _cand["away"]))
        try:
            _fm_probs = get_fotmob_corner_probs(_cand["home"], _cand["away"], _cand["league"],
                                                 line=_cand["line"])
        except Exception:
            _fm_probs = {}
        if not _fm_probs:
            continue

        if _existing is not None:
            # 跟corner_recs重叠：沿用原有0.85/0.15 blend口径，行为不变
            _fm_cr_p = _fm_probs.get(_existing["direction"])
            if _fm_cr_p is None:
                continue
            _cr_model_p = _existing.get("p_fusion") or _existing.get("p_model") or 0.0
            _model_p = 0.85 * _cr_model_p + 0.15 * _fm_cr_p
            _direction, _odds, _line = _existing["direction"], _existing["odds"], _existing["line"]
        else:
            # corner_recs没覆盖（主模型无团队数据）：FotMob独立信号，方向按
            # 相对隐含公平概率的edge选择（跟corner_model.py自己的选边逻辑一致）
            _p_fair_o, _p_fair_u = _corner_implied_fair(_cand["odds_o"], _cand["odds_u"])
            _p_over_fm, _p_under_fm = _fm_probs.get("over"), _fm_probs.get("under")
            if _p_over_fm is None or _p_under_fm is None:
                continue
            if (_p_over_fm - _p_fair_o) >= (_p_under_fm - _p_fair_u):
                _direction, _model_p, _odds = "over", _p_over_fm, _cand["odds_o"]
            else:
                _direction, _model_p, _odds = "under", _p_under_fm, _cand["odds_u"]
            _line = _cand["line"]

        _raw_k_cr = 0.0
        if _model_p > 0 and _odds > 1:
            _raw_k_cr = (_model_p * _odds - 1) / (_odds - 1)
            _raw_k_cr = max(0.0, min(_raw_k_cr * KELLY_FRACTION, KELLY_MAX_RATIO))
        if _raw_k_cr <= 0 or _model_p < 0.50:
            continue

        _corner_shadow_multi[(_cand["league"], _cand["home"], _cand["away"], _line)] = {
            "unified_id": f"corner_{_cand['league']}_{_cand['home']}_{_cand['away']}_{_line}",
            "sport_code": "football", "league_name": _cand["league"],
            "home_team": _cand["home"], "away_team": _cand["away"],
            "kickoff_utc": _cand["kickoff_utc"], "shadow_type": "fotmob_corner",
            "market": "corner_ou", "outcome": f"corner_{_direction}", "handicap": _line,
            "best_odds": round(_odds, 4), "model_prob": round(_model_p, 4),
            "kelly_fraction": round(_raw_k_cr, 4), "hit_score": round(_model_p, 4),
            "predicted_score": "-", "fetch_date": fetch_date,
        }
    if _corner_shadow_multi:
        log.info(f"  FotMob角球影子观察: {len(_corner_shadow_multi)} 条")

    # ── 半全场(HT/FT)信号影子观察 ──────────────────────────────────────────
    # 2026-07-24新增：predict_football.py已经把9格联合概率写进
    # market_prediction_snapshot(market_group='HTFT')，这里读出来、每场只取
    # hit_score(=model_prob)最高的1个结果转成shadow_multi["htft"]条目，跟
    # fotmob_corner同一套precomputed注入路径，避免在这里重复计算联合分布。
    # best_odds暂时用模型隐含公平赔率(1/model_prob)占位——竞彩hafu真实盘口
    # (sporttery_source.py已采集)还没接入unified_odds/consensus_odds，这个
    # 桶目前只能验证"argmax选对的频率是否符合model_prob"这个校准问题，ROI/
    # 盈亏数字暂不代表真实市场edge，等hafu赔率接入后再让profit_loss变得有意义。
    _htft_shadow_multi: dict = {}
    try:
        with engine.connect() as _htft_conn:
            # Bug修复(2026-08-31)：market_prediction_snapshot.league_code是predict_football.py
            # 写HTFT行时从没填过的空字符串列(非NULL，是''，容易被误判"已经处理过没查到")，
            # 导致半全场影子观察单联赛名列一直是空的——用户反馈后核查发现。match_id_internal
            # 就是unified_matches.unified_id，改成JOIN过去取真实联赛名，不改predict_football.py
            # 写入侧(不确定改了会不会影响其他消费者)，只在这个展示读取点上修，风险更低。
            _htft_rows = _htft_conn.execute(text("""
                SELECT mps.match_id_internal, COALESCE(NULLIF(mps.league_code, ''), um.league_name, ''),
                       mps.home_team_name_std, mps.away_team_name_std,
                       mps.kickoff_local, mps.selection_name, mps.model_prob
                FROM market_prediction_snapshot mps
                LEFT JOIN unified_matches um ON um.unified_id = mps.match_id_internal
                WHERE mps.match_date=:fd AND mps.market_group='HTFT'
            """), {"fd": fetch_date}).fetchall()
    except Exception as _e:
        _htft_rows = []
        log.warning(f"  半全场信号读取异常（跳过）: {_e}")

    _htft_by_match: dict = {}
    for _uid_h, _lg_h, _h_h, _a_h, _ko_h, _sel_h, _p_h in _htft_rows:
        _htft_by_match.setdefault((_uid_h, _lg_h, _h_h, _a_h, _ko_h), []).append((_sel_h, _p_h))

    # 联赛白名单过滤(2026-09-01新增)：2026-08-25~08-31一周49场联网核实真实结算样本
    # 发现命中率按联赛量级分裂明显——大联赛(西甲/荷甲/德甲/德甲女足/奥甲/奥甲女足/
    # 比利时甲)命中率44.0%(11胜14负)，沙特联/乌兹别克联/巴林联/埃及联/阿曼联/
    # 英格兰非联赛级/各种U21热身赛这类联赛只有15.8%(3胜16负)。根因是htft联合概率
    # 模型靠球队历史进球/失球统计驱动，这些冷门联赛在football_team_stats里样本
    # 本身稀薄，模型给出的"半场主胜+全场主胜"更接近默认猜测而非真实校准信号，
    # 属于CLAUDE.md"推荐单数据支撑规则"里点名的"退化成兜底占位数字但格式跟真信号
    # 一样"陷阱。全历史(07-19~08-24)结算积压263条尝试自动结算全部失败(0/37天，
    # 半场比分数据源本身缺失，非结算逻辑问题)，没法凑够更大样本验证，先用这一周
    # 的样本(44.0% vs 15.8%，差距3倍)作为依据加这道白名单过滤，只保留统计基础
    # 扎实的联赛，之后随样本积累可以再调整名单。
    _HTFT_LEAGUE_WHITELIST = {
        "spain - la liga", "laliga", "netherlands - eredivisie", "eredivisie",
        "germany - bundesliga", "bundesliga", "germany - bundesliga women",
        "austria - bundesliga", "austria - bundesliga women", "belgium - pro league",
    }
    # 无过滤平行线(2026-09-01新增)：跟_htft_shadow_multi同一批候选，不套联赛白名单，
    # 用户要求每天跟过滤版对比命中率/ROI，验证这道过滤实际效果，见generate_recommendations()
    # 里shadow_multi["htft_nofilter"]说明。
    #
    # Bug修复(2026-09-02)：用户报告投注单里混入了已经开赛/结束的比赛（Helsingborgs
    # vs Orebro SK，kickoff=2026-09-01T17:00:00Z，报告生成时(09-02 13:07北京)早已开赛
    # 12小时）。查明这条候选来自market_prediction_snapshot(market_group='HTFT')，
    # 这张表只按match_date过滤(WHERE mps.match_date=:fd)，从未像generate_recommendations()
    # 主窗口查询那样额外核对kickoff_utc是否已经过了当前时间——跟CLAUDE.md"企鹅体育开赛
    # 时间处理规则"记录的2026-07-13那次bug是同一类缺陷(只不过这次出现在predict_football.py
    # 写入的HTFT快照这条独立数据源上，不是qiety)。这里补上跟主窗口query一致的实时
    # kickoff核对(now_utc < kickoff <= 次日12:00北京)，不管上游market_date字段语义
    # 是否精确，都能把已经开赛的比赛从htft/htft_nofilter两个观察桶里剔除。
    _bj_tz_h = timezone(timedelta(hours=8))
    _now_utc_h = datetime.now(timezone.utc)
    _win_end_utc_h = (datetime.strptime(fetch_date, "%Y-%m-%d") + timedelta(days=1)) \
        .replace(hour=12, minute=0, second=0, tzinfo=_bj_tz_h).astimezone(timezone.utc)

    def _htft_kickoff_in_window(_ko_raw: str) -> bool:
        if not _ko_raw:
            return False
        try:
            _dt_h = datetime.fromisoformat(_ko_raw.replace("Z", "+00:00"))
            if _dt_h.tzinfo is None:
                _dt_h = _dt_h.replace(tzinfo=timezone.utc)
        except Exception:
            return False
        return _now_utc_h < _dt_h <= _win_end_utc_h

    _htft_nofilter_shadow_multi: dict = {}
    for (_uid_h, _lg_h, _h_h, _a_h, _ko_h), _sels_h in _htft_by_match.items():
        if not _htft_kickoff_in_window(_ko_h):
            continue
        _best_sel_h, _best_p_h = max(_sels_h, key=lambda x: x[1])
        # 9选1均匀基线约0.111，明显低于这个说明模型对这场没有偏好，不值得观察
        if not _best_p_h or _best_p_h < 0.15:
            continue
        _htft_entry = {
            "unified_id": _uid_h, "sport_code": "football", "league_name": _lg_h,
            "home_team": _h_h, "away_team": _a_h, "kickoff_utc": _ko_h,
            "market": "ht_ft", "outcome": _best_sel_h,
            "handicap": None, "best_odds": round(1 / _best_p_h, 4),
            "model_prob": round(_best_p_h, 4), "kelly_fraction": 0.0,
            "hit_score": round(_best_p_h, 4), "predicted_score": "-",
            "fetch_date": fetch_date,
        }
        _htft_nofilter_shadow_multi[(_uid_h, "ht_ft", _best_sel_h)] = {**_htft_entry, "shadow_type": "htft_nofilter"}
        if (_lg_h or "").strip().lower() in _HTFT_LEAGUE_WHITELIST:
            _htft_shadow_multi[(_uid_h, "ht_ft", _best_sel_h)] = {**_htft_entry, "shadow_type": "htft"}
    if _htft_shadow_multi:
        log.info(f"  半全场(HT/FT)信号影子观察: {len(_htft_shadow_multi)} 条（无过滤平行线: {len(_htft_nofilter_shadow_multi)} 条）")

    log.info("\n🎯 第四阶段：命中评分 & 投注单生成...")
    recs, _desk_file = generate_recommendations(fetch_date, precomputed=True,
                                     precomputed_corner_shadow=_corner_shadow_multi,
                                     precomputed_htft_shadow=_htft_shadow_multi,
                                     precomputed_htft_nofilter_shadow=_htft_nofilter_shadow_multi,
                                     precomputed_corner_recs=corner_recs)

    # 足球球队大小/小球"老逻辑"平行线(2026-08-01新增，用户要求)——跟当前正式
    # 推荐单完全独立，见_generate_legacy_team_total_under()说明。放在
    # generate_recommendations()之后，因为它读的team_total_shadow_full是
    # generate_recommendations()这次运行刚写好的。
    try:
        _generate_legacy_team_total_under(fetch_date)
    except Exception as _e:
        log.warning(f"  老逻辑平行线(足球球队大小/小球)生成异常（跳过）: {_e}")

    # 篮球小球/独赢"反着买"转正平行线(2026-08-01新增，用户要求)——同样独立于
    # 正式推荐单，见_generate_basketball_under_fade()/_generate_basketball_moneyline_fade()
    # 说明。放在generate_recommendations()之后，因为读的under_shadow_bets/
    # shadow_recommendations都是这次运行刚写好的。
    try:
        _generate_basketball_under_fade(fetch_date)
    except Exception as _e:
        log.warning(f"  篮球小球反着买平行线生成异常（跳过）: {_e}")
    try:
        _generate_basketball_moneyline_fade(fetch_date)
    except Exception as _e:
        log.warning(f"  篮球独赢反着买平行线生成异常（跳过）: {_e}")

    # 反着买人工批准转正(2026-08-03从generate_recommendations()内部挪到这里，见
    # _generate_and_display_fade_manual()docstring说明的执行顺序bug修复)——必须
    # 放在上面两个_generate_basketball_*_fade()调用之后，此时两张fade表才是这次
    # 运行的新数据。写入hit_recommendations + 打印/保存详细说明都在这个函数里。
    try:
        _generate_and_display_fade_manual(fetch_date, _desk_file)
    except Exception as _e:
        log.warning(f"  反着买人工批准转正异常（跳过）: {_e}")

    # 联赛让球盘客队+方向市场edge(2026-08-27新增，见_generate_league_ah_edge()
    # docstring)——独立于反着买机制，同样是人工批准非算法验证，紧跟在
    # fade_manual之后执行，两者互不依赖。
    try:
        _generate_league_ah_edge(fetch_date)
        _generate_and_display_league_ah_edge(fetch_date, _desk_file)
    except Exception as _e:
        log.warning(f"  联赛让球盘客队+方向edge生成异常（跳过）: {_e}")

    # 平行线展示(2026-08-02从generate_recommendations()内部挪到这里，见
    # _display_parallel_lines()docstring说明的执行顺序bug修复)——必须放在上面
    # 三个_generate_*调用之后，此时legacy_team_total_under_recs等表才是这次
    # 运行的新数据，不是运行开始前的旧数据。
    try:
        _display_parallel_lines(fetch_date, _desk_file)
    except Exception as _e:
        log.warning(f"  平行线展示异常（跳过）: {_e}")

    # FotMob三桶(角球/球队大小/大小球)串关推荐(2026-08-20用户要求的永久规则)——
    # 放在_display_parallel_lines()之后，同样是因为读的shadow_recommendations
    # 三个FotMob桶是generate_recommendations()这次运行刚写好的新数据。见
    # _generate_fotmob_parlay()说明。
    try:
        _generate_fotmob_parlay(fetch_date, _desk_file)
    except Exception as _e:
        log.warning(f"  FotMob串关推荐生成异常（跳过）: {_e}")

    log.info("\n📸 第五阶段：赔率快照保存...")
    save_odds_snapshots(fetch_date)

    log.info("\n📈 第六阶段：CLV（收盘线价值）计算...")
    compute_clv(fetch_date)

    log.info("\n📋 第七阶段：赛果自动回填...")
    # Bug修复：禁止 importlib 动态导入独立模块（规范：独立子进程运行）
    try:
        import subprocess as _sp_settle
        _settle_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "21_auto_settle.py")
        # Bug修复(2026-08-14)：原 timeout=300 小于 21_auto_settle.py 自身 __main__
        # 入口内部两个角球补抓子进程(各300s超时，最坏情况串行600s)的耗时，真正的
        # auto_settle()等结算函数经常在被杀之前都没轮到执行——跟 _daily_settle.py
        # (每天22:30计划任务)里同一个调用点是完全同一类bug，一并修（见该文件
        # 2026-08-14注释）。改成1800s。
        _r_settle = _sp_settle.run(
            [sys.executable, "-X", "utf8", _settle_path, "--date", fetch_date],
            timeout=1800, cwd=_os.path.dirname(_os.path.abspath(__file__)),
            stdout=_sp_settle.PIPE, stderr=_sp_settle.PIPE
        )
        if _r_settle.returncode != 0:
            _err_tail = (_r_settle.stderr or b"")[-200:].decode("utf-8", errors="replace").strip()
            log.warning(f"  赛果回填异常: exit {_r_settle.returncode}: {_err_tail}")
        else:
            log.info("  ✅ 赛果自动回填完成")
    except Exception as _e:
        log.warning(f"  赛果回填异常: {_e}")

    log.info("\n📊 第八阶段：竞彩官方赔率分歧度追踪（纯观察，不影响推荐单）...")
    # 2026-08-05新增：把42号爬虫(okooo镜像的竞彩官方赔率)跟consensus_odds做联赛+
    # 开赛时间匹配，记进jingcai_divergence_log，为以后"多源分歧度能否当特征/风控
    # 信号"的显著性回测积累样本(当天回测n=74不显著，见项目记忆)。纯观察脚本，
    # 用subprocess隔离(不用importlib，见项目记忆feedback_scraper_launch)，任何
    # 异常都不影响上面已经生成好的推荐单。
    try:
        import subprocess as _sp_jc
        _jc_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "_jingcai_divergence_tracker.py")
        _r_jc = _sp_jc.run(
            [sys.executable, "-X", "utf8", _jc_path, "--date", fetch_date],
            timeout=120, cwd=_os.path.dirname(_os.path.abspath(__file__)),
            stdout=_sp_jc.PIPE, stderr=_sp_jc.PIPE
        )
        if _r_jc.returncode != 0:
            _err_tail_jc = (_r_jc.stderr or b"")[-200:].decode("utf-8", errors="replace").strip()
            log.warning(f"  竞彩分歧度追踪异常: exit {_r_jc.returncode}: {_err_tail_jc}")
        else:
            _out_tail_jc = (_r_jc.stdout or b"").decode("utf-8", errors="replace").strip()
            log.info(f"  {_out_tail_jc}")
    except Exception as _e:
        log.warning(f"  竞彩分歧度追踪异常: {_e}")

    return recs


def run(run_scrapers: bool = True, skip_slow_scrapers: bool = False,
        fetch_date: str | None = None):
    """
    完整运行命中系统
    run_scrapers         : 是否先运行所有爬虫
    skip_slow_scrapers   : 跳过耗时爬虫
    fetch_date           : 指定日期（默认今日）

    generate_recommendations() 内部的比赛筛选窗口本就是「今日全部未开赛 + 次日12:00前」，
    单次调用已覆盖两天，因此只跑一次即可得到一份合并的推荐单/落库记录，
    不再需要对次日单独重复调用（避免同一场比赛在两个 fetch_date 下被重复推荐/写库）。
    """
    start = datetime.now()
    if fetch_date is None:
        fetch_date = start.strftime("%Y-%m-%d")

    log.info("="*60)
    log.info(f"  🏆 命中系统启动  [{fetch_date}]（今日+次日12:00前，合并一份推荐单）")
    log.info("="*60)

    recs = _run_one_date(fetch_date, run_scrapers, skip_slow_scrapers)

    # FIX-008.1：未映射中文队名收尾落 data_quality_issue_log（同日同队幂等）
    try:
        _flush_unmapped_cn_teams(fetch_date)
    except Exception as _e:
        log.warning(f"  ⚠ 未映射中文队名收尾落库失败: {type(_e).__name__}: {_e}")

    # FIX-005.3：跑批收尾数据新鲜度监控（核心表1天/辅助表7天阈值，超阈值写
    # data_quality_issue_log）。检查失败不静默、不掩盖主流程结果。
    try:
        from freshness_check import run_freshness_check
        _stale = run_freshness_check()
        if _stale:
            log.warning(f"  ⚠ 数据新鲜度: {len(_stale)} 个表超阈值（已写 data_quality_issue_log）")
            for _s in _stale:
                log.warning(f"    [{_s['kind']}] {_s['msg']}")
        else:
            log.info("  ✅ 数据新鲜度检查通过")
    except Exception as _e:
        log.warning(f"  ⚠ 数据新鲜度检查本身失败: {type(_e).__name__}: {_e}")

    elapsed = (datetime.now() - start).total_seconds()
    log.info(f"\n✅ 命中系统完成！耗时 {elapsed:.1f}s，合计推荐 {len(recs)} 条")

    return recs


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="命中系统主控")
    parser.add_argument("--no-scrape",   action="store_true", help="跳过爬虫，只做整合")
    parser.add_argument("--fast",        action="store_true", help="跳过慢速爬虫")
    parser.add_argument("--date",        default=None,        help="指定日期 YYYY-MM-DD（默认今日）")
    args = parser.parse_args()

    run(
        run_scrapers       = not args.no_scrape,
        skip_slow_scrapers = args.fast,
        fetch_date         = args.date,
    )
