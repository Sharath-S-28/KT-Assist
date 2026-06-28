"""
frontend — Phase 11 Streamlit presentation layer over the Phase 1-10
FastAPI backend.

Layout (reconciled against the Phase 11 spec's literal proposal, the
same discipline Phases 9/10 applied to their own specs):
  - frontend/api_client.py  the ONLY module that talks to the backend
    (HTTP via httpx), and the only place outside schemas/ this package
    may import a backend Pydantic schema from.
  - frontend/theme.py       the [FROZEN] colour palette + small Streamlit
    styling helpers, sourced from config.COLORS rather than re-typed.
  - frontend/components/    small reusable rendering helpers (cards,
    badges) built only from data already returned by api_client.
  - frontend/screens/       one module per Screen 1-10, each exposing a
    single `render(client) -> None` function.

The spec's literal `pages/` proposal is reconciled to `frontend/screens/`
rather than the repo's existing (placeholder, empty) top-level `pages/`
package: Streamlit auto-discovers a sibling `pages/` directory as a
flat, alphabetically-ordered multipage sidebar, which would fight the
locked 8-concept nav grouping (Screen 6, for example, must sit under
"Knowledge Packages", not get its own top-level nav slot). Session 33
instead drives navigation explicitly via st.navigation()/st.Page() in
streamlit_app.py, with frontend/screens/ supplying the page callables.

Architectural boundary (mechanically enforced by
tests/test_frontend_boundary.py): no module under frontend/ or
streamlit_app.py may import services, agents, models (the ORM package),
storage, or database. Importing schemas/ (response shapes only) is the
one explicit exception -- it is how api_client.py returns typed objects
without duplicating field names a third time. This is the boundary that
makes "a future React rewrite only ever has to re-implement the HTTP
calls in api_client.py" true rather than aspirational.
"""
