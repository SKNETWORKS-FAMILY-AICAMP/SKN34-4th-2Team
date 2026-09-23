import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import {
  RoutePaths,
  adminCohortEditPath,
  adminStudentDetailPath,
  adminStudentEditPath,
} from '../../app/routePaths';
import {
  createCohort,
  createUser,
  updateCohort,
  updateUser,
  useAttendanceOfUser,
  useCohorts,
  useInstructors,
  useMileageTransactions,
  useMySubmissions,
  useStudents,
  useUser,
} from '../../data/repository';
import { nextId } from '../../data/store';
import { CohortStatusLabels, RecordTypeLabels, attendanceLabel } from '../../domain/constants';
import type { Cohort, CohortStatus, User } from '../../domain/types';
import {
  Badge,
  Button,
  Card,
  DataTable,
  EmptyState,
  Field,
  PageHeader,
  Row,
  Select,
  Spacer,
  StatTile,
  TextArea,
  TextInput,
  Toggle,
} from '../../ui/components';
import { formatDate, formatDateTime, formatMileage } from '../../utils/format';
import { FilterPillHeader } from '../../ui/FilterPillHeader';
import { MoreMenu } from '../../ui/MoreMenu';
import { Icon } from '../../ui/Icon';
import { dateKeyOf } from '../../data/seed';
import { useCurrentUser } from '../auth/session';

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
    <div className="list-page">
      <FilterPillHeader
        pills={[
          { id: 'active', label: '재원', count: students.filter((s) => s.isActive).length },
          { id: 'inactive', label: '퇴소', count: students.filter((s) => !s.isActive).length },
        ]}
        selected={filter}
        onSelect={(id) => setFilter(id as 'active' | 'inactive')}
        trailing={
          <>
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
            <Link className="btn btn--filled btn--md" to={RoutePaths.adminStudentsCreate}>
              <Icon name="person_add" size={18} />
              학생 등록
            </Link>
          </>
        }
      />

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
    </div>
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
            <Button
              variant={student.isActive ? 'danger' : 'filled'}
              onClick={() => updateUser(student.uid, { isActive: !student.isActive })}
            >
              {student.isActive ? '비활성화' : '재활성화'}
            </Button>
          </>
        }
      />

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
  const [error, setError] = useState<string | null>(null);

  const save = () => {
    if (displayName.trim() === '' || email.trim() === '') {
      setError('이름과 이메일은 반드시 입력해야 합니다.');
      return;
    }
    if (existing === undefined) {
      const uid = nextId('user');
      createUser({
        uid,
        email: email.trim(),
        personalEmail: personalEmail.trim(),
        displayName: displayName.trim(),
        role: 'student',
        cohortId: admin.cohortId,
        cohortName: admin.cohortName,
        seatNumber: seatNumber === '' ? undefined : Number(seatNumber),
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
      navigate(adminStudentDetailPath(uid));
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
          <Field label="이름" error={error ?? undefined}>
            <TextInput value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </Field>
          <Field label="계정 이메일">
            <TextInput value={email} onChange={(e) => setEmail(e.target.value)} placeholder="student@playdata.co.kr" />
          </Field>
          <Field label="개인 이메일" hint="구글폼 제출 매칭에 씁니다.">
            <TextInput value={personalEmail} onChange={(e) => setPersonalEmail(e.target.value)} />
          </Field>
          <Field label="좌석 번호">
            <TextInput type="number" value={seatNumber} onChange={(e) => setSeatNumber(e.target.value)} />
          </Field>
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
        <Row>
          <Spacer />
          <Button variant="outline" onClick={() => navigate(RoutePaths.adminStudents)}>
            취소
          </Button>
          <Button onClick={save}>저장</Button>
        </Row>
      </Card>
    </div>
  );
}

/** 강사 관리 — admin_instructors_screen.dart */
export function AdminInstructorsScreen() {
  const instructors = useInstructors();

  return (
    <div className="list-page">
      <div className="pill-head">
        <div className="pill-head__trailing">
          <Link className="btn btn--filled btn--md" to={RoutePaths.adminInstructorsCreate}>
            <Icon name="person_add" size={18} />
            강사 등록
          </Link>
        </div>
      </div>

      {instructors.length === 0 ? (
        <div className="list-page__empty">
          <Icon name="badge" size={44} />
          <p>등록된 강사가 없습니다</p>
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
                    onSelect: () => updateUser(i.uid, { mustChangePassword: true }),
                  },
                  {
                    key: 'toggle',
                    label: i.isActive ? '비활성으로' : '활성으로',
                    danger: i.isActive,
                    onSelect: () => updateUser(i.uid, { isActive: !i.isActive }),
                  },
                ]}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** 강사 등록 — admin_instructor_create_screen.dart */
export function AdminInstructorCreateScreen() {
  const admin = useCurrentUser();
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState('');
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);

  const save = () => {
    if (displayName.trim() === '' || email.trim() === '') {
      setError('이름과 이메일은 반드시 입력해야 합니다.');
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
    createUser(newInstructor);
    navigate(RoutePaths.adminInstructors);
  };

  return (
    <div className="screen__inner">
      <PageHeader title="강사 등록" />
      <Card>
        <Field label="이름" error={error ?? undefined}>
          <TextInput value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </Field>
        <Field label="계정 이메일">
          <TextInput value={email} onChange={(e) => setEmail(e.target.value)} placeholder="instructor@playdata.co.kr" />
        </Field>
        <div className="callout">임시 비밀번호로 계정이 만들어지고, 첫 로그인에서 비밀번호를 바꾸게 됩니다.</div>
        <Row>
          <Spacer />
          <Button variant="outline" onClick={() => navigate(RoutePaths.adminInstructors)}>
            취소
          </Button>
          <Button onClick={save}>등록</Button>
        </Row>
      </Card>
    </div>
  );
}

/** 기수 관리 — admin_cohorts_screen.dart */
export function AdminCohortsScreen() {
  const user = useCurrentUser();
  const cohorts = useCohorts();
  const [filter, setFilter] = useState<'active' | 'planned' | 'closed'>('active');

  const count = (status: string) => cohorts.filter((c) => c.status === status).length;
  const shown = cohorts.filter((c) => c.status === filter);

  return (
    <div className="list-page">
      <FilterPillHeader
        pills={[
          { id: 'active', label: '진행중', count: count('active') },
          { id: 'planned', label: '예정', count: count('planned') },
          { id: 'closed', label: '종료', count: count('closed') },
        ]}
        selected={filter}
        onSelect={(id) => setFilter(id as 'active' | 'planned' | 'closed')}
        trailing={
          <Link className="btn btn--filled btn--md" to={RoutePaths.adminCohortsCreate}>
            <Icon name="add" size={18} />
            기수 생성
          </Link>
        }
      />

      {shown.length === 0 ? (
        <div className="list-page__empty">
          <Icon name="calendar_month" size={44} />
          <p>해당하는 기수가 없습니다</p>
        </div>
      ) : (
        <div className="list-page__body">
          {shown.map((c) => {
            const current = c.cohortId === user.cohortId;
            return (
              <article key={c.cohortId} className={`cohort-card${current ? ' cohort-card--on' : ''}`}>
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

                <div>
                  <Link className="btn btn--outline btn--sm" to={adminCohortEditPath(c.cohortId)}>
                    수정
                  </Link>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** 기수 만들기·수정 — admin_cohort_form_screen.dart */
export function AdminCohortFormScreen() {
  const { cohortId } = useParams<{ cohortId: string }>();
  const cohorts = useCohorts();
  const existing = cohorts.find((c) => c.cohortId === cohortId);
  const navigate = useNavigate();

  const [name, setName] = useState(existing?.name ?? '');
  const [description, setDescription] = useState(existing?.description ?? '');
  const [termNumber, setTermNumber] = useState(String(existing?.termNumber ?? ''));
  const [classroomName, setClassroomName] = useState(existing?.classroomName ?? '');
  const [startDate, setStartDate] = useState(toInputDate(existing?.startDate));
  const [endDate, setEndDate] = useState(toInputDate(existing?.endDate));
  const [status, setStatus] = useState<CohortStatus>(existing?.status ?? 'planned');
  const [error, setError] = useState<string | null>(null);

  const save = () => {
    if (name.trim() === '') {
      setError('기수 이름을 입력해 주세요.');
      return;
    }
    const cohort: Cohort = {
      cohortId: existing?.cohortId ?? nextId('cohort'),
      name: name.trim(),
      description: description.trim(),
      startDate: startDate === '' ? undefined : new Date(startDate),
      endDate: endDate === '' ? undefined : new Date(endDate),
      isActive: status === 'active',
      status,
      termNumber: termNumber === '' ? undefined : Number(termNumber),
      classroomName: classroomName.trim(),
      studentCount: existing?.studentCount ?? 0,
      createdAt: existing?.createdAt ?? new Date(),
    };
    if (existing === undefined) createCohort(cohort);
    else updateCohort(existing.cohortId, cohort);
    navigate(RoutePaths.adminCohorts);
  };

  return (
    <div className="screen__inner">
      <PageHeader title={existing === undefined ? '기수 만들기' : '기수 수정'} />
      <Card>
        <Field label="기수 이름" error={error ?? undefined}>
          <TextInput value={name} onChange={(e) => setName(e.target.value)} placeholder="SK네트웍스 Family AI 캠프 35기" />
        </Field>
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
          <Field label="시작일">
            <TextInput type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
          </Field>
          <Field label="종료일">
            <TextInput type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
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
        <Row>
          <Spacer />
          <Button variant="outline" onClick={() => navigate(RoutePaths.adminCohorts)}>
            취소
          </Button>
          <Button onClick={save}>저장</Button>
        </Row>
      </Card>
    </div>
  );
}
