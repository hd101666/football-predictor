# -*- coding: utf-8 -*-
"""
leagues.py — 统一联赛路径映射（Flashscore 管道格式）

合并自 08/09/10/11 四个爬虫的 FOOTBALL_LEAGUES / BASKETBALL_LEAGUES 字典。
所有爬虫统一从此处导入，避免重复定义。

注意：不同数据源对同一联赛可能使用不同的路径 slug：
  - liga-portugal  (Flashscore / Soccerway 原始路径)
  - prima-liga     (OddsPortal / BetExplorer 原始路径)
  两个路径都映射到同一个 league_code = "liga_portugal"，两个都保留以保证兼容。
"""

# ─── 足球联赛路径 → league_code ──────────────────────────────────────────────
FLASHSCORE_FOOTBALL_LEAGUES = {
    "/football/england/premier-league/":        "premier_league",
    "/football/england/championship/":          "championship",
    "/football/spain/laliga/":                  "laliga",
    "/football/germany/bundesliga/":            "bundesliga",
    "/football/italy/serie-a/":                 "serie_a",
    "/football/france/ligue-1/":                "ligue_1",
    "/football/netherlands/eredivisie/":        "eredivisie",
    # 葡超：Flashscore/Soccerway 用 liga-portugal，OddsPortal/BetExplorer 用 primeira-liga
    "/football/portugal/liga-portugal/":        "liga_portugal",
    "/football/portugal/primeira-liga/":        "liga_portugal",
    "/football/turkey/super-lig/":              "super_lig",
    "/football/usa/mls/":                       "mls",
    "/football/brazil/serie-a/":                "serie_a_br",
    "/football/argentina/primera-division/":    "liga_argentina",
    "/football/russia/premier-league/":         "rpl",
    "/football/china/super-league/":            "csl",
    "/football/japan/j1-league/":               "j1",
    "/football/south-korea/k-league-1/":        "k_league_1",
    "/football/europe/champions-league/":       "ucl",
    "/football/europe/europa-league/":          "uel",
    "/football/europe/europa-conference-league/": "uecl",
}

# ─── 篮球联赛路径 → league_code ──────────────────────────────────────────────
FLASHSCORE_BASKETBALL_LEAGUES = {
    # 北美
    "/basketball/usa/nba/":                             "nba",
    "/basketball/usa/wnba/":                            "wnba",
    # 欧洲顶级赛事
    "/basketball/europe/euroleague/":                   "euroleague",
    "/basketball/europe/admiralbet-aba-league/":        "aba_league",
    "/basketball/europe/bnxt-league/":                  "bnxt",
    # 欧洲联赛
    "/basketball/spain/acb/":                           "acb",
    "/basketball/turkey/super-lig/":                    "turkey_sl",
    "/basketball/greece/basket-league/":                "greece_bl",
    "/basketball/russia/vtb-united-league/":            "vtb",
    "/basketball/france/lnb/":                          "france_lnb",
    "/basketball/germany/bbl/":                         "germany_bbl",
    "/basketball/italy/lega-a/":                        "italy_lega_a",
    "/basketball/israel/super-league/":                 "israel_sl",
    "/basketball/lithuania/lkl/":                       "lkl",
    "/basketball/poland/basket-liga/":                  "poland_bl",
    "/basketball/serbia/superleague/":                  "serbia_sl",
    "/basketball/croatia/premijer-liga/":               "croatia_pl",
    # 亚太
    "/basketball/china/cba/":                           "cba",
    "/basketball/australia/nbl/":                       "australia_nbl",
    "/basketball/new-zealand/nbl/":                     "nz_nbl",
    "/basketball/taiwan/tpbl/":                         "taiwan_tpbl",
    # 美洲
    "/basketball/brazil/nbb/":                          "brazil_nbb",
    "/basketball/argentina/liga-a/":                    "argentina_la",
    # 中东/非洲
    "/basketball/lebanon/division-1/":                  "lebanon_d1",
    "/basketball/africa/bal/":                          "africa_bal",
}

# ─── 向后兼容别名（供爬虫文件直接 import）──────────────────────────────────────
FOOTBALL_LEAGUES = FLASHSCORE_FOOTBALL_LEAGUES
BASKETBALL_LEAGUES = FLASHSCORE_BASKETBALL_LEAGUES
