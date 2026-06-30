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
