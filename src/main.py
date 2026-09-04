import os
import threading
import time
from flask import Flask
from flask_cors import CORS

from helpers import (
    FRONTEND_URL,
    TOKEN_1_ROTATION_SECONDS,
    _generate_token1
)
from routes import register_routes

app = Flask(__name__)
CORS(app)

import logging

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _token_logger_loop():
    """Background loop logging new Token 1 and user page URL to terminal on every rotation."""
    last_window = -1
    while True:
        current_window = int(time.time()) // TOKEN_1_ROTATION_SECONDS
        if current_window != last_window:
            token1 = _generate_token1(current_window)
            user_url = f"{FRONTEND_URL}/user?token={token1}"
            logger.info("\n" + "=" * 65)
            logger.info(f"[TERRALOG] TOKEN 1 ROTATION (Gültig für 5 Min)")
            logger.info(f"  Token 1: {token1}")
            logger.info(f"  URL:     {user_url}")
            logger.info("=" * 65 + "\n")
            last_window = current_window
        time.sleep(2)


def start_token_logger():
    """Start background logger thread once."""
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
        t = threading.Thread(target=_token_logger_loop, daemon=True)
        t.start()


register_routes(app)
start_token_logger()

if __name__ == '__main__':
    app.run(debug=True)