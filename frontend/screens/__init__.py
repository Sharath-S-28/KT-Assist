"""
frontend/screens — one module per Phase 11 screen, each exposing a single
`render(client: frontend.api_client.ApiClient) -> None` entry point that
streamlit_app.py wires to a st.Page(). Every screen reaches the backend
only through the injected ApiClient -- the same boundary
tests/test_frontend_boundary.py enforces for the rest of frontend/.

Session 33: Screens 1-5.
  - screen1_executive_dashboard
  - screen2_program_dashboard
  - screen3_package_workspace
  - screen4_graph_explorer
  - screen5_validation_center
Session 34: Screens 6-10, completing the ten-screen Phase 11 spec.
  - screen6_gap_resolution_workspace
  - screen7_participant_management      (reconstructed -- see its docstring)
  - screen8_readiness_scorecard
  - screen9_explanation_traceability
  - screen10_kt_assurance_report        (reconstructed -- see its docstring)
"""
