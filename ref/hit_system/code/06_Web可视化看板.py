# 06_Web可视化看板.py — Streamlit 全球体育量化系统看板
import streamlit as st
import pandas as pd
import json, os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from config import DB_ENGINE_URL, HIT_SCORE_GLOBAL_THRESHOLD

engine = create_engine(DB_ENGINE_URL)

st.set_page_config(page_title="全球双体育量化系统", layout="wide")
st.title("全球双体育七层融合量化分析系统")


def safe_read(sql: str) -> pd.DataFrame:
    try:
        return pd.read_sql(sql, engine)
    except Exception:
        return pd.DataFrame()


def metric_value(df: pd.DataFrame, col: str, default="-"):
    if df.empty or col not in df.columns:
        return default
    return df[col].iloc[0]


tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10 = st.tabs([
    "预测结果", "预测快照", "串关推荐", "仓位分配", "回测报告",
    "命中追踪", "基础数据", "套利机会", "足球原始数据", "复盘看板",
])

with tab1:
    dfs1 = safe_read("SELECT * FROM prediction_snapshot ORDER BY id DESC LIMIT 500")
    dfs2 = safe_read("SELECT * FROM basketball_prediction LIMIT 500")
    if not dfs1.empty or not dfs2.empty:
        st.subheader("新表 prediction_snapshot（主流水线输出）")
        if not dfs1.empty:
            st.metric("快照记录", len(dfs1))
            st.dataframe(dfs1, use_container_width=True)
        else:
            st.info("prediction_snapshot 无数据，请先运行 run_today_prediction.py")
        with st.expander("旧表 basketball_prediction（兼容）"):
            if not dfs2.empty:
                st.dataframe(dfs2, use_container_width=True)
            else:
                st.info("旧表无数据")
    else:
        st.info("暂无预测数据，请先运行 run_today_prediction.py")

with tab2:
    df = safe_read("SELECT * FROM prediction_snapshot ORDER BY id DESC")
    if df.empty:
        st.info("暂无预测快照，请先运行 run_today_prediction.py")
    else:
        st.metric("快照记录", len(df))
        st.dataframe(df, use_container_width=True)

with tab3:
    df = safe_read("SELECT * FROM combination_result ORDER BY comb_kelly DESC")
    if df.empty:
        st.info("暂无串关推荐，请先运行 05_7_Combination_Optimize_Module.py")
    else:
        st.dataframe(df, use_container_width=True)

with tab4:
    df = safe_read("SELECT * FROM capital_allocation ORDER BY kelly DESC")
    if df.empty:
        st.info("暂无仓位数据，请先运行 05_8_Kelly_Capital_Allocation_Module.py")
    else:
        st.metric("推荐注单数", len(df))
        st.dataframe(df, use_container_width=True)

with tab5:
    col1, col2 = st.columns([1, 2])
    with col1:
        df_bt = safe_read("SELECT * FROM backtest_summary")
        if not df_bt.empty:
            st.metric("胜率", f"{metric_value(df_bt, 'win_rate', 0):.1%}")
            st.metric("最终资金", f"¥{metric_value(df_bt, 'final_capital', 0):,.0f}")
            st.metric("最大回撤", f"{metric_value(df_bt, 'max_drawdown', 0):.1%}")
            st.metric("夏普比率", f"{metric_value(df_bt, 'sharpe_ratio', 0):.2f}")
        else:
            st.info("暂无回测数据")
    with col2:
        df_curve = safe_read("SELECT capital_curve FROM backtest_curve")
        if not df_curve.empty and "capital_curve" in df_curve.columns:
            st.line_chart(df_curve["capital_curve"])

with tab6:
    st.subheader("🎯 命中追踪（真实预测 vs 实际结果）")
    df_hit = safe_read("""
        SELECT sport_code, match_date, home_team_name_std, away_team_name_std,
               best_pick, best_odds, confidence_grade, is_hit, actual_result,
               actual_home_score, actual_away_score, result_verified_at
        FROM prediction_snapshot
        WHERE is_hit IS NOT NULL
        ORDER BY result_verified_at DESC
        LIMIT 1000
    """)
    if df_hit.empty:
        st.info("暂无命中回写数据，请先运行 run_today_prediction.py（Step 7 自动回写）")
    else:
        total = len(df_hit)
        hits = int(df_hit["is_hit"].sum())
        rate = hits / total if total > 0 else 0
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("记录数", total)
        col2.metric("命中", hits)
        col3.metric("命中率", f"{rate:.1%}")
        col4.metric("平均赔率", f"{df_hit['best_odds'].mean():.2f}" if "best_odds" in df_hit.columns and not df_hit['best_odds'].isna().all() else "-")

        st.subheader("按运动类型")
        for sport in df_hit["sport_code"].unique():
            sub = df_hit[df_hit["sport_code"] == sport]
            st.metric(sport, f"{int(sub['is_hit'].sum())}/{len(sub)} ({int(sub['is_hit'].sum())/max(len(sub),1):.1%})")

        st.subheader("按置信度等级")
        if "confidence_grade" in df_hit.columns:
            grade_df = df_hit.groupby("confidence_grade").agg(
                场次=("is_hit", "count"), 命中=("is_hit", "sum")
            ).assign(命中率=lambda x: x["命中"] / x["场次"])
            st.dataframe(grade_df.style.format({"命中率": "{:.1%}"}), use_container_width=True)

        st.subheader("近期明细")
        show_cols = ["match_date", "sport_code", "home_team_name_std", "away_team_name_std",
                     "best_pick", "best_odds", "is_hit", "actual_result", "actual_home_score", "actual_away_score"]
        show_cols = [c for c in show_cols if c in df_hit.columns]
        st.dataframe(df_hit[show_cols].head(50), use_container_width=True)

with tab7:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("球队战力")
        df = safe_read("SELECT * FROM basketball_team_stats ORDER BY win_rate DESC")
        st.dataframe(df, use_container_width=True)
    with col2:
        st.subheader("联赛大小分基准")
        df = safe_read("SELECT * FROM basketball_league_ou ORDER BY avg_total DESC")
        st.dataframe(df, use_container_width=True)

with tab8:
    df = safe_read("SELECT * FROM arbitrage_opportunities ORDER BY arb_profit_pct DESC")
    if df.empty:
        st.info("暂无套利数据，请先运行 03_实时赔率抓取.py")
    else:
        st.metric("套利机会数", len(df))
        st.dataframe(df, use_container_width=True)

with tab9:
    df = safe_read("SELECT * FROM football_matches ORDER BY match_date DESC LIMIT 500")
    if df.empty:
        st.info("暂无足球数据，请先运行 01_初始化全量数据.py")
    else:
        count_df = safe_read("SELECT COUNT(*) as c FROM football_matches")
        st.metric("总比赛数", metric_value(count_df, 'c', 0))
        if "league" in df.columns:
            league_filter = st.selectbox("联赛筛选", ["全部"] + sorted(df["league"].dropna().unique().tolist()))
            if league_filter != "全部":
                df = df[df["league"] == league_filter]
        st.dataframe(df, use_container_width=True)


# ── 复盘看板 ──────────────────────────────────────────────────────────────────
with tab10:
    st.subheader("复盘看板 — 胜率 / ROI / 命中分校准")

    # ── 校准状态 ──────────────────────────────────────────
    _state_file    = os.path.join(os.path.dirname(__file__), '_calibration_state.json')
    _override_file = os.path.join(os.path.dirname(__file__), '_param_overrides.json')

    col_a, col_b, col_c = st.columns(3)
    try:
        with open(_state_file, 'r', encoding='utf-8') as _f:
            _state = json.load(_f)
        col_a.metric("上次校准", _state.get('last_calibration_date', '从未'))
        col_b.metric("已校准次数", _state.get('calibration_count', 0))
        col_c.metric("当前阈值 HIT_SCORE", _state.get('HIT_SCORE_GLOBAL_THRESHOLD', HIT_SCORE_GLOBAL_THRESHOLD))
    except FileNotFoundError:
        col_a.metric("校准状态", "未初始化")
        col_b.metric("已校准次数", 0)
        col_c.metric("当前阈值 HIT_SCORE", HIT_SCORE_GLOBAL_THRESHOLD)

    days_opt = st.selectbox("统计区间", [30, 60, 90, 180], index=2)
    cutoff = (datetime.now() - timedelta(days=days_opt)).strftime('%Y-%m-%d')

    # ── 总览指标 ──────────────────────────────────────────
    try:
        with engine.connect() as _conn:
            _rows = _conn.execute(text("""
                SELECT market, outcome, best_odds, model_prob, hit_score, status, fetch_date
                FROM hit_recommendations
                WHERE status IN ('win','lose','push')
                  AND fetch_date >= :cutoff
                  AND best_odds BETWEEN 1.20 AND 20.0
                ORDER BY fetch_date
            """), {'cutoff': cutoff}).fetchall()
    except Exception as _e:
        _rows = []
        st.warning(f"数据库读取失败: {_e}")

    if not _rows:
        st.info(f"近 {days_opt} 天无已结算数据，请先运行 _daily_settle.py")
    else:
        _total  = len(_rows)
        _wins   = sum(1 for r in _rows if r[5] == 'win')
        _pushes = sum(1 for r in _rows if r[5] == 'push')
        _eff    = _total - _pushes
        _wr     = _wins / _eff * 100 if _eff else 0
        _pnl    = sum((r[2]-1) if r[5]=='win' else (0 if r[5]=='push' else -1) for r in _rows)
        _roi    = _pnl / _eff * 100 if _eff else 0

        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric("总结算注数", f"{_total}")
        mc2.metric("胜率", f"{_wr:.1f}%")
        mc3.metric("ROI", f"{_roi:+.1f}%", delta=f"{_pnl:+.1f}U")
        mc4.metric("有效注数", f"{_eff}")

        # ── 按市场 ROI 表格 ────────────────────────────────
        st.markdown("#### 按市场分层")
        _mkt_data = {}
        for r in _rows:
            _mkt_data.setdefault(r[0], []).append(r)
        _mkt_rows = []
        for _m, _mrs in sorted(_mkt_data.items(), key=lambda x: -len(x[1])):
            _meff = sum(1 for r in _mrs if r[5] != 'push')
            _mwin = sum(1 for r in _mrs if r[5] == 'win')
            _mpnl = sum((r[2]-1) if r[5]=='win' else (0 if r[5]=='push' else -1) for r in _mrs)
            _mwr  = _mwin / _meff * 100 if _meff else 0
            _mroi = _mpnl / _meff * 100 if _meff else 0
            _mavg = sum(r[2] for r in _mrs) / len(_mrs)
            _mkt_rows.append({'市场': _m, '注数': len(_mrs),
                               '胜率%': round(_mwr, 1), 'ROI%': round(_mroi, 1),
                               '平均赔率': round(_mavg, 2)})
        _df_mkt = pd.DataFrame(_mkt_rows)
        st.dataframe(_df_mkt.style.format({'胜率%': '{:.1f}', 'ROI%': '{:+.1f}',
                                           '平均赔率': '{:.2f}'}), use_container_width=True)

        # ── 命中分校准表格 ─────────────────────────────────
        st.markdown("#### 命中分区间校准")
        _buckets = [(0.45,0.55),(0.55,0.65),(0.65,0.70),(0.70,0.75),(0.75,1.01)]
        _cal_rows = []
        for _lo, _hi in _buckets:
            _brows = [r for r in _rows if _lo <= r[4] < _hi]
            if len(_brows) < 3:
                continue
            _beff = sum(1 for r in _brows if r[5] != 'push')
            _bwin = sum(1 for r in _brows if r[5] == 'win')
            _bwr  = _bwin / _beff * 100 if _beff else 0
            _pavg = sum(r[3] for r in _brows) / len(_brows) * 100
            _cal_rows.append({'区间': f'[{_lo:.2f},{_hi:.2f})',
                               '注数': len(_brows), '实际胜率%': round(_bwr, 1),
                               'p融合均值%': round(_pavg, 1),
                               '校准差%': round(_bwr - _pavg, 1)})
        if _cal_rows:
            _df_cal = pd.DataFrame(_cal_rows)
            st.dataframe(_df_cal.style.format({
                '实际胜率%': '{:.1f}', 'p融合均值%': '{:.1f}', '校准差%': '{:+.1f}'
            }), use_container_width=True)

        # ── 近期每周 ROI 趋势 ─────────────────────────────
        st.markdown("#### 周度 ROI 趋势")
        _week_data = {}
        for r in _rows:
            try:
                _dt = datetime.strptime(r[6], '%Y-%m-%d')
                _wk = _dt.strftime('%Y-W%U')
                _week_data.setdefault(_wk, []).append(r)
            except Exception:
                pass
        if _week_data:
            _trend_rows = []
            for _wk in sorted(_week_data.keys()):
                _wr2 = _week_data[_wk]
                _we  = sum(1 for r in _wr2 if r[5] != 'push')
                _ww  = sum(1 for r in _wr2 if r[5] == 'win')
                _wp  = sum((r[2]-1) if r[5]=='win' else (0 if r[5]=='push' else -1) for r in _wr2)
                _trend_rows.append({'周': _wk, '注数': len(_wr2),
                                    'ROI%': round(_wp / _we * 100 if _we else 0, 1)})
            _df_trend = pd.DataFrame(_trend_rows).set_index('周')
            st.line_chart(_df_trend['ROI%'])
