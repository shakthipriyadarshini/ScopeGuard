"""Create demo data:  python seed.py  (safe to run twice)."""
import json
from datetime import datetime, timezone

from app import create_app
from app.models import Agreement, Milestone, Project, SessionLocal, User

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
            description="Online store for a fashion brand: product pages, cart and checkout, admin dashboard.",
            freelancer_id=user.id,
        )
        project.publish()  # creates the invite token and sets status ACTIVE
        db.add(project)
        db.flush()

        # Agreement v1, already approved. Budget = the three milestones below ($200).
        scope = {
            "deliverables": ["Product catalog pages", "Shopping cart and checkout", "Admin dashboard"],
            "exclusions": ["Mobile app", "Content writing"],
            "timeline_days": 30,
        }
        agreement = Agreement(
            project_id=project.id,
            version=1,
            scope_json=json.dumps(scope),
            budget_cents=20000,
            status="ACTIVE",
            approved_at=datetime.now(timezone.utc),
        )
        agreement.content_hash = agreement.compute_hash()
        db.add(agreement)

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