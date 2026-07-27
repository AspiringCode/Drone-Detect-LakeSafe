import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { InvitationAcceptPage } from "./InvitationAcceptPage";

describe("station journeys", () => {
  it("shows an invitation acceptance action for a token in the route", () => {
    render(<MemoryRouter initialEntries={["/invitations/accept?token=single-use"]}><InvitationAcceptPage /></MemoryRouter>);
    expect(screen.getByRole("button", { name: /accept invitation/i })).toBeVisible();
  });
});
