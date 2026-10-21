# -*- coding: utf-8 -*-
# env_setup.py — 环境变量加载 + 全局初始化
# 所有爬虫统一 import env_setup 即可完成：.env 加载 + 日志配置 + stdout 编码 + SSL 路径
import os
import sys
import logging

# ─── 1. stdout/stderr UTF-8 ────────────────────────────────────────────────
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# ─── 2. 加载 .env 文件 ─────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
    load_dotenv(_env_path, override=False)
except ImportError:
    pass  # 没有 python-dotenv 则用环境变量或 config.py fallback

# ─── 3. SSL 证书路径 ───────────────────────────────────────────────────────
_configured_cert = os.environ.get('SSL_CERT_FILE', r'F:\ssl_fix\cacert.pem')
if os.path.isfile(_configured_cert):
    SSL_CERT_PATH = _configured_cert
    os.environ.setdefault('SSL_CERT_FILE',  SSL_CERT_PATH)
    os.environ.setdefault('CURL_CA_BUNDLE', SSL_CERT_PATH)
else:
    # 证书文件不存在时使用系统/certifi默认CA，避免requests崩溃
    try:
        import certifi
        SSL_CERT_PATH = certifi.where()
        os.environ.setdefault('SSL_CERT_FILE',  SSL_CERT_PATH)
        os.environ.setdefault('CURL_CA_BUNDLE', SSL_CERT_PATH)
    except ImportError:
        SSL_CERT_PATH = None  # 让requests使用系统默认CA

# ─── 4. 统一日志配置 ───────────────────────────────────────────────────────
_logging_initialized = False

def init_logging(level=logging.INFO):
    """全局日志初始化（只执行一次）"""
    global _logging_initialized
    if _logging_initialized:
        return
    _logging_initialized = True
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
