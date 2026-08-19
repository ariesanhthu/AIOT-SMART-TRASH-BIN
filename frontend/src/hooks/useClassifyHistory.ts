import { useEffect, useState } from 'react';
import { fetchClassifyHistory } from '../services/eventService';
import type { ClassifyHistoryRow } from '../types/api';

export function useClassifyHistory(deviceId: string | null) {
  const [rows, setRows] = useState<ClassifyHistoryRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!deviceId) return;

    let cancelled = false;
    const load = (showLoading: boolean) => {
      if (showLoading) setLoading(true);
      fetchClassifyHistory(deviceId)
        .then((data) => {
          if (!cancelled) setRows(data);
        })
        .finally(() => {
          if (!cancelled && showLoading) setLoading(false);
        });
    };

    const initialLoad = window.setTimeout(() => load(true), 0);
    const timer = window.setInterval(() => load(false), 5000);
    return () => {
      cancelled = true;
      window.clearTimeout(initialLoad);
      window.clearInterval(timer);
    };
  }, [deviceId]);

  return {
    rows: deviceId ? rows : [],
    loading: deviceId ? loading : false,
  };
}
