"""Schema creation. Alembic can be layered on later; create_all keeps the MVP simple."""

from __future__ import annotations

from app.core.logging import get_logger
from app.db.base import Base
from app.db.session import engine
from app.models import *  # noqa: F401,F403  (registers all tables)

logger = get_logger(__name__)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    logger.info("database schema ensured (%s tables)", len(Base.metadata.tables))
