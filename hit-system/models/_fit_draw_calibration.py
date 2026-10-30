# -*- coding: utf-8 -*-
# _fit_draw_calibration.py — 用全量历史真实赛果拟合足球1x2平局的等渗回归校准曲线
#
# 背景：_backtest_draw_calibration_fix.py 已经用训练/测试集分开的方法验证过，
# 等渗回归校准能在样本外(out-of-sample)数据上把edge从+2.8%提升到+4.7%（详见该文件）。
# 本脚本是生产环境实际使用的拟合器：00_命中系统.py 会在校准曲线过期(>30天未更新)时
# 自动调用 fit_and_save()，不需要人工干预。
#
# 拟合用全部可用历史数据（不再像验证阶段那样切70/30，因为验证已经做过，生产阶段
# 要用尽可能多的数据拟合出更稳的曲线）。

import sys, time, bisect, json
from collections import defaultdict
from datetime import datetime

import env_setup
from config import DB_ENGINE_URL
from db_utils import exec_ddl
from sqlalchemy import create_engine, text
from poisson_model_v2 import _compute_lambda, match_total_probs

engine = create_engine(DB_ENGINE_URL)

MIN_TRAIN_SAMPLES = 500  # 拟合样本太少时曲线不可靠，宁可不更新也不用垃圾曲线覆盖


def init_table():
    exec_ddl(engine, """
        CREATE TABLE IF NOT EXISTS draw_calibration_curve (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            fit_date         TEXT,
            breakpoints_json TEXT,
            values_json      TEXT,
            train_samples    INTEGER,
            created_at       TEXT DEFAULT (datetime('now'))
        )
    """)


MIN_BIN_SIZE = 200  # 分位数预分桶的最小样本量，防止PAVA尾部小样本产生1.0这种不可信极端值


def _prebin(xs, ys, min_bin_size=MIN_BIN_SIZE):
    """按x排序后，从头贪心地每凑够 min_bin_size 个样本切一桶，桶内取均值。
    是等渗回归标准的稳健化做法——直接对原始逐场数据跑PAVA，足球平局这种小概率事件
    在高概率尾部样本天然稀疏，几场比赛就能让PAVA给出0或1这种极端值，不可信。
    预分桶保证送进PAVA的每个点都代表足够多的真实比赛，PAVA只在桶间做单调化。"""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    x_sorted = [xs[i] for i in order]
    y_sorted = [ys[i] for i in order]
    bin_x, bin_y = [], []
    i = 0
    n = len(x_sorted)
    while i < n:
        j = min(i + min_bin_size, n)
        if n - j < min_bin_size:  # 最后一桶不够量，并入当前桶，避免尾巴太碎
            j = n
        chunk_x, chunk_y = x_sorted[i:j], y_sorted[i:j]
        bin_x.append(sum(chunk_x) / len(chunk_x))
        bin_y.append(sum(chunk_y) / len(chunk_y))
        i = j
    return bin_x, bin_y


def _fit_isotonic(xs, ys):
    """预分桶(每桶>=MIN_BIN_SIZE场) + 标准PAVA(Pool Adjacent Violators)算法"""
    bin_x, bin_y = _prebin(xs, ys)
    blocks = [[y, 1, bin_x[i], bin_x[i]] for i, y in enumerate(bin_y)]
    i = 0
    while i < len(blocks) - 1:
        if blocks[i][0] > blocks[i + 1][0] + 1e-12:
            v1, n1, lo1, hi1 = blocks[i]
            v2, n2, lo2, hi2 = blocks[i + 1]
            merged = [(v1 * n1 + v2 * n2) / (n1 + n2), n1 + n2, lo1, hi2]
            blocks[i:i + 2] = [merged]
            i = max(i - 1, 0)
        else:
            i += 1
    return [b[2] for b in blocks], [b[0] for b in blocks]


def _build_team_indices(conn):
    rows = conn.execute(text("""
        SELECT home_team, away_team, home_score, away_score, match_date, country, league_slug
        FROM match_results
        WHERE sport='football' AND home_score IS NOT NULL AND away_score IS NOT NULL
          AND match_date IS NOT NULL
        ORDER BY match_date
    """)).fetchall()
    home_games, away_games, league_games, global_games = defaultdict(list), defaultdict(list), defaultdict(list), []
    for ht, at, hs, as_, md, country, slug in rows:
        home_games[ht].append((md, hs, as_))
        away_games[at].append((md, hs, as_))
        league_games[((country or "").lower(), (slug or "").lower())].append((md, hs, as_))
        global_games.append((md, hs, as_))
    idx = {
        "home_games": home_games, "away_games": away_games,
        "league_games": league_games, "global_games": global_games,
        "home_dates": {t: [g[0] for g in v] for t, v in home_games.items()},
        "away_dates": {t: [g[0] for g in v] for t, v in away_games.items()},
        "league_dates": {k: [g[0] for g in v] for k, v in league_games.items()},
        "global_dates": [g[0] for g in global_games],
    }
    return idx


def _cutoff(dates_sorted, before_date):
    return bisect.bisect_left(dates_sorted, before_date)


def _team_stats_asof(idx, team, before_date):
    h_hist = idx["home_games"].get(team, [])[:_cutoff(idx["home_dates"].get(team, []), before_date)]
    a_hist = idx["away_games"].get(team, [])[:_cutoff(idx["away_dates"].get(team, []), before_date)]
    hc, ac = len(h_hist), len(a_hist)
    r = {"home_games": hc, "away_games": ac, "total_games": hc + ac,
         "home_attack": (sum(g[1] for g in h_hist)/hc) if hc else 1.0,
         "home_defense": (sum(g[2] for g in h_hist)/hc) if hc else 1.0,
         "away_attack": (sum(g[2] for g in a_hist)/ac) if ac else 1.0,
         "away_defense": (sum(g[1] for g in a_hist)/ac) if ac else 1.0}
    rh, ra = h_hist[-5:], a_hist[-5:]
    r["recent_home_attack"]  = (sum(g[1] for g in rh)/len(rh)) if rh else r["home_attack"]
    r["recent_home_defense"] = (sum(g[2] for g in rh)/len(rh)) if rh else r["home_defense"]
    r["recent_away_attack"]  = (sum(g[2] for g in ra)/len(ra)) if ra else r["away_attack"]
    r["recent_away_defense"] = (sum(g[1] for g in ra)/len(ra)) if ra else r["away_defense"]
    return r


def _league_baseline_asof(idx, country, slug, before_date):
    key = (country.lower(), slug.lower())
    hist = idx["league_games"].get(key, [])[:_cutoff(idx["league_dates"].get(key, []), before_date)]
    if len(hist) >= 20:
        return {"home_attack": sum(g[1] for g in hist)/len(hist), "away_attack": sum(g[2] for g in hist)/len(hist), "n": len(hist)}
    g_hist = idx["global_games"][:_cutoff(idx["global_dates"], before_date)]
    if not g_hist:
        return {"home_attack": 1.35, "away_attack": 1.1, "n": 0}
    return {"home_attack": sum(g[1] for g in g_hist)/len(g_hist), "away_attack": sum(g[2] for g in g_hist)/len(g_hist), "n": len(g_hist)}


def _p_poisson_draw(idx, home, away, league_name, before_date):
    parts = league_name.split(" - ") if " - " in league_name else [league_name, ""]
    country = parts[0].strip()
    slug = parts[1].strip().replace(" ", "-") if len(parts) > 1 else ""
    hs, as_ = _team_stats_asof(idx, home, before_date), _team_stats_asof(idx, away, before_date)
    baseline = _league_baseline_asof(idx, country, slug, before_date)
    lam_h, lam_a, _ = _compute_lambda(hs, as_, baseline)
    return match_total_probs(lam_h, lam_a)["1x2"]["draw"]


def fit_and_save(fetch_date: str | None = None) -> dict:
    """用全部可用历史数据拟合等渗回归曲线并存库。返回拟合摘要dict。"""
    if fetch_date is None:
        fetch_date = datetime.now().strftime("%Y-%m-%d")

    init_table()
    t0 = time.time()

    with engine.connect() as conn:
        idx = _build_team_indices(conn)
        rows = conn.execute(text("""
            SELECT home_team, away_team, league_name, psh, psd, psa, ftr, match_date
            FROM fd_matches
            WHERE psd IS NOT NULL AND psh IS NOT NULL AND psa IS NOT NULL
              AND ftr IS NOT NULL
            ORDER BY match_date
        """)).fetchall()

    xs, ys = [], []
    for home, away, league, psh, psd, psa, ftr, mdate in rows:
        try:
            p_book = 1.0 / psd
            p_pois = _p_poisson_draw(idx, home, away, league or "", mdate)
            fused = 0.5 * p_book + 0.5 * p_pois
            xs.append(fused)
            ys.append(1.0 if ftr == 'D' else 0.0)
        except Exception:
            continue

    n = len(xs)
    if n < MIN_TRAIN_SAMPLES:
        return {"ok": False, "reason": f"样本不足({n}<{MIN_TRAIN_SAMPLES})，跳过本次拟合，沿用上一版曲线"}

    breakpoints, values = _fit_isotonic(xs, ys)

    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO draw_calibration_curve (fit_date, breakpoints_json, values_json, train_samples)
            VALUES (:fd, :bp, :vl, :n)
        """), {
            "fd": fetch_date,
            "bp": json.dumps(breakpoints),
            "vl": json.dumps(values),
            "n": n,
        })

    elapsed = time.time() - t0
    return {"ok": True, "train_samples": n, "segments": len(breakpoints), "elapsed": round(elapsed, 1)}


if __name__ == "__main__":
    import sys as _sys
    result = fit_and_save()
    print(result)
    if not result.get("ok"):
        _sys.exit(1)
