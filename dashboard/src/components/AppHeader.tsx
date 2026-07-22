import { Link } from "react-router-dom";

type AppHeaderProps = {
  active: "lakes" | "operations";
  contextLabel?: string;
};

export function AppHeader({ active, contextLabel }: AppHeaderProps) {
  return (
    <header className="app-header">
      <Link className="app-brand" to="/lakes" aria-label="LakeSafe managed lakes">
        <span className="app-brand__name">LakeSafe</span>
        <span className="app-brand__mark" aria-hidden="true" />
      </Link>
      <nav className="app-nav" aria-label="Primary navigation">
        <Link className={active === "lakes" ? "app-nav__item is-active" : "app-nav__item"} to="/lakes" aria-current={active === "lakes" ? "page" : undefined}>
          Lakes
        </Link>
        <span className={active === "operations" ? "app-nav__item is-active" : "app-nav__item"} aria-current={active === "operations" ? "page" : undefined}>
          Operations
        </span>
      </nav>
      <div className="app-context">
        <span className="status-dot" aria-hidden="true" />
        <span>{contextLabel ?? "Operator workspace"}</span>
      </div>
    </header>
  );
}
