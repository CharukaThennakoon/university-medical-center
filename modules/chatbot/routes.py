"""
modules/chatbot/routes.py - JSON endpoint used by the floating chat widget.

POST /chatbot/message   body: {"message": "...", "history": [{"role": "user"|"assistant", "text": "..."}]}
                        header: X-CSRFToken (the app-wide CSRF check in app.py enforces it)
Open to everyone (including visitors on the login page); the user's ROLE is
passed to the assistant, nothing else about them.
"""
from flask import Blueprint, jsonify, request, session

from modules.chatbot.service import answer

chatbot_bp = Blueprint("chatbot", __name__, url_prefix="/chatbot")


def _client_key():
    """Who is being rate limited: the logged-in user, otherwise the network address."""
    if "user_id" in session:
        return f"user:{session['user_id']}"
    return f"ip:{request.remote_addr or 'unknown'}"


@chatbot_bp.route("/message", methods=["POST"])
def message():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(ok=False, kind="error", reply="Invalid request."), 400

    result = answer(
        message=payload.get("message"),
        history=payload.get("history", []),
        role=session.get("role"),
        client_key=_client_key(),
    )
    response = jsonify(ok=result.ok, kind=result.kind, reply=result.reply)
    if result.retry_after:
        response.headers["Retry-After"] = str(result.retry_after)
    return response, result.status
