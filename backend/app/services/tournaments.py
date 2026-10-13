from collections.abc import Iterable
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Match, Team, TeamMember, Tournament, TournamentRegistration, User
from app.schemas import BracketType, RegistrationCreate, RegistrationType, TournamentCreate

ACTIVE_REGISTRATION_STATUSES = ("confirmed", "pending")
FINAL_MATCH_STATUSES = ("finished", "bye", "cancelled")


def _format_team_size(game_format: str) -> int:
    return {"1v1": 1, "2v2": 2, "5v5": 5}[game_format]


async def create_tournament(
    session: AsyncSession, creator: User, payload: TournamentCreate
) -> Tournament:
    tournament = Tournament(
        name=payload.name,
        game_format=payload.game_format.value,
        bracket_type=payload.bracket_type.value,
        status="registration",
        start_date=payload.start_date,
        registration_deadline=payload.registration_deadline,
        max_teams=payload.max_teams,
        prize_pool=payload.prize_pool,
        rules=payload.rules,
        created_by=creator.id,
    )
    session.add(tournament)
    await session.commit()
    await session.refresh(tournament)
    return tournament


async def register_for_tournament(
    session: AsyncSession, tournament_id: int, user: User, payload: RegistrationCreate
) -> TournamentRegistration:
    tournament = await session.scalar(select(Tournament).where(Tournament.id == tournament_id))
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if tournament.status != "registration":
        raise HTTPException(status_code=409, detail="Registration is closed")
    now = datetime.now(UTC)
    deadline = tournament.registration_deadline
    if deadline and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    if deadline and deadline < now:
        raise HTTPException(status_code=409, detail="Registration deadline has passed")

    registered_count = await session.scalar(
        select(func.count(TournamentRegistration.id)).where(
            TournamentRegistration.tournament_id == tournament.id,
            TournamentRegistration.status.in_(ACTIVE_REGISTRATION_STATUSES),
        )
    )
    if registered_count and registered_count >= tournament.max_teams:
        raise HTTPException(status_code=409, detail="Tournament is full")

    member_team_ids = select(TeamMember.team_id).where(TeamMember.user_id == user.id)
    duplicate = await session.scalar(
        select(TournamentRegistration.id).where(
            TournamentRegistration.tournament_id == tournament.id,
            TournamentRegistration.status.in_(ACTIVE_REGISTRATION_STATUSES),
            or_(
                TournamentRegistration.user_id == user.id,
                TournamentRegistration.team_id.in_(member_team_ids),
            ),
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="You or your team are already registered")

    if payload.registration_type == RegistrationType.single:
        team = Team(
            name=user.nickname_cs2 or user.username or f"Player {user.telegram_id}",
            tag=None,
            captain_id=user.id,
            player_profile_links=[str(link) for link in payload.player_profile_links],
            is_singleton=True,
        )
        session.add(team)
        await session.flush()
        session.add(TeamMember(team_id=team.id, user_id=user.id))
        registration = TournamentRegistration(
            tournament_id=tournament.id,
            user_id=user.id,
            team_id=None,
            participant_team_id=team.id,
            registration_type="single",
            status="confirmed",
        )
    else:
        expected_size = _format_team_size(tournament.game_format)
        member_ids = list(dict.fromkeys([user.telegram_id, *payload.member_telegram_ids]))
        if len(member_ids) != expected_size:
            raise HTTPException(
                status_code=422,
                detail=f"{tournament.game_format} team must have exactly {expected_size} player(s)",
            )
        if not payload.team_name or not payload.team_tag:
            raise HTTPException(status_code=422, detail="team_name and team_tag are required")

        members = list(
            await session.scalars(select(User).where(User.telegram_id.in_(member_ids)))
        )
        if len(members) != len(member_ids):
            raise HTTPException(
                status_code=422,
                detail="Every teammate must open the bot at least once before registration",
            )
        team = Team(
            name=payload.team_name,
            tag=payload.team_tag.upper(),
            captain_id=user.id,
            player_profile_links=[str(link) for link in payload.player_profile_links],
            is_singleton=False,
        )
        session.add(team)
        await session.flush()
        session.add_all([TeamMember(team_id=team.id, user_id=member.id) for member in members])
        registration = TournamentRegistration(
            tournament_id=tournament.id,
            team_id=team.id,
            user_id=None,
            participant_team_id=team.id,
            registration_type="team",
            status="confirmed",
        )

    session.add(registration)
    await session.commit()
    await session.refresh(registration)
    return registration


def _next_power_of_two(value: int) -> int:
    result = 1
    while result < value:
        result *= 2
    return result


def _set_match_slot(match: Match, slot: int, team_id: int | None) -> None:
    if team_id is None:
        return
    if slot == 1:
        if match.team1_id not in (None, team_id):
            raise ValueError(f"Match {match.id} team 1 is already occupied")
        match.team1_id = team_id
    else:
        if match.team2_id not in (None, team_id):
            raise ValueError(f"Match {match.id} team 2 is already occupied")
        match.team2_id = team_id
    if match.team1_id and match.team2_id and match.status == "waiting":
        match.status = "ready"


def _propagate_winner(match: Match, team_id: int, by_id: dict[int, Match]) -> None:
    if match.next_match_id and match.next_slot:
        _set_match_slot(by_id[match.next_match_id], match.next_slot, team_id)


def _propagate_loser(match: Match, loser_id: int, by_id: dict[int, Match]) -> None:
    if match.loser_next_match_id and match.loser_next_slot:
        _set_match_slot(by_id[match.loser_next_match_id], match.loser_next_slot, loser_id)


def _wire_winner_rounds(rounds: list[list[Match]]) -> None:
    for round_index in range(len(rounds) - 1):
        current_round = rounds[round_index]
        next_round = rounds[round_index + 1]
        for index, match in enumerate(current_round):
            match.next_match_id = next_round[index // 2].id
            match.next_slot = 1 if index % 2 == 0 else 2


async def _auto_advance_byes(session: AsyncSession, matches: list[Match]) -> None:
    by_id = {match.id: match for match in matches}
    for match in matches:
        if match.status == "bye" and match.winner_id:
            _propagate_winner(match, match.winner_id, by_id)

    changed = True
    while changed:
        changed = False
        incoming: dict[int, list[Match]] = {}
        for source in matches:
            if source.next_match_id:
                incoming.setdefault(source.next_match_id, []).append(source)
            if source.loser_next_match_id:
                incoming.setdefault(source.loser_next_match_id, []).append(source)
        for match in matches:
            if match.status != "waiting" or not (match.team1_id or match.team2_id):
                continue
            if match.team1_id and match.team2_id:
                match.status = "ready"
                changed = True
                continue
            sources = incoming.get(match.id, [])
            if not sources or not all(source.status in FINAL_MATCH_STATUSES for source in sources):
                continue
            match.winner_id = match.team1_id or match.team2_id
            match.status = "bye"
            if match.winner_id:
                _propagate_winner(match, match.winner_id, by_id)
            changed = True
    await session.flush()


async def _new_round(
    session: AsyncSession,
    tournament_id: int,
    count: int,
    bracket: str,
    round_number: int,
    stage: str,
) -> list[Match]:
    matches = [
        Match(
            tournament_id=tournament_id,
            bracket=bracket,
            stage=stage,
            round_number=round_number,
            bracket_position=index,
            status="waiting",
        )
        for index in range(count)
    ]
    session.add_all(matches)
    await session.flush()
    return matches


async def _materialize_participants(
    session: AsyncSession, registrations: list[TournamentRegistration]
) -> list[int]:
    result: list[int] = []
    for registration in registrations:
        if registration.participant_team_id:
            result.append(registration.participant_team_id)
            continue
        if not registration.user:
            raise HTTPException(status_code=422, detail="Registration has no participant")
        team = Team(
            name=registration.user.nickname_cs2
            or registration.user.username
            or f"Player {registration.user.telegram_id}",
            captain_id=registration.user.id,
            player_profile_links=[],
            is_singleton=True,
        )
        session.add(team)
        await session.flush()
        session.add(TeamMember(team_id=team.id, user_id=registration.user.id))
        registration.participant_team_id = team.id
        result.append(team.id)
    await session.flush()
    return result


async def _generate_single_bracket(
    session: AsyncSession, tournament: Tournament, participants: list[int], bracket: str = "single"
) -> list[Match]:
    bracket_size = _next_power_of_two(len(participants))
    round_count = bracket_size.bit_length() - 1
    rounds: list[list[Match]] = []
    for round_number in range(1, round_count + 1):
        rounds.append(
            await _new_round(
                session,
                tournament.id,
                bracket_size // (2**round_number),
                bracket,
                round_number,
                f"round_{round_number}",
            )
        )
    _wire_winner_rounds(rounds)

    padded = participants + [None] * (bracket_size - len(participants))
    for index, match in enumerate(rounds[0]):
        match.team1_id = padded[index * 2]
        match.team2_id = padded[index * 2 + 1]
        if match.team1_id and match.team2_id:
            match.status = "ready"
        elif match.team1_id or match.team2_id:
            match.status = "bye"
            match.winner_id = match.team1_id or match.team2_id
    return [match for current_round in rounds for match in current_round]


async def _generate_double_bracket(
    session: AsyncSession, tournament: Tournament, participants: list[int]
) -> list[Match]:
    if len(participants) < 4:
        raise HTTPException(status_code=422, detail="Double elimination requires at least 4 participants")
    bracket_size = _next_power_of_two(len(participants))
    winners_round_count = bracket_size.bit_length() - 1
    winners: list[list[Match]] = []
    for round_number in range(1, winners_round_count + 1):
        winners.append(
            await _new_round(
                session,
                tournament.id,
                bracket_size // (2**round_number),
                "winners",
                round_number,
                f"winners_r{round_number}",
            )
        )
    _wire_winner_rounds(winners)

    loser_round_count = 2 * winners_round_count - 2
    losers: list[list[Match]] = []
    for loser_round in range(1, loser_round_count + 1):
        phase = (loser_round + 1) // 2
        count = max(1, bracket_size // (2 ** (phase + 1)))
        losers.append(
            await _new_round(
                session,
                tournament.id,
                count,
                "losers",
                loser_round,
                f"losers_r{loser_round}",
            )
        )

    grand_final = Match(
        tournament_id=tournament.id,
        bracket="grand_final",
        stage="grand_final",
        round_number=1,
        bracket_position=0,
        status="waiting",
    )
    session.add(grand_final)
    await session.flush()

    for round_index in range(len(winners) - 1):
        for index, match in enumerate(winners[round_index]):
            match.next_match_id = winners[round_index + 1][index // 2].id
            match.next_slot = 1 if index % 2 == 0 else 2
    winners[-1][0].next_match_id = grand_final.id
    winners[-1][0].next_slot = 1

    for index, match in enumerate(winners[0]):
        match.loser_next_match_id = losers[0][index // 2].id
        match.loser_next_slot = 1 if index % 2 == 0 else 2
    for winner_round in range(1, winners_round_count):
        loser_round_index = 2 * winner_round - 1
        for index, match in enumerate(winners[winner_round]):
            match.loser_next_match_id = losers[loser_round_index].__getitem__(index).id
            match.loser_next_slot = 2

    for loser_round_index, current_round in enumerate(losers):
        if loser_round_index == len(losers) - 1:
            current_round[0].next_match_id = grand_final.id
            current_round[0].next_slot = 2
            continue
        next_round = losers[loser_round_index + 1]
        for index, match in enumerate(current_round):
            if loser_round_index % 2 == 0:
                match.next_match_id = next_round[index].id
                match.next_slot = 1
            else:
                match.next_match_id = next_round[index // 2].id
                match.next_slot = 1 if index % 2 == 0 else 2

    padded = participants + [None] * (bracket_size - len(participants))
    for index, match in enumerate(winners[0]):
        match.team1_id = padded[index * 2]
        match.team2_id = padded[index * 2 + 1]
        if match.team1_id and match.team2_id:
            match.status = "ready"
        elif match.team1_id or match.team2_id:
            match.status = "bye"
            match.winner_id = match.team1_id or match.team2_id
    return [match for current_round in [*winners, *losers, [grand_final]] for match in current_round]


async def _generate_round_robin(
    session: AsyncSession, tournament: Tournament, participants: list[int]
) -> list[Match]:
    matches: list[Match] = []
    for index, team1_id in enumerate(participants):
        for team2_id in participants[index + 1 :]:
            match = Match(
                tournament_id=tournament.id,
                bracket="round_robin",
                stage="round_robin",
                round_number=1,
                bracket_position=len(matches),
                team1_id=team1_id,
                team2_id=team2_id,
                status="ready",
            )
            session.add(match)
            matches.append(match)
    await session.flush()
    return matches


async def generate_bracket(session: AsyncSession, tournament_id: int) -> list[Match]:
    tournament = await session.scalar(select(Tournament).where(Tournament.id == tournament_id))
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    if tournament.status != "registration":
        raise HTTPException(status_code=409, detail="Bracket can only be generated during registration")

    existing = await session.scalar(select(Match.id).where(Match.tournament_id == tournament.id))
    if existing:
        raise HTTPException(status_code=409, detail="Bracket already exists")

    registrations = list(
        await session.scalars(
            select(TournamentRegistration)
            .where(
                TournamentRegistration.tournament_id == tournament.id,
                TournamentRegistration.status == "confirmed",
            )
            .options(selectinload(TournamentRegistration.user))
            .order_by(TournamentRegistration.registered_at, TournamentRegistration.id)
        )
    )
    if len(registrations) < 2:
        raise HTTPException(status_code=422, detail="At least two registrations are required")
    participants = await _materialize_participants(session, registrations)

    if tournament.bracket_type == BracketType.single_elimination.value:
        matches = await _generate_single_bracket(session, tournament, participants)
    elif tournament.bracket_type == BracketType.double_elimination.value:
        matches = await _generate_double_bracket(session, tournament, participants)
    else:
        matches = await _generate_round_robin(session, tournament, participants)

    tournament.status = "ongoing"
    await _auto_advance_byes(session, matches)
    await session.commit()
    return matches


async def _load_match_graph(session: AsyncSession, match: Match) -> dict[int, Match]:
    matches = list(
        await session.scalars(select(Match).where(Match.tournament_id == match.tournament_id))
    )
    return {item.id: item for item in matches}


async def record_match_result(
    session: AsyncSession, match_id: int, score1: int, score2: int
) -> tuple[Match, bool]:
    match = await session.scalar(
        select(Match)
        .where(Match.id == match_id)
        .options(selectinload(Match.tournament), selectinload(Match.team1), selectinload(Match.team2))
    )
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    if match.status in FINAL_MATCH_STATUSES:
        raise HTTPException(status_code=409, detail="Match is already finished")
    if not match.team1_id or not match.team2_id:
        raise HTTPException(status_code=409, detail="Match does not have two participants yet")
    if score1 == score2:
        raise HTTPException(status_code=422, detail="A tournament match cannot end in a draw")

    by_id = await _load_match_graph(session, match)
    match.score1 = score1
    match.score2 = score2
    match.winner_id = match.team1_id if score1 > score2 else match.team2_id
    loser_id = match.team2_id if match.winner_id == match.team1_id else match.team1_id
    match.status = "finished"

    tournament_finished = False
    if match.bracket == "grand_final" and match.tournament.bracket_type == BracketType.double_elimination.value:
        if match.stage == "grand_final" and match.winner_id == match.team2_id:
            reset = Match(
                tournament_id=match.tournament_id,
                bracket="grand_final",
                stage="grand_final_reset",
                round_number=2,
                bracket_position=0,
                team1_id=match.winner_id,
                team2_id=loser_id,
                status="ready",
            )
            session.add(reset)
        else:
            match.tournament.status = "finished"
            tournament_finished = True
    elif match.bracket == "round_robin":
        unfinished = await session.scalar(
            select(Match.id).where(
                Match.tournament_id == match.tournament_id,
                Match.status.notin_(FINAL_MATCH_STATUSES),
                Match.id != match.id,
            )
        )
        if unfinished is None:
            match.tournament.status = "finished"
            tournament_finished = True
    elif match.next_match_id:
        _propagate_winner(match, match.winner_id, by_id)
        if match.bracket == "winners" and loser_id:
            _propagate_loser(match, loser_id, by_id)
    else:
        match.tournament.status = "finished"
        tournament_finished = True

    await _auto_advance_byes(session, list(by_id.values()))
    await session.commit()
    return match, tournament_finished


async def get_tournament_user_telegram_ids(
    session: AsyncSession, tournament_id: int, team_ids: Iterable[int] | None = None
) -> list[int]:
    if team_ids is None:
        team_ids = list(
            await session.scalars(
                select(TournamentRegistration.participant_team_id).where(
                    TournamentRegistration.tournament_id == tournament_id,
                    TournamentRegistration.participant_team_id.is_not(None),
                )
            )
        )
    ids = list(team_ids)
    if not ids:
        return []
    return list(
        await session.scalars(
            select(User.telegram_id)
            .join(TeamMember, TeamMember.user_id == User.id)
            .where(TeamMember.team_id.in_(ids))
            .distinct()
        )
    )
