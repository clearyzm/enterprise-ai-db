'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore, selectIsAuthenticated } from '@/lib/store/auth';

export default function RootPage() {
  const router = useRouter();
  const isAuthenticated = useAuthStore(selectIsAuthenticated);
  const isHydrated = useAuthStore((state) => state.isHydrated);

  useEffect(() => {
    if (!isHydrated) return;
    if (isAuthenticated) {
      router.replace('/datasets');
    } else {
      router.replace('/login');
    }
  }, [isHydrated, isAuthenticated, router]);

  return (
    <div className="flex h-screen items-center justify-center">
      <div className="text-gray-500">加载中...</div>
    </div>
  );
}