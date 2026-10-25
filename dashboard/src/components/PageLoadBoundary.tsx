import { Component, type ReactNode } from "react";

export class PageLoadBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (!this.state.failed) return this.props.children;
    return <main className="auth-page"><section className="auth-card" role="alert"><h1>This page couldn’t load</h1><p>A website update or connection problem may have interrupted loading. Reload to try the latest version.</p><button type="button" onClick={() => window.location.reload()}>Reload page</button></section></main>;
  }
}
