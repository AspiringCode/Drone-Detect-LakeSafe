import type { Alert } from "./types";
import type { SupabaseLike } from "./supabase";

type LakeReference = { lake_id: string; name: string };
export type LakeAlert = Alert & { lakeId: string; lakeName: string };
export type LakeDataScope = { lakeId: string; name: string; available: boolean; unavailableReason?: string };
export type OperationsOverview = { alerts: LakeAlert[]; lakes: LakeDataScope[] };

export async function loadOperationsAlerts(client: SupabaseLike, fetcher: typeof fetch, apiBaseUrl: string): Promise<LakeAlert[]> {
  return (await loadOperationsOverview(client, fetcher, apiBaseUrl)).alerts;
}

export async function loadOperationsOverview(client: SupabaseLike, fetcher: typeof fetch, apiBaseUrl: string): Promise<OperationsOverview> {
  const { data, error } = await client.from("lakes").select("lake_id,name").order("name");
  if (error) throw error;
  const lakes = (data ?? []) as LakeReference[];
  const token = (await client.auth.getSession()).data.session?.access_token;
  const headers = token ? { Authorization: `Bearer ${token}` } : undefined;
  const groups = await Promise.all(lakes.map(async (lake) => {
    const response = await fetcher(`${apiBaseUrl}/api/lakes/${lake.lake_id}/alerts`, { headers });
    // A missing or unready runtime must not hide records from other assigned lakes.
    if (response.status === 404) return { alerts: [], lake: { lakeId: lake.lake_id, name: lake.name, available: false } };
    if (response.status === 409) {
      const body = await response.json();
      const status = body?.detail?.setup_status;
      if (status === "queued" || status === "failed") return {
        alerts: [], lake: { lakeId: lake.lake_id, name: lake.name, available: false,
          unavailableReason: status === "queued" ? "Lake setup is queued" : "Lake setup needs attention" },
      };
    }
    if (!response.ok) throw new Error(`Alerts unavailable for ${lake.name}`);
    const alerts = await response.json() as Alert[];
    return { alerts: alerts.map((alert) => ({ ...alert, lakeId: lake.lake_id, lakeName: lake.name })), lake: { lakeId: lake.lake_id, name: lake.name, available: true } };
  }));
  return { alerts: groups.flatMap((group) => group.alerts).sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)), lakes: groups.map((group) => group.lake) };
}
