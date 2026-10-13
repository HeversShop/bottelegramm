import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, hasTelegramAuth } from "./api";
import { notify } from "./telegram";
import type { Bracket, Match, ProfileStats, Registration, Tournament, User } from "./types";

type Tab = "tournaments" | "bracket" | "profile" | "admin";

const statusLabel: Record<string, string> = {
  registration: "Регистрация",
  ongoing: "Идёт сейчас",
  finished: "Завершён",
  cancelled: "Отменён"
};

const bracketLabel: Record<string, string> = {
  single_elimination: "Single elimination",
  double_elimination: "Double elimination",
  round_robin: "Круговая система"
};

function formatDate(date: string): string {
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(date)
  );
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [tournaments, setTournaments] = useState<Tournament[]>([]);
  const [selected, setSelected] = useState<Tournament | null>(null);
  const [bracket, setBracket] = useState<Bracket | null>(null);
  const [registration, setRegistration] = useState<Registration | null>(null);
  const [stats, setStats] = useState<ProfileStats | null>(null);
  const [tab, setTab] = useState<Tab>("tournaments");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadTournaments() {
    const list = await api<Tournament[]>("/tournaments");
    setTournaments(list);
  }

  useEffect(() => {
    if (!hasTelegramAuth()) {
      setError("Откройте Mini App из Telegram — Telegram initData отсутствует.");
      setLoading(false);
      return;
    }
    Promise.all([api<User>("/me"), api<ProfileStats>("/me/stats"), loadTournaments()])
      .then(([me, profileStats]) => { setUser(me); setStats(profileStats); })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

  async function openTournament(tournament: Tournament) {
    setSelected(tournament);
    setTab("bracket");
    try {
      const [nextBracket, nextRegistration] = await Promise.all([
        api<Bracket>(`/tournaments/${tournament.id}/bracket`),
        api<Registration>(`/tournaments/${tournament.id}/registrations/me`).catch(() => null)
      ]);
      setBracket(nextBracket);
      setRegistration(nextRegistration);
    } catch (reason) {
      setError((reason as Error).message);
    }
  }

  if (loading) return <div className="center-screen">Загрузка турниров…</div>;
  if (error && !user) {
    return (
      <div className="center-screen error-screen">
        <div className="brand-mark">CS<span>2</span></div>
        <h1>CS2 Tournament Center</h1>
        <p>{error}</p>
        <small>Для локальной разработки используйте Mini App в Telegram или настройте HTTPS-туннель.</small>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><span className="brand-mark">CS<span>2</span></span><span>Tournament Center</span></div>
        <div className="user-chip">{user?.username ? `@${user.username}` : user?.first_name}</div>
      </header>

      <main className="content">
        {error && <div className="toast error">{error}<button onClick={() => setError(null)}>×</button></div>}
        {tab === "tournaments" && (
          <TournamentList tournaments={tournaments} onOpen={openTournament} onRefresh={loadTournaments} />
        )}
        {tab === "bracket" && selected && (
          <BracketView tournament={selected} bracket={bracket} registration={registration} user={user} onRefresh={() => openTournament(selected)} />
        )}
        {tab === "profile" && <Profile user={user} tournaments={tournaments} stats={stats} />}
        {tab === "admin" && user?.role === "admin" && <AdminPanel onRefresh={loadTournaments} />}
      </main>

      <nav className="bottom-nav">
        <button className={tab === "tournaments" ? "active" : ""} onClick={() => setTab("tournaments")}>🏆<span>Турниры</span></button>
        <button className={tab === "bracket" ? "active" : ""} onClick={() => selected && setTab("bracket")} disabled={!selected}>⌘<span>Сетка</span></button>
        <button className={tab === "profile" ? "active" : ""} onClick={() => setTab("profile")}>◉<span>Профиль</span></button>
        {user?.role === "admin" && <button className={tab === "admin" ? "active" : ""} onClick={() => setTab("admin")}>⚙<span>Админ</span></button>}
      </nav>
    </div>
  );
}

function TournamentList({ tournaments, onOpen, onRefresh }: { tournaments: Tournament[]; onOpen: (t: Tournament) => void; onRefresh: () => Promise<void> }) {
  const [filter, setFilter] = useState("all");
  const visible = useMemo(() => filter === "all" ? tournaments : tournaments.filter((t) => t.status === filter), [filter, tournaments]);
  return (
    <section>
      <div className="hero"><p className="eyebrow">COMPETITIVE CS2</p><h1>Турниры</h1><p>Следи за матчами, собирай состав и забирай кубок.</p></div>
      <div className="filter-row">{[["all", "Все"], ["registration", "Регистрация"], ["ongoing", "Идут"], ["finished", "Архив"]].map(([value, label]) => <button key={value} className={filter === value ? "selected" : ""} onClick={() => setFilter(value)}>{label}</button>)}</div>
      <div className="tournament-grid">
        {visible.map((tournament) => <TournamentCard key={tournament.id} tournament={tournament} onOpen={() => onOpen(tournament)} />)}
        {!visible.length && <div className="empty-card">Пока нет турниров в этой категории.</div>}
      </div>
      <button className="ghost-button refresh" onClick={() => void onRefresh()}>Обновить список</button>
    </section>
  );
}

function TournamentCard({ tournament, onOpen }: { tournament: Tournament; onOpen: () => void }) {
  return <article className="tournament-card" onClick={onOpen}>
    <div className="card-top"><span className={`status-dot ${tournament.status}`}></span><span>{statusLabel[tournament.status] ?? tournament.status}</span><span className="format">{tournament.game_format}</span></div>
    <h2>{tournament.name}</h2>
    <p className="muted">{bracketLabel[tournament.bracket_type] ?? tournament.bracket_type}</p>
    <div className="card-meta"><span>📅 {formatDate(tournament.start_date)}</span><span>👥 {tournament.registered_count}/{tournament.max_teams}</span></div>
    {tournament.prize_pool && <div className="prize">Призовой фонд <strong>{tournament.prize_pool}</strong></div>}
    <button className="primary-button" onClick={(event) => { event.stopPropagation(); onOpen(); }}>{tournament.status === "registration" ? "Открыть и зарегистрироваться" : "Открыть сетку"}</button>
  </article>;
}

function BracketView({ tournament, bracket, registration, user, onRefresh }: { tournament: Tournament; bracket: Bracket | null; registration: Registration | null; user: User | null; onRefresh: () => Promise<void> }) {
  const [showRegistration, setShowRegistration] = useState(false);
  const rounds = useMemo(() => {
    const grouped = new Map<string, Match[]>();
    bracket?.matches.forEach((match) => grouped.set(match.stage, [...(grouped.get(match.stage) ?? []), match]));
    return [...grouped.entries()];
  }, [bracket]);
  return <section>
    <button className="back-button" onClick={() => history.back()}>← Все турниры</button>
    <div className="detail-heading"><div><p className="eyebrow">{tournament.game_format} · {bracketLabel[tournament.bracket_type]}</p><h1>{tournament.name}</h1><p className="muted">Старт: {formatDate(tournament.start_date)}</p></div>{tournament.status === "registration" && !registration && <button className="primary-button" onClick={() => setShowRegistration(true)}>Зарегистрироваться</button>}</div>
    {registration && <div className="success-banner">Вы зарегистрированы. Следите за обновлениями в этой сетке.</div>}
    {!bracket?.matches.length ? <div className="empty-card">Сетка ещё не сгенерирована организатором.</div> : <div className="bracket-board">{rounds.map(([stage, matches]) => <div className="bracket-column" key={stage}><h3>{stage.replaceAll("_", " ")}</h3>{matches.map((match) => <MatchCard key={match.id} match={match} />)}</div>)}</div>}
    {showRegistration && <RegistrationModal tournament={tournament} user={user} onClose={() => setShowRegistration(false)} onSuccess={() => { setShowRegistration(false); void onRefresh(); }} />}
  </section>;
}

function MatchCard({ match }: { match: Match }) {
  const team1 = match.team1?.tag ? `[${match.team1.tag}] ${match.team1.name}` : match.team1?.name ?? "Ожидание";
  const team2 = match.team2?.tag ? `[${match.team2.tag}] ${match.team2.name}` : match.team2?.name ?? "Ожидание";
  return <div className={`match-card ${match.status}`}><div className="match-id">MATCH #{match.id} <span>{match.status}</span></div><div className={match.winner_id === match.team1?.id ? "winner" : ""}>{team1}<b>{match.score1 ?? "—"}</b></div><div className={match.winner_id === match.team2?.id ? "winner" : ""}>{team2}<b>{match.score2 ?? "—"}</b></div></div>;
}

function RegistrationModal({ tournament, user, onClose, onSuccess }: { tournament: Tournament; user: User | null; onClose: () => void; onSuccess: () => void }) {
  const [type, setType] = useState<"single" | "team">("single");
  const [teamName, setTeamName] = useState("");
  const [teamTag, setTeamTag] = useState("");
  const [memberIds, setMemberIds] = useState("");
  const [links, setLinks] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await api<Registration>(`/tournaments/${tournament.id}/registrations`, { method: "POST", body: JSON.stringify({ registration_type: type, team_name: teamName || null, team_tag: teamTag || null, member_telegram_ids: memberIds.split(",").map((id) => Number(id.trim())).filter(Boolean), player_profile_links: links.split("\n").map((link) => link.trim()).filter(Boolean) }) });
      notify("Регистрация подтверждена!"); onSuccess();
    } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); }
  }
  return <div className="modal-backdrop"><form className="modal" onSubmit={submit}><div className="modal-header"><h2>Регистрация</h2><button type="button" onClick={onClose}>×</button></div><p className="muted">{tournament.name} · ваш Telegram: {user?.username ? `@${user.username}` : user?.telegram_id}</p><div className="segmented"><button type="button" className={type === "single" ? "selected" : ""} onClick={() => setType("single")}>Одиночная</button><button type="button" className={type === "team" ? "selected" : ""} onClick={() => setType("team")}>Команда</button></div>{type === "team" && <><label>Название команды<input value={teamName} onChange={(e) => setTeamName(e.target.value)} required /></label><label>Тэг<input value={teamTag} onChange={(e) => setTeamTag(e.target.value)} maxLength={16} required /></label><label>Telegram ID тиммейтов, через запятую<input value={memberIds} onChange={(e) => setMemberIds(e.target.value)} placeholder="123456789, 987654321" /></label></>}<label>Ссылки на Steam/профили, по одной в строке<textarea value={links} onChange={(e) => setLinks(e.target.value)} /></label>{error && <div className="form-error">{error}</div>}<button className="primary-button" disabled={busy}>{busy ? "Отправка…" : "Подтвердить регистрацию"}</button></form></div>;
}

function Profile({ user, tournaments, stats }: { user: User | null; tournaments: Tournament[]; stats: ProfileStats | null }) {
  return <section><div className="hero"><p className="eyebrow">PLAYER PROFILE</p><h1>{user?.nickname_cs2 ?? user?.username ?? user?.first_name}</h1><p>Telegram ID: {user?.telegram_id}</p></div><div className="stats-grid"><div><strong>{stats?.registered_tournaments ?? 0}</strong><span>Регистраций</span></div><div><strong>{stats?.wins ?? 0}</strong><span>Побед</span></div><div><strong>{stats?.matches ?? 0}</strong><span>Матчей</span></div></div><div className="panel"><h2>История турниров</h2><p className="muted">Сыграно турниров: {stats?.played_tournaments ?? 0}</p><div className="mini-list">{tournaments.filter((t) => t.status === "finished").slice(0, 3).map((t) => <div key={t.id}>{t.name}<span>{statusLabel[t.status]}</span></div>)}</div></div></section>;
}

function AdminPanel({ onRefresh }: { onRefresh: () => Promise<void> }) {
  const [name, setName] = useState(""); const [format, setFormat] = useState("5v5"); const [bracket, setBracket] = useState("single_elimination"); const [maxTeams, setMaxTeams] = useState(16); const [startDate, setStartDate] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(""); try { await api<Tournament>("/admin/tournaments", { method: "POST", body: JSON.stringify({ name, game_format: format, bracket_type: bracket, max_teams: maxTeams, start_date: new Date(startDate).toISOString() }) }); notify("Турнир создан"); setName(""); await onRefresh(); } catch (reason) { setError((reason as Error).message); } finally { setBusy(false); } }
  return <section><div className="hero"><p className="eyebrow">ADMIN CONTROL</p><h1>Админ-панель</h1><p>Создавайте турнир, закрывайте регистрацию, генерируйте сетку и отправляйте результаты через API.</p></div><form className="panel admin-form" onSubmit={submit}><h2>Новый турнир</h2><label>Название<input value={name} onChange={(e) => setName(e.target.value)} required /></label><div className="form-grid"><label>Формат<select value={format} onChange={(e) => setFormat(e.target.value)}><option>1v1</option><option>2v2</option><option>5v5</option></select></label><label>Макс. команд<input type="number" min="2" value={maxTeams} onChange={(e) => setMaxTeams(Number(e.target.value))} /></label></div><label>Тип сетки<select value={bracket} onChange={(e) => setBracket(e.target.value)}><option value="single_elimination">Single elimination</option><option value="double_elimination">Double elimination</option><option value="round_robin">Round robin</option></select></label><label>Дата и время старта<input type="datetime-local" value={startDate} onChange={(e) => setStartDate(e.target.value)} required /></label>{error && <div className="form-error">{error}</div>}<button className="primary-button" disabled={busy}>{busy ? "Создание…" : "Создать турнир"}</button></form></section>;
}
