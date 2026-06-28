"""
models/asset.py — Knowledge assets (raw inputs) and knowledge graph versions
(structured output of KAI / KGE).
"""

from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class KnowledgeAsset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A single uploaded/captured source document (PDF, DOCX, PPTX, TXT, ...).

    Stored as a file on disk; this row carries metadata plus the document
    hash used for KAI output caching (cost control).
    """

    __tablename__ = "knowledge_assets"

    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_packages.id"), nullable=False, index=True
    )

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(32), nullable=False)  # pdf/docx/pptx/txt
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    # SHA-256 of raw file content. KAI extraction is cached by this hash so
    # unchanged assets never re-hit the Claude API.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    extraction_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="Pending"
    )  # Pending / Extracted / Failed

    def __repr__(self) -> str:
        return f"<KnowledgeAsset id={self.id} filename={self.filename!r}>"


class KnowledgeGraphVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A versioned snapshot of a package's knowledge graph.

    v1 = initial KAI extraction; v2..vn = KGE enrichment increments.
    The graph payload itself is stored as JSON on disk
    (config.GRAPH_STORAGE_DIR); this row is the indexed pointer + summary.
    """

    __tablename__ = "knowledge_graph_versions"

    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("knowledge_packages.id"), nullable=False, index=True
    )

    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)

    node_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    relationship_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Free-text change summary (e.g. "Added 3 escalation objects via gap
    # closure"); empty/null for v1.
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<KnowledgeGraphVersion package_id={self.package_id} v{self.version_number}>"
