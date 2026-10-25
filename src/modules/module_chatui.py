"""Compatibility facade for the TARS browser interface.

New WebUI code belongs in :mod:`modules.webui`.  This module preserves the
public import path used by the runtime, QML controller, and older integrations.
"""

from modules.webui.application import (  # noqa: F401
    BOOT_ID,
    begin_bot_stream,
    flask_app,
    push_user_message,
    socketio,
    start_flask_app,
    stream_reply_token,
    update_emotion,
    _cloudflared_bin,
    _get_tunnel_status,
    _install_cloudflared,
    _start_tunnel,
    _stop_tunnel,
)

__all__ = [
    "BOOT_ID",
    "begin_bot_stream",
    "flask_app",
    "push_user_message",
    "socketio",
    "start_flask_app",
    "stream_reply_token",
    "update_emotion",
]
