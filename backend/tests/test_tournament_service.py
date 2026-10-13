from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Match, Team, TeamMember, Tournament, TournamentRegistration, User
from app.services.tournaments import generate_bracket, record_match_result


@pytest.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


async def seed_tournament(session, bracket_type: str, count: int = 4) -> Tournament:
    users = [User(telegram_id=1000 + index, username=f"p{index}") for index in range(count)]
    session.add_all(users)
    await session.flush()
    tournament = Tournament(
        name="Test Cup",
        game_format="1v1",
        bracket_type=bracket_type,
        status="registration",
        start_date=datetime.now(UTC) + timedelta(days=1),
        max_teams=16,
        created_by=users[0].id,
    )
    session.add(tournament)
    await session.flush()
    for index, user in enumerate(users):
        team = Team(name=f"Team {index}", tag=f"T{index}", captain_id=user.id, player_profile_links=[])
        session.add(team)
        await session.flush()
        session.add(TeamMember(team_id=team.id, user_id=user.id))
        session.add(
            TournamentRegistration(
                tournament_id=tournament.id,
                team_id=team.id,
                participant_team_id=team.id,
                registration_type="team",
                status="confirmed",
            )
        )
    await session.commit()
    return tournament


@pytest.mark.asyncio
async def test_single_elimination_advances_winner(session) -> None:
    tournament = await seed_tournament(session, "single_elimination")
    matches = await generate_bracket(session, tournament.id)
    ready = [match for match in matches if match.status == "ready"]
    assert len(ready) == 2

    finished, _ = await record_match_result(session, ready[0].id, 13, 7)
    next_match = await session.scalar(select(Match).where(Match.id == ready[0].next_match_id))
    assert finished.status == "finished"
    assert finished.winner_id in (finished.team1_id, finished.team2_id)
    assert next_match.team1_id == finished.winner_id or next_match.team2_id == finished.winner_id


@pytest.mark.asyncio
async def test_double_elimination_creates_winners_losers_and_final(session) -> None:
    tournament = await seed_tournament(session, "double_elimination", count=4)
    matches = await generate_bracket(session, tournament.id)
    brackets = {match.bracket for match in matches}
    assert brackets == {"winners", "losers", "grand_final"}
    assert len([match for match in matches if match.bracket == "grand_final"]) == 1


@pytest.mark.asyncio
async def test_double_elimination_promotes_loser_and_creates_reset_final(session) -> None:
    tournament = await seed_tournament(session, "double_elimination", count=4)
    matches = await generate_bracket(session, tournament.id)
    for match in [item for item in matches if item.bracket == "winners" and item.round_number == 1]:
        await record_match_result(session, match.id, 13, 5)

    winners_final = next(item for item in matches if item.bracket == "winners" and item.round_number == 2)
    await record_match_result(session, winners_final.id, 13, 10)
    losers_first = next(item for item in matches if item.bracket == "losers" and item.round_number == 1)
    await record_match_result(session, losers_first.id, 13, 11)
    losers_final = next(item for item in matches if item.bracket == "losers" and item.round_number == 2)
    assert losers_final.status == "ready"
    await record_match_result(session, losers_final.id, 13, 8)

    grand_final = next(item for item in matches if item.bracket == "grand_final")
    assert grand_final.status == "ready"
    await record_match_result(session, grand_final.id, 1, 13)
    reset_final = await session.scalar(
        select(Match).where(Match.tournament_id == tournament.id, Match.stage == "grand_final_reset")
    )
    assert reset_final is not None
    assert reset_final.status == "ready"
