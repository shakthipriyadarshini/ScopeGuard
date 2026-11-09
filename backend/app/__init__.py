"""App factory: builds and configures the Flask app."""
from flask import Flask

from app.models import init_db
from config import Config


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Sessions are signed with SECRET_KEY, so it must exist
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("SECRET_KEY is missing. Copy .env.example to .env and set it.")

    init_db(app.config["DATABASE_URL"])  # connect DB + create tables

    # Imported here (not at the top) to avoid circular imports
    from app.routes import auth, payments, projects

    app.register_blueprint(auth.bp)
    app.register_blueprint(projects.bp)
    app.register_blueprint(payments.bp)

    return app
