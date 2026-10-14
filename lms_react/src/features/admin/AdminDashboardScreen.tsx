import { Link } from 'react-router-dom';

import { RoutePaths } from '../../app/routePaths';
import {
  useFormTasks,
  usePurchaseRequests,
  useResumes,
  useSubmissions,
} from '../../data/repository';
import { RecordTypeLabels } from '../../domain/constants';
import { toTime } from '../../utils/format';
import { Icon } from '../../ui/Icon';
import { useCurrentUser } from '../auth/session';

/**
 * 관리자 대시보드 — features/admin/presentation/admin_dashboard_screen.dart
 *
 * 처리할 일을 큰 줄로 세워 두고, 오른쪽에 승인 대기 목록을 둔다. 숫자를 늘어놓는
 * 대신 「무엇을 눌러야 하는가」를 먼저 보여 준다.
 */
export function AdminDashboardScreen() {
  const submissions = useSubmissions();
  const resumes = useResumes();
  const requests = usePurchaseRequests();
  const forms = useFormTasks();

  const pendingRecords = submissions.filter((s) => s.status === 'pending');
  const pendingResumes = resumes.filter((r) => r.status === 'feedbackRequested');
  const pendingPurchases = requests.filter((r) => r.status === 'pending');
  const openForms = forms.filter((f) => f.published && toTime(f.dueAt) >= Date.now());

  const menus = [
    {
      icon: 'history',
      title: '기록실 승인 대기',
      sub: `${pendingRecords.length}건 대기`,
      tone: pendingRecords.length > 0 ? 'alert' : undefined,
      to: RoutePaths.adminRecords,
    },
    {
      icon: 'description',
      title: '이력서 검토 대기',
      sub: `${pendingResumes.length}건 대기`,
      tone: pendingResumes.length > 0 ? 'info' : undefined,
      to: RoutePaths.adminResumes,
    },
    { icon: 'calendar_month', title: '기수 관리', to: RoutePaths.adminCohorts },
    { icon: 'groups', title: '학생 관리 — 상담 등록 / 계정', to: RoutePaths.adminStudents },
    { icon: 'fact_check', title: '출석관리 — 기수별 전원 / 폼 반영', to: RoutePaths.adminAttendance },
    { icon: 'event_seat', title: '좌석 배치 — 틀 설정 / 확정', to: RoutePaths.adminSeating },
    {
      icon: 'card_giftcard',
      title: '마일리지 관리',
      sub: `${pendingPurchases.length}건 대기`,
      tone: pendingPurchases.length > 0 ? 'alert' : undefined,
      to: RoutePaths.adminMileage,
    },
    {
      icon: 'ballot',
      title: '설문 · 제출 관리',
      sub: `${openForms.length}개 운영`,
      tone: openForms.length > 0 ? 'alert' : undefined,
      to: RoutePaths.adminFormTasks,
    },
  ];

  return (
    <div className="admin-dash">
      <div className="admin-dash__main">
        <header className="page-head">
          <div>
            <h1 className="page-head__title">관리자 대시보드</h1>
            <p className="page-head__desc">승인 대기 항목을 확인하고 처리하세요.</p>
          </div>
        </header>

        <div className="admin-dash__pair">
          {menus.slice(0, 2).map((menu) => (
            <MenuRow key={menu.to} {...menu} />
          ))}
        </div>

        {menus.slice(2).map((menu) => (
          <MenuRow key={menu.to} {...menu} />
        ))}
      </div>

      <aside className="admin-dash__side">
        <h2 className="approval-panel__title">승인 현황</h2>
        <div className="panel panel--flush">
          {pendingRecords.length === 0 ? (
            <p className="hint" style={{ padding: '0 16px 16px' }}>
              승인 대기 중인 항목이 없습니다.
            </p>
          ) : (
            pendingRecords.map((s) => (
              <Link key={s.id} className="approval-link" to={RoutePaths.adminRecords}>
                <span>
                  <strong>{s.title}</strong>
                  <span className="hint">
                    {RecordTypeLabels[s.type]} · {s.userDisplayName}
                  </span>
                </span>
                <Icon name="chevron_right" size={18} />
              </Link>
            ))
          )}
        </div>
      </aside>
    </div>
  );
}

export function MenuRow({
  icon,
  title,
  sub,
  tone,
  to,
}: {
  icon: string;
  title: string;
  sub?: string;
  tone?: string;
  to: string;
}) {
  return (
    <Link className="menu-row" to={to}>
      <span className="menu-row__icon">
        <Icon name={icon} size={22} />
      </span>
      <span>
        <span className="menu-row__title">{title}</span>
        {sub !== undefined && (
          <span className={`menu-row__sub${tone === undefined ? '' : ` menu-row__sub--${tone}`}`}>
            {sub}
          </span>
        )}
      </span>
      <span className="spacer" />
      <Icon name="chevron_right" size={20} />
    </Link>
  );
}

/** 관리자 셸의 상단 사용자 정보 — 다른 화면에서도 쓴다. */
export function useAdminHeader() {
  return useCurrentUser();
}
