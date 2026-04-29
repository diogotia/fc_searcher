"""WSGI entrypoint for Gunicorn (avoids --factory, works across Gunicorn versions)."""

from src.main import create_app

app = create_app()
