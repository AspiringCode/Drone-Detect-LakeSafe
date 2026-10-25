import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { LakePreviewMap } from "./LakePreviewMap";
const leaflet = vi.hoisted(()=>({map:vi.fn(),fitBounds:vi.fn(),setView:vi.fn(),remove:vi.fn()}));
vi.mock("leaflet",()=>({default:{map:leaflet.map,tileLayer:()=>({addTo:vi.fn()})}}));
it("fits the actual lake bounds and enables navigation only on the public map",()=>{
  leaflet.map.mockReturnValue(leaflet);
  const view=render(<LakePreviewMap name="Beaver Lake" lat={47.6} lon={-122} bounds={[-122.1,47.59,-122.09,47.6]} interactive/>);
  expect(leaflet.map).toHaveBeenCalledWith(expect.anything(),expect.objectContaining({dragging:true,touchZoom:true,keyboard:true,zoomControl:true}));
  expect(leaflet.fitBounds).toHaveBeenCalledWith([[47.59,-122.1],[47.6,-122.09]],expect.objectContaining({maxZoom:16}));
  expect(leaflet.setView).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button",{name:"Reset lake view"}));
  expect(leaflet.fitBounds).toHaveBeenCalledTimes(2);
  view.unmount();expect(leaflet.remove).toHaveBeenCalledOnce();
});
it("keeps clickable lake-card previews noninteractive",()=>{
  leaflet.map.mockClear();leaflet.map.mockReturnValue(leaflet);
  render(<LakePreviewMap name="Pine Lake" lat={47.6} lon={-122}/>);
  expect(leaflet.map).toHaveBeenCalledWith(expect.anything(),expect.objectContaining({dragging:false,touchZoom:false,zoomControl:false}));
  expect(screen.queryByRole("button",{name:"Reset lake view"})).not.toBeInTheDocument();
});
