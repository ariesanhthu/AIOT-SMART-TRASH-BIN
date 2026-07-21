import React, { useState } from 'react';
import { getAuth, signInWithEmailAndPassword } from 'firebase/auth';

export const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await signInWithEmailAndPassword(getAuth(), email, password);
      // Không cần điều hướng thủ công — App.tsx đang lắng nghe
      // useAuthUser, đăng nhập xong sẽ tự chuyển sang dashboard.
    } catch (err) {
      setError('Email hoặc mật khẩu không đúng.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--surface-container-lowest)',
        padding: 16,
      }}
    >
      <div className="card card-padding" style={{ width: '100%', maxWidth: 380 }}>
        <div className="flex items-center gap-3 mb-6">
          <div className="sidebar-logo-icon">
            <i className="fa-solid fa-recycle"></i>
          </div>
          <div>
            <p className="sidebar-logo-title">SmartTrashBin</p>
            <p className="sidebar-logo-subtitle">Đăng nhập quản trị</p>
          </div>
        </div>

        <form onSubmit={handleSubmit}>
          <label className="body-md mb-1" style={{ display: 'block', color: 'var(--on-surface)' }}>
            Email
          </label>
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="input-field mb-4"
            placeholder="admin@truong.edu.vn"
            autoFocus
          />

          <label className="body-md mb-1" style={{ display: 'block', color: 'var(--on-surface)' }}>
            Mật khẩu
          </label>
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="input-field mb-4"
            placeholder="••••••••"
          />

          {error && (
            <p className="body-md mb-4" style={{ color: '#DC2626' }}>
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="input-field"
            style={{
              background: 'var(--primary-container, #1F6D4C)',
              color: '#fff',
              border: 'none',
              cursor: submitting ? 'not-allowed' : 'pointer',
              fontWeight: 600,
            }}
          >
            {submitting ? 'Đang đăng nhập...' : 'Đăng nhập'}
          </button>
        </form>
      </div>
    </div>
  );
};