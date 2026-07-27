import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("../auth/PrincipalProvider", () => ({ useOptionalPrincipal: () => ({ principal: { reviewer: true, memberships: [] } }) }));
vi.mock("../lib/apiClient", () => ({ apiRequest: () => Promise.resolve({ requests: [{ station_request_id: "request-1", requested_name: "Lake Sammamish Station" }] }) }));
import { ReviewConsolePage } from "./ReviewConsolePage";

describe("ReviewConsolePage", () => {
  it("renders the requested station name returned by the review queue", async () => {
    render(<MemoryRouter><ReviewConsolePage /></MemoryRouter>);
    expect(await screen.findByRole("heading", { name: "Lake Sammamish Station" })).toBeVisible();
  });
});
