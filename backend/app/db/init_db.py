"""Database initialization and Alembic migrations.

Supports:
- Automatic schema migration on boot (AUTO_MIGRATE=true) via Alembic.
- Zero-crash fallback / stamping for pre-existing local databases without alembic_version.
- Single-user local workspace and user seeding.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import inspect

from app.core.config import settings
from app.core.logging import get_logger
from app.db.base import Base
from app.db.session import engine
from app.models import *  # noqa: F401,F403  (registers all tables on Base.metadata)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = get_logger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]


def get_alembic_config(db_url: str | None = None):
    """Construct an Alembic Config object configured for LLM-EvalHub."""
    from alembic.config import Config

    ini_file = BACKEND_DIR / "alembic.ini"
    cfg = Config(str(ini_file))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    effective_url = db_url or settings.database_url
    cfg.set_main_option("sqlalchemy.url", effective_url)
    return cfg


def run_migrations(db_url: str | None = None, target: str = "head") -> None:
    """Run Alembic migrations programmatically.

    If the database already has tables from a previous create_all() execution
    but lacks an alembic_version table, it is stamped to the initial revision/head
    so subsequent migrations proceed without table collision.
    """
    from sqlalchemy import create_engine

    from alembic import command

    cfg = get_alembic_config(db_url)
    effective_url = db_url or settings.database_url

    has_existing_tables = False
    has_version_row = False

    try:
        from sqlalchemy import text
        insp_eng = engine if db_url is None else create_engine(effective_url)
        with insp_eng.connect() as conn:
            insp = inspect(conn)
            table_names = set(insp.get_table_names())
            if "alembic_version" in table_names:
                rows = conn.execute(text("SELECT version_num FROM alembic_version")).fetchall()
                has_version_row = bool(rows)

            domain_tables = {"datasets", "experiments", "workspaces", "users", "jobs", "audit_runs"}
            has_existing_tables = bool(domain_tables.intersection(table_names))
        if db_url is not None:
            insp_eng.dispose()
    except Exception as exc:
        logger.debug("Database inspection before migration encountered: %s", exc)

    if has_existing_tables and not has_version_row:
        logger.info("Existing pre-Alembic database detected (or missing version row). Stamping schema to 'head'.")
        command.stamp(cfg, "head")
        return

    logger.info("Executing Alembic migration upgrade to '%s'", target)
    command.upgrade(cfg, target)


def seed_default_workspace_and_user() -> None:
    """Ensure default local workspace and user exist for single-user local mode."""
    from sqlalchemy import select

    from app.core.security import hash_password
    from app.db.session import SessionLocal
    from app.models.auth import User, Workspace, WorkspaceMember

    with SessionLocal() as session:
        wks = session.get(Workspace, "wks_default")
        if not wks:
            # Check by slug
            wks = session.execute(
                select(Workspace).where(Workspace.slug == "default")
            ).scalar_one_or_none()
            if not wks:
                wks = Workspace(
                    id="wks_default",
                    name="Default Workspace",
                    slug="default",
                    description="Default local workspace for single-user development.",
                )
                session.add(wks)
                session.flush()

        user = session.get(User, "usr_default")
        if not user:
            user = session.execute(
                select(User).where(User.email == "local@evalhub.local")
            ).scalar_one_or_none()
            if not user:
                user = User(
                    id="usr_default",
                    email="local@evalhub.local",
                    hashed_password=hash_password("evalhub-local-password-1234"),
                    full_name="Local Developer",
                    is_active=True,
                    is_superuser=True,
                )
                session.add(user)
                session.flush()

        member = session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == wks.id,
                WorkspaceMember.user_id == user.id,
            )
        ).scalar_one_or_none()
        if not member:
            member = WorkspaceMember(
                id="wkm_default",
                workspace_id=wks.id,
                user_id=user.id,
                role="owner",
            )
            session.add(member)

        session.commit()


def _migrate_schema() -> None:
    """Safely migrate legacy tables when columns are added without Alembic."""
    from sqlalchemy import inspect, text

    tables_to_scope = [
        "datasets",
        "documents",
        "experiments",
        "evaluation_runs",
        "recommendations",
        "reports",
    ]
    with engine.begin() as conn:
        inspector = inspect(conn)
        for table_name in tables_to_scope:
            if inspector.has_table(table_name):
                columns = [col["name"] for col in inspector.get_columns(table_name)]
                if "workspace_id" not in columns:
                    logger.info("Migrating table %s: adding workspace_id column", table_name)
                    conn.execute(
                        text(
                            f"ALTER TABLE {table_name} ADD COLUMN workspace_id VARCHAR(64) DEFAULT 'wks_default'"
                        )
                    )
                    conn.execute(
                        text(
                            f"UPDATE {table_name} SET workspace_id = 'wks_default' WHERE workspace_id IS NULL"
                        )
                    )
                    try:
                        conn.execute(
                            text(
                                f"CREATE INDEX IF NOT EXISTS ix_{table_name}_workspace_id ON {table_name} (workspace_id)"
                            )
                        )
                    except Exception as exc:
                        logger.debug("Failed creating index ix_%s_workspace_id: %s", table_name, exc)


def init_db(engine_override: Engine | None = None, db_url: str | None = None) -> None:
    """Initialize database tables and run migrations if AUTO_MIGRATE is enabled."""
    effective_url = db_url or settings.database_url

    if settings.auto_migrate:
        try:
            run_migrations(db_url=effective_url)
            logger.info("Database schema up to date via Alembic migrations.")
        except Exception as exc:
            logger.error("Alembic migration failed: %s. Falling back to create_all.", exc)
            Base.metadata.create_all(bind=engine_override or engine)
    else:
        logger.info("AUTO_MIGRATE is False; skipping automatic migration on startup.")

    try:
        seed_default_workspace_and_user()
    except Exception as exc:
        logger.debug("seed_default_workspace_and_user: %s", exc)
    try:
        _migrate_schema()
    except Exception as exc:
        logger.error("schema migration failed: %s", exc)
