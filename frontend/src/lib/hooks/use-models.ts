import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../api-client/client";

export const championsQueryKey = () => ["models", "champions"] as const;

/** Champion provenance per head (version · trained-through · feature version). */
export function useChampions() {
  return useQuery({
    queryKey: championsQueryKey(),
    staleTime: 5 * 60 * 1000, // provenance changes only on a promotion; cache generously
    queryFn: async () => {
      const { data, error } = await apiClient.GET("/api/v1/models/champions");
      if (error) throw new Error("Failed to fetch model provenance");
      return data;
    },
  });
}
