export type User = {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  nickname_cs2: string | null;
  steam_id: string | null;
  role: "user" | "admin" | string;
};

export type Tournament = {
  id: number;
  name: string;
  game_format: string;
  bracket_type: string;
  status: "registration" | "ongoing" | "finished" | "cancelled" | string;
  start_date: string;
  registration_deadline: string | null;
  max_teams: number;
  prize_pool: string | null;
  rules: string | null;
  registered_count: number;
};

export type Team = {
  id: number;
  name: string;
  tag: string | null;
  captain_id: number;
  player_profile_links: string[];
  is_singleton: boolean;
};

export type Match = {
  id: number;
  bracket: string;
  stage: string;
  round_number: number;
  bracket_position: number;
  team1: Team | null;
  team2: Team | null;
  score1: number | null;
  score2: number | null;
  winner_id: number | null;
  status: string;
  scheduled_at: string | null;
};

export type Bracket = {
  tournament_id: number;
  tournament_status: string;
  matches: Match[];
};

export type Registration = {
  id: number;
  tournament_id: number;
  team_id: number | null;
  user_id: number | null;
  participant_team_id: number | null;
  registration_type: string;
  status: string;
  registered_at: string;
};

export type ProfileStats = {
  registered_tournaments: number;
  played_tournaments: number;
  matches: number;
  wins: number;
};
