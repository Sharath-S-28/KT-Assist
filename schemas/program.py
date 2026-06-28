"""
schemas/program.py — Request/response contracts for KT Programs and
Knowledge Packages.
"""

from typing import Optional

from pydantic import BaseModel, Field

from schemas.common import TimestampedSchema


class KTProgramCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class KTProgramRead(TimestampedSchema):
    name: str
    description: Optional[str] = None
    lifecycle_state: str
    completion_status: str


class KnowledgePackageCreate(BaseModel):
    program_id: str
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class KnowledgePackageRead(TimestampedSchema):
    program_id: str
    name: str
    description: Optional[str] = None
    package_type: Optional[str] = None
    complexity_signal_score: Optional[float] = None
    latest_coverage_score: Optional[float] = None
