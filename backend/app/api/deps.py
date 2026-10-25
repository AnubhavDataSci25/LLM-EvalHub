"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db


def db_session() -> Iterator[Session]:
    yield from get_db()


DbSession = Annotated[Session, Depends(db_session)]


class Pagination:
    def __init__(
        self,
        limit: int = Query(50, ge=1, le=200, description="Maximum rows to return"),
        offset: int = Query(0, ge=0, description="Rows to skip"),
    ) -> None:
        self.limit = limit
        self.offset = offset


PageParams = Annotated[Pagination, Depends(Pagination)]
