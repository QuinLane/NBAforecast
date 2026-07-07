import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../api-client/client";

export type RapmSort = "rapm" | "orapm" | "drapm" | "possessions";

export type RapmParams = {
  window?: number;
  sort?: RapmSort;
  as_of?: string;
  min_poss?: number;
  page?: number;
  page_size?: number;
};

export const rapmQueryKey = (params?: RapmParams) =>
  ["rapm", params ?? {}] as const;
export const playerRapmQueryKey = (playerId: number) =>
  ["players", playerId, "rapm"] as const;

export function useRapmLeaderboard(params?: RapmParams) {
  return useQuery({
    queryKey: rapmQueryKey(params),
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/rapm", {
        params: { query: params },
      });
      if (error) throw new Error("Failed to fetch RAPM leaderboard");
      return data;
    },
  });
}

export function usePlayerRapm(playerId: number) {
  return useQuery({
    queryKey: playerRapmQueryKey(playerId),
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/api/v1/players/{player_id}/rapm",
        { params: { path: { player_id: playerId } } },
      );
      if (error) throw new Error("Failed to fetch player RAPM history");
      return data;
    },
  });
}
