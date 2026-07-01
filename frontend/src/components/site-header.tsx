"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/games", label: "Games" },
  { href: "/rapm", label: "RAPM" },
  { href: "/players", label: "Players" },
  { href: "/teams", label: "Teams" },
];

/** Global app shell header (frontend-design.md §5) — wordmark + primary nav, active-route aware. */
export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur">
      <nav className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3">
        <Link href="/" className="flex items-center gap-2 font-extrabold tracking-tight">
          <span className="size-2.5 rounded-full bg-brand shadow-[0_0_14px_2px] shadow-brand/70" />
          <span className="text-sm">NBAFORECAST</span>
        </Link>
        <div className="flex items-center gap-5 text-sm font-semibold">
          {NAV.map((item) => {
            const active =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={
                  active
                    ? "text-foreground"
                    : "text-muted-foreground transition-colors hover:text-foreground"
                }
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      </nav>
    </header>
  );
}
