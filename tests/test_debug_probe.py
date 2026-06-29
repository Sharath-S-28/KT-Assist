import sys
sys.path.insert(0, "/sessions/nice-focused-ramanujan/mnt/KT Assist")
import pytest

from services.claude_client import ClaudeClient
from services.demo.demo_runner import DemoRunner

EXTRACTION_MOCK = {
    "objects": [
        {"id": "p1", "object_type": "Process", "name": "Process", "description": "Closes the books monthly.",
         "criticality": "Important", "confidence": 0.9},
        {"id": "t1", "object_type": "Task", "name": "Task", "description": "",
         "criticality": "Important", "confidence": 0.9},
        {"id": "s1", "object_type": "System", "name": "System", "description": "SAP FI is the system of record.",
         "criticality": "Important", "confidence": 0.9},
        {"id": "d1", "object_type": "Dependency", "name": "Dependency", "description": "Upstream GL feed.",
         "criticality": "Important", "confidence": 0.9},
        {"id": "r1", "object_type": "Risk", "name": "Risk", "description": "Late close risk.",
         "criticality": "Important", "confidence": 0.9},
        {"id": "b1", "object_type": "Business Rule", "name": "Business Rule", "description": "GL must balance to zero.",
         "criticality": "Important", "confidence": 0.9},
        {"id": "k1", "object_type": "Known Issue", "name": "Known Issue", "description": "Known late-feed lag.",
         "criticality": "Important", "confidence": 0.9},
    ]
}
BOUNDARY_MOCK = {"verdicts": [{"object_id": oid, "verdict": "confirm"} for oid in ("p1", "t1", "s1", "d1", "r1", "b1", "k1")]}
RELATIONSHIP_MOCK = {"relationships": []}


def _interpretation_for_gap(kva_result):
    from services.response_interpretation import InterpretationResult, InterpretedObjectChange

    if not kva_result.gaps:
        return None
    gap = kva_result.gaps[0]
    if gap.object_type == "Control":
        return InterpretationResult(
            gap_object_type="Control",
            raw_text="We run a month-end close checklist control.",
            object_changes=[
                InterpretedObjectChange(
                    action="create", object_type="Control", name="Close Checklist",
                    description="Month-end close checklist control.",
                    criticality="Important",
                )
            ],
        )
    if gap.object_type == "Task":
        return InterpretationResult(
            gap_object_type="Task",
            raw_text="We reconcile sub-ledgers daily before the close.",
            object_changes=[
                InterpretedObjectChange(
                    action="update", object_type="Task", name="Task",
                    description="We reconcile sub-ledgers daily before the close.",
                    criticality="Important", target_object_id="t1",
                )
            ],
        )
    return None


def test_probe(db_session, sample_program, sample_package):
    from models import Participant

    client = ClaudeClient(dev_mode=True, cache_enabled=False)
    demo = DemoRunner(db_session, claude_client=client)

    participant = Participant(program_id=sample_program.id, name="Demo Receiver", participant_type="Receiver")
    db_session.add(participant)
    db_session.flush()

    log = demo.run_full_demo(
        program_id=sample_program.id,
        package_id=sample_package.id,
        filename="sop.txt",
        content=b"Month-end close SOP.",
        interpretation_for_gap=_interpretation_for_gap,
        participant_id=participant.id,
        role_tier="Primary",
        competency_response_strategy={},
        extraction_mock=EXTRACTION_MOCK, boundary_mocks=[BOUNDARY_MOCK], relationship_mock=RELATIONSHIP_MOCK,
    )
    for step in log.steps:
        print("STEP:", step.name, step.status, step.detail)
