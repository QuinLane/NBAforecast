import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../../api-client/client";
import { useGame, useGames } from "../use-games";

vi.mock("../../api-client/client", () => ({
  apiClient: { GET: vi.fn() },
}));

const mockGET = vi.mocked(apiClient.GET);

const mockGamesPage = {
  items: [
    {
      game_id: "g1",
      season: "2024-25",
      game_date: "2024-10-22",
      home_team: { team_id: 1, abbreviation: "BOS", full_name: "Boston Celtics" },
      away_team: { team_id: 2, abbreviation: "LAL", full_name: "Los Angeles Lakers" },
      home_score: 110,
      away_score: 105,
      status: "Final",
    },
  ],
  total: 1,
  page: 1,
  page_size: 25,
};

const mockGameDetail = {
  game_id: "g1",
  season: "2024-25",
  game_date: "2024-10-22",
  home_team: { team_id: 1, abbreviation: "BOS", full_name: "Boston Celtics" },
  away_team: { team_id: 2, abbreviation: "LAL", full_name: "Los Angeles Lakers" },
  home_score: 110,
  away_score: 105,
  status: "Final",
  game_datetime: "2024-10-22T19:30:00",
  num_periods: 4,
};

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useGames", () => {
  it("returns a games page on success", async () => {
    mockGET.mockResolvedValueOnce({ data: mockGamesPage, error: undefined });
    const { result } = renderHook(() => useGames(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.total).toBe(1);
    expect(result.current.data?.items).toHaveLength(1);
    expect(result.current.data?.items[0].game_id).toBe("g1");
  });

  it("passes query params through to the client", async () => {
    mockGET.mockResolvedValueOnce({ data: mockGamesPage, error: undefined });
    renderHook(() => useGames({ season: "2024-25", page: 2 }), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(mockGET).toHaveBeenCalledOnce());
    const [, options] = mockGET.mock.calls[0] as [unknown, { params: { query?: unknown } }];
    expect(options.params.query).toMatchObject({ season: "2024-25", page: 2 });
  });

  it("is pending initially", () => {
    mockGET.mockResolvedValueOnce({ data: mockGamesPage, error: undefined });
    const { result } = renderHook(() => useGames(), {
      wrapper: createWrapper(),
    });
    expect(result.current.isPending).toBe(true);
  });

  it("sets isError when the client returns an error", async () => {
    mockGET.mockResolvedValueOnce({ data: undefined, error: { status: 500 } });
    const { result } = renderHook(() => useGames(), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useGame", () => {
  it("returns game detail on success", async () => {
    mockGET.mockResolvedValueOnce({ data: mockGameDetail, error: undefined });
    const { result } = renderHook(() => useGame("g1"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.game_id).toBe("g1");
    expect(result.current.data?.num_periods).toBe(4);
  });

  it("sets isError for an unknown game", async () => {
    mockGET.mockResolvedValueOnce({ data: undefined, error: { status: 404 } });
    const { result } = renderHook(() => useGame("unknown"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("unknown");
  });
});
