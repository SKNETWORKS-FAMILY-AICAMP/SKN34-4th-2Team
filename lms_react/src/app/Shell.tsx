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

function RailItem({ item, selected }: { item: NavItem; selected: boolean }) {
  const ref = useTourTarget(item.targetId ?? '');
  return (
    <NavLink
      to={item.path}
      ref={item.targetId === undefined ? undefined : ref}
      className={`rail__item${selected ? ' rail__item--on' : ''}`}
    >
      <Icon name={item.icon} size={20} fill={selected} />
      <span className="rail__label">{item.label}</span>
    </NavLink>
  );
}

function RailSection({ section, location }: { section: NavSection; location: string }) {
  const hasSelected = section.items.some((i) => isNavSelected(location, i.path));
  const [open, setOpen] = useState(hasSelected);

  // 한 번 들어간 묶음은 열린 채로 둔다. 원본도 그렇게 쌓인다 — 방을 나왔다고
  // 서랍이 저절로 닫히지는 않는다.
  useEffect(() => {
    if (hasSelected) setOpen(true);
  }, [hasSelected]);

  if (section.collapsible !== true) {
    return (
      <div className="rail__section">
        {section.items.map((item) => (
          <RailItem key={item.path} item={item} selected={isNavSelected(location, item.path)} />
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
          <RailItem key={item.path} item={item} selected={isNavSelected(location, item.path)} />
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
    <div className={`shell${menuOpen ? ' shell--menu-open' : ''}`}>
      <nav className="rail" aria-label="주 메뉴">
        <button type="button" className="rail__brand" onClick={() => navigate(home)}>
          <img className="rail__logo" src="/brand/playdata.jpg" alt="" />
          <span className="rail__wordmark">PLAYDATA</span>
        </button>

        <div className="rail__items">
          {sections.map((section) => (
            <RailSection key={section.id} section={section} location={location} />
          ))}
        </div>

        <div className="rail__foot">
          <button type="button" className="rail__me" onClick={() => navigate(myPagePath)}>
            <span className="rail__me-avatar">
              {user.role === 'student' ? <Icon name="person" size={16} /> : user.displayName.slice(0, 1)}
            </span>
            <span>{user.displayName}</span>
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
            <span>로그아웃</span>
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
  );
}
