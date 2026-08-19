import { useEffect, useRef, useState } from 'react';
import { fetchFullAlerts, resolveFullAlert } from '../services/eventService';
import { fullAlertEventToRow } from '../mappers/alertMapper';
import type { AlertRow, Bin } from '../types/api';

export function useFullAlerts(bins: Bin[]) {
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [loading, setLoading] = useState(true);
  const binsRef = useRef(bins);
  const deviceIds = bins.map((bin) => bin.id).join(',');

  useEffect(() => {
    binsRef.current = bins;
  }, [bins]);

  useEffect(() => {
    if (!deviceIds) return;

    let cancelled = false;

    const load = (showLoading: boolean) => {
      if (showLoading) setLoading(true);
      Promise.all(
        binsRef.current.map((bin) =>
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

    const initialLoad = window.setTimeout(() => load(true), 0);
    const timer = window.setInterval(() => load(false), 5000);
    return () => {
      cancelled = true;
      window.clearTimeout(initialLoad);
      window.clearInterval(timer);
    };
  }, [deviceIds]);

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

  return {
    alerts: bins.length > 0 ? alerts : [],
    loading: bins.length > 0 ? loading : false,
    resolveAlert,
    markAllResolved,
  };
}
