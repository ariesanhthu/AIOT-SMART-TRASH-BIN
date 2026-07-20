// Thay thế WASTE_TYPES cũ trong data.ts.
// Khóa PHẢI khớp với backend: Compartment map key = "organic" | "paper" | "plastic"
// (xem UpdateDeviceConfigRequest.java, DailyStat.java). Không dùng "recycle"/"inorganic" nữa.

export type WasteTypeKey = 'organic' | 'paper' | 'plastic';

interface WasteTypeMeta {
  label: string;
  color: string;
  bgClass: string;
}

export const WASTE_TYPES: Record<WasteTypeKey, WasteTypeMeta> = {
  organic: { label: 'Hữu cơ', color: '#22c55e', bgClass: 'badge-success' },
  paper: { label: 'Giấy', color: '#f59e0b', bgClass: 'badge-neutral' },
  plastic: { label: 'Nhựa', color: '#3b82f6', bgClass: 'badge-info' },
};

export const WASTE_TYPE_KEYS: WasteTypeKey[] = ['organic', 'paper', 'plastic'];