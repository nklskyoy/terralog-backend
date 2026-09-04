import hashlib
import hmac
import os
import secrets
import time
from functools import wraps

import redis
from flask import request, jsonify

# Cache Initialization
REDIS_HOST = os.environ.get('REDIS_HOST', 'localhost')
cache = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)

# --- Config & Environments ---
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:5173')

# --- 1. Token 1: Short-lived rotating token (5 mins) ---
TOKEN_SECRET = os.environ.get('TERRALOG_SECRET', 'change-me-in-production')
TOKEN_1_ROTATION_SECONDS = 300  # 5 minutes

# --- 2. Token 2: Long-lived session token (2 hours) ---
TOKEN_2_LIFETIME_SECONDS = 7200  # 2 hours (7200s)

# --- 3. IP Restriction for /subscribe ---
ALLOWED_SUBSCRIBE_IPS = [ip.strip() for ip in os.environ.get('ALLOWED_SUBSCRIBE_IPS', '127.0.0.1,::1').split(',')]


def _generate_token1(window: int) -> str:
    """Generate hex Token 1 for a given time window."""
    msg = str(window).encode()
    return hmac.new(TOKEN_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def get_current_token1() -> str:
    """Return Token 1 for the current time window."""
    window = int(time.time()) // TOKEN_1_ROTATION_SECONDS
    return _generate_token1(window)


def _is_valid_token1(token: str) -> bool:
    """Accept the current or previous window's Token 1 to handle rotation edges."""
    if not token:
        return False
    window = int(time.time()) // TOKEN_1_ROTATION_SECONDS
    return hmac.compare_digest(token, _generate_token1(window)) or \
           hmac.compare_digest(token, _generate_token1(window - 1))


def create_session_token() -> str:
    """Generate a Token 2 (Session Token) and store in Redis with 2-hour TTL."""
    token2 = secrets.token_hex(32)
    cache.setex(f"session:{token2}", TOKEN_2_LIFETIME_SECONDS, "active")
    return token2


def _is_valid_session_token(token2: str) -> bool:
    """Check if Token 2 exists and is valid in Redis."""
    if not token2:
        return False
    return cache.exists(f"session:{token2}") == 1


def require_session_token(f):
    """Decorator enforcing valid 2-hour session Token 2 on endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get('Authorization', '')
        token2 = None
        if auth.startswith('Bearer '):
            token2 = auth.split(' ', 1)[1]
        elif request.headers.get('X-Session-Token'):
            token2 = request.headers.get('X-Session-Token')

        if not token2 or not _is_valid_session_token(token2):
            return jsonify({"error": "Ungültiger oder abgelaufener Sitzungs-Token (Token 2)"}), 401
        return f(*args, **kwargs)
    return decorated


def _is_localhost() -> bool:
    """Check if the request originates from localhost or Docker network."""
    client_ip = request.headers.get('X-Real-IP', request.remote_addr)
    
    if client_ip in ('127.0.0.1', '::1'):
        return True
    
    # Allow Docker bridge IPs (which appear when using SSH tunneling to localhost)
    if client_ip and client_ip.startswith(('172.', '192.168.', '10.')):
        return True
        
    return False
