import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import type { Alert } from "./types";

// Falls back to a syntactically valid placeholder so importing this module
// never throws when env vars are unset (e.g. under test). The placeholder is
// never reachable in practice -- real alerts only flow through a properly
// configured VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY.
const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL || "https://placeholder.supabase.co";
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY || "placeholder-anon-key";

export const supabase: SupabaseClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

export function subscribeAlerts(onAlert: (alert: Alert) => void, client: SupabaseClient = supabase): () => void {
  const channel = client
    .channel("alerts-changes")
    .on(
      "postgres_changes",
      { event: "INSERT", schema: "public", table: "alerts" },
      (payload: { new: Alert }) => {
        onAlert(payload.new);
      },
    )
    .subscribe();

  return () => {
    client.removeChannel(channel);
  };
}

export async function fetchAlerts(client: SupabaseClient = supabase): Promise<Alert[]> {
  const { data, error } = await client
    .from("alerts")
    .select("*")
    .order("created_at", { ascending: false });
  if (error) throw error;
  return (data ?? []) as Alert[];
}
