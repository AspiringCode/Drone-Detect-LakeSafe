import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { supabase, type SupabaseLike } from "../lib/supabase";
import type { Lake } from "../lib/types";
import { useOrientation } from "../lib/useOrientation";
import { AppHeader } from "../components/AppHeader";

export function LakeGridPage({ client = supabase }: { client?: SupabaseLike }) {
  const ref = useOrientation();
  const [lakes, setLakes] = useState<Lake[]>([]);
  useEffect(() => { void client.from("lakes").select("lake_id,name").order("name").then(({ data, error }: { data: Lake[]; error: unknown }) => { if (!error) setLakes(data ?? []); }); }, [client]);
  return (
    <main className="app-page workflow-page">
      <AppHeader active="lakes" contextLabel="Managed lakes" />
      <section ref={ref} className="lake-grid-page">
        <header className="page-heading">
          <p className="kicker">Lake operations</p>
          <h1>Managed lakes</h1>
          <p>Select a lake to open its live operations workspace.</p>
        </header>
        <div className="lake-grid">
          {lakes.map((lake) => <Link className="lake-card" to={`/lakes/${lake.lake_id}`} key={lake.lake_id}>{lake.name}</Link>)}
        </div>
        {!lakes.length && <p className="empty-state">No lakes yet. Complete station setup to add one.</p>}
      </section>
    </main>
  );
}
