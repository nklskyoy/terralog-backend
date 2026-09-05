import os
import threading
import time
from flask import Flask
from flask_cors import CORS
from a2wsgi import WSGIMiddleware

from helpers import (
    FRONTEND_URL,
    TOKEN_1_ROTATION_SECONDS,
    _generate_token1
)
from routes import register_routes

app = Flask(__name__)
CORS(app)
asgi_app = WSGIMiddleware(app)

import logging

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _token_logger_loop():
    """Log the fixed static Token 1 on startup."""
    token1 = os.environ.get('STATIC_TOKEN1', 'dev_default_static_token')
    user_url = f"{FRONTEND_URL}/user?token={token1}"
    logger.info("\n" + "=" * 65)
    logger.info(f"[TERRALOG] STATISCHER ZUGANGS-TOKEN (STATIC_TOKEN1)")
    logger.info(f"  Token 1: {token1}")
    logger.info(f"  URL:     {user_url}")
    logger.info("=" * 65 + "\n")

def start_token_logger():
    """Start background logger thread once (now just executes immediately)."""
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        _token_logger_loop()


register_routes(app)
start_token_logger()

if __name__ == '__main__':
    app.run(debug=True)