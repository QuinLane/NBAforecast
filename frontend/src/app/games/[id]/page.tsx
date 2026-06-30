"use client";

import { use, useState } from "react";
import Link from "next/link";
import { PredictionExplainer } from "@/components/prediction-explainer";
import {
  useGame,
  useGamePrediction,
  useGamePredictionFullExplanation,
} from "@/lib/hooks";

export default function GameDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [wantFull, setWantFull] = useState(false);

  const gameQ = useGame(id);
  const predQ = useGamePrediction(id);
  const fullQ = useGamePredictionFullExplanation(wantFull ? id : "");

  const game = gameQ.data;
  const prediction = predQ.data;
  const explanation = wantFull && fullQ.data ? fullQ.data.explanation : prediction?.explanation;

  if (gameQ.isError) {
    return (
      <main className="p-8 text-center text-zinc-400">
        Game not found.{" "}
        <Link href="/games" className="underline">
          Back to games
        </Link>
      </main>
    );
  }

  return (
    <main className="max-w-2xl mx-auto px-4 py-8 space-y-6">
      <Link
        href="/games"
        className="text-sm text-zinc-500 hover:text-zinc-300 transition-colors"
      >
        ← All games
      </Link>

      {/* Game header */}
      {gameQ.isPending ? (
        <div className="h-24 rounded-xl bg-zinc-800/50 animate-pulse" />
      ) : game ? (
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-5">
          <div className="flex items-center justify-between gap-4">
            <div className="text-center flex-1">
              <div className="text-2xl font-bold">{game.home_team.abbreviation}</div>
              <div className="text-xs text-zinc-500">{game.home_team.full_name}</div>
              {game.home_score != null && (
                <div className="text-3xl font-mono mt-1">{game.home_score}</div>
              )}
            </div>
            <div className="text-center">
              <div className="text-zinc-500 text-sm">vs</div>
              <div className="text-xs text-zinc-600 mt-1">{game.game_date}</div>
              <div
                className={`text-xs mt-1 px-2 py-0.5 rounded-full ${
                  game.status === "Final"
                    ? "bg-zinc-700 text-zinc-400"
                    : "bg-emerald-900/40 text-emerald-400"
                }`}
              >
                {game.status}
              </div>
            </div>
            <div className="text-center flex-1">
              <div className="text-2xl font-bold">{game.away_team.abbreviation}</div>
              <div className="text-xs text-zinc-500">{game.away_team.full_name}</div>
              {game.away_score != null && (
                <div className="text-3xl font-mono mt-1">{game.away_score}</div>
              )}
            </div>
          </div>
        </section>
      ) : null}

      {/* Win probability headline */}
      {predQ.isPending ? (
        <div className="h-8 w-48 rounded bg-zinc-800/50 animate-pulse" />
      ) : prediction ? (
        <div className="flex items-baseline gap-2">
          <span className="text-4xl font-bold text-emerald-400">
            {(prediction.win_prob * 100).toFixed(1)}%
          </span>
          <span className="text-zinc-500 text-sm">
            home win probability
          </span>
        </div>
      ) : predQ.isError ? (
        <p className="text-zinc-500 text-sm">Prediction unavailable.</p>
      ) : null}

      {/* PredictionExplainer */}
      {explanation ? (
        <PredictionExplainer
          explanation={explanation}
          onRequestFull={() => setWantFull(true)}
          fullLoading={wantFull && fullQ.isPending}
        />
      ) : predQ.isPending ? (
        <div className="h-64 rounded-xl bg-zinc-800/50 animate-pulse" />
      ) : null}
    </main>
  );
}
