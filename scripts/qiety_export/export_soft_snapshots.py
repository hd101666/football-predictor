# -*- coding: utf-8 -*-
"""qiety 赛前赔率 → GitHub 持续导出（exports/grokbot/<日期>/soft_snapshots）

分工：
  * 采集：由既有 qqsj_v2_cycle_peak（10:00-次日04:00 每30分）+ offpeak（04:00-10:00 每60分）
    完成，链路是 预检 → 29号qiety抓取 → snapshot_qiety → soft_odds_snapshots
  * 本脚本：把 soft_odds_snapshots 里的 qiety 行导出成 gzip CSV，补 pinn_id，
    生成队名对照表，按「只新增不覆盖」推到 hit-system-exports 分支。

设计要点：
  1. 每次运行生成一个【快照子目录】：exports/grokbot/<日期>/soft_snapshots/run_<HHMM>/
     ——任务要求"每天至少推送两次"，用子目录保证每次都是新增、绝不覆盖历史
  2. 同一天内多次运行各自独立，manifest 记录每次的行数与 sha256
  3. pinn_id 用 v2_value_picks 的 match_events（开赛±15分 + 队名相似度≥0.80）
  4. 队名对照表 qiety_team_map.csv 一并推送
  5. 凭据只从环境变量读（本脚本不接触任何账号密码）

用法：
  python -X utf8 export_soft_snapshots.py --db D:\\cl\\qqsj\\data\\sports_data.db \
      --repo D:\\cl\\fp_exports [--hours 24] [--push]
"""
import argparse
import gzip
import hashlib
import json
import os
import subprocess
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, r"D:\cl\qqsj_v2")

BJ = timedelta(hours=8)
TEAM_MAP = r"D:\cl\qqsj_v2\qiety_team_map.csv"


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def esc(v):
    if v is None:
        return ""
    s = str(v)
    return '"' + s.replace('"', '""') + '"' if any(c in s for c in ',"\n\r') else s


def dump_gz(path, header, rows):
    tmp = path + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8", newline="") as f:
        f.write(",".join(header) + "\n")
        for r in rows:
            f.write(",".join(esc(v) for v in r) + "\n")
    os.replace(tmp, path)
    return len(rows)


def ro(db):
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=60)
    con.row_factory = sqlite3.Row
    return con


def load_team_map(con):
    """qiety 中文队名 -> 英文"""
    import csv as _csv
    m = {}
    try:
        rows = con.execute("SELECT zh_name, en_name FROM team_name_map "
                           "WHERE zh_name IS NOT NULL AND en_name IS NOT NULL").fetchall()
        for r in rows:
            m[str(r[0]).strip()] = str(r[1]).strip()
    except sqlite3.OperationalError:
        pass
    if os.path.exists(TEAM_MAP):
        with open(TEAM_MAP, encoding="utf-8-sig") as f:
            for row in _csv.DictReader(f):
                zh = (row.get("zh_name") or "").strip()
                en = (row.get("en_name") or "").strip()
                if zh and en:
                    m[zh] = en
    return m


def fill_pinn_id(con, rows, tmap):
    """用 Pinnacle fixtures 给 qiety 行补 pinn_id。

    匹配规则（沿用 v2_value_picks.match_events）：
      开赛时间 ±15 分钟 且 主客队名相似度均 ≥0.80，取唯一最佳。
    队名先过 tmap 转英文。
    """
    import re as _re
    from difflib import SequenceMatcher

    _STRIP = _re.compile(r"\b(fc|cf|sc|ac|afc|cd|ud|sv|fk|nk|bk|if|ff|u19|u20|u21|u23)\b")

    def norm(x):
        """归一化：小写、去连字符/点/多余空格、去常见俱乐部后缀、去音译括号。"""
        s = str(x or "").lower()
        s = s.replace("-", " ").replace(".", " ").replace("'", "")
        s = _re.sub(r"[（(].*?[)）]", " ", s)          # 去掉中西文括号内容
        s = _STRIP.sub(" ", s)
        s = _re.sub(r"\s+", " ", s).strip()
        return s

    def sim(a, b):
        na, nb = norm(a), norm(b)
        if not na or not nb:
            return 0.0
        r1 = SequenceMatcher(None, na, nb).ratio()
        # 再做一次 token 级：任一方包含另一方算高分（Al Ittihad vs Ittihad）
        if na in nb or nb in na:
            r1 = max(r1, 0.90)
        return r1

    # Pinnacle 赛事
    try:
        pin = con.execute("""
            SELECT DISTINCT pinn_id, home_team, away_team, kickoff_utc, league_name
            FROM theodds_fixtures
            WHERE source='pinnacle' AND pinn_id IS NOT NULL AND kickoff_utc IS NOT NULL
        """).fetchall()
    except sqlite3.OperationalError:
        return rows, 0

    if not pin:
        return rows, 0

    pin_parsed = []
    for p in pin:
        try:
            ko = datetime.fromisoformat(str(p["kickoff_utc"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        pin_parsed.append((int(p["pinn_id"]), p["home_team"], p["away_team"], ko, p["league_name"]))

    filled = 0
    # 按 (home,away,kickoff) 去重后再匹配，避免同一场逐行算
    cache = {}
    for r in rows:
        if r.get("pinn_id"):
            continue
        key = (r["home_team"], r["away_team"], r["kickoff_utc"])
        if key in cache:
            r["pinn_id"] = cache[key]
            if r["pinn_id"]:
                filled += 1
            continue
        h_en = tmap.get(str(r["home_team"]).strip(), r["home_team"])
        a_en = tmap.get(str(r["away_team"]).strip(), r["away_team"])
        try:
            ko = datetime.fromisoformat(str(r["kickoff_utc"]).replace("Z", "+00:00"))
        except ValueError:
            cache[key] = None
            continue
        best = []
        for pid, ph, pa, pko, _lg in pin_parsed:
            if abs((pko - ko).total_seconds()) > 15 * 60:
                continue
            s = min(sim(h_en, ph), sim(a_en, pa))
            if s >= 0.80:
                best.append((s, pid))
        best.sort(reverse=True)
        val = best[0][1] if (best and (len(best) == 1 or best[0][0] > best[1][0])) else None
        cache[key] = val
        r["pinn_id"] = val
        if val:
            filled += 1
    return rows, filled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=r"D:\cl\qqsj\data\sports_data.db")
    ap.add_argument("--repo", default=r"D:\cl\fp_exports")
    ap.add_argument("--hours", type=float, default=24, help="只导出开赛前 N 小时内的比赛")
    ap.add_argument("--push", action="store_true", help="导出后立即 commit+push")
    ap.add_argument("--force", action="store_true", help="允许同分钟重复导出（会加序号后缀）")
    a = ap.parse_args()

    now = datetime.now(timezone.utc)
    day = now.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")   # 用北京日期分目录
    hhmm = now.astimezone(timezone(timedelta(hours=8))).strftime("%H%M")

    base = os.path.join(a.repo, "exports", "grokbot", day, "soft_snapshots")
    outdir = os.path.join(base, f"run_{hhmm}")
    if os.path.exists(outdir):
        if not a.force:
            print(f"本次已导出过: {outdir}（跳过；--force 可加序号重导）")
            return 0
        k = 1
        while os.path.exists(f"{outdir}_{k}"):
            k += 1
        outdir = f"{outdir}_{k}"
    os.makedirs(outdir, exist_ok=True)

    con = ro(a.db)
    tmap = load_team_map(con)

    # 只取开赛前 N 小时内的 qiety 快照（任务要求"开赛前 24 小时内"）
    horizon = (now + timedelta(hours=a.hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows_db = con.execute("""
        SELECT id, source, book, match_key, pinn_id, home_team, away_team, kickoff_utc,
               market, line, selection, price_dec, book_last_update_utc, captured_at_utc,
               row_hash, qc_flag, league, src_row_id
        FROM soft_odds_snapshots
        WHERE source = 'qiety'
          AND kickoff_utc IS NOT NULL
          AND kickoff_utc > ?
          AND kickoff_utc <= ?
        ORDER BY kickoff_utc, market, selection
    """, (now.strftime("%Y-%m-%dT%H:%M:%SZ"), horizon)).fetchall()

    rows = [dict(r) for r in rows_db]
    print(f"qiety 快照: {len(rows)} 行（开赛前 {a.hours}h 内）")

    rows, filled = fill_pinn_id(con, rows, tmap)
    total_matches = len({(r["home_team"], r["away_team"], r["kickoff_utc"]) for r in rows})
    matched_matches = len({(r["home_team"], r["away_team"], r["kickoff_utc"])
                           for r in rows if r["pinn_id"]})
    print(f"pinn_id 匹配: {matched_matches}/{total_matches} 场（{len(rows)} 行中 {filled} 行填入）")

    hdr = ["id", "source", "book", "match_key", "pinn_id", "home_team", "away_team",
           "kickoff_utc", "market", "line", "selection", "price_dec",
           "book_last_update_utc", "captured_at_utc", "row_hash", "qc_flag", "league", "src_row_id"]
    out_rows = [[r.get(k) for k in hdr] for r in rows]
    p = os.path.join(outdir, "soft_snapshots.csv.gz")
    n = dump_gz(p, hdr, out_rows)
    print(f"  已写 {p}  {n} 行")

    # 队名对照表
    mp = os.path.join(outdir, "qiety_team_map.csv")
    with open(mp, "w", encoding="utf-8", newline="") as f:
        f.write("zh_name,en_name\n")
        for zh, en in sorted(tmap.items()):
            f.write(f"{esc(zh)},{esc(en)}\n")
    print(f"  队名对照表 {mp}  {len(tmap)} 条")

    man = {
        "exported_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "day_bj": day,
        "run": os.path.basename(outdir),
        "window_hours": a.hours,
        "source_db": os.path.basename(a.db),
        "files": {
            "soft_snapshots.csv.gz": {"rows": n, "bytes": os.path.getsize(p), "sha256": sha256(p)},
            "qiety_team_map.csv": {"rows": len(tmap), "bytes": os.path.getsize(mp), "sha256": sha256(mp)},
        },
        "matches": {"total": total_matches, "with_pinn_id": matched_matches},
        "markets": {},
        "timezone_notes": {
            "captured_at_utc": "UTC（抓取时刻）",
            "book_last_update_utc": "UTC（庄家最后更新）",
            "kickoff_utc": "UTC",
            "day_bj": "目录日期按北京时间（赛程习惯）",
        },
        "source_note": "qiety (企鹅体育) 胜平负/亚盘/大小球，采集脚本 29_qiety_yb_full_scraper.py --within-hours 12；"
                       "本目录为 soft_odds_snapshots 的定时导出",
    }
    # 市场分布
    mk = {}
    for r in rows:
        mk[r["market"]] = mk.get(r["market"], 0) + 1
    man["markets"] = mk

    with open(os.path.join(outdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    print(f"  manifest: {os.path.join(outdir, 'manifest.json')}")
    print(f"  市场分布: {mk}")

    if not a.push:
        print("\n（未推送，加 --push 才提交）")
        return 0

    # 推送：只推 hit-system-exports，只 add 本目录
    rel = os.path.relpath(outdir, a.repo).replace("\\", "/")
    cmds = [
        ["git", "add", rel],
        ["git", "-c", "user.name=hermes", "-c", "user.email=hermes@local",
         "commit", "-m", f"qiety soft_snapshots {day} {hhmm} ({n} rows, {matched_matches}/{total_matches} pinn matched)"],
        ["git", "push", "origin", "hit-system-exports"],
    ]
    for c in cmds:
        r = subprocess.run(c, cwd=a.repo, capture_output=True)
        out = (r.stdout or b"").decode("utf-8", "replace").strip()
        err = (r.stderr or b"").decode("utf-8", "replace").strip()
        if r.returncode != 0:
            if "nothing to commit" in out + err:
                print("  无新增内容，跳过提交")
                return 0
            print(f"  ✗ {' '.join(c[:2])} 失败: {err[:300]}")
            return 1
        print(f"  ✓ {' '.join(c[:2])}: {out[-160:] if out else 'ok'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
