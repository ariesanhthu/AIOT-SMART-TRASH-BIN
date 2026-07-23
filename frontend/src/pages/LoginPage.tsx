import React, { useState } from 'react';
import { getAuth, signInWithEmailAndPassword } from 'firebase/auth';

function authErrorCode(err: unknown): string | undefined {
  if (typeof err === 'object' && err !== null && 'code' in err) {
    const code = (err as { code: unknown }).code;
    return typeof code === 'string' ? code : undefined;
  }
  return undefined;
}

function authErrorMessage(err: unknown): string {
  switch (authErrorCode(err)) {
    case 'auth/invalid-email':
      return 'Email không hợp lệ.';
    case 'auth/user-not-found':
    case 'auth/invalid-credential':
    case 'auth/wrong-password':
      return 'Email hoặc mật khẩu không đúng.';
    case 'auth/too-many-requests':
      return 'Bạn đã thử quá nhiều lần. Vui lòng thử lại sau.';
    case 'auth/network-request-failed':
      return 'Không thể kết nối. Kiểm tra mạng và thử lại.';
    default:
      return 'Đăng nhập thất bại. Vui lòng thử lại.';
  }
}

export const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
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
      setError(authErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-shell">
      <div className="card card-padding login-card">
        <div className="login-brand">
          <div className="sidebar-logo-icon">
            <i className="fa-solid fa-recycle"></i>
          </div>
          <div>
            <p className="sidebar-logo-title">SmartTrashBin</p>
            <p className="sidebar-logo-subtitle">Đăng nhập quản trị</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} aria-busy={submitting}>
          <div className="login-field-group">
            <label htmlFor="login-email" className="body-md login-label">
              Email
            </label>
            <input
              id="login-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="input-field"
              placeholder="admin@truong.edu.vn"
              autoComplete="email"
              autoFocus
              aria-invalid={!!error}
              aria-describedby={error ? 'login-error' : undefined}
            />
          </div>

          <div className="login-field-group">
            <label htmlFor="login-password" className="body-md login-label">
              Mật khẩu
            </label>
            <div className="login-input-wrap">
              <input
                id="login-password"
                type={showPassword ? 'text' : 'password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input-field"
                placeholder="••••••••"
                autoComplete="current-password"
                aria-invalid={!!error}
                aria-describedby={error ? 'login-error' : undefined}
              />
              <button
                type="button"
                className="login-password-toggle"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
              >
                <i className={`fa-solid ${showPassword ? 'fa-eye-slash' : 'fa-eye'}`}></i>
              </button>
            </div>
          </div>

          {error && (
            <p id="login-error" className="login-error" role="alert" aria-live="polite">
              <i className="fa-solid fa-circle-exclamation"></i>
              {error}
            </p>
          )}

          <button type="submit" disabled={submitting} className="btn btn-primary login-submit">
            {submitting && <i className="fa-solid fa-spinner fa-spin"></i>}
            {submitting ? 'Đang đăng nhập...' : 'Đăng nhập'}
          </button>
        </form>
      </div>
    </div>
  );
};
