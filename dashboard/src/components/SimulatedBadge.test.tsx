import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SimulatedBadge } from "./SimulatedBadge";

describe("SimulatedBadge", () => {
  it("renders simulated source label", () => {
    render(<SimulatedBadge source="simulated" />);
    expect(screen.getByText("SIMULATED")).toBeTruthy();
  });

  it("renders real source with a different class", () => {
    const { container: sim } = render(<SimulatedBadge source="simulated" />);
    const simClass = sim.firstElementChild?.className;
    const { container: real } = render(<SimulatedBadge source="real" />);
    expect(screen.getByText("REAL")).toBeTruthy();
    expect(real.firstElementChild?.className).not.toEqual(simClass);
  });
});
