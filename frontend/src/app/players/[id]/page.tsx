"use client";

import { use } from "react";
import Link from "next/link";
import { PlayerHeadshot, TeamLogo } from "@/components/nba-images";
import { PlayerTrajectory } from "@/components/player-trajectory";
import {
  usePlayer,
  usePlayerProps,
  usePlayerRapm,
  usePlayerStats,
} from "@/lib/hooks";

const STAT_LABELS: Record<string, string> = {
  pts: "Points",
  reb: "Rebounds",
  ast: "Assists",
  fg3m: "3-Pointers",
};

function PropsBoard({ playerId, gameId }: { playerId: number; gameId: string }) {
  const { data, isPending, isError } = usePlayerProps(playerId, gameId);

  if (isPending) {
    return <div className="h-24 rounded-lg bg-zinc-800/50 animate-pulse" />;
  }
  if (isError || !data || data.length === 0) {
    return (
      <p className="text-sm text-zinc-500">
        Projections unavailable (no props champion loaded yet).
      </p>
    );
  }
  return (
    <div className="grid grid-cols-2 gap-2">
      {data.map((p) => {
        const topDriver = p.explanation.contributions[0];
        return (
          <div
            key={p.stat}
            className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 space-y-1"
          >
            <div className="text-xs text-zinc-500">
              {STAT_LABELS[p.stat] ?? p.stat}
            </div>
            <div className="flex items-baseline gap-1">
              <span className="text-2xl font-bold font-mono">
                {p.point.toFixed(1)}
              </span>
              <span className="text-xs text-zinc-600 font-mono">
                [{p.interval_low.toFixed(0)}–{p.interval_high.toFixed(0)}]
              </span>
            </div>
            {topDriver && (
              <div className="text-[11px] text-zinc-500 truncate">
                {topDriver.direction === "up" ? "▲" : "▼"}{" "}
                {topDriver.display_label}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function pct(value: number | null | undefined): string {
  return value == null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function SeasonAveragesTable({ playerId }: { playerId: number }) {
  const { data, isPending } = usePlayerStats(playerId);
  const seasons = data?.seasons ?? [];

  if (isPending) {
    return <div className="h-20 rounded-lg bg-zinc-800/40 animate-pulse" />;
  }
  if (seasons.length === 0) return null;

  return (
    <section className="space-y-2">
      <h2 className="text-sm font-semibold text-zinc-300">Season averages</h2>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
            <th className="py-2 pr-2 font-medium">Season</th>
            <th className="py-2 px-2 font-medium text-right">GP</th>
            <th className="py-2 px-2 font-medium text-right">MIN</th>
            <th className="py-2 px-2 font-medium text-right">PTS</th>
            <th className="py-2 px-2 font-medium text-right">REB</th>
            <th className="py-2 px-2 font-medium text-right">AST</th>
            <th className="py-2 px-2 font-medium text-right">3PM</th>
            <th className="py-2 px-2 font-medium text-right">FG%</th>
            <th className="py-2 px-2 font-medium text-right">3P%</th>
            <th className="py-2 pl-2 font-medium text-right">FT%</th>
          </tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {seasons.map((s) => (
            <tr key={s.season} className="border-b border-zinc-900">
              <td className="py-2 pr-2 font-sans text-zinc-300">{s.season}</td>
              <td className="py-2 px-2 text-right text-zinc-400">{s.games_played}</td>
              <td className="py-2 px-2 text-right text-zinc-400">
                {s.min == null ? "—" : s.min.toFixed(1)}
              </td>
              <td className="py-2 px-2 text-right text-zinc-200">{s.pts.toFixed(1)}</td>
              <td className="py-2 px-2 text-right">{s.reb.toFixed(1)}</td>
              <td className="py-2 px-2 text-right">{s.ast.toFixed(1)}</td>
              <td className="py-2 px-2 text-right">{s.fg3m.toFixed(1)}</td>
              <td className="py-2 px-2 text-right text-zinc-400">{pct(s.fg_pct)}</td>
              <td className="py-2 px-2 text-right text-zinc-400">{pct(s.fg3_pct)}</td>
              <td className="py-2 pl-2 text-right text-zinc-400">{pct(s.ft_pct)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

export default function PlayerDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const playerId = Number(id);
  const playerQ = usePlayer(playerId);
  const rapmQ = usePlayerRapm(playerId);

  const player = playerQ.data;
  const latestGame = player?.recent_games[0]?.game_id ?? "";
  const latestRapm = rapmQ.data?.[rapmQ.data.length - 1];

  if (playerQ.isError) {
    return (
      <main className="p-8 text-center text-zinc-400">
        Player not found.{" "}
        <Link href="/players" className="underline">
          Back to players
        </Link>
      </main>
    );
  }

  return (
    <main className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <Link
        href="/players"
        className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        ← All players
      </Link>

      {playerQ.isPending ? (
        <div className="h-20 rounded-xl bg-zinc-800/50 animate-pulse" />
      ) : player ? (
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
          <div className="flex items-center gap-4">
            <PlayerHeadshot
              playerId={player.player_id}
              name={player.full_name}
              className="size-16"
            />
            <div className="space-y-1 min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold tracking-tight truncate">
                  {player.full_name}
                </h1>
                {player.recent_games[0] && (
                  <TeamLogo
                    teamId={player.recent_games[0].team_id}
                    name={player.recent_games[0].team_abbreviation ?? "team"}
                    className="size-7"
                  />
                )}
              </div>
              <p className="text-sm text-zinc-500">
                {[
                  player.position,
                  player.height_inches ? `${player.height_inches}"` : null,
                  player.weight_lbs ? `${player.weight_lbs} lb` : null,
                ]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              {latestRapm && (
                <p className="text-sm text-zinc-400 pt-1">
                  RAPM{" "}
                  <span className="font-mono font-semibold text-emerald-400">
                    {latestRapm.rapm?.toFixed(2) ?? "—"}
                  </span>{" "}
                  <span className="text-xs text-zinc-600">
                    (O {latestRapm.orapm?.toFixed(2) ?? "—"} / D{" "}
                    {latestRapm.drapm?.toFixed(2) ?? "—"})
                  </span>
                </p>
              )}
            </div>
          </div>
        </section>
      ) : null}

      {/* Props projections for the player's most recent game */}
      {player && latestGame && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-zinc-300">
            Projected props
            <span className="text-xs text-zinc-600 font-normal">
              {" "}
              ·{" "}
              {player.recent_games[0].team_abbreviation ?? "—"}{" "}
              {player.recent_games[0].is_home ? "vs" : "@"}{" "}
              {player.recent_games[0].opponent_abbreviation ?? "—"},{" "}
              {player.recent_games[0].game_date}
            </span>
          </h2>
          <PropsBoard playerId={playerId} gameId={latestGame} />
        </section>
      )}

      {/* Stat trajectory + season averages (players with ingested games) */}
      {player && player.recent_games.length > 0 && (
        <>
          <PlayerTrajectory playerId={playerId} />
          <SeasonAveragesTable playerId={playerId} />
        </>
      )}

      {/* Players from the historical index with no data in the loaded seasons */}
      {player && player.recent_games.length === 0 && (
        <section className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-4">
          <p className="text-sm text-zinc-400">
            No games for {player.full_name} in the loaded seasons — projections and game
            logs appear once a season they played in has been ingested.
          </p>
        </section>
      )}

      {/* Recent game logs */}
      {player && player.recent_games.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-semibold text-zinc-300">Recent games</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
                <th className="py-2 pr-2 font-medium">Date</th>
                <th className="py-2 px-2 font-medium">Matchup</th>
                <th className="py-2 px-2 font-medium text-right">MIN</th>
                <th className="py-2 px-2 font-medium text-right">PTS</th>
                <th className="py-2 px-2 font-medium text-right">REB</th>
                <th className="py-2 px-2 font-medium text-right">AST</th>
                <th className="py-2 pl-2 font-medium text-right">3PM</th>
              </tr>
            </thead>
            <tbody className="font-mono tabular-nums">
              {player.recent_games.map((g) => (
                <tr
                  key={g.game_id}
                  className="border-b border-zinc-900 hover:bg-zinc-900/50"
                >
                  <td className="py-2 pr-2 text-zinc-400 font-sans">
                    <Link href={`/games/${g.game_id}`} className="hover:underline">
                      {g.game_date}
                    </Link>
                  </td>
                  <td className="py-2 px-2 font-sans whitespace-nowrap">
                    <span
                      aria-label={g.won == null ? undefined : g.won ? "won" : "lost"}
                      className={
                        g.won == null
                          ? "text-zinc-600"
                          : g.won
                            ? "text-emerald-400"
                            : "text-rose-400"
                      }
                    >
                      {g.won == null ? "·" : g.won ? "▸" : "◂"}
                    </span>{" "}
                    <span className="text-zinc-300">
                      {g.team_abbreviation ?? "—"} {g.is_home ? "vs" : "@"}{" "}
                      {g.opponent_abbreviation ?? "—"}
                    </span>
                  </td>
                  <td className="py-2 px-2 text-right text-zinc-500">
                    {g.min == null ? "—" : g.min.toFixed(0)}
                  </td>
                  <td className="py-2 px-2 text-right">{g.pts}</td>
                  <td className="py-2 px-2 text-right">{g.reb}</td>
                  <td className="py-2 px-2 text-right">{g.ast}</td>
                  <td className="py-2 pl-2 text-right">{g.fg3m}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </main>
  );
}
