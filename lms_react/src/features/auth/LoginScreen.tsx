import { useEffect, useRef, useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';

import { homeFor, RoutePaths } from '../../app/routePaths';
import { getDb } from '../../data/store';
import { DemoAccounts } from '../../data/seed';
import type { UserRole } from '../../domain/types';
import { RoleLabels } from '../../domain/constants';
import { Icon } from '../../ui/Icon';
import { easeInCubic, easeInOutCubic, interval, lerp } from '../../utils/curves';
import { LoginBrandStage } from './LoginBrandStage';
import { useSession } from './session';

/**
 * 로그인 — features/auth/presentation/login_screen.dart
 *
 * 이 화면만 테마를 따르지 않는다. 밝은 화면에서도 어둡다. 왼쪽에 로그인 칸,
 * 오른쪽에 브랜드 카드 세 장이 떠 있는 시네마틱 크롬 그대로다.
 *
 * 로그인에 성공하면 바로 넘어가지 않는다. 820ms 동안 로그인 칸은 옅어지며
 * 살짝 오므라들고, 가운데 PLAYDATA 패널은 화면 한가운데로 옮겨 가며 부풀어
 * 화면을 삼킨다. 그 끝에서 홈으로 넘어간다 — Dart의 _exitCtrl 연출 그대로다.
 */
const EXIT_MS = 820;
export function LoginScreen() {
  const { signIn, user, loading } = useSession();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [demoOpen, setDemoOpen] = useState(false);
  const [exiting, setExiting] = useState(false);

  const panelRef = useRef<HTMLDivElement>(null);
  const exitRef = useRef(0);
  const frameRef = useRef(0);

  useEffect(
    () => () => {
      window.cancelAnimationFrame(frameRef.current);
    },
    [],
  );

  const hydratedRef = useRef(false);
  useEffect(() => {
    if (loading || hydratedRef.current) return;
    hydratedRef.current = true;
    if (user !== null) navigate(homeFor(user.role), { replace: true });
  }, [loading, user, navigate]);

  const goHome = (role: UserRole) => {
    navigate(homeFor(role), { replace: true });
  };

  /** 로그인 성공 연출. 끝나야 화면을 넘긴다. */
  const enter = (role: UserRole, mustChangePassword: boolean) => {
    if (mustChangePassword) {
      navigate(RoutePaths.changePassword, { replace: true });
      return;
    }

    // 움직임을 줄여 달라고 한 사람에게는 연출 없이 곧장 넘어간다.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      goHome(role);
      return;
    }

    setExiting(true);
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / EXIT_MS);
      exitRef.current = t;

      const panel = panelRef.current;
      if (panel !== null) {
        // 앞 45%에 걸쳐 옅어지고, 앞 40%에 걸쳐 0.94배로 오므라든다.
        panel.style.opacity = String(1 - easeInCubic(interval(t, 0, 0.45)));
        panel.style.transform = `scale(${lerp(1, 0.94, easeInOutCubic(interval(t, 0, 0.4)))})`;
      }

      if (t < 1) frameRef.current = window.requestAnimationFrame(step);
      else goHome(role);
    };
    frameRef.current = window.requestAnimationFrame(step);
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (exiting) return;
    void (async () => {
      const result = await signIn(email, password);
      if (!result.ok) {
        setError(result.message);
        return;
      }
      enter(result.role, result.mustChangePassword);
    })();
  };

  const quickLogin = (address: string) => {
    if (exiting) return;
    setEmail(address);
    setPassword(DemoAccounts.password);
    setError(null);
    void (async () => {
      const result = await signIn(address, DemoAccounts.password);
      if (!result.ok) {
        setError(result.message);
        return;
      }
      enter(result.role, result.mustChangePassword);
    })();
  };

  return (
    <div className={`login${exiting ? ' login--exiting' : ''}`}>
      <div className="login__panel" ref={panelRef}>
        <h1 className="login__title">Log in</h1>
        <p className="login__sub">Welcome to PLAYDATA</p>

        <form className="login__form" onSubmit={submit}>
          <label className="login__field">
            <span className="login__label">사용자 아이디</span>
            <input
              className="login__input"
              type="email"
              value={email}
              autoComplete="username"
              placeholder="이메일을 입력하세요"
              onChange={(e) => {
                setEmail(e.target.value);
                setError(null);
              }}
            />
          </label>

          <label className="login__field">
            <span className="login__label">비밀번호</span>
            <span className="login__input-wrap">
              <input
                className="login__input"
                type={showPassword ? 'text' : 'password'}
                value={password}
                autoComplete="current-password"
                placeholder="비밀번호를 입력하세요"
                onChange={(e) => {
                  setPassword(e.target.value);
                  setError(null);
                }}
              />
              <button
                type="button"
                className="login__eye"
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? '비밀번호 숨기기' : '비밀번호 보기'}
              >
                <Icon name={showPassword ? 'visibility' : 'visibility_off'} size={20} />
              </button>
            </span>
          </label>

          <button type="button" className="login__find">
            아이디/비밀번호 찾기
          </button>

          {error !== null && <p className="login__error">{error}</p>}

          <button type="submit" className="login__submit">
            로그인
          </button>
        </form>

        <button type="button" className="login__demo-toggle" onClick={() => setDemoOpen((v) => !v)}>
          빠른 로그인 (데모)
        </button>

        {demoOpen && (
          <div className="login__demo">
            {(['student', 'instructor', 'admin'] as const).map((role) => {
              const account = getDb().users.find((u) => u.role === role);
              if (account === undefined) return null;
              return (
                <button
                  key={role}
                  type="button"
                  className="login__demo-btn"
                  onClick={() => quickLogin(account.email)}
                >
                  {RoleLabels[role]}
                </button>
              );
            })}
          </div>
        )}

        <p className="login__notice">계정은 관리자가 발급합니다.</p>
      </div>

      <LoginBrandStage exiting={exiting} exitRef={exitRef} />
    </div>
  );
}
