import type { WasteTypeKey } from '../constants/wasteTypes';

export type ThresholdValues = Partial<Record<WasteTypeKey, number>>;

export function normalizeBackendThreshold(value: number): number | null {
  if (!Number.isFinite(value)) return null;

  const percentage = value <= 1 ? value * 100 : value;
  if (percentage < 0 || percentage > 100) return null;

  return Math.round(percentage);
}

export function getConfiguredThreshold(
  thresholds: ThresholdValues,
  key: WasteTypeKey,
): number | null {
  const value = thresholds[key];
  return value == null || !Number.isFinite(value) ? null : value;
}

export function hasCompleteThresholds(
  thresholds: ThresholdValues,
): thresholds is Record<WasteTypeKey, number> {
  return (
    getConfiguredThreshold(thresholds, 'organic') !== null &&
    getConfiguredThreshold(thresholds, 'paper') !== null &&
    getConfiguredThreshold(thresholds, 'plastic') !== null
  );
}

