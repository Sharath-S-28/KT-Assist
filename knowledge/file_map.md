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
- [ontology.py](file:///config/ontology.py): Hierarchical-assurance ontology registry (9 knowledge-object types; System fully authored).
- [kttl_v2_profiles.py](file:///config/kttl_v2_profiles.py): `KTTLProfileV2` (incl. `PILOT_PROFILE`) — v2 templates w/ relationship/sufficiency/evidence requirements + weights; v1-compat loader.
- [prioritization.py](file:///config/prioritization.py): Gap-ranking factor weights (criticality/readiness_blocking/aging active; 4 more named at zero weight).
- [risk_rules.py](file:///config/risk_rules.py): `RiskMappingRule`s (6, one per pilot rule_family) driving deterministic TransitionRisk derivation.

## models/ (SQLAlchemy ORM)
- [mixins.py](file:///models/mixins.py): Shared columns (ids, timestamps).
- [program.py](file:///models/program.py): Program + lifecycle_state.
- [KnowledgePackage] gained nullable `kttl_profile_id` (NULL = legacy v1 path, the only opt-in gate anywhere for hierarchical assurance).
- [asset.py](file:///models/asset.py): Uploaded KT assets/chunks.
- [participant.py](file:///models/participant.py): Participants and roles (giver/receiver).
- [coverage.py](file:///models/coverage.py): CoverageResult incl. domain_breakdown_json; +9 nullable hierarchical columns (kcs/tc/ac/rc/kqs/os/ev scores + 2 quality-gate booleans).
- [assessment.py](file:///models/assessment.py): Scenarios, responses, evidence.
- [scoring.py](file:///models/scoring.py): KASE/competency/pillar score rows.
- [readiness.py](file:///models/readiness.py): Readiness verdicts/gates.
- [workflow.py](file:///models/workflow.py): Workflow/run state.
- [ground_truth_models.py](file:///models/ground_truth_models.py): Phase-13 dataset ground-truth tables.

## schemas/ (Pydantic API contracts)
- One module per resource mirroring routers: [program](file:///schemas/program.py), [upload](file:///schemas/upload.py), [asset](file:///schemas/asset.py), [graph](file:///schemas/graph.py), [knowledge_graph](file:///schemas/knowledge_graph.py), [gap](file:///schemas/gap.py), [assessment](file:///schemas/assessment.py), [participant](file:///schemas/participant.py), [dashboard](file:///schemas/dashboard.py), [explanation](file:///schemas/explanation.py), [assurance_report](file:///schemas/assurance_report.py), [workflow](file:///schemas/workflow.py), [agent_contracts](file:///schemas/agent_contracts.py) (inter-agent I/O shapes), [common](file:///schemas/common.py).
- Hierarchical-assurance schemas (Wave 1-7): [knowledge_element_state.py](file:///schemas/knowledge_element_state.py) (`KnowledgeElementState` 5-state model + `AttributeValue`/`RelationshipAssertion`/`EvidenceRequirement`), [hierarchical.py](file:///schemas/hierarchical.py) (`Finding`/`KnowledgeGap`/`GapBundle`/`TransitionRisk`), [gap_model.py](file:///schemas/gap_model.py) (Finding↔GapCandidate compat adapter), [kttl_profile.py](file:///schemas/kttl_profile.py), [validation_plan.py](file:///schemas/validation_plan.py), [knowledge_assurance.py](file:///schemas/knowledge_assurance.py) (KAR — `KnowledgeAssuranceResult`), [knowledge_graph.py](file:///schemas/knowledge_graph.py) additively extended (`schema_version`, `attributes`, `validation_status`, `evidence_refs`, `state`, `provenance`).

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

## services/agents/ — hierarchical-assurance addition
- [attribute_arbitration.py](file:///services/agents/attribute_arbitration.py): Python-owned final-state assignment for structured attributes across chunks (merge/CONFLICTING/deterministic-N/A/NOT_OBSERVED). Wired into `kai_pipeline.run_kai_pipeline()` via opt-in `pilot_profile` param (`None` = legacy, byte-identical).

## services/coverage/ — hierarchical-assurance addition (Phase 4 Waves 1-7, `KnowledgeElementState`/Finding-based, parallel to v1 gap_detection)
- [validation_plan_builder.py](file:///services/coverage/validation_plan_builder.py): Builds `ValidationPlan` from `KTTLProfileV2`.
- [condition_evaluator.py](file:///services/coverage/condition_evaluator.py): Shared conditional-requirement syntax evaluator (unsupported syntax fails loudly).
- [sufficiency_rules.py](file:///services/coverage/sufficiency_rules.py): Pilot sufficiency rules (Sufficiency/Quality gates).
- [finding_detectors.py](file:///services/coverage/finding_detectors.py): 5-level Finding detection (Level 1 reuses v1 `_validate_type_status`).
- [dimensional_scoring.py](file:///services/coverage/dimensional_scoring.py): TC/AC/RC/OS/EV dimensional scores, KCS/KQS (N/A-renormalized), gate evaluation. Fully independent of `coverage_engine.py`/`kva.py`.
- [consolidation.py](file:///services/coverage/consolidation.py): Finding → `KnowledgeGap` (by object_id, rule_family) → `GapBundle`.
- [prioritization.py](file:///services/coverage/prioritization.py): Ranks gaps per `config/prioritization.py` weights.
- [enrichment_coordinator.py](file:///services/coverage/enrichment_coordinator.py): Thin coordinator (question gen → interpretation → graph update → revalidation), sequences existing modules only.
- [hierarchical_closure.py](file:///services/coverage/hierarchical_closure.py): `run_hierarchical_closure_loop()` — hierarchical equivalent of `close_gaps_until_sufficient`; 6 termination reasons.
- [transition_risk.py](file:///services/coverage/transition_risk.py): `evaluate_risk_rules()` — deterministic TransitionRisk via `config/risk_rules.py`, never calls scoring functions.
- [knowledge_assurance_builder.py](file:///services/coverage/knowledge_assurance_builder.py) / [knowledge_assurance_persistence.py](file:///services/coverage/knowledge_assurance_persistence.py): Builds/persists KAR (pure composition; separate writer from v1's `persist_coverage_result`, same table).

## services/readiness/ — hierarchical-assurance addition
- [kar_adapter.py](file:///services/readiness/kar_adapter.py): `adapt_kar_to_gates()` — feeds KAR into unmodified `resolve_readiness()` via `gap_governance.determine_completion_status`.

## services/routers/ — hierarchical-assurance addition
- [hierarchical.py](file:///services/routers/hierarchical.py): 4 read-only endpoints (`/kar`, `/knowledge-gaps`, `/transition-risks`, `/closure-status`), 404 for non-opted-in packages. Mounted in `app.py` alongside v1 routers.

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
- [workflow_runner.py](file:///services/orchestration/workflow_runner.py): End-to-end pipeline runner over HTTP-equivalent service calls. +3 additive hierarchical methods (`ingest_hierarchical`, `validate_hierarchical`, `run_hierarchical_closure`) + `resolve_v2_profile_for_package`/`HIERARCHICAL_PROFILE_REGISTRY`; zero v1 methods touched.
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
