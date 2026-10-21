# -*- coding: utf-8 -*-
# http_utils.py — 公共 HTTP 工具模块
# 提供：StealthSession 基类（TLS指纹 + UA轮换 + Cookie热身 + 重试 + 429处理）
#       统一随机延迟 random_sleep()
#       统一 UA 池 DEFAULT_USER_AGENTS
#       赔率校验 valid_odds()
#
# 依赖: curl_cffi (必须)

import sys
import time
import random
import logging
from typing import Optional, List, Dict

log = logging.getLogger(__name__)

# ─── 依赖检测: curl_cffi ─────────────────────────────────────────────────────
try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    print("错误: curl_cffi 未安装。请先安装: pip install curl_cffi", file=sys.stderr)
    sys.exit(1)

# ─── SSL 修复：curl_cffi 无法处理含中文路径的 CA 证书 ───────────────────────────
import os as _os
_SSL_CA_FIXED = None
try:
    import certifi as _certifi_mod
    _ca_src = _certifi_mod.where()
    _ca_ascii = _os.path.join(_os.environ.get("TEMP", _os.environ.get("TMP", "REDACTED")), "cacert.pem")
    if not _os.path.exists(_ca_ascii):
        import shutil as _shutil
        _shutil.copy2(_ca_src, _ca_ascii)
    _SSL_CA_FIXED = _ca_ascii
    _os.environ["CURL_CA_BUNDLE"] = _SSL_CA_FIXED
    _os.environ["SSL_CERT_FILE"] = _SSL_CA_FIXED
except Exception:
    pass


# ─── 默认 TLS 指纹池 ─────────────────────────────────────────────────────────
DEFAULT_IMPERSONATES = [
    "chrome116", "chrome120", "chrome123", "chrome124", "chrome131",
    "chrome133a", "chrome136",
    "firefox133", "firefox135",
    "edge99", "edge101",
]


# ─── 默认 User-Agent 池（≥10 个现代 UA）─────────────────────────────────────
DEFAULT_USER_AGENTS = [
    # Chrome desktop
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    # Firefox desktop
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:133.0) Gecko/20100101 Firefox/133.0",
    # Edge
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
    # Mobile
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6422.165 Mobile Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
]


# ─── 随机延迟（正态分布）─────────────────────────────────────────────────────
def random_sleep(base: float = 1.5, sigma: float = 0.5):
    """
    正态分布随机延迟，截断到 [base*0.2, base*3.0] 范围。
    base  : 均值（秒），默认 1.5s
    sigma : 标准差（秒），默认 0.5s
    """
    lo = base * 0.2
    hi = base * 3.0
    delay = max(lo, min(hi, random.gauss(base, sigma)))
    time.sleep(delay)


# ─── 赔率值校验 ──────────────────────────────────────────────────────────────
def valid_odds(value) -> Optional[float]:
    """
    校验赔率值是否合法（正浮点数，且 >= 1.01）。
    返回 float 或 None。
    """
    if value is None:
        return None
    try:
        f = float(str(value).strip())
        return f if f >= 1.01 else None
    except (ValueError, TypeError):
        return None


# ─── StealthSession 基类 ────────────────────────────────────────────────────
class StealthSession:
    """
    统一的 HTTP 会话基类，封装：
    - curl_cffi TLS 指纹随机选择
    - UA 轮换
    - Cookie 热身（warm_up）
    - 带重试的 GET 请求（处理 429/403/503）
    - 指纹轮换（_rotate）

    子类可覆盖 _build_headers() 来添加站点特有 headers。
    """

    def __init__(self, base_url: str,
                 impersonates: List[str] = None,
                 user_agents: List[str] = None,
                 headers: Dict[str, str] = None):
        """
        base_url     : 站点根 URL（用于 warm_up）
        impersonates : TLS 指纹候选列表，默认 DEFAULT_IMPERSONATES
        user_agents  : UA 候选列表，默认 DEFAULT_USER_AGENTS
        headers      : 额外固定 headers（如 Referer / Accept 等）
        """
        self.base_url = base_url.rstrip("/")
        self._impersonates = impersonates or DEFAULT_IMPERSONATES
        self._user_agents = user_agents or DEFAULT_USER_AGENTS
        self._extra_headers = headers or {}
        self._imp = random.choice(self._impersonates)
        self._ua = random.choice(self._user_agents)
        self._sess = cffi_requests.Session(impersonate=self._imp, verify=_SSL_CA_FIXED) if _SSL_CA_FIXED else cffi_requests.Session(impersonate=self._imp)
        self._sess.headers.update({**self._build_headers(), "User-Agent": self._ua})
        self._warmed = False

    def _build_headers(self) -> Dict[str, str]:
        """子类可覆盖此方法来添加站点特有的 headers。"""
        return dict(self._extra_headers)

    def warm_up(self, path: str = "/"):
        """访问首页获取 Cookie，可选指定子路径。"""
        if self._warmed:
            return
        try:
            url = self.base_url + path
            r = self._sess.get(url, timeout=15, headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            })
            log.info(f"  热身 HTTP {r.status_code}")
            random_sleep(base=2.0, sigma=0.8)
        except Exception as e:
            log.warning(f"热身失败: {e}")
        self._warmed = True

    def _rotate(self):
        """轮换 TLS 指纹 + UA，重建会话。

        Bug修复(2026-08-12)：原先直接覆盖 self._sess，**从不关闭旧会话**——旧的
        libcurl 句柄/TLS 连接就此泄漏。get() 里每个URL最多轮换3次(attempt>=1时)，
        成百上千个URL累积下来会耗尽底层 OpenSSL 资源，症状是先
        "Connection closed abruptly"、随后恶化成
        "TLS connect error: OPENSSL_internal:invalid library"，并形成
        「失败→轮换→新建连接→资源更紧张→更多失败」的死亡螺旋。
        2026-08-12 实测 09_flashscore_schedule 补爬两轮全灭、日志里正是这个演化过程，
        而同日同样打 flashscore 的 16号/30号(轮换次数少)全部成功。
        同源问题 37_corner_stats_scraper.py 早有注释记载(那边的解法是复用模块级
        Session)，这里是公共基类，改成"换之前先关掉旧的"。
        """
        try:
            self._sess.close()
        except Exception:
            pass
        self._imp = random.choice(self._impersonates)
        self._ua = random.choice(self._user_agents)
        self._sess = cffi_requests.Session(impersonate=self._imp, verify=_SSL_CA_FIXED) if _SSL_CA_FIXED else cffi_requests.Session(impersonate=self._imp)
        self._sess.headers.update({**self._build_headers(), "User-Agent": self._ua})
        self._warmed = False

    def get(self, url: str, retries: int = 4, **kwargs) -> Optional[object]:
        """
        带重试的 GET 请求，自动处理 429/403/503。
        kwargs 透传给 curl_cffi requests.get()（如 params, headers, timeout）。
        返回 Response 对象或 None。
        """
        self.warm_up()
        timeout = kwargs.pop("timeout", 25)
        extra_headers = kwargs.pop("headers", {})
        for attempt in range(retries):
            try:
                r = self._sess.get(url, headers=extra_headers, timeout=timeout, **kwargs)
                if r.status_code == 200:
                    return r
                if r.status_code == 429:
                    wait = 20 * (attempt + 1)
                    log.warning(f"限流429，等待{wait}s...")
                    time.sleep(wait)
                    continue
                if r.status_code in (403, 503):
                    log.warning(f"拦截{r.status_code}（attempt {attempt+1}），轮换指纹...")
                    self._rotate()
                    self.warm_up()
                    time.sleep(5 + attempt * 3)
                    continue
                if r.status_code == 404:
                    return None
                log.warning(f"HTTP {r.status_code}: {url[:100]}")
            except Exception as e:
                log.warning(f"请求异常(attempt {attempt+1}): {e}")
                time.sleep(3 + attempt * 2)
                if attempt >= 1:
                    self._rotate()
        return None

    # ── 便捷方法 ──

    def get_json(self, url: str, retries: int = 4, **kwargs) -> Optional[dict]:
        """GET 请求并返回解析后的 JSON dict，失败返回 None。"""
        r = self.get(url, retries=retries, **kwargs)
        if r is not None:
            try:
                return r.json()
            except Exception:
                pass
        return None

    def get_text(self, url: str, retries: int = 4, **kwargs) -> Optional[str]:
        """GET 请求并返回响应文本，失败返回 None。"""
        r = self.get(url, retries=retries, **kwargs)
        return r.text if r is not None else None
