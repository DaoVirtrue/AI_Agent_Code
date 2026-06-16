import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/store';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { useEffect, useState } from 'react';

interface RouteGuardProps {
  children: React.ReactNode;
  requiredRole?: 'admin' | 'developer' | 'viewer';
}

export function RouteGuard({ children, requiredRole }: RouteGuardProps) {
  const { isAuthenticated, user, checkAuth } = useAuthStore();
  const location = useLocation();
  const [isChecking, setIsChecking] = useState(true);

  useEffect(() => {
    checkAuth().finally(() => setIsChecking(false));
  }, [checkAuth]);

  // Show loading spinner while checking auth status
  if (isChecking) {
    return <LoadingSpinner tip="验证身份信息..." />;
  }

  // Redirect to login if not authenticated
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Check role if required
  if (requiredRole && user?.role !== requiredRole) {
    // Admin role is the highest - allow admins everywhere
    if (user?.role === 'admin') {
      return <>{children}</>;
    }
    return (
      <div className="flex items-center justify-center h-full min-h-[400px]">
        <div className="text-center">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
            访问被拒绝
          </h2>
          <p className="text-gray-500 dark:text-gray-400">
            需要 {requiredRole} 权限才能访问此页面。
          </p>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
