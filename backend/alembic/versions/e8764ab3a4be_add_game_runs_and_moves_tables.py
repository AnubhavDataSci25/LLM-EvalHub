"""add_game_runs_and_moves_tables

Revision ID: e8764ab3a4be
Revises: 45ac2178be85
Create Date: 2026-11-23 12:09:22.378924

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e8764ab3a4be'
down_revision: str | Sequence[str] | None = '45ac2178be85'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('game_runs',
        sa.Column('workspace_id', sa.String(length=48), nullable=False),
        sa.Column('evaluation_run_id', sa.String(length=48), nullable=True),
        sa.Column('game_type', sa.String(length=48), nullable=False),
        sa.Column('task_type', sa.String(length=48), nullable=False),
        sa.Column('model_id', sa.String(length=128), nullable=False),
        sa.Column('provider_key', sa.String(length=48), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('summary', sa.JSON(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.String(length=48), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['evaluation_run_id'], ['evaluation_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('game_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_game_runs_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_game_runs_evaluation_run_id'), ['evaluation_run_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_game_runs_game_type'), ['game_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_game_runs_model_id'), ['model_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_game_runs_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_game_runs_task_type'), ['task_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_game_runs_workspace_id'), ['workspace_id'], unique=False)

    op.create_table('game_moves',
        sa.Column('game_run_id', sa.String(length=48), nullable=False),
        sa.Column('evaluation_result_id', sa.String(length=48), nullable=True),
        sa.Column('ply', sa.Integer(), nullable=False),
        sa.Column('turn', sa.String(length=16), nullable=False),
        sa.Column('fen_before', sa.Text(), nullable=False),
        sa.Column('fen_after', sa.Text(), nullable=True),
        sa.Column('raw_model_output', sa.Text(), nullable=True),
        sa.Column('parsed_move', sa.String(length=32), nullable=True),
        sa.Column('is_legal', sa.Boolean(), nullable=False),
        sa.Column('is_parseable', sa.Boolean(), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('engine_eval_before', sa.Float(), nullable=True),
        sa.Column('engine_eval_after', sa.Float(), nullable=True),
        sa.Column('centipawn_loss', sa.Float(), nullable=True),
        sa.Column('is_blunder', sa.Boolean(), nullable=False),
        sa.Column('latency_ms', sa.Float(), nullable=True),
        sa.Column('commentary', sa.Text(), nullable=True),
        sa.Column('id', sa.String(length=48), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['evaluation_result_id'], ['evaluation_results.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['game_run_id'], ['game_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('game_moves', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_game_moves_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_game_moves_evaluation_result_id'), ['evaluation_result_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_game_moves_game_run_id'), ['game_run_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_game_moves_ply'), ['ply'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('game_moves', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_game_moves_ply'))
        batch_op.drop_index(batch_op.f('ix_game_moves_game_run_id'))
        batch_op.drop_index(batch_op.f('ix_game_moves_evaluation_result_id'))
        batch_op.drop_index(batch_op.f('ix_game_moves_created_at'))

    op.drop_table('game_moves')
    with op.batch_alter_table('game_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_game_runs_workspace_id'))
        batch_op.drop_index(batch_op.f('ix_game_runs_task_type'))
        batch_op.drop_index(batch_op.f('ix_game_runs_status'))
        batch_op.drop_index(batch_op.f('ix_game_runs_model_id'))
        batch_op.drop_index(batch_op.f('ix_game_runs_game_type'))
        batch_op.drop_index(batch_op.f('ix_game_runs_evaluation_run_id'))
        batch_op.drop_index(batch_op.f('ix_game_runs_created_at'))

    op.drop_table('game_runs')
