import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
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

  it("signs the operator out and returns to login", async () => {
    const signOut = vi.fn().mockResolvedValue({ error: null });
    render(
      <MemoryRouter initialEntries={["/lakes"]}>
        <Routes>
          <Route path="/lakes" element={<AppHeader active="lakes" client={{ auth: { signOut } } as never} />} />
          <Route path="/login" element={<p>Signed out</p>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() => expect(signOut).toHaveBeenCalledOnce());
    expect(await screen.findByText("Signed out")).toBeInTheDocument();
  });
});
