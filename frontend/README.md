# Smart Trash Bin Frontend

Dashboard React 19 + TypeScript + Vite. Dữ liệu thiết bị, sự kiện và thống kê được đọc/ghi qua Spring Boot backend; Firebase Web SDK chỉ dùng để đăng nhập và lấy Firebase ID Token cho request quản trị.

## Cài đặt

Yêu cầu Node.js 20 trở lên. Chạy từ thư mục `frontend`:

```powershell
npm ci
Copy-Item .env.example .env.local
```

Mở `.env.local` và điền cấu hình Firebase Web App. Khi chạy dev, để browser gọi
`/api` cùng origin và để Vite proxy sang backend:

```dotenv
VITE_API_BASE_URL=
BACKEND_URL=http://localhost:8080
```

Không đưa Firebase service-account JSON hoặc `DEVICE_JWT_SECRET` vào frontend. Các giá trị `VITE_FIREBASE_*` là cấu hình Firebase Web App, không phải Admin SDK credential.

## Chạy cùng backend

Terminal 1:

```powershell
cd backend
$env:DEVICE_PROVISIONING_SECRET = "thay-bang-secret-cua-thiet-bi"
$env:DEVICE_JWT_SECRET = "thay-bang-khoa-ngau-nhien-it-nhat-32-ky-tu"
.\gradlew.bat bootRun
```

Terminal 2:

```powershell
cd frontend
npm run dev
```

Truy cập `http://localhost:5173`. Backend chạy tại `http://localhost:8080` và đã cho phép CORS từ cổng 5173.

Nếu backend chạy ở máy khác nhưng frontend vẫn chạy bằng Vite dev server, đổi
`BACKEND_URL`. Browser vẫn gọi `/api` cùng origin nên có thể mở dashboard từ IP LAN:

```dotenv
BACKEND_URL=http://192.168.1.10:8080
```

Sau khi đổi `.env.local`, phải khởi động lại Vite.

## Kiểm tra

```powershell
npm run build
npm run lint
```

Build production nhúng các biến `VITE_*` tại thời điểm build. Khi deploy frontend
và backend khác origin, đặt `VITE_API_BASE_URL` thành URL HTTPS công khai của backend.

Hướng dẫn cấu hình chi tiết backend nằm tại [backend/README.md](../backend/README.md).
