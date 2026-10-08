import './cohortForm.css';
import { useEffect, useRef, useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import {
  RoutePaths,
  adminCohortEditPath,
  adminStudentDetailPath,
  adminStudentEditPath,
} from '../../app/routePaths';
import {
  createCohort,
  deleteCohort,
  getCohortDeletionPreview,
  getCohortDocuments,
  uploadCohortDocument,
  createUser,
  updateCohort,
  setCohortStatus,
  updateUser,
  useAttendanceOfUser,
  useCohorts,
  useInstructors,
  useMileageTransactions,
  useMySubmissions,
  useStudents,
  useUser,
  resetUserPassword,
  saveStudentIntake,
  type AccountCredentials,
  type CohortDocumentStatus,
  type CohortDeletionPreview,
} from '../../data/repository';
import { selectCohort } from '../../data/cohortSelection';
import { readApiError } from '../../data/http';
import { nextId } from '../../data/store';
import { CohortStatusLabels, RecordTypeLabels, attendanceLabel } from '../../domain/constants';
import type { Cohort, CohortStatus, StudentIntake, User } from '../../domain/types';
import {
  Badge,
  Button,
  Card,
  DataTable,
  Dialog,
  EmptyState,
  Field,
  PageHeader,
  Row,
  Select,
  Spacer,
  StatTile,
  TabPage,
  Tabs,
  TextArea,
  TextInput,
  Toggle,
} from '../../ui/components';
import { formatDate, formatDateTime, formatMileage } from '../../utils/format';
import { MoreMenu } from '../../ui/MoreMenu';
import { Icon } from '../../ui/Icon';
import { dateKeyOf } from '../../data/seed';
import { useCurrentUser } from '../auth/session';
import { StudentCounselSection } from './AdminCounselScreens';
import { CredentialDialog } from './CredentialDialog';

// 내 PC 시각 기준 — toISOString 은 세계 표준시라 하루 어긋난다
const toInputDate = (d?: Date) => (d === undefined ? '' : dateKeyOf(d));

/** 학생 관리 — admin_students_screen.dart */
export function AdminStudentsScreen() {
  const user = useCurrentUser();
  const students = useStudents(user.cohortId);
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<'active' | 'inactive'>('active');

  const q = query.trim().toLowerCase();
  const rows = students
    .filter((s) => (filter === 'active' ? s.isActive : !s.isActive))
    .filter(
      (s) =>
        q === '' || s.displayName.toLowerCase().includes(q) || s.email.toLowerCase().includes(q),
    );

  return (
    <TabPage
      title="학생 관리"
      description="상담 등록으로 계정을 만들고, 재원 · 퇴소를 관리합니다."
      actions={
        <Link className="btn btn--filled btn--md" to={RoutePaths.adminStudentsCreate}>
          <Icon name="person_add" size={18} />
          학생 등록
        </Link>
      }
      tabs={
        <Tabs
          active={filter}
          onChange={(id) => setFilter(id as 'active' | 'inactive')}
          items={[
            { id: 'active', label: '재원', count: students.filter((s) => s.isActive).length },
            { id: 'inactive', label: '퇴소', count: students.filter((s) => !s.isActive).length },
          ]}
          trailing={
            <label className="search-bar search-bar--sm">
              <Icon name="search" size={20} />
              <input
                className="search-bar__input"
                value={query}
                placeholder="학생 이름 또는 이메일 검색"
                onChange={(e) => setQuery(e.target.value)}
              />
              {query !== '' && (
                <button
                  type="button"
                  className="icon-btn"
                  aria-label="검색어 지우기"
                  onClick={() => setQuery('')}
                >
                  <Icon name="close" size={18} />
                </button>
              )}
            </label>
          }
        />
      }
    >
      {rows.length === 0 ? (
        <div className="list-page__empty">
          <Icon name="groups" size={44} />
          <p>{filter === 'active' ? '등록된 학생이 없습니다' : '퇴소 처리된 학생이 없습니다'}</p>
          {filter === 'active' && (
            <Link className="btn btn--outline btn--md" to={RoutePaths.adminStudentsCreate}>
              <Icon name="person_add" size={18} />첫 학생 상담 등록
            </Link>
          )}
        </div>
      ) : (
        <div className="list-page__body">
          {rows.map((s) => (
            <button
              key={s.uid}
              type="button"
              className={`people-row${s.isActive ? '' : ' people-row--out'}`}
              onClick={() => navigate(adminStudentDetailPath(s.uid))}
            >
              <span className="people-row__avatar">{s.displayName.slice(0, 1)}</span>
              <span className="people-row__body">
                <strong>{s.displayName}</strong>
                <span className="people-row__email">{s.email}</span>
                <span className="people-row__major" title={s.educationMajor}>
                  {s.educationMajor ?? '전공 미입력'}
                </span>
                <span className="hint">
                  {s.seatNumber === undefined ? '좌석 미배정' : `${s.seatNumber}번`} ·{' '}
                  {formatMileage(s.mileageBalance)}
                </span>
              </span>
              {s.isActive ? (
                s.mustChangePassword ? (
                  <Icon name="chevron_right" size={20} />
                ) : (
                  <span className="people-row__chip">PW 변경됨</span>
                )
              ) : (
                <span className="people-row__chip">퇴소</span>
              )}
            </button>
          ))}
        </div>
      )}
    </TabPage>
  );
}

/** 학생 상세 — admin_student_detail_screen.dart */
export function AdminStudentDetailScreen() {
  const { studentUid } = useParams<{ studentUid: string }>();
  const student = useUser(studentUid);
  const attendance = useAttendanceOfUser(studentUid ?? '');
  const submissions = useMySubmissions(studentUid ?? '');
  const transactions = useMileageTransactions(studentUid);
  const navigate = useNavigate();
  const account = useAccountActions();

  if (student === undefined) {
    return (
      <div className="screen__inner">
        <Card>
          <EmptyState message="학생을 찾을 수 없습니다" />
        </Card>
      </div>
    );
  }

  const present = attendance.filter((a) => a.status === 'present').length;

  return (
    <div className="screen__inner">
      <PageHeader
        title={student.displayName}
        description={`${student.email} · ${student.cohortName}`}
        actions={
          <>
            <Button variant="outline" onClick={() => navigate(adminStudentEditPath(student.uid))}>
              정보 수정
            </Button>
            <Button variant="outline" onClick={() => account.askReset(student)}>
              비밀번호 재발급
            </Button>
            <Button variant={student.isActive ? 'danger' : 'filled'} onClick={() => account.askActive(student)}>
              {student.isActive ? '퇴소 처리' : '복학 처리'}
            </Button>
          </>
        }
      />
      {account.dialogs}

      <div className="grid grid--4">
        <StatTile label="좌석" value={`${student.seatNumber ?? '-'}번`} />
        <StatTile
          label="출석률"
          value={attendance.length === 0 ? '-' : `${Math.round((present / attendance.length) * 100)}%`}
          sub={`${present} / ${attendance.length}일`}
          tone="success"
        />
        <StatTile label="제출 기록" value={submissions.length} />
        <StatTile label="마일리지" value={formatMileage(student.mileageBalance)} tone="primary" />
      </div>

      <div className="grid grid--2">
        <Card title="프로필">
          <ul className="list">
            <li className="list__item">
              <span className="hint">개인 이메일</span>
              <Spacer />
              <span>{student.personalEmail ?? '-'}</span>
            </li>
            <li className="list__item">
              <span className="hint">생년월일</span>
              <Spacer />
              <span>{student.birthDate ?? '-'}</span>
            </li>
            <li className="list__item">
              <span className="hint">기술 스택</span>
              <Spacer />
              <span>{student.skills.join(', ') || '-'}</span>
            </li>
            <li className="list__item">
              <span className="hint">희망 직무</span>
              <Spacer />
              <span>{student.jobPreferences.targetRoles.join(', ') || '-'}</span>
            </li>
          </ul>
        </Card>

        <Card padded={false} title="최근 출결">
          <DataTable
            rows={attendance.slice(0, 8)}
            rowKey={(a) => a.id}
            empty="출결 기록이 없습니다."
            columns={[
              { key: 'date', header: '날짜', render: (a) => a.dateKey },
              { key: 'status', header: '상태', render: (a) => <Badge tone="neutral">{attendanceLabel(a.status)}</Badge> },
              { key: 'in', header: '입실', render: (a) => a.checkInTime ?? '-' },
              { key: 'out', header: '퇴실', render: (a) => a.checkOutTime ?? '-' },
            ]}
          />
        </Card>
      </div>

      <StudentCounselSection student={student} />

      <Card padded={false} title="제출 기록">
        <DataTable
          rows={submissions}
          rowKey={(s) => s.id}
          empty="제출 기록이 없습니다."
          columns={[
            { key: 'type', header: '종류', width: '110px', render: (s) => RecordTypeLabels[s.type] },
            { key: 'title', header: '제목', render: (s) => s.title },
            { key: 'status', header: '상태', width: '90px', render: (s) => s.status },
            { key: 'at', header: '제출', width: '160px', render: (s) => formatDateTime(s.submittedAt) },
          ]}
        />
      </Card>

      <Card padded={false} title="마일리지 내역">
        <DataTable
          rows={transactions}
          rowKey={(t) => t.id}
          empty="마일리지 내역이 없습니다."
          columns={[
            { key: 'at', header: '일시', width: '160px', render: (t) => formatDateTime(t.createdAt) },
            { key: 'reason', header: '내용', render: (t) => t.reason },
            {
              key: 'amount',
              header: '변동',
              align: 'right',
              render: (t) => (
                <strong style={{ color: t.amount > 0 ? 'var(--success)' : 'var(--error)' }}>
                  {t.amount > 0 ? '+' : ''}
                  {t.amount.toLocaleString()}
                </strong>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}

/**
 * 학생 상담 문항 — admin_student_create_screen.dart 의 다섯 묶음 그대로.
 * 등록할 때만 받는다(수정 화면에는 원본에도 없다).
 */
const INTAKE_SECTIONS: {
  title: string;
  fields: { key: keyof StudentIntake; label: string; hint?: string }[];
}[] = [
  {
    title: '1. 기본 인적 사항',
    fields: [
      { key: 'educationMajor', label: '학력 / 전공' },
      { key: 'currentStatus', label: '현재 상태', hint: '재학, 휴학, 직장인, 구직 등' },
      { key: 'weeklyStudyHours', label: '주당 학습 가능 시간', hint: '예: 평일 3시간, 주말 6시간' },
    ],
  },
  {
    title: '2. 기술 역량 및 사전 준비도',
    fields: [
      { key: 'programmingLevel', label: '프로그래밍 언어 숙련도' },
      { key: 'collaborationTools', label: 'Git 등 협업 툴' },
      { key: 'aiLlmExperience', label: 'AI/LLM 활용 경험' },
    ],
  },
  {
    title: '3. 지원 동기 및 수료 후 목표',
    fields: [
      { key: 'motivation', label: '지원 동기' },
      { key: 'desiredRole', label: '희망 직무' },
      { key: 'postCompletionGoal', label: '수료 후 목표', hint: '취업, 창업, 역량 강화 등' },
    ],
  },
  {
    title: '4. 수상 경력 및 프로젝트 경험',
    fields: [
      { key: 'awards', label: '수상 경력', hint: '해커톤, 경진대회 등' },
      { key: 'projectLinks', label: '주요 프로젝트 링크', hint: 'GitHub, Notion 등' },
    ],
  },
  {
    title: '5. 협업 성향',
    fields: [
      { key: 'teamRole', label: '팀 프로젝트 역할' },
      { key: 'selfLearningStyle', label: '자기주도 학습 방식' },
      { key: 'slumpOvercomeExperience', label: '슬럼프 극복 경험' },
    ],
  },
];

const EMPTY_INTAKE: StudentIntake = {
  educationMajor: '',
  currentStatus: '',
  weeklyStudyHours: '',
  programmingLevel: '',
  collaborationTools: '',
  aiLlmExperience: '',
  motivation: '',
  desiredRole: '',
  postCompletionGoal: '',
  awards: '',
  projectLinks: '',
  teamRole: '',
  selfLearningStyle: '',
  slumpOvercomeExperience: '',
};

/** 학생 등록·수정 — admin_student_create_screen.dart / admin_student_edit_screen.dart */
export function AdminStudentFormScreen() {
  const { studentUid } = useParams<{ studentUid: string }>();
  const existing = useUser(studentUid);
  const admin = useCurrentUser();
  const navigate = useNavigate();

  const [displayName, setDisplayName] = useState(existing?.displayName ?? '');
  const [email, setEmail] = useState(existing?.email ?? '');
  const [personalEmail, setPersonalEmail] = useState(existing?.personalEmail ?? '');
  const [seatNumber, setSeatNumber] = useState(String(existing?.seatNumber ?? ''));
  const [birthDate, setBirthDate] = useState(existing?.birthDate ?? '');
  const [isActive, setActive] = useState(existing?.isActive ?? true);
  const [intake, setIntake] = useState<StudentIntake>(EMPTY_INTAKE);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [created, setCreated] = useState<AccountCredentials | null>(null);

  const setField = (key: keyof StudentIntake, value: string) =>
    setIntake((current) => ({ ...current, [key]: value }));

  const save = async () => {
    if (displayName.trim() === '') {
      setError('이름을 입력해 주세요.');
      return;
    }
    if (existing === undefined) {
      // 원본(createStudentAccount)처럼 구글폼 매칭용 개인 이메일은 꼭 받는다. 로그인 이메일은 비우면 서버가 만든다
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(personalEmail.trim())) {
        setError('구글폼 매칭에 쓸 개인 이메일을 입력해 주세요.');
        return;
      }
      setSaving(true);
      setError(null);
      try {
        const account = await createUser({
          uid: nextId('user'),
          email: email.trim(),
          personalEmail: personalEmail.trim(),
          displayName: displayName.trim(),
          role: 'student',
          cohortId: admin.cohortId,
          cohortName: admin.cohortName,
          isActive,
          // 새 계정은 임시 비밀번호로 만들고 첫 로그인에서 바꾸게 한다.
          mustChangePassword: true,
          skills: [],
          socialLinks: {},
          jobPreferences: { targetRoles: [], regions: [], employmentTypes: [] },
          birthDate: birthDate === '' ? undefined : birthDate,
          mileageBalance: 0,
          createdAt: new Date(),
        });
        if (Object.values(intake).some((v) => v.trim() !== '')) saveStudentIntake(account.uid, intake);
        setCreated(account);
      } catch (e) {
        setError(await readApiError(e));
      } finally {
        setSaving(false);
      }
      return;
    }
    if (email.trim() === '') {
      setError('로그인 이메일을 비울 수 없습니다.');
      return;
    }
    updateUser(existing.uid, {
      displayName: displayName.trim(),
      email: email.trim(),
      personalEmail: personalEmail.trim(),
      seatNumber: seatNumber === '' ? undefined : Number(seatNumber),
      birthDate: birthDate === '' ? undefined : birthDate,
      isActive,
    });
    navigate(adminStudentDetailPath(existing.uid));
  };

  return (
    <div className="screen__inner">
      <PageHeader title={existing === undefined ? '학생 등록' : '학생 정보 수정'} />
      <Card>
        <div className="grid grid--2">
          <Field label="이름 *">
            <TextInput value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </Field>
          <Field
            label="로그인 이메일"
            hint={existing === undefined ? '비워 두면 무작위 주소(@playdata.co.kr)를 만듭니다.' : undefined}
          >
            <TextInput value={email} onChange={(e) => setEmail(e.target.value)} placeholder="student@playdata.co.kr" />
          </Field>
          <Field label={existing === undefined ? '개인 이메일 (Gmail) *' : '개인 이메일'} hint="구글폼 제출 매칭에 씁니다.">
            <TextInput
              value={personalEmail}
              onChange={(e) => setPersonalEmail(e.target.value)}
              placeholder="student@gmail.com"
            />
          </Field>
          {existing && (
            <Field label="좌석 번호">
              <TextInput type="number" value={seatNumber} onChange={(e) => setSeatNumber(e.target.value)} />
            </Field>
          )}
          <Field label="생년월일">
            <TextInput type="date" value={birthDate} onChange={(e) => setBirthDate(e.target.value)} />
          </Field>
        </div>
        <Toggle checked={isActive} onChange={setActive} label="재적 상태" />
        {existing === undefined && (
          <div className="callout">
            등록하면 임시 비밀번호로 계정이 만들어지고, 첫 로그인에서 비밀번호를 바꾸게 됩니다.
          </div>
        )}
        {error !== null && (
          <div className="callout callout--error" role="alert">
            {error}
          </div>
        )}
      </Card>

      {existing === undefined &&
        INTAKE_SECTIONS.map((section) => (
          <Card key={section.title} title={section.title}>
            {section.fields.map(({ key, label, hint }) => (
              <Field key={String(key)} label={label} hint={hint}>
                <TextArea rows={2} value={intake[key]} onChange={(e) => setField(key, e.target.value)} />
              </Field>
            ))}
          </Card>
        ))}

      <Card>
        <Row>
          <Spacer />
          <Button variant="outline" onClick={() => navigate(RoutePaths.adminStudents)}>
            취소
          </Button>
          <Button onClick={() => void save()} disabled={saving}>
            {existing === undefined ? '아이디 · 비밀번호 생성하기' : '저장'}
          </Button>
        </Row>
      </Card>

      {created !== null && (
        <CredentialDialog
          title="계정 생성 완료"
          credentials={created}
          onClose={() => navigate(adminStudentDetailPath(created.uid))}
        />
      )}
    </div>
  );
}

/** 강사 관리 — admin_instructors_screen.dart */
export function AdminInstructorsScreen() {
  const all = useInstructors();
  const account = useAccountActions();
  // 학생 관리(재원 · 퇴소)와 같은 구조 — 활성 · 비활성으로 나눠 본다
  const [filter, setFilter] = useState<'active' | 'inactive'>('active');
  const instructors = all.filter((i) => (filter === 'active' ? i.isActive : !i.isActive));

  return (
    <TabPage
      title="강사 관리"
      description="강사 계정을 만들고 비밀번호 재발급 · 활성 여부를 관리합니다."
      actions={
        <Link className="btn btn--filled btn--md" to={RoutePaths.adminInstructorsCreate}>
          <Icon name="person_add" size={18} />
          강사 등록
        </Link>
      }
      tabs={
        <Tabs
          active={filter}
          onChange={(id) => setFilter(id as 'active' | 'inactive')}
          items={[
            { id: 'active', label: '활성', count: all.filter((i) => i.isActive).length },
            { id: 'inactive', label: '비활성', count: all.filter((i) => !i.isActive).length },
          ]}
        />
      }
    >
      {instructors.length === 0 ? (
        <div className="list-page__empty">
          <Icon name="badge" size={44} />
          <p>{filter === 'active' ? '등록된 강사가 없습니다' : '비활성 강사가 없습니다'}</p>
        </div>
      ) : (
        <div className="list-page__body">
          {instructors.map((i) => (
            <div key={i.uid} className="people-row people-row--plain">
              <span className="people-row__avatar">{i.displayName.slice(0, 1)}</span>
              <span className="people-row__body">
                <strong>{i.displayName}</strong>
                <span className="people-row__email">
                  {i.email} · {i.cohortName} · {i.isActive ? '활성' : '비활성'}
                </span>
              </span>
              <MoreMenu
                icon="more_vert"
                items={[
                  {
                    key: 'reset',
                    label: '비밀번호 재발급',
                    onSelect: () => account.askReset(i),
                  },
                  {
                    key: 'toggle',
                    label: i.isActive ? '비활성으로' : '활성으로',
                    danger: i.isActive,
                    onSelect: () => account.askActive(i),
                  },
                ]}
              />
            </div>
          ))}
        </div>
      )}
      {account.dialogs}
    </TabPage>
  );
}

/**
 * 비밀번호 재발급 · 퇴소(비활성) 확인 창 — 학생 상세와 강사 목록이 같이 쓴다.
 * 재발급은 resetStudentPassword / resetInstructorPassword, 활성 바꾸기는 set*ActiveStatus 자리다.
 */
function useAccountActions() {
  const [resetTarget, setResetTarget] = useState<User | null>(null);
  const [activeTarget, setActiveTarget] = useState<User | null>(null);
  const [issued, setIssued] = useState<AccountCredentials | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const who = (u: User) => (u.role === 'instructor' ? `${u.displayName} 강사` : `${u.displayName} 학생`);
  const activeLabel = (u: User) =>
    u.role === 'student' ? (u.isActive ? '퇴소' : '복학') : u.isActive ? '비활성' : '활성';
  const close = () => {
    setResetTarget(null);
    setActiveTarget(null);
    setError(null);
  };
  const reset = async (u: User) => {
    setBusy(true);
    setError(null);
    try {
      setIssued(await resetUserPassword(u.uid));
      setResetTarget(null);
    } catch (e) {
      setError(await readApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const dialogs = (
    <>
      {resetTarget !== null && (
        <Dialog
          title="비밀번호 재발급"
          onClose={close}
          actions={
            <>
              <Button variant="text" onClick={close}>
                취소
              </Button>
              <Button onClick={() => void reset(resetTarget)} disabled={busy}>
                재발급
              </Button>
            </>
          }
        >
          <p>{who(resetTarget)}의 비밀번호를 재발급할까요? 지금 비밀번호로는 더 이상 로그인할 수 없습니다.</p>
          {error !== null && (
            <div className="callout callout--error" role="alert">
              {error}
            </div>
          )}
        </Dialog>
      )}
      {activeTarget !== null && (
        <Dialog
          title={`${activeLabel(activeTarget)} 처리`}
          onClose={close}
          actions={
            <>
              <Button variant="text" onClick={close}>
                취소
              </Button>
              <Button
                variant={activeTarget.isActive ? 'danger' : 'filled'}
                onClick={() => {
                  updateUser(activeTarget.uid, { isActive: !activeTarget.isActive });
                  close();
                }}
              >
                {activeLabel(activeTarget)}
              </Button>
            </>
          }
        >
          <p>
            {who(activeTarget)}을(를) {activeLabel(activeTarget)} 처리할까요?{' '}
            {activeTarget.isActive ? '로그인할 수 없게 됩니다.' : '다시 로그인할 수 있게 됩니다.'}
          </p>
        </Dialog>
      )}
      {issued !== null && (
        <CredentialDialog title="비밀번호 재발급 완료" credentials={issued} onClose={() => setIssued(null)} />
      )}
    </>
  );

  return { askReset: setResetTarget, askActive: setActiveTarget, dialogs };
}

/** 강사 등록 — admin_instructor_create_screen.dart */
export function AdminInstructorCreateScreen() {
  const admin = useCurrentUser();
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [created, setCreated] = useState<AccountCredentials | null>(null);

  const save = async () => {
    if (displayName.trim() === '') {
      setError('이름을 입력해 주세요.');
      return;
    }
    const newInstructor: User = {
      uid: nextId('user'),
      email: email.trim(),
      displayName: displayName.trim(),
      role: 'instructor',
      cohortId: admin.cohortId,
      cohortName: admin.cohortName,
      isActive: true,
      mustChangePassword: true,
      skills: [],
      socialLinks: {},
      jobPreferences: { targetRoles: [], regions: [], employmentTypes: [] },
      mileageBalance: 0,
      createdAt: new Date(),
    };
    setSaving(true);
    setError(null);
    try {
      setCreated(await createUser(newInstructor));
    } catch (e) {
      setError(await readApiError(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="screen__inner">
      <PageHeader title="강사 등록" />
      <Card>
        <Field label="이름" error={error ?? undefined}>
          <TextInput value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </Field>
        <Field label="로그인 이메일 (선택)" hint="비워 두면 무작위 주소(@playdata.co.kr)를 만듭니다.">
          <TextInput value={email} onChange={(e) => setEmail(e.target.value)} placeholder="instructor@playdata.co.kr" />
        </Field>
        <div className="callout">임시 비밀번호로 계정이 만들어지고, 첫 로그인에서 비밀번호를 바꾸게 됩니다.</div>
        <Row>
          <Spacer />
          <Button variant="outline" onClick={() => navigate(RoutePaths.adminInstructors)}>
            취소
          </Button>
          <Button onClick={() => void save()} disabled={saving}>
            계정 생성
          </Button>
        </Row>
      </Card>
      {created !== null && (
        <CredentialDialog
          title="계정 생성 완료"
          credentials={created}
          onClose={() => navigate(RoutePaths.adminInstructors)}
        />
      )}
    </div>
  );
}

/** 기수 관리 — admin_cohorts_screen.dart */
export function AdminCohortsScreen() {
  const user = useCurrentUser();
  const cohorts = useCohorts();
  const navigate = useNavigate();
  const [filter, setFilter] = useState<'active' | 'planned' | 'closed'>('active');
  const [deleteTarget, setDeleteTarget] = useState<Cohort | null>(null);
  const [deletePreview, setDeletePreview] = useState<CohortDeletionPreview | null>(null);
  const [confirmName, setConfirmName] = useState('');
  const [restoreTarget, setRestoreTarget] = useState<Cohort | null>(null);
  const [restoreStatus, setRestoreStatus] = useState<'planned' | 'active'>('planned');
  const [actionBusy, setActionBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  const showDelete = async (cohort: Cohort) => {
    setDeleteTarget(cohort); setDeletePreview(null); setConfirmName(''); setActionError('');
    try { setDeletePreview(await getCohortDeletionPreview(cohort.cohortId)); }
    catch (error) { setActionError(await readApiError(error)); }
  };
  const executeDelete = async () => {
    if (!deleteTarget || !deletePreview || !deletePreview.canDelete || confirmName !== deletePreview.name) return;
    setActionBusy(true); setActionError('');
    try { await deleteCohort(deleteTarget.cohortId, confirmName); setDeleteTarget(null); setDeletePreview(null); }
    catch (error) {
      setActionError(await readApiError(error));
      try { setDeletePreview(await getCohortDeletionPreview(deleteTarget.cohortId)); } catch { /* keep last preview */ }
    } finally { setActionBusy(false); }
  };
  const closeCohort = async (cohort: Cohort) => {
    if (!window.confirm(`“${cohort.name}” 기수를 종료하시겠습니까? 종료된 기수 목록으로 이동하며 학생·출결·문서는 유지됩니다.`)) return;
    setActionBusy(true); setActionError('');
    try { await setCohortStatus(cohort.cohortId, 'closed'); setFilter('closed'); }
    catch (error) { setActionError(await readApiError(error)); }
    finally { setActionBusy(false); }
  };
  const restoreCohort = async () => {
    if (!restoreTarget) return;
    setActionBusy(true); setActionError('');
    try { await setCohortStatus(restoreTarget.cohortId, restoreStatus); setFilter(restoreStatus); setRestoreTarget(null); }
    catch (error) { setActionError(await readApiError(error)); }
    finally { setActionBusy(false); }
  };

  const count = (status: string) => cohorts.filter((c) => c.status === status).length;
  const shown = cohorts.filter((c) => c.status === filter);

  return (
    <TabPage
      title="기수 관리"
      description="기수를 만들고 기간 · 상태 · 강의장을 관리합니다."
      actions={
        <Link className="btn btn--filled btn--md" to={RoutePaths.adminCohortsCreate}>
          <Icon name="add" size={18} />
          기수 생성
        </Link>
      }
      tabs={
        <Tabs
          active={filter}
          onChange={(id) => setFilter(id as 'active' | 'planned' | 'closed')}
          items={[
            { id: 'active', label: '진행중', count: count('active') },
            { id: 'planned', label: '예정', count: count('planned') },
            { id: 'closed', label: '종료된 기수', count: count('closed') },
          ]}
        />
      }
    >

      {shown.length === 0 ? (
        <div className="list-page__empty">
          <Icon name="calendar_month" size={44} />
          <p>해당하는 기수가 없습니다</p>
        </div>
      ) : (
        <div className="list-page__body">
          {shown.map((c) => {
            const current = c.cohortId === user.cohortId;
            const selectable = c.status === 'active' || c.status === 'planned';
            return (
              <article
                key={c.cohortId}
                className={`cohort-card cohort-card--link${current ? ' cohort-card--on' : ''}`}
                // 카드를 누르면 수정으로 간다(Flutter InkWell). 안의 단추는 제 일만 한다
                onClick={() => navigate(adminCohortEditPath(c.cohortId))}
              >
                <header className="cohort-card__head">
                  <Badge
                    tone={
                      c.status === 'active' ? 'success' : c.status === 'planned' ? 'info' : 'neutral'
                    }
                  >
                    {CohortStatusLabels[c.status]}
                  </Badge>
                  {current && <span className="cohort-card__now">현재 선택</span>}
                  <span className="spacer" />
                  <span className="cohort-card__count">
                    <strong>{c.studentCount}명</strong>
                    <span className="hint">학생</span>
                  </span>
                </header>

                <h2 className="cohort-card__title">{c.name}</h2>
                <p className="cohort-card__period">
                  {formatDate(c.startDate)} ~ {formatDate(c.endDate)}
                </p>

                <div className="cohort-card__actions" onClick={(e) => e.stopPropagation()}>
                  {selectable && !current && (
                    <Button variant="outline" size="sm" onClick={() => selectCohort(user.uid, c.cohortId)}>
                      이 기수로 전환
                    </Button>
                  )}
                  <Link className="btn btn--outline btn--sm" to={adminCohortEditPath(c.cohortId)}>
                    수정
                  </Link>
                  {c.status === 'closed' ?
                    <Button variant="outline" size="sm" disabled={actionBusy} onClick={() => { setRestoreTarget(c); setRestoreStatus('planned'); setActionError(''); }}>복원</Button> :
                    <Button variant="outline" size="sm" disabled={actionBusy} onClick={() => void closeCohort(c)}>기수 종료</Button>}
                  <Button variant="outline" size="sm" disabled={actionBusy} onClick={() => void showDelete(c)}>기수 삭제</Button>
                </div>
              </article>
            );
          })}
        </div>
      )}
      {actionError && !deleteTarget && !restoreTarget && <p role="alert">{actionError}</p>}
      {restoreTarget && <div className="cohort-action-overlay" role="dialog" aria-modal="true" aria-label="기수 복원">
        <div className="cohort-action-dialog"><h2>기수 복원</h2><p>{restoreTarget.name}</p>
          <label>복원 후 상태 <select aria-label="복원 후 상태" value={restoreStatus}
            onChange={(event) => setRestoreStatus(event.target.value as 'planned' | 'active')}>
            <option value="planned">예정</option><option value="active">진행중</option>
          </select></label>
          {actionError && <p role="alert">{actionError}</p>}
          <Row><Button variant="outline" disabled={actionBusy} onClick={() => setRestoreTarget(null)}>취소</Button>
            <Button disabled={actionBusy} onClick={() => void restoreCohort()}>복원</Button></Row>
        </div>
      </div>}
      {deleteTarget && <div className="cohort-action-overlay" role="dialog" aria-modal="true" aria-label="기수 삭제 확인">
        <div className="cohort-action-dialog"><h2>기수 영구 삭제</h2>
          <p>대상 기수: <strong>{deletePreview?.name ?? deleteTarget.name}</strong></p>
          {!deletePreview && !actionError && <p>삭제 가능 여부 확인 중…</p>}
          {deletePreview && <>
            <p>삭제 대상: 기수 정보{deletePreview.documents.map((doc) => ` · ${doc.kind === 'curriculum' ? '커리큘럼' : '정책'} ${doc.filename}`).join('')}</p>
            <p>이 기수 전용 이전 업로드 파일과 검색 색인도 정리합니다. 학생·출결 등 운영 기록은 삭제하지 않습니다.</p>
            {deletePreview.blockers.length > 0 && <p role="alert">운영 기록이 있어 삭제할 수 없습니다: {deletePreview.blockers.map((item) => item.label).join(', ')}. 기수 종료를 이용해 주세요.</p>}
            {deletePreview.unsafeDocuments.length > 0 && <p role="alert">소유권을 확인할 수 없는 문서가 있어 삭제할 수 없습니다: {deletePreview.unsafeDocuments.join(', ')}</p>}
            {deletePreview.state === 'failed' && <p role="status">이전 삭제가 완료되지 않았습니다. 같은 대상의 남은 정리를 다시 시도할 수 있습니다.</p>}
            {deletePreview.canDelete && <label>확인을 위해 기수명 입력
              <input aria-label="삭제 확인 기수명" value={confirmName} onChange={(event) => setConfirmName(event.target.value)} />
            </label>}
          </>}
          {actionError && <p role="alert">{actionError}</p>}
          <Row><Button variant="outline" disabled={actionBusy} onClick={() => setDeleteTarget(null)}>취소</Button>
            <Button disabled={actionBusy || !deletePreview?.canDelete || confirmName !== deletePreview.name}
              onClick={() => void executeDelete()}>{actionBusy ? '삭제 진행 중…' : '영구 삭제'}</Button></Row>
        </div>
      </div>}
    </TabPage>
  );
}

/** 기수 만들기·수정 — admin_cohort_form_screen.dart */
export function AdminCohortFormScreen() {
  const { cohortId } = useParams<{ cohortId: string }>();
  const cohorts = useCohorts();
  const existing = cohorts.find((c) => c.cohortId === cohortId);
  const navigate = useNavigate();
  const location = useLocation();
  const wizard = !cohortId;
  const [step, setStep] = useState((location.state as { documentUploadComplete?: boolean } | null)?.documentUploadComplete ? 1 : 0);
  const stepHeading = useRef<HTMLHeadingElement>(null);
  const goToStep = (next: number) => {
    if (saving) return;
    if (next > 0 && (!name.trim() || (startDate && endDate && endDate < startDate))) {
      setError(!name.trim() ? '기수 이름은 필수입니다.' : null);
      setPeriodError(startDate && endDate && endDate < startDate ? '종료일은 시작일 이후여야 합니다.' : null);
      setStep(0); return;
    }
    setError(null); setPeriodError(null); setStep(next);
  };
  useEffect(() => { stepHeading.current?.focus(); }, [step]);

  const [name, setName] = useState(existing?.name ?? '');
  const [description, setDescription] = useState(existing?.description ?? '');
  const [termNumber, setTermNumber] = useState(String(existing?.termNumber ?? ''));
  const [classroomName, setClassroomName] = useState(existing?.classroomName ?? '');
  const [startDate, setStartDate] = useState(toInputDate(existing?.startDate));
  const [endDate, setEndDate] = useState(toInputDate(existing?.endDate));
  const [status, setStatus] = useState<CohortStatus>(existing?.status ?? 'planned');
  const [error, setError] = useState<string | null>(null);
  const [periodError, setPeriodError] = useState<string | null>(null);
  const [curriculumFile, setCurriculumFile] = useState<File | null>(null);
  const [policyFile, setPolicyFile] = useState<File | null>(null);
  const curriculumInput = useRef<HTMLInputElement>(null);
  const policyInput = useRef<HTMLInputElement>(null);
  const documentLoadGeneration = useRef(0);
  const [documents, setDocuments] = useState<{ curriculum: CohortDocumentStatus | null; policy: CohortDocumentStatus | null } | null>(null);
  const [documentsCohortId, setDocumentsCohortId] = useState<string | null>(null);
  const [documentError, setDocumentError] = useState('');
  const [documentsLoading, setDocumentsLoading] = useState(false);
  const [uploadingKind, setUploadingKind] = useState<'curriculum' | 'policy' | null>(null);
  const [savePhase, setSavePhase] = useState<'cohort' | 'curriculum' | 'policy' | 'confirm'>('cohort');
  const [processingFilename, setProcessingFilename] = useState('');
  const [saveElapsed, setSaveElapsed] = useState(0);
  const [completed, setCompleted] = useState(Boolean((location.state as { documentUploadComplete?: boolean } | null)?.documentUploadComplete));
  const [saving, setSaving] = useState(false);
  const [savedCohortId, setSavedCohortId] = useState<string | null>(null);
  useEffect(() => {
    if (!saving) return;
    const startedAt = Date.now();
    setSaveElapsed(0);
    const timer = window.setInterval(() => setSaveElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, [saving]);
  const [saveError, setSaveError] = useState('');
  const normalizedName = name.trim().replace(/\s+/g, ' ').toLocaleLowerCase();
  const enteredTerm = termNumber.trim() === '' ? null : Number(termNumber);
  const duplicateCandidates = wizard && !savedCohortId ? cohorts.filter((candidate) =>
    (normalizedName !== '' && candidate.name.trim().replace(/\s+/g, ' ').toLocaleLowerCase() === normalizedName)
    || (enteredTerm !== null && Number.isInteger(enteredTerm) && candidate.termNumber === enteredTerm)
  ) : [];
  const duplicateCodes = duplicateCandidates.map((candidate) => candidate.cohortId).sort().join('|');
  const [duplicateStates, setDuplicateStates] = useState<Record<string, string>>({});
  useEffect(() => {
    if (!duplicateCodes) return;
    let active = true;
    void Promise.all(duplicateCodes.split('|').map(async (code) => {
      try { return [code, (await getCohortDeletionPreview(code)).state] as const; }
      catch { return [code, 'unknown'] as const; }
    })).then((states) => { if (active) setDuplicateStates(Object.fromEntries(states)); });
    return () => { active = false; };
  }, [duplicateCodes]);
  const documentCohortId = existing?.cohortId ?? savedCohortId;
  const visibleDocuments = documentsCohortId === documentCohortId ? documents : null;
  useEffect(() => {
    if (!documentCohortId) return;
    let active = true;
    const generation = ++documentLoadGeneration.current;
    setDocumentsLoading(true);
    getCohortDocuments(documentCohortId).then((result) => {
      if (active && generation === documentLoadGeneration.current) {
        setDocuments(result.documents); setDocumentsCohortId(result.cohortId); setDocumentError('');
      }
    }).catch(() => { if (active && generation === documentLoadGeneration.current) setDocumentError('현재 등록 문서 상태를 불러오지 못했습니다.'); })
      .finally(() => { if (active && generation === documentLoadGeneration.current) setDocumentsLoading(false); });
    return () => { active = false; };
  }, [documentCohortId]);
  // 개강한 기수는 시작일을 잠근다 — 출석 단위기간(장려금 판정)이 시작일부터 한 달씩 나뉘어, 바꾸면 지난 기간까지 다시 계산된다.
  // 종료일은 마지막 기간만 바뀌어 열어 둔다. 서버(op_update_cohort)도 같은 규칙으로 거절한다
  const started = existing?.startDate !== undefined && toInputDate(existing.startDate) <= dateKeyOf(new Date());

  const save = async () => {
    if (saving) return;
    if (duplicateCandidates.length > 0 && !savedCohortId) {
      setSaveError('같은 기수 번호 또는 이름이 이미 있습니다. 기존 기수 수정 화면을 이용해 주세요.');
      setStep(0);
      return;
    }
    if (name.trim() === '') {
      setError('기수 이름은 필수입니다.');
      setStep(0);
      return;
    }
    if (startDate !== '' && endDate !== '' && endDate < startDate) {
      setPeriodError('종료일은 시작일 이후여야 합니다.');
      setStep(0);
      return;
    }
    const cohort: Cohort = {
      cohortId: existing?.cohortId ?? savedCohortId ?? nextId('cohort'),
      name: name.trim(),
      description: description.trim(),
      startDate: startDate === '' ? undefined : new Date(startDate),
      endDate: endDate === '' ? undefined : new Date(endDate),
      isActive: existing?.isActive ?? status === 'active',
      status,
      termNumber: termNumber === '' ? undefined : Number(termNumber),
      classroomName: classroomName.trim(),
      studentCount: existing?.studentCount ?? 0,
      createdAt: existing?.createdAt ?? new Date(),
    };
    for (const file of [curriculumFile, policyFile]) {
      if (file && (file.size === 0 || file.size > 10 * 1024 * 1024)) {
        setSaveError('첨부 문서는 비어 있지 않은 10MB 이하 파일이어야 합니다.');
        return;
      }
    }
    setSavePhase('cohort');
    setProcessingFilename('');
    setSaving(true);
    setSaveError('');
    setCompleted(false);
    let persisted = Boolean(existing || savedCohortId);
    try {
      if (!persisted) await createCohort(cohort);
      else await updateCohort(cohort.cohortId, cohort);
      persisted = true;
      setSavedCohortId(cohort.cohortId);
      const uploadFailures: string[] = [];
      for (const [kind, file] of [['curriculum', curriculumFile], ['policy', policyFile]] as const) {
        if (!file) continue;
        setUploadingKind(kind);
        setSavePhase(kind);
        setProcessingFilename(file.name);
        try {
          await uploadCohortDocument(cohort.cohortId, kind, file);
          if (kind === 'curriculum') { setCurriculumFile(null); if (curriculumInput.current) curriculumInput.current.value = ''; }
          else { setPolicyFile(null); if (policyInput.current) policyInput.current.value = ''; }
        } catch (err) {
          uploadFailures.push(`${kind === 'curriculum' ? '커리큘럼' : '정책 문서'}: ${await readApiError(err)}`);
        }
      }
      setUploadingKind(null);
      setSavePhase('confirm');
      setProcessingFilename('');
      const generation = ++documentLoadGeneration.current;
      try {
        const current = await getCohortDocuments(cohort.cohortId);
        if (generation === documentLoadGeneration.current) {
          setDocuments(current.documents); setDocumentsCohortId(current.cohortId); setDocumentError('');
        }
      } catch {
        if (generation === documentLoadGeneration.current) setDocumentError('등록 문서 상태를 새로고침하지 못했습니다. 다시 열어 확인해 주세요.');
      } finally {
        if (generation === documentLoadGeneration.current) setDocumentsLoading(false);
      }
      if (uploadFailures.length) {
        setStep(1);
        setSaveError(`기수 정보는 저장됐습니다. 기존 등록 문서와 성공한 업로드는 유지됩니다. 실패한 항목만 다시 저장해 주세요. ${uploadFailures.join(' / ')}`);
      } else {
        setCompleted(true);
        setStep(1);
        if (curriculumFile || policyFile) navigate(adminCohortEditPath(cohort.cohortId), { state: { documentUploadComplete: true } });
        else navigate(RoutePaths.adminCohorts);
      }
    } catch (err) {
      setSaveError(`${persisted ? '기수 정보는 저장됐습니다. 실패한 첨부를 확인한 뒤 다시 저장해 주세요. ' : ''}${await readApiError(err)}`);
    } finally { setSaving(false); setUploadingKind(null); }
  };

  return (
    <div className="screen__inner cohort-form">
      <PageHeader title={existing === undefined ? '기수 생성' : '기수 수정'} />
      {wizard && <nav className="cohort-steps" aria-label="기수 생성 단계">
        {['기본 정보', '교육 자료', '확인 및 생성'].map((label, index) => <button key={label} type="button"
          disabled={saving} aria-current={step === index ? 'step' : undefined} onClick={() => goToStep(index)}>
          <span>{index + 1}</span>{label}
        </button>)}
      </nav>}
      {!wizard && <nav className="cohort-edit-tabs" aria-label="기수 수정 항목">
        {['기본 정보', '교육 자료'].map((label, index) => <button key={label} type="button"
          disabled={saving} aria-pressed={step === index} onClick={() => setStep(index)}>{label}</button>)}
      </nav>}
      <Card>
        <h2 ref={stepHeading} tabIndex={-1} className="cohort-form__heading"><Icon name={step === 1 ? 'folder_open' : 'tune'} size={20} />{['기본 정보', '교육 자료', '등록 정보 확인'][step]}</h2>
        <fieldset disabled={saving} hidden={step !== 0} className="cohort-form__section">
        <Field label="기수 이름" error={error ?? undefined}>
          <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="SK네트웍스 Family AI 캠프 35기" />
        </Field>
        {wizard && duplicateCandidates.length > 0 && <section className="cohort-duplicate" aria-label="기존 기수 확인">
          <h3>이미 등록된 기수가 있습니다</h3>
          <p>기수 번호나 이름이 같습니다. 새로 만들지 말고 기존 기수의 문서를 교체할 수 있습니다.</p>
          {duplicateCandidates.map((candidate) => {
            const deletionState = duplicateStates[candidate.cohortId];
            const deleting = deletionState !== 'not_started';
            return <div key={candidate.cohortId} className="cohort-duplicate__row">
              <span>{candidate.name} · {candidate.termNumber ?? '번호 없음'}기 · {formatDate(candidate.startDate)} ~ {formatDate(candidate.endDate)} · {CohortStatusLabels[candidate.status]}</span>
              {deleting ? <span>{deletionState === 'unknown' || !deletionState ? '삭제 상태 확인 중' : '삭제 처리 중 · 수정 불가'}</span> :
                <Button variant="outline" size="sm" onClick={() => {
                  if ((curriculumFile || policyFile) && !window.confirm('선택한 파일은 기존 기수로 전달되지 않습니다. 수정 화면에서 다시 선택하시겠습니까?')) return;
                  navigate(adminCohortEditPath(candidate.cohortId));
                }}>기존 기수 수정</Button>}
            </div>;
          })}
        </section>}
        <Field label="설명">
          <TextArea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <div className="grid grid--2">
          <Field label="기수 번호">
            <TextInput type="number" value={termNumber} onChange={(e) => setTermNumber(e.target.value)} />
          </Field>
          <Field label="강의장">
            <TextInput value={classroomName} onChange={(e) => setClassroomName(e.target.value)} />
          </Field>
          <Field label={started ? '시작일 · 변경 불가' : '시작일'} hint={started ? '개강 후 고정 · 출석 단위기간 산정 기준' : undefined}>
            <TextInput type="date" value={startDate} disabled={started} onChange={(e) => setStartDate(e.target.value)} />
          </Field>
          <Field label="종료일" error={periodError ?? undefined}>
            <TextInput
              type="date"
              value={endDate}
              onChange={(e) => {
                setEndDate(e.target.value);
                setPeriodError(null);
              }}
            />
          </Field>
        </div>
        <Field label="상태">
          <Select value={status} onChange={(e) => setStatus(e.target.value as CohortStatus)}>
            {Object.entries(CohortStatusLabels).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </Select>
        </Field>
        </fieldset>
        <fieldset disabled={saving} hidden={step !== 1} className="cohort-form__section cohort-form__documents">
        {documentsLoading && <p className="hint">등록 문서 조회 중…</p>}
        {documentError && <p role="status">{documentError}</p>}
        {(['curriculum', 'policy'] as const).map(kind => {
          const stored = visibleDocuments?.[kind];
          const file = kind === 'curriculum' ? curriculumFile : policyFile;
          const label = kind === 'curriculum' ? '커리큘럼 PDF' : '기수별 정책 문서';
          return <section className="cohort-document" key={kind} aria-label={label}>
            <div className="cohort-document__header">
              <span className="cohort-document__icon"><Icon name="description" size={24} /></span>
              <div><h3>{label} <span className="cohort-document__optional">선택</span></h3>
                {stored && <Badge tone={stored.ragStatus === 'ready' ? 'success' : 'neutral'}>{stored.ragStatus === 'ready' ? '검색 반영 완료' : stored.ragStatus === 'inactive' ? '비활성' : '등록됨 · 검색 반영 미확인'}</Badge>}
              </div>
            </div>
            {stored ? <div role="status"><p className="cohort-document__filename">현재 등록 · {stored.filename}</p>
              <p className="cohort-document__meta">{stored.updatedAt ? new Date(stored.updatedAt).toLocaleString('ko-KR') : '갱신 시각 없음'}</p></div>
              : <p className="cohort-document__meta">{documentError ? '등록 상태 확인 필요' : documentsLoading ? '등록 문서 조회 중…' : documentCohortId && !visibleDocuments ? '등록 상태 확인 중' : '등록된 문서 없음'}</p>}
            <div className="cohort-document__actions">
              <span className="cohort-document__meta">{kind === 'curriculum' ? '텍스트 PDF' : '텍스트 PDF / 정책집 양식 DOCX'} · 최대 10MB</span>
              <label className="cohort-document__upload">{stored ? '파일 교체' : '파일 선택'}
                <input ref={kind === 'curriculum' ? curriculumInput : policyInput} type="file"
                  accept={kind === 'curriculum' ? '.pdf,application/pdf' : '.pdf,.docx'} disabled={saving} aria-label={label}
                  onChange={e => (kind === 'curriculum' ? setCurriculumFile : setPolicyFile)(e.target.files?.[0] ?? null)} />
              </label>
            </div>
            {file && <p className="cohort-document__pending">{stored ? '교체 예정' : '등록 예정'} · {file.name}</p>}
            {uploadingKind === kind && <p role="status">{label} 저장·검색 준비 중…</p>}
          </section>;
        })}
        <p className="cohort-document__meta">선택한 파일은 저장 후 반영됩니다. 등록에 실패하거나 파일을 선택하지 않으면 기존 문서를 유지합니다.</p>
        </fieldset>
        {wizard && step === 2 && <dl className="cohort-summary">
          {[
            ['기수', name, 0],
            ['운영 정보', `${termNumber ? termNumber + '기 · ' : ''}${classroomName || '강의장 미지정'} · ${CohortStatusLabels[status]}`, 0],
            ['교육기간', `${startDate || '미지정'} ~ ${endDate || '미지정'}`, 0],
            ['설명', description || '없음', 0],
            ['커리큘럼', curriculumFile?.name ?? visibleDocuments?.curriculum?.filename ?? '등록 안 함', 1],
            ['정책 문서', policyFile?.name ?? visibleDocuments?.policy?.filename ?? '등록 안 함', 1],
          ].map(([label, value, target]) => <div key={String(label)}><dt>{label}</dt><dd>{value}</dd>
            <button type="button" disabled={saving} onClick={() => goToStep(Number(target))}>{label} 수정</button></div>)}
          <p className="hint">문서 등록 및 검색 준비가 완료되면 해당 기수 챗봇에 반영됩니다.</p>
        </dl>}
        {completed && <p role="status">저장 완료 · 문서별 검색 반영 상태는 교육 자료 탭에서 확인할 수 있습니다.</p>}
        {saveError && <p role="alert">{saveError}</p>}
        {saving && <section className="cohort-save-progress" aria-label="저장 진행 상황">
          <div className="cohort-save-progress__top">
            <strong role="status">{savePhase === 'cohort' ? '기수 정보 저장 중' : savePhase === 'confirm' ? '등록 결과 확인 중' : `${savePhase === 'curriculum' ? '커리큘럼' : '정책 문서'} 저장·검색 준비 중`}</strong>
            <span>{saveElapsed}초 경과</span>
          </div>
          <progress aria-label="저장 처리 중" />
          {processingFilename && <p className="cohort-save-progress__filename">{processingFilename}</p>}
          <p>{savePhase === 'cohort' ? '기수의 기본 정보를 저장하고 있습니다.' : savePhase === 'confirm' ? '문서별 등록 상태를 확인하고 있습니다.' : '문서 업로드와 챗봇 검색 준비를 진행합니다. 문서 분량과 서버 상태에 따라 시간이 걸릴 수 있습니다.'}</p>
          {saveElapsed >= 30 && <p>처리 결과를 기다리고 있습니다. 중복 등록을 피하려면 이 화면을 유지해 주세요.</p>}
        </section>}
        <div className="cohort-form__footer"><Row>
          {wizard && <span className="cohort-form__progress">{step + 1} / 3단계 · {savedCohortId ? '기수 저장됨' : '저장 전'}</span>}
          <Spacer />
          <Button variant="outline" disabled={saving} onClick={() => navigate(RoutePaths.adminCohorts)}>
            취소
          </Button>
          {wizard && step > 0 && <Button variant="outline" disabled={saving} onClick={() => goToStep(step - 1)}>이전</Button>}
          {wizard && step < 2
            ? <Button disabled={saving} onClick={() => goToStep(step + 1)}>{step === 0 ? '교육 자료 등록' : '등록 내용 확인'}</Button>
            : <Button onClick={() => void save()} disabled={saving || (wizard && !savedCohortId && duplicateCandidates.length > 0)}>{saving ? '저장·검색 준비 중…' : wizard ? (savedCohortId ? '다시 저장' : '기수 생성') : '변경사항 저장'}</Button>}
        </Row></div>
      </Card>
    </div>
  );
}
