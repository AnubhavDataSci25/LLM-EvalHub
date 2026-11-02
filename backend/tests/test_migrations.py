"""Tests for Alembic database migrations."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

import app.models  # noqa: F401
from alembic import command
from app.db.base import Base
from app.db.init_db import get_alembic_config, init_db, run_migrations


@pytest.fixture()
def temp_db_path(tmp_path: Path) -> Generator[str, None, None]:
    db_file = tmp_path / "test_migration.db"
    db_url = f"sqlite:///{db_file}"
    yield db_url
    if db_file.exists():
        db_file.unlink()


def test_empty_db_upgrade_head_matches_models(temp_db_path: str) -> None:
    """An empty SQLite database upgraded to head creates all tables and matches Base.metadata."""
    # 1. Run migration from scratch on a blank database
    run_migrations(db_url=temp_db_path, target="head")

    engine = create_engine(temp_db_path)
    try:
        with engine.connect() as conn:
            insp = inspect(conn)
            table_names = set(insp.get_table_names())

            # Verify alembic_version tracking table exists
            assert "alembic_version" in table_names

            # Verify every table in Base.metadata was created
            expected_tables = set(Base.metadata.tables.keys())
            for table_name in expected_tables:
                assert table_name in table_names, f"Missing table: {table_name}"

            # Verify all columns match for each table
            for table_name, model_table in Base.metadata.tables.items():
                db_cols = {col["name"] for col in insp.get_columns(table_name)}
                model_cols = {col.name for col in model_table.columns}
                assert model_cols.issubset(db_cols), (
                    f"Columns mismatch in {table_name}: missing {model_cols - db_cols}"
                )

            # Strict comparison using Alembic compare_metadata
            ctx = MigrationContext.configure(conn)
            diffs = compare_metadata(ctx, Base.metadata)
            assert diffs == [], f"Alembic detected schema differences against Base.metadata: {diffs}"
    finally:
        engine.dispose()


def test_upgrade_and_downgrade_cycle(temp_db_path: str) -> None:
    """Migrations can cleanly upgrade to head, downgrade to base, and re-upgrade."""
    cfg = get_alembic_config(temp_db_path)
    engine = create_engine(temp_db_path)

    try:
        # Upgrade to head
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            insp = inspect(conn)
            assert len(insp.get_table_names()) >= 28

        # Downgrade to base
        command.downgrade(cfg, "base")
        with engine.connect() as conn:
            insp = inspect(conn)
            tables = set(insp.get_table_names())
            # Only alembic_version remains after base downgrade
            assert tables == {"alembic_version"}

        # Re-upgrade to head
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            insp = inspect(conn)
            assert "datasets" in insp.get_table_names()
            assert "jobs" in insp.get_table_names()
            assert "experiments" in insp.get_table_names()
    finally:
        engine.dispose()


def test_stamp_existing_pre_alembic_db(temp_db_path: str) -> None:
    """A legacy pre-Alembic database (with tables but no alembic_version) is stamped to head without error."""
    engine = create_engine(temp_db_path)

    # 1. Simulate legacy state: create all tables directly via Base.metadata.create_all
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        insp = inspect(conn)
        assert "alembic_version" not in insp.get_table_names()
        assert "datasets" in insp.get_table_names()

    # 2. Run migrations; should detect existing tables and stamp to head rather than crashing
    run_migrations(db_url=temp_db_path)

    with engine.connect() as conn:
        insp = inspect(conn)
        assert "alembic_version" in insp.get_table_names()

    # 3. Subsequent upgrade head proceeds cleanly as a no-op
    cfg = get_alembic_config(temp_db_path)
    command.upgrade(cfg, "head")

    engine.dispose()


def test_auto_migrate_flag_behavior(temp_db_path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """init_db respects AUTO_MIGRATE=False and does not migrate when disabled."""
    # When AUTO_MIGRATE is False, init_db should skip migration
    monkeypatch.setattr("app.db.init_db.settings.auto_migrate", False)

    init_db(db_url=temp_db_path)
    engine = create_engine(temp_db_path)
    try:
        with engine.connect() as conn:
            insp = inspect(conn)
            # Empty database should remain unmigrated (no alembic_version)
            assert "alembic_version" not in insp.get_table_names()
    finally:
        engine.dispose()

    # When AUTO_MIGRATE is True, init_db migrates
    monkeypatch.setattr("app.db.init_db.settings.auto_migrate", True)
    init_db(db_url=temp_db_path)
    engine = create_engine(temp_db_path)
    try:
        with engine.connect() as conn:
            insp = inspect(conn)
            assert "alembic_version" in insp.get_table_names()
            assert "datasets" in insp.get_table_names()
    finally:
        engine.dispose()
