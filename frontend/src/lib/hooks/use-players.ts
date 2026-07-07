import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../api-client/client";

export type PlayersParams = {
  active?: boolean;
  with_stats?: boolean;
  page?: number;
  page_size?: number;
};

export const playersQueryKey = (params?: PlayersParams) =>
  ["players", params ?? {}] as const;
export const playerQueryKey = (playerId: number) =>
  ["players", playerId] as const;
export const playerPropsQueryKey = (playerId: number, gameId: string) =>
  ["players", playerId, "props", gameId] as const;

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
