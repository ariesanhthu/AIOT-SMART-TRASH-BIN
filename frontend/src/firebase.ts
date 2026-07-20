import { initializeApp } from 'firebase/app';

// Lấy 6 giá trị này ở Firebase Console > Project settings > General > Your apps > Web app (</>).
// KHÔNG phải serviceAccountKey.json (đó là key phía backend/Admin SDK, khác hoàn toàn).
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};

export const firebaseApp = initializeApp(firebaseConfig);