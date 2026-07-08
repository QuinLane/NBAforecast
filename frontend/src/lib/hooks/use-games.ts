import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../api-client/client";

export type GamesParams = {
  game_date?: string;
  season?: string;
  team?: number;
  page?: number;
  page_size?: number;
};

export const gamesQueryKey = (params?: GamesParams) =>
  ["games", params ?? {}] as const;
export const gameQueryKey = (gameId: string) => ["games", gameId] as const;
export const gameBoxScoreQueryKey = (gameId: string) =>
  ["games", gameId, "boxscore"] as const;
export const gameWinProbabilityQueryKey = (gameId: string) =>
  ["games", gameId, "win-probability"] as const;

export function useGames(params?: GamesParams) {
  return useQuery({
    queryKey: gamesQueryKey(params),
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/games", {
        params: { query: params },
      });
      if (error) throw new Error("Failed to fetch games");
      return data;
    },
  });
}

export function useGame(gameId: string) {
  return useQuery({
    queryKey: gameQueryKey(gameId),
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/games/{game_id}", {
        params: { path: { game_id: gameId } },
      });
      if (error) throw new Error(`Game ${gameId} not found`);
      return data;
    },
  });
}

/** In-game win-probability timeline. 404s until played; 503 until a champion is loaded. */
export function useGameWinProbability(gameId: string, enabled = true) {
  return useQuery({
    queryKey: gameWinProbabilityQueryKey(gameId),
    enabled: enabled && gameId !== "",
    retry: false,
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/api/v1/games/{game_id}/win-probability",
        { params: { path: { game_id: gameId } } },
      );
      if (error) throw new Error("Win-probability timeline unavailable");
      return data;
    },
  });
}

/** Box score (team totals + player lines). 404s until the game has been played/ingested. */
export function useGameBoxScore(gameId: string, enabled = true) {
  return useQuery({
    queryKey: gameBoxScoreQueryKey(gameId),
    enabled: enabled && gameId !== "",
    retry: false, // a 404 (game not played yet) is expected, not worth retrying
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/api/v1/games/{game_id}/boxscore",
        { params: { path: { game_id: gameId } } },
      );
      if (error) throw new Error("Box score unavailable");
      return data;
    },
  });
}
