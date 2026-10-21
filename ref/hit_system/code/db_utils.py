# -*- coding: utf-8 -*-
# db_utils.py — 跨数据库 DDL 兼容层 + 批量写入工具（SQLite ↔ MySQL 自动适配）
import re
import time
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)


def exec_ddl(engine, sql: str):
    """
    执行 CREATE TABLE 语句，自动将 SQLite 语法适配为 MySQL 语法。
    - AUTOINCREMENT → AUTO_INCREMENT
    - 添加 ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    - 移除超长 UNIQUE 复合键（MySQL 单索引最大 767 bytes）
    """
    dialect = engine.dialect.name

    if dialect == "mysql":
        # AUTOINCREMENT → AUTO_INCREMENT
        sql = re.sub(r'\bAUTOINCREMENT\b', 'AUTO_INCREMENT', sql, flags=re.IGNORECASE)
        # INTEGER PRIMARY KEY → INT AUTO_INCREMENT PRIMARY KEY
        sql = re.sub(
            r'\bINTEGER\s+PRIMARY\s+KEY\s+AUTO_INCREMENT\b',
            'INT AUTO_INCREMENT PRIMARY KEY',
            sql, flags=re.IGNORECASE,
        )
        # 移除可能超长的内联 UNIQUE 复合键（由 Python 去重保证唯一性）
        sql = re.sub(r',?\s*UNIQUE\s*\([^)]+\)', '', sql, flags=re.IGNORECASE)
        # 补充 ENGINE=InnoDB（若尚未添加）
        if 'ENGINE=' not in sql.upper():
            sql = re.sub(r'\)\s*$', ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4', sql.rstrip())

    with engine.begin() as conn:
        conn.execute(text(sql))


def batch_upsert(engine, table, rows, unique_keys, batch_size=200,
                 max_retries=6, retry_delay=1.5):
    """
    批量 INSERT OR REPLACE（upsert）行数据到指定表。

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine
        数据库引擎（SQLite 或 MySQL）。
    table : sqlalchemy.Table
        目标表对象（可用 sqlalchemy.MetaData + reflect 获取，或手写 Table）。
    rows : list[dict]
        待写入的行数据列表，每个元素是 {column_name: value} 字典。
    unique_keys : list[str]
        用于冲突检测的唯一键列名列表。
    batch_size : int
        每批次写入的行数，默认 200。
    max_retries : int
        遇到 "database is locked" 等可重试错误时的最大重试次数，默认 3。
    retry_delay : float
        重试之间的等待秒数（秒），默认 0.5。

    Returns
    -------
    int : 成功写入的总行数。

    Notes
    -----
    - SQLite: 使用 INSERT OR REPLACE（基于表的主键或 UNIQUE 约束）。
    - MySQL:  使用 INSERT ... ON DUPLICATE KEY UPDATE。
    - 自动按 batch_size 分批提交，避免单次事务过大。
    - 内置重试机制处理 SQLite "database is locked" 错误。
    """
    if not rows:
        return 0

    dialect = engine.dialect.name
    table_name = table.name
    # ★2026-10-11 修复：columns 必须来自「表中真实存在的列 ∩ 行里出现的键」，
    #   否则 _filter_columns 已把行裁到表列，而 SQL 仍按原始 row.keys() 生成
    #   占位符 → sqlalchemy 报 "A value is required for bind parameter 'xxx'"
    #   （典型：fotmob_match_availability 行含 first_name 等表里没有的列）。
    #   并且同一批里不同行的键集合可能不同 → 取全批并集，缺失键补 None，
    #   保证 executemany 时每条记录都提供全部占位符。
    table_cols = {c.name for c in table.columns}
    columns = []
    _seen = set()
    for _r in rows:
        for _k in _r.keys():
            if _k in table_cols and _k not in _seen:
                _seen.add(_k)
                columns.append(_k)
    total_written = 0

    # 分批处理
    for batch_start in range(0, len(rows), batch_size):
        batch = rows[batch_start:batch_start + batch_size]
        # 过滤只保留表中存在的列，并补齐缺失键为 None
        filtered = []
        for row in batch:
            f = _filter_columns(row, table)
            for c in columns:
                f.setdefault(c, None)
            filtered.append(f)

        for attempt in range(max_retries):
            try:
                if dialect == "sqlite":
                    _batch_upsert_sqlite(engine, table, filtered, columns)
                else:
                    _batch_upsert_mysql(engine, table, filtered, columns)
                total_written += len(filtered)
                break
            except Exception as e:
                err_msg = str(e).lower()
                is_retryable = any(kw in err_msg for kw in (
                    "database is locked",
                    "database is busy",
                    "locked",
                    "deadlock",
                    "timeout",
                    "connection",
                ))
                if is_retryable and attempt < max_retries - 1:
                    wait = retry_delay * (2 ** attempt)  # 指数退避
                    logger.warning(
                        f"[db_utils] batch_upsert 重试 {attempt+1}/{max_retries} "
                        f"(表={table_name}, 等待={wait:.1f}s): {e}"
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        f"[db_utils] batch_upsert 失败 (表={table_name}, "
                        f"批次={batch_start//batch_size+1}): {e}"
                    )
                    raise

    return total_written


def _filter_columns(row, table):
    """只保留表中存在的列，忽略多余字段。"""
    table_cols = {c.name for c in table.columns}
    return {k: v for k, v in row.items() if k in table_cols}


def _batch_upsert_sqlite(engine, table, rows, columns):
    """SQLite: INSERT OR REPLACE，写前设 busy_timeout=30s 防并发锁"""
    if not rows:
        return
    col_list = ", ".join(columns)
    placeholders = ", ".join([f":{c}" for c in columns])
    sql = f"INSERT OR REPLACE INTO {table.name} ({col_list}) VALUES ({placeholders})"

    with engine.begin() as conn:
        conn.execute(text("PRAGMA busy_timeout = 30000"))
        conn.execute(text(sql), rows)


def _batch_upsert_mysql(engine, table, rows, columns):
    """MySQL: INSERT ... ON DUPLICATE KEY UPDATE"""
    if not rows:
        return
    col_list = ", ".join(columns)
    placeholders = ", ".join([f":{c}" for c in columns])
    # 获取主键列名用于 ON DUPLICATE KEY UPDATE
    pk_cols = [c.name for c in table.primary_key.columns]
    update_cols = [c for c in columns if c not in pk_cols]
    update_clause = ", ".join([f"{c}=VALUES({c})" for c in update_cols])

    sql = (
        f"INSERT INTO {table.name} ({col_list}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_clause}"
    )

    with engine.begin() as conn:
        conn.execute(text(sql), rows)


def db_execute_with_retry(engine, sql_str, params=None, max_retries=3,
                          retry_delay=0.5):
    """
    带重试的数据库执行包装，自动处理 SQLite "database is locked" 错误。

    Parameters
    ----------
    engine : sqlalchemy.engine.Engine
    sql_str : str
        SQL 语句字符串。
    params : dict or list[dict], optional
        SQL 参数。
    max_retries : int
    retry_delay : float

    Returns
    -------
    result of conn.execute()
    """
    for attempt in range(max_retries):
        try:
            with engine.begin() as conn:
                result = conn.execute(text(sql_str), params or {})
                return result
        except Exception as e:
            err_msg = str(e).lower()
            is_retryable = any(kw in err_msg for kw in (
                "database is locked",
                "database is busy",
                "locked",
                "deadlock",
                "timeout",
            ))
            if is_retryable and attempt < max_retries - 1:
                wait = retry_delay * (2 ** attempt)
                logger.warning(
                    f"[db_utils] db_execute 重试 {attempt+1}/{max_retries} "
                    f"(等待={wait:.1f}s): {e}"
                )
                time.sleep(wait)
            else:
                raise
