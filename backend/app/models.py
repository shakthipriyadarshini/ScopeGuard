"""Database models (SQLAlchemy). Money is always stored as integer cents."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from werkzeug.security import check_password_hash, generate_password_hash

Base = declarative_base()

# Routes open a session like this:  with SessionLocal() as db: ...
SessionLocal = sessionmaker()


def init_db(database_url):
    """Connect SessionLocal to the database and create any missing tables."""
    engine = create_engine(database_url)
    SessionLocal.configure(bind=engine)
    Base.metadata.create_all(engine)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)  # never store the raw password

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    client_name = Column(String, nullable=False)
    invite_token = Column(String, unique=True, nullable=False)  # for the client link (later)
    freelancer_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    milestones = relationship("Milestone", back_populates="project", order_by="Milestone.id")


class Milestone(Base):
    __tablename__ = "milestones"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    title = Column(String, nullable=False)
    amount_cents = Column(Integer, nullable=False)  # 6000 = $60.00
    status = Column(String, nullable=False, default="PENDING")  # PENDING or PAID
    agreement_version = Column(Integer, nullable=False, default=1)

    project = relationship("Project", back_populates="milestones")

    @property
    def amount_str(self):
        """6000 -> "60.00" (display now, and the string format PayPal wants later)."""
        return f"{self.amount_cents // 100}.{self.amount_cents % 100:02d}"


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True)
    milestone_id = Column(Integer, ForeignKey("milestones.id"), nullable=False)
    paypal_order_id = Column(String, unique=True)
    capture_id = Column(String)  # filled in after capture
    amount_cents = Column(Integer, nullable=False)
    currency = Column(String, nullable=False, default="USD")
    status = Column(String, nullable=False, default="CREATED")  # CREATED, CAPTURED or FAILED
    request_id = Column(String, nullable=False)  # PayPal idempotency key
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
