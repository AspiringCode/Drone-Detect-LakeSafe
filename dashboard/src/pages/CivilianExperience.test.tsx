import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { CivilianHomePage } from "./CivilianHomePage";
import { PrincipalProvider } from "../auth/PrincipalProvider";

const fetcher = async (url: string) => ({
  ok: true,
  json: async () => url.endsWith("/lakes")
    ? [{ lake_id: "lake-1", name: "Lake Sammamish", approximate_center_geohash: "c23nb", public_status: "patrolling", refreshed_at: "2026-07-30T12:05:00Z" }]
    : url.endsWith("/alerts")
      ? [{ lake_id: "lake-1", category: "Safety notice", approximate_area_label: "North lake area", public_status: "active", occurred_at: "2026-07-30T12:00:00Z", published_at: "2026-07-30T12:05:00Z" }]
      : [{ lake_id: "lake-1", generalized_zone: "North lake area", public_state: "patrolling", observed_bucket: "2026-07-30T12:00:00Z", published_at: "2026-07-30T12:05:00Z" }],
});

describe("CivilianHomePage", () => {
  it("restores a lake from its URL and preserves other query parameters on selection", async () => {
    const Query = () => <output aria-label="Current query">{useLocation().search}</output>;
    const catalog = async (url: string) => ({ok:true,json:async () => url.endsWith("/lakes") ? ["one","two"].map((id) => ({lake_id:id,name:`Lake ${id}`})) : []});
    render(<MemoryRouter initialEntries={["/?lake=two&context=visit"]}><CivilianHomePage fetcher={catalog}/><Query/></MemoryRouter>);
    expect(await screen.findByRole("button",{name:"Lake two"})).toHaveAttribute("aria-pressed","true");
    fireEvent.click(screen.getByRole("button",{name:"Lake one"}));
    expect(screen.getByLabelText("Current query")).toHaveTextContent("lake=one&context=visit");
  });
  it("lets a signed-in civilian reach profile settings without showing sign-in actions", async () => {
    const client = { auth: {
      getSession: async () => ({ data: { session: { access_token: "civilian-session" } } }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => undefined } } }),
    } };
    const request = async <T,>() => ({ user_id: "civilian", account_class: "civilian", memberships: [] } as T);
    render(<MemoryRouter><PrincipalProvider client={client as never} request={request}><CivilianHomePage fetcher={fetcher} /></PrincipalProvider></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "Profile settings" })).toHaveAttribute("href", "/profile");
    expect(screen.getByRole("link", { name: "LakeSafe" })).toHaveAttribute("href", "/lakes");
    expect(screen.queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Create account" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Operations" })).not.toBeInTheDocument();
  });

  it("offers a signed-in operator the way back to their workspace", async () => {
    const client = { auth: {
      getSession: async () => ({ data: { session: { access_token: "officer-session" } } }),
      onAuthStateChange: () => ({ data: { subscription: { unsubscribe: () => undefined } } }),
    } };
    const request = async <T,>() => ({ user_id: "officer", account_class: "officer", memberships: [] } as T);
    render(<MemoryRouter><PrincipalProvider client={client as never} request={request}><CivilianHomePage fetcher={fetcher} /></PrincipalProvider></MemoryRouter>);
    expect(await screen.findByRole("link", { name: "Return to workspace" })).toHaveAttribute("href", "/lakes");
    expect(screen.queryByRole("link", { name: "Sign in" })).not.toBeInTheDocument();
  });

  it("keeps account entry links available to anonymous visitors", () => {
    render(<MemoryRouter><CivilianHomePage fetcher={fetcher} /></MemoryRouter>);
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Create account" })).toHaveAttribute("href", "/signup");
    expect(screen.getByRole("link", { name: "LakeSafe" })).toHaveAttribute("href", "/");
    expect(screen.queryByRole("link", { name: "Profile settings" })).not.toBeInTheDocument();
  });

  it("browses the published catalog and ignores updates for a previously selected lake", async () => {
    let resolveSlow!: (value: unknown) => void;
    const catalogFetcher = async (url: string) => ({ ok: true, json: async () => {
      if (url.endsWith("/lakes")) return ["one", "two", "three"].map((id) => ({ lake_id: id, name: `Lake ${id}` }));
      if (url.includes("/two/") && url.endsWith("/alerts")) return new Promise((resolve) => { resolveSlow = resolve; });
      if (url.endsWith("/alerts")) return [{ lake_id: "test", category: url.includes("/three/") ? "Third lake notice" : "First lake notice", approximate_area_label: "Lake area", public_status: "active", occurred_at: "2026-07-30T12:00:00Z", published_at: "2026-07-30T12:05:00Z" }];
      return [];
    } });
    render(<MemoryRouter><CivilianHomePage fetcher={catalogFetcher} /></MemoryRouter>);
    expect(await screen.findByText("First lake notice")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Lake two" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Loading lake updates");
    expect(screen.queryByText("First lake notice")).not.toBeInTheDocument();
    await act(async () => { await Promise.resolve(); });
    fireEvent.click(screen.getByRole("button", { name: "Lake three" }));
    expect(await screen.findByText("Third lake notice")).toBeVisible();
    await act(async () => { resolveSlow([]); });
    expect(screen.getByText("Third lake notice")).toBeVisible();
    expect(screen.getByRole("button", { name: "Lake three" })).toHaveAttribute("aria-pressed", "true");
  });

  it("keeps secondary data failures unavailable until Retry succeeds", async () => {
    let offline = true;
    const secondaryFailure = async (url: string) => {
      if (url.endsWith("/alerts") && offline) throw new TypeError("Failed to fetch");
      return fetcher(url);
    };
    render(<MemoryRouter><CivilianHomePage fetcher={secondaryFailure} /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toBeVisible();
    expect(screen.queryByText("No current public safety notices.")).not.toBeInTheDocument();
    offline = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Safety notice")).toBeVisible();
  });

  it("explains an outage and recovers through Retry without showing a false all-clear", async () => {
    let offline = true;
    const recoverable = async (url: string) => {
      if (offline) throw new TypeError("Failed to fetch");
      return fetcher(url);
    };
    render(<MemoryRouter><CivilianHomePage fetcher={recoverable} /></MemoryRouter>);
    expect(await screen.findByRole("alert")).toHaveTextContent("Lake updates are unavailable");
    expect(screen.queryByText("No current public safety notices.")).not.toBeInTheDocument();
    offline = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Patrol presence")).toBeVisible();
    expect(screen.getByRole("button", { name: "Refresh lake updates" })).toBeVisible();
    expect(screen.getByText(/Checked at/)).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("distinguishes an empty catalog from an outage", async () => {
    render(<MemoryRouter><CivilianHomePage fetcher={async () => ({ ok: true, json: async () => [] })} /></MemoryRouter>);
    expect(await screen.findByText("No lake updates published yet")).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders public patrol and alert summaries without operational fields", async () => {
    render(<MemoryRouter><CivilianHomePage fetcher={fetcher} /></MemoryRouter>);

    expect(await screen.findByText("Patrol presence")).toBeVisible();
    expect(screen.getAllByText("North lake area")).toHaveLength(2);
    expect(screen.queryByText(/battery|serial number|exact coordinates/i)).not.toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Lake Sammamish map preview" })).toBeInTheDocument();
    expect(screen.queryByText(/privacy|generalized for/)).not.toBeInTheDocument();
  });
});
