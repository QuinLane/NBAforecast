"use client";

import { useChampions } from "@/lib/hooks";

/**
 * A compact provenance line for the champion behind a prediction: model version, the season it
 * was trained through, and the feature version. Renders nothing until a champion is available.
 * `featuresAsOf` describes when the features are snapshotted (e.g. "tip-off" for pre-game heads).
 */
export function ModelProvenance({
  head,
  featuresAsOf,
}: {
  head: string;
  featuresAsOf?: string;
}) {
  const { data } = useChampions();
  const champ = data?.find((c) => c.head === head);
  if (!champ) return null;

  return (
    <p className="text-[11px] text-zinc-600">
      Model <span className="font-mono text-zinc-500">{head}</span> ·{" "}
      <span className="font-mono">{champ.version}</span>
      {champ.trained_through_season && <> · trained through {champ.trained_through_season}</>}
      {featuresAsOf ? (
        <> · features as of {featuresAsOf}</>
      ) : (
        champ.feature_version && <> · features {champ.feature_version}</>
      )}
    </p>
  );
}
