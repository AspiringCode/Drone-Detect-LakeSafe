import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { supabase, type SupabaseLike } from "../lib/supabase";
import type { Lake } from "../lib/types";
import { useOrientation } from "../lib/useOrientation";
import { AppHeader } from "../components/AppHeader";
import { LakePreviewMap } from "../components/LakePreviewMap";

export function LakeGridPage({ client = supabase }: { client?: SupabaseLike }) {
  const ref = useOrientation();
  const [searchParams] = useSearchParams();
  const [lakes, setLakes] = useState<Lake[]>([]);
  const stationId = searchParams.get("station");
  const visibleLakes = stationId ? lakes.filter((lake) => lake.org_id === stationId) : lakes;
  useEffect(() => { void client.from("lakes").select("lake_id,org_id,name,centroid_lat,centroid_lon").order("name").then(({ data, error }: { data: Lake[]; error: unknown }) => { if (!error) setLakes(data ?? []); }); }, [client]);
  return (
    <main className="app-page workflow-page">
      <AppHeader active="lakes" contextLabel="Managed lakes" client={client} />
      <section ref={ref} className="lake-grid-page">
        <header className="page-heading">
          <p className="kicker">Lake operations</p>
          <h1>Managed lakes</h1>
          <p>Select a lake to open its live operations workspace.</p>
        </header>
        <div className="lake-grid">
          {visibleLakes.map((lake) => (
            <Link className="lake-card" to={`/lakes/${lake.lake_id}`} key={lake.lake_id}>
              <LakePreviewMap name={lake.name} lat={lake.centroid_lat} lon={lake.centroid_lon} />
              <span className="lake-card__footer"><strong>{lake.name}</strong><span aria-hidden="true">→</span></span>
            </Link>
          ))}
        </div>
        {!visibleLakes.length && <p className="empty-state">No lakes are assigned to this station yet.</p>}
      </section>
    </main>
  );
}
