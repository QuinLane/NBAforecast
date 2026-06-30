import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../api-client/client";

export const gamePredictionQueryKey = (gameId: string) =>
  ["games", gameId, "prediction"] as const;
export const gamePredictionFullQueryKey = (gameId: string) =>
  ["games", gameId, "prediction", "full"] as const;

export function useGamePrediction(gameId: string) {
  return useQuery({
    queryKey: gamePredictionQueryKey(gameId),
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/api/v1/games/{game_id}/prediction",
        { params: { path: { game_id: gameId } } },
      );
      if (error) throw new Error(`Prediction for game ${gameId} not found`);
      return data;
    },
  });
}

export function useGamePredictionFullExplanation(gameId: string) {
  return useQuery({
    queryKey: gamePredictionFullQueryKey(gameId),
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/api/v1/games/{game_id}/prediction/full-explanation",
        { params: { path: { game_id: gameId } } },
      );
      if (error)
        throw new Error(`Full explanation for game ${gameId} not found`);
      return data;
    },
    enabled: !!gameId,
  });
}
