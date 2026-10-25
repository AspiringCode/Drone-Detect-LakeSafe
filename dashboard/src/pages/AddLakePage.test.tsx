import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { AddLakePage } from "./AddLakePage";
const state = vi.hoisted(() => ({ request: vi.fn(), refresh: vi.fn(), principal: { memberships: [{station_id:"station-1",station_name:"Station one",status:"active",capabilities:["lake.create"]}] } }));
vi.mock("../lib/apiClient", () => ({ apiRequest: state.request }));
vi.mock("../auth/PrincipalProvider", () => ({ useOptionalPrincipal: () => ({ principal: state.principal, refresh: state.refresh }) }));
vi.mock("../components/AppHeader", () => ({ AppHeader: () => <header/> }));
vi.mock("../components/ShorelinePreview", () => ({ ShorelinePreview: ({onFailure}: {onFailure:()=>void}) => <div role="img" aria-label="Shoreline preview"><button type="button" onClick={onFailure}>Drawing failure</button></div> }));
const candidate = {candidate_id:13645,component_index:0,area_label:"Main waterbody",name:"Lake Washington",source:"King County GIS",shoreline:{type:"Polygon",coordinates:[]}};
function page() {
  render(<MemoryRouter initialEntries={["/lakes/new"]}><Routes><Route path="/lakes/new" element={<AddLakePage/>}/><Route path="/lakes/:id" element={<p>Opened lake</p>}/></Routes></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("Lake name"),{target:{value:"Washington"}});
  fireEvent.click(screen.getByRole("button",{name:"Search lakes"}));
}
async function selectLake() { fireEvent.click(await screen.findByRole("radio",{name:/Lake Washington/})); }
beforeEach(()=>{state.request.mockReset();state.refresh.mockReset();state.principal.memberships=[{station_id:"station-1",station_name:"Station one",status:"active",capabilities:["lake.create"]}];});
it("searches without coordinates and gives an actionable empty result",async()=>{
  state.request.mockResolvedValue({candidates:[]});page();
  expect(await screen.findByText(/No matching shoreline/)).toBeVisible();
  expect(screen.queryByLabelText("Latitude")).not.toBeInTheDocument();
  expect(state.request).toHaveBeenCalledWith("/api/lake-search?query=Washington",{},expect.anything());
});
it("invalidates selection when the search name changes",async()=>{
  state.request.mockResolvedValue({candidates:[candidate]});page();await selectLake();
  expect(screen.getByRole("img",{name:"Shoreline preview"})).toBeVisible();
  fireEvent.change(screen.getByLabelText("Lake name"),{target:{value:"Pine"}});
  expect(screen.queryByRole("button",{name:"Add lake to station"})).not.toBeInTheDocument();
});
it("does not create a lake whose preview fails",async()=>{
  state.request.mockResolvedValue({candidates:[candidate]});page();await selectLake();
  fireEvent.click(screen.getByRole("button",{name:"Drawing failure"}));
  expect(screen.getByRole("alert")).toHaveTextContent("could not be drawn");
  expect(screen.queryByRole("button",{name:"Add lake to station"})).not.toBeInTheDocument();
});
it("creates in an existing station using only the verified candidate ID",async()=>{
  state.request.mockResolvedValueOnce({candidates:[candidate]}).mockResolvedValueOnce({lake_id:"lake-created",station_id:"station-1"});page();await selectLake();
  fireEvent.click(screen.getByRole("button",{name:"Add lake to station"}));
  expect(await screen.findByText("Opened lake")).toBeVisible();
  expect(JSON.parse(state.request.mock.calls[1][1].body)).toEqual({candidate_id:13645,component_index:0,station_id:"station-1"});
});
it("offers a separate station and refreshes its new administrator membership",async()=>{
  state.request.mockResolvedValueOnce({candidates:[candidate]}).mockResolvedValueOnce({lake_id:"lake-created",station_id:"station-new"});
  state.refresh.mockImplementation(async()=>{state.principal.memberships.push({station_id:"station-new",station_name:"Washington station",status:"active",capabilities:["lake.create"]});});
  page();await selectLake();fireEvent.click(screen.getByRole("radio",{name:"New station for this lake"}));
  fireEvent.change(screen.getByLabelText("New station name"),{target:{value:"Washington station"}});
  fireEvent.click(screen.getByRole("button",{name:"Create station and add lake"}));
  expect(await screen.findByText("Opened lake")).toBeVisible();
  expect(JSON.parse(state.request.mock.calls[1][1].body)).toEqual({candidate_id:13645,component_index:0,new_station_name:"Washington station"});
});
