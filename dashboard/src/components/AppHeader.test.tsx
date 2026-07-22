import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { AppHeader } from "./AppHeader";

describe("AppHeader", () => {
  it("identifies LakeSafe and marks the active workspace section", () => {
    render(
      <MemoryRouter>
        <AppHeader active="operations" contextLabel="Lake Sammamish" />
      </MemoryRouter>,
    );

    expect(screen.getByText("LakeSafe")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Lakes" })).toHaveAttribute("href", "/lakes");
    expect(screen.getByText("Operations")).toHaveAttribute("aria-current", "page");
    expect(screen.getByText("Lake Sammamish")).toBeInTheDocument();
  });
});
