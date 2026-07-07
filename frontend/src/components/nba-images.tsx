"use client";

import Image from "next/image";
import { useState } from "react";

// The NBA's public CDN serves headshots and logos keyed by the same stats ids we
// store, so no mapping table is needed. Hotlinked unoptimized: assets are already
// small (260x190 PNG / SVG) and the optimizer would just proxy them. Non-commercial
// hotlinking of these assets is standard practice; a licensed image provider would
// be required if this project ever became commercial.
function headshotUrl(playerId: number): string {
  return `https://cdn.nba.com/headshots/nba/latest/260x190/${playerId}.png`;
}

function logoUrl(teamId: number): string {
  return `https://cdn.nba.com/logos/nba/${teamId}/global/L/logo.svg`;
}

/** Circular player headshot that falls back to initials when the CDN has no photo. */
export function PlayerHeadshot({
  playerId,
  name,
  className = "size-9",
}: {
  playerId: number;
  name: string;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);
  const initials = name
    .split(/\s+/)
    .map((word) => word[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <span
      className={`relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-zinc-800 ${className}`}
    >
      {failed ? (
        <span className="text-[11px] font-semibold text-zinc-500">
          {initials || "?"}
        </span>
      ) : (
        <Image
          src={headshotUrl(playerId)}
          alt={name}
          fill
          unoptimized
          sizes="96px"
          className="object-cover object-top"
          onError={() => setFailed(true)}
        />
      )}
    </span>
  );
}

/** Team logo that degrades to an empty spacer (abbreviations are always shown beside it). */
export function TeamLogo({
  teamId,
  name,
  className = "size-8",
}: {
  teamId: number;
  name: string;
  className?: string;
}) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return <span aria-hidden className={`inline-block shrink-0 ${className}`} />;
  }
  return (
    <Image
      src={logoUrl(teamId)}
      alt={`${name} logo`}
      width={48}
      height={48}
      unoptimized
      className={`shrink-0 object-contain ${className}`}
      onError={() => setFailed(true)}
    />
  );
}
