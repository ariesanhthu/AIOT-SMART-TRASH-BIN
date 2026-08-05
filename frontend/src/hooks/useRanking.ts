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
          const rows = data.map((deviceRank) => {
            const bin = bins.find((item) => item.id === deviceRank.deviceId);
            const binName = bin?.name?.trim();

            return {
              name: binName || deviceRank.deviceId,
              points: deviceRank.totalCount,
            };
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
