import Link from "next/link";

const SECTIONS: { href: string; title: string; blurb: string }[] = [
  { href: "/games", title: "Games", blurb: "Schedule, results, and explained win probability." },
  { href: "/rapm", title: "RAPM", blurb: "Regularized Adjusted Plus-Minus leaderboard." },
  { href: "/players", title: "Players", blurb: "Profiles, game logs, and projected props." },
  { href: "/teams", title: "Teams", blurb: "Team directory and profiles." },
];

export default function Home() {
  return (
    <main className="mx-auto flex max-w-2xl flex-1 flex-col gap-6 p-8">
      <div className="space-y-2 pt-8">
        <h1 className="text-4xl font-bold tracking-tight">NBAforecast</h1>
        <p className="text-muted-foreground max-w-md">
          Explainable NBA predictions — calibrated win probability, player props,
          and RAPM with SHAP-driven breakdowns.
        </p>
      </div>

      <nav className="grid grid-cols-2 gap-3" aria-label="Sections">
        {SECTIONS.map((section) => (
          <Link
            key={section.href}
            href={section.href}
            className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 transition-colors hover:bg-zinc-800/60"
          >
            <div className="font-semibold">{section.title}</div>
            <div className="text-sm text-zinc-500">{section.blurb}</div>
          </Link>
        ))}
      </nav>
    </main>
  );
}
