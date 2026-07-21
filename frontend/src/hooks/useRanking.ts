import { useEffect, useState } from 'react';
import { fetchRanking } from '../services/statsService';
import type { DeviceRankDto, Bin } from '../types/api';

export interface RankRow {
  name: string;
  points: number;
}

export function useRanking(bins: Bin[], days = 7) {
  const [ranking, setRanking] = useState<RankRow[]>([]);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      fetchRanking(days).then((data: DeviceRankDto[]) => {
        if (!cancelled) {
            const rows = data.map((d) => {
            const bin = bins.find((b) => b.id === d.deviceId);
            return { name: bin?.className ?? bin?.name ?? d.deviceId, points: d.totalCount };
            });
          setRanking(rows.sort((a, b) => b.points - a.points));
        }
      });
    };
    load();
    const timer = window.setInterval(load, 5000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [bins, days]);

  return ranking;
}