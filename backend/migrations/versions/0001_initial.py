"""Create CS2 tournament schema.

Revision ID: 0001_initial
Revises:
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64)),
        sa.Column("first_name", sa.String(128)),
        sa.Column("last_name", sa.String(128)),
        sa.Column("nickname_cs2", sa.String(128)),
        sa.Column("steam_id", sa.String(64)),
        sa.Column("role", sa.String(16), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=False)
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    op.create_table(
        "teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("tag", sa.String(16)),
        sa.Column("captain_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("player_profile_links", sa.JSON(), nullable=False),
        sa.Column("is_singleton", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_teams_captain_id", "teams", ["captain_id"], unique=False)

    op.create_table(
        "team_members",
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "tournaments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("game_format", sa.String(8), nullable=False),
        sa.Column("bracket_type", sa.String(24), nullable=False, server_default="single_elimination"),
        sa.Column("status", sa.String(16), nullable=False, server_default="registration"),
        sa.Column("start_date", sa.DateTime(), nullable=False),
        sa.Column("registration_deadline", sa.DateTime()),
        sa.Column("max_teams", sa.Integer(), nullable=False),
        sa.Column("prize_pool", sa.String(64)),
        sa.Column("rules", sa.Text()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tournaments_status", "tournaments", ["status"], unique=False)

    op.create_table(
        "tournament_registrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="RESTRICT")),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("participant_team_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("registration_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="confirmed"),
        sa.Column("registered_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "(team_id IS NOT NULL AND user_id IS NULL) OR (team_id IS NULL AND user_id IS NOT NULL)",
            name="registration_subject_check",
        ),
    )
    op.create_index("ix_tournament_registrations_tournament_id", "tournament_registrations", ["tournament_id"])
    op.create_index("ix_tournament_registrations_status", "tournament_registrations", ["status"])

    op.create_table(
        "matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("bracket", sa.String(16), nullable=False, server_default="single"),
        sa.Column("stage", sa.String(64), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("bracket_position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("team1_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("team2_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("score1", sa.Integer()),
        sa.Column("score2", sa.Integer()),
        sa.Column("winner_id", sa.Integer(), sa.ForeignKey("teams.id", ondelete="SET NULL")),
        sa.Column("status", sa.String(16), nullable=False, server_default="waiting"),
        sa.Column("scheduled_at", sa.DateTime()),
        sa.Column("next_match_id", sa.Integer(), sa.ForeignKey("matches.id")),
        sa.Column("next_slot", sa.Integer()),
        sa.Column("loser_next_match_id", sa.Integer(), sa.ForeignKey("matches.id")),
        sa.Column("loser_next_slot", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_matches_tournament_id", "matches", ["tournament_id"])
    op.create_index("ix_matches_status", "matches", ["status"])


def downgrade() -> None:
    op.drop_table("matches")
    op.drop_table("tournament_registrations")
    op.drop_table("tournaments")
    op.drop_table("team_members")
    op.drop_table("teams")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")

