"use client";

import { use, useState } from "react";
import Link from "next/link";
import { PlayerHeadshot, TeamLogo } from "@/components/nba-images";
import { useHeadToHead, useTeamProfile, useTeams } from "@/lib/hooks";
import type { components } from "@/lib/api-client/schema";

type GameSummary = components["schemas"]["GameSummary"];

function teamResult(g: GameSummary, teamId: number): "W" | "L" | null {
  if (g.home_score == null || g.away_score == null) return null;
  const homeWon = g.home_score > g.away_score;
  const isHome = g.home_team.team_id === teamId;
  return (isHome ? homeWon : !homeWon) ? "W" : "L";
}

function ResultBadge({ result }: { result: "W" | "L" | null }) {
  return (
    <span
      aria-label={result == null ? "result pending" : result === "W" ? "win" : "loss"}
      className={`inline-block w-4 text-center font-bold ${
        result == null
          ? "text-zinc-600"
          : result === "W"
            ? "text-emerald-400"
            : "text-rose-400"
      }`}
    >
      {result ?? "–"}
    </span>
  );
}

function GamesTable({ games, teamId }: { games: GameSummary[]; teamId: number }) {
  if (games.length === 0) {
    return <p className="text-sm text-zinc-500">No games.</p>;
  }
  return (
    <table className="w-full text-sm">
      <tbody className="font-mono tabular-nums">
        {games.map((g) => {
          const score =
            g.home_score != null && g.away_score != null
              ? `${g.away_score}–${g.home_score}`
              : "—";
          return (
            <tr key={g.game_id} className="border-b border-zinc-900 hover:bg-zinc-900/50">
              <td className="py-2 pr-2 font-sans text-zinc-400">
                <Link href={`/games/${g.game_id}`} className="hover:underline">
                  {g.game_date}
                </Link>
              </td>
              <td className="py-2 px-2 font-sans whitespace-nowrap">
                <ResultBadge result={teamResult(g, teamId)} />{" "}
                <span className="text-zinc-300">
                  {g.away_team.abbreviation} @ {g.home_team.abbreviation}
                </span>
              </td>
              <td className="py-2 pl-2 text-right text-zinc-300">{score}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function HeadToHead({ teamId }: { teamId: number }) {
  const [opponent, setOpponent] = useState<number | null>(null);
  const teamsQ = useTeams({ page_size: 40 });
  const h2hQ = useHeadToHead(teamId, opponent);
  const options = (teamsQ.data?.items ?? []).filter((t) => t.team_id !== teamId);
  const h2h = h2hQ.data;

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-zinc-300">Head-to-head</h2>
        <label className="flex items-center gap-2 text-xs text-zinc-500">
          vs
          <select
            value={opponent ?? ""}
            onChange={(e) => setOpponent(e.target.value ? Number(e.target.value) : null)}
            className="bg-zinc-900 border border-zinc-800 rounded-md px-2 py-1 text-sm text-zinc-300"
          >
            <option value="">Select opponent…</option>
            {options.map((t) => (
              <option key={t.team_id} value={t.team_id}>
                {t.full_name}
              </option>
            ))}
          </select>
        </label>
      </div>

      {opponent == null ? (
        <p className="text-sm text-zinc-600">
          Pick an opponent to see the series record and every meeting.
        </p>
      ) : h2hQ.isPending ? (
        <div className="h-24 rounded-lg bg-zinc-800/40 animate-pulse" />
      ) : h2h ? (
        <>
          <p className="text-sm text-zinc-400">
            Series:{" "}
            <span className="font-mono text-zinc-200">
              {h2h.team.abbreviation} {h2h.team_wins}–{h2h.opponent_wins}{" "}
              {h2h.opponent.abbreviation}
            </span>{" "}
            {h2h.games.length === 0 && "(no games in the loaded seasons)"}
          </p>
          <GamesTable games={h2h.games} teamId={teamId} />
        </>
      ) : (
        <p className="text-sm text-zinc-500">Head-to-head unavailable.</p>
      )}
    </section>
  );
}

export default function TeamDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const teamId = Number(id);
  const { data: profile, isPending, isError } = useTeamProfile(teamId);

  if (isError) {
    return (
      <main className="p-8 text-center text-zinc-400">
        Team not found.{" "}
        <Link href="/teams" className="underline">
          Back to teams
        </Link>
      </main>
    );
  }

  return (
    <main className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <Link
        href="/teams"
        className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        ← All teams
      </Link>

      {isPending ? (
        <div className="h-24 rounded-xl bg-zinc-800/50 animate-pulse" />
      ) : profile ? (
        <>
          <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
            <div className="flex items-center gap-4">
              <TeamLogo
                teamId={profile.team.team_id}
                name={profile.team.full_name}
                className="size-14"
              />
              <div className="space-y-1">
                <div className="flex items-baseline gap-3">
                  <span className="font-mono text-sm text-zinc-500">
                    {profile.team.abbreviation}
                  </span>
                  <h1 className="text-2xl font-bold tracking-tight">
                    {profile.team.full_name}
                  </h1>
                </div>
                <p className="text-sm text-zinc-500">
                  {[profile.team.conference, profile.team.division]
                    .filter(Boolean)
                    .join(" · ") || "Conference/division not available"}
                </p>
                <p className="text-sm text-zinc-400">
                  Record{" "}
                  <span className="font-mono font-semibold text-zinc-200">
                    {profile.wins}–{profile.losses}
                  </span>
                </p>
              </div>
            </div>
          </section>

          <section className="space-y-2">
            <h2 className="text-sm font-semibold text-zinc-300">Recent games</h2>
            <GamesTable games={profile.recent_games} teamId={teamId} />
          </section>

          <HeadToHead teamId={teamId} />

          <section className="space-y-2">
            <h2 className="text-sm font-semibold text-zinc-300">
              Roster{" "}
              <span className="text-xs text-zinc-600 font-normal">
                ({profile.roster.length})
              </span>
            </h2>
            <ul className="grid grid-cols-2 gap-1" aria-label="Roster">
              {profile.roster.map((p) => (
                <li key={p.player_id}>
                  <Link
                    href={`/players/${p.player_id}`}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900/50 hover:bg-zinc-800/60 transition-colors"
                  >
                    <PlayerHeadshot
                      playerId={p.player_id}
                      name={p.full_name}
                      className="size-7"
                    />
                    <span className="text-sm truncate">{p.full_name}</span>
                    <span className="ml-auto text-xs text-zinc-500">
                      {p.position ?? ""}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        </>
      ) : null}
    </main>
  );
}
