import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AlertPanel } from "./AlertPanel";
import type { Alert } from "../lib/types";

function mkAlert(overrides: Partial<Alert> = {}): Alert {
  return {
    alert_id: "a1",
    created_at: "2026-07-06T00:00:00Z",
    location: { lat: 47.581, lon: -122.091 },
    detection_mode: "thermal-cv",
    drone_id: "d1",
    thermal_clip_ref: null,
    confirmed: false,
    source: "simulated",
    latency_ms: 100,
    ...overrides,
  };
}

describe("AlertPanel", () => {
  it("renders GPS coordinates and a maps link", () => {
    render(<AlertPanel alert={mkAlert()} />);
    expect(screen.getByText(/47\.58100, -122\.09100/)).toBeTruthy();
    const link = screen.getByRole("link", { name: /open in maps/i }) as HTMLAnchorElement;
    expect(link.href).toContain("47.581");
  });

  it("calls onEscalate with the alert id when Confirm & Dispatch is clicked", () => {
    const onEscalate = vi.fn();
    render(<AlertPanel alert={mkAlert()} onEscalate={onEscalate} />);
    fireEvent.click(screen.getByRole("button", { name: /mark reviewed/i }));
    expect(onEscalate).toHaveBeenCalledTimes(1);
    expect(onEscalate).toHaveBeenCalledWith("a1");
  });

  it("shows operator-assist framing when detection_mode is operator-assist", () => {
    render(<AlertPanel alert={mkAlert({ detection_mode: "operator-assist" })} />);
    expect(screen.getByText(/human operator must confirm/i)).toBeTruthy();
  });

  it("does not show operator-assist framing for a normal thermal-cv alert", () => {
    render(<AlertPanel alert={mkAlert()} />);
    expect(screen.queryByText(/human operator must confirm/i)).toBeNull();
  });

  it("always renders the SimulatedBadge matching the alert source", () => {
    render(<AlertPanel alert={mkAlert({ source: "real" })} />);
    expect(screen.getByText("REAL")).toBeTruthy();
  });

  it("renders a placeholder when there is no active alert", () => {
    render(<AlertPanel alert={null} />);
    expect(screen.getByText(/no active alert/i)).toBeTruthy();
  });

  it("surfaces failed review without claiming success and allows retry", async () => {
    const review = vi.fn().mockRejectedValueOnce(new Error("Review unavailable")).mockResolvedValueOnce(undefined);
    render(<AlertPanel alert={mkAlert()} onEscalate={review}/>);
    fireEvent.click(screen.getByRole("button", {name:"Mark reviewed"}));
    expect(await screen.findByRole("alert")).toHaveTextContent("Review unavailable");
    fireEvent.click(screen.getByRole("button", {name:"Mark reviewed"}));
    expect(await screen.findByRole("button", {name:"Reviewed"})).toBeDisabled();
    expect(screen.getByText(/No emergency services are contacted/)).toBeVisible();
  });

  it("requests authorized evidence without displaying a private storage key", async () => {
    const evidence = vi.fn().mockResolvedValue({url:"https://example.com/signed-clip", expires_in:60});
    render(<AlertPanel alert={mkAlert({thermal_clip_ref:"private/bucket/key.mp4"})} onEvidence={evidence}/>);
    expect(screen.queryByText(/private\/bucket/)).toBeNull();
    fireEvent.click(screen.getByRole("button", {name:"Review thermal evidence"}));
    expect(await screen.findByRole("link", {name:/Open thermal evidence/})).toHaveAttribute("href","https://example.com/signed-clip");
    expect(evidence).toHaveBeenCalledWith("a1");
  });
});
