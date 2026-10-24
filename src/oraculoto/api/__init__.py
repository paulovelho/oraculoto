"""HTTP API under /api/v1 (docs/api.md). `create_app()` builds it; `oraculoto.api.cgi` serves it as CGI.

Local development: `uv run uvicorn oraculoto.api.app:create_app --factory --reload`
"""
