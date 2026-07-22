import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AppHeader } from "./AppHeader";

describe("AppHeader", () => {
  function client() {
    return {
      auth: {
        getUser: vi.fn().mockResolvedValue({ data: { user: { email: "operator@example.com", user_metadata: { display_name: "Lake Operator" } } }, error: null }),
        signOut: vi.fn().mockResolvedValue({ error: null }),
      },
      from: vi.fn(() => ({
        select: vi.fn().mockResolvedValue({ data: [{ org_id: "org-demo", name: "LakeSafe Demo Station" }], error: null }),
      })),
    };
  }

  it("shows workspace navigation, a station selector, and an account menu", async () => {
    const fakeClient = client();
    render(
      <MemoryRouter>
        <AppHeader active="operations" client={fakeClient as never} />
      </MemoryRouter>,
    );

    expect(screen.getByText("LakeSafe")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Lakes" })).toHaveAttribute("href", "/lakes");
    expect(screen.getByRole("link", { name: "Operations" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Alerts" })).toHaveAttribute("href", "/alerts");
    expect(screen.getByRole("link", { name: "Reports" })).toHaveAttribute("href", "/reports");
    expect(await screen.findByRole("combobox", { name: /active station/i })).toHaveDisplayValue("LakeSafe Demo Station");

    fireEvent.click(screen.getByRole("button", { name: /open account menu/i }));
    expect(screen.getByRole("link", { name: /profile settings/i })).toHaveAttribute("href", "/profile");
    expect(screen.getByRole("button", { name: /sign out/i })).toBeInTheDocument();
  });

  it("signs the operator out and returns to login", async () => {
    const fakeClient = client();
    render(
      <MemoryRouter initialEntries={["/lakes"]}>
        <Routes>
          <Route path="/lakes" element={<AppHeader active="lakes" client={fakeClient as never} />} />
          <Route path="/login" element={<p>Signed out</p>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /open account menu/i }));
    fireEvent.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() => expect(fakeClient.auth.signOut).toHaveBeenCalledOnce());
    expect(await screen.findByText("Signed out")).toBeInTheDocument();
  });
});
