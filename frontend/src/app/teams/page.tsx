"use client";

import Link from "next/link";
import { TeamLogo } from "@/components/nba-images";
import { useTeams } from "@/lib/hooks";

export default function TeamsPage() {
  const { data, isPending, isError } = useTeams({ page_size: 40 });

  return (
    <main className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Teams</h1>

      {isPending && (
        <div className="grid grid-cols-2 gap-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-14 rounded-lg bg-zinc-800/50 animate-pulse" />
          ))}
        </div>
      )}

      {isError && (
        <p className="text-zinc-400">Could not load teams. Is the backend running?</p>
      )}

      {data && (
        <ul className="grid grid-cols-2 gap-2" aria-label="Teams list">
          {data.items.map((team) => (
            <li key={team.team_id}>
              <Link
                href={`/teams/${team.team_id}`}
                className="flex items-center gap-3 px-4 py-3 rounded-lg border border-zinc-800 bg-zinc-900/50 hover:bg-zinc-800/60 transition-colors"
              >
                <TeamLogo teamId={team.team_id} name={team.full_name} />
                <span className="font-mono text-xs text-zinc-500 w-10">
                  {team.abbreviation}
                </span>
                <span className="font-medium text-sm truncate">{team.full_name}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
