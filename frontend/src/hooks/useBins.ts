import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchAllBins } from '../services/deviceService';
import type { Bin } from '../types/api';

const DEVICE_REFRESH_INTERVAL_MS = 2_000;

export function useBins() {
  const [bins, setBins] = useState<Bin[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const latestRequestId = useRef(0);

  const reload = useCallback(async (showLoading = true): Promise<boolean> => {
    const requestId = ++latestRequestId.current;
    if (showLoading) setLoading(true);
    try {
      const data = await fetchAllBins();
      // A slow, older poll must not overwrite fresher fill levels.
      if (requestId !== latestRequestId.current) return false;
      setBins(data);
      setError(null);
      return true;
    } catch (e) {
      if (requestId !== latestRequestId.current) return false;
      setError(e instanceof Error ? e.message : 'Không thể tải cấu hình thiết bị');
      return false;
    } finally {
      if (showLoading && requestId === latestRequestId.current) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    const initialLoad = window.setTimeout(() => void reload(true), 0);
    const timer = window.setInterval(
      () => void reload(false),
      DEVICE_REFRESH_INTERVAL_MS,
    );
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') void reload(false);
    };
    window.addEventListener('focus', refreshWhenVisible);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      window.clearTimeout(initialLoad);
      window.clearInterval(timer);
      window.removeEventListener('focus', refreshWhenVisible);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
      latestRequestId.current += 1;
    };
  }, [reload]);

  return { bins, loading, error, reload };
}
