"use client";

import Link from "next/link";
import { TeamLogo } from "@/components/nba-images";
import { useGameBoxScore } from "@/lib/hooks";
import type { components } from "@/lib/api-client/schema";

type BoxScoreTeam = components["schemas"]["BoxScoreTeam"];
type BoxScorePlayerLine = components["schemas"]["BoxScorePlayerLine"];

function plusMinus(value: number | null): string {
  if (value == null) return "—";
  return value > 0 ? `+${value}` : `${value}`;
}

function TeamBox({ side }: { side: BoxScoreTeam }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <TeamLogo teamId={side.team.team_id} name={side.team.full_name} className="size-6" />
        <span className="font-semibold text-sm text-zinc-200">{side.team.full_name}</span>
        <span className="text-xs text-zinc-500">
          {side.pts} pts · {side.reb} reb · {side.ast} ast
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-sm">
          <thead>
            <tr className="text-left text-xs text-zinc-500 border-b border-zinc-800">
              <th className="py-1.5 pr-2 font-medium">Player</th>
              <th className="py-1.5 px-2 font-medium text-right">MIN</th>
              <th className="py-1.5 px-2 font-medium text-right">PTS</th>
              <th className="py-1.5 px-2 font-medium text-right">REB</th>
              <th className="py-1.5 px-2 font-medium text-right">AST</th>
              <th className="py-1.5 px-2 font-medium text-right">STL</th>
              <th className="py-1.5 px-2 font-medium text-right">BLK</th>
              <th className="py-1.5 px-2 font-medium text-right">TOV</th>
              <th className="py-1.5 px-2 font-medium text-right">FG</th>
              <th className="py-1.5 px-2 font-medium text-right">3P</th>
              <th className="py-1.5 px-2 font-medium text-right">FT</th>
              <th className="py-1.5 pl-2 font-medium text-right">+/-</th>
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {side.players.map((p: BoxScorePlayerLine) => (
              <tr key={p.player_id} className="border-b border-zinc-900 hover:bg-zinc-900/50">
                <td className="py-1.5 pr-2 font-sans whitespace-nowrap">
                  <Link href={`/players/${p.player_id}`} className="hover:underline text-zinc-300">
                    {p.full_name ?? `#${p.player_id}`}
                  </Link>
                  {p.started && <span className="text-emerald-500/70 ml-1">•</span>}
                </td>
                <td className="py-1.5 px-2 text-right text-zinc-500">
                  {p.min == null ? "—" : p.min.toFixed(0)}
                </td>
                <td className="py-1.5 px-2 text-right text-zinc-200 font-semibold">{p.pts}</td>
                <td className="py-1.5 px-2 text-right">{p.reb}</td>
                <td className="py-1.5 px-2 text-right">{p.ast}</td>
                <td className="py-1.5 px-2 text-right text-zinc-400">{p.stl}</td>
                <td className="py-1.5 px-2 text-right text-zinc-400">{p.blk}</td>
                <td className="py-1.5 px-2 text-right text-zinc-400">{p.tov}</td>
                <td className="py-1.5 px-2 text-right text-zinc-400">
                  {p.fgm}-{p.fga}
                </td>
                <td className="py-1.5 px-2 text-right text-zinc-400">
                  {p.fg3m}-{p.fg3a}
                </td>
                <td className="py-1.5 px-2 text-right text-zinc-400">
                  {p.ftm}-{p.fta}
                </td>
                <td className="py-1.5 pl-2 text-right text-zinc-500">
                  {plusMinus(p.plus_minus)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Full box score for a played game. Renders nothing until the box score is available. */
export function GameBoxScore({ gameId, enabled }: { gameId: string; enabled: boolean }) {
  const { data, isPending, isError } = useGameBoxScore(gameId, enabled);

  if (!enabled || isError) return null; // not played yet / 404 — nothing to show
  if (isPending) {
    return <div className="h-40 rounded-xl bg-zinc-800/40 animate-pulse" />;
  }
  if (!data) return null;

  return (
    <section className="space-y-4">
      <h2 className="text-sm font-semibold text-zinc-300">Box score</h2>
      <TeamBox side={data.away} />
      <TeamBox side={data.home} />
      <p className="text-xs text-zinc-600">
        <span className="text-emerald-500/70">•</span> starter · FG/3P/FT shown as made–attempted.
      </p>
    </section>
  );
}
