import { useCallback, useEffect, useState } from 'react';

/** Small data-fetching hook with loading + error states. */
export function useFetch<T>(fetcher: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetcher()
      .then(setData)
      .catch((e: unknown) => {
        const resp = (e as { response?: { status?: number } })?.response;
        setError(resp?.status
          ? `The backend responded with an error (HTTP ${resp.status}).`
          : 'Could not reach the server. Is the backend running?');
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => { load(); }, [load]);
  return { data, loading, error, reload: load };
}
