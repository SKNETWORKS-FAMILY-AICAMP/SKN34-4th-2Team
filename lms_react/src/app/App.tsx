import { Navigate, Outlet, Route, Routes, useLocation, useNavigate } from 'react-router-dom';

import { AppearanceProvider } from './appearance';
import { RoutePaths, homeFor } from './routePaths';
import { Shell } from './Shell';
import { CartProvider } from '../features/mileage/cart';
import { SessionProvider, useSession } from '../features/auth/session';
import { LoginScreen } from '../features/auth/LoginScreen';
import { ChangePasswordScreen } from '../features/auth/ChangePasswordScreen';
import { TourHost } from '../tour/TourHost';
import { TourProvider } from '../tour/useTour';
import { tourFor } from '../tour/tours';
import { appRoutes, fullScreenRoutes } from './routes';

/** 로그인·비밀번호 변경 가드 — Flutter GoRouter의 redirect 자리 */
function Protected() {
  const { user, loading } = useSession();
  const location = useLocation();

  if (loading) return null;
  if (user === null) return <Navigate to={RoutePaths.login} replace />;
  if (user.mustChangePassword && location.pathname !== RoutePaths.changePassword) {
    return <Navigate to={RoutePaths.changePassword} replace />;
  }
  return <Outlet />;
}

/** 역할이 맞지 않는 셸에 들어오면 제 홈으로 돌려보낸다. */
function RoleGuard({ allow, children }: { allow: string[]; children: React.ReactNode }) {
  const { user } = useSession();
  if (user === null) return null;
  if (!allow.includes(user.role)) return <Navigate to={homeFor(user.role)} replace />;
  return <>{children}</>;
}

function ShellWithTour() {
  const { user } = useSession();
  const location = useLocation().pathname;
  const navigate = useNavigate();

  if (user === null) return null;

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
    <AppearanceProvider>
      <SessionProvider>
        <TourProvider>
          <CartProvider>
            <Routes>
              <Route path={RoutePaths.login} element={<LoginScreen />} />
              <Route element={<Protected />}>
                <Route path={RoutePaths.changePassword} element={<ChangePasswordScreen />} />
                {fullScreenRoutes.map((route) => (
                  <Route
                    key={route.path}
                    path={route.path}
                    element={
                      route.roles === undefined ? (
                        route.element
                      ) : (
                        <RoleGuard allow={route.roles}>{route.element}</RoleGuard>
                      )
                    }
                  />
                ))}
                <Route element={<ShellWithTour />}>
                  {appRoutes.map((route) => (
                    <Route
                      key={route.path}
                      path={route.path}
                      element={
                        route.roles === undefined ? (
                          route.element
                        ) : (
                          <RoleGuard allow={route.roles}>{route.element}</RoleGuard>
                        )
                      }
                    />
                  ))}
                </Route>
              </Route>
              <Route path="*" element={<Navigate to={RoutePaths.dashboard} replace />} />
            </Routes>
          </CartProvider>
        </TourProvider>
      </SessionProvider>
    </AppearanceProvider>
  );
}
