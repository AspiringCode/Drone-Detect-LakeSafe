export type PublicLake = Readonly<{
  lake_id: string;
  name: string;
  approximate_center_geohash: string | null;
  public_status: string;
  refreshed_at: string;
}>;

export type PublicAlert = Readonly<{
  lake_id: string;
  category: string;
  approximate_area_label: string;
  public_status: string;
  occurred_at: string;
  published_at: string;
}>;

export type PublicPatrolPresence = Readonly<{
  lake_id: string;
  generalized_zone: string;
  public_state: string;
  observed_bucket: string;
  published_at: string;
}>;

export type PublicFetcher = (url: string) => Promise<{ ok: boolean; json: () => Promise<unknown> }>;
const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function load<T>(path: string, fetcher: PublicFetcher): Promise<T> {
  const response = await fetcher(`${API}${path}`);
  if (!response.ok) throw new Error("Public lake information is temporarily unavailable.");
  return response.json() as Promise<T>;
}

export const loadPublicLakes = (fetcher: PublicFetcher = fetch) => load<PublicLake[]>("/api/public/lakes", fetcher);
export const loadPublicAlerts = (lakeId: string, fetcher: PublicFetcher = fetch) => load<PublicAlert[]>(`/api/public/lakes/${encodeURIComponent(lakeId)}/alerts`, fetcher);
export const loadPublicPatrolPresence = (lakeId: string, fetcher: PublicFetcher = fetch) => load<PublicPatrolPresence[]>(`/api/public/lakes/${encodeURIComponent(lakeId)}/patrol-presence`, fetcher);
