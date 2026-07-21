import { useEffect, useState } from 'react';
import { fetchClassifyHistory } from '../services/eventService';
import type { ClassifyHistoryRow } from '../types/api';

export function useClassifyHistory(deviceId: string | null) {
  const [rows, setRows] = useState<ClassifyHistoryRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!deviceId) return;
    setLoading(true);
    fetchClassifyHistory(deviceId)
      .then(setRows)
      .finally(() => setLoading(false));
  }, [deviceId]);

  return { rows, loading };
}