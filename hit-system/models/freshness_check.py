# -*- coding: utf-8 -*-
"""freshness_check.py — FIX-005.3 每日跑批收尾的数据新鲜度监控（2026-09-13）
=================================================================
每日跑批（00_命中系统.py run() 末尾）调用 run_freshness_check()：
  - 核心表（阈值1天）：unified_matches / hit_recommendations / match_results /
    qiety_matches —— 每日链路直接产出或消费，断更1天即异常
  - 辅助表（阈值7天）：club_elo / jingcai_history_matches / corner_recommendations /
    fotmob_matches / ren9_rule_review —— 低频源，断更7天才报警
超阈值 → 写 data_quality_issue_log（level='warning'，issue_code='DATA_STALE'），
同一天同表不重复记录（幂等）。打印汇总到跑批日志。

也可独立运行: python -X utf8 freshness_check.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from datetime import datetime
from sqlalchemy import create_engine, text
from config import DB_ENGINE_URL

# (表名, 日期列, 阈值天数, 类别)
CHECKS = [
    ("unified_matches", "fetch_date", 1, "核心"),
    ("hit_recommendations", "fetch_date", 1, "核心"),
    ("match_results", "match_date", 1, "核心"),
    ("qiety_matches", "fetch_date", 1, "核心"),
    ("club_elo", "fetch_date", 7, "辅助"),
    ("jingcai_history_matches", "match_date", 7, "辅助"),  # 无fetch_date列(实测schema)
    ("corner_recommendations", "fetch_date", 7, "辅助"),
    ("fotmob_matches", "fetch_date", 7, "辅助"),
    ("ren9_rule_review", "fetch_date", 7, "辅助"),
]


def run_freshness_check(engine=None) -> list[dict]:
    """返回问题列表（无问题=空列表）。异常不静默：打印警告并继续检查其余表。"""
    own_engine = engine is None
    if own_engine:
        engine = create_engine(DB_ENGINE_URL, connect_args={"timeout": 60})
    today = datetime.now().date()
    now_s = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    issues = []
    try:
        with engine.begin() as conn:
            for table, date_col, threshold, kind in CHECKS:
                try:
                    row = conn.execute(text(
                        f"SELECT MAX({date_col}) FROM {table}")).fetchone()
                    max_d = row[0] if row else None
                    if not max_d:
                        issues.append({"table": table, "kind": kind,
                                       "msg": f"{table} 无任何{date_col}数据"})
                        continue
                    age = (today - datetime.strptime(str(max_d)[:10], "%Y-%m-%d").date()).days
                    if age > threshold:
                        msg = (f"{table}.{date_col} 最新={str(max_d)[:10]}，"
                               f"距今{age}天 > {kind}表阈值{threshold}天")
                        issues.append({"table": table, "kind": kind, "msg": msg})
                        # 幂等：今天同表已记过就跳过
                        dup = conn.execute(text(
                            "SELECT COUNT(*) FROM data_quality_issue_log "
                            "WHERE entity_type=:t AND issue_code='DATA_STALE' "
                            "AND substr(created_at,1,10)=:d"),
                            {"t": table, "d": today.strftime("%Y-%m-%d")}).fetchone()[0]
                        if not dup:
                            conn.execute(text(
                                "INSERT INTO data_quality_issue_log "
                                "(entity_type, entity_key, issue_code, message, level, "
                                " source_name, created_at) "
                                "VALUES (:t, :ek, 'DATA_STALE', :msg, 'warning', "
                                "'freshness_check', :ts)"),
                                {"t": table, "ek": str(max_d)[:10], "msg": msg, "ts": now_s})
                except Exception as e:
                    # 单表检查失败不静默、不中断其余表（纪律4）
                    print(f"  ⚠ freshness_check: {table} 检查失败 {type(e).__name__}: {e}")
                    issues.append({"table": table, "kind": kind,
                                   "msg": f"检查本身失败: {type(e).__name__}: {e}"})
    finally:
        if own_engine:
            engine.dispose()
    return issues


if __name__ == "__main__":
    res = run_freshness_check()
    if not res:
        print("✅ 全部表新鲜度达标")
    else:
        print(f"⚠ 发现 {len(res)} 个新鲜度问题:")
        for i in res:
            print(f"  [{i['kind']}] {i['msg']}")
