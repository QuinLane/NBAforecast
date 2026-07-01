import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../api-client/client";

export type TeamsParams = { page?: number; page_size?: number };

export const teamsQueryKey = (params?: TeamsParams) =>
  ["teams", params ?? {}] as const;
export const teamQueryKey = (teamId: number) => ["teams", teamId] as const;

export function useTeams(params?: TeamsParams) {
  return useQuery({
    queryKey: teamsQueryKey(params),
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/teams", {
        params: { query: params },
      });
      if (error) throw new Error("Failed to fetch teams");
      return data;
    },
  });
}

export function useTeam(teamId: number) {
  return useQuery({
    queryKey: teamQueryKey(teamId),
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/teams/{team_id}", {
        params: { path: { team_id: teamId } },
      });
      if (error) throw new Error(`Team ${teamId} not found`);
      return data;
    },
  });
}
