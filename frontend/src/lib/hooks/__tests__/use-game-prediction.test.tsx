import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "../../api-client/client";
import {
  useGamePrediction,
  useGamePredictionFullExplanation,
} from "../use-game-prediction";

vi.mock("../../api-client/client", () => ({
  apiClient: { GET: vi.fn() },
}));

const mockGET = vi.mocked(apiClient.GET);

const makeContributions = (count: number) =>
  Array.from({ length: count }, (_, i) => ({
    feature: `feature_${i}`,
    display_label: `Feature ${i}`,
    raw_value: 5.2 - i,
    formatted_value: `${5.2 - i}`,
    contribution: 0.08 - i * 0.005,
    direction: "up" as const,
  }));

const mockPrediction = {
  game_id: "g1",
  win_prob: 0.62,
  margin: null,
  total: null,
  market: null,
  explanation: {
    baseline: 0.5,
    prediction: 0.62,
    contributions: makeContributions(5),
    units: "probability_points" as const,
    notes: "Top-5 drivers only.",
  },
};

const mockFullPrediction = {
  ...mockPrediction,
  explanation: {
    ...mockPrediction.explanation,
    contributions: makeContributions(12),
    notes: "All drivers.",
  },
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

describe("useGamePrediction", () => {
  it("returns prediction with win_prob in [0, 1]", async () => {
    mockGET.mockResolvedValueOnce({
      data: mockPrediction,
      error: undefined,
    });
    const { result } = renderHook(() => useGamePrediction("g1"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.game_id).toBe("g1");
    expect(result.current.data?.win_prob).toBeGreaterThan(0);
    expect(result.current.data?.win_prob).toBeLessThanOrEqual(1);
  });

  it("explanation units are probability_points", async () => {
    mockGET.mockResolvedValueOnce({ data: mockPrediction, error: undefined });
    const { result } = renderHook(() => useGamePrediction("g1"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.explanation.units).toBe("probability_points");
  });

  it("top-5 has at most 5 contributions", async () => {
    mockGET.mockResolvedValueOnce({ data: mockPrediction, error: undefined });
    const { result } = renderHook(() => useGamePrediction("g1"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.explanation.contributions).toHaveLength(5);
  });

  it("sets isError on failure", async () => {
    mockGET.mockResolvedValueOnce({
      data: undefined,
      error: { status: 404 },
    });
    const { result } = renderHook(() => useGamePrediction("unknown"), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("unknown");
  });
});

describe("useGamePredictionFullExplanation", () => {
  it("full explanation has more than 5 contributions", async () => {
    mockGET.mockResolvedValueOnce({
      data: mockFullPrediction,
      error: undefined,
    });
    const { result } = renderHook(
      () => useGamePredictionFullExplanation("g1"),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(
      result.current.data?.explanation.contributions.length,
    ).toBeGreaterThan(5);
  });

  it("sets isError on failure", async () => {
    mockGET.mockResolvedValueOnce({
      data: undefined,
      error: { status: 404 },
    });
    const { result } = renderHook(
      () => useGamePredictionFullExplanation("unknown"),
      { wrapper: createWrapper() },
    );
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toContain("unknown");
  });
});
