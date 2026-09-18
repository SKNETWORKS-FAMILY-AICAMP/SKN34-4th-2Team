import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { RoutePaths } from '../../app/routePaths';
import {
  useAttendanceOfUser,
  useCurriculumSheets,
  useFormResponses,
  useFormTasks,
  useMySubmissions,
  useNotices,
  useQualExams,
  useYoutubeRecommendations,
} from '../../data/repository';
import { dateKeyOf } from '../../data/seed';
import { AttendanceColorVars, RecordTypeLabels, SubmissionStatusLabels } from '../../domain/constants';
import type { Notice } from '../../domain/types';
import { StudentTargets } from '../../tour/targets';
import { useTourTarget } from '../../tour/useTourTarget';
import { Icon } from '../../ui/Icon';
import { Badge } from '../../ui/components';
import { MileageCreditCard } from '../mileage/MileageCreditCard';
import { formatDate, formatDueIn, formatYmd } from '../../utils/format';
import { buildMissionGuidance, missionProgressOf } from '../../domain/missions';
import type { MissionGuidanceItem } from '../../domain/missions';
import { useCurrentUser } from '../auth/session';
import { NoticeDetailDialog } from '../board/NoticeDetailDialog';

/**
 * 대시보드 — features/dashboard/presentation/dashboard_screen.dart
 *
 * 왼쪽에 프로필·마일리지 카드와 공지·학습 추천·설문, 오른쪽에 출석 캘린더와
 * 미션·커리큘럼·자격 시험·승인 현황을 둔다.
 */
export function DashboardScreen() {
  const notices = useNotices();
  const [openNotice, setOpenNotice] = useState<Notice | null>(null);

  return (
    <div className="dash">
      <div className="dash__main">
        <div className="dash__top">
          <ProfileCard />
          <MileageCard />
        </div>

        <section className="section">
          <header className="section__head">
            <h2 className="section__title">시스템 공지</h2>
            <span className="spacer" />
            <Link className="section__more" to={RoutePaths.board}>
              더보기 <Icon name="chevron_right" size={16} />
            </Link>
          </header>
          {notices.length === 0 ? (
            <div className="panel panel--empty">공지사항이 없습니다</div>
          ) : (
            <div className="panel panel--flush">
              <ul className="notice-rows">
                {notices.slice(0, 5).map((notice) => (
                  <li key={notice.id}>
                    <button type="button" className="notice-row" onClick={() => setOpenNotice(notice)}>
                      {notice.isFavorite && <Badge tone="error">중요</Badge>}
                      <span className="notice-row__title">{notice.title}</span>
                      <span className="notice-row__date">{formatDate(notice.createdAt)}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <WeeklyLearningSection />
        <FormTasksSection />
      </div>

      <aside className="dash__side">
        <AttendanceCalendarCard />
        <MissionProgressCard />
        <CurriculumCard />
        <QualExamCard />
        <ApprovalCard />
      </aside>

      {openNotice !== null && (
        <NoticeDetailDialog notice={openNotice} onClose={() => setOpenNotice(null)} />
      )}
    </div>
  );
}

/** 프로필 카드 — widgets/dashboard_profile_header.dart */
function ProfileCard() {
  const user = useCurrentUser();
  return (
    <div className="panel profile-card">
      <div className="profile-card__row">
        <span className="profile-card__avatar">
          <Icon name="person" size={26} />
        </span>
        <div>
          <p className="profile-card__cohort">{user.cohortName}</p>
          <strong className="profile-card__name">{user.displayName}님</strong>
        </div>
      </div>
      <hr className="profile-card__rule" />
      <div className="profile-card__skills">
        {user.skills.length === 0 ? (
          <span className="hint">마이페이지에서 기술 스택을 등록해 보세요.</span>
        ) : (
          user.skills.map((skill) => (
            <span key={skill} className="skill-chip">
              {skill}
            </span>
          ))
        )}
      </div>
    </div>
  );
}

/** 마일리지 카드 — 눌러서 마일리지로, 포인터를 따라 기울어진다 */
function MileageCard() {
  const user = useCurrentUser();
  const navigate = useNavigate();
  return (
    <div
      className="mileage-card-slot"
      role="link"
      tabIndex={0}
      onClick={() => navigate(RoutePaths.mileage)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') navigate(RoutePaths.mileage);
      }}
    >
      <MileageCreditCard balance={user.mileageBalance} holderName={user.displayName} />
    </div>
  );
}

/** 출석 캘린더 — widgets/attendance_calendar_card.dart */
function AttendanceCalendarCard() {
  const user = useCurrentUser();
  const rows = useAttendanceOfUser(user.uid);
  const ref = useTourTarget(StudentTargets.dashboardCalendar);
  const [month, setMonth] = useState(() => {
    const d = new Date();
    return new Date(d.getFullYear(), d.getMonth(), 1);
  });

  const byDate = useMemo(() => {
    const map = new Map<string, string>();
    for (const r of rows) if (r.status !== undefined) map.set(r.dateKey, r.status);
    return map;
  }, [rows]);

  const first = month.getDay();
  const daysInMonth = new Date(month.getFullYear(), month.getMonth() + 1, 0).getDate();
  const cells: (Date | null)[] = [
    ...Array.from({ length: first }, () => null),
    ...Array.from({ length: daysInMonth }, (_, i) => new Date(month.getFullYear(), month.getMonth(), i + 1)),
  ];
  const todayKey = dateKeyOf(new Date());

  const shift = (delta: number) =>
    setMonth((m) => new Date(m.getFullYear(), m.getMonth() + delta, 1));

  const legend: [string, string][] = [
    ['출석', 'present'],
    ['지각', 'late'],
    ['결석', 'absent'],
    ['공가', 'officialLeave'],
    ['조퇴', 'earlyLeave'],
    ['외출', 'outing'],
  ];

  return (
    <div className="panel side-card" ref={ref}>
      <h3 className="side-card__title">출석</h3>
      <div className="cal__nav">
        <button type="button" className="icon-btn" onClick={() => shift(-1)} aria-label="이전 달">
          <Icon name="chevron_left" size={18} />
        </button>
        <strong>
          {month.getFullYear()}.{String(month.getMonth() + 1).padStart(2, '0')}
        </strong>
        <button type="button" className="icon-btn" onClick={() => shift(1)} aria-label="다음 달">
          <Icon name="chevron_right" size={18} />
        </button>
      </div>

      <div className="cal">
        {['일', '월', '화', '수', '목', '금', '토'].map((d, i) => (
          <span key={d} className={`cal__head${i === 0 ? ' cal__head--sun' : i === 6 ? ' cal__head--sat' : ''}`}>
            {d}
          </span>
        ))}
        {cells.map((date, i) => {
          if (date === null) return <span key={`e-${i}`} />;
          const key = dateKeyOf(date);
          const status = byDate.get(key);
          const weekday = date.getDay();
          return (
            <span
              key={key}
              className={`cal__day${key === todayKey ? ' cal__day--today' : ''}${
                weekday === 0 ? ' cal__day--sun' : weekday === 6 ? ' cal__day--sat' : ''
              }`}
            >
              {date.getDate()}
              {status !== undefined && (
                <i className="cal__dot" style={{ background: AttendanceColorVars[status] }} />
              )}
            </span>
          );
        })}
      </div>

      <div className="cal__legend">
        {legend.map(([label, code]) => (
          <span key={code}>
            <i style={{ background: AttendanceColorVars[code] }} />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}

/**
 * 미션 프로그레스 — widgets/mission_progress_dashboard_card.dart
 *
 * 기록실과 같은 규칙을 읽는다. 끝난 미션은 뒤로 밀고 앞에서 셋만 보인다.
 * 맨 위 옅은 칸에는 아직 못 끝낸 첫 미션이 「다음 · …」으로 선다.
 */
function MissionProgressCard() {
  const user = useCurrentUser();
  const submissions = useMySubmissions(user.uid);
  const items = buildMissionGuidance(missionProgressOf(submissions));

  const isDone = (m: MissionGuidanceItem) => m.maxEarn > 0 && m.earned >= m.maxEarn;
  const sorted = [...items].sort((a, b) => Number(isDone(a)) - Number(isDone(b)));
  const visible = sorted.slice(0, 3);
  const next = sorted.find((m) => !isDone(m));

  return (
    <div className="panel side-card">
      <header className="side-card__head">
        <h3 className="side-card__title">미션 프로그레스</h3>
        <Link className="section__more" to={RoutePaths.records}>
          기록실
        </Link>
      </header>

      {next === undefined ? (
        <p className="hint">주요 미션을 모두 달성했어요. 기록실에서 추가 활동을 이어가 보세요.</p>
      ) : (
        <div className="mission-next">
          <Icon name="flag" size={16} />
          <div>
            <strong>다음 · {next.title}</strong>
            <span>{next.statusText}</span>
          </div>
        </div>
      )}

      {visible.map((m) => {
        const done = isDone(m);
        const ratio = m.maxEarn <= 0 ? 0 : Math.min(1, m.earned / m.maxEarn);
        return (
          <div key={m.id} className="mission-row">
            <strong className="mission-row__label">{m.title}</strong>
            <span className={`mission-row__value${done ? ' mission-row__value--done' : ''}`}>
              {done ? '완료' : `${m.earned.toLocaleString()} / ${m.maxEarn.toLocaleString()}M`}
            </span>
            <span className="mission-row__bar">
              <i
                className={done ? 'mission-row__bar--done' : undefined}
                style={{ width: `${ratio * 100}%` }}
              />
            </span>
          </div>
        );
      })}
    </div>
  );
}

/** 커리큘럼 — features/curriculum/presentation/widgets/curriculum_dashboard_section.dart */
function CurriculumCard() {
  const sheets = useCurriculumSheets();
  const sheet = sheets[0];

  return (
    <div className="panel side-card">
      <h3 className="side-card__title">커리큘럼</h3>
      <div className="curriculum-row">
        <span className="curriculum-row__icon">PDF</span>
        <span className="hint">
          {sheet === undefined ? '등록된 커리큘럼 PDF가 없습니다' : `${sheet.title} · ${sheet.rows.length}일차`}
        </span>
      </div>
      <button type="button" className="btn btn--soft btn--md">
        <Icon name="picture_as_pdf" size={18} />
        PDF 보기
      </button>
    </div>
  );
}

/** 다가오는 자격 시험 — widgets/qual_exam_schedule_section.dart */
function QualExamCard() {
  const exams = useQualExams();
  const upcoming = exams.slice(0, 2);

  return (
    <div className="panel side-card">
      <header className="side-card__head">
        <h3 className="side-card__title">다가오는 자격 시험</h3>
        <Link className="section__more" to={RoutePaths.qualExams}>
          전체 보기
        </Link>
      </header>
      {upcoming.length === 0 ? (
        <p className="hint">다가오는 시험 일정이 없습니다</p>
      ) : (
        upcoming.map((exam) => (
          <div key={`${exam.qualgbNm}-${exam.implSeq}`} className="exam-row">
            <strong>{exam.qualgbNm}</strong>
            <span className="hint">
              필기 접수 {formatYmd(exam.docRegStartDt)} ~ {formatYmd(exam.docRegEndDt)}
            </span>
          </div>
        ))
      )}
    </div>
  );
}

/** 승인 현황 */
function ApprovalCard() {
  const user = useCurrentUser();
  const submissions = useMySubmissions(user.uid).slice(0, 4);

  return (
    <div className="panel side-card">
      <h3 className="side-card__title">승인 현황</h3>
      {submissions.length === 0 ? (
        <p className="hint">제출 내역이 없습니다</p>
      ) : (
        submissions.map((s) => (
          <div key={s.id} className="approval-row">
            <span className="approval-row__top">
              <Badge tone="primary">{RecordTypeLabels[s.type]}</Badge>
              <Badge tone={s.status === 'approved' ? 'success' : s.status === 'pending' ? 'warning' : 'error'}>
                {SubmissionStatusLabels[s.status]}
              </Badge>
            </span>
            <span className="approval-row__title">{s.title}</span>
          </div>
        ))
      )}
    </div>
  );
}

/** 이번 주 학습 추천 — widgets/weekly_learning_recommend_section.dart */
function WeeklyLearningSection() {
  const user = useCurrentUser();
  const videos = useYoutubeRecommendations().filter((v) => v.isPublished);

  const ranked = videos
    .map((v) => ({
      video: v,
      score: v.tags.filter((t) => user.skills.some((s) => s.toLowerCase() === t.toLowerCase())).length,
    }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 3);

  return (
    <section className="section">
      <header className="section__head">
        <h2 className="section__title">이번 주 학습 추천</h2>
        <span className="spacer" />
        <Link className="section__more" to={RoutePaths.studyRoom}>
          학습실
        </Link>
      </header>

      {ranked.length === 0 ? (
        <div className="panel panel--empty">
          <p>이번 주 추천 영상이 준비되면 여기에 표시됩니다.</p>
          <Link className="btn btn--outline btn--md" to={RoutePaths.studyRoom}>
            학습실 바로가기
          </Link>
        </div>
      ) : (
        <div className="grid grid--3">
          {ranked.map(({ video, score }) => (
            <a key={video.id} className="video-card" href={video.youtubeUrl} target="_blank" rel="noreferrer">
              <span className="video-card__thumb">
                <Icon name="play_circle" size={26} />
              </span>
              <strong className="video-card__title">{video.title}</strong>
              <span className="video-card__tags">
                {video.tags.slice(0, 3).map((t) => (
                  <span key={t} className="skill-chip">
                    {t}
                  </span>
                ))}
              </span>
              {score > 0 && <span className="hint">내 스택과 {score}개 일치</span>}
            </a>
          ))}
        </div>
      )}
    </section>
  );
}

/** 설문 · 제출 — features/forms의 대시보드 섹션 */
function FormTasksSection() {
  const user = useCurrentUser();
  const tasks = useFormTasks().filter((t) => t.published);
  const responses = useFormResponses();

  const open = tasks.filter((t) => t.dueAt.getTime() >= Date.now()).slice(0, 3);
  const notDone = open.filter((t) => !responses.some((r) => r.taskId === t.id && r.userId === user.uid));

  return (
    <section className="section">
      <header className="section__head">
        <h2 className="section__title">설문 · 제출</h2>
        <span className="spacer" />
        <Link className="section__more" to={RoutePaths.forms}>
          전체 보기
        </Link>
      </header>

      {notDone.length > 0 && <Badge tone="warning">미제출 {notDone.length}건</Badge>}

      {open.length === 0 ? (
        <div className="panel panel--empty">마감 전 설문이 없습니다</div>
      ) : (
        open.map((task) => {
          const responded = responses.some((r) => r.taskId === task.id && r.userId === user.uid);
          return (
            <div key={task.id} className="panel form-row">
              <div className="form-row__head">
                <strong className="form-row__title">{task.title}</strong>
                <span className="spacer" />
                <Badge tone={responded ? 'success' : 'warning'}>{responded ? '제출' : '미제출'}</Badge>
              </div>
              <span className="form-row__due">
                <Icon name="schedule" size={15} />
                마감 {formatDate(task.dueAt)} · {formatDueIn(task.dueAt)}
              </span>
              <div className="form-row__actions">
                <a className="btn btn--filled btn--md" href={task.formUrl} target="_blank" rel="noreferrer">
                  <Icon name="description" size={17} />
                  구글폼 작성
                </a>
                {task.notionGuideUrl !== undefined && (
                  <a className="btn btn--outline btn--md" href={task.notionGuideUrl} target="_blank" rel="noreferrer">
                    <Icon name="menu_book" size={17} />
                    노션 가이드
                  </a>
                )}
              </div>
            </div>
          );
        })
      )}
    </section>
  );
}
