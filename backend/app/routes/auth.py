"""Login / logout with Flask sessions, plus the authorization helpers."""
from functools import wraps

from flask import Blueprint, redirect, render_template, request, session, url_for

from app.models import SessionLocal, User

bp = Blueprint("auth", __name__)


def login_required(view):
    """Redirect to the login page if nobody is logged in."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def can_pay(milestone):
    """Who is allowed to pay this milestone?

    For now: the logged-in freelancer who owns the project.
    Tomorrow: replace the body with client invite-link access.
    (Call it while the milestone's DB session is still open.)
    """
    user_id = session.get("user_id")
    return user_id is not None and milestone.project.freelancer_id == user_id


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        with SessionLocal() as db:
            user = db.query(User).filter_by(email=email).first()
            if user and user.check_password(password):
                session.clear()  # start a fresh session on login
                session["user_id"] = user.id
                return redirect(url_for("projects.index"))

        # Same message for wrong email or wrong password
        return render_template("login.html", error="Invalid email or password."), 401

    return render_template("login.html", error=None)


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
