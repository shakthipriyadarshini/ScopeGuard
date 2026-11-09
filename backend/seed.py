"""Create demo data:  python seed.py  (safe to run twice)."""
import secrets

from app import create_app
from app.models import Milestone, Project, SessionLocal, User

create_app()  # connects the database and creates the tables

with SessionLocal() as db:
    if db.query(User).filter_by(email="demo@scopeguard.test").first():
        print("Demo data already exists. Delete scopeguard.db to start fresh.")
    else:
        # Demo freelancer
        user = User(name="Demo Freelancer", email="demo@scopeguard.test")
        user.set_password("demo1234")
        db.add(user)
        db.flush()  # gives user.id without committing yet

        # One project for that freelancer
        project = Project(
            title="E-commerce Website",
            client_name="Fashion Store",
            invite_token=secrets.token_urlsafe(16),
            freelancer_id=user.id,
        )
        db.add(project)
        db.flush()

        # Three milestones, amounts in cents
        db.add_all(
            [
                Milestone(project_id=project.id, title="Initial advance", amount_cents=6000),
                Milestone(project_id=project.id, title="Development completion", amount_cents=8000),
                Milestone(project_id=project.id, title="Final delivery", amount_cents=6000),
            ]
        )
        db.commit()
        print(f"Seeded. Log in as demo@scopeguard.test, then open /projects/{project.id}")
