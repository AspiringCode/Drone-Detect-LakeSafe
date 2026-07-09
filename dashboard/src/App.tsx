import { useEffect, useState } from "react";
import { SimulatedBadge } from "./components/SimulatedBadge";
import { LakeMap, type RiskGeoJSON } from "./components/LakeMap";
import { DroneRoster } from "./components/DroneRoster";
import { AlertPanel } from "./components/AlertPanel";
import { connectPositions } from "./lib/ws";
import { fetchAlerts, subscribeAlerts } from "./lib/supabase";
import type { Alert, Drone, SimulationState } from "./lib/types";
import "./styles.css";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const WS_URL = API_BASE_URL.replace(/^http/, "ws") + "/ws/positions";

export default function App() {
  const [drones, setDrones] = useState<Drone[]>([]);
  const [riskmap, setRiskmap] = useState<RiskGeoJSON | null>(null);
  const [activeAlert, setActiveAlert] = useState<Alert | null>(null);

  useEffect(() => {
    const unsubscribe = connectPositions(WS_URL, (state: SimulationState) => {
      setDrones(state.drones);
    });
    return unsubscribe;
  }, []);

  useEffect(() => {
    fetch(`${API_BASE_URL}/api/riskmap`)
      .then((res) => res.json())
      .then((data: RiskGeoJSON) => setRiskmap(data))
      .catch(() => setRiskmap(null));
  }, []);

  useEffect(() => {
    fetchAlerts()
      .then((alerts) => {
        if (alerts.length > 0) setActiveAlert(alerts[0]);
      })
      .catch(() => {
        // Supabase not configured yet in local dev -- dashboard still renders.
      });
    const unsubscribe = subscribeAlerts((alert) => setActiveAlert(alert));
    return unsubscribe;
  }, []);

  const handleEscalate = async (alertId: string) => {
    await fetch(`${API_BASE_URL}/api/alerts/${alertId}/escalate`, { method: "POST" });
  };

  const fireDemoTrigger = async () => {
    const response = await fetch(`${API_BASE_URL}/api/demo/trigger`, { method: "POST" });
    const alert = (await response.json()) as Alert;
    setActiveAlert(alert);
  };

  return (
    <main className="app-shell">
      <section className="operator-header">
        <div>
          <p className="eyebrow">LakeSafe Initiative</p>
          <h1>Operator Dashboard</h1>
        </div>
        <div className="operator-header__actions">
          <SimulatedBadge source="simulated" />
          <button type="button" onClick={fireDemoTrigger}>
            Fire Demo Trigger
          </button>
        </div>
      </section>
      <section className="operator-layout">
        <LakeMap riskmap={riskmap} drones={drones} />
        <div className="side-panel">
          <DroneRoster drones={drones} />
          <AlertPanel alert={activeAlert} onEscalate={handleEscalate} apiBaseUrl={API_BASE_URL} />
        </div>
      </section>
    </main>
  );
}
