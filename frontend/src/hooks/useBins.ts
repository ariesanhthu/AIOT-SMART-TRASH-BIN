import { useCallback, useEffect, useState } from 'react';
import { fetchAllBins } from '../services/deviceService';
import type { Bin } from '../types/api';

export function useBins() {
  const [bins, setBins] = useState<Bin[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback((showLoading = true) => {
    if (showLoading) setLoading(true);
    fetchAllBins()
      .then((data) => {
        setBins(data);
        setError(null);
      })
      .catch((e) => setError(e.message))
      .finally(() => {
        if (showLoading) setLoading(false);
      });
  }, []);

  useEffect(() => {
    reload(true);
    const timer = window.setInterval(() => reload(false), 5000);
    return () => window.clearInterval(timer);
  }, [reload]);

  return { bins, loading, error, reload };
}
