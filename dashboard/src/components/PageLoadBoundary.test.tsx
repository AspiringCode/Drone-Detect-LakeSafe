import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { PageLoadBoundary } from "./PageLoadBoundary";

it("keeps a failed route recoverable instead of blank", () => {
  const log = vi.spyOn(console, "error").mockImplementation(() => {});
  const expectedError = (event: ErrorEvent) => event.preventDefault();
  window.addEventListener("error", expectedError);
  function Broken(): never { throw new TypeError("Failed to fetch dynamically imported module"); }
  try {
    render(<PageLoadBoundary><Broken /></PageLoadBoundary>);
    expect(screen.getByRole("heading", { name: "This page couldn’t load" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reload page" })).toBeInTheDocument();
  } finally { window.removeEventListener("error", expectedError); log.mockRestore(); }
});
