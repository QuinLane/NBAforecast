import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PredictionExplainer } from "../prediction-explainer";
import type { components } from "@/lib/api-client";

type Explanation = components["schemas"]["Explanation"];

function makeExplanation(overrides?: Partial<Explanation>): Explanation {
  return {
    baseline: 0.5,
    prediction: 0.62,
    contributions: [
      {
        feature: "home_net_rating_10g",
        display_label: "Home Net Rating (10g)",
        raw_value: 5.2,
        formatted_value: "+5.2",
        contribution: 0.08,
        direction: "up",
      },
      {
        feature: "travel_distance_km",
        display_label: "Travel distance",
        raw_value: 1200,
        formatted_value: "1200 km",
        contribution: -0.05,
        direction: "down",
      },
      {
        feature: "rest_days_diff",
        display_label: "Rest advantage",
        raw_value: 2,
        formatted_value: "+2 days",
        contribution: 0.04,
        direction: "up",
      },
    ],
    units: "probability_points",
    notes: "Top-5 drivers only.",
    ...overrides,
  };
}

describe("PredictionExplainer", () => {
  it("displays the baseline and final prediction formatted as %", () => {
    render(
      <PredictionExplainer
        explanation={makeExplanation()}
      />,
    );
    expect(screen.getByText("50.0%")).toBeInTheDocument();
    expect(screen.getByText("62.0%")).toBeInTheDocument();
  });

  it("renders all contribution display_labels", () => {
    render(
      <PredictionExplainer
        explanation={makeExplanation()}
      />,
    );
    expect(screen.getByText("Home Net Rating (10g)")).toBeInTheDocument();
    expect(screen.getByText("Travel distance")).toBeInTheDocument();
    expect(screen.getByText("Rest advantage")).toBeInTheDocument();
  });

  it("shows honesty caveat text", () => {
    render(
      <PredictionExplainer
        explanation={makeExplanation()}
      />,
    );
    expect(screen.getByText(/Top-5 drivers only/)).toBeInTheDocument();
    expect(screen.getByText(/model's reasoning/)).toBeInTheDocument();
  });

  it("shows 'See all drivers' button when onRequestFull is provided and <= 5 contributions", () => {
    const onFull = vi.fn();
    render(
      <PredictionExplainer
        explanation={makeExplanation()}
        onRequestFull={onFull}
      />,
    );
    expect(screen.getByText("See all drivers")).toBeInTheDocument();
  });

  it("calls onRequestFull when 'See all drivers' is clicked", async () => {
    const user = userEvent.setup();
    const onFull = vi.fn();
    render(
      <PredictionExplainer
        explanation={makeExplanation()}
        onRequestFull={onFull}
      />,
    );
    await user.click(screen.getByText("See all drivers"));
    expect(onFull).toHaveBeenCalledOnce();
  });

  it("hides 'See all' and shows count when > 5 contributions", () => {
    const manyContribs = Array.from({ length: 12 }, (_, i) => ({
      feature: `f${i}`,
      display_label: `Feature ${i}`,
      raw_value: i,
      formatted_value: String(i),
      contribution: 0.01 * (i + 1),
      direction: "up" as const,
    }));
    render(
      <PredictionExplainer
        explanation={makeExplanation({ contributions: manyContribs })}
        onRequestFull={vi.fn()}
      />,
    );
    expect(screen.queryByText("See all drivers")).not.toBeInTheDocument();
    expect(screen.getByText(/Showing all 12 drivers/)).toBeInTheDocument();
  });

  it("shows log-odds toggle button and switches label on click", async () => {
    const user = userEvent.setup();
    render(
      <PredictionExplainer
        explanation={makeExplanation()}
      />,
    );
    const toggle = screen.getByText("Show log-odds");
    await user.click(toggle);
    expect(screen.getByText("Show probability %")).toBeInTheDocument();
  });
});
