#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日结算复盘·逐场明细表（永久格式，2026-08-29确立，见CLAUDE.md）
================================================================
8列固定表格：比赛时间(北京时间) / 联赛 / 主队VS客队 / 推荐玩法 / 推荐方向(带队名) /
实际赛果 / 命中率 / ROI —— 命中率与ROI是该"桶"(市场分类)整体的聚合值，同一个桶内
每一行重复展示（markdown表格不支持合并单元格，重复值是纯文本表格里的等价做法）。

覆盖范围：正式推荐单(hit_recommendations/corner_recommendations) +
全部影子观察单(under_shadow_bets/over_shadow_bets/moneyline_shadow_full/
team_total_shadow_full/shadow_recommendations 全部shadow_type)。

复用 _translate_slip_zh.py 的 Translator（team_zh()/league_zh()+_slip_zh_dict.json）
做中文翻译，不重复造轮子。

用法：
  python -X utf8 settle_match_detail_zh.py --date 2026-08-28 [--save]
"""
import sys, os, sqlite3, argparse
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _BASE_DIR)
DB_PATH = os.path.join(_BASE_DIR, "data", "sports_data.db")

import _translate_slip_zh as tsz

STATUS_ZH = {"win": "胜", "lose": "负", "push": "走盘", "void": "作废",
             "pending": "待结算", "invalid": "无效", None: "待结算"}

# 队名别名表(2026-09-03新增，修复严谨性审查发现的报告层显示缺口)——ScoreLookup/
# CornerLookup此前只做原始字符串小写包含匹配，撞不上英语/本地语变体（如
# "Rapid Vienna"英文名 vs fotmob存的"Rapid Wien"德语名，"Independiente del Valle"
# 全称 vs match_results存的"Ind. del Valle"缩写），导致21_auto_settle.py三层匹配
# 已经用真实数据结算成功的场次，报告展示层却显示"未存档比分/角球数未存档"——结算
# 结果本身是对的(已核实corner_recommendations/shadow_recommendations里的win/lose都能
# 在fotmob_match_team_stats/match_results找到真实数据支撑)，只是这两个只读展示类没能
# 把同一份真实数据找出来显示。不改结算脚本本身，只加强本文件的展示层查找。
_NAME_ALIASES = {
    "vienna": "wien", "wien": "wien",
}


def _norm_name(name: str) -> str:
    """归一化用于模糊比对：小写、去标点缩写点号、常见地名英语/本地语别名替换。"""
    if not name:
        return ""
    s = name.lower().replace(".", "").replace("-", " ")
    s = " ".join(s.split())
    for word, alias in _NAME_ALIASES.items():
        s = s.replace(word, alias)
    return s


def _names_match(a: str, b: str) -> bool:
    """比ScoreLookup/CornerLookup原来的纯小写子串包含更宽松一档：别名替换后的
    子串包含 + 缩写词前缀容忍。

    性能教训(2026-09-04)：最初版本这里还加了一层"team_zh()归一化后比较"，
    想用它兜底"两个队名翻译成中文后是否相同"这类场景——但team_zh()自身找不到
    精确/后缀匹配时会退化成遍历整个TEAM_ZH字典(数千条)做正则子串匹配，是
    O(字典大小)的重操作。本函数被设计成在成千上万行的候选表上做线性扫描兜底
    (_fuzzy()/_fotmob())，等于把O(字典大小)乘上O(候选行数)，实测直接把一次
    报告生成从几秒钟拖到卡死数小时(见_fullrun同期commit记录)。已确认当前
    需要处理的场景(Vienna/Wien、Ind./Independiente缩写)靠下面的别名替换+
    缩写前缀两条规则就能覆盖，不依赖team_zh()分支，故直接删除，改为只用
    廉价的字符串操作。"""
    if not a or not b:
        return False
    al, bl = a.lower(), b.lower()
    if al in bl or bl in al:
        return True
    na, nb = _norm_name(a), _norm_name(b)
    if na and (na in nb or nb in na):
        return True
    # 缩写容忍：逐词比较，每一对同位置词里较短的那个必须是较长那个的前缀，
    # 处理"Ind. del Valle"(缩写) vs "Independiente del Valle"(全称)这类场景。
    # 注意：是"每个词自身"取较短的一个做前缀比较，不是整个词组按词数分短组/长组
    # （2026-09-04修复：原实现按数组词数分short/long_，词数相同但单词本身长度不同
    # 时方向会判反，导致"independiente"/"ind"这种真实缩写反而判不出来）。
    wa, wb = [w for w in na.split() if len(w) >= 3], [w for w in nb.split() if len(w) >= 3]
    if wa and len(wa) == len(wb):
        if all(x == y or x.startswith(y) or y.startswith(x) for x, y in zip(wa, wb)):
            return True
    return False

OUTCOME_SIDE_ZH = {"home": "主胜", "away": "客胜", "draw": "平局",
                    "over": "大球", "under": "小球",
                    "corner_over": "大球", "corner_under": "小球"}


def bj_time(kickoff_raw: str) -> str:
    """kickoff_utc 统一按UTC处理(+8h)，不管字符串里有没有'Z'后缀
    (corner_recommendations/qiety来源的裸时间戳实测也是UTC，已用真实比赛核对过)。"""
    if not kickoff_raw:
        return "-"
    s = kickoff_raw.replace("Z", "").replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(s[:19], fmt)
            dt_bj = dt + timedelta(hours=8)
            return dt_bj.strftime("%m月%d日%H:%M")
        except ValueError:
            continue
    return kickoff_raw


def direction_zh(tr, market, outcome, handicap, home_zh, away_zh):
    """列5：推荐玩法方向，能落到具体队伍的一律带队名。"""
    if market == "ht_ft":
        # outcome形如 "home-away"：半场结果-全场结果
        parts = (outcome or "").split("-")
        if len(parts) == 2:
            ht_zh = OUTCOME_SIDE_ZH.get(parts[0], parts[0])
            ft_zh = OUTCOME_SIDE_ZH.get(parts[1], parts[1])
            return f"半场{ht_zh}+全场{ft_zh}"
        return outcome or "-"

    if market == "correct_score":
        return f"比分{outcome}"

    if outcome in ("home", "away", "draw"):
        side_zh = OUTCOME_SIDE_ZH.get(outcome, outcome)
        team = home_zh if outcome == "home" else (away_zh if outcome == "away" else None)
        hc_s = f"{handicap:+g}" if handicap not in (None, 0) else ""
        if team:
            return f"{side_zh}{hc_s}({team})"
        return f"{side_zh}{hc_s}"

    if outcome in ("over", "under", "corner_over", "corner_under"):
        side_zh = OUTCOME_SIDE_ZH.get(outcome, outcome)
        line_s = f"{handicap:g}" if handicap is not None else ""
        if market in ("team_total_home", "team_total_away"):
            team = home_zh if market == "team_total_home" else away_zh
            return f"{side_zh}{line_s}({team})"
        return f"{side_zh}{line_s}"

    return f"{outcome}{f'{handicap:+g}' if handicap else ''}"


def market_label_zh(tr, market):
    if market in ("corner_total",):
        return "角球大小"
    return tr.market(market)


class ScoreLookup:
    """按unified_id直连取比分(含半场)，取不到时按队名+日期在match_results做
    弱匹配兜底(跟21_auto_settle.py的_layer2_fuzzy_scores同一个思路，独立实现，
    只读不改结算脚本)。"""

    def __init__(self, conn):
        self.conn = conn
        self._um_cache = {}
        self._mr_rows = None
        self._fm_rows = None

    def by_unified_id(self, uid):
        if not uid:
            return None
        if uid in self._um_cache:
            return self._um_cache[uid]
        row = self.conn.execute(
            "SELECT home_score, away_score, home_score_ht, away_score_ht "
            "FROM unified_matches WHERE unified_id=?",
            (uid,),
        ).fetchone()
        self._um_cache[uid] = row
        return row

    def _load_match_results(self):
        if self._mr_rows is not None:
            return
        self._mr_rows = self.conn.execute(
            "SELECT home_team, away_team, home_score, away_score, match_date "
            "FROM match_results WHERE home_score IS NOT NULL"
        ).fetchall()
        self._mr_index = {}  # 同_load_fotmob()的O(1)索引优化，match_results同样上万行
        for rh, ra, hs, aws, md in self._mr_rows:
            self._mr_index.setdefault((_norm_name(rh), _norm_name(ra)), []).append((rh, ra, hs, aws, md))

    def _fuzzy(self, home, away, kickoff_raw):
        self._load_match_results()
        target_date = None
        if kickoff_raw:
            try:
                target_date = kickoff_raw[:10]
            except Exception:
                pass

        def _pick(candidates):
            for rh, ra, hs, aws, md in candidates:
                if not target_date or not md or abs(
                    (datetime.strptime(md, "%Y-%m-%d") - datetime.strptime(target_date, "%Y-%m-%d")).days
                ) <= 1:
                    return (hs, aws, None, None)
            return None

        indexed = self._mr_index.get((_norm_name(home), _norm_name(away)))
        if indexed:
            hit = _pick(indexed)
            if hit:
                return hit
        for rh, ra, hs, aws, md in self._mr_rows:
            if _names_match(home, rh) and _names_match(away, ra):
                if not target_date or not md or abs(
                    (datetime.strptime(md, "%Y-%m-%d") - datetime.strptime(target_date, "%Y-%m-%d")).days
                ) <= 1:
                    return (hs, aws, None, None)
        return None

    def _load_fotmob(self):
        if self._fm_rows is not None:
            return
        self._fm_rows = []
        self._fm_index = {}  # (norm_home,norm_away) -> list of rows，O(1)命中大多数场次，
        # 避免每次查询都对全表(实测14765行)做_names_match线性扫描——90条报告行×14765行
        # 逐个字符串比对在纯Python下实测会拖到以小时计，改成先按归一化队名建索引，
        # 只有索引未命中(缩写等特殊场景)才退化到线性扫描兜底。
        for h, a, hs, aws, md, hht, aht in self.conn.execute(
            "SELECT home_team, away_team, home_score, away_score, match_date, "
            "home_score_ht, away_score_ht FROM fotmob_matches WHERE home_score IS NOT NULL"
        ).fetchall():
            try:
                dt = datetime.strptime(md.split(",", 1)[1].strip().rsplit(",", 1)[0].strip(), "%b %d %Y")
            except Exception:
                dt = None
            row = (h, a, hs, aws, dt, hht, aht)
            self._fm_rows.append(row)
            self._fm_index.setdefault((_norm_name(h), _norm_name(a)), []).append(row)

    def _fotmob(self, home, away, kickoff_raw):
        """第三层：fotmob_matches兜底(跟21_auto_settle.py的fotmob兜底同一份数据，
        独立只读实现)——修复2026-09-03严谨性审查发现的展示层缺口：结算本身已经
        用这份数据算出真实win/lose，但报告展示层此前完全没查这张表，导致明明有
        真实比分支撑的场次显示成"未存档比分"。"""
        self._load_fotmob()
        target_date = None
        if kickoff_raw:
            try:
                target_date = datetime.strptime(kickoff_raw[:10], "%Y-%m-%d")
            except Exception:
                pass

        def _pick(candidates):
            for rh, ra, hs, aws, dt, hht, aht in candidates:
                if not target_date or not dt or abs((dt - target_date).days) <= 1:
                    return (hs, aws, hht, aht)
            return None

        indexed = self._fm_index.get((_norm_name(home), _norm_name(away)))
        if indexed:
            hit = _pick(indexed)
            if hit:
                return hit
        # 索引未命中(缩写等极少数场景)才退化到全表线性扫描兜底
        for rh, ra, hs, aws, dt, hht, aht in self._fm_rows:
            if _names_match(home, rh) and _names_match(away, ra):
                if not target_date or not dt or abs((dt - target_date).days) <= 1:
                    return (hs, aws, hht, aht)
        return None

    def render(self, uid, market, home=None, away=None, kickoff=None):
        row = self.by_unified_id(uid)
        if row and row[0] is not None:
            hs, aws, hs_ht, as_ht = row[0], row[1], row[2], row[3]
        else:
            fz = self._fuzzy(home, away, kickoff) if home else None
            if not fz:
                fz = self._fotmob(home, away, kickoff) if home else None
            if not fz:
                return "-"
            hs, aws, hs_ht, as_ht = fz
        if market == "ht_ft":
            if hs_ht is None or as_ht is None:
                return f"全场{hs}-{aws}(半场缺)"
            return f"半场{hs_ht}-{as_ht} / 全场{hs}-{aws}"
        return f"{hs}-{aws}"


class CornerLookup:
    """角球市场的"实际赛果"：优先 corner_stats_final，再退 fotmob_matches+team_stats
    联合角球和(逻辑与21_auto_settle.py的_get_fotmob_corner_totals一致，此处只读不改)。"""

    def __init__(self, conn, fetch_date):
        self.conn = conn
        self.fetch_date = fetch_date
        self._rows = None

    def _load(self):
        if self._rows is not None:
            return
        self._rows = []
        try:
            for h, a, md, hc, ac, tot in self.conn.execute(
                "SELECT home_team, away_team, match_date, home_corners, away_corners, total_corners "
                "FROM corner_stats_final"
            ).fetchall():
                self._rows.append((h.lower(), a.lower(), tot))
        except Exception:
            pass
        try:
            for h, a, tot in self.conn.execute(
                """SELECT fm.home_team, fm.away_team, SUM(fts.corners)
                   FROM fotmob_matches fm JOIN fotmob_match_team_stats fts ON fm.match_id=fts.match_id
                   WHERE fts.corners IS NOT NULL GROUP BY fm.match_id HAVING COUNT(fts.corners)=2"""
            ).fetchall():
                self._rows.append((h.lower(), a.lower(), tot))
        except Exception:
            pass

    def render(self, home, away, line, status):
        self._load()
        for rh, ra, tot in self._rows:
            if _names_match(home, rh) and _names_match(away, ra) and tot is not None:
                return f"全场角球{tot}(线{line:g})"
        if status in ("win", "lose"):
            return f"角球数未存档(按{STATUS_ZH.get(status)}结算,线{line:g})"
        return "-"


def bucket_stats(rows_status_pl):
    win = sum(1 for s, _ in rows_status_pl if s == "win")
    lose = sum(1 for s, _ in rows_status_pl if s == "lose")
    push = sum(1 for s, _ in rows_status_pl if s == "push")
    pl_sum = sum(p for s, p in rows_status_pl if s in ("win", "lose", "push") and p is not None)
    n = win + lose
    hit_rate = f"{win/n*100:.1f}%" if n else "N/A"
    roi_n = win + lose + push
    roi = f"{pl_sum/roi_n*100:+.1f}%" if roi_n else "N/A"
    return hit_rate, roi


HEADERS = ["比赛时间", "联赛", "主队VS客队", "推荐玩法", "推荐方向", "实际赛果", "命中率", "ROI"]


def _disp_w(s: str) -> int:
    return sum(2 if ord(ch) > 127 else 1 for ch in s)


def _pad(s: str, width: int) -> str:
    return s + " " * (width - _disp_w(s))


def render_grid_table(rows):
    """行列都有实线分隔的box-drawing表格（Excel网格线风格），
    列宽按该表实际内容自适应，不做全局固定宽度截断。"""
    all_rows = [HEADERS] + rows
    n_col = len(HEADERS)
    col_w = [max(_disp_w(str(r[i])) for r in all_rows) for i in range(n_col)]

    def hline(left, mid, right, fill="─"):
        return left + mid.join(fill * (w + 2) for w in col_w) + right

    def data_line(cells):
        return "│" + "│".join(" " + _pad(str(c), w) + " " for c, w in zip(cells, col_w)) + "│"

    out = [hline("┌", "┬", "┐")]
    out.append(data_line(HEADERS))
    out.append(hline("├", "┼", "┤"))
    for i, r in enumerate(rows):
        out.append(data_line(r))
        out.append(hline("├", "┼", "┤") if i < len(rows) - 1 else hline("└", "┴", "┘"))
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()
    fetch_date = args.date

    conn = sqlite3.connect(DB_PATH)
    teams_dict, leagues_dict, outcomes_dict = tsz.load_dict()
    tr = tsz.Translator(teams_dict, leagues_dict, outcomes_dict)
    score_lu = ScoreLookup(conn)
    corner_lu = CornerLookup(conn, fetch_date)

    out_lines = []
    def emit(s=""):
        out_lines.append(s)

    def build_rows(records, market_key_fn, is_corner=False):
        status_pl = [(rec["status"], rec["pl"]) for rec in records]
        hit_rate, roi = bucket_stats(status_pl)
        rows = []
        for rec in records:
            hm_zh, aw_zh = tr.team(rec["home"]), tr.team(rec["away"])
            lg_zh = tr.league(rec["league"]) if rec["league"] else "-"
            mkt_zh = market_label_zh(tr, rec["market"])
            dir_zh = direction_zh(tr, rec["market"], rec["outcome"], rec["handicap"], hm_zh, aw_zh)
            if is_corner:
                result_s = corner_lu.render(rec["home"], rec["away"], rec["handicap"], rec["status"])
            else:
                result_s = score_lu.render(rec.get("unified_id"), rec["market"],
                                            home=rec["home"], away=rec["away"], kickoff=rec["kickoff"])
                if result_s == "-" and rec["status"] in ("win", "lose", "push"):
                    result_s = f"(未存档比分,按{STATUS_ZH.get(rec['status'])}结算)"
            status_s = STATUS_ZH.get(rec["status"], rec["status"] or "待结算")
            result_s = f"{result_s} [{status_s}]" if result_s != "-" else status_s
            rows.append([bj_time(rec["kickoff"]), lg_zh, f"{hm_zh} VS {aw_zh}", mkt_zh, dir_zh,
                         result_s, hit_rate, roi])
        return rows

    # ── 一、正式推荐单 ──
    emit("## 一、正式推荐单（真钱）")
    cur = conn.cursor()
    cur.execute("""SELECT league_name, home_team, away_team, kickoff_utc, market, outcome, handicap,
                          unified_id, status, profit_loss
                   FROM hit_recommendations WHERE fetch_date=?""", (fetch_date,))
    recs = [dict(league=r[0], home=r[1], away=r[2], kickoff=r[3], market=r[4], outcome=r[5],
                 handicap=r[6], unified_id=r[7], status=r[8], pl=r[9]) for r in cur.fetchall()]
    rows = build_rows(recs, None)
    if rows:
        emit("### 主推荐单 hit_recommendations")
        emit(render_grid_table(rows))
        emit("")

    cur.execute("""SELECT league_name, home_team, away_team, kickoff_utc, direction, line, odds,
                          status, profit_loss
                   FROM corner_recommendations WHERE fetch_date=?""", (fetch_date,))
    recs = [dict(league=r[0], home=r[1], away=r[2], kickoff=r[3], market="corner_total",
                 outcome=r[4], handicap=r[5], status=r[7], pl=r[8]) for r in cur.fetchall()]
    rows = build_rows(recs, None, is_corner=True)
    if rows:
        emit("### 角球正式推荐 corner_recommendations")
        emit(render_grid_table(rows))
        emit("")

    # ── 二、影子观察单 ──
    emit("\n## 二、影子观察单（仅观察，非真钱）")
    for table, label in [("under_shadow_bets", "小球候选"), ("over_shadow_bets", "大球候选")]:
        cur.execute(f"""SELECT league_name, home_team, away_team, kickoff_utc, market, handicap,
                              unified_id, status, profit_loss
                       FROM {table} WHERE fetch_date=?""", (fetch_date,))
        recs = []
        for lg, hm, aw, ko, mkt, hc, uid, status, pl in cur.fetchall():
            outcome = "over" if label == "大球候选" else "under"
            recs.append(dict(league=lg, home=hm, away=aw, kickoff=ko, market=mkt, outcome=outcome,
                              handicap=hc, unified_id=uid, status=status, pl=pl))
        rows = build_rows(recs, None)
        if rows:
            emit(f"### {label} {table}")
            emit(render_grid_table(rows))
            emit("")

    SHADOW_LABEL = {
        "1x2": "独赢影子(≈独赢完整候选,FIX-014-2非严格镜像)", "fotmob_1x2": "FotMob独赢观察",
        "fotmob_corner": "FotMob角球观察", "fotmob_spread": "FotMob让球观察",
        "fotmob_team_total": "FotMob球队大小观察", "fotmob_totals": "FotMob大小球观察",
        "gated": "门槛拦截观察", "htft": "半全场观察", "lstm_1x2": "LSTM独赢观察·1x2口径",
        "lstm_moneyline": "LSTM独赢观察·moneyline口径", "lstm_spread": "LSTM让球观察",
        "moneyline": "独赢观察", "qiety_h2h": "企鹅交锋观察", "spread": "让球观察",
        "team_total": "球队大小观察(≈球队大小完整候选,FIX-014-2非严格镜像)",
    }
    cur.execute("SELECT DISTINCT shadow_type FROM shadow_recommendations WHERE fetch_date=?", (fetch_date,))
    types = sorted(r[0] for r in cur.fetchall())
    for stype in types:
        cur.execute("""SELECT league_name, home_team, away_team, kickoff_utc, market, outcome, handicap,
                              unified_id, status, profit_loss
                       FROM shadow_recommendations WHERE fetch_date=? AND shadow_type=?
                       ORDER BY kickoff_utc""", (fetch_date, stype))
        recs = [dict(league=r[0], home=r[1], away=r[2], kickoff=r[3], market=r[4], outcome=r[5],
                     handicap=r[6], unified_id=r[7], status=r[8], pl=r[9]) for r in cur.fetchall()]
        for rec in recs:
            if not rec["league"] and rec.get("unified_id"):
                lg_row = cur.execute(
                    "SELECT league_name FROM unified_matches WHERE unified_id=?", (rec["unified_id"],)
                ).fetchone()
                if lg_row and lg_row[0]:
                    rec["league"] = lg_row[0]
        is_corner = stype == "fotmob_corner"
        rows = build_rows(recs, None, is_corner=is_corner)
        if rows:
            emit(f"### {SHADOW_LABEL.get(stype, stype)} (shadow_type={stype})")
            emit(render_grid_table(rows))
            emit("")

    report = "\n".join(out_lines)
    print(report)

    if args.save:
        out_path = os.path.join("D:\\lucky", f"结算复盘逐场明细_{fetch_date}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\n已保存: {out_path}")

    conn.close()


if __name__ == "__main__":
    main()
