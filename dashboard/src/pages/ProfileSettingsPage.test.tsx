import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ProfileSettingsPage } from "./ProfileSettingsPage";

describe("ProfileSettingsPage", () => {
  it("loads the signed-in account and updates its display name", async () => {
    const updateUser = vi.fn().mockResolvedValue({ error: null });
    const client = {
      auth: {
        getUser: vi.fn().mockResolvedValue({
          data: {
            user: {
              id: "bc14340d-ea56-4a7a-9b74-7b679f9055c4",
              email: "operator@example.com",
              user_metadata: { display_name: "Lake Operator" },
            },
          },
          error: null,
        }),
        updateUser,
        signOut: vi.fn(),
      },
    };

    render(<MemoryRouter><ProfileSettingsPage client={client as never} /></MemoryRouter>);

    expect(await screen.findByDisplayValue("Lake Operator")).toBeInTheDocument();
    expect(screen.getByDisplayValue("operator@example.com")).toHaveAttribute("readonly");
    expect(screen.getByRole("navigation", { name: "Account settings" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Access" })).toHaveAttribute("href", "/verify-affiliation");
    expect(screen.getByRole("link", { name: "Stations" })).toHaveAttribute("href", "/station-access");
    expect(screen.getByRole("group")).toHaveTextContent("Account details");
    expect(screen.queryByText(/Supabase/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/display name/i), { target: { value: "Sammamish Operator" } });
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(updateUser).toHaveBeenCalledWith({ data: { display_name: "Sammamish Operator" } }));
    expect(await screen.findByRole("status")).toHaveTextContent(/profile saved/i);
  });
});
