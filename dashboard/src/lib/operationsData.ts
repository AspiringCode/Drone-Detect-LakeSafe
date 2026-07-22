import type { Alert } from "./types";
import type { SupabaseLike } from "./supabase";

type LakeReference = { lake_id: string; name: string };
export type LakeAlert = Alert & { lakeId: string; lakeName: string };

export async function loadOperationsAlerts(client: SupabaseLike, fetcher: typeof fetch, apiBaseUrl: string): Promise<LakeAlert[]> {
  const { data, error } = await client.from("lakes").select("lake_id,name").order("name");
  if (error) throw error;
  const lakes = (data ?? []) as LakeReference[];
  const groups = await Promise.all(lakes.map(async (lake) => {
    const response = await fetcher(`${apiBaseUrl}/api/lakes/${lake.lake_id}/alerts`);
    if (!response.ok) return [];
    const alerts = await response.json() as Alert[];
    return alerts.map((alert) => ({ ...alert, lakeId: lake.lake_id, lakeName: lake.name }));
  }));
  return groups.flat().sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
}
