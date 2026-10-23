"""
app.py - Application entry point.
Run from PyCharm (right-click -> Run 'app') or:  python app.py
Then open http://127.0.0.1:5000
"""
import secrets
from datetime import timedelta

from flask import Flask, abort, render_template, request, session

from config import Config
from modules.admin.routes import admin_bp
from modules.auth.routes import auth_bp
from modules.chatbot.knowledge_base import get_kb
from modules.chatbot.routes import chatbot_bp
from modules.counter.routes import counter_bp
from modules.doctor.routes import doctor_bp
from modules.patients.routes import patients_bp
from modules.pharmacy.routes import pharmacy_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.config.update(
        PERMANENT_SESSION_LIFETIME=timedelta(hours=2),  # auto-logout
        SESSION_COOKIE_HTTPONLY=True,    # JavaScript cannot read the cookie
        SESSION_COOKIE_SAMESITE="Lax",
    )

    # ---- Blueprints -----------------------------------------------------
    for bp in (auth_bp, patients_bp, doctor_bp, pharmacy_bp, counter_bp,
               admin_bp, chatbot_bp):
        app.register_blueprint(bp)

    # ---- AI chatbot start-up checks (warnings only; the app still runs) --
    if Config.CHATBOT_ENABLED:
        get_kb()  # loads the knowledge base and logs any <<FILL IN>> details
        if not Config.GEMINI_API_KEY:
            app.logger.warning("GEMINI_API_KEY is not set - the chat widget will say the "
                               "assistant is not set up. Run: python check_chatbot.py")

    # ---- CSRF protection ------------------------------------------------
    # Every POST must carry the token stored in the user's session
    # (hidden form field "csrf_token" or header "X-CSRFToken" for JS/AJAX).
    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(16)
        return session["csrf_token"]

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def csrf_protect():
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            sent = (request.form.get("csrf_token")
                    or request.headers.get("X-CSRFToken", ""))
            expected = session.get("csrf_token", "")
            if not expected or not secrets.compare_digest(
                    sent.encode(), expected.encode()):
                abort(400)

    # ---- Do not cache pages (Back button after logout shows nothing) ----
    @app.after_request
    def no_cache(response):
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    # ---- Error pages ----------------------------------------------------
    def _error(code, title, message):
        return render_template("error.html", code=code, title=title,
                               message=message), code

    @app.errorhandler(400)
    def bad_request(_e):
        return _error(400, "Invalid request",
                      "Your form has expired or is invalid. "
                      "Go back, refresh the page and try again.")

    @app.errorhandler(403)
    def forbidden(_e):
        return _error(403, "Access denied",
                      "Your role does not have permission to open this page.")

    @app.errorhandler(404)
    def not_found(_e):
        return _error(404, "Page not found",
                      "The page you are looking for does not exist.")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=Config.DEBUG)
