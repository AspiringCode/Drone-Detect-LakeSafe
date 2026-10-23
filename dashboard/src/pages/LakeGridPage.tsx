import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { supabase, type SupabaseLike } from "../lib/supabase";
import type { Lake } from "../lib/types";
import { useOrientation } from "../lib/useOrientation";
import { AppHeader } from "../components/AppHeader";
import { LakePreviewMap } from "../components/LakePreviewMap";
import { useOptionalActiveStation } from "../hooks/useActiveStation";

export function LakeGridPage({ client = supabase }: { client?: SupabaseLike }) {
  const ref = useOrientation();
  const [lakes, setLakes] = useState<Lake[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const activeStation = useOptionalActiveStation();
  useEffect(() => {
    let current = true;
    setLoading(true);
    setError(false);
    async function load() {
      try {
        const { data, error: loadError } = await client.from("lakes").select("lake_id,station_id,org_id,name,centroid_lat,centroid_lon").order("name");
        if (!current) return;
        if (loadError) throw loadError;
        setLakes(data ?? []);
      } catch {
        if (current) setError(true);
      } finally {
        if (current) setLoading(false);
      }
    }
    void load();
    return () => { current = false; };
  }, [client, attempt]);
  return (
    <main className="app-page workflow-page">
      <AppHeader active="lakes" contextLabel="Managed lakes" client={client} />
      <section ref={ref} className="lake-grid-page">
        <header className="page-heading">
          <h1>Managed lakes</h1>
          <p>Select a lake to open its live operations workspace.</p>
        </header>
        {loading && <p className="empty-state" role="status">Loading lakes…</p>}
        {error && <section className="workflow-card"><p className="form-error" role="alert">Could not load lakes. Please try again.</p><button type="button" onClick={() => setAttempt((value) => value + 1)}>Retry</button></section>}
        {!loading && !error && <div className="lake-grid">
          {lakes.map((lake) => (
            <Link className="lake-card" to={`/lakes/${lake.lake_id}`} key={lake.lake_id} onClick={() => { if (lake.station_id) activeStation?.select(lake.station_id); }}>
              <LakePreviewMap name={lake.name} lat={lake.centroid_lat} lon={lake.centroid_lon} />
              <span className="lake-card__footer"><strong>{lake.name}</strong><span aria-hidden="true">→</span></span>
            </Link>
          ))}
        </div>}
        {!loading && !error && !lakes.length && <p className="empty-state">No lakes are assigned to your account yet.</p>}
      </section>
    </main>
  );
}
