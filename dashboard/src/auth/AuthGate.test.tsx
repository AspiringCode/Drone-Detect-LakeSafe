import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { AuthGate } from "./AuthGate";

it("returns an ended session home even when an older session read completes", async () => {
  let changed: (event: string) => void = () => {};
  let resolveSession!: (result: unknown) => void;
  const client = { auth: {
    getSession: vi.fn().mockImplementationOnce(() => Promise.resolve({ data: { session: { access_token: "token" } } }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveSession = resolve; })),
    onAuthStateChange: (callback: typeof changed) => { changed = callback; return { data: { subscription: { unsubscribe: vi.fn() } } }; },
  } };
  render(<MemoryRouter initialEntries={["/lakes"]}><Routes><Route path="/" element={<p>Public home</p>}/><Route path="/login" element={<p>Login</p>}/><Route element={<AuthGate client={client as never}/>}><Route path="/lakes" element={<p>Workspace</p>}/></Route></Routes></MemoryRouter>);
  expect(await screen.findByText("Workspace")).toBeInTheDocument();
  act(() => changed("TOKEN_REFRESHED"));
  act(() => changed("SIGNED_OUT"));
  await act(async () => resolveSession({ data: { session: null } }));
  expect(await screen.findByText("Public home")).toBeInTheDocument();
  expect(screen.queryByText("Login")).not.toBeInTheDocument();
});

it("still sends an initially signed-out deep link through login", async () => {
  const client = { auth: {
    getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
    onAuthStateChange: () => ({ data: { subscription: { unsubscribe: vi.fn() } } }),
  } };
  function Login() { return <p>{useLocation().search}</p>; }
  render(<MemoryRouter initialEntries={["/lakes/lake-beaver?tab=map"]}><Routes><Route path="/login" element={<Login/>}/><Route element={<AuthGate client={client as never}/>}><Route path="/lakes/:id" element={<p>Workspace</p>}/></Route></Routes></MemoryRouter>);
  expect(await screen.findByText("?returnTo=%2Flakes%2Flake-beaver%3Ftab%3Dmap")).toBeInTheDocument();
});
