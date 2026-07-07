"""
frontend/guided_demo/ — Executive Command Center + Guided Demo Case
Shell (UI Phase 1).

Participates in the same frontend/ boundary guard as every other module
under frontend/ (tests/test_frontend_boundary.py): reaches the backend
only through frontend.api_client, never services/models/database
directly. The synthetic portfolio fixture lives here (not under
services/demo/) precisely because of that boundary -- it is pure
presentation data with no backend meaning, and frontend/ code must be
able to import it directly.
"""
