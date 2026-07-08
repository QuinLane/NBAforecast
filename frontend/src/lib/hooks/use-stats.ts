import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../api-client/client";

export type LeaderboardStat = "pts" | "reb" | "ast" | "stl" | "blk" | "fg3m";

export type LeaderboardParams = {
  stat: LeaderboardStat;
  season?: string;
  page?: number;
  page_size?: number;
};

export const statsLeaderboardQueryKey = (params: LeaderboardParams) =>
  ["stats", "leaderboards", params] as const;

/** Per-game average leaderboard for a counting stat (PTS/REB/AST/STL/BLK/3PM). */
export function useStatsLeaderboard(params: LeaderboardParams) {
  return useQuery({
    queryKey: statsLeaderboardQueryKey(params),
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/stats/leaderboards", {
        params: { query: params },
      });
      if (error) throw new Error("Failed to fetch leaderboard");
      return data;
    },
  });
}
