# -*- coding: utf-8 -*-
"""独立比分/投注单全中文统一格式报告脚本——2026-08-20用户要求，不修改00_命中系统.py，
不修改已生成的原始txt文件。

2026-08-20第二版重构：第一版是纯文本替换（读原txt→翻译剩余英文→存新txt），但用户
进一步要求"所有表格都要重新排版成统一格式"（序/开赛时间/联赛/主队/客队/市场/方向/
赔率/p融合/K₁/₄/命中分/比分预测这11列，跟CLAUDE.md"投注单标准格式"一致）——原文件
里不同区块（小球/大球候选观察单、角球候选观察单、比分候选观察单、FotMob串关推荐单等）
列结构互不相同，纯文本替换没法做列重排，而且原文件本身是定宽列会截断队名/联赛名，
按位置解析截断文本取不到完整队名。改成直接从数据库按fetch_date查询每个区块对应的
原始表（hit_recommendations/corner_recommendations/under_shadow_bets/over_shadow_bets/
shadow_recommendations），拿到未截断的完整队名/联赛名，翻译后统一按11列格式重新渲染，
不再依赖解析已生成的txt（"比分候选观察单"除外，见下方说明）。

翻译来源两层，跟第一版一致：
  1. team_zh()/league_zh()（系统自带，只读复用）
  2. _slip_zh_dict.json（本脚本专用补充词典，跟team_mapping.py完全独立，只收录
     "实际会出现在投注单里"的名字，不追求覆盖数据库全部长尾——见2026-08-20对话）

"比分候选观察单"特殊处理：correct_score候选在没转正时不进hit_recommendations，
在DB里没有持久化的表能直接查（跟其他市场不一样，其他市场未转正的候选好歹进了
shadow_recommendations(shadow_type='gated')兜底），只存在于当次运行生成的txt文件
里。本脚本改成解析最新投注单txt文件里"比分候选观察单/比分投注单"这一个区块（脚本
自己控制这个区块的生成格式，见00_命中系统.py的_generate_correct_score_recs()调用
处），提取比分候选后同样按11列格式重新渲染，不影响其它区块走纯DB查询这条路。

用法:
  python -X utf8 _translate_slip_zh.py                     # 默认取今天fetch_date
  python -X utf8 _translate_slip_zh.py --date 2026-08-20
  python -X utf8 _translate_slip_zh.py --audit --date 2026-08-20
      # 只扫描当天数据库里出现过、且真的会印进报告、但词典还没覆盖的球队/联赛名，
      # 不生成报告——用来逐日扩充_slip_zh_dict.json
"""
import sys, os, json, re, glob, argparse
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_DICT_PATH = os.path.join(_BASE_DIR, "_slip_zh_dict.json")
_SLIP_DIR = r"D:\lucky"
_DB_PATH = os.path.join(_BASE_DIR, "data", "sports_data.db")

_W_TIME, _W_LEAGUE, _W_TEAM, _W_MARKET, _W_DIR = 14, 16, 16, 8, 10
_HEADER = (f"  {'序':>3}  {'开赛时间':<{_W_TIME}}{'联赛':<{_W_LEAGUE}}{'主队':<{_W_TEAM}}{'客队':<{_W_TEAM}}"
           f" {'市场':<{_W_MARKET}} {'方向':<{_W_DIR}} {'赔率':<6} {'p融合':<7} {'K₁/₄':<7} {'命中分':<8} 比分预测")
_SEP = "─" * 138


# ─── 词典 / 翻译 ────────────────────────────────────────────────────────────
def load_dict():
    with open(_DICT_PATH, encoding="utf-8") as f:
        d = json.load(f)
    return d.get("teams", {}), d.get("leagues", {}), d.get("outcomes", {})


def _load_hs_module():
    import importlib.util as _iu
    spec = _iu.spec_from_file_location("_hs_zh", os.path.join(_BASE_DIR, "00_命中系统.py"))
    hs = _iu.module_from_spec(spec)
    spec.loader.exec_module(hs)
    return hs


class Translator:
    """封装team_zh()/league_zh()(只读复用系统自带的) + 补充词典，供本脚本所有
    区块统一调用，保证同一个队名/联赛名在整份报告里翻译结果一致。"""

    def __init__(self, teams_dict, leagues_dict, outcomes_dict):
        sys.path.insert(0, _BASE_DIR)
        from team_zh import team_zh as _team_zh
        self._team_zh = _team_zh
        self._hs = _load_hs_module()
        self.teams_dict = teams_dict
        self.leagues_dict = leagues_dict
        self.outcomes_dict = outcomes_dict

    def team(self, name: str) -> str:
        if not name:
            return name
        zh = self._team_zh(name)
        if zh != name:
            return zh
        return self.teams_dict.get(name, name)

    def league(self, name: str) -> str:
        if not name:
            return name
        for kw, zh in self._hs._LEAGUE_ZH:
            if kw.lower() in name.lower():
                return zh
        return self.leagues_dict.get(name, name)

    _MARKET_EXTRA = {"1x2": "独赢", "lstm_1x2": "独赢", "fotmob_1x2": "独赢"}

    def market(self, market: str) -> str:
        if market in self._hs._MARKET_ZH:
            return self._hs._MARKET_ZH[market]
        return self._MARKET_EXTRA.get(market, market)

    def outcome(self, outcome: str) -> str:
        if outcome in self.outcomes_dict:
            return self.outcomes_dict[outcome]
        return self._hs._OUTCOME_ZH.get(outcome, outcome)


# ─── 格式化工具（跟00_命中系统.py展示层同一套算法，独立实现，只读不改系统）──
def _tw(name: str, width: int) -> str:
    result, w = "", 0
    for ch in name or "":
        cw = 2 if ord(ch) > 127 else 1
        if w + cw > width:
            break
        result += ch
        w += cw
    return result + " " * (width - w)


def _fmt_time(kickoff_utc: str) -> str:
    try:
        s = (kickoff_utc or "").replace(" ", "T")
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        bj = dt.astimezone(timezone(timedelta(hours=8)))
        return bj.strftime("%m月%d日%H:%M")
    except Exception:
        return "--月--日--:--"


def _num(v, fmt):
    return format(v, fmt) if v is not None else "-"


def render_row(seq, kickoff_utc, league_zh, home_zh, away_zh, market_zh, direction_zh,
                odds, p_fusion, kelly, hit_score, score):
    return (f"  {seq:>3}.  {_tw(_fmt_time(kickoff_utc), _W_TIME)}{_tw(league_zh, _W_LEAGUE)}"
            f"{_tw('[主]' + home_zh, _W_TEAM)}{_tw('[客]' + away_zh, _W_TEAM)}"
            f" {market_zh:<{_W_MARKET}} {direction_zh:<{_W_DIR}} {_num(odds,'.2f'):<6}"
            f" {_num(p_fusion,'.3f'):<7} {_num(kelly,'.4f'):<7} {_num(hit_score,'.3f'):<8} {score or '-'}")


def render_section(title, note, rows):
    """rows: list of dict，key跟render_row参数一致。空列表时返回空字符串(区块整体跳过)。"""
    if not rows:
        return ""
    lines = ["", "═" * 138, f"  {title}", "═" * 138, _HEADER, _SEP]
    for i, r in enumerate(rows, 1):
        lines.append(render_row(i, r["kickoff_utc"], r["league_zh"], r["home_zh"], r["away_zh"],
                                  r["market_zh"], r["direction_zh"], r.get("odds"), r.get("p_fusion"),
                                  r.get("kelly"), r.get("hit_score"), r.get("score")))
    lines.append(_SEP)
    lines.append(f"  共 {len(rows)} 条")
    if note:
        lines.append(f"  {note}")
    lines.append("═" * 138)
    return "\n".join(lines)


# ─── 比分预测查表(football_score_predictions，跟outcome/market无关的公共查表)──
def build_score_lookup(conn, fetch_date, next_date):
    cur = conn.cursor()
    cur.execute("""
        SELECT LOWER(home_team), LOWER(away_team), top_score
        FROM football_score_predictions WHERE fetch_date IN (?, ?)
    """, (fetch_date, next_date))
    return {(h, a): s for h, a, s in cur.fetchall() if s and s != "?"}


def build_full_name_lookup(conn, fetch_date, next_date):
    """"比分候选观察单"区块用：从原txt解析出来的主客队名/联赛名是截断片段，
    反查football_score_predictions拿完整未截断的名字（同时用主队+客队两个片段
    一起当匹配条件，比只用其中一个更不容易撞到别的比赛，见fetch_score_candidates()
    调用处）。返回 list[(home_full, away_full, league_full, top_score)]。"""
    cur = conn.cursor()
    cur.execute("""
        SELECT home_team, away_team, league_name, top_score
        FROM football_score_predictions WHERE fetch_date IN (?, ?)
    """, (fetch_date, next_date))
    return cur.fetchall()


# ─── 各区块数据获取：统一转成 render_row() 需要的dict list ──────────────────
def _mk_row(tr, score_lookup, kickoff_utc, league, home, away, market_zh, direction_zh,
            odds, p_fusion, kelly, hit_score, score=None):
    if score is None:
        score = score_lookup.get((home.lower(), away.lower()))
    return {
        "kickoff_utc": kickoff_utc, "league_zh": tr.league(league),
        "home_zh": tr.team(home), "away_zh": tr.team(away),
        "market_zh": market_zh, "direction_zh": direction_zh,
        "odds": odds, "p_fusion": p_fusion, "kelly": kelly, "hit_score": hit_score, "score": score,
    }


def fetch_hit_recommendations(conn, tr, score_lookup, fetch_date, exclude_fade_manual=False):
    """exclude_fade_manual=False 时只取 formula_version='fade_manual'（反着买正式
    推荐）；=True 时取除它以外的全部（正式推荐单，v1/v2等）。"""
    cur = conn.cursor()
    if exclude_fade_manual:
        cur.execute("""
            SELECT league_name, home_team, away_team, kickoff_utc, market, outcome, handicap,
                   best_odds, model_prob, kelly_fraction, hit_score
            FROM hit_recommendations WHERE fetch_date=? AND formula_version!='fade_manual'
            ORDER BY hit_score DESC
        """, (fetch_date,))
    else:
        cur.execute("""
            SELECT league_name, home_team, away_team, kickoff_utc, market, outcome, handicap,
                   best_odds, model_prob, kelly_fraction, hit_score
            FROM hit_recommendations WHERE fetch_date=? AND formula_version='fade_manual'
            ORDER BY hit_score DESC
        """, (fetch_date,))
    rows = []
    for lg, hm, aw, ko, mkt, oc, hc, odds, mp, kf, hs in cur.fetchall():
        direction = tr.outcome(oc) + (f"{hc:g}" if hc is not None else "")
        rows.append(_mk_row(tr, score_lookup, ko, lg, hm, aw, tr.market(mkt), direction, odds, mp, kf, hs))
    return rows


def fetch_corner_recommendations(conn, tr, score_lookup, fetch_date):
    cur = conn.cursor()
    cur.execute("""
        SELECT league_name, home_team, away_team, kickoff_utc, direction, line,
               odds, p_fusion, kelly, hit_score
        FROM corner_recommendations WHERE fetch_date=?
        ORDER BY hit_score DESC
    """, (fetch_date,))
    rows = []
    for lg, hm, aw, ko, direction, line, odds, pf, kelly, hs in cur.fetchall():
        dir_zh = tr.outcome(direction) + (f"{line:g}" if line is not None else "")
        rows.append(_mk_row(tr, score_lookup, ko, lg, hm, aw, "角球大小", dir_zh, odds, pf, kelly, hs))
    return rows


def fetch_under_over_shadow(conn, tr, score_lookup, fetch_date, table, direction_label):
    cur = conn.cursor()
    cur.execute(f"""
        SELECT league_name, home_team, away_team, kickoff_utc, market, handicap,
               best_odds, model_prob, kelly_fraction, hit_score
        FROM {table} WHERE fetch_date=?
        ORDER BY hit_score DESC
    """, (fetch_date,))
    rows = []
    for lg, hm, aw, ko, mkt, hc, odds, mp, kf, hs in cur.fetchall():
        dir_zh = direction_label + (f"{hc:g}" if hc is not None else "")
        rows.append(_mk_row(tr, score_lookup, ko, lg, hm, aw, tr.market(mkt), dir_zh, odds, mp, kf, hs))
    return rows


def fetch_shadow_recommendations(conn, tr, score_lookup, fetch_date, shadow_type, top_n=7):
    cur = conn.cursor()
    cur.execute("""
        SELECT league_name, home_team, away_team, kickoff_utc, market, outcome, handicap,
               best_odds, model_prob, kelly_fraction, hit_score, predicted_score
        FROM shadow_recommendations WHERE fetch_date=? AND shadow_type=?
        ORDER BY hit_score DESC LIMIT ?
    """, (fetch_date, shadow_type, top_n))
    rows = []
    for lg, hm, aw, ko, mkt, oc, hc, odds, mp, kf, hs, psc in cur.fetchall():
        dir_zh = tr.outcome(oc) + (f"{hc:g}" if hc is not None else "")
        row = _mk_row(tr, score_lookup, ko, lg, hm, aw, tr.market(mkt), dir_zh, odds, mp, kf, hs,
                       score=(psc if psc and psc not in ("-", "?") else None))
        rows.append(row)
    return rows


# ─── "比分候选观察单"：数据库没有持久化表，从最新生成的txt里解析这一个区块 ──
def find_latest_slip():
    files = [f for f in glob.glob(os.path.join(_SLIP_DIR, "投注单_*.txt"))
             if "全中文" not in os.path.basename(f)]
    if not files:
        return None
    return max(files, key=os.path.getmtime)


# Bug修复(2026-08-20)：第一版尝试用字符位置切片(比如league字段固定在原文本第
# 22-38个字符)来定位这几列——想当然假设"_tw()按显示宽度(display width，中文
# 算2)padding"等价于"按字符数(character count)切片"，对纯ASCII文本这两者刚好
# 相等所以之前没暴露问题，但这份文本里主客队名很多已经是中文（team_zh()在
# 00_命中系统.py生成原文件时已经翻过一轮），中文字符2个显示宽度只占1个字符位，
# 用固定字符数切片会切到完全错位的位置，导致整个区块一行都解析不出来（这也是
# 为什么第一次全量重构测试时"比分候选观察单"区块在最终报告里直接消失了）。
# 现在改成不依赖任何固定位置/固定宽度假设的锚点匹配：用"[主]"/"[客]"两个不会
# 被截断、必然原样出现的标记定位主客队边界；用"N-N或-"紧跟"已知有限的引擎名
# 集合(poisson_global/poisson/elo/fotmob/xG)"这个组合模式定位"预测比分+引擎"
# 字段的起点，从而反推出它前面就是客队名的结尾——不管客队名被截断成什么长度、
# 是中文还是英文，都不影响这个锚点的位置。
_CS_ENGINE_ALT = r"poisson_global|poisson|elo|fotmob|xG"
_CS_ROW_RE = re.compile(
    r"^\s*\d+\.\s+(\d{2}月\d{2}日\d{2}:\d{2})\s*"
    r"(.*?)\[主\](.*?)\[客\](.*?)"
    r"(\d+-\d+|-)\s+(?:" + _CS_ENGINE_ALT + r")\s+(.*)$"
)
_CS_PICK_RE = re.compile(r"🎯(\S+?)\((首选|次选)\)\s+([\d.]+)\s+([\d.]+)")


def _resolve_full_names(home_raw: str, away_raw: str, league_raw: str,
                          full_name_lookup: list, tr: "Translator") -> tuple:
    """主客队名/联赛名从原txt解析出来是截断片段，反查football_score_predictions
    拿完整未截断名字——同时用主队+客队两个字段一起当匹配条件(只用其中一个字段
    单独匹配，遇到"两支队伍恰好共享同一个截断前缀"时会跟前面翻译脚本第一版踩过
    的"UEFA -"张冠李戴是同一类风险)。联赛全名直接从匹配到的记录里一并拿到，不
    需要再单独处理"UEFA - Conferenc"这种联赛名截断——两个问题一次性解决。

    Bug修复(2026-08-20)：原来无条件要求两个字段都按"英文前缀"匹配，但两支队伍
    经常一支已经被team_zh()翻成中文、另一支还是截断英文这种混合情况(比如"Inter
    Turku"对"哥本哈根")——中文字段永远不会是任何英文全名的前缀，AND条件必然
    失败，导致连"能查到的"那个字段也白白算不出来。现在按字段类型分别处理：
    ASCII字段按前缀匹配完整英文名，已经是中文的字段改成"这个英文全名翻译后是不是
    正好等于这段中文"来验证，两种判断方式都要通过。"""
    home_s, away_s = home_raw.strip(), away_raw.strip()
    home_ascii, away_ascii = _is_ascii(home_s), _is_ascii(away_s)

    def home_ok(h):
        return h.startswith(home_s) if home_ascii else tr.team(h).startswith(home_s)

    def away_ok(a):
        return a.startswith(away_s) if away_ascii else tr.team(a).startswith(away_s)

    matches = [(h, a, lg) for h, a, lg, _ in full_name_lookup
               if home_s and away_s and home_ok(h) and away_ok(a)]
    if len(matches) == 1:
        return matches[0]
    return home_s, away_s, league_raw.strip()


def fetch_score_candidates(tr, slip_path, full_name_lookup):
    """解析最新投注单txt里的"比分候选观察单/比分投注单"区块（本脚本第一版翻译过的
    格式，见00_命中系统.py里_correct_score_validation_status()调用处的展示代码）。
    每场比赛可能有多条🎯候选(首选+最多2次选)，每条候选单独渲染成一行——市场固定
    "比分"，方向是具体推荐比分+首选/次选标签，比分预测列放泊松参考比分(跟方向列
    的具体推荐是两回事，前者是模型的"最可能"比分，后者是真实盘口验证过命中分够
    高的"推荐"比分，可能不是同一个比分)。"""
    if not slip_path or not os.path.exists(slip_path):
        return []
    with open(slip_path, encoding="utf-8") as f:
        lines = f.readlines()

    rows = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _CS_ROW_RE.match(line)
        if m:
            kickoff_txt, league_raw, home_raw, away_raw, top_score, rest = m.groups()
            home_full, away_full, league_full = _resolve_full_names(
                home_raw, away_raw, league_raw, full_name_lookup, tr)
            # 把本行(可能含首选)以及紧随其后缩进的次选行都收集起来
            pick_block = rest
            j = i + 1
            while j < len(lines) and "🎯" in lines[j] and not _CS_ROW_RE.match(lines[j]):
                pick_block += " " + lines[j].strip()
                j += 1
            picks = _CS_PICK_RE.findall(pick_block)
            for pick_score, pick_label, odds_s, hs_s in picks:
                rows.append({
                    "kickoff_utc": None, "kickoff_txt": kickoff_txt,
                    "league_zh": tr.league(league_full),
                    "home_zh": tr.team(home_full),
                    "away_zh": tr.team(away_full),
                    "market_zh": "比分", "direction_zh": f"{pick_score}({pick_label})",
                    "odds": float(odds_s), "p_fusion": None, "kelly": None,
                    "hit_score": float(hs_s), "score": top_score if top_score != "-" else None,
                })
            i = j
            continue
        i += 1
    rows.sort(key=lambda r: -(r["hit_score"] or 0))
    return rows


def _is_ascii(s):
    return bool(s) and all(ord(c) < 128 for c in s)


def render_score_section(rows):
    """跟render_section()同一套表头/列宽，但用kickoff_txt(原文件里已经是"MM月DD日
    HH:MM"格式的字符串)而不是kickoff_utc(这批数据没有真实的ISO时间戳可用，只能
    保留原文件已经格式化好的文本)。"""
    if not rows:
        return ""
    lines = ["", "═" * 138, "  📊 比分候选观察单  [真实盘口比分推荐，命中分降序，仅数据追踪未正式启用]",
              "═" * 138, _HEADER, _SEP]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"  {i:>3}.  {_tw(r['kickoff_txt'], _W_TIME)}{_tw(r['league_zh'], _W_LEAGUE)}"
            f"{_tw('[主]' + r['home_zh'], _W_TEAM)}{_tw('[客]' + r['away_zh'], _W_TEAM)}"
            f" {r['market_zh']:<{_W_MARKET}} {r['direction_zh']:<{_W_DIR}} {_num(r['odds'],'.2f'):<6}"
            f" {_num(r['p_fusion'],'.3f'):<7} {_num(r['kelly'],'.4f'):<7} {_num(r['hit_score'],'.3f'):<8} "
            f"{r['score'] or '-'}"
        )
    lines.append(_SEP)
    lines.append(f"  共 {len(rows)} 条候选")
    lines.append("═" * 138)
    return "\n".join(lines)


# ─── 审计：仍未覆盖的队伍/联赛（沿用第一版逻辑，只是取数源头改成DB queries直查全部）
def audit(fetch_date, tr):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT home_team FROM shadow_recommendations WHERE fetch_date=?
        UNION SELECT DISTINCT away_team FROM shadow_recommendations WHERE fetch_date=?
        UNION SELECT DISTINCT home_team FROM under_shadow_bets WHERE fetch_date=?
        UNION SELECT DISTINCT away_team FROM under_shadow_bets WHERE fetch_date=?
        UNION SELECT DISTINCT home_team FROM over_shadow_bets WHERE fetch_date=?
        UNION SELECT DISTINCT away_team FROM over_shadow_bets WHERE fetch_date=?
        UNION SELECT DISTINCT home_team FROM corner_recommendations WHERE fetch_date=?
        UNION SELECT DISTINCT away_team FROM corner_recommendations WHERE fetch_date=?
    """, (fetch_date,) * 8)
    teams = sorted(set(r[0] for r in cur.fetchall() if r[0] and _is_ascii(r[0])))
    cur.execute("""
        SELECT DISTINCT league_name FROM shadow_recommendations WHERE fetch_date=?
        UNION SELECT DISTINCT league_name FROM under_shadow_bets WHERE fetch_date=?
        UNION SELECT DISTINCT league_name FROM over_shadow_bets WHERE fetch_date=?
        UNION SELECT DISTINCT league_name FROM corner_recommendations WHERE fetch_date=?
    """, (fetch_date,) * 4)
    leagues = sorted(set(r[0] for r in cur.fetchall() if r[0] and _is_ascii(r[0])))
    conn.close()

    missing_teams = [t for t in teams if tr.team(t) == t]
    missing_leagues = [lg for lg in leagues if tr.league(lg) == lg]
    print(f"仍未覆盖的球队({len(missing_teams)}个):")
    for t in missing_teams:
        print(f"  {t!r}")
    print(f"仍未覆盖的联赛({len(missing_leagues)}个):")
    for lg in missing_leagues:
        print(f"  {lg!r}")


def _connect():
    import sqlite3
    return sqlite3.connect(_DB_PATH)


# ─── 主流程 ─────────────────────────────────────────────────────────────────
_SECTIONS = [
    # (标题, table/shadow_type, fetcher, 备注)
    ("📋 反着买正式推荐（formula_version=fade_manual，人工批准非算法验证）", None, None, None),
]

_SHADOW_TITLES = [
    ("moneyline", "📊 独赢影子观察单  [仅数据追踪，未正式启用]"),
    ("spread", "📊 让分影子观察单  [仅数据追踪，未正式启用]"),
    ("1x2", "📊 胜平负影子观察单  [仅数据追踪，未正式启用]"),
    ("lstm_moneyline", "📊 LSTM独赢影子观察单  [仅数据追踪，未正式启用]"),
    ("lstm_1x2", "📊 LSTM胜平负影子观察单  [仅数据追踪，未正式启用]"),
    ("lstm_spread", "📊 LSTM让球影子观察单  [仅数据追踪，未正式启用]"),
    ("team_total", "📊 球队大小影子观察单  [仅数据追踪，未正式启用]"),
    ("fotmob_1x2", "📊 FotMob胜平负影子观察单  [仅数据追踪，未正式启用]"),
    ("fotmob_totals", "📊 FotMob大小球影子观察单  [仅数据追踪，未正式启用]"),
    ("fotmob_team_total", "📊 FotMob球队大小影子观察单  [仅数据追踪，未正式启用]"),
    ("fotmob_spread", "📊 FotMob让球影子观察单  [仅数据追踪，未正式启用]"),
    ("fotmob_corner", "📊 FotMob角球影子观察单  [仅数据追踪，未正式启用]"),
    ("qiety_h2h", "📊 企鹅交锋影子观察单  [仅数据追踪，未正式启用]"),
]


def main():
    ap = argparse.ArgumentParser(description="投注单全中文统一格式报告（独立脚本，不改命中系统）")
    ap.add_argument("--date", default=None, help="fetch_date，默认今日")
    ap.add_argument("--file", default=None, help="比分候选观察单区块要解析的原始投注单txt，默认自动找D:\\lucky最新的")
    ap.add_argument("--audit", action="store_true", help="只扫描仍未覆盖的队伍/联赛，不生成报告")
    args = ap.parse_args()

    fetch_date = args.date or datetime.now().strftime("%Y-%m-%d")
    next_date = (datetime.strptime(fetch_date, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")

    teams_dict, leagues_dict, outcomes_dict = load_dict()
    tr = Translator(teams_dict, leagues_dict, outcomes_dict)

    if args.audit:
        audit(fetch_date, tr)
        return

    conn = _connect()
    score_lookup = build_score_lookup(conn, fetch_date, next_date)
    full_name_lookup = build_full_name_lookup(conn, fetch_date, next_date)

    out_blocks = []

    main_rows = fetch_hit_recommendations(conn, tr, score_lookup, fetch_date, exclude_fade_manual=True)
    out_blocks.append(render_section("📋 今日投注推荐单（正式）", None, main_rows))

    fade_rows = fetch_hit_recommendations(conn, tr, score_lookup, fetch_date, exclude_fade_manual=False)
    out_blocks.append(render_section(
        "📋 反着买正式推荐（formula_version=fade_manual，人工批准非算法验证）", None, fade_rows))

    under_rows = fetch_under_over_shadow(conn, tr, score_lookup, fetch_date, "under_shadow_bets", "小球")
    out_blocks.append(render_section("📊 小球候选观察单  [仅数据追踪，未正式启用]", None, under_rows))

    over_rows = fetch_under_over_shadow(conn, tr, score_lookup, fetch_date, "over_shadow_bets", "大球")
    out_blocks.append(render_section("📊 大球候选观察单  [仅数据追踪，未正式启用]", None, over_rows))

    corner_rows = fetch_corner_recommendations(conn, tr, score_lookup, fetch_date)
    out_blocks.append(render_section("📊 角球候选观察单  [仅数据追踪，未正式启用]", None, corner_rows))

    for shadow_type, title in _SHADOW_TITLES:
        rows = fetch_shadow_recommendations(conn, tr, score_lookup, fetch_date, shadow_type)
        out_blocks.append(render_section(title, None, rows))

    conn.close()

    slip_path = args.file or find_latest_slip()
    score_rows = fetch_score_candidates(tr, slip_path, full_name_lookup)
    out_blocks.append(render_score_section(score_rows))

    final_text = "\n".join(b for b in out_blocks if b) + "\n"

    ts = datetime.now().strftime("%H%M")
    out_path = os.path.join(_SLIP_DIR, f"投注单_全中文_{fetch_date}_{ts}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    print(f"fetch_date: {fetch_date}")
    print(f"比分候选观察单解析源: {slip_path}")
    print(f"输出文件: {out_path}")


if __name__ == "__main__":
    main()
