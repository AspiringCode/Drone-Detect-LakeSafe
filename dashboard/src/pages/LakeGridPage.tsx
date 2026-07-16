import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { supabase, type SupabaseLike } from "../lib/supabase";
import type { Lake } from "../lib/types";
import { useOrientation } from "../lib/useOrientation";

export function LakeGridPage({ client = supabase }: { client?: SupabaseLike }) {
  const ref = useOrientation();
  const [lakes, setLakes] = useState<Lake[]>([]);
  useEffect(() => { void client.from("lakes").select("lake_id,name").order("name").then(({ data, error }: { data: Lake[]; error: unknown }) => { if (!error) setLakes(data ?? []); }); }, [client]);
  return <main className="workflow-page"><section ref={ref} className="lake-grid-page"><header className="page-header"><div><p className="kicker">LakeSafe Initiative</p><h1>Your lakes</h1></div></header><div className="lake-grid">{lakes.map((lake) => <Link className="lake-card" to={`/lakes/${lake.lake_id}`} key={lake.lake_id}>{lake.name}</Link>)}</div>{!lakes.length && <p className="empty-state">No lakes yet. Complete station setup to add one.</p>}</section></main>;
}
