import asyncio

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_admin_user, get_bot, get_current_user
from app.config import get_settings
from app.database import get_session
from app.models import Match, TeamMember, Tournament, TournamentRegistration, User
from app.schemas import (
    BracketRead,
    MatchRead,
    MatchResultCreate,
    NotificationCreate,
    NotificationRead,
    ProfileStats,
    RegistrationCreate,
    RegistrationRead,
    TelegramLoginPayload,
    TournamentCreate,
    TournamentRead,
    TournamentStatus,
    UserRead,
    UserUpdate,
)
from app.security.init_data import TelegramInitDataError, validate_login_widget
from app.services.tournaments import (
    create_tournament,
    generate_bracket,
    get_tournament_user_telegram_ids,
    record_match_result,
    register_for_tournament,
)

router = APIRouter(prefix="/api/v1")


def _tournament_read(tournament: Tournament, registered_count: int) -> TournamentRead:
    return TournamentRead(
        id=tournament.id,
        name=tournament.name,
        game_format=tournament.game_format,
        bracket_type=tournament.bracket_type,
        status=tournament.status,
        start_date=tournament.start_date,
        registration_deadline=tournament.registration_deadline,
        max_teams=tournament.max_teams,
        prize_pool=tournament.prize_pool,
        rules=tournament.rules,
        registered_count=registered_count,
    )


async def _get_tournament_with_count(session: AsyncSession, tournament_id: int):
    result = await session.execute(
        select(Tournament, func.count(TournamentRegistration.id))
        .outerjoin(
            TournamentRegistration,
            (TournamentRegistration.tournament_id == Tournament.id)
            & TournamentRegistration.status.in_(("confirmed", "pending")),
        )
        .where(Tournament.id == tournament_id)
        .group_by(Tournament.id)
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    return row[0], int(row[1])


async def _match_read(session: AsyncSession, match: Match) -> MatchRead:
    loaded = await session.scalar(
        select(Match)
        .where(Match.id == match.id)
        .options(selectinload(Match.team1), selectinload(Match.team2))
    )
    if loaded is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return MatchRead.model_validate(loaded)


async def _bracket_response(session: AsyncSession, tournament_id: int) -> BracketRead:
    tournament = await session.scalar(select(Tournament).where(Tournament.id == tournament_id))
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    matches = list(
        await session.scalars(
            select(Match)
            .where(Match.tournament_id == tournament_id)
            .options(selectinload(Match.team1), selectinload(Match.team2))
            .order_by(Match.bracket, Match.round_number, Match.bracket_position, Match.id)
        )
    )
    return BracketRead(
        tournament_id=tournament.id,
        tournament_status=tournament.status,
        matches=[MatchRead.model_validate(match) for match in matches],
    )


@router.get("/healthz", include_in_schema=False)
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.patch("/me", response_model=UserRead)
async def update_me(
    payload: UserUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> User:
    user.nickname_cs2 = payload.nickname_cs2
    user.steam_id = payload.steam_id
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/me/stats", response_model=ProfileStats)
async def my_stats(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ProfileStats:
    team_ids = list(
        await session.scalars(select(TeamMember.team_id).where(TeamMember.user_id == user.id))
    )
    registered = await session.scalar(
        select(func.count(TournamentRegistration.id)).where(
            or_(
                TournamentRegistration.user_id == user.id,
                TournamentRegistration.team_id.in_(team_ids or [-1]),
            ),
            TournamentRegistration.status != "cancelled",
        )
    )
    match_filter = or_(Match.team1_id.in_(team_ids or [-1]), Match.team2_id.in_(team_ids or [-1]))
    matches = await session.scalar(select(func.count(Match.id)).where(match_filter))
    wins = await session.scalar(
        select(func.count(Match.id)).where(match_filter, Match.winner_id.in_(team_ids or [-1]))
    )
    played_tournaments = await session.scalar(
        select(func.count(func.distinct(Match.tournament_id))).where(match_filter, Match.status == "finished")
    )
    return ProfileStats(
        registered_tournaments=int(registered or 0),
        played_tournaments=int(played_tournaments or 0),
        matches=int(matches or 0),
        wins=int(wins or 0),
    )


@router.post("/auth/telegram-login", response_model=UserRead)
async def telegram_login(
    payload: TelegramLoginPayload,
    session: AsyncSession = Depends(get_session),
) -> User:
    try:
        telegram_user = validate_login_widget(
            payload.model_dump(), get_settings().bot_token, get_settings().telegram_initdata_max_age
        )
    except TelegramInitDataError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    user = await session.scalar(select(User).where(User.telegram_id == telegram_user.telegram_id))
    if user is None:
        user = User(telegram_id=telegram_user.telegram_id)
        session.add(user)
    user.username = telegram_user.username
    user.first_name = telegram_user.first_name
    user.last_name = telegram_user.last_name
    if telegram_user.telegram_id in get_settings().admin_ids:
        user.role = "admin"
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/tournaments", response_model=list[TournamentRead])
async def list_tournaments(
    tournament_status: TournamentStatus | None = Query(default=None, alias="status"),
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> list[TournamentRead]:
    query = (
        select(Tournament, func.count(TournamentRegistration.id))
        .outerjoin(
            TournamentRegistration,
            (TournamentRegistration.tournament_id == Tournament.id)
            & TournamentRegistration.status.in_(("confirmed", "pending")),
        )
        .group_by(Tournament.id)
        .order_by(Tournament.start_date.desc())
    )
    if tournament_status:
        query = query.where(Tournament.status == tournament_status.value)
    rows = (await session.execute(query)).all()
    return [_tournament_read(row[0], int(row[1])) for row in rows]


@router.get("/tournaments/{tournament_id}", response_model=TournamentRead)
async def get_tournament(
    tournament_id: int,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> TournamentRead:
    tournament, registered_count = await _get_tournament_with_count(session, tournament_id)
    return _tournament_read(tournament, registered_count)


@router.get("/tournaments/{tournament_id}/bracket", response_model=BracketRead)
async def get_bracket(
    tournament_id: int,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> BracketRead:
    return await _bracket_response(session, tournament_id)


@router.post("/tournaments/{tournament_id}/registrations", response_model=RegistrationRead, status_code=201)
async def register(
    tournament_id: int,
    payload: RegistrationCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TournamentRegistration:
    return await register_for_tournament(session, tournament_id, user, payload)


@router.get("/tournaments/{tournament_id}/registrations/me", response_model=RegistrationRead)
async def get_my_registration(
    tournament_id: int,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> TournamentRegistration:
    registration = await session.scalar(
        select(TournamentRegistration)
        .where(
            TournamentRegistration.tournament_id == tournament_id,
            (TournamentRegistration.user_id == user.id)
            | TournamentRegistration.team_id.in_(
                select(TeamMember.team_id).where(TeamMember.user_id == user.id)
            ),
        )
        .order_by(TournamentRegistration.id.desc())
    )
    if registration is None:
        raise HTTPException(status_code=404, detail="Registration not found")
    return registration


admin_router = APIRouter(prefix="/api/v1/admin", dependencies=[Depends(get_admin_user)])


@admin_router.post("/tournaments", response_model=TournamentRead, status_code=201)
async def admin_create_tournament(
    payload: TournamentCreate,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(get_admin_user),
) -> TournamentRead:
    tournament = await create_tournament(session, admin, payload)
    return _tournament_read(tournament, 0)


@admin_router.post("/tournaments/{tournament_id}/generate-bracket", response_model=BracketRead)
async def admin_generate_bracket(
    tournament_id: int,
    session: AsyncSession = Depends(get_session),
    _: User = Depends(get_admin_user),
) -> BracketRead:
    await generate_bracket(session, tournament_id)
    return await _bracket_response(session, tournament_id)


@admin_router.post("/matches/{match_id}/result", response_model=MatchRead)
async def admin_record_result(
    match_id: int,
    payload: MatchResultCreate,
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
    _: User = Depends(get_admin_user),
) -> MatchRead:
    match, _ = await record_match_result(session, match_id, payload.score1, payload.score2)
    if payload.notify_participants:
        team_ids = [team_id for team_id in (match.team1_id, match.team2_id) if team_id]
        telegram_ids = await get_tournament_user_telegram_ids(session, match.tournament_id, team_ids)
        text = (
            f"Результат матча #{match.id}: {match.score1}:{match.score2}. "
            f"Победитель: команда #{match.winner_id}."
        )
        await _broadcast(bot, telegram_ids, text)
    return await _match_read(session, match)


@admin_router.post("/tournaments/{tournament_id}/notify", response_model=NotificationRead)
async def admin_notify_tournament(
    tournament_id: int,
    payload: NotificationCreate,
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
    _: User = Depends(get_admin_user),
) -> NotificationRead:
    tournament = await session.scalar(select(Tournament.id).where(Tournament.id == tournament_id))
    if tournament is None:
        raise HTTPException(status_code=404, detail="Tournament not found")
    telegram_ids = await get_tournament_user_telegram_ids(session, tournament_id)
    sent, failed = await _broadcast(bot, telegram_ids, payload.message)
    return NotificationRead(sent=sent, failed=failed)


@admin_router.post("/matches/{match_id}/notify", response_model=NotificationRead)
async def admin_notify_match(
    match_id: int,
    payload: NotificationCreate,
    session: AsyncSession = Depends(get_session),
    bot: Bot = Depends(get_bot),
    _: User = Depends(get_admin_user),
) -> NotificationRead:
    match = await session.scalar(select(Match).where(Match.id == match_id))
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    team_ids = [team_id for team_id in (match.team1_id, match.team2_id) if team_id]
    telegram_ids = await get_tournament_user_telegram_ids(session, match.tournament_id, team_ids)
    sent, failed = await _broadcast(bot, telegram_ids, payload.message)
    return NotificationRead(sent=sent, failed=failed)


async def _broadcast(bot: Bot, telegram_ids: list[int], message: str) -> tuple[int, int]:
    async def send(telegram_id: int) -> bool:
        try:
            await bot.send_message(telegram_id, message)
            return True
        except Exception:
            return False

    results = await asyncio.gather(*(send(telegram_id) for telegram_id in set(telegram_ids)))
    return sum(results), len(results) - sum(results)
