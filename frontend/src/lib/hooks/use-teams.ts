import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../api-client/client";

export type TeamsParams = { page?: number; page_size?: number };

export const teamsQueryKey = (params?: TeamsParams) =>
  ["teams", params ?? {}] as const;
export const teamQueryKey = (teamId: number) => ["teams", teamId] as const;
export const teamProfileQueryKey = (teamId: number) =>
  ["teams", teamId, "profile"] as const;
export const headToHeadQueryKey = (teamId: number, opponentId: number) =>
  ["teams", teamId, "head-to-head", opponentId] as const;

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

/** Team record + roster + recent games for the team page. */
export function useTeamProfile(teamId: number) {
  return useQuery({
    queryKey: teamProfileQueryKey(teamId),
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/api/v1/teams/{team_id}/profile",
        { params: { path: { team_id: teamId } } },
      );
      if (error) throw new Error(`Team ${teamId} profile unavailable`);
      return data;
    },
  });
}

/** The series between two teams. `enabled` gates on an opponent being selected. */
export function useHeadToHead(teamId: number, opponentId: number | null) {
  return useQuery({
    queryKey: headToHeadQueryKey(teamId, opponentId ?? 0),
    enabled: opponentId != null,
    queryFn: async () => {
      const { data, error } = await apiClient.GET(
        "/api/v1/teams/{team_id}/head-to-head",
        {
          params: {
            path: { team_id: teamId },
            query: { opponent: opponentId as number },
          },
        },
      );
      if (error) throw new Error("Head-to-head unavailable");
      return data;
    },
  });
}
