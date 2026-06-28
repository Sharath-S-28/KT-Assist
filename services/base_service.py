"""
services/base_service.py — Base abstraction for non-agent business
services (e.g. workflow engine, coverage engine call sites).

Services differ from agents in that they perform deterministic Python
logic and may call one or more agents/repositories, but never call
Claude directly themselves outside of an agent.
"""

import logging
from abc import ABC

from sqlalchemy.orm import Session

logger = logging.getLogger("kt_assist.services")


class BaseService(ABC):
    """Common constructor + logger for all services."""

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(f"kt_assist.services.{self.__class__.__name__}")
