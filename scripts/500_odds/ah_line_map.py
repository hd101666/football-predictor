# -*- coding: utf-8 -*-
"""亚盘盘口文字 -> 数值（主队视角）映射。

500.com 的 handline 文字格式实测样例：
    平手 / 平手/半球 / 半球 / 半球/一球 / 一球 / 一球/球半 /
    球半 / 球半/两球 / 两球 / 两球/两球半 / 两球半 ...
  以及受让前缀："受平手/半球"、"受半球" 等（主队受让，符号相反）

任务要求 line 为主队视角：
    主队让球 → 负数（-0.75 表示主队让半球/一球）
    主队受让 → 正数（+0.75 表示主队受平手/半球立场相反）

500.com 的 handline 描述的是【盘口本身】不带方向，需要配合 pan（盘路）或
直接按"主让/主受"语义判定。实测：handline 里带"受"字的才是主队受让。
"""
import re

# 基础盘口 -> 绝对值
BASE = {
    "平手": 0.0,
    "平手/半球": 0.25,
    "半球": 0.5,
    "半球/一球": 0.75,
    "一球": 1.0,
    "一球/球半": 1.25,
    "球半": 1.5,
    "球半/两球": 1.75,
    "两球": 2.0,
    "两球/两球半": 2.25,
    "两球半": 2.5,
    "两球半/三球": 2.75,
    "三球": 3.0,
    "三球/三球半": 3.25,
    "三球半": 3.5,
    "三球半/四球": 3.75,
    "四球": 4.0,
    "四球/四球半": 4.25,
    "四球半": 4.5,
    "四球半/五球": 4.75,
    "五球": 5.0,
}

# 别名（500.com 有时用不同写法）
ALIAS = {
    "平/半": 0.25,
    "半/一": 0.75,
    "一/球半": 1.25,
    "球半/两": 1.75,
    "两/两半": 2.25,
    "两半": 2.5,
    "两半/三": 2.75,
    "三/三半": 3.25,
    "三半": 3.5,
}


def handline_to_num(text, home_is_favorite=None):
    """把 500.com 的 handline 文字转成数值。

    参数：
        text             : 如 "半球/一球"、"受平手/半球"
        home_is_favorite : True=主队让球(负), False=主队受让(正), None=按文本判

    返回 (line: float|None, side: 'home_gives'|'home_receives'|None)
        line 为主队视角数值：负=主让，正=主受
    """
    if not text:
        return None, None
    t = str(text).strip().replace(" ", "")

    # 判断方向：带"受"=主队受让
    receives = t.startswith("受")
    core = t[1:] if receives else t

    val = BASE.get(core)
    if val is None:
        val = ALIAS.get(core)
    if val is None:
        # 兜底：用正则把 "X球/Y球" 拆成两个数和
        m = re.match(r"^([^/]+)/([^/]+)$", core)
        if m:
            a, b = BASE.get(m.group(1)), BASE.get(m.group(2))
            if a is not None and b is not None:
                val = round((a + b) / 2, 3)
    if val is None:
        return None, None

    # 已显式给了方向，覆盖文本
    if home_is_favorite is True:
        line = -abs(val)
        side = "home_gives"
    elif home_is_favorite is False:
        line = abs(val)
        side = "home_receives"
    else:
        if receives:
            line = abs(val)
            side = "home_receives"
        else:
            line = -abs(val)
            side = "home_gives"
    return round(line, 3), side


def ou_line_to_num(text):
    """大小球盘口文字 -> 数值（如 '2.5' / '两球半' / '2/2.5'）"""
    if not text:
        return None
    t = str(text).strip()
    try:
        return float(t)
    except ValueError:
        pass
    v, _ = handline_to_num(t)
    return abs(v) if v is not None else None


if __name__ == "__main__":
    tests = [
        "平手", "平手/半球", "半球", "半球/一球", "一球", "一球/球半",
        "球半", "球半/两球", "两球", "两球半", "三球", "四球半",
        "受平手/半球", "受半球", "受一球",
    ]
    print(f"{'文字':16} {'主队让球':>10} {'主队受让':>10}")
    print("-" * 42)
    for t in tests:
        g, _ = handline_to_num(t, home_is_favorite=True)
        r, _ = handline_to_num(t, home_is_favorite=False)
        print(f"{t:16} {g:>10.2f} {r:>10.2f}")
    print()
    print("自动判方向（按文本是否带'受'）:")
    for t in ["半球/一球", "受平手/半球"]:
        v, side = handline_to_num(t)
        print(f"  {t:14} -> line={v:+.2f}  side={side}")
