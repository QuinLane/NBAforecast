"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { PlayerHeadshot, TeamLogo } from "@/components/nba-images";
import { usePlayerSearch, useTeams } from "@/lib/hooks";

const MAX_TEAMS = 4;

export function HeaderSearch() {
  const router = useRouter();
  const [raw, setRaw] = useState("");
  const [q, setQ] = useState(""); // debounced
  const [open, setOpen] = useState(false);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounce the query by 200ms.
  useEffect(() => {
    const t = setTimeout(() => setQ(raw), 200);
    return () => clearTimeout(t);
  }, [raw]);

  const playersQ = usePlayerSearch(q);
  const teamsQ = useTeams({ page_size: 40 });

  const needle = q.trim().toLowerCase();
  const players = needle.length >= 2 ? (playersQ.data?.items ?? []) : [];
  const teams =
    needle.length >= 2
      ? (teamsQ.data?.items ?? [])
          .filter(
            (t) =>
              t.full_name.toLowerCase().includes(needle) ||
              t.abbreviation.toLowerCase().includes(needle),
          )
          .slice(0, MAX_TEAMS)
      : [];

  const hasResults = players.length > 0 || teams.length > 0;
  const showDropdown = open && needle.length >= 2;

  function go(href: string) {
    setRaw("");
    setQ("");
    setOpen(false);
    router.push(href);
  }

  return (
    <div className="relative">
      <input
        type="search"
        value={raw}
        onChange={(e) => {
          setRaw(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          blurTimer.current = setTimeout(() => setOpen(false), 150);
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
        }}
        placeholder="Search players, teams…"
        aria-label="Search players and teams"
        className="w-40 sm:w-52 rounded-md border border-border bg-background/60 px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-brand/60"
      />

      {showDropdown && (
        <div
          className="absolute right-0 mt-1 w-72 max-h-96 overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-950/95 backdrop-blur p-1 shadow-xl z-50"
          onMouseDown={(e) => {
            // Keep focus so onBlur's close doesn't fire before the click navigates.
            e.preventDefault();
            if (blurTimer.current) clearTimeout(blurTimer.current);
          }}
        >
          {playersQ.isPending && players.length === 0 && teams.length === 0 ? (
            <p className="px-3 py-2 text-xs text-zinc-500">Searching…</p>
          ) : !hasResults ? (
            <p className="px-3 py-2 text-xs text-zinc-500">No matches.</p>
          ) : (
            <>
              {players.length > 0 && (
                <div className="mb-1">
                  <p className="px-3 py-1 text-[11px] uppercase tracking-wide text-zinc-600">
                    Players
                  </p>
                  {players.map((p) => (
                    <button
                      key={p.player_id}
                      onClick={() => go(`/players/${p.player_id}`)}
                      className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-sm text-zinc-200 hover:bg-zinc-800/70"
                    >
                      <PlayerHeadshot playerId={p.player_id} name={p.full_name} className="size-6" />
                      <span className="truncate">{p.full_name}</span>
                      <span className="ml-auto text-xs text-zinc-500">{p.position ?? ""}</span>
                    </button>
                  ))}
                </div>
              )}
              {teams.length > 0 && (
                <div>
                  <p className="px-3 py-1 text-[11px] uppercase tracking-wide text-zinc-600">
                    Teams
                  </p>
                  {teams.map((t) => (
                    <button
                      key={t.team_id}
                      onClick={() => go(`/teams/${t.team_id}`)}
                      className="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-left text-sm text-zinc-200 hover:bg-zinc-800/70"
                    >
                      <TeamLogo teamId={t.team_id} name={t.full_name} className="size-6" />
                      <span className="truncate">{t.full_name}</span>
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
