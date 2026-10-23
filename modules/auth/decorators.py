"""
modules/auth/decorators.py - Route protection.

    @login_required                 -> any logged-in user
    @role_required("Doctor")        -> only that role (several roles allowed)

Not logged in  -> redirected to the login page.
Wrong role     -> HTTP 403 (Forbidden).
"""
from functools import wraps

from flask import abort, flash, redirect, request, session, url_for


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def role_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if session.get("role") not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)

        # login check runs first, then the role check
        return login_required(wrapped)

    return decorator
