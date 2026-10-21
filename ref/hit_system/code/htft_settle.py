# -*- coding: utf-8 -*-
"""半全场(HT/FT)结果判定 —— 21_auto_settle.py 和 backtest_engine.py 共用同一份逻辑，
避免两处分别维护判定代码产生不一致（这两个文件的市场判定历史上就是分别维护的两份，
21_auto_settle.py 里能看到不少"Bug修复"注释，起因都是两边各自维护、行为逐渐分叉）。
"""


def classify_ht_ft(home_score_ht, away_score_ht, home_score, away_score):
    """返回 (ht_result, ft_result)，各自 ∈ {'home','draw','away'}。
    任一比分缺失（半场比分/全场比分没到位）返回 (None, None)，调用方应视为未结算。"""
    if home_score_ht is None or away_score_ht is None:
        return None, None
    if home_score is None or away_score is None:
        return None, None
    try:
        hs_ht, as_ht = int(home_score_ht), int(away_score_ht)
        hs, as_ = int(home_score), int(away_score)
    except (TypeError, ValueError):
        return None, None
    ht_r = "home" if hs_ht > as_ht else ("away" if hs_ht < as_ht else "draw")
    ft_r = "home" if hs > as_ else ("away" if hs < as_ else "draw")
    return ht_r, ft_r
