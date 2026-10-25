import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { StationMemberTable } from "./StationMemberTable";

const request = vi.hoisted(() => vi.fn());
vi.mock("../lib/apiClient", () => ({ apiRequest: request }));
const membership = { station_id: "s-1", station_name: "Station", status: "active", roles: ["station_admin"], capabilities: ["member.manage"] } as never;
beforeEach(() => { request.mockReset(); });
it("loads the station roster and submits the reviewed member roles", async () => {
  request.mockResolvedValue({ members: [{ membership_id: "m-1", user_id: "u-2", display_name: "Officer", status: "active", roles: ["viewer"] }] });
  render(<MemoryRouter><StationMemberTable membership={membership}/></MemoryRouter>);
  await screen.findByText("Officer");
  fireEvent.click(screen.getByLabelText("Dispatcher"));
  fireEvent.click(screen.getByRole("button", { name: "Save access for Officer" }));
  expect(screen.getByRole("dialog", {name:"Review station access"})).toHaveFocus();
  expect(request).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", {name:"Confirm access change"}));
  await waitFor(() => expect(request).toHaveBeenCalledWith("/api/stations/s-1/members/m-1", expect.objectContaining({ method: "PATCH", body: JSON.stringify({ roles: ["viewer", "dispatcher"], status: "active" }) }), expect.anything()));
});
it("never shows an empty roster as success when loading fails", async () => {
  request.mockRejectedValue(new Error("Unable to reach station"));
  render(<MemoryRouter><StationMemberTable membership={membership}/></MemoryRouter>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to reach station");
  expect(screen.getByRole("button", { name: "Retry members" })).toBeInTheDocument();
});

it("cancels revocation without sending a membership mutation", async () => {
  request.mockResolvedValue({ members: [{membership_id:"m-1", user_id:"u-2", display_name:"Officer", status:"active", roles:["viewer"]}] });
  render(<MemoryRouter><StationMemberTable membership={membership}/></MemoryRouter>);
  await screen.findByText("Officer");
  fireEvent.change(screen.getByLabelText("Membership status"), {target:{value:"revoked"}});
  fireEvent.click(screen.getByRole("button", {name:"Save access for Officer"}));
  expect(screen.getByRole("dialog")).toHaveTextContent("This removes their access");
  fireEvent.click(screen.getByRole("button", {name:"Cancel"}));
  expect(request).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("dialog")).toBeNull();
});
