import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../api-client/client";

export type PlayersParams = {
  active?: boolean;
  with_stats?: boolean;
  search?: string;
  page?: number;
  page_size?: number;
};

export const playersQueryKey = (params?: PlayersParams) =>
  ["players", params ?? {}] as const;
export const playerQueryKey = (playerId: number) =>
  ["players", playerId] as const;
export const playerPropsQueryKey = (playerId: number, gameId: string) =>
  ["players", playerId, "props", gameId] as const;
export const playerStatsQueryKey = (playerId: number) =>
  ["players", playerId, "stats"] as const;
export const playerShotsQueryKey = (playerId: number, season?: string) =>
  ["players", playerId, "shots", season ?? "all"] as const;

export function usePlayers(params?: PlayersParams) {
  return useQuery({
    queryKey: playersQueryKey(params),
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/players", {
        params: { query: params },
      });
      if (error) throw new Error("Failed to fetch players");
      return data;
    },
  });
}

export function usePlayer(playerId: number) {
  return useQuery({
    queryKey: playerQueryKey(playerId),
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/api/v1/players/{player_id}",
        { params: { path: { player_id: playerId } } },
      );
      if (error) throw new Error(`Player ${playerId} not found`);
      return data;
    },
  });
}

/** Name search over players-with-stats, gated on a 2+ char query. Powers the header search. */
export function usePlayerSearch(query: string, limit = 6) {
  const q = query.trim();
  return useQuery({
    queryKey: ["players", "search", q, limit] as const,
    enabled: q.length >= 2,
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/players", {
        params: { query: { search: q, with_stats: true, page_size: limit } },
      });
      if (error) throw new Error("Player search failed");
      return data;
    },
  });
}

/** Per-game stat series + season averages for the trajectory chart and season tables. */
export function usePlayerStats(playerId: number) {
  return useQuery({
    queryKey: playerStatsQueryKey(playerId),
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/api/v1/players/{player_id}/stats",
        { params: { path: { player_id: playerId } } },
      );
      if (error) throw new Error("Failed to fetch player stats");
      return data;
    },
  });
}

/** Field-goal attempts for the shot chart (optionally one season). */
export function usePlayerShots(playerId: number, season?: string) {
  return useQuery({
    queryKey: playerShotsQueryKey(playerId, season),
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/api/v1/players/{player_id}/shots",
        {
          params: {
            path: { player_id: playerId },
            query: season ? { season } : undefined,
          },
        },
      );
      if (error) throw new Error("Failed to fetch shots");
      return data;
    },
  });
}

/** Props projections for a player in a given game. `enabled` gates on having a game id. */
export function usePlayerProps(playerId: number, gameId: string) {
  return useQuery({
    queryKey: playerPropsQueryKey(playerId, gameId),
    enabled: gameId !== "",
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/api/v1/players/{player_id}/props",
        {
          params: {
            path: { player_id: playerId },
            query: { game_id: gameId },
          },
        },
      );
      if (error) throw new Error("Props projections unavailable");
      return data;
    },
  });
}
