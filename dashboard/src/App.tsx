import { SimulatedBadge } from "./components/SimulatedBadge";
import "./styles.css";

export default function App() {
  return (
    <main className="app-shell">
      <section className="operator-header">
        <div>
          <p className="eyebrow">LakeSafe Initiative</p>
          <h1>Operator Dashboard</h1>
        </div>
        <SimulatedBadge source="simulated" />
      </section>
    </main>
  );
}
