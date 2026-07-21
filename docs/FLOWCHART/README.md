# Flowchart cho các Use Case của AIoT Smart Trash Bin

Nguồn: `[AIOT_NHÓM 2] AIoT_Smart_Trash_Bin_Requirements_Specification.md`, mục 2.3 đến 2.5.

Mỗi Use Case có một file mã Mermaid (`.mmd`) và một ảnh render (`.png`) cùng tên:

| UC | Use Case | Mã Mermaid | PNG |
| --- | --- | --- | --- |
| UC1 | Đưa rác vào vùng chờ | `UC01_dua_rac_vao_vung_cho.mmd` | `UC01_dua_rac_vao_vung_cho.png` |
| UC2 | Phân loại rác bằng Trí tuệ nhân tạo AI | `UC02_phan_loai_rac_bang_AI.mmd` | `UC02_phan_loai_rac_bang_AI.png` |
| UC3 | Điều khiển mở nắp ngăn chứa rác phù hợp | `UC03_dieu_khien_mo_nap_ngan_rac.mmd` | `UC03_dieu_khien_mo_nap_ngan_rac.png` |
| UC4 | Giám sát lượng rác và cập nhật đèn tín hiệu | `UC04_giam_sat_luong_rac_va_LED.mmd` | `UC04_giam_sat_luong_rac_va_LED.png` |
| UC5 | Ghi nhận trạng thái lượng rác | `UC05_ghi_nhan_trang_thai_luong_rac.mmd` | `UC05_ghi_nhan_trang_thai_luong_rac.png` |
| UC6 | Thống kê phân loại rác | `UC06_thong_ke_phan_loai_rac.mmd` | `UC06_thong_ke_phan_loai_rac.png` |
| UC7 | Xem dashboard trạng thái thùng | `UC07_xem_dashboard_trang_thai_thung.mmd` | `UC07_xem_dashboard_trang_thai_thung.png` |

Quy ước màu:

- Vàng: input hoặc actor.
- Xanh dương: device/phần cứng.
- Tím: bước xử lý.
- Cam: điểm quyết định.
- Xanh lá: output.
- Đỏ: cảnh báo hoặc luồng lỗi.
- Xanh nhạt dạng kho dữ liệu: bộ nhớ, server hoặc cơ sở dữ liệu.

Render lại toàn bộ bằng PowerShell:

```powershell
$env:PUPPETEER_SKIP_DOWNLOAD = "true"
$env:PUPPETEER_EXECUTABLE_PATH = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
Get-ChildItem .\FLOWCHART\*.mmd | ForEach-Object {
    npx -y @mermaid-js/mermaid-cli -i $_.FullName -o ($_.FullName -replace '\.mmd$', '.png') -b white -s 2
}
```
