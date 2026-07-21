import type { EventResponseDto, AlertRow, Bin } from '../types/api';
import type { WasteTypeKey } from '../constants/wasteTypes';

/**
 * GIẢ ĐỊNH cần xác nhận với AI/backend team: với event FULL_ALERT,
 * targetCompartment mang đúng khóa ngăn bị đầy (organic/paper/plastic),
 * và fillPercent[targetCompartment] là % đầy tại thời điểm cảnh báo.
 * Nếu backend đặt tên khác, chỉ cần sửa duy nhất hàm này.
 */
export function fullAlertEventToRow(event: EventResponseDto, bin: Bin): AlertRow | null {
  const compartmentKey = event.targetCompartment as WasteTypeKey | null;
  if (!compartmentKey) return null;

  const timestamp = event.deviceTimestamp ? new Date(event.deviceTimestamp) : null;
  const fill = event.fillPercent?.[compartmentKey] ?? 0;

  return {
    id: event.id,
    binId: bin.id,
    bin: bin.name,
    type: compartmentKey,
    compartment: compartmentKey,
    date: timestamp ? timestamp.toLocaleDateString('vi-VN') : '',
    time: timestamp ? timestamp.toLocaleTimeString('vi-VN') : '',
    fill,
    status: event.alertStatus === 'resolved' ? 'resolved' : 'pending',
  };
}
