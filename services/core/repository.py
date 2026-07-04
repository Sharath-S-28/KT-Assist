"""
services/repository.py — Generic repository / CRUD abstraction over ORM
models.

Every service should go through a Repository rather than issuing raw
db.query() calls directly, so commit/rollback discipline and not-found
handling stay in one place.
"""

from typing import Generic, Optional, TypeVar

from sqlalchemy.orm import Session

from utils.errors import NotFoundError

ModelType = TypeVar("ModelType")


class Repository(Generic[ModelType]):
    """Thin generic CRUD wrapper. Subclass per model for model-specific
    query methods; the base methods cover create/get/list/update/delete.
    """

    def __init__(self, db: Session, model: type[ModelType]):
        self.db = db
        self.model = model

    def create(self, **kwargs) -> ModelType:
        instance = self.model(**kwargs)
        self.db.add(instance)
        self.db.flush()
        return instance

    def get(self, id: str) -> Optional[ModelType]:
        return self.db.get(self.model, id)

    def get_or_404(self, id: str) -> ModelType:
        instance = self.get(id)
        if instance is None:
            raise NotFoundError(
                f"{self.model.__name__} with id={id!r} not found",
                details={"model": self.model.__name__, "id": id},
            )
        return instance

    def list(self, limit: int = 100, offset: int = 0, **filters) -> list[ModelType]:
        query = self.db.query(self.model)
        for key, value in filters.items():
            query = query.filter(getattr(self.model, key) == value)
        return query.offset(offset).limit(limit).all()

    def update(self, id: str, **fields) -> ModelType:
        instance = self.get_or_404(id)
        for key, value in fields.items():
            setattr(instance, key, value)
        self.db.flush()
        return instance

    def delete(self, id: str) -> None:
        instance = self.get_or_404(id)
        self.db.delete(instance)
        self.db.flush()

    def count(self, **filters) -> int:
        query = self.db.query(self.model)
        for key, value in filters.items():
            query = query.filter(getattr(self.model, key) == value)
        return query.count()
