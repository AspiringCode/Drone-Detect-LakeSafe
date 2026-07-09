import type { Source } from "../lib/types";

interface SimulatedBadgeProps {
  source: Source;
}

export function SimulatedBadge({ source }: SimulatedBadgeProps) {
  const label = source === "real" ? "REAL" : "SIMULATED";
  return <span className={`source-badge source-badge--${source}`}>{label}</span>;
}
