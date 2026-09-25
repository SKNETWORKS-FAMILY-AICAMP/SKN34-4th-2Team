import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';

import { useSession } from '../features/auth/session';
import { AttendanceForm } from '../domain/constants';
import { Icon } from '../ui/Icon';
import { StudentTargets } from '../tour/targets';
import { useTourTarget } from '../tour/useTourTarget';
import { isNavSelected, navFor, type NavItem, type NavSection } from './navigation';
import { RoutePaths, homeFor } from './routePaths';
import { AlertPopupHost } from '../features/board/AlertPopupHost';
import { ChatbotHost } from '../features/chatbot/ChatbotHost';
import { useCohorts } from '../data/repository';
import { AppbarCrumbs, CrumbsProvider } from './crumbs';

function RailItem({ item, selected, mini }: { item: NavItem; selected: boolean; mini: boolean }) {
  const ref = useTourTarget(item.targetId ?? '');
  return (
    <NavLink
      to={item.path}
      ref={item.targetId === undefined ? undefined : ref}
      className={`rail__item${selected ? ' rail__item--on' : ''}`}
      // 접힌 메뉴는 아이콘만 보인다. 올려 두면 이름이 뜬다
      title={mini ? item.label : undefined}
      aria-label={mini ? item.label : undefined}
    >
      <Icon name={item.icon} size={20} fill={selected} />
      <span className="rail__label">{item.label}</span>
    </NavLink>
  );
}

function RailSection({ section, location, mini }: { section: NavSection; location: string; mini: boolean }) {
  const hasSelected = section.items.some((i) => isNavSelected(location, i.path));
  const [open, setOpen] = useState(hasSelected);

  // 한 번 들어간 묶음은 열린 채로 둔다. 원본도 그렇게 쌓인다 — 방을 나왔다고
  // 서랍이 저절로 닫히지는 않는다.
  useEffect(() => {
    if (hasSelected) setOpen(true);
  }, [hasSelected]);

  // 접힌 메뉴에는 묶음 제목을 둘 자리가 없다. 아이콘을 모두 늘어놓는다
  if (section.collapsible !== true || mini) {
    return (
      <div className="rail__section">
        {section.items.map((item) => (
          <RailItem key={item.path} item={item} selected={isNavSelected(location, item.path)} mini={mini} />
        ))}
      </div>
    );
  }

  return (
    <div className="rail__section">
      <button type="button" className="rail__group" onClick={() => setOpen((v) => !v)}>
        <span>{section.title}</span>
        <Icon name={open ? 'expand_less' : 'expand_more'} size={18} />
      </button>
      {(open || hasSelected) &&
        section.items.map((item) => (
          <RailItem key={item.path} item={item} selected={isNavSelected(location, item.path)} mini={mini} />
        ))}
    </div>
  );
}

/**
 * 셸 — Flutter의 MainShell / InstructorShell / AdminShell 셋을 하나로 합쳤다.
 *
 * 셋은 메뉴 목록과 홈 경로만 달랐다. Dart에서는 위젯 셋으로 갈라져 있었지만,
 * 여기서는 역할로 메뉴만 갈아 끼운다.
 */
export function Shell() {
  const { user, signOut } = useSession();
  const location = useLocation().pathname;
  const navigate = useNavigate();
  const cohorts = useCohorts();
  const [menuOpen, setMenuOpen] = useState(false);
  // 넓은 화면에서 왼쪽 메뉴를 아이콘만 남기고 접는다(지메일처럼). 다음에 와도 그대로
  const [mini, setMini] = useState(() => {
    try {
      return window.localStorage.getItem('rail_mini') === 'true';
    } catch {
      return false;
    }
  });
  const toggleRail = () => {
    // 좁은 화면에서는 메뉴가 서랍이다. 같은 단추가 서랍을 닫는다
    if (window.matchMedia('(max-width: 900px)').matches) {
      setMenuOpen(false);
      return;
    }
    setMini((v) => {
      try {
        window.localStorage.setItem('rail_mini', String(!v));
      } catch {
        /* 못 남겨도 이번에는 접힌다 */
      }
      return !v;
    });
  };
  // 좁은 화면에서 연 메뉴는 다른 화면으로 가면 닫는다(메뉴 · 로고 · 마이페이지 무엇을 눌러도)
  useEffect(() => {
    setMenuOpen(false);
  }, [location]);

  const attendanceFormRef = useTourTarget(StudentTargets.attendanceForm);
  const myPageRef = useTourTarget(StudentTargets.navMyPage);

  if (user === null) return null;

  const sections = navFor(user.role);
  const home = homeFor(user.role);
  const myPagePath =
    user.role === 'admin'
      ? RoutePaths.adminMyPage
      : user.role === 'instructor'
        ? RoutePaths.instructorMyPage
        : RoutePaths.myPage;

  return (
    <CrumbsProvider>
      <div className={`shell${menuOpen ? ' shell--menu-open' : ''}${mini ? ' shell--rail-mini' : ''}`}>
        <nav className="rail" aria-label="주 메뉴">
          <div className="rail__top">
            <button
              type="button"
              className="rail__toggle"
              onClick={toggleRail}
              aria-label={mini ? '메뉴 펼치기' : '메뉴 접기'}
              title={mini ? '메뉴 펼치기' : '메뉴 접기'}
            >
              <Icon name="menu" size={22} />
            </button>
            <button type="button" className="rail__brand" onClick={() => navigate(home)}>
              <img className="rail__logo" src="/brand/playdata.jpg" alt="" />
              <span className="rail__wordmark">PLAYDATA</span>
            </button>
          </div>

          <div className="rail__items">
            {sections.map((section) => (
              <RailSection key={section.id} section={section} location={location} mini={mini} />
            ))}
          </div>

          <div className="rail__foot">
            <button type="button" className="rail__me" onClick={() => navigate(myPagePath)} title={mini ? user.displayName : undefined}>
              <span className="rail__me-avatar">
                {user.role === 'student' ? <Icon name="person" size={16} /> : user.displayName.slice(0, 1)}
              </span>
              <span className="rail__me-name">{user.displayName}</span>
            </button>
            <button
              type="button"
              className="rail__logout"
              onClick={() => {
                signOut();
                navigate(RoutePaths.login);
              }}
            >
              <Icon name="logout" size={18} />
              <span className="rail__logout-label">로그아웃</span>
            </button>
          </div>
        </nav>

        <div className="main">
          <header className="appbar">
            <button
              type="button"
              className="appbar__menu"
              onClick={() => setMenuOpen((v) => !v)}
              aria-label="메뉴"
            >
              <Icon name="menu" size={22} />
            </button>

            {user.role === 'admin' && (
              <button type="button" className="cohort-select">
                <span>{cohorts.find((c) => c.cohortId === user.cohortId)?.name ?? user.cohortName}</span>
                <Icon name="expand_more" size={18} />
              </button>
            )}

            <AppbarCrumbs />

            <span className="spacer" />

            {user.role === 'student' && (
              <a
                className="appbar__action"
                ref={attendanceFormRef}
                href={AttendanceForm.url}
                target="_blank"
                rel="noreferrer"
              >
                <Icon name="open_in_new" size={18} />
                출결 폼
              </a>
            )}

            <button
              type="button"
              className="profile"
              ref={user.role === 'student' ? myPageRef : undefined}
              onClick={() => navigate(myPagePath)}
            >
              {user.role === 'student' && (
                <span className="profile__avatar">
                  <Icon name="person" size={16} />
                </span>
              )}
              <span className="profile__text">
                <strong>{user.displayName}</strong>
                <span>{user.cohortName}</span>
              </span>
            </button>
          </header>

          <main className="screen" onClick={() => menuOpen && setMenuOpen(false)}>
            <Outlet />
          </main>
        </div>

        <AlertPopupHost />
        <ChatbotHost />
      </div>
    </CrumbsProvider>
  );
}
