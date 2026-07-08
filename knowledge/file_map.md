# KT-Assist — File Map

## Root
- [app.py](file:///app.py): FastAPI app factory; mounts all 10 routers.
- [streamlit_app.py](file:///streamlit_app.py): Streamlit entry point; nav + screen dispatch.
- [database.py](file:///database.py): SQLAlchemy engine/session factory; SQLite WAL setup.
- [cli.py](file:///cli.py): CLI utilities for running/administering the platform.
- [requirements.txt](file:///requirements.txt): Pinned dependencies, grouped by layer.

## config/ (single source of truth for constants — no magic numbers elsewhere)
- [__init__.py](file:///config/__init__.py): Re-exports all config submodules as flat `config` namespace.
- [settings.py](file:///config/settings.py): Runtime settings (env, dev-mode/mock flag, paths).
- [scoring.py](file:///config/scoring.py): Frozen weights, thresholds, gates for KVA/KASE/OIS/readiness.
- [domain.py](file:///config/domain.py): Domain enums/constants (lifecycle states, package types, object types).
- [templates.py](file:///config/templates.py): KTTL template profiles — required/optional object sets per package type.
- [ui.py](file:///config/ui.py): Frozen color palette + UI constants.

## models/ (SQLAlchemy ORM)
- [mixins.py](file:///models/mixins.py): Shared columns (ids, timestamps).
- [program.py](file:///models/program.py): Program + lifecycle_state.
- [asset.py](file:///models/asset.py): Uploaded KT assets/chunks.
- [participant.py](file:///models/participant.py): Participants and roles (giver/receiver).
- [coverage.py](file:///models/coverage.py): CoverageResult incl. domain_breakdown_json.
- [assessment.py](file:///models/assessment.py): Scenarios, responses, evidence.
- [scoring.py](file:///models/scoring.py): KASE/competency/pillar score rows.
- [readiness.py](file:///models/readiness.py): Readiness verdicts/gates.
- [workflow.py](file:///models/workflow.py): Workflow/run state.
- [ground_truth_models.py](file:///models/ground_truth_models.py): Phase-13 dataset ground-truth tables.

## schemas/ (Pydantic API contracts)
- One module per resource mirroring routers: [program](file:///schemas/program.py), [upload](file:///schemas/upload.py), [asset](file:///schemas/asset.py), [graph](file:///schemas/graph.py), [knowledge_graph](file:///schemas/knowledge_graph.py), [gap](file:///schemas/gap.py), [assessment](file:///schemas/assessment.py), [participant](file:///schemas/participant.py), [dashboard](file:///schemas/dashboard.py), [explanation](file:///schemas/explanation.py), [assurance_report](file:///schemas/assurance_report.py), [workflow](file:///schemas/workflow.py), [agent_contracts](file:///schemas/agent_contracts.py) (inter-agent I/O shapes), [common](file:///schemas/common.py).

## services/core/
- [claude_client.py](file:///services/core/claude_client.py): Sole Anthropic API wrapper + caching + dev-mode mocks.
- [base_agent.py](file:///services/core/base_agent.py) / [base_service.py](file:///services/core/base_service.py): Agent/service base classes.
- [repository.py](file:///services/core/repository.py): Generic DB repository/session helpers.
- [asset_ingestion.py](file:///services/core/asset_ingestion.py): File parsing → chunking → asset persistence.
- [workflow_engine.py](file:///services/core/workflow_engine.py): Step/state machine for pipeline runs.
- [complexity_signal.py](file:///services/core/complexity_signal.py): Complexity heuristics feeding scoring/weighting.
- [resilience.py](file:///services/core/resilience.py): Retry/backoff wrappers for LLM calls.

## services/agents/
- [kai_extraction.py](file:///services/agents/kai_extraction.py): Per-chunk KAI knowledge-object extraction (Claude).
- [kai_relationship_discovery.py](file:///services/agents/kai_relationship_discovery.py): Cross-object relationship discovery.
- [kai_pipeline.py](file:///services/agents/kai_pipeline.py): Orchestrates ingest→extract→relate→graph write.
- [kttl.py](file:///services/agents/kttl.py): Package-type detection + template profile selection.
- [kva.py](file:///services/agents/kva.py): Coverage validation agent (run_kva) — Python scoring.
- [kra.py](file:///services/agents/kra.py): Readiness/scenario assessment agent orchestration.
- [kase.py](file:///services/agents/kase.py) / [kase_scoring.py](file:///services/agents/kase_scoring.py): Competency→pillar→OIS scoring engine (pure Python).

## services/coverage/
- [coverage_engine.py](file:///services/coverage/coverage_engine.py): Coverage % + domain breakdown computation.
- [coverage_persistence.py](file:///services/coverage/coverage_persistence.py): Leaf-level persist of CoverageResult (circular-import breaker).
- [gap_detection.py](file:///services/coverage/gap_detection.py): Derives gaps from coverage vs template.
- [gap_governance.py](file:///services/coverage/gap_governance.py): Gap lifecycle incl. close_gap → KVA re-run + persist + graph version bump.

## services/assessment/
- [scenario_generation.py](file:///services/assessment/scenario_generation.py): Claude-generated scenarios per competency.
- [scenario_weighting.py](file:///services/assessment/scenario_weighting.py) / [scenario_validation.py](file:///services/assessment/scenario_validation.py): Python weighting + structural validation of scenarios.
- [scenario_cache.py](file:///services/assessment/scenario_cache.py): Scenario package cache (cost control).
- [response_interpretation.py](file:///services/assessment/response_interpretation.py) / [evidence_detection.py](file:///services/assessment/evidence_detection.py): Receiver-response parsing + Claude evidence detection.

## services/graph/
- [knowledge_model.py](file:///services/graph/knowledge_model.py): Knowledge-object/edge domain model.
- [graph_engine.py](file:///services/graph/graph_engine.py): networkx graph construction/queries.
- [graph_storage.py](file:///services/graph/graph_storage.py): Versioned graph persistence (graph_version_id).
- [graph_update.py](file:///services/graph/graph_update.py): Applies gap-closure deltas → new graph version.
- [graph_viewer.py](file:///services/graph/graph_viewer.py): pyvis HTML rendering for Screen 4.

## services/readiness/
- [threshold_model.py](file:///services/readiness/threshold_model.py) / [role_threshold.py](file:///services/readiness/role_threshold.py): Gate thresholds per competency/role.
- [completion_status.py](file:///services/readiness/completion_status.py): Aggregate completion/readiness verdicts.

## services/explanation/ (EML)
- [explanation_framework.py](file:///services/explanation/explanation_framework.py): EML layer contracts.
- [explanation_data_layer.py](file:///services/explanation/explanation_data_layer.py) → [explanation_template_layer.py](file:///services/explanation/explanation_template_layer.py) → [explanation_narrative_layer.py](file:///services/explanation/explanation_narrative_layer.py): 3-layer pipeline (facts → templated text → Claude narrative).
- [explanation_engine.py](file:///services/explanation/explanation_engine.py): Orchestrates the 3 layers.
- [explanation_prompts.py](file:///services/explanation/explanation_prompts.py): Narrative prompts.
- [recommendation_service.py](file:///services/explanation/recommendation_service.py): Fires only on individual critical-competency gate failure.
- [traceability_service.py](file:///services/explanation/traceability_service.py): Score→evidence trace chains (Screen 9).

## services/reporting/ & exporters/
- [assurance_report_service.py](file:///services/reporting/assurance_report_service.py): Final KT Assurance Report assembly.
- [executive_dashboard_service.py](file:///services/reporting/executive_dashboard_service.py) / [coverage_dashboard_service.py](file:///services/reporting/coverage_dashboard_service.py) / [readiness_dashboard_service.py](file:///services/reporting/readiness_dashboard_service.py): Read-model aggregation per dashboard.
- [pdf_exporter.py](file:///services/exporters/pdf_exporter.py) / [pptx_exporter.py](file:///services/exporters/pptx_exporter.py): reportlab/python-pptx export.

## services/orchestration/ & demo/ & datasets/ & checks/
- [workflow_runner.py](file:///services/orchestration/workflow_runner.py): End-to-end pipeline runner over HTTP-equivalent service calls.
- [demo_runner.py](file:///services/orchestration/demo_runner.py): Scripted E2E demo (frozen golden values 63%→89%, OIS 84, READY/Silver); [services/demo/demo_runner.py](file:///services/demo/demo_runner.py) legacy shim.
- [dataset_loader.py](file:///services/datasets/dataset_loader.py) / [dataset_validator.py](file:///services/datasets/dataset_validator.py): Phase-13 ground-truth dataset load + tuning-loop validation harness.
- [definition_of_done.py](file:///services/checks/definition_of_done.py): Programmatic DoD probes per session.

## services/routers/ (FastAPI)
- [programs.py](file:///services/routers/programs.py), [packages.py](file:///services/routers/packages.py) (incl. generate-assessment / scenarios / responses / score-readiness), [assets.py](file:///services/routers/assets.py) (upload → ingest+validate+persist), [graph.py](file:///services/routers/graph.py), [gaps.py](file:///services/routers/gaps.py), [assessment.py](file:///services/routers/assessment.py), [participants.py](file:///services/routers/participants.py), [dashboard.py](file:///services/routers/dashboard.py), [explanation.py](file:///services/routers/explanation.py), [assurance_report.py](file:///services/routers/assurance_report.py): one router per resource, thin over services.

## frontend/
- [api_client.py](file:///frontend/api_client.py): Only sanctioned backend access (HTTP).
- [theme.py](file:///frontend/theme.py): Frozen palette + CSS (logo sizing via sidebar-collapse hook).
- [screens/screen1_executive_dashboard.py](file:///frontend/screens/screen1_executive_dashboard.py) … [screen10_kt_assurance_report.py](file:///frontend/screens/screen10_kt_assurance_report.py): Screens 1–10 = Executive Dashboard, Program Dashboard, Package Workspace, Graph Explorer, Validation Center, Gap Resolution, Participant Mgmt (2 tabs: Participants & Roles / Receiver Assessment per-scenario), Readiness Scorecard, Explanation & Traceability, Assurance Report.

## utils/, data/, scripts/
- [utils/errors.py](file:///utils/errors.py) / [utils/logging_config.py](file:///utils/logging_config.py): Error taxonomy + logging setup.
- [data/seed_data.py](file:///data/seed_data.py) / [scripts/seed_data.py](file:///scripts/seed_data.py) / [scripts/reset_demo.py](file:///scripts/reset_demo.py): Seed + demo reset utilities.

## tests/ (~515 tests)
- [conftest.py](file:///tests/conftest.py): Fixtures (DB, client, mocks).
- [invariants/test_architectural_boundaries.py](file:///tests/invariants/test_architectural_boundaries.py): Phase-12 unified guard — Python-only scoring, import boundaries.
- [test_frontend_boundary.py](file:///tests/test_frontend_boundary.py): Frontend HTTP-only import guard.
- [level1/](file:///tests/level1/test_framework_validation.py) / [level2/](file:///tests/level2/test_agent_validation.py) / [level3/](file:///tests/level3/test_full_workflow.py): Framework → agent → full-workflow tiers.
- [cost/test_cost_controls.py](file:///tests/cost/test_cost_controls.py): Verifies the 4 cost controls.
- [datasets/](file:///tests/datasets/test_dataset_ground_truth.py): Phase-13 ground-truth + golden-response assertions.
- `test_sessionN_*.py` (S1–S32): One suite per build session — data layer(1), services(2), workflow(4), programs/packages/roles(5), completion(6), knowledge model(7), graph storage(8), graph viewer(9), ingestion(10), KAI extraction(11), relationships(12), KAI pipeline(13), KTTL(14), coverage(15), gap detection(16), KVA(17), response interpretation(18), graph update(19), gap governance(20), scenario gen(21), weighting(22), validation(23), KRA(24), evidence(25), KASE scoring(26), thresholds(27), KASE integration(28), explanation(29), recommendations(30), assurance report(32).
- Router/API suites: [test_assets_router.py](file:///tests/test_assets_router.py), [test_gaps_router.py](file:///tests/test_gaps_router.py), [test_graph_router.py](file:///tests/test_graph_router.py), [test_api_client.py](file:///tests/test_api_client.py), [test_dashboards.py](file:///tests/test_dashboards.py), [test_demo_runner.py](file:///tests/test_demo_runner.py), [test_resilience.py](file:///tests/test_resilience.py), [test_definition_of_done.py](file:///tests/test_definition_of_done.py), [test_dod_probe.py](file:///tests/test_dod_probe.py), [test_reset_demo.py](file:///tests/test_reset_demo.py).
- Cleanup candidates (do not extend): `tests/zz_debug_test*.py`, `tests/test_demo_runner_copy.py`, `models/__init__placeholder__.py`, empty `agents/`, `storage/` stubs.
- [test_competency_coverage_correction.py](file:///tests/test_competency_coverage_correction.py): regression tests for the additive `OBJECT_TYPE_COMPETENCY_MAP_ADDITIONAL` correction (issue_log #14).
- [test_hierarchical_demo_replay_proof.py](file:///tests/test_hierarchical_demo_replay_proof.py): offline, deterministic replay-proof lifecycle tests (gap-signature stability, real closure, KAR, scenario-level fixture resolution order, 3 real KASE/KRA outcomes all matching golden, no-Anthropic-call, deterministic rerun) — issue_log #13-#16.
- [services/demo/](file:///services/demo/) (demo-mode-hierarchical-wip branch only): `hierarchical_fixtures.py` (pinned demo ids/names), `hierarchical_kai_attributes.py` (pilot attribute overlay), `hierarchical_gap_answers.py` (evidence-confirmation + relationship-closure fixture answers), `receiver_strategies.py` (3 golden receiver strategies + `TUNING_OVERRIDES` (competency-level) + `SCENARIO_LEVEL_OVERRIDES`/`build_receiver_scenario_responses()` (scenario-instance-level, issue_log #16) + `UnknownScenarioOverrideKeyError`), `seed_demo_hierarchical_kai_cache.py`, `run_hierarchical_demo_replay_proof.py` (thin CLI wrapper around the orchestrator, issue_log #17), `hierarchical_demo_orchestrator.py` (new, issue_log #17 — `HierarchicalDemoOrchestrator`: `get_demo_state/reset_demo/ingest_demo/validate_demo/advance_enrichment/complete_assurance/assess_receiver/get_demo_summary`).
- [models/demo_journey.py](file:///models/demo_journey.py) (new, issue_log #17): `DemoJourneyState` — orchestration-progress-only checkpoint, one row per demo package_id.
- [services/routers/demo_hierarchical.py](file:///services/routers/demo_hierarchical.py) (new, issue_log #17): `/api/demo/hierarchical/*` — additive, demo-scoped API surface over `HierarchicalDemoOrchestrator`. Distinct from `services/routers/hierarchical.py` (generic v2-profile read endpoints for any opted-in package) — this one is specifically the pinned demo journey.
- [scripts/reset_hierarchical_demo.py](file:///scripts/reset_hierarchical_demo.py) (new, issue_log #17): idempotent reset CLI for the hierarchical demo only — distinct from `scripts/reset_demo.py` (legacy v1 `cli.py demo` runbook cleanup).
- [frontend/guided_demo/](file:///frontend/guided_demo/) (new, issue_log #18): `portfolio_fixture.py` (static synthetic portfolio + PBI-case live-state overlay), `executive_dashboard.py` (Executive Command Center screen), `guided_shell.py` (Guided Demo Case Shell screen — real PBI journey progress + resume CTA; lightweight static detail view for synthetic cases). Lives under `frontend/`, not `services/demo/`, because `tests/test_frontend_boundary.py` forbids `frontend/` from importing `services/` — this is pure presentation data, deliberately placed on the frontend side of that boundary.
- [frontend/api_client.py](file:///frontend/api_client.py): +8 wrapper methods for `/api/demo/hierarchical/*` (issue_log #18) — `get_demo_state`, `get_demo_summary`, `reset_demo_hierarchical`, `ingest_demo_hierarchical`, `validate_demo_hierarchical`, `advance_demo_enrichment`, `complete_demo_assurance`, `assess_demo_receiver`.
- [streamlit_app.py](file:///streamlit_app.py): +2 pages (Executive Command Center — now the default landing page — and Guided Demo Case Shell), + `st.session_state["_nav_pages"]` registry for cross-page `st.switch_page()` (issue_log #18). The original 10 screens/4 nav groups are unmodified.
- [frontend/guided_demo/lifecycle_scenes.py](file:///frontend/guided_demo/lifecycle_scenes.py) (new, issue_log #19): 5 detailed scene renderers (Knowledge Intake/Discovery/Assurance/Gap Closure/Assurance Result), integrated into `guided_shell.py` via `st.tabs()`. Read-mostly over real backend outputs; mutating actions are explicit button presses only.
- [frontend/guided_demo/presentation_labels.py](file:///frontend/guided_demo/presentation_labels.py) (new, issue_log #19): `rule_family`/attribute-state → human-readable label mapping, presentation-only, never touches backend taxonomy values.
- [models/demo_journey.py](file:///models/demo_journey.py): `DemoJourneyState.closure_round_history_json` (new column, issue_log #19) — real per-round question/SME-response/resolved-finding-count history; migrated via `scripts/migrate_demo_journey_round_history.py`.
- [services/demo/hierarchical_demo_orchestrator.py](file:///services/demo/hierarchical_demo_orchestrator.py): +5 methods (issue_log #19) — `get_discovery_summary`, `get_knowledge_gaps_detail`, `get_pre_enrichment_kar`, `get_assurance_snapshot`, `get_closure_history`, `get_traceability_example`; `advance_enrichment()` now also captures round history (SME response text via a thin interpretation-function wrapper, no core closure-loop changes).
- [services/routers/demo_hierarchical.py](file:///services/routers/demo_hierarchical.py): +5 read-only endpoints (issue_log #19) — `/discovery-summary`, `/knowledge-gaps`, `/assurance-snapshot`, `/closure-history`, `/traceability-example`; +1 more (issue_log #20) — `/receivers/{participant_id}/assessment-detail`.
- [frontend/guided_demo/receiver_scenes.py](file:///frontend/guided_demo/receiver_scenes.py) (new, issue_log #20): Receiver Assessment Setup, Assessment Experience, Competency Evidence Profile, Readiness Decision, Executive Recommendation, Cross-Receiver Comparison — all read via `get_demo_receiver_assessment_detail()`. Imports `config` directly (COMPETENCY_CATALOG) — allowed, same precedent as `theme.py`'s `config.COLORS`.
- [services/demo/hierarchical_demo_orchestrator.py](file:///services/demo/hierarchical_demo_orchestrator.py): +1 method (issue_log #20) — `get_receiver_assessment_detail`; `_rollup_from_existing_readiness` bug-fixed to recompute the real `ThresholdResolution` via `resolve_readiness()` instead of a placeholder `effective_threshold=0`.
- [services/graph/graph_storage.py](file:///services/graph/graph_storage.py) (issue_log #21): `storage_path` now persisted as a portable repo-relative path; new `_resolve_graph_path()` (centralized, used by both save/load) + `GraphArtifactNotFoundError`. All graph consumers (explanation engine, graph router, demo router, workflow_runner) inherit the fix automatically — none were touched individually.
- [scripts/migrate_graph_storage_paths.py](file:///scripts/migrate_graph_storage_paths.py) (new, issue_log #21): idempotent repair utility for legacy absolute `KnowledgeGraphVersion.storage_path` values (`--dry-run` supported); never mutates a row it can't verify.
