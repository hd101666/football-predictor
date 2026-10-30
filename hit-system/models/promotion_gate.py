# -*- coding: utf-8 -*-
"""promotion_gate.py — FIX-003 影子桶转正闸门（2026-09-12 终审修复）
=================================================================
背景（终审发现的问题）：全系统 14 个转正判定（_validation_result 的调用方）
共用"样本量+平注ROI+单尾95%CI+近30注哨兵"一套统计检验，但存在两个结构性漏洞：

1. **无预注册**：任何一个影子桶都可以在"看到数据之后"才被定义为候选——先观察到
   某桶近期 ROI 高，再决定"让它转正试试"，这相当于假设可以事后挑选，多重比较
   下的假阳性没有任何防护。本模块要求：桶必须先预注册（假设/门槛/最少样本写入
   promotion_registry.json，registered_at 必须早于观察窗口末端），注册前积累
   的数据不能用来给注册后定义的假设做转正证明。

2. **无多重比较防护**：14 个桶各自做 α=0.05 单尾检验，全部独立时为噪音放行的
   期望次数 ≈ 14×5% = 0.7 个/轮，长期滚动等于稳定地漏假阳性进真钱通道。
   采用终审给的两档方案中更可执行的一档：**每季度（自然季度）最多放行 1 个
   新转正**（硬规则）。Bonferroni 矫正会把单桶门槛抬到 α=0.05/14≈0.0036，
   以现有桶的样本增速实际上永远转不了正，等于冻结全部新信号，收益小于损失。

遗留桶豁免（2026-09-12 bootstrap）：FIX-003 落地前已经处于"转正"状态的桶
（football total/over 等）在 registry 里以 status='promoted' + promoted_at=
'legacy' 登记，registered_at=None——预注册规则无法追溯适用，由同阶段的
全量重审（_promotion_review_fix003.py 输出的保留/降级表）替代背书。
'legacy' 不占用季度额度。

registry 文件：promotion_registry.json（项目根目录，纳入 git 版本管理，
每次状态变更自动重写，全部字段留痕）。
"""
import json
import os
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_BASE = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(_BASE, "promotion_registry.json")

# 每自然季度最多放行的新转正数量（终审 FIX-003 硬规则）
QUARTERLY_PROMOTION_QUOTA = 1


def _load() -> dict:
    if not os.path.exists(REGISTRY_PATH):
        return {"version": 1, "entries": []}
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save(reg: dict) -> None:
    tmp = REGISTRY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, REGISTRY_PATH)  # 原子替换，避免写一半损坏


def _find(reg: dict, key: str):
    for e in reg.get("entries", []):
        if e.get("key") == key:
            return e
    return None


def _quarter(d: datetime) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _quarter_promotions(reg: dict, quarter: str) -> int:
    """本自然季度内已由闸门放行的新转正数（'legacy' 遗留登记不占额度）。"""
    n = 0
    for e in reg.get("entries", []):
        pa = e.get("promoted_at")
        if e.get("status") == "promoted" and pa and pa != "legacy":
            try:
                if _quarter(datetime.strptime(pa[:10], "%Y-%m-%d")) == quarter:
                    n += 1
            except ValueError:
                continue
    return n


def check_promotion_gate(gate_key: str, window_end: str | None,
                         logger=None) -> tuple[bool, str]:
    """转正闸门。_validation_result() 统计检验通过后调用。

    gate_key:   桶标识，如 'total_over:football'、'fotmob_totals:under'
    window_end: 本次判定所用样本的最新 fetch_date（观察窗口末端，'YYYY-MM-DD'）
    返回 (allowed, reason)。allowed=True 且是首次放行时，自动把 registry 里该桶
    置为 promoted 并写 promoted_at=今天（原子落盘留痕）。

    判定顺序（任一不过即拦截）：
      0. 已 promoted → 直接放行（历史遗留或本季度之前已放行，不重复占额度）
      1. 必须存在预注册条目（status='observing'），否则拦截
      2. registered_at 必须早于 window_end（注册前数据不算数），否则拦截
      3. 本季度已放行数 < QUARTERLY_PROMOTION_QUOTA，否则拦截
    """
    reg = _load()
    entry = _find(reg, gate_key)
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    if entry and entry.get("status") == "promoted":
        return True, "已转正（registry登记）"

    if entry is None:
        return False, ("未预注册：promotion_registry.json 中没有该桶条目，"
                       "需先登记假设/门槛/最少样本（注册后新积累的数据才计入转正判定）")

    reg_at = entry.get("registered_at")
    if not reg_at:
        return False, "预注册条目缺 registered_at，视为未注册"
    if not window_end:
        return False, "观察窗口末端未知（样本无fetch_date），无法验证注册先于观察"
    if str(reg_at)[:10] >= str(window_end)[:10]:
        return False, (f"注册时间({reg_at})不早于观察窗口末端({window_end})："
                       f"注册前积累的数据不能用于转正证明，需等注册后的新样本")

    q = _quarter(now)
    used = _quarter_promotions(reg, q)
    if used >= QUARTERLY_PROMOTION_QUOTA:
        return False, (f"多重比较防护：{q} 季度已放行 {used} 个新转正，"
                       f"达每季度最多 {QUARTERLY_PROMOTION_QUOTA} 个的硬上限，下季度再评")

    # 全部通过 → 首次放行，落 registry 留痕
    entry["status"] = "promoted"
    entry["promoted_at"] = today
    entry.setdefault("history", []).append(
        {"event": "promoted_by_gate", "at": now.strftime("%Y-%m-%d %H:%M:%S"),
         "window_end": window_end})
    _save(reg)
    msg = f"[promotion_gate] 放行新转正: {gate_key}（{q} 季度第 {used + 1} 个）"
    if logger:
        logger.warning(msg)
    else:
        print(msg)
    return True, "闸门通过（首次放行已登记）"


def register_candidate(key: str, hypothesis: str, min_samples: int,
                       min_roi: float, notes: str = "") -> bool:
    """预注册一个影子桶候选。已存在同 key 条目时不覆盖（返回 False）。"""
    reg = _load()
    if _find(reg, key) is not None:
        return False
    reg.setdefault("entries", []).append({
        "key": key,
        "hypothesis": hypothesis,
        "min_samples": min_samples,
        "min_roi": min_roi,
        "registered_at": datetime.now().strftime("%Y-%m-%d"),
        "status": "observing",
        "promoted_at": None,
        "notes": notes,
    })
    _save(reg)
    return True


if __name__ == "__main__":
    # 只读查看当前 registry 状态
    reg = _load()
    print(f"registry: {REGISTRY_PATH}")
    print(f"本季度({_quarter(datetime.now())})已放行: "
          f"{_quarter_promotions(reg, _quarter(datetime.now()))}/{QUARTERLY_PROMOTION_QUOTA}")
    for e in reg.get("entries", []):
        print(f"  {e['key']:<32} status={e.get('status'):<10} "
              f"registered_at={e.get('registered_at')} promoted_at={e.get('promoted_at')}")
        if e.get("notes"):
            print(f"    notes: {e['notes'][:120]}")
