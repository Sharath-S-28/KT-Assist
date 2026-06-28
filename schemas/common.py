"""
schemas/common.py — Shared Pydantic base classes and enums.

These mirror the JSON contracts that agents (KAI, KVA, KGE, KRA, KASE)
exchange with services. Agents must communicate only through these
structured contracts, never free-text prompts (Appendix D).
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class ORMBaseSchema(BaseModel):
    """Base for schemas that read directly from ORM model instances."""

    model_config = ConfigDict(from_attributes=True)


class Criticality(str, Enum):
    CRITICAL = "Critical"
    IMPORTANT = "Important"
    SUPPORTING = "Supporting"


class ObjectValidationStatus(str, Enum):
    COMPLETE = "Complete"
    PARTIAL = "Partial"
    MISSING = "Missing"


class EvidenceStatus(str, Enum):
    DEMONSTRATED = "Demonstrated"
    PARTIAL = "Partial"
    MISSING = "Missing"


class ReceiverRoleTier(str, Enum):
    PRIMARY = "Primary"
    SECONDARY = "Secondary"
    OVERSIGHT = "Oversight"


class ReadinessDecision(str, Enum):
    READY = "Ready"
    CONDITIONALLY_READY = "Conditionally Ready"
    NOT_READY = "Not Ready"


class TimestampedSchema(ORMBaseSchema):
    id: str
    created_at: datetime
    updated_at: datetime
