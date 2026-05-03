from __future__ import annotations

import atexit
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

from src.api.routes_admin import bp as admin_bp
from src.api.routes_health import bp as health_bp
from src.api.routes_public_search import bp as public_search_bp
from src.config import clear_settings_caches, get_settings
from src.db.session import init_db, init_engine
from src.jobs.scheduler import start_scheduler
from src.logging_config import configure_logging, get_logger
from src.webhooks.facebook_webhook import bp as fb_webhook_bp


def create_app() -> Flask:
    if os.environ.get("RUNNING_PYTEST") != "1":
        load_dotenv()
    _repo = Path(__file__).resolve().parent.parent
    os.environ.setdefault("FC_SEARCHER_REPO_ROOT", str(_repo))
    if str(Path.cwd()) not in sys.path:
        sys.path.insert(0, str(Path.cwd()))

    clear_settings_caches()
    settings = get_settings()
    use_json = os.environ.get("LOG_JSON", "").lower() in {"1", "true", "yes"}
    configure_logging(level=settings.log_level, use_json=use_json)
    get_logger(__name__).info(
        "Application initialized",
        log_level=settings.log_level,
        log_json=use_json,
    )

    init_engine(settings.database_url)
    init_db()

    app = Flask(__name__)
    app.config["SETTINGS"] = settings
    app.config["TEMPLATES_DIR"] = str(Path(__file__).resolve().parent.parent / "templates")

    app.register_blueprint(health_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(public_search_bp)
    app.register_blueprint(fb_webhook_bp)

    scheduler = start_scheduler(app)
    if scheduler is not None:

        def _shutdown() -> None:
            scheduler.shutdown(wait=False)

        atexit.register(_shutdown)

    return app


def main() -> None:
    port = int(os.environ.get("PORT", "5000"))
    flask_app = create_app()
    flask_app.run(
        host="0.0.0.0",
        port=port,
        debug=os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"},
    )


if __name__ == "__main__":
    main()
