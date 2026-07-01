import Link from "next/link";

const SECTIONS: { href: string; title: string; blurb: string }[] = [
  { href: "/games", title: "Games", blurb: "Schedule, results, and explained win probability." },
  { href: "/rapm", title: "RAPM", blurb: "Regularized Adjusted Plus-Minus leaderboard." },
  { href: "/players", title: "Players", blurb: "Profiles, game logs, and projected props." },
  { href: "/teams", title: "Teams", blurb: "Team directory and profiles." },
];

export default function Home() {
  return (
    <main className="mx-auto flex max-w-2xl flex-1 flex-col gap-8 px-4 py-12">
      <div className="space-y-3">
        <h1 className="text-4xl font-extrabold tracking-tight">
          NBA<span className="text-brand">forecast</span>
        </h1>
        <p className="max-w-md text-muted-foreground">
          Explainable NBA predictions — calibrated win probability, player props,
          and RAPM, every projection broken down by the factors driving it.
        </p>
      </div>

      <nav className="grid grid-cols-2 gap-3" aria-label="Sections">
        {SECTIONS.map((section) => (
          <Link
            key={section.href}
            href={section.href}
            className="group rounded-xl border border-border bg-card/60 p-4 transition-colors hover:border-brand/50"
          >
            <div className="font-bold transition-colors group-hover:text-brand">
              {section.title}
            </div>
            <div className="mt-0.5 text-sm text-muted-foreground">{section.blurb}</div>
          </Link>
        ))}
      </nav>
    </main>
  );
}
