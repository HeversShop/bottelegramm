from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class RegistrationType(str, Enum):
    single = "single"
    team = "team"


class TournamentStatus(str, Enum):
    registration = "registration"
    ongoing = "ongoing"
    finished = "finished"
    cancelled = "cancelled"


class BracketType(str, Enum):
    single_elimination = "single_elimination"
    double_elimination = "double_elimination"
    round_robin = "round_robin"


class GameFormat(str, Enum):
    one_v_one = "1v1"
    two_v_two = "2v2"
    five_v_five = "5v5"


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    nickname_cs2: str | None
    steam_id: str | None
    role: str


class UserUpdate(BaseModel):
    nickname_cs2: str | None = Field(default=None, max_length=128)
    steam_id: str | None = Field(default=None, max_length=64)


class TelegramLoginPayload(BaseModel):
    id: int
    auth_date: int
    hash: str
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class ProfileStats(BaseModel):
    registered_tournaments: int
    played_tournaments: int
    matches: int
    wins: int


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    tag: str | None
    captain_id: int
    player_profile_links: list[str]
    is_singleton: bool


class TournamentCreate(BaseModel):
    name: str = Field(min_length=3, max_length=160)
    game_format: GameFormat
    bracket_type: BracketType = BracketType.single_elimination
    start_date: datetime
    registration_deadline: datetime | None = None
    max_teams: int = Field(ge=2, le=1024)
    prize_pool: str | None = Field(default=None, max_length=64)
    rules: str | None = None


class TournamentRead(BaseModel):
    id: int
    name: str
    game_format: str
    bracket_type: str
    status: str
    start_date: datetime
    registration_deadline: datetime | None
    max_teams: int
    prize_pool: str | None
    rules: str | None
    registered_count: int = 0


class RegistrationCreate(BaseModel):
    registration_type: RegistrationType
    team_name: str | None = Field(default=None, max_length=128)
    team_tag: str | None = Field(default=None, max_length=16)
    player_profile_links: list[HttpUrl] = Field(default_factory=list, max_length=10)
    member_telegram_ids: list[int] = Field(default_factory=list, max_length=5)

    @field_validator("member_telegram_ids")
    @classmethod
    def unique_member_ids(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("member_telegram_ids must be unique")
        return value


class RegistrationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tournament_id: int
    team_id: int | None
    user_id: int | None
    participant_team_id: int | None
    registration_type: str
    status: str
    registered_at: datetime


class MatchRead(BaseModel):
    id: int
    bracket: str
    stage: str
    round_number: int
    bracket_position: int
    team1: TeamRead | None = None
    team2: TeamRead | None = None
    score1: int | None
    score2: int | None
    winner_id: int | None
    status: str
    scheduled_at: datetime | None


class BracketRead(BaseModel):
    tournament_id: int
    tournament_status: str
    matches: list[MatchRead]


class MatchResultCreate(BaseModel):
    score1: int = Field(ge=0, le=99)
    score2: int = Field(ge=0, le=99)
    notify_participants: bool = True


class NotificationCreate(BaseModel):
    message: str = Field(min_length=1, max_length=4096)


class NotificationRead(BaseModel):
    sent: int
    failed: int
