export interface BinCompartments {
  organic: number;
  recycle: number;
  inorganic: number;
}

export interface Bin {
  id: string;
  name: string;
  location: string;
  online: boolean;
  compartments: BinCompartments;
}

export const BINS: Bin[] = [
  { id: 'A1', name: 'Bin A301', location: 'Classroom A301', online: true, compartments: { organic: 72, recycle: 45, inorganic: 88 } },
  { id: 'A2', name: 'Bin B102', location: 'Hallway B', online: false, compartments: { organic: 30, recycle: 65, inorganic: 20 } },
  { id: 'B1', name: 'Bin C205', location: 'Sân trường', online: true, compartments: { organic: 91, recycle: 78, inorganic: 55 } },
  { id: 'B2', name: 'Bin D101', location: 'Căng tin', online: true, compartments: { organic: 55, recycle: 40, inorganic: 70 } },
  { id: 'C1', name: 'Bin E302', location: 'Thư viện', online: true, compartments: { organic: 25, recycle: 82, inorganic: 15 } },
  { id: 'C2', name: 'Bin F201', location: 'Phòng thể dục', online: false, compartments: { organic: 60, recycle: 60, inorganic: 60 } },
  { id: 'D1', name: 'Bin G102', location: 'Cổng chính', online: true, compartments: { organic: 48, recycle: 33, inorganic: 62 } },
  { id: 'D2', name: 'Bin H301', location: 'Nhà xe', online: true, compartments: { organic: 15, recycle: 25, inorganic: 30 } },
];

export const THRESHOLDS: Record<string, BinCompartments> = {
  A1: { organic: 80, recycle: 85, inorganic: 90 },
  A2: { organic: 80, recycle: 85, inorganic: 90 },
  B1: { organic: 75, recycle: 80, inorganic: 85 },
  B2: { organic: 80, recycle: 80, inorganic: 85 },
  C1: { organic: 85, recycle: 90, inorganic: 90 },
};

export const WASTE_TYPES: Record<string, { label: string, color: string, bgClass: string, labelShort: string }> = {
  organic:   { label: 'Hữu cơ',  color: '#22c55e', bgClass: 'badge-success',  labelShort: 'Hữu cơ' },
  recycle:   { label: 'Nhựa',    color: '#3b82f6', bgClass: 'badge-info',     labelShort: 'Nhựa'  },
  inorganic: { label: 'Giấy',    color: '#f59e0b', bgClass: 'badge-warning',  labelShort: 'Giấy'  },
};

export const REWARDS = [
  { name: 'Lớp 5A1', points: 1240, rank: 1, delta: +30 },
  { name: 'Lớp 4B2', points: 1180, rank: 2, delta: +15 },
  { name: 'Lớp 5C',  points: 1050, rank: 3, delta: +45 },
  { name: 'Lớp 3A',  points:  920, rank: 4, delta: -5 },
  { name: 'Lớp 2B',  points:  875, rank: 5, delta: +10 },
];

export const ALERT_HISTORY = [
  { id: 1, bin: 'A301', compartment: 'Hữu cơ', fill: 95, time: '10:30', date: '24/10/2023', status: 'pending',  type: 'Hữu cơ'  },
  { id: 2, bin: 'B102', compartment: 'Offline', fill: 0, time: '10:28', date: '24/10/2023', status: 'pending', type: 'Vô cơ' },
  { id: 3, bin: 'C205', compartment: 'Giấy',   fill: 82, time: '10:15', date: '24/10/2023', status: 'pending',  type: 'Tái chế'},
  { id: 4, bin: 'D101', compartment: 'Nhựa',   fill: 85, time: '16:20', date: '23/10/2023', status: 'resolved', type: 'Tái chế' },
  { id: 5, bin: 'A301', compartment: 'Nhựa',   fill: 87, time: '14:05', date: '23/10/2023', status: 'resolved', type: 'Tái chế'},
  { id: 6, bin: 'E302', compartment: 'Hữu cơ', fill: 92, time: '11:30', date: '22/10/2023', status: 'resolved', type: 'Hữu cơ' },
  { id: 7, bin: 'C205', compartment: 'Giấy',   fill: 83, time: '10:15', date: '22/10/2023', status: 'resolved', type: 'Vô cơ'  },
];

export const CLASSIFY_HISTORY_A1 = [
  { time: '10:32:14', type: 'recycle',   compartment: 'Nhựa',    accuracy: 94.2, result: 'success' },
  { time: '10:28:07', type: 'organic',   compartment: 'Hữu cơ',  accuracy: 87.5, result: 'success' },
  { time: '10:21:55', type: 'inorganic', compartment: 'Giấy',    accuracy: 91.8, result: 'success' },
  { time: '10:15:30', type: 'recycle',   compartment: 'Nhựa',    accuracy: 72.1, result: 'rejected' },
  { time: '10:10:02', type: 'organic',   compartment: 'Hữu cơ',  accuracy: 96.3, result: 'success' },
  { time: '09:58:44', type: 'inorganic', compartment: 'Giấy',    accuracy: 83.7, result: 'success' },
  { time: '09:45:11', type: 'recycle',   compartment: 'Nhựa',    accuracy: 89.4, result: 'success' },
  { time: '09:32:08', type: 'organic',   compartment: 'Hữu cơ',  accuracy: 92.0, result: 'success' },
];

export const DAILY_DATA = {
  labels: ['03/06','04/06','05/06','06/06','07/06','08/06','09/06'],
  organic:   [45, 52, 38, 61, 55, 48, 67],
  recycle:   [30, 28, 35, 42, 38, 31, 45],
  inorganic: [22, 25, 18, 30, 27, 22, 35],
  accuracy:  [89.2, 91.5, 88.0, 93.1, 90.4, 92.8, 94.2],
};
