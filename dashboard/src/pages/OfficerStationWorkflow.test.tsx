import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { SignupPage } from "./SignupPage";

describe("officer and station workflow", () => {
  it("describes every new account as civilian", () => {
    render(<MemoryRouter><SignupPage /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Create your LakeSafe account" })).toBeVisible();
    expect(screen.queryByText(/operator account/i)).not.toBeInTheDocument();
  });
});
