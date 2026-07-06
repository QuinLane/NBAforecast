"""play_by_play: v2 integer event codes → v3 string action types

The NBA retired the v2 stats endpoints (discovered live at M3.5: playbyplayv2 /
boxscore*v2 return empty payloads for every era). PlayByPlayV3 describes events as
``actionType``/``subType`` strings instead of ``EVENTMSGTYPE``/``EVENTMSGACTIONTYPE``
integer codes, so the columns change with the source.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("play_by_play", "event_msg_type")
    op.drop_column("play_by_play", "event_action_type")
    op.add_column("play_by_play", sa.Column("action_type", sa.String(), nullable=True))
    op.add_column("play_by_play", sa.Column("sub_type", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("play_by_play", "action_type")
    op.drop_column("play_by_play", "sub_type")
    op.add_column("play_by_play", sa.Column("event_msg_type", sa.Integer(), nullable=True))
    op.add_column("play_by_play", sa.Column("event_action_type", sa.Integer(), nullable=True))
