import type { Alert } from "./types";
import type { SupabaseLike } from "./supabase";

type LakeReference = { lake_id: string; name: string };
export type LakeAlert = Alert & { lakeId: string; lakeName: string };

export async function loadOperationsAlerts(client: SupabaseLike, fetcher: typeof fetch, apiBaseUrl: string): Promise<LakeAlert[]> {
  const { data, error } = await client.from("lakes").select("lake_id,name").order("name");
  if (error) throw error;
  const lakes = (data ?? []) as LakeReference[];
  const token = (await client.auth.getSession()).data.session?.access_token;
  const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
  const groups = await Promise.all(lakes.map(async (lake) => {
    const response = await fetcher(`${apiBaseUrl}/api/lakes/${lake.lake_id}/alerts`, { headers });
    // 404 = a lake with no live runtime; anything else is a real failure the page must show.
    if (response.status === 404) return [];
    if (!response.ok) throw new Error(`Alerts unavailable for ${lake.name}`);
    const alerts = await response.json() as Alert[];
    return alerts.map((alert) => ({ ...alert, lakeId: lake.lake_id, lakeName: lake.name }));
  }));
  return groups.flat().sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
}
