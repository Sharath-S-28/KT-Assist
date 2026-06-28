"""
frontend/api_client.py — The ONLY module any Streamlit screen may use to
reach the KT Assist backend (Phase 11 / Session 33's locked
architectural rule).

Every method here is a thin httpx call against a real router path that
exists today (verified against services/routers/*.py, Phases 2-11 --
not the spec's placeholder int-based signatures, which are corrected to
the real str/UUID ids the same way schemas/dashboard.py and
schemas/explanation.py already reconciled the spec against the live
schema). Response bodies are parsed into the backend's own Pydantic
response schemas (schemas/program.py, schemas/participant.py,
schemas/workflow.py, schemas/graph.py, schemas/dashboard.py,
schemas/explanation.py, schemas/assurance_report.py) -- this module is
the one explicitly-allowed place outside the backend itself that may
import schemas/, per the frontend boundary guard
(tests/test_frontend_boundary.py). It must never import services/,
agents/, models (the ORM package), storage/, or database.

Run model: two independent processes -- `uvicorn app:app` (default
http://127.0.0.1:8000) and `streamlit run streamlit_app.py` -- talking
over plain HTTP on localhost. KT_ASSIST_API_BASE_URL overrides the
backend's base URL (e.g. for a non-default port); tests instead inject
an already-built httpx.Client (fastapi.testclient.TestClient is one) so
the exact same request/response code path is exercised without a
socket.

TraceNode is intentionally NOT imported from
services.traceability_service -- that module lives under services/,
which this file may never import from even though TraceNode happens to
be a Pydantic BaseModel. It is redefined here as a plain structural
mirror of the same four fields (level/id/label/value) plus children,
which is all the explanation router's /trace endpoints ever serialize.
"""

import os
from typing import Optional

import httpx
from pydantic import BaseModel, Field

from schemas.assurance_report import AssuranceReport
from schemas.dashboard import CoverageDashboard, ExecutiveDashboard, ReadinessDashboard
from schemas.explanation import ExplanationResponse, RecommendationItem
from schemas.graph import GraphPayload, NodeDetail
from schemas.participant import ParticipantRead, ReceiverRoleAssignmentRead
from schemas.program import KnowledgePackageRead, KTProgramRead
from schemas.workflow import CompletionStatusReportRead, WorkflowTransitionLogRead

DEFAULT_BASE_URL = os.environ.get("KT_ASSIST_API_BASE_URL", "http://127.0.0.1:8000")


class TraceNode(BaseModel):
    """Frontend-local mirror of services.traceability_service.TraceNode
    -- see module docstring for why this isn't imported directly."""

    level: str
    id: str
    label: str
    value: Optional[float] = None
    children: list["TraceNode"] = Field(default_factory=list)


TraceNode.model_rebuild()


class ApiError(RuntimeError):
    """Raised when the backend returns a non-2xx response. Carries the
    structured error_code/message/details shape every router error uses
    (utils.errors.kt_assist_exception_handler) so a screen can show a
    real message instead of a raw traceback."""

    def __init__(self, status_code: int, error_code: str, message: str, details: Optional[dict] = None):
        super().__init__(f"[{status_code} {error_code}] {message}")
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details or {}


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        body = response.json()
        error_code = body.get("error_code", "unknown_error")
        message = body.get("message", response.text)
        details = body.get("details", {})
    except Exception:
        error_code = "unknown_error"
        message = response.text
        details = {}
    raise ApiError(response.status_code, error_code, message, details)


class ApiClient:
    """Synchronous httpx-backed client. One instance is shared per
    Streamlit session (see get_client() below); each method opens no
    state beyond the underlying connection pool."""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        transport: Optional[httpx.BaseTransport] = None,
        timeout: float = 30.0,
        http_client: Optional[httpx.Client] = None,
    ):
        # http_client lets tests hand in an already-built httpx.Client
        # subclass (fastapi.testclient.TestClient is one) that bridges
        # sync calls onto the real ASGI `app` object via an anyio portal
        # -- httpx's own ASGITransport only implements the async path, so
        # plain `transport=ASGITransport(app=app)` does not work with a
        # synchronous httpx.Client. Production code never sets this; it
        # always builds a real httpx.Client against base_url/transport.
        self._client = http_client if http_client is not None else httpx.Client(
            base_url=base_url, transport=transport, timeout=timeout
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    # -- internal helpers ---------------------------------------------------

    def _get(self, path: str, params: Optional[dict] = None) -> httpx.Response:
        response = self._client.get(path, params=params)
        _raise_for_status(response)
        return response

    def _post(self, path: str, json: Optional[dict] = None) -> httpx.Response:
        response = self._client.post(path, json=json)
        _raise_for_status(response)
        return response

    # -- programs (services/routers/programs.py) ---------------------------

    def list_programs(self, limit: int = 100, offset: int = 0) -> list[KTProgramRead]:
        body = self._get("/api/programs", params={"limit": limit, "offset": offset}).json()
        return [KTProgramRead.model_validate(row) for row in body]

    def get_program(self, program_id: str) -> KTProgramRead:
        return KTProgramRead.model_validate(self._get(f"/api/programs/{program_id}").json())

    def create_program(self, name: str, description: Optional[str] = None) -> KTProgramRead:
        payload = {"name": name, "description": description}
        return KTProgramRead.model_validate(self._post("/api/programs", json=payload).json())

    def get_allowed_transitions(self, program_id: str) -> list[str]:
        return self._get(f"/api/programs/{program_id}/allowed-transitions").json()

    def transition_program(
        self, program_id: str, to_state: str, triggered_by: Optional[str] = None, reason: Optional[str] = None
    ) -> KTProgramRead:
        payload = {"to_state": to_state, "triggered_by": triggered_by, "reason": reason}
        return KTProgramRead.model_validate(
            self._post(f"/api/programs/{program_id}/transition", json=payload).json()
        )

    def get_transition_log(self, program_id: str) -> list[WorkflowTransitionLogRead]:
        body = self._get(f"/api/programs/{program_id}/transition-log").json()
        return [WorkflowTransitionLogRead.model_validate(row) for row in body]

    def get_completion_status(self, program_id: str) -> CompletionStatusReportRead:
        return CompletionStatusReportRead.model_validate(
            self._get(f"/api/programs/{program_id}/completion-status").json()
        )

    # -- packages (services/routers/packages.py) ----------------------------

    def list_packages(
        self, program_id: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> list[KnowledgePackageRead]:
        params = {"limit": limit, "offset": offset}
        if program_id is not None:
            params["program_id"] = program_id
        body = self._get("/api/packages", params=params).json()
        return [KnowledgePackageRead.model_validate(row) for row in body]

    def get_package(self, package_id: str) -> KnowledgePackageRead:
        return KnowledgePackageRead.model_validate(self._get(f"/api/packages/{package_id}").json())

    def create_package(
        self, program_id: str, name: str, description: Optional[str] = None
    ) -> KnowledgePackageRead:
        payload = {"program_id": program_id, "name": name, "description": description}
        return KnowledgePackageRead.model_validate(self._post("/api/packages", json=payload).json())

    # -- participants (services/routers/participants.py) --------------------

    def list_participants(
        self, program_id: Optional[str] = None, limit: int = 100, offset: int = 0
    ) -> list[ParticipantRead]:
        params = {"limit": limit, "offset": offset}
        if program_id is not None:
            params["program_id"] = program_id
        body = self._get("/api/participants", params=params).json()
        return [ParticipantRead.model_validate(row) for row in body]

    def get_participant(self, participant_id: str) -> ParticipantRead:
        return ParticipantRead.model_validate(self._get(f"/api/participants/{participant_id}").json())

    def create_participant(
        self, program_id: str, name: str, participant_type: str, email: Optional[str] = None
    ) -> ParticipantRead:
        payload = {"program_id": program_id, "name": name, "participant_type": participant_type, "email": email}
        return ParticipantRead.model_validate(self._post("/api/participants", json=payload).json())

    def assign_receiver_role(
        self, participant_id: str, package_id: str, role_tier: str
    ) -> ReceiverRoleAssignmentRead:
        payload = {"participant_id": participant_id, "package_id": package_id, "role_tier": role_tier}
        return ReceiverRoleAssignmentRead.model_validate(
            self._post("/api/participants/role-assignments", json=payload).json()
        )

    # -- graph (services/routers/graph.py, Phase 11 / Session 33) ----------

    def get_graph(self, package_id: str, version: Optional[int] = None) -> GraphPayload:
        params = {"version": version} if version is not None else None
        return GraphPayload.model_validate(self._get(f"/api/packages/{package_id}/graph", params=params).json())

    def get_graph_html(self, package_id: str, version: Optional[int] = None) -> str:
        params = {"version": version} if version is not None else None
        return self._get(f"/api/packages/{package_id}/graph/html", params=params).text

    def get_graph_node(self, package_id: str, node_id: str, version: Optional[int] = None) -> NodeDetail:
        params = {"version": version} if version is not None else None
        return NodeDetail.model_validate(
            self._get(f"/api/packages/{package_id}/graph/nodes/{node_id}", params=params).json()
        )

    def get_graph_versions(self, package_id: str) -> list[dict]:
        return self._get(f"/api/packages/{package_id}/graph/versions").json()

    # -- dashboards (services/routers/dashboard.py) --------------------------

    def get_executive_dashboard(self) -> ExecutiveDashboard:
        return ExecutiveDashboard.model_validate(self._get("/api/dashboards/executive").json())

    def get_readiness_dashboard(self, participant_id: str) -> ReadinessDashboard:
        return ReadinessDashboard.model_validate(
            self._get(f"/api/receivers/{participant_id}/dashboard/readiness").json()
        )

    def get_coverage_dashboard(self, package_id: str) -> CoverageDashboard:
        return CoverageDashboard.model_validate(
            self._get(f"/api/packages/{package_id}/dashboard/coverage").json()
        )

    # -- explanations (services/routers/explanation.py) ----------------------

    def get_explanation(self, receiver_readiness_id: str) -> ExplanationResponse:
        return ExplanationResponse.model_validate(
            self._get(f"/api/explanations/{receiver_readiness_id}").json()
        )

    def get_trace(self, receiver_readiness_id: str) -> TraceNode:
        return TraceNode.model_validate(self._get(f"/api/explanations/{receiver_readiness_id}/trace").json())

    def get_trace_subtree(self, receiver_readiness_id: str, level: str, node_id: str) -> TraceNode:
        return TraceNode.model_validate(
            self._get(f"/api/explanations/{receiver_readiness_id}/trace/{level}/{node_id}").json()
        )

    def get_recommendations(self, receiver_readiness_id: str) -> list[RecommendationItem]:
        body = self._get(f"/api/explanations/{receiver_readiness_id}/recommendations").json()
        return [RecommendationItem.model_validate(row) for row in body]

    # -- assurance report (services/routers/assurance_report.py) ------------

    def get_assurance_report(self, program_id: str) -> AssuranceReport:
        return AssuranceReport.model_validate(
            self._get(f"/api/programs/{program_id}/assurance-report").json()
        )

    def export_assurance_report_pdf(self, program_id: str) -> bytes:
        return self._get(f"/api/programs/{program_id}/assurance-report/export/pdf").content

    def export_assurance_report_pptx(self, program_id: str) -> bytes:
        return self._get(f"/api/programs/{program_id}/assurance-report/export/pptx").content


_default_client: Optional[ApiClient] = None


def get_client() -> ApiClient:
    """The shared client every screen should use. A fresh ApiClient()
    against KT_ASSIST_API_BASE_URL (or its localhost:8000 default) --
    tests build their own ApiClient(http_client=...) instead of calling
    this factory."""
    global _default_client
    if _default_client is None:
        _default_client = ApiClient()
    return _default_client
