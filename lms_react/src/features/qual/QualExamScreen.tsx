import { useState } from 'react';

import { useQualExams } from '../../data/repository';
import type { QualExamSchedule } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { ErrorState, Skeleton } from '../../ui/components';
import { formatYmd, parseYmd } from '../../utils/format';

/**
 * 자격 시험 일정 — features/dashboard/presentation/qual_exam_schedules_screen.dart
 *
 * 머리글이 없다. 가운데 좁은 줄기(560px)에 검색 한 줄, 「2026년 · 다가오는 N건」,
 * 그리고 시험 달로 묶인 타임라인 카드가 이어진다. 지난 시험은 목록에서 빠진다.
 */
const HAYSTACK = (e: QualExamSchedule) =>
  [e.description, e.qualgbNm, e.qualgbCd, String(e.implSeq), e.implYy].join(' ').toLowerCase();

/** 이 시험이 언제인지 — 필기 시험일이 있으면 그날, 없으면 실기 시험일 */
const examDayOf = (e: QualExamSchedule) => e.docExamStartDt ?? e.pracExamStartDt;

export function QualExamScreen() {
  const examsQuery = useQualExams();
  const [query, setQuery] = useState('');

  if (examsQuery.loading) return <Skeleton rows={3} />;
  if (examsQuery.error !== null) {
    return <ErrorState message="시험 일정을 불러오지 못했습니다" onRetry={() => window.location.reload()} />;
  }

  const exams = examsQuery.data ?? [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const q = query.trim().toLowerCase();

  const upcoming = exams
    .filter((e) => {
      const day = parseYmd(examDayOf(e));
      return day !== null && day.getTime() >= today.getTime();
    })
    .filter((e) => q === '' || HAYSTACK(e).includes(q))
    .sort(
      (a, b) =>
        (parseYmd(examDayOf(a))?.getTime() ?? Infinity) -
        (parseYmd(examDayOf(b))?.getTime() ?? Infinity),
    );

  // 시험 달로 묶는다 — groupByMonth
  const months = new Map<string, QualExamSchedule[]>();
  for (const exam of upcoming) {
    const day = parseYmd(examDayOf(exam));
    const label = day === null ? '일정 미정' : `${day.getFullYear()}년 ${day.getMonth() + 1}월`;
    const bucket = months.get(label);
    if (bucket === undefined) months.set(label, [exam]);
    else bucket.push(exam);
  }

  return (
    <div className="qual-page">
      <div className="qual-column">
        <label className="study-search">
          <Icon name="search" size={20} />
          <input
            className="study-search__input"
            value={query}
            placeholder="자격명·회차 검색 (예: 정보처리, 기능사, 107)"
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>

        <p className="qual-count">
          {today.getFullYear()}년 · 다가오는 {upcoming.length}건
        </p>

        {upcoming.length === 0 ? (
          <p className="qual-empty">조건에 맞는 시험 일정이 없습니다</p>
        ) : (
          [...months.entries()].map(([month, items]) => (
            <section key={month} className="qual-month">
              <h2 className="qual-month__title">{month}</h2>
              <div className="panel qual-month__card">
                {items.map((exam) => (
                  <ExamTimeline key={`${exam.qualgbNm}-${exam.implYy}-${exam.implSeq}`} exam={exam} />
                ))}
              </div>
            </section>
          ))
        )}

        <p className="qual-source">출처: 한국산업인력공단 공공데이터</p>
      </div>
    </div>
  );
}

/** widgets/qual_exam_timeline.dart */
function ExamTimeline({ exam }: { exam: QualExamSchedule }) {
  const stages = [
    { label: '필기 접수', from: exam.docRegStartDt, to: exam.docRegEndDt },
    { label: '필기 시험', from: exam.docExamStartDt, to: exam.docExamEndDt },
    { label: '필기 발표', from: exam.docPassDt, to: exam.docPassDt },
    { label: '실기 접수', from: exam.pracRegStartDt, to: exam.pracRegEndDt },
    { label: '실기 시험', from: exam.pracExamStartDt, to: exam.pracExamEndDt },
    { label: '실기 발표', from: exam.pracPassDt, to: exam.pracPassDt },
  ].filter((s) => s.from !== undefined);

  const day = parseYmd(examDayOf(exam));
  const days =
    day === null ? null : Math.round((day.getTime() - Date.now()) / (24 * 60 * 60 * 1000));
  const dday = days === null ? '—' : days === 0 ? 'D-DAY' : days > 0 ? `D-${days}` : '종료';

  return (
    <article className="qual-exam">
      <header className="qual-exam__head">
        <strong>{exam.qualgbNm}</strong>
        <span className="qual-exam__seq">
          {exam.implYy}년 {exam.implSeq}회
        </span>
        <span className="qual-exam__dday">{dday}</span>
        <span className="spacer" />
        <span className="hint">{exam.description}</span>
      </header>

      <ol className="timeline">
        {stages.map((stage) => {
          const start = parseYmd(stage.from);
          const done = start !== null && start.getTime() < Date.now();
          return (
            <li key={stage.label} className={`timeline__item${done ? ' timeline__item--done' : ''}`}>
              <span className="timeline__dot" aria-hidden />
              <div>
                <strong className="timeline__label">{stage.label}</strong>
                <span className="hint">
                  {formatYmd(stage.from)}
                  {stage.to !== stage.from && stage.to !== undefined
                    ? ` ~ ${formatYmd(stage.to)}`
                    : ''}
                </span>
              </div>
            </li>
          );
        })}
      </ol>
    </article>
  );
}
