"use client";

import { use } from "react";
import Link from "next/link";
import { TeamLogo } from "@/components/nba-images";
import { useTeam } from "@/lib/hooks";

export default function TeamDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const teamId = Number(id);
  const { data: team, isPending, isError } = useTeam(teamId);

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
      ) : team ? (
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
          <div className="flex items-center gap-4">
            <TeamLogo
              teamId={team.team_id}
              name={team.full_name}
              className="size-14"
            />
            <div className="space-y-1">
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-sm text-zinc-500">
                  {team.abbreviation}
                </span>
                <h1 className="text-2xl font-bold tracking-tight">{team.full_name}</h1>
              </div>
              <p className="text-sm text-zinc-500">
                {[team.conference, team.division].filter(Boolean).join(" · ") ||
                  "Conference/division not available"}
              </p>
            </div>
          </div>
        </section>
      ) : null}
    </main>
  );
}
