"""Project pages. Only the project's owner can view them."""
import os

from flask import Blueprint, abort, redirect, render_template, session, url_for

from app.models import Payment, Project, SessionLocal
from app.routes.auth import can_pay, login_required

bp = Blueprint("projects", __name__)


@bp.get("/")
@login_required
def index():
    """No project list yet: send the user to their first project."""
    with SessionLocal() as db:
        project = (
            db.query(Project)
            .filter_by(freelancer_id=session["user_id"])
            .order_by(Project.id)
            .first()
        )
        if project is None:
            return "You have no projects yet."
        return redirect(url_for("projects.view_project", project_id=project.id))


@bp.get("/projects/<int:project_id>")
@login_required
def view_project(project_id):
    with SessionLocal() as db:
        project = db.get(Project, project_id)

        # Owner only. We return 404 (not 403) so ids of other projects are not revealed.
        if project is None or project.freelancer_id != session["user_id"]:
            abort(404)

        # Milestones that should show a PayPal button: still pending AND allowed to pay
        payable_ids = {
            m.id for m in project.milestones if m.status == "PENDING" and can_pay(m)
        }

        # PayPal capture id of each paid milestone, shown next to the PAID badge
        milestone_ids = [m.id for m in project.milestones]
        capture_ids = {
            p.milestone_id: p.capture_id
            for p in db.query(Payment).filter(
                Payment.milestone_id.in_(milestone_ids), Payment.status == "CAPTURED"
            )
        }

        # Render inside the "with" so the milestones can still be loaded
        return render_template(
            "project.html",
            project=project,
            payable_ids=payable_ids,
            capture_ids=capture_ids,
            # Only the public client id goes to the browser, never the secret
            paypal_client_id=os.environ.get("PAYPAL_CLIENT_ID"),
        )
