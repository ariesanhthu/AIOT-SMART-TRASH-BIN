import React from 'react';

interface TeamMember {
  name: string;
  role: string;
}

const TEAM: TeamMember[] = [
  { name: 'Nguyễn Anh Thư', role: 'Trưởng nhóm' },
  { name: 'Đặng Nguyễn Thành Hiếu', role: 'Backend & Dashboard' },
  { name: 'Nguyễn Phạm Minh Thư', role: 'Frontend & UX' },
  { name: 'Trần Hoàng Nam', role: 'IoT & Phần cứng' },
];

export const SupportPage: React.FC = () => {
  return (
    <section className="page-section">
      <div className="page-header">
        <div>
          <h1>Hỗ trợ</h1>
          <p className="subtitle body-md">Thông tin nhóm phát triển và hỗ trợ hệ thống</p>
        </div>
      </div>

      <div className="grid-2 mb-6">
        <div className="card card-padding">
          <div className="flex items-center gap-3 mb-6">
            <div style={{ width: '36px', height: '36px', background: 'var(--primary-fixed)', borderRadius: 'var(--radius-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <i className="fa-solid fa-users" style={{ color: 'var(--primary)' }}></i>
            </div>
            <div>
              <h2 className="title-sm" style={{ color: 'var(--on-surface)' }}>Nhóm phát triển</h2>
              <p className="body-md" style={{ color: 'var(--outline)', fontSize: '12px' }}>Nhóm 2 — Smart Trash Bin</p>
            </div>
          </div>

          <div className="space-y-3">
            {TEAM.map((member) => (
              <div key={member.name} style={{ padding: '12px 16px', background: 'var(--surface-container-low)', borderRadius: 'var(--radius-lg)', border: '1px solid #E3E8E1', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span className="body-md" style={{ fontWeight: 600, color: 'var(--on-surface)' }}>{member.name}</span>
                <span className="badge badge-pill badge-neutral">{member.role}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="card card-padding">
          <div className="flex items-center gap-3 mb-6">
            <div style={{ width: '36px', height: '36px', background: '#dbeafe', borderRadius: 'var(--radius-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <i className="fa-solid fa-graduation-cap" style={{ color: '#3b82f6' }}></i>
            </div>
            <div>
              <h2 className="title-sm" style={{ color: 'var(--on-surface)' }}>Thông tin môn học</h2>
            </div>
          </div>

          <div className="space-y-4">
            <div>
              <p className="label-caps" style={{ color: 'var(--outline)', marginBottom: '4px' }}>Môn học</p>
              <p className="body-md" style={{ color: 'var(--on-surface)' }}>CSC16106 – An Introduction to Smart Device Programming</p>
            </div>
            <div>
              <p className="label-caps" style={{ color: 'var(--outline)', marginBottom: '4px' }}>Giảng viên hướng dẫn</p>
              <p className="body-md" style={{ color: 'var(--on-surface)' }}>Thầy Võ Hoài Việt</p>
              <p className="body-md" style={{ color: 'var(--on-surface)' }}>Cô Đỗ Thị Thanh Hà</p>
            </div>
          </div>
        </div>
      </div>

      <div className="card card-padding">
        <div className="flex items-center gap-3 mb-4">
          <div style={{ width: '36px', height: '36px', background: '#dcfce7', borderRadius: 'var(--radius-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <i className="fa-solid fa-circle-info" style={{ color: '#22c55e' }}></i>
          </div>
          <h2 className="title-sm" style={{ color: 'var(--on-surface)' }}>Về dự án</h2>
        </div>
        <p className="body-md" style={{ color: 'var(--outline)', lineHeight: 1.7 }}>
          SmartTrashBin là hệ thống thùng rác thông minh hỗ trợ giáo dục phân loại rác,
          nhằm nâng cao ý thức bảo vệ môi trường cho học sinh. Hệ thống sử dụng cảm biến
          và AI để tự động phân loại rác thải (hữu cơ, giấy, nhựa), kết hợp dashboard giám
          sát thời gian thực cho giáo viên và quản trị viên theo dõi tình trạng từng thùng rác
          tại các lớp học.
        </p>
      </div>
    </section>
  );
};