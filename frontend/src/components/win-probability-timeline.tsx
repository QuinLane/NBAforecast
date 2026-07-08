"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import { useGameWinProbability } from "@/lib/hooks";

const SPEEDS = [0.5, 1, 2, 4] as const;
const BASE_MS_PER_POINT = 220; // playback cadence at 1x

// Map a home win probability (0–1) to a font size for each team's name: the favored team grows,
// the other shrinks — the NBA 2K "sim" effect. Even at a tossup both read clearly.
function nameSize(prob: number): string {
  return `${(1.05 + Math.max(0, prob - 0.5) * 2.4).toFixed(2)}rem`;
}

export function WinProbabilityTimeline({
  gameId,
  enabled,
}: {
  gameId: string;
  enabled: boolean;
}) {
  const { data, isPending, isError } = useGameWinProbability(gameId, enabled);
  const points = useMemo(() => data?.points ?? [], [data]);

  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(1);

  // Advance during playback; stop at the final moment.
  useEffect(() => {
    if (!playing || points.length === 0) return;
    const id = setInterval(() => {
      setIndex((i) => {
        if (i >= points.length - 1) {
          setPlaying(false);
          return i;
        }
        return i + 1;
      });
    }, BASE_MS_PER_POINT / speed);
    return () => clearInterval(id);
  }, [playing, speed, points.length]);

  const chartData = useMemo(
    () => points.map((p, i) => ({ i, wp: p.home_win_prob * 100 })),
    [points],
  );

  if (!enabled || isError) return null;
  if (isPending) {
    return <div className="h-72 rounded-xl bg-zinc-800/40 animate-pulse" />;
  }
  if (!data || points.length === 0) return null;

  const current = points[Math.min(index, points.length - 1)];
  const homeProb = current.home_win_prob;
  const home = data.home_team;
  const away = data.away_team;
  const homeFavored = homeProb >= 0.5;
  const atEnd = index >= points.length - 1;

  const togglePlay = () => {
    if (atEnd) setIndex(0); // restart from tip-off
    setPlaying((p) => !p);
  };

  return (
    <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
      <h2 className="text-sm font-semibold text-zinc-300">Win probability</h2>

      {/* 2K-style scoreboard: the favored team's name grows with its win probability */}
      <div className="flex items-end justify-between gap-3">
        <div className="flex-1 text-left">
          <div
            className={`font-bold leading-none transition-all duration-200 ${
              homeFavored ? "text-emerald-400" : "text-zinc-500"
            }`}
            style={{ fontSize: nameSize(homeProb) }}
          >
            {home.abbreviation}
          </div>
          <div className="text-xs text-zinc-500 mt-1">{home.full_name}</div>
        </div>
        <div className="text-center shrink-0">
          <div className="font-mono text-2xl text-zinc-100">
            {current.home_score}–{current.away_score}
          </div>
          <div className="text-xs text-zinc-500">
            {current.period > 4 ? `OT${current.period - 4}` : `Q${current.period}`} · {current.clock}
          </div>
        </div>
        <div className="flex-1 text-right">
          <div
            className={`font-bold leading-none transition-all duration-200 ${
              !homeFavored ? "text-emerald-400" : "text-zinc-500"
            }`}
            style={{ fontSize: nameSize(1 - homeProb) }}
          >
            {away.abbreviation}
          </div>
          <div className="text-xs text-zinc-500 mt-1">{away.full_name}</div>
        </div>
      </div>

      <div className="text-center text-sm text-zinc-400">
        <span className="font-mono font-semibold text-emerald-400">
          {(homeProb * 100).toFixed(1)}%
        </span>{" "}
        {home.abbreviation} win probability
      </div>

      {/* Win-probability curve with a marker at the current moment */}
      <div className="h-40">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 6, right: 6, bottom: 0, left: -24 }}>
            <defs>
              <linearGradient id="wpFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#34d399" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#34d399" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis dataKey="i" type="number" domain={[0, points.length - 1]} hide />
            <YAxis domain={[0, 100]} tick={{ fill: "#71717a", fontSize: 11 }} width={34} />
            <ReferenceLine y={50} stroke="#52525b" strokeDasharray="3 3" />
            <ReferenceLine x={index} stroke="#e4e4e7" strokeWidth={1} />
            <Area
              type="monotone"
              dataKey="wp"
              stroke="#34d399"
              strokeWidth={2}
              fill="url(#wpFill)"
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Playback controls */}
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={togglePlay}
          className="rounded-full bg-zinc-200 text-zinc-900 text-sm font-medium px-4 py-1 hover:bg-white transition-colors"
        >
          {playing ? "❚❚ Pause" : atEnd ? "↻ Replay" : "▶ Play"}
        </button>
        <div className="flex gap-1" role="group" aria-label="Playback speed">
          {SPEEDS.map((s) => (
            <button
              key={s}
              onClick={() => setSpeed(s)}
              aria-pressed={speed === s}
              className={`text-xs px-2 py-1 rounded-full transition-colors ${
                speed === s
                  ? "bg-emerald-500/20 text-emerald-300"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
            >
              {s}×
            </button>
          ))}
        </div>
        <input
          type="range"
          min={0}
          max={points.length - 1}
          value={index}
          onChange={(e) => {
            setPlaying(false);
            setIndex(Number(e.target.value));
          }}
          aria-label="Scrub timeline"
          className="flex-1 min-w-[8rem] accent-emerald-400"
        />
      </div>

      {/* The model's "thinking" at this moment */}
      <div className="space-y-1.5 border-t border-zinc-800 pt-3">
        <div className="text-xs text-zinc-500">What the model sees now</div>
        {current.drivers.map((d) => (
          <div key={d.label} className="flex items-center gap-2 text-sm">
            <span className="w-28 shrink-0 text-zinc-400">{d.label}</span>
            <span className="w-16 shrink-0 font-mono text-zinc-300">{d.value}</span>
            <span
              className={`font-mono text-xs ${
                d.direction === "up" ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {d.direction === "up" ? "▲" : "▼"} {(d.contribution * 100 >= 0 ? "+" : "")}
              {(d.contribution * 100).toFixed(1)}%
            </span>
          </div>
        ))}
        {current.description && (
          <p className="text-xs text-zinc-500 pt-1 italic">{current.description}</p>
        )}
      </div>

      <p className="text-xs text-zinc-600">
        Win probability from the in-game model, replayed through the game&apos;s play-by-play — it
        updates as the score and clock change, built only from the game state at each moment.
      </p>
    </section>
  );
}
