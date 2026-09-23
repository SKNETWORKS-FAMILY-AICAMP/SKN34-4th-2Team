import { QueryClientProvider } from '@tanstack/react-query';
import { Suspense, useEffect } from 'react';
import { Navigate, Outlet, Route, Routes, useLocation, useNavigate } from 'react-router-dom';

import { AppearanceProvider } from './appearance';
import { RoutePaths, homeFor } from './routePaths';
import { Shell } from './Shell';
import { BootstrapQuery } from '../data/BootstrapQuery';
import { queryClient } from '../data/queryClient';
import { CartProvider } from '../features/mileage/cart';
import { JobPostingScreen } from '../features/jobs/JobPostingScreen';
import { ReviewDockHost } from '../features/resume/review/ReviewDock';
import { SessionProvider, useSession } from '../features/auth/session';
import { LoginScreen } from '../features/auth/LoginScreen';
import { ChangePasswordScreen } from '../features/auth/ChangePasswordScreen';
import { TourHost } from '../tour/TourHost';
import { TourProvider } from '../tour/useTour';
import { tourFor } from '../tour/tours';
import { prefetchWhenIdle } from './lazyNamed';
import { appRoutes, fullScreenRoutes, prefetchByRole } from './routes';
import { ScreenErrorBoundary, ScreenLoading } from './ScreenLoading';

/** 로그인·비밀번호 변경 가드 — Flutter GoRouter의 redirect 자리 */
function Protected() {
  const { user, loading } = useSession();
  const location = useLocation();

  if (loading && user === null) {
    return (
      <div className="centered-screen" role="status" aria-live="polite">
        <p className="muted">세션 확인 중…</p>
      </div>
    );
  }
  if (user === null) return <Navigate to={RoutePaths.login} replace />;
  if (user.mustChangePassword && location.pathname !== RoutePaths.changePassword) {
    return <Navigate to={RoutePaths.changePassword} replace />;
  }
  return <Outlet />;
}

/** 역할이 맞지 않는 셸에 들어오면 제 홈으로 돌려보낸다. */
function RoleGuard({ allow, children }: { allow: string[]; children: React.ReactNode }) {
  const { user } = useSession();
  if (user === null) {
    return (
      <div className="centered-screen" role="status">
        <p className="muted">화면 준비 중…</p>
      </div>
    );
  }
  if (!allow.includes(user.role)) return <Navigate to={homeFor(user.role)} replace />;
  return <>{children}</>;
}

function ShellWithTour() {
  const { user } = useSession();
  const location = useLocation().pathname;
  const navigate = useNavigate();
  const role = user?.role;

  // 로그인한 역할의 화면 청크를 한가할 때 미리 받아 둔다
  useEffect(() => (role ? prefetchWhenIdle(prefetchByRole[role] ?? []) : undefined), [role]);

  if (user === null) {
    return (
      <div className="centered-screen" role="status">
        <p className="muted">화면 준비 중…</p>
      </div>
    );
  }

  return (
    <TourHost
      key={user.uid}
      tour={tourFor(user.role)}
      uid={user.uid}
      location={location}
      navigate={(path) => navigate(path)}
    >
      <Shell />
    </TourHost>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
    <BootstrapQuery />
    <AppearanceProvider>
      <SessionProvider>
        <TourProvider>
          <CartProvider>
            {/* 첨삭 창은 화면 위 층에 뜬다. 화면을 옮겨도 진행 중인 첨삭이 남는다 */}
            <ReviewDockHost>
            <Routes>
              <Route path={RoutePaths.login} element={<LoginScreen />} />
              {/* 새 탭은 로그인 정보를 넘겨받지 못한다. 공개된 공고라 로그인 밖에 둔다 */}
              <Route path="/jobs/:jobId" element={<JobPostingScreen />} />
              <Route element={<Protected />}>
                <Route path={RoutePaths.changePassword} element={<ChangePasswordScreen />} />
                {fullScreenRoutes.map((route) => (
                  <Route
                    key={route.path}
                    path={route.path}
                    element={
                      <ScreenErrorBoundary>
                        <Suspense fallback={<ScreenLoading />}>
                          {route.roles === undefined ? (
                            route.element
                          ) : (
                            <RoleGuard allow={route.roles}>{route.element}</RoleGuard>
                          )}
                        </Suspense>
                      </ScreenErrorBoundary>
                    }
                  />
                ))}
                <Route element={<ShellWithTour />}>
                  {appRoutes.map((route) => (
                    <Route
                      key={route.path}
                      path={route.path}
                      element={
                        <ScreenErrorBoundary>
                          <Suspense fallback={<ScreenLoading />}>
                            {route.roles === undefined ? (
                              route.element
                            ) : (
                              <RoleGuard allow={route.roles}>{route.element}</RoleGuard>
                            )}
                          </Suspense>
                        </ScreenErrorBoundary>
                      }
                    />
                  ))}
                </Route>
              </Route>
              <Route path="*" element={<Navigate to={RoutePaths.dashboard} replace />} />
            </Routes>
            </ReviewDockHost>
          </CartProvider>
        </TourProvider>
      </SessionProvider>
    </AppearanceProvider>
    </QueryClientProvider>
  );
}
