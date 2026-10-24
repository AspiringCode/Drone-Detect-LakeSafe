import { useEffect, useState } from "react";
import { loadOperationsOverview, type OperationsOverview } from "../lib/operationsData";
import type { SupabaseLike } from "../lib/supabase";

const API = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function useOperationsRecords(client: SupabaseLike, fetcher: typeof fetch) {
  const [data, setData] = useState<OperationsOverview>({ alerts: [], lakes: [] });
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let current = true;
    setLoading(true); setFailed(false);
    void loadOperationsOverview(client, fetcher, API)
      .then((result) => { if (current) { setData(result); setCheckedAt(new Date().toLocaleString()); } })
      .catch(() => { if (current) setFailed(true); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [client, fetcher, attempt]);
  return { ...data, loading, failed, checkedAt, retry: () => setAttempt((value) => value + 1) };
}
