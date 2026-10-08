import { useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';

import { useSession } from '../features/auth/session';
import { CohortStatusLabels } from '../domain/constants';
import { selectCohort } from '../data/cohortSelection';
import { Icon } from '../ui/Icon';
import { MoreMenu } from '../ui/MoreMenu';
import { StudentTargets } from '../tour/targets';
import { useTourTarget } from '../tour/useTourTarget';
import { isNavSelected, navFor, type NavItem, type NavSection } from './navigation';
import { RoutePaths, homeFor } from './routePaths';
import { AlertPopupHost } from '../features/board/AlertPopupHost';
import { ChatbotHost } from '../features/chatbot/ChatbotHost';
import { AdminAssistantHost } from '../features/manager/AdminAssistantHost';
import { useCohorts } from '../data/repository';
import { AppbarCrumbs, CrumbsProvider } from './crumbs';

function RailItem({ item, selected, mini }: { item: NavItem; selected: boolean; mini: boolean }) {
  const ref = useTourTarget(item.targetId ?? '');
  return (
    <NavLink
      to={item.path}
      ref={item.targetId === undefined ? undefined : ref}
      className={`rail__item${selected ? ' rail__item--on' : ''}`}
      // 지금 화면의 탭을 다시 눌러도 맨 위로 올라간다(다른 화면으로 가는 경우는 셸이 올린다)
      onClick={() => window.scrollTo(0, 0)}
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
  // 첫 화면에서는 모든 묶음을 펼쳐 둔다(학생 · 강사 · 관리자 모두). 접는 것은 사용자가 한다
  const [open, setOpen] = useState(true);

  // 지금 화면이 든 묶음은 접혀 있었어도 연다
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

/** 이만큼 넘게 한 방향으로 움직여야 숨기고 · 보인다(손가락 떨림에 깜빡이지 않게) */
const BAR_SCROLL_STEP = 8;
/** 맨 위에서 이만큼 안쪽이면 늘 보인다 */
const BAR_TOP_ZONE = 80;

/**
 * 작은 화면(폭 900 이하, 또는 data-autohide-bar 를 단 쌓인 배치)의 상단 막대 — 내려 읽을 때는 숨고, 조금이라도 올리면 다시 나온다
 * (모바일 브라우저 주소창처럼). 고정해 두면 휴대폰에서 이력서 칸이 너무 좁아졌다.
 * 넓은 화면 · 맨 위 근처 · 메뉴를 연 동안 · 화면을 옮긴 직후에는 늘 보인다.
 * 셸에 `shell--bar-hidden` 을 달면 CSS 가 상단 막대와 화면의 붙어 있는 머리글을 함께 올린다.
 */
function useHideOnScroll(location: string, menuOpen: boolean): boolean {
  const [hidden, setHidden] = useState(false);

  useEffect(() => {
    setHidden(false);
  }, [location, menuOpen]);

  useEffect(() => {
    const narrow = window.matchMedia('(max-width: 900px)');
    let last = window.scrollY;
    let frame = 0;
    const update = () => {
      frame = 0;
      const y = window.scrollY;
      // 창이 900 보다 넓어도 화면이 모바일처럼 쌓인 배치를 알리면(data-autohide-bar — 이력서 편집 ·
      // 연습장 튜터의 아래 시트) 똑같이 숨긴다
      const small = narrow.matches || document.querySelector('[data-autohide-bar]') !== null;
      if (!small || menuOpen || y < BAR_TOP_ZONE) {
        setHidden(false);
      } else if (y > last + BAR_SCROLL_STEP) {
        setHidden(true);
      } else if (y < last - BAR_SCROLL_STEP) {
        setHidden(false);
      } else {
        return; // 조금 움직인 것은 쌓아 두고 기준점을 옮기지 않는다
      }
      last = y;
    };
    const onScroll = () => {
      if (frame === 0) frame = window.requestAnimationFrame(update);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    narrow.addEventListener?.('change', onScroll); // 옛 Safari 는 없다 — 없으면 스크롤할 때만 다시 본다
    return () => {
      window.removeEventListener('scroll', onScroll);
      narrow.removeEventListener?.('change', onScroll);
      if (frame !== 0) window.cancelAnimationFrame(frame);
    };
  }, [menuOpen]);

  return hidden;
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
  // 넓은 화면에서 왼쪽 메뉴를 아이콘만 남기고 접는다(지메일처럼). 로그인한 첫 화면은 늘 펼친 채로 시작한다
  const [mini, setMini] = useState(false);
  const toggleRail = () => {
    // 좁은 화면에서는 메뉴가 서랍이다. 같은 단추가 서랍을 닫는다
    if (window.matchMedia('(max-width: 900px)').matches) {
      setMenuOpen(false);
      return;
    }
    setMini((v) => !v);
  };
  // 다른 화면으로 가면 좁은 화면의 메뉴는 닫고, 새 화면은 맨 위부터 보인다
  useEffect(() => {
    setMenuOpen(false);
    window.scrollTo(0, 0);
  }, [location]);
  const barHidden = useHideOnScroll(location, menuOpen);

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
      <div
        className={`shell${menuOpen ? ' shell--menu-open' : ''}${mini ? ' shell--rail-mini' : ''}${
          barHidden ? ' shell--bar-hidden' : ''
        }`}
      >
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
                void signOut();
                navigate(RoutePaths.login, { replace: true });
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
              <div className="appbar__cohort-slot">
                <MoreMenu
                  className="cohort-select"
                  label="기수 선택"
                  align="left"
                  items={cohorts.filter((c) => c.status === 'active').map((c) => ({
                    key: c.cohortId,
                    label: c.name,
                    hint: CohortStatusLabels[c.status],
                    icon: c.cohortId === user.cohortId ? 'check_circle' : 'circle',
                    onSelect: () => selectCohort(user.uid, c.cohortId),
                  }))}
                >
                  <span>{cohorts.find((c) => c.cohortId === user.cohortId)?.name ?? user.cohortName}</span>
                </MoreMenu>
              </div>
            )}

            <AppbarCrumbs />

            <span className="spacer" />

            {user.role === 'student' && (
              <Link className="appbar__action" ref={attendanceFormRef} to={RoutePaths.attendanceRequest}>
                <Icon name="event_busy" size={18} />
                출결 신청
              </Link>
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
        <AdminAssistantHost />
      </div>
    </CrumbsProvider>
  );
}
