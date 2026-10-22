"""Machine-readable description of the HTTP API.

The frontend is developed separately from this service, so it needs a stable,
discoverable contract. This blueprint publishes the route list (methods, paths
and required auth) as JSON, so the other team can generate clients or check
their integration without reading this source.
"""

import inspect

from flask import Blueprint, current_app, jsonify

bp = Blueprint("api_docs", __name__, url_prefix="/api")


def _requires_auth(view):
    """True when the view is protected by a JWT decorator."""
    try:
        source = inspect.getsource(view)
    except (OSError, TypeError):
        return False
    return "jwt_required" in source


@bp.get("/docs")
def docs():
    """Return the API contract: base URL, auth scheme and every route."""
    routes = []
    for rule in sorted(current_app.url_map.iter_rules(), key=lambda r: str(r)):
        if not str(rule).startswith("/api/"):
            continue
        methods = sorted(rule.methods - {"HEAD", "OPTIONS"})
        if not methods:
            continue
        view = current_app.view_functions.get(rule.endpoint)
        routes.append(
            {
                "path": str(rule),
                "methods": methods,
                "auth": "bearer" if view and _requires_auth(view) else "none",
                "endpoint": rule.endpoint,
            }
        )

    return jsonify(
        name="StarzChat API",
        version="1",
        base_url=current_app.config.get("API_BASE_URL", ""),
        auth={
            "scheme": "Bearer JWT",
            "header": "Authorization: Bearer <token>",
            "login": "POST /api/auth/login",
            "register": "POST /api/auth/register",
            "logout": "POST /api/auth/logout",
            "note": (
                "Logging out or changing the password invalidates every token "
                "already issued for that user."
            ),
        },
        realtime={
            "transport": "socket.io",
            "path": "/socket.io",
            "auth": {"token": "<jwt>"},
            "client_events": [
                "send_message",
                "typing",
                "read_receipt",
                "presence",
            ],
            "server_events": [
                "new_message",
                "message_updated",
                "message_deleted",
                "typing",
                "read_receipt",
                "presence",
                "error",
            ],
        },
        pagination={
            "messages": "GET /api/chats/<id>/messages?limit=&before=",
            "chats": "GET /api/chats?limit=&offset=",
        },
        rate_limits={
            "login": current_app.config.get("RATE_LIMIT_LOGIN"),
            "register": current_app.config.get("RATE_LIMIT_REGISTER"),
            "send": current_app.config.get("RATE_LIMIT_SEND"),
            "default": current_app.config.get("RATE_LIMIT_DEFAULT"),
        },
        routes=routes,
    )
