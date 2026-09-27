"""ASGI entry point: `uvicorn marginal_api.main:app`."""

from marginal_api.app import create_app

app = create_app()
