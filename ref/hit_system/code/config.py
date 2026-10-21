# config.py — 全球双体育量化系统全局配置
import os, json
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件（项目根目录）
_ENV_FILE = Path(__file__).resolve().parent / '.env'
load_dotenv(_ENV_FILE, override=False)

# ========== 数据库 ==========
DB_DIR = os.environ.get("DB_DIR", r'D:\cl\qqsj\data')
os.makedirs(DB_DIR, exist_ok=True)
DB_ENGINE_URL = f'sqlite:///{DB_DIR}/sports_data.db'

# ========== 投注单输出目录 ==========
SLIP_OUTPUT_DIR = os.environ.get("SLIP_OUTPUT_DIR", r"D:\lucky")

# ========== 投注模式（FIX-001，2026-09-12）==========
# 真钱通道默认冻结：BETTING_MODE 默认 "paper"，投注单写 D:\lucky_paper\ 并带
# [纸面模式-非真钱投注] 水印；只有 BETTING_MODE="live" 且环境变量
# ENABLE_LIVE_BETTING=1 同时成立才写 D:\lucky\（双开关，缺一不可）。
# 原 D:\lucky\ 目录及历史文件不动。
PAPER_MODE = "paper"   # sanitized: original literal replaced, behavior identical
BETTING_MODE = os.environ.get("BETTING_MODE", PAPER_MODE)
SLIP_PAPER_DIR = os.environ.get("SLIP_PAPER_DIR", r"D:\lucky_paper")
PAPER_WATERMARK = "[纸面模式-非真钱投注]"

def is_live_betting() -> bool:
    """真钱投注双开关：config BETTING_MODE=live 且环境变量 ENABLE_LIVE_BETTING=1。"""
    return BETTING_MODE == "live" and os.environ.get("ENABLE_LIVE_BETTING") == "1"

def slip_output_dir() -> str:
    """当前模式下的投注单输出目录：live→SLIP_OUTPUT_DIR(D:\lucky)，否则纸面目录。"""
    return SLIP_OUTPUT_DIR if is_live_betting() else SLIP_PAPER_DIR

# ========== API-Sports 密钥（api-sports.io） ==========
APISPORTS_KEY_1 = os.environ.get("APISPORTS_KEY_1", "")  # 东叔新提供 ✅
APISPORTS_KEY_2 = os.environ.get("APISPORTS_KEY_2", "")  # 之前的（账户暂停，需解封）
APISPORTS_KEY_3 = os.environ.get("APISPORTS_KEY_3", "")  # 原密钥（每天100次）
APISPORTS_KEY = APISPORTS_KEY_3  # 原 key 唯一可用（新 key 均被暂停）

# ========== API-Sports 端点 ==========
BASKETBALL_API_BASE = "https://v1.basketball.api-sports.io"
FOOTBALL_API_BASE   = "https://v3.football.api-sports.io"
APISPORTS_HEADERS   = {"x-apisports-key": APISPORTS_KEY}

# ========== Tavily 搜索/舆情密钥 ==========
TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")

# ========== SharpAPI 密钥 ==========
SHARPAPI_KEY = os.environ.get("SHARPAPI_KEY", "")

# ========== The Odds API 密钥池（固定顺序轮换） ==========
# ★2026-10-09 安全修正：明文 Key 已从本文件移除（本文件被 git 跟踪 → 历史泄露面）。
#   全部 7 枚只从环境变量/.env 读取（.env 已被 .gitignore 忽略）。
#   若 .env 缺失对应键位 → 该槽 configured=False 会被直接跳过（不会静默用错 Key）。
THE_ODDS_API_KEYS=[
    {"key": os.environ.get("THE_ODDS_API_KEY_1", "REDACTED"), "remaining": 500},  # Key 1
    {"key": os.environ.get("THE_ODDS_API_KEY_2", "REDACTED"), "remaining": 500},  # Key 2
    {"key": os.environ.get("THE_ODDS_API_KEY_3", "REDACTED"), "remaining": 500},  # Key 3
    {"key": os.environ.get("THE_ODDS_API_KEY_4", "REDACTED"), "remaining": 500},  # Key 4
    {"key": os.environ.get("THE_ODDS_API_KEY_5", "REDACTED"), "remaining": 500},  # Key 5
    {"key": os.environ.get("THE_ODDS_API_KEY_6", "REDACTED"), "remaining": 500},  # Key 6
    {"key": os.environ.get("THE_ODDS_API_KEY_7", "REDACTED"), "remaining": 500},  # Key 7
    {"key": os.environ.get("THE_ODDS_API_KEY_8", "REDACTED"), "remaining": 500},  # Key 8 ★2026-10-09 新增
]
THE_ODDS_API_BASE = "https://api.the-odds-api.com/v4"

# Key 轮换规则（用户 2026-10-09 明确；★2026-10-09 由 7 枚扩为 8 枚）：
#   1 共 8 个 Key；2 每 Key 月度基准 500；3 固定顺序 1→8 轮换；
#   4 剩余额度「严格小于」50 时切下一枚有效 Key；5 恰好 50 仍可用；
#   6 不选余额最高者破坏既定顺序；7 过期缓存不得当最新余额；8 失败请求不换 Key 重试；
#   9 记录真实请求数/成本/响应；10 日志绝不打印 API Key。
# ★新增第 8 枚：2026-10-09 用户提供，实测 /sports 返回 remaining=500 used=0（满额新 Key）。
#   加入后 8 槽合计 remaining=511（原 7 槽合计 11），跨过 50 阈值 → 默认 BLOCK 解除。
# 下面 THE_ODDS_API_ROTATE_BELOW 即第 4 条的「严格小于」阈值。
THE_ODDS_API_ROTATE_BELOW = 50

# 配额持久化文件（跨重启保留真实余量，避免 config.py 静态值失效）
_QUOTA_CACHE_FILE = os.path.join(os.path.dirname(__file__), ".odds_api_quota.json")

# ========== The Odds API runtime quota pool (S05.2P) ==========
_QUOTA_SCHEMA_VERSION = "v3-the-odds-api-quota-cache/2"
_QUOTA_PROVIDER = "The Odds API"
_QUOTA_SELECTION_POLICY = "FIXED_DECLARATION_ORDER_ROTATE_BELOW_50_V1"
_QUOTA_SLOT_PREFIX = "THE_ODDS_API_SLOT_"
_QUOTA_INITIAL_REMAINING = 500
_SAFE_QUOTA_HEADERS = frozenset({
    "x-requests-remaining", "x-requests-used", "x-requests-cost", "x-requests-last",
})


def _quota_now_text():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _quota_period():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _quota_int(value):
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed >= 0 else None


def _quota_safe_headers(headers):
    result = {}
    if not hasattr(headers, "items"):
        return result
    for name, value in headers.items():
        lower = str(name).strip().lower()
        if lower not in _SAFE_QUOTA_HEADERS:
            continue
        rendered = str(value).strip()
        if len(rendered) <= 64 and "\r" not in rendered and "\n" not in rendered:
            result[lower] = rendered
    return dict(sorted(result.items()))


def _quota_slot_metadata(slot):
    return {
        "slot_id": slot["slot_id"],
        "configured": bool(slot.get("configured")),
        "enabled": bool(slot.get("enabled")),
        "configured_initial_remaining": int(slot.get("configured_initial_remaining", _QUOTA_INITIAL_REMAINING)),
        "remaining": int(slot.get("remaining", 0)),
        "remaining_status": str(slot.get("remaining_status", "UNKNOWN")),
        "remaining_source": str(slot.get("remaining_source", "UNKNOWN")),
        "provider_confirmed_remaining": slot.get("provider_confirmed_remaining"),
        "last_authoritative_remaining": slot.get("last_authoritative_remaining"),
        "effective_selection_remaining": int(slot.get("remaining", 0)),
        "last_response_time": slot.get("last_response_time"),
        "last_http_status": slot.get("last_http_status"),
        "last_status": str(slot.get("last_status", "NOT_YET_REQUESTED")),
        "exhausted": bool(slot.get("exhausted", False)),
    }


def _quota_cache_document():
    return {
        "schema_version": _QUOTA_SCHEMA_VERSION,
        "provider": _QUOTA_PROVIDER,
        "quota_period": _quota_period(),
        "selection_policy": _QUOTA_SELECTION_POLICY,
        "slots": [_quota_slot_metadata(slot) for slot in THE_ODDS_API_KEYS],
        "cache_updated_at": _quota_now_text(),
    }


def _save_quota_cache():
    # Explicit allowlist above prevents credential serialization.
    import tempfile
    payload = json.dumps(_quota_cache_document(), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False) + "\n"
    cache_parent = os.path.dirname(_QUOTA_CACHE_FILE)
    fd, temp_path = tempfile.mkstemp(prefix=".odds-quota-", suffix=".tmp", dir=cache_parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, _QUOTA_CACHE_FILE)
    finally:
        try:
            os.unlink(temp_path)
        except FileNotFoundError:
            pass


def _load_quota_cache():
    # Legacy credential-keyed caches are ignored and never copied forward.
    try:
        with open(_QUOTA_CACHE_FILE, "r", encoding="utf-8") as handle:
            cached = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError, UnicodeError):
        return
    if not isinstance(cached, dict):
        return
    if cached.get("schema_version") != _QUOTA_SCHEMA_VERSION:
        return
    if cached.get("provider") != _QUOTA_PROVIDER or cached.get("quota_period") != _quota_period():
        return
    by_slot = {
        item.get("slot_id"): item
        for item in cached.get("slots", [])
        if isinstance(item, dict) and isinstance(item.get("slot_id"), str)
    }
    for slot in THE_ODDS_API_KEYS:
        saved = by_slot.get(slot["slot_id"])
        if not isinstance(saved, dict):
            continue
        remaining = _quota_int(saved.get("remaining"))
        if remaining is None:
            continue
        slot["remaining"] = remaining
        slot["remaining_status"] = str(saved.get("remaining_status", "PERSISTED_UNCONFIRMED"))
        slot["remaining_source"] = "PERSISTED_CACHE"
        slot["provider_confirmed_remaining"] = _quota_int(saved.get("provider_confirmed_remaining"))
        slot["last_authoritative_remaining"] = _quota_int(saved.get("last_authoritative_remaining"))
        slot["last_response_time"] = saved.get("last_response_time")
        slot["last_http_status"] = saved.get("last_http_status")
        slot["last_status"] = str(saved.get("last_status", "NOT_YET_REQUESTED"))
        slot["exhausted"] = bool(saved.get("exhausted", remaining <= 0))


def get_the_odds_api_pool():
    """Internal runtime pool; callers must never serialize or log ``key``."""
    return [dict(slot) for slot in THE_ODDS_API_KEYS]


def get_the_odds_api_pool_metadata():
    """Secret-free structural view for diagnostics and evidence."""
    return [_quota_slot_metadata(slot) for slot in THE_ODDS_API_KEYS]


def _slot_dispatch_eligible(slot, rotate_below=THE_ODDS_API_ROTATE_BELOW):
    """单枚槽位是否可直接派发（固定顺序轮换口径）。

    不可派发：未配置/未启用 / AUTH_FAILED / exhausted / remaining 非数值 / <=0 / < rotate_below。
    注意：剩余恰好等于 50 视为可用（用户规则第 5 条）。
    """
    if slot.get("configured") is not True:
        return False
    if not (isinstance(slot.get("key"), str) and slot["key"].strip()):
        return False
    if slot.get("enabled") is not True:
        return False
    if str(slot.get("remaining_status")) == "AUTH_FAILED":
        return False
    if slot.get("exhausted") is True:
        return False
    rem = _quota_int(slot.get("remaining"))
    if rem is None or rem <= 0:
        return False
    return rem >= rotate_below


def select_slot_fixed_order(slots, rotate_below=THE_ODDS_API_ROTATE_BELOW):
    """纯函数：按声明顺序 1→7 选第一枚可派发槽位；全部不可用 → None（BLOCK）。

    与「选余额最高」相反：顺序优先，只有当前槽低于阈值才顺延。便于单元测试。
    """
    for slot in slots:
        if _slot_dispatch_eligible(slot, rotate_below):
            return dict(slot)
    return None


def select_slot_max_remaining_legacy(slots, rotate_below=1):
    """旧策略（仅留作对照/测试，生产不再使用）：选余额最高者。"""
    eligible = [s for s in slots
                if s.get("configured") is True and s.get("enabled") is True
                and _quota_int(s.get("remaining")) not in (None,)
                and s.get("remaining", 0) >= rotate_below
                and s.get("exhausted") is not True]
    if not eligible:
        return None
    return dict(max(eligible, key=lambda s: s["remaining"]))


def select_the_odds_api_slot(rotate_below=None):
    """固定顺序 1→7 轮换（剩余 < 阈值才切下一枚）；无可用槽位 → None（阻断派发）。

    rotate_below=None → 用 config 默认 THE_ODDS_API_ROTATE_BELOW(50)。
    仅在操作者显式降阈（如 35 号爬虫 `--allow-low-quota`）时才传入更小值；策略本身不变。
    """
    rb = THE_ODDS_API_ROTATE_BELOW if rotate_below is None else rotate_below
    return select_slot_fixed_order(THE_ODDS_API_KEYS, rb)


def _find_the_odds_api_slot(slot_id):
    for slot in THE_ODDS_API_KEYS:
        if slot.get("slot_id") == slot_id:
            return slot
    raise KeyError("unknown The Odds API slot")


def update_the_odds_api_quota(slot_id, *, http_status=None, headers=None,
                              response_time=None, transport_error=None):
    """Update only the selected slot; no retry or same-call failover."""
    slot = _find_the_odds_api_slot(slot_id)
    safe_headers = _quota_safe_headers(headers)
    raw_remaining = safe_headers.get("x-requests-remaining")
    remaining = _quota_int(raw_remaining) if raw_remaining is not None and raw_remaining.isdigit() else None
    slot["last_response_time"] = response_time or _quota_now_text()
    slot["last_http_status"] = http_status
    if http_status in (401, 403):
        slot.update(remaining=0, remaining_status="AUTH_FAILED", remaining_source="AUTH_STATUS",
                    last_status="AUTH_FAILED", exhausted=True)
    elif http_status == 429:
        slot["last_status"] = "RATE_LIMITED"
        if remaining is not None:
            slot.update(remaining=remaining, remaining_status="AUTHORITATIVE",
                        remaining_source="PROVIDER_HEADER", provider_confirmed_remaining=remaining,
                        last_authoritative_remaining=remaining, exhausted=(remaining == 0))
    elif transport_error:
        normalized = str(transport_error).upper()
        slot["last_status"] = normalized if normalized in {"TIMEOUT", "CONNECTION_ERROR"} else "NETWORK_ERROR"
    elif http_status is not None and 200 <= http_status < 300:
        slot["last_status"] = f"HTTP_{http_status}"
        if remaining is not None:
            slot.update(remaining=remaining, remaining_status="AUTHORITATIVE",
                        remaining_source="PROVIDER_HEADER", provider_confirmed_remaining=remaining,
                        last_authoritative_remaining=remaining, exhausted=(remaining == 0))
        else:
            slot["remaining_status"] = "STALE_OR_UNCONFIRMED"
    elif http_status is not None and http_status >= 500:
        slot["last_status"] = f"HTTP_{http_status}"
    else:
        slot["last_status"] = f"HTTP_{http_status}" if http_status is not None else "NO_RESPONSE"
    _save_quota_cache()
    return _quota_slot_metadata(slot)


def get_odds_api_key():
    selected = select_the_odds_api_slot()
    return selected.get("key") if selected else None


def update_odds_api_remaining(api_key, remaining):
    # Compatibility for legacy callers; matching stays internal and is never logged.
    for slot in THE_ODDS_API_KEYS:
        if slot.get("key") == api_key:
            update_the_odds_api_quota(slot["slot_id"], http_status=200,
                                      headers={"x-requests-remaining": str(remaining)})
            return


for _slot_index, _slot in enumerate(THE_ODDS_API_KEYS, start=1):
    _slot.setdefault("slot_id", f"{_QUOTA_SLOT_PREFIX}{_slot_index}")
    _slot["configured"] = isinstance(_slot.get("key"), str) and bool(_slot["key"].strip())
    _slot.setdefault("enabled", True)
    _slot.setdefault("configured_initial_remaining", _QUOTA_INITIAL_REMAINING)
    _slot.setdefault("provider_confirmed_remaining", None)
    _slot.setdefault("last_authoritative_remaining", None)
    _slot.setdefault("remaining_status", "INITIAL_CONFIGURED")
    _slot.setdefault("remaining_source", "CONFIG_INITIAL")
    _slot.setdefault("last_response_time", None)
    _slot.setdefault("last_http_status", None)
    _slot.setdefault("last_status", "NOT_YET_REQUESTED")
    _slot.setdefault("exhausted", _slot.get("remaining", 0) <= 0)

_load_quota_cache()

# 键位缺失时显式告警（不静默使用空 Key）
_missing_odds_slots = [s["slot_id"] for s in THE_ODDS_API_KEYS if not s.get("configured")]
if _missing_odds_slots:
    import logging as _logging
    _logging.getLogger("config").warning(
        "The Odds API: %d/%d 槽位未配置（.env 缺少对应 THE_ODDS_API_KEY_n）: %s",
        len(_missing_odds_slots), len(THE_ODDS_API_KEYS), ",".join(_missing_odds_slots))

# ========== 凯利/风控参数 ==========
KELLY_MAX_RATIO = 0.25
KELLY_SIGNAL_MAX = 0.50
KELLY_MIN_VALUE = 0.01
MIN_RECOMMEND_ODDS = 1.75   # 回退至Jun13水平：Jun13推荐赔率范围1.80~1.97，1.75覆盖全部
MAX_RECOMMEND_ODDS = 3.50   # 适度放宽上限：2.50+段ROI+82.5%为最佳区间

# 比分玩法(correct_score) 验证准入门槛：结算样本量和ROI都达标之前，
# 只在"足球比分预测单"展示+结算统计，不进单注分配/主推荐单（更不进串关白名单）
CORRECT_SCORE_VALIDATION_MIN_SAMPLES = 30   # 已结算(win/lose)样本数下限
CORRECT_SCORE_VALIDATION_MIN_ROI     = 0.05  # 平注ROI下限：拉到+5%强制比分玩法继续积累样本；
#    历史复盘(2026-07-17)：correct_score 累计ROI -43.3%(70注仅4胜)，
#    原0.0门槛未能拦住——可能是转正时早期样本ROI为正、后被新数据拉负。
#    拉到+5%后，除非比分玩法真的稳定盈利，否则不会进主推荐单。

# 比分玩法模型概率校准权重：2026-07-16复盘111个已结算样本发现Dixon-Coles格子概率
# (model_prob)系统性虚高——均值9.1% vs 实际胜率4.5%(2.02倍)，而真实赔率去水位隐含
# 概率(implied_prob)均值4.9%，跟实际胜率几乎完美吻合(1.08倍)。说明比分玩法之前是
# 全系统唯一一个不做"model vs market"融合、直接拿泊松原始概率去算edge/凯利仓位的
# 市场，这几乎必然把"模型自己算错概率"误判成"发现了市场定价错误的正edge"，是
# -33%~-40%平注ROI的主要原因。用小样本(n=111)对raw model_prob单独拟合逻辑回归
# 校准曲线接近全平(各分位预测都在4-5%附近，说明这个样本量下model_prob本身几乎没有
# 判别力)，与其硬套一条可能过拟合的曲线，改成跟其他市场同样的"model×market加权
# 融合"架构更稳健、更一致——权重比其他市场(book固定0.50)更偏向market，因为这里
# 已经证明market校准准而model校准差。
CORRECT_SCORE_MODEL_WEIGHT = 0.30   # calibrated_prob = 0.30*model_prob + 0.70*implied_prob

# 小球玩法(total/under, team_total/under) 验证准入门槛：MARKET_BIAS里小球默认bias=0.0
# (2026-06-29策略锁定"只推大球")，但一直在"小球影子观察单"里结算追踪真实命中率/ROI。
# 达标后 compute_hit_score() 会动态把bias改回1.00(不再强制乘0)，让小球也能进主推荐单，
# 不需要手动改MARKET_BIAS——用真实结算数据自动转正，跟比分玩法是同一套思路。
UNDER_VALIDATION_MIN_SAMPLES = 30

# 近期哨兵的时效上限（天）。转正门槛除全历史显著性外还有一道最近30注ROI哨兵，
# 但 _total_over/_correct_score/_corner 三个门槛读的是生产表而非影子桶——门槛
# 一关就不再产生新样本，窗口会永久冻结在失败样本上，门槛再也打不开(实测
# football total/over 冻结24天，而其全历史显著性其实已通过)。最新样本超过这个
# 天数即视为无近期数据，哨兵不再否决，退回只看全历史显著性。
VALIDATION_RECENT_MAX_AGE_DAYS = 21
UNDER_VALIDATION_MIN_ROI     = 0.0

# ========== 影子桶瘦身（FIX-007-3，2026-09-13） ==========
# 2026-09-12 全量转正重审（FIX_REPORT.md 附录B）中 n<50 且 ci_lower<0 的桶，
# 停止写入新影子记录（存量保留，不删历史）。判据数字（重算原始ci_lower，
# 与 _validation_result() 同一公式）：injury_impact:football n=2 ci=-1.8579；
# moneyline:basketball:away n=15 ci=-0.7298；fotmob_spread:away n=28 ci=-0.0045；
# fotmob_corner:corner_over n=43 ci=-0.0879。n=0 的两个桶（injury_impact篮球/
# team_total篮球）ci 无定义、本来就不产出，不在停写清单。
# 元素格式：(shadow_type, sport_code或None不限, outcome或None不限)
SHADOW_WRITE_STOP = frozenset({
    ("injury_impact", "football", None),
    ("moneyline", "basketball", "away"),
    ("fotmob_spread", None, "away"),
    ("fotmob_corner", None, "corner_over"),
})

def is_shadow_write_stopped(shadow_type: str, sport_code: str, outcome: str) -> bool:
    """FIX-007-3：该影子桶是否已停写。sport_code 的 soccer 归一为 football。"""
    sp = "football" if (sport_code or "").lower() in ("football", "soccer") else (sport_code or "").lower()
    for st, s, o in SHADOW_WRITE_STOP:
        if st != shadow_type:
            continue
        if s is not None and s != sp:
            continue
        if o is not None and o != (outcome or ""):
            continue
        return True
    return False

# 独赢玩法(moneyline: 足球胜平负/篮球独赢) 验证准入门槛：MARKET_BIAS里两个运动
# 都没配置moneyline的key，默认bias=0.0，只在"胜平负影子观察单"(足球)/"独赢影子观察单"
# (篮球)结算追踪。足球篮球分开判断（3选1 vs 2选1结构不同，样本不能混）。
MONEYLINE_VALIDATION_MIN_SAMPLES = 30
MONEYLINE_VALIDATION_MIN_ROI     = 0.0

# 篮球独赢(旧口径)"反着买"赔率下限(2026-08-03深度审计后新增)：最初只用"历史样本
# 从未低于1.3"这个观察值当下限，用户指出1.3本身也不是盈亏平衡点，必须用胜率反推——
# 已按盈亏平衡赔率=1/胜率重新计算：审计样本(按生产Top7/日截断，锁定决策当天真实
# 赔率，n=21)胜率57.14%，盈亏平衡赔率=1/0.5714≈1.75，低于1.75的候选平均期望值为负。
# 注意n=21太小，胜率本身95%置信区间是[35.98%,78.31%]，对应盈亏平衡赔率的合理范围
# 是[1.28,2.78]——1.75只是point estimate，不代表这条线本身很稳。该市场目前样本量
# (21~23)仍未达到_validation_result()的min_samples=30门槛、平注ROI仍为负，本质上
# 是"证据不足的策略"，这个赔率下限只是在证据不足的前提下把明显没有胜算的候选
# (赔率远低于盈亏平衡点)先挡掉，不代表赔率≥1.75的候选就有正期望值。
BASKETBALL_MONEYLINE_FADE_MIN_ODDS = 1.75

# LSTM(EMA+AR1,04_1_LSTM_时序状态模型.py)信号准入门槛：2026-07-16回测(真实历史赛果,
# 严格walk-forward)验证state_diff对净胜分有真实增量解释力(控制累计胜率差后
# 足球R^2+0.0102/篮球+0.0157)，但从未在实盘结算验证过，先只进"lstm_moneyline"/
# "lstm_1x2"影子观察单(shadow_recommendations)，跟现有model_prob按0.85/0.15
# 融合单独打分结算，达标后再考虑把这个权重正式并入get_model_probs()的p_fusion，
# 不是先接进主流程再看效果。
LSTM_VALIDATION_MIN_SAMPLES = 30
LSTM_VALIDATION_MIN_ROI     = 0.0

# 球队大小(team_total: 单队大小球，含team_total/team_total_home/team_total_away)
# 验证准入门槛（2026-07-19新增）：此前该市场既没有独立的影子观察单，也没有转正判断，
# 是个"可以生成候选、甚至混进正式推荐单，但从来没有历史数据能验证是否真的有价值"
# 的半成品市场——发现于用户核对`hit_recommendations`历史数据时(球队大小/大球25场
# 60.0%胜率，样本太小不足以下结论)。跟小球一样按sport_code分开判断（足球单队进球
# 0-3的分布和篮球单队得分80-120的分布完全不是一回事，样本不能混）。
TEAM_TOTAL_VALIDATION_MIN_SAMPLES = 30
TEAM_TOTAL_VALIDATION_MIN_ROI     = 0.0

# FotMob xG/射正信号（2026-07-20新增，见43_fotmob_match_data_scraper.py）验证准入门槛：
# 数据源当天才开始回填、零结算历史，按北极星原则不直接混入get_model_probs()的p_fusion，
# 跟LSTM信号同样处理——先进"fotmob_1x2"影子观察单，用现有model_prob和FotMob信号按
# 0.85/0.15融合单独打分结算，达标后再考虑正式并入，不是先接进主流程再看效果。
FOTMOB_VALIDATION_MIN_SAMPLES = 30
FOTMOB_VALIDATION_MIN_ROI     = 0.0

# 角球投注单（corner_model.py）验证准入门槛（2026-08-09追加）：此前该玩法直接以
# "正式推荐单"身份上线，唯一依据是corner_model.py里一行没有样本量/显著性支撑的
# 历史回测注释("EV≥10%+双队=65.2%胜率")，从未经过_validation_result()统一检验，
# 违反北极星原则和2026-08-01确立的"转正必须双重检验"规则（见项目记忆
# feedback_validation_significance_test）。现在补上跟FotMob信号同样的门槛，
# 降级为影子观察单直到达标。
CORNER_VALIDATION_MIN_SAMPLES = 30
CORNER_VALIDATION_MIN_ROI     = 0.0

# ========== P5: 推荐过滤 & 资金管理（200元本金） ==========
# 全局门槛：hit_score >= 此值才保留
HIT_SCORE_GLOBAL_THRESHOLD = 0.70  # 复盘校准(2026-07-17，2026-07-18复核修正)：
#    hermes(GLM)当时提出"7月total数据显示0.78+区间胜率显著高于0.70-0.77区间，应
#    上调至0.76"，但代码实际从未落地这个值(一直停留0.70，属于分析和执行没对上的
#    bug)。2026-07-18用真实hit_recommendations结算数据复核该claim时发现方向是反的：
#    market='total'，0.70-0.77区间已结算28场胜率57.1%，0.78+区间已结算68场胜率反而
#    只有50.0%（仅看outcome=over同样是0.70-0.77更高：56.5% vs 54.4%）。样本量不算大，
#    后续应继续观察，但现有数据不支持上调到0.76，维持0.70是当前更符合真实结算表现
#    的选择。教训：新代码里"已用回测/结算数据验证"的claim要抽查复核，不能只看注释
#    就当真——参见 feedback_hermes_backtest_claim_unverified 同类记录。
HIT_SCORE_V2_THRESHOLD     = 0.55  # v2公式阈值（价值边际驱动，量程不同）

# FIX-016-5（2026-09-15）：共识赔率最低源数底线。source_count < 本值的共识行
# 视为"单源共识"（实无共识可言，只是某一家赔率原样照抄），compute_consensus_odds
# 逐场/汇总 WARNING 标注、推荐单 reason 打"⚠共识仅N源"标签，供复盘对照单源
# 推荐的命中表现。注意：本底线只标注不拦截——历史数据显示绝大多数比赛的多数
# 市场天然只有单源（2026-09-13：12044/12462行=97%单源），拦截会清空推荐单。
CONSENSUS_MIN_SOURCES = 2

# 每场比赛最多推荐条数（每场只推命中分最高的一个方向）
MAX_RECS_PER_MATCH = 1

# 每日推荐上限（2026-08-02由20改为7，用户要求全部正式推荐单/影子观察单统一
# 按Top7规则，分散风险逻辑(每场≤1条+市场分散)保留不变，只收紧当日总量上限）
MAX_DAILY_RECOMMENDATIONS = 7

# ========== 市场偏置权重（仅推荐大球，2026-06-29 策略锁定）==========
# 策略：只推足球/篮球 total/over 和 team_total/over
# 实测: 足球 total/over 66.7%/+73.2%, 篮球 total/over 70.6%/+37.3%
# 其他玩法（独赢/让球/小球/胜平负）全部 bias=0.0 → hit_score归零 → 不推荐

# 足球/soccer 专用
MARKET_BIAS_FOOTBALL = {
    # total/over 加权2026-07-24复盘下调：1.15x是拿"66.7%/+73.2%"这个历史回测数字
    # 校准的，但复盘发现这个数字被FIFA俱乐部世界杯期间的11注(+25.2%ROI)显著抬高——
    # 剔除世界杯后，全历史其余83注实际是-4.25%ROI(50.0%胜率)，接近盈亏平衡而非
    # "核心暴利市场"；且07-13~07-22世界杯结束后这段时间(n=30)已经开始亏钱(-21.4%ROI)，
    # 校准差(预测胜率57.5% vs 实际40.0%)超出正常方差范围但样本还不够大不能下"模型
    # 失效"的结论。排查过程中已排除结算/数据bug(抽查比分匹配全部正确)、模型系统性
    # 高估(整体校准差仅-5.6%)、薄样本球队拖累(薄/厚样本两组降幅相近，非该因素主导)，
    # 判断是原校准基线本身不具代表性(依赖一次性赛事)而非可修复的具体bug。用户已
    # 确认下调到保守值，跟team_total同档，继续积累不含世界杯的新样本再评估是否恢复。
    ("total",       "over"):  (1.05, 0.65),
    ("team_total",  "over"):  (1.10, 0.65),   # 核心市场：62.2%/+48.8%
    # moneyline(胜平负)已于2026-07-24复盘验证转正后持续跑出正收益并小幅走高
    # (90天ROI+20.2%/n=84有效，近30天+17.4%/n=27有效，主客胜均为正)，加权幅度
    # 参照total/team_total同档，用户已确认加权。draw方向目前0结算样本，暂不配置。
    ("moneyline",   "home"):  (1.10, 0.65),
    ("moneyline",   "away"):  (1.10, 0.65),
}

# 篮球专用
MARKET_BIAS_BASKETBALL = {
    ("total",       "over"):  (1.20, 0.65),   # 核心市场：70.6%/+37.3%
    # team_total 已恢复（2026-07-06）：新增 compute_team_total_probs()（单队自己近40场
    # 得分均值/标准差建模，不再借用整场总分分布）后重新放开。注意：这个1.10倍率是当初
    # 拿旧的(有bug的)模型输出回测校准出来的，现在底层概率来源换了，倍率是否还准确
    # 需要重新积累结算数据验证，先沿用旧值观察，不代表已经过新模型校准。
    ("team_total",  "over"):  (1.10, 0.65),
    ("total_flip",  "under"): (0.90, 0.70),   # 反手小球：盘口线>联赛历史上限×1.05时触发，小幅折扣
    # moneyline(独赢)2026-07-24复盘发现主客胜方向分裂严重：客胜(away)90天ROI+74.6%
    # (n=20有效)非常强，主胜(home)反而-24.9%(n=20有效，亏钱)——原有的按sport聚合
    # 判定的_moneyline_validation_status()掩盖了这个分裂。只给away单独加权，home
    # 暂不配置(维持现状=靠_moneyline_validation_status()整体转正逻辑兜底为1.00，
    # 不额外加权)，用户已确认此方案；home是否需要收紧/排除留待样本积累后单独评估。
    ("moneyline",   "away"):  (1.15, 0.65),
}

# 兜底（未知运动类型，也只放行大球）
MARKET_BIAS = {
    ("total",       "over"):  (1.10, 0.65),
    ("team_total",  "over"):  (1.05, 0.65),
}

def get_market_bias(sport_code: str, market: str, outcome: str):
    """根据运动类型返回对应的市场偏置 (multiplier, min_threshold)
    未在白名单内的市场返回 (0.0, 1.0)，hit_score 归零后自动被过滤。
    """
    sc = (sport_code or "").lower()
    if sc in ("basketball", "basket"):
        table = MARKET_BIAS_BASKETBALL
    elif sc in ("football", "soccer"):
        table = MARKET_BIAS_FOOTBALL
    else:
        table = MARKET_BIAS
    # team_total_home/team_total_away（主客队各自独立盘口线，见team_total主客队身份
    # 修复）跟裸的"team_total"共用同一档偏置——bias是按"这个市场类型整体好不好"配置的，
    # 不需要主客队分开定倍率。
    lookup_market = "team_total" if (market or "").startswith("team_total") else market
    return table.get((lookup_market, outcome), (0.0, 1.0))

# ========== 小球专项风控 ==========
UNDER_MIN_HANDICAP = 2.5   # 小球盘口下限：低盘进球风险大，历史失败案例为2.75以下
UNDER_MAX_DAILY    = 3     # 每日小球推荐上限（样本尚小，保守控制）

# 联赛 Tier 加成
LEAGUE_TIER_BOOST = {
    "wc_boost": 1.10, # 世界杯/欧杯/美洲杯等顶级国际赛事（赔率高质量+国家队ELO加成）
    "tier1": 1.00,
    "tier2": 1.03,   # 次级联赛命中率最高，微加成
    "tier3": 0.88,   # 冷门联赛抑制
    "tier4": 0.60,   # 极冷门强抑制（由0.80降至0.60，配合门槛0.65基本过滤掉）
}

# 顶级国际赛事关键词 → wc_boost
LEAGUE_WC_BOOST_KEYWORDS = [
    "World Cup", "FIFA", "UEFA Euro", "Copa America", "Nations League",
    "African Cup", "AFCON", "Asian Cup", "Gold Cup",
]

# 低流动性篮球联赛：名称含 "NBL" 但实为州级/低级联赛，需在 tier2 匹配前拦截为 tier3
# 否则 "New Zealand - NBL" / "NBL1 North" 等会被 tier2 关键词 "NBL" 误捞起得到 ×1.03 加成
LEAGUE_TIER_LOW_BBALL_KEYWORDS = [
    "new zealand - nbl", "nbl1", "nbl 1",
    "nbl north", "nbl south", "nbl east", "nbl west", "nbl central",
]

# Bug修复(2026-07-22)：原来"Premier League"/"Serie A"是裸关键词直接进tier1，实测
# 命中了大量完全不相关的低级别联赛——"Australia - NorZone Premier League"(地区业余联赛)、
# "Australia - Queensland Premier League 3"(联赛自己命名都带"3"，第三级)、
# "Ecuador - Serie A"(厄瓜多尔顶级联赛，跟意甲Serie A同名但完全不是一个量级)都被
# 误判成跟英超/意甲同样的tier1(×1.00，比tier3的×0.88高出一截)。这两个词只对
# 英格兰/意大利本尊有效，改成需要国家名同时出现才算(见LEAGUE_TIER1_QUALIFIED)，
# 从裸关键词列表里移除。
LEAGUE_TIER1_KEYWORDS = [
    "La Liga", "Bundesliga", "Ligue 1",
    "Champions League", "Europa League", "Euroleague", "NBA", "WNBA",
]
# (国家关键词, 联赛关键词) 都要同时出现在名字里才算对应tier——防止"Premier League"/
# "Serie A"这类被全世界地区级/低级联赛copy命名的通用词裸匹配到不相关的联赛。
LEAGUE_TIER1_QUALIFIED = [
    ("england", "premier league"),
    ("italy", "serie a"),
]
LEAGUE_TIER2_KEYWORDS = [
    "Segunda", "Bundesliga 2", "Serie B", "Ligue 2",
    "Eredivisie", "Primeira", "Super Lig", "Pro League", "Premiership",
    "Eliteserien", "Allsvenskan", "Superliga", "MLS", "Major League Soccer", "J League", "J1",
    "J2", "J3", "K League", "Super League", "League One",
    "CBA", "NBB", "ACB", "BBL",
    "Serie A", "Primera Division",
    # "Primera B"(2026-07-26移除)：只匹配到Argentina - Primera B Metropolitana/Nacional
    # 两个联赛，大样本回测(market=total,outcome=over真实下注方向)显示这两个联赛
    # 平注ROI分别是-73.9%(n=7)/-18.2%(n=7)，明显不该拿tier2的+3%加成，
    # 降到tier3(0.88x)。样本量还不算大，值得继续观察，但方向两次独立检验一致。
    "Liga Profesional", "Liga 1", "Ekstraklasa",
    "Liga Portugal", "Nacional",
    "Iceland", "Faroe", "Ireland",
    "Portugal",
]
# 同上，"NBL"/"NPL"是被多国低级别/地区业余联赛广泛借用的通用缩写(实测"Uganda NBL"、
# "Australia - NPL Tasmania/Capital Territory/Northern NSW"等一堆地区业余联赛全部
# 被误判tier2)，改成需要限定国家/上下文才算，裸缩写从LEAGUE_TIER2_KEYWORDS移除。
# 澳大利亚的NBL(国家级职业联赛，跟NBL1系列地区业余联赛是两回事，NBL1已由
# LEAGUE_TIER_LOW_BBALL_KEYWORDS在更早的判断分支里排除)是唯一确认过的合法用法。
LEAGUE_TIER2_QUALIFIED = [
    ("australia", "nbl"),
]

# 各篮球联赛大小球总分线合理上限（异常预警用）。超过 cap × 1.05 的线视为定价异常，跳过大球改推反手小球。
# 上限基于实测推荐数据最大值适度上浮；未匹配到的联赛使用 BBALL_TOTAL_CAP_DEFAULT。
BBALL_TOTAL_CAP = {
    # "wnba" 必须排在 "nba" 之前：'nba' 是 'wnba' 的子串，子串匹配需要更具体的键先命中
    "wnba":       185.0,  # 实测最高180.5
    "nba":        235.0,  # 实测最高217.5
    "euroleague": 180.0,
    "eurocup":    180.0,
    "nbl1":       185.0,
    "nbl 1":      185.0,
    "bsn":        195.0,  # 实测最高192，上调至195
    "puerto rico": 195.0,
    "cba":        220.0,
    "ncaa":       155.0,
    "acb":        180.0,  # 实测最高177
    "spain":      180.0,
    "israel":     180.0,  # 实测最高177
}
BBALL_TOTAL_CAP_NZ_NBL = 185.0  # "new zealand" + "nbl" 组合：实测最高191，cap降至185更敏感
BBALL_TOTAL_CAP_DEFAULT = 200.0  # 未知篮球联赛默认上限（保守）

# ========== 联赛过滤 ==========
# 推荐最低 Tier（tier1/tier2/tier3/tier4），低于此级别的联赛不推荐
RECOMMEND_MIN_TIER = "tier3"

# 黑名单关键词：联赛名包含这些关键词的直接跳过
LEAGUE_BLACKLIST_KEYWORDS = [
    # 澳洲低级联赛
    "Queensland Premier", "NorZone", "NPL Victoria",
    "NPL Queensland Women", "NPL South Australia",
    "NPL Western Australia", "NPL Capital", "NPL New South Wales Women",
    # YB 中文名澳洲低级别
    "澳大利亚NBL1", "澳大利亚女子NBL1", "澳大利亚新南威尔士",
    "澳大利亚维多利亚", "澳大利亚昆士兰", "澳大利亚北部",
    "西澳大利亚", "南澳大利亚", "澳大利亚女子",
    "新西兰国家篮球", "新西兰北", "新西兰南", "新西兰中",
    # YB 模拟/电竞联赛（足球+篮球所有电竞盘）
    "PANDA独家", "PANDA", "梦幻对垒", "VS-", "EAFC", "NBA 2K",
    "模拟联赛", "电竞",
    # YB 土耳其/保加利亚/其他小联赛
    "土耳其EBBL", "保加利亚BBL", "前锋B队", "泰坦",
    # YB 更多低级别
    "墨西哥CIBACOPA", "阿根廷篮球联邦", "巴西女子篮球",
    "IPBL", "国际篮球女子友谊赛", "俄罗斯篮球",
    "FIBA 3x3",
    # 国家队级FIBA资格赛：实力悬殊场次多，大小球总分线系统性失准（0706复盘6场全灭）
    "FIBA - World Cup Europe Qualification",
    # 无结果源覆盖的冷门篮球联赛：推荐无法结算复盘，纯噪声（0706复盘4场查无比分）
    "Uruguay - Metro League", "Guatemala - LMM", "Paraguay - Primera",
    # 北欧/东欧低级
    "3. Deild", "2. Deild", "1. Deild",
    "Kansallinen Women", "Ykkonen", "Ykkosliiga",
    # 女子小联赛
    "Damallsvenskan", "SAFF",
    # 青年/替补
    "Reserve", "Youth", "U19", "U21", "U23", "U20",
    # 非标准市场
    "Bookings", "Corners", "Cards",
    # 德国低级
    "Regionalliga", "Oberliga",
    # 亚洲小联赛
    "V League", "Vietnam",
    # 西班牙丙级
    "Tercera", "FEB",
    # 其他小联赛
    "Venezuela", "Chinese Taipei", "El Salvador",
    "Costa Rica", "Dominican Republic", "Uganda",
]

# ========== 联赛中文名映射 ==========
LEAGUE_CN_MAP = {
    # 五大联赛
    "Premier League": "英超", "England - Premier League": "英超",
    "La Liga": "西甲", "Spain - La Liga": "西甲",
    "Bundesliga": "德甲", "Germany - Bundesliga": "德甲",
    "Serie A": "意甲", "Italy - Serie A": "意甲",
    "Ligue 1": "法甲", "France - Ligue 1": "法甲",
    # 次级联赛
    "England - Championship": "英冠", "Championship": "英冠",
    "England - League One": "英甲",
    "Spain - Segunda Division": "西乙", "Segunda Division": "西乙",
    "Germany - 2. Bundesliga": "德乙",
    "Italy - Serie B": "意乙",
    "France - Ligue 2": "法乙",
    # 亚洲
    "China - Super League": "中超", "csl": "中超",
    "China - League One": "中甲",
    "j1": "日职联", "Japan - J League": "日职联", "J1 League": "日职联",
    "Japan - J2/J3 League": "日职乙",
    "K League 1": "韩K联", "South Korea - K League 1": "韩K联",
    # 欧洲其他
    "Portugal - Primeira Liga": "葡超",
    "Netherlands - Eredivisie": "荷甲",
    "Turkey - Super League": "土超", "Turkey - Super Lig": "土超",
    "Scotland - Premiership": "苏超",
    "Norway - Eliteserien": "挪超", "Eliteserien": "挪超",
    "Sweden - Allsvenskan": "瑞典超", "Allsvenskan": "瑞典超",
    "Sweden - Damallsvenskan": "瑞典女超",
    "Sweden - Superettan": "瑞典甲",
    "Denmark - Superliga": "丹麦超",
    "Austria - Bundesliga": "奥超",
    "Switzerland - Super League": "瑞士超",
    "Poland - Ekstraklasa": "波兰超",
    "Bulgaria - First League": "保加利亚超",
    "Iceland - Premier League": "冰岛超",
    "Faroe Islands - Premier League": "法罗群岛超",
    "Ireland - Premier Division": "爱尔兰超",
    "Finland - Veikkausliiga": "芬超",
    # 欧战
    "Champions League": "欧冠", "Europe - Champions League": "欧冠",
    "Europa League": "欧联", "Europe - Europa League": "欧联",
    "Conference League": "欧协联",
    # 美洲
    "Brazil - Serie A": "巴甲",
    "Brazil - Serie B": "巴乙",
    "Argentina - Primera Division": "阿甲",
    "Chile - Primera Division": "智利甲",
    "Chile - Primera B": "智利乙",
    "Chile - Segunda Division": "智利乙",
    "CONMEBOL - Copa Libertadores": "解放者杯",
    "CONMEBOL - Copa Sudamericana": "南美杯",
    "USA - MLS": "美职联", "MLS": "美职联",
    "USA - MLS Next Pro League": "美职联发展",
    # 篮球
    "NBA": "NBA", "nba": "NBA", "USA - NBA": "NBA",
    "WNBA": "WNBA",
    "CBA": "CBA", "China - CBA": "CBA",
    "Europe - Euroleague": "欧篮联", "Euroleague": "欧篮联",
    "Europe - Eurocup": "欧篮杯",
    "Spain - ACB": "西甲篮球",
    "Germany - BBL": "德甲篮球",
    "CONMEBOL - Copa Sudamericana": "南美杯",
    "USA - MLS": "美职联", "MLS": "美职联",
    "USA - MLS Next Pro League": "美职联发展",
    "USA - National Womens Soccer League": "美国女足大联盟",
    "Spain - Primera Division Women": "西甲女足",
    "Chile - Primera Division Women": "智利女足",
    "Portugal - Nacional Championship Women": "葡女甲",
    "Portugal - Campeonato de Portugal Prio": "葡锦标",
    "Peru - Liga 1": "秘鲁甲",
    "Australia - NPL Queensland": "澳昆超",
    "Australia - NPL New South Wales": "澳新南超",
    "Australia - NPL Capital Territory": "澳首都联",
}

# ========== 队名中文映射 ==========
# Bug修复(2026-08-10)：本字典原名也叫TEAM_CN_MAP，被下面813行"中国球队名称映射"
# 那个同名字典覆盖丢失(Python同名变量后定义覆盖前定义)——中超18支球队+部分
# 南美/北欧小众球队的中文映射已经静默失效了不知道多久，没有任何报错，只是
# _get_team_cn()查不到这些球队时会retur回原文英文名。改名为LEGACY，在下面
# _get_team_cn()函数里加一层回退查找，不改变813行主字典任何现有行为(向后
# 兼容所有已依赖config.TEAM_CN_MAP的代码)，只是把这批丢失的映射重新接回
# 查找链路。
TEAM_CN_MAP_LEGACY_CSL = {
    # === 中超 ===
    "Wuhan Three Towns": "武汉三镇", "Yunnan Yukun": "云南玉昆",
    "Chengdu Rongcheng": "成都蓉城", "Shanghai Port": "上海海港",
    "Shanghai Shenhua": "上海申花", "Beijing Guoan": "北京国安",
    "Shandong Taishan": "山东泰山", "Zhejiang FC": "浙江队",
    "Tianjin Jinmen Tiger": "天津津门虎", "Henan FC": "河南队",
    "Changchun Yatai": "长春亚泰", "Cangzhou Mighty Lions": "沧州雄狮",
    "Meizhou Hakka": "梅州客家", "Shenzhen FC": "深圳队",
    "Qingdao Hainiu": "青岛海牛", "Nantong Zhiyun": "南通支云",
    "Dalian Pro": "大连人", "Qingdao West Coast": "青岛西海岸",
    # === 英超 ===
    "Arsenal": "阿森纳", "Manchester City": "曼城", "Liverpool": "利物浦",
    "Chelsea": "切尔西", "Manchester Utd": "曼联", "Tottenham": "热刺",
    "Newcastle": "纽卡斯尔", "Brighton": "布莱顿", "Aston Villa": "阿斯顿维拉",
    "West Ham": "西汉姆", "Crystal Palace": "水晶宫", "Brentford": "布伦特福德",
    "Fulham": "富勒姆", "Wolves": "狼队", "Everton": "埃弗顿",
    "Nottingham": "诺丁汉森林", "Bournemouth": "伯恩茅斯", "Leeds": "利兹联",
    "Leicester": "莱斯特城", "Burnley": "伯恩利", "Southampton": "南安普顿",
    "Sheffield Utd": "谢菲尔德联", "Luton": "卢顿", "Sunderland": "桑德兰",
    # === 西甲 ===
    "Real Madrid": "皇家马德里", "Barcelona": "巴塞罗那", "FC Barcelona": "巴塞罗那",
    "Atletico Madrid": "马德里竞技", "Real Sociedad": "皇家社会",
    "Real Betis": "皇家贝蒂斯", "Villarreal": "比利亚雷亚尔",
    "Athletic Bilbao": "毕尔巴鄂竞技", "Sevilla": "塞维利亚",
    "Valencia": "瓦伦西亚", "Celta Vigo": "塞尔塔",
    "Osasuna": "奥萨苏纳", "Girona": "赫罗纳", "Mallorca": "马洛卡",
    "Cadiz": "加的斯", "Rayo Vallecano": "巴列卡诺",
    "Getafe": "赫塔费", "Alaves": "阿拉维斯", "Granada": "格拉纳达",
    "Las Palmas": "拉斯帕尔马斯", "Almeria": "阿尔梅里亚",
    "Espanyol": "西班牙人", "Valladolid": "巴利亚多利德",
    "Real Valladolid": "巴利亚多利德", "Leganes": "莱加内斯",
    "Eibar": "埃瓦尔", "Zaragoza": "萨拉戈萨", "Real Zaragoza": "萨拉戈萨",
    "Malaga": "马拉加", "Castellon": "卡斯特利翁", "Burgos": "布尔戈斯",
    "Racing Santander": "桑坦德竞速", "Levante": "莱万特",
    "FC Andorra": "安道尔FC", "Tenerife": "特内里费",
    "Deportivo La Coruna": "拉科鲁尼亚",
    # === 德甲 ===
    "Bayern Munich": "拜仁慕尼黑", "Bayern": "拜仁慕尼黑",
    "Borussia Dortmund": "多特蒙德", "Dortmund": "多特蒙德",
    "RB Leipzig": "莱比锡", "Leverkusen": "勒沃库森",
    "Union Berlin": "柏林联合", "Freiburg": "弗赖堡",
    "Eintracht Frankfurt": "法兰克福", "Wolfsburg": "沃尔夫斯堡",
    "Hoffenheim": "霍芬海姆", "Mainz": "美因茨", "Monchengladbach": "门兴",
    "Werder Bremen": "不来梅", "Augsburg": "奥格斯堡",
    "Bochum": "波鸿", "Stuttgart": "斯图加特",
    "Heidenheim": "海登海姆", "Darmstadt": "达姆施塔特",
    "Koln": "科隆", "Hamburg": "汉堡", "Schalke": "沙尔克04",
    "Hertha Berlin": "柏林赫塔", "Hannover": "汉诺威",
    "St. Pauli": "圣保利", "Holstein Kiel": "基尔",
    # === 意甲 ===
    "Inter Milan": "国际米兰", "Inter": "国际米兰",
    "AC Milan": "AC米兰", "Juventus": "尤文图斯",
    "Napoli": "那不勒斯", "Roma": "罗马", "Lazio": "拉齐奥",
    "Atalanta": "亚特兰大", "Fiorentina": "佛罗伦萨",
    "Bologna": "博洛尼亚", "Torino": "都灵", "Monza": "蒙扎",
    "Udinese": "乌迪内斯", "Sassuolo": "萨索洛", "Empoli": "恩波利",
    "Cagliari": "卡利亚里", "Genoa": "热那亚", "Verona": "维罗纳",
    "Lecce": "莱切", "Salernitana": "萨勒尼塔纳", "Frosinone": "弗罗西诺内",
    "Cagliari": "卡利亚里", "Como": "科莫", "Parma": "帕尔马",
    "Venezia": "威尼斯", "Cremonese": "克雷莫纳",
    # === 法甲 ===
    "PSG": "巴黎圣日耳曼", "Paris Saint-Germain": "巴黎圣日耳曼",
    "Marseille": "马赛", "Monaco": "摩纳哥", "AS Monaco": "摩纳哥",
    "Lyon": "里昂", "Lille": "里尔", "Nice": "尼斯",
    "Lens": "朗斯", "Rennes": "雷恩", "Strasbourg": "斯特拉斯堡",
    "Toulouse": "图卢兹", "Montpellier": "蒙彼利埃",
    "Nantes": "南特", "Reims": "兰斯", "Brest": "布雷斯特",
    "Lorient": "洛里昂", "Clermont": "克莱蒙",
    "Le Havre": "勒阿弗尔", "Metz": "梅斯",
    # === 日职联 ===
    "Vissel Kobe": "神户胜利船", "Yokohama F. Marinos": "横滨水手",
    "Kawasaki Frontale": "川崎前锋", "Urawa Red Diamonds": "浦和红钻",
    "Kashima Antlers": "鹿岛鹿角", "FC Tokyo": "FC东京",
    "Sanfrecce Hiroshima": "广岛三箭", "Nagoya Grampus": "名古屋鲸八",
    "Cerezo Osaka": "大阪樱花", "Gamba Osaka": "大阪钢巴",
    "Sagan Tosu": "鸟栖砂岩", "Avispa Fukuoka": "福冈黄蜂",
    "Kashiwa Reysol": "柏太阳神", "Consadole Sapporo": "札幌冈萨多",
    "Shonan Bellmare": "湘南海洋", "Albirex Niigata": "新潟天鹅",
    "Kyoto Sanga": "京都不死鸟", "Jubilo Iwata": "磐田喜悦",
    "Tochigi": "枥木SC", "Nagano Parceiro": "长野帕塞罗",
    "Imabari": "今治", "Ryukyu": "琉球FC",
    # === NBA ===
    "Oklahoma City Thunder": "雷霆", "Boston Celtics": "凯尔特人",
    "Denver Nuggets": "掘金", "Minnesota Timberwolves": "森林狼",
    "Dallas Mavericks": "独行侠", "LA Clippers": "快船",
    "Milwaukee Bucks": "雄鹿", "Cleveland Cavaliers": "骑士",
    "New York Knicks": "尼克斯", "Philadelphia 76ers": "76人",
    "Miami Heat": "热火", "Indiana Pacers": "步行者",
    "Orlando Magic": "魔术", "Los Angeles Lakers": "湖人",
    "Phoenix Suns": "太阳", "Sacramento Kings": "国王",
    "Golden State Warriors": "勇士", "Houston Rockets": "火箭",
    "San Antonio Spurs": "马刺", "Memphis Grizzlies": "灰熊",
    "New Orleans Pelicans": "鹈鹕", "Chicago Bulls": "公牛",
    "Atlanta Hawks": "老鹰", "Brooklyn Nets": "篮网",
    "Toronto Raptors": "猛龙", "Charlotte Hornets": "黄蜂",
    "Detroit Pistons": "活塞", "Portland Trail Blazers": "开拓者",
    "Utah Jazz": "爵士", "Washington Wizards": "奇才",
    # === 其他常见队 ===
    "Palmeiras": "帕尔梅拉斯", "Chapecoense": "沙佩科恩塞",
    "Cobreloa": "科布雷洛亚", "CSD Rangers": "流浪者",
    "Thor Akureyri": "索尔阿克雷里", "Stjarnan": "斯塔尔南",
    "Gil Vicente": "吉维森特", "Rio Ave": "里奥阿维",
    "Alianza Atletico": "竞技联盟", "Alianza Lima": "利马联盟",
    "FBC Melgar": "梅尔加", "Los Chankas": "洛斯昌卡斯",
    "UTC de Cajamarca": "卡哈马卡UTC", "FC Cajamarca": "卡哈马卡",
    "Brujas de Salamanca": "萨拉斯魔术师", "Santiago City": "圣地亚哥城",
    "Orlando City": "奥兰多城", "Chattanooga": "查塔努加",
    "Orlando City II": "奥兰多城B队",
    "NJ/NY Gotham FC": "哥特姆FC", "Houston Dash": "休斯顿短跑",
    "Olympic FC": "奥林匹克FC", "Brisbane City": "布里斯班城",
    "Madrid CFF": "马德里CFF", "Universidad de Concepcion": "康塞普西翁大学",
    "Palestino": "巴勒斯蒂诺",
    "Oliveira do Hospital": "奥利维拉医院", "Atletico Malveira": "马略维拉竞技",
    "Kristianstads": "克里斯蒂安斯塔德", "Hacken": "哈肯",
    "Broadbeach United": "布罗德海滩联", "St George Willawong": "圣乔治",
    "Deportivo Tachira": "塔奇拉竞技",
}

# ========== 资金管理（200元本金） ==========
BANKROLL = 200

# 单注策略
SINGLE_BET_PCT = 0.02      # 2% = 4元/注（基准）
SINGLE_BET_MAX = 10        # 每日最多10注单注

# P3: 动态Kelly — 根据hit_score调整单注金额
# hit_score区间 → 乘数系数（基准=1.0）
DYNAMIC_KELLY_SCALE = {
    (0.90, 1.01): 2.0,    # 极高信心 → 2倍 = 12元
    (0.80, 0.90): 1.5,    # 高信心 → 1.5倍 = 9元
    (0.70, 0.80): 1.0,    # 标准 → 6元
    (0.60, 0.70): 0.7,    # 低信心 → 0.7倍 = 4元
    (0.00, 0.60): 0.5,    # 很低 → 0.5倍 = 3元
}

# 串关策略（2-8串1，以小博大）
PARLAY_CONFIG = {
    #  n: (本金百分比, 每日最多几单)
    2: (0.020, 4),   # 2串1: 2%=4元, 最多4单, 胜率59%, 赔率4.8x
    3: (0.010, 3),   # 3串1: 1%=2元, 最多3单, 胜率45%, 赔率10x
    4: (0.010, 2),   # 4串1: 1%=2元, 最多2单, 胜率35%, 赔率23x
    5: (0.010, 1),   # 5串1: 1%=2元, 最多1单, 胜率27%, 赔率49x
    6: (0.010, 1),   # 6串1: 1%=2元, 最多1单, 胜率20%, 赔率107x
    7: (0.010, 1),   # 7串1: 1%=2元, 最多1单, 胜率16%, 赔率234x
    8: (0.010, 1),   # 8串1: 1%=2元, 最多1单, 胜率12%, 赔率510x
}

# 串关只串精选市场（回验胜率>70%, 正ROI）
PARLAY_ELIGIBLE_MARKETS = [
    ("total", "over"),
    ("team_total", "over"),
    ("spread", "home"),
]

# 风控
DAILY_LOSS_LIMIT_PCT = 0.30    # 日亏上限 30% = 60元
STOP_LOSS_STREAK = 3           # 连亏3注停手
HALF_BANKROLL = 120            # 本金<120减半投注

# ========== 七层融合权重 ==========
WEIGHT_POISSON     = 0.40
WEIGHT_LSTM        = 0.15
WEIGHT_TRANSFORMER = 0.15
WEIGHT_XG          = 0.10
WEIGHT_GNN         = 0.08
WEIGHT_RL          = 0.07
WEIGHT_MULTIMODAL  = 0.05

# ========== LSTM 训练参数 ==========
LSTM_SEQ_LENGTH = 10
LSTM_EPOCHS     = 15
LSTM_BATCH_SIZE = 32

# ========== 爬虫参数 ==========
CRAWL_MIN_SLEEP = 1
CRAWL_MAX_SLEEP = 3

# Pinnacle 角球赔率全量抓取时间预算（秒）：逐场遍历全球联赛耗时不可控，
# 超预算则跳过剩余联赛并保留已抓部分，避免被外层爬虫调度的 1800s 超时强杀导致 0 条落库
CORNER_SCRAPE_TIME_BUDGET_S = 1500

# ========== 联赛映射 (api-sports.io fallback) ==========
FOOTBALL_LEAGUE_ID_MAP = {
    39: 'premier_league', 140: 'laliga', 135: 'serie_a', 78: 'bundesliga',
    61: 'ligue_1', 169: 'csl', 98: 'j1', 292: 'k_league_1', 253: 'mls',
    71: 'serie_a_br', 203: 'super_lig', 88: 'eredivisie', 94: 'liga_portugal',
    144: 'pro_league_be', 235: 'rpl', 179: 'spfl_premiership', 119: 'superliga_dk',
    128: 'liga_argentina', 40: 'championship', 51: 'eliteserien', 58: 'allsvenskan',
}
BASKETBALL_LEAGUE_ID_MAP = {12: 'nba', 150: 'wnba', 229: 'cba', 117: 'euroleague'}

PRIORITY_FOOTBALL_LEAGUES = ['premier_league', 'laliga', 'bundesliga', 'serie_a', 'ligue_1',
                            'mls', 'j1', 'csl', 'k_league_1']
PRIORITY_BASKETBALL_LEAGUES = ['nba', 'wnba']

FOOTBALL_LEAGUE_LIST = list(FOOTBALL_LEAGUE_ID_MAP.values())
BASKETBALL_LEAGUE_LIST = list(BASKETBALL_LEAGUE_ID_MAP.values())

# ========== 预测模型参数 ==========
POISSON_HOME_ADV_XG  = 1.08   # understat xG 主场优势系数
POISSON_HOME_ADV_SOT = 1.06   # 射正/FBref xG 主场优势系数
KELLY_FRACTION       = 0.25   # 四分之一 Kelly
BBALL_SIGMA_BREF     = 13.0   # Basketball-Reference 模型得分标准差
BBALL_SIGMA_PACE     = 14.0   # 回合制大小球标准差
NBA_HOME_ADV_PTS     = 2.5    # NBA 主场优势分差

# ========== K值融合概率口径（p_fusion = W_BOOK×P_book + W_POISSON×P_poisson + W_ELO×P_elo） ==========
# FIX-007-4（2026-09-13）维持 0.50/0.30/0.20 不变的理由：该组权重是初始设定值
# （git历史实证：随首个commit引入，之后从未做过权重扫描/回测），没有任何样本外
# 证据证明其他组合更优；而调整它属于"现有特征上的模型调优"，按模型宪章
# （CLAUDE.md，终审41/42单元格市场占优+B臂-15.2%）一律禁止，除非绑定新信息源+
# 预注册+独立CLV纸面验收通过。在出现这种证据之前维持现状是唯一合规选择。
FUSION_W_BOOK    = 0.50   # 庄家隐含概率权重
FUSION_W_POISSON = 0.30   # 泊松/xG 模型权重
FUSION_W_ELO     = 0.20   # ELO 模型权重

# ========== RapidAPI 备用密钥（暂未订阅，留存备用） ==========
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "REDACTED")
RAPIDAPI_KEY_SPARE = os.environ.get("RAPIDAPI_KEY_SPARE", "REDACTED")

# ========== API-Basketball (RapidAPI) ==========
API_BASKETBALL_HOST = "api-basketball.p.rapidapi.com"

# ========== Sportradar Global Basketball API ==========
# 注册地址: https://developer.sportradar.com/  试用key 100次/月
SPORTRADAR_API_KEY = os.environ.get("SPORTRADAR_API_KEY", "REDACTED")
SPORTRADAR_BASE_URL = "https://api.sportradar.com/basketball/trial/v8/en"

# ========== BetsAPI ==========
# 注册地址: https://betsapi.com/  付费订阅获取 token
BETSAPI_TOKEN = os.environ.get("BETSAPI_TOKEN", "REDACTED")
BETSAPI_BASE_URL = "https://api.betsapi.com/v2"

# ========== TheSports API ==========
# 注册地址: https://thesports.com/  付费订阅
THESPORTS_USER   = os.environ.get("THESPORTS_USER", "REDACTED")
THESPORTS_SECRET = os.environ.get("THESPORTS_SECRET", "REDACTED")
THESPORTS_BASE_URL = "https://api.thesports.com/v1"

# ========== Highlightly (RapidAPI) ==========
# RapidAPI上搜索 "highlightly basketball"，订阅后获得与RAPIDAPI_KEY相同的key
HIGHLIGHTLY_HOST = "highlightly.p.rapidapi.com"

# Pinnacle Guest API Key（来自官网 JS 内置）
PINNACLE_GUEST_KEY = os.environ.get("PINNACLE_GUEST_KEY", "")

# api-sports.io key 回退函数（三个 key 自动轮换）
_APISPORTS_HEADERS_CACHE = {}  # 缓存当前成功使用的 key 序号

def get_apisports_headers(fallback=False):
    """返回 api-sports.io 请求头，fallback=True 时用旧 key"""
    key = APISPORTS_KEY_3 if fallback else APISPORTS_KEY
    return {"x-apisports-key": key}

def apisports_fallback_headers(last_response):
    """如果上次请求返回 errors，自动回退到下一个 key"""
    try:
        if last_response and last_response.get("errors"):
            for key in [APISPORTS_KEY_2, APISPORTS_KEY_3]:
                if key != APISPORTS_KEY:
                    return {"x-apisports-key": key}
    except:
        pass
    return {"x-apisports-key": APISPORTS_KEY}

def rapidapi_headers(host: str) -> dict:
    return {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": host
    }

# ========== 联赛ID对照 ==========
# 注意：api-sports.io 的 FIBA 杯赛 league_id 可能需要在赛季更新时更换
LEAGUE_IDS = {
    "nba":     {"football": None, "basketball": 12},
    "wnba":    {"football": None, "basketball": 150},
    "cba":     {"football": None, "basketball": 229},
    "euroleague": {"football": None, "basketball": 117},
    "ucl":     {"football": 2,    "basketball": None},
    "europa":  {"football": 3,    "basketball": None},
    "epl":     {"football": 39,   "basketball": None},
    "laliga":  {"football": 140,  "basketball": None},
    "seriea":  {"football": 135,  "basketball": None},
    "bundesliga": {"football": 78,  "basketball": None},
    "ligue1":  {"football": 61,   "basketball": None},
    "csl":     {"football": 169,  "basketball": None},
    "jleague": {"football": 98,   "basketball": None},
    "kleague": {"football": 292,  "basketball": None},
    "mls":     {"football": 253,  "basketball": None},
}

# === The Odds API 联赛/赛事键名（api-sports.io 无法获取时用此 ===
ODDS_API_LEAGUES = {
    # ── 篮球 ──
    "basketball_nba":               "NBA",
    "basketball_wnba":              "WNBA",
    "basketball_euroleague":        "欧洲篮球联赛",
    "basketball_ncaab":             "NCAA篮球",
    "basketball_nbl":               "澳大利亚NBL",
    # ── 足球顶级联赛 ──
    "soccer_epl":                   "英超(EPL)",
    "soccer_spain_la_liga":         "西甲(LaLiga)",
    "soccer_germany_bundesliga":    "德甲(Bundesliga)",
    "soccer_italy_serie_a":         "意甲(SerieA)",
    "soccer_france_ligue_one":      "法甲(Ligue1)",
    "soccer_netherlands_eredivisie":"荷甲",
    "soccer_portugal_primeira_liga":"葡超",
    "soccer_turkey_super_league":   "土超",
    "soccer_belgium_first_div":     "比甲",
    "soccer_scotland_premiership":  "苏超",
    # ── 足球国际赛事 ──
    "soccer_fifa_world_cup":        "FIFA世界杯2026",
    "soccer_uefa_champs_league":    "欧冠(UCL)",
    "soccer_uefa_europa_league":    "欧联(UEL)",
    "soccer_conmebol_copa_libertadores": "美洲杯解放者杯",
    "soccer_conmebol_copa_sudamericana": "南美杯",
    # ── 足球次级联赛 ──
    "soccer_england_championship":  "英冠(Championship)",
    "soccer_germany_bundesliga2":   "德乙(Bundesliga2)",
    "soccer_spain_segunda_division":"西乙(Segunda)",
    "soccer_italy_serie_b":         "意乙(SerieB)",
    "soccer_france_ligue_two":      "法乙(Ligue2)",
    "soccer_germany_dfb_pokal":     "德国杯",
    # ── 足球美洲 ──
    "soccer_usa_mls":               "美职联(MLS)",
    "soccer_usa_nwsl":              "美国女子联赛",
    "soccer_brazil_serie_a":        "巴西甲",
    "soccer_brazil_serie_b":        "巴西乙",
    "soccer_argentina_primera_division": "阿根廷甲",
    # ── 足球亚洲 ──
    "soccer_china_superleague":     "中国超级联赛",
    "soccer_japan_j_league":        "日本J联赛",
    "soccer_south_korea_kleague1":  "韩国K联赛1",
    "soccer_australia_aleague":     "澳超",
    # ── 足球北欧 ──
    "soccer_sweden_allsvenskan":    "瑞典超",
    "soccer_sweden_superettan":     "瑞典乙",
    "soccer_norway_eliteserien":    "挪威超",
    "soccer_finland_veikkausliiga": "芬兰超",
    # ── 足球其他 ──
    "soccer_league_of_ireland":     "爱尔兰甲",
    "soccer_spain_segunda_division":"西乙",
    "soccer_greece_super_league":   "希腊超",
}

# ========== 中国球队名称映射 ==========
TEAM_CN_MAP = {
    # ============ NBA ============
    "Atlanta Hawks": "亚特兰大老鹰",
    "Boston Celtics": "波士顿凯尔特人",
    "Brooklyn Nets": "布鲁克林篮网",
    "Charlotte Hornets": "夏洛特黄蜂",
    "Chicago Bulls": "芝加哥公牛",
    "Cleveland Cavaliers": "克利夫兰骑士",
    "Dallas Mavericks": "达拉斯独行侠",
    "Denver Nuggets": "丹佛掘金",
    "Detroit Pistons": "底特律活塞",
    "Golden State Warriors": "金州勇士",
    "Houston Rockets": "休斯顿火箭",
    "Indiana Pacers": "印第安那步行者",
    "Los Angeles Clippers": "洛杉矶快船",
    "Los Angeles Lakers": "洛杉矶湖人",
    "Memphis Grizzlies": "孟菲斯灰熊",
    "Miami Heat": "迈阿密热火",
    "Milwaukee Bucks": "密尔沃基雄鹿",
    "Minnesota Timberwolves": "明尼苏达森林狼",
    "New Orleans Pelicans": "新奥尔良鹈鹕",
    "New York Knicks": "纽约尼克斯",
    "Oklahoma City Thunder": "俄克拉荷马雷霆",
    "Orlando Magic": "奥兰多魔术",
    "Philadelphia 76ers": "费城76人",
    "Phoenix Suns": "菲尼克斯太阳",
    "Portland Trail Blazers": "波特兰开拓者",
    "Sacramento Kings": "萨克拉门托国王",
    "San Antonio Spurs": "圣安东尼奥马刺",
    "Toronto Raptors": "多伦多猛龙",
    "Utah Jazz": "犹他爵士",
    "Washington Wizards": "华盛顿奇才",
    # ============ WNBA ============
    "Atlanta Dream": "亚特兰大梦想",
    "Chicago Sky": "芝加哥天空",
    "Connecticut Sun": "康涅狄格太阳",
    "Dallas Wings": "达拉斯飞翼",
    "Indiana Fever": "印第安那狂热",
    "Las Vegas Aces": "拉斯维加斯王牌",
    "Los Angeles Sparks": "洛杉矶火花",
    "Minnesota Lynx": "明尼苏达山猫",
    "New York Liberty": "纽约自由人",
    "Phoenix Mercury": "菲尼克斯水星",
    "Seattle Storm": "西雅图风暴",
    "Washington Mystics": "华盛顿神秘人",
    # ============ 欧洲足球五大联赛 ============
    # --- EPL ---
    "Arsenal": "阿森纳",
    "Aston Villa": "阿斯顿维拉",
    "Bournemouth": "伯恩茅斯",
    "Brentford": "布伦特福德",
    "Brighton": "布莱顿",
    "Burnley": "伯恩利",
    "Chelsea": "切尔西",
    "Crystal Palace": "水晶宫",
    "Everton": "埃弗顿",
    "Fulham": "富勒姆",
    "Ipswich": "伊普斯维奇",
    "Leeds United": "利兹联",
    "Leicester": "莱斯特城",
    "Liverpool": "利物浦",
    "Luton": "卢顿",
    "Manchester City": "曼彻斯特城",
    "Manchester United": "曼彻斯特联",
    "Newcastle": "纽卡斯尔联",
    "Norwich": "诺维奇",
    "Nottingham Forest": "诺丁汉森林",
    "Southampton": "南安普顿",
    "Tottenham": "托特纳姆热刺",
    "Watford": "沃特福德",
    "West Ham": "西汉姆联",
    "Wolverhampton": "狼队",
    # --- La Liga ---
    "Alaves": "阿拉维斯",
    "Athletic Bilbao": "毕尔巴鄂竞技",
    "Atletico Madrid": "马德里竞技",
    "Barcelona": "巴塞罗那",
    "Betis": "皇家贝蒂斯",
    "Celta Vigo": "塞尔塔",
    "Espanyol": "西班牙人",
    "Getafe": "赫塔费",
    "Girona": "赫罗纳",
    "Granada": "格拉纳达",
    "Las Palmas": "拉斯帕尔马斯",
    "Leganes": "莱加内斯",
    "Mallorca": "马洛卡",
    "Osasuna": "奥萨苏纳",
    "Rayo Vallecano": "巴列卡诺",
    "Real Madrid": "皇家马德里",
    "Real Sociedad": "皇家社会",
    "Sevilla": "塞维利亚",
    "Valencia": "瓦伦西亚",
    "Valladolid": "巴利亚多利德",
    "Villarreal": "比利亚雷亚尔",
    # --- Serie A ---
    "AC Milan": "AC米兰",
    "Atalanta": "亚特兰大",
    "Bologna": "博洛尼亚",
    "Cagliari": "卡利亚里",
    "Como": "科莫",
    "Empoli": "恩波利",
    "Fiorentina": "佛罗伦萨",
    "Genoa": "热那亚",
    "Inter": "国际米兰",
    "Juventus": "尤文图斯",
    "Lazio": "拉齐奥",
    "Lecce": "莱切",
    "Milan": "AC米兰",
    "Monza": "蒙扎",
    "Napoli": "那不勒斯",
    "Parma": "帕尔马",
    "Roma": "罗马",
    "Salernitana": "萨勒尼塔纳",
    "Sassuolo": "萨索洛",
    "Torino": "都灵",
    "Udinese": "乌迪内斯",
    "Venezia": "威尼斯",
    "Verona": "维罗纳",
    # --- Bundesliga ---
    "Augsburg": "奥格斯堡",
    "Bayer Leverkusen": "勒沃库森",
    "Bayern Munich": "拜仁慕尼黑",
    "Bochum": "波鸿",
    "Borussia Dortmund": "多特蒙德",
    "Borussia Monchengladbach": "门兴格拉德巴赫",
    "Darmstadt": "达姆施塔特",
    "Eintracht Frankfurt": "法兰克福",
    "Freiburg": "弗赖堡",
    "Heidenheim": "海登海姆",
    "Holstein Kiel": "荷尔斯泰因基尔",
    "Mainz": "美因茨",
    "RB Leipzig": "莱比锡红牛",
    "St. Pauli": "圣保利",
    "Stuttgart": "斯图加特",
    "Union Berlin": "柏林联合",
    "Werder Bremen": "云达不莱梅",
    "Wolfsburg": "沃尔夫斯堡",
    # --- Ligue 1 ---
    "Angers": "昂热",
    "Auxerre": "欧塞尔",
    "Brest": "布雷斯特",
    "Le Havre": "勒阿弗尔",
    "Lens": "朗斯",
    "Lille": "里尔",
    "Lyon": "里昂",
    "Marseille": "马赛",
    "Monaco": "摩纳哥",
    "Montpellier": "蒙彼利埃",
    "Nantes": "南特",
    "Nice": "尼斯",
    "Paris Saint Germain": "巴黎圣日耳曼",
    "PSG": "巴黎圣日耳曼",
    "Reims": "兰斯",
    "Rennes": "雷恩",
    "Strasbourg": "斯特拉斯堡",
    "Toulouse": "图卢兹",
    # --- MLS ---
    "Atlanta United FC": "亚特兰大联",
    "Austin FC": "奥斯汀FC",
    "Chicago Fire FC": "芝加哥火焰",
    "Colorado Rapids": "科罗拉多急流",
    "Columbus Crew": "哥伦布机员",
    "D.C. United": "华盛顿联",
    "FC Cincinnati": "辛辛那提FC",
    "FC Dallas": "达拉斯FC",
    "Houston Dynamo FC": "休斯顿迪纳摩",
    "LA Galaxy": "洛杉矶银河",
    "Los Angeles FC": "洛杉矶FC",
    "Minnesota United FC": "明尼苏达联",
    "Montreal Impact": "蒙特利尔冲击",
    "CF Montreal": "蒙特利尔CF",
    "Nashville SC": "纳什维尔SC",
    "New England Revolution": "新英格兰革命",
    "New York City FC": "纽约城FC",
    "New York Red Bulls": "纽约红牛",
    "Orlando City SC": "奥兰多城",
    "Philadelphia Union": "费城联合",
    "Portland Timbers": "波特兰伐木者",
    "Real Salt Lake": "皇家盐湖城",
    "San Jose Earthquakes": "圣何塞地震",
    "Seattle Sounders FC": "西雅图海湾人",
    "Sporting Kansas City": "堪萨斯城竞技",
    "Toronto FC": "多伦多FC",
    "Vancouver Whitecaps FC": "温哥华白帽",
    # --- J-League ---
    "Albirex Niigata": "新潟天鹅",
    "Avispa Fukuoka": "福冈黄蜂",
    "Cerezo Osaka": "大阪樱花",
    "FC Tokyo": "东京FC",
    "Gamba Osaka": "大阪钢巴",
    "Jubilo Iwata": "磐田喜悦",
    "Kashima Antlers": "鹿岛鹿角",
    "Kashiwa Reysol": "柏太阳神",
    "Kawasaki Frontale": "川崎前锋",
    "Kyoto Sanga": "京都不死鸟",
    "Machida Zelvia": "町田泽维亚",
    "Nagoya Grampus": "名古屋鲸八",
    "Sagan Tosu": "鸟栖砂岩",
    "Sanfrecce Hiroshima": "广岛三箭",
    "Shonan Bellmare": "湘南比马",
    "Shonan": "湘南比马",
    "Tokyo Verdy": "东京绿茵",
    "Urawa Red Diamonds": "浦和红钻",
    "Vissel Kobe": "神户胜利船",
    "Yokohama F. Marinos": "横滨水手",
    # --- K-League ---
    "Daegu FC": "大邱FC",
    "Daejeon Citizen": "大田市民",
    "Daejeon Hana Citizen": "大田韩亚市民",
    "Gangwon FC": "江原FC",
    "Gimcheon Sangmu": "金泉尚武",
    "Gwangju FC": "光州FC",
    "Incheon United": "仁川联",
    "Jeju United": "济州联",
    "Jeonbuk Hyundai Motors": "全北现代",
    "Pohang Steelers": "浦项制铁",
    "Seoul": "首尔FC",
    "FC Seoul": "首尔FC",
    "Suwon FC": "水原FC",
    "Suwon Samsung Bluewings": "水原三星",
    "Ulsan Hyundai": "蔚山现代",
    # --- CPL ---
    "Atletico Ottawa": "渥太华竞技",
    "Cavalry FC": "骑兵队",
    "Forge FC": "锻造FC",
    "HFX Wanderers": "哈利法克斯流浪者",
    "Pacific FC": "太平洋FC",
    "Valour FC": "英勇FC",
    "Vancouver FC": "温哥华FC",
    "York United FC": "约克联",
}

# 缩写匹配（用于 The Odds API 的短名称）
TEAM_ABBR_MAP = {
    "LA Clippers": "Los Angeles Clippers",
    "LA Lakers": "Los Angeles Lakers",
    "NY Knicks": "New York Knicks",
    "OKC": "Oklahoma City Thunder",
    "SAS": "San Antonio Spurs",
    "PHI": "Philadelphia 76ers",
    "CHA": "Charlotte Hornets",
    "MIL": "Milwaukee Bucks",
    "BOS": "Boston Celtics",
    "GSW": "Golden State Warriors",
    "BKN": "Brooklyn Nets",
    "DAL": "Dallas Mavericks",
    "DEN": "Denver Nuggets",
    "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans",
    "TOR": "Toronto Raptors",
    "UTA": "Utah Jazz",
    "DET": "Detroit Pistons",
    "MAN UTD": "Manchester United",
    "MAN CITY": "Manchester City",
    "TOT": "Tottenham",
    "ARS": "Arsenal",
    "CHE": "Chelsea",
    "LIV": "Liverpool",
    "NEW": "Newcastle",
    "LEI": "Leicester",
    "BAR": "Barcelona",
    "RMA": "Real Madrid",
    "ATM": "Atletico Madrid",
    "INTER": "Inter",
    "ACM": "AC Milan",
    "JUV": "Juventus",
    "NAP": "Napoli",
    "BAY": "Bayern Munich",
    "DOR": "Borussia Dortmund",
    "LEV": "Bayer Leverkusen",
    "PSG": "PSG",
    "MRS": "Marseille",
    "LYO": "Lyon",
    "MCO": "Monaco",
    "LOSC": "Lille",
}

def _get_team_cn(team_name: str) -> str:
    """
    获取球队中文名
    策略：直接匹配 → 缩写展开匹配 → WNBA去掉后缀匹配
    """
    if not team_name:
        return team_name
    # 1. 直接匹配
    if team_name in TEAM_CN_MAP:
        return TEAM_CN_MAP[team_name]
    # 2. 缩写展开匹配
    expanded = TEAM_ABBR_MAP.get(team_name)
    if expanded and expanded in TEAM_CN_MAP:
        return TEAM_CN_MAP[expanded]
    # 3. WNBA 队名带 "W" 后缀的处理
    if team_name.endswith("W") and team_name[:-1] in TEAM_CN_MAP:
        return TEAM_CN_MAP[team_name[:-1]]
    # 4. 尝试去掉空格后匹配
    no_space = team_name.replace(" ", "")
    for k, v in TEAM_CN_MAP.items():
        if k.replace(" ", "") == no_space:
            return v
    # 5. 回退查legacy字典(2026-08-10新增，见TEAM_CN_MAP_LEGACY_CSL上方说明)：
    # 中超及部分南美/北欧小众球队的映射，之前因同名字典覆盖静默丢失
    if team_name in TEAM_CN_MAP_LEGACY_CSL:
        return TEAM_CN_MAP_LEGACY_CSL[team_name]
    no_space_legacy = team_name.replace(" ", "")
    for k, v in TEAM_CN_MAP_LEGACY_CSL.items():
        if k.replace(" ", "") == no_space_legacy:
            return v
    # 6. 查不到就返回原名
    return team_name

# ========== 数据文件路径 ==========
DATA_DIR = "data"
FOOTBALL_NBA_DB = f"{DATA_DIR}/football_predictions.db"
BASKETBALL_NBA_DB = f"{DATA_DIR}/basketball_predictions.db"
DAILY_LOGS = f"{DATA_DIR}/daily_logs"
BACKTEST_RESULTS = f"{DATA_DIR}/backtest_results"
PREDICTION_SNAPSHOT = f"{DATA_DIR}/prediction_snapshot.db"
CAPITAL_FILE = f"{DATA_DIR}/capital_alloc.xlsx"
ODDS_CACHE = f"{DATA_DIR}/odds_cache.json"

# ========== 推送配置 ==========
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "REDACTED")
WXPUSHER_TOKEN = os.environ.get("WXPUSHER_TOKEN", "REDACTED")
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "REDACTED")
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "REDACTED")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "REDACTED")

# ========== 实时赔率 API（03_实时赔率抓取.py） ==========
SPORTSBOOK_BASE  = "https://api.the-odds-api.com/v4"
ODDS_FEED_BASE   = "https://api.the-odds-api.com/v4"

# ========== 参数动态覆盖（_auto_calibrate.py 写入，每100注触发一次） ==========
_OVERRIDES_FILE = os.path.join(os.path.dirname(__file__), '_param_overrides.json')
def _apply_overrides():
    try:
        with open(_OVERRIDES_FILE, 'r', encoding='utf-8') as _f:
            _ov = json.load(_f)
        global HIT_SCORE_GLOBAL_THRESHOLD
        if 'HIT_SCORE_GLOBAL_THRESHOLD' in _ov:
            HIT_SCORE_GLOBAL_THRESHOLD = float(_ov['HIT_SCORE_GLOBAL_THRESHOLD'])
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
        pass
_apply_overrides()
