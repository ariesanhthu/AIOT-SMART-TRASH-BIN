import { useEffect, useState } from 'react';
import { fetchFullAlerts, resolveFullAlert } from '../services/eventService';
import { fullAlertEventToRow } from '../mappers/alertMapper';
import type { AlertRow, Bin } from '../types/api';

export function useFullAlerts(bins: Bin[]) {
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (bins.length === 0) {
      setAlerts([]);
      setLoading(false);
      return;
    }

    let cancelled = false;

    const load = (showLoading: boolean) => {
      if (showLoading) setLoading(true);
      Promise.all(
        bins.map((bin) =>
          fetchFullAlerts(bin.id).then((events) =>
            events
              .map((event) => fullAlertEventToRow(event, bin))
              .filter((row): row is AlertRow => row !== null)
          )
        )
      )
        .then((rowsPerBin) => {
          if (!cancelled) setAlerts(rowsPerBin.flat());
        })
        .finally(() => {
          if (!cancelled && showLoading) setLoading(false);
        });
    };

    load(true);
    const timer = window.setInterval(() => load(false), 5000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [bins.map((b) => b.id).join(',')]);

  const resolveAlert = async (id: string) => {
    const alert = alerts.find((item) => item.id === id);
    if (!alert) return;
    await resolveFullAlert(alert.binId, alert.id);
    setAlerts((prev) => prev.map((item) => (item.id === id ? { ...item, status: 'resolved' } : item)));
  };

  const markAllResolved = async () => {
    const pending = alerts.filter((item) => item.status === 'pending');
    await Promise.all(pending.map((item) => resolveFullAlert(item.binId, item.id)));
    setAlerts((prev) => prev.map((item) => (item.status === 'pending' ? { ...item, status: 'resolved' } : item)));
  };

  return { alerts, loading, resolveAlert, markAllResolved };
}
