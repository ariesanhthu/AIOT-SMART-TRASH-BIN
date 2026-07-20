import { useEffect, useState } from 'react';
import { getAuth, onAuthStateChanged, signOut, type User } from 'firebase/auth';

export function useAuthUser() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(getAuth(), (u) => {
      setUser(u);
      setLoading(false);
    });
    return unsubscribe;
  }, []);

  const logout = () => signOut(getAuth());

  return { user, loading, logout };
}