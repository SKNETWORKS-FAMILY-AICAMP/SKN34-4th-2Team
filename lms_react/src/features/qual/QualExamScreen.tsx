import { useState } from 'react';

import { syncQualExams, useQualExams, useQualExamsSyncedAt } from '../../data/repository';
import { readApiError } from '../../data/http';
import type { QualExamSchedule } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { ErrorState, PageHeader, Skeleton } from '../../ui/components';
import { formatYmd } from '../../utils/format';
import { useCurrentUser } from '../auth/session';
import {
  examName,
  nextStageLabel,
  roundLabel,
  stageStatus,
  stagesOf,
  startOfToday,
  subjectsOf,
  upcomingExams,
  type NextStage,
  type QualStage,
} from './qualExams';

function syncedLabel(at: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${at.getMonth() + 1}/${at.getDate()} ${pad(at.getHours())}:${pad(at.getMinutes())} 기준`;
}

/**
 * 자격 시험 일정 — features/dashboard/presentation/qual_exam_schedules_screen.dart
 *
 * 서버는 정보기술 분야 종목만 Q-Net 에서 받는다. 위쪽 칩으로 종목을 고르면
 * 그 종목의 남은 회차가 다음 단계 날짜순으로 나온다. 다 끝난 회차는 빠진다.
 */
export function QualExamScreen() {
  const examsQuery = useQualExams();
  const syncedAt = useQualExamsSyncedAt();
  const user = useCurrentUser();
  const [picked, setPicked] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  const refresh = async () => {
    setSyncing(true);
    setSyncMessage(null);
    try {
      const counts = await syncQualExams();
      const total = Object.values(counts).reduce((sum, n) => sum + n, 0);
      setSyncMessage(`최신 일정 ${total}건을 받았습니다.`);
    } catch (error) {
      setSyncMessage(await readApiError(error));
    } finally {
      setSyncing(false);
    }
  };

  if (examsQuery.loading) return <Skeleton rows={3} />;
  if (examsQuery.error !== null) {
    return <ErrorState message="시험 일정을 불러오지 못했습니다" onRetry={() => window.location.reload()} />;
  }

  const exams = examsQuery.data ?? [];
  const today = startOfToday();
  const subjects = subjectsOf(exams);
  const subject = picked !== null && subjects.includes(picked) ? picked : subjects[0];
  const upcoming = upcomingExams(
    exams.filter((e) => examName(e) === subject),
    today,
  );

  return (
    <div className="qual-page">
      <div className="qual-column">
        <PageHeader
          title="자격 시험 일정"
          description="정보기술 분야 국가기술자격(Q-Net) 시험의 접수 · 시험 · 발표 일정을 확인하세요."
        />

        {subjects.length > 1 && (
          <div className="mchips" role="radiogroup" aria-label="종목">
            {subjects.map((name) => (
              <button
                key={name}
                type="button"
                role="radio"
                aria-checked={name === subject}
                className={`mchip${name === subject ? ' mchip--on' : ''}`}
                onClick={() => setPicked(name)}
              >
                {name}
              </button>
            ))}
          </div>
        )}

        <div className="qual-meta">
          <p className="qual-count">
            {subject ?? '자격 시험'} · 남은 회차 {upcoming.length}개
          </p>
          {syncedAt !== undefined && <span className="hint">{syncedLabel(syncedAt)}</span>}
          {user.role === 'admin' && (
            <button
              type="button"
              className="btn btn--text btn--sm"
              onClick={() => void refresh()}
              disabled={syncing}
              title="Q-Net 에서 지금 다시 받기"
            >
              <Icon name="refresh" size={16} />
              {syncing ? '받는 중…' : '지금 새로고침'}
            </button>
          )}
        </div>
        {syncMessage !== null && <p className="hint">{syncMessage}</p>}

        {upcoming.length === 0 ? (
          <p className="qual-empty">남은 시험 일정이 없습니다</p>
        ) : (
          <div className="panel qual-list">
            {upcoming.map(({ exam, next }) => (
              <ExamTimeline
                key={`${exam.jmCd ?? exam.qualgbNm}-${exam.implYy}-${exam.implSeq}-${exam.description}`}
                exam={exam}
                next={next}
                today={today}
              />
            ))}
          </div>
        )}

        <p className="qual-source">출처: 한국산업인력공단 공공데이터 (Q-Net)</p>
      </div>
    </div>
  );
}

function periodText(from?: string, to?: string): string {
  return `${formatYmd(from)}${to !== undefined && to !== from ? ` ~ ${formatYmd(to)}` : ''}`;
}

function stageText(stage: QualStage): string {
  const extra = (stage.extra ?? []).map(([from, to]) => ` · 추가 접수 ${periodText(from, to)}`).join('');
  return periodText(stage.from, stage.to) + extra;
}

/** widgets/qual_exam_timeline.dart */
function ExamTimeline({ exam, next, today }: { exam: QualExamSchedule; next: NextStage; today: Date }) {
  return (
    <article className="qual-exam">
      <header className="qual-exam__head">
        <strong>{examName(exam)}</strong>
        <span className="qual-exam__seq">{roundLabel(exam)}</span>
        <span className={`qual-exam__dday${next.days === 0 ? ' qual-exam__dday--now' : ''}`}>
          {nextStageLabel(next)}
        </span>
      </header>

      <ol className="timeline">
        {stagesOf(exam).map((stage) => {
          const status = stageStatus(stage, today);
          return (
            <li key={stage.label} className={`timeline__item timeline__item--${status}`}>
              <span className="timeline__dot" aria-hidden />
              <div>
                <strong className="timeline__label">{stage.label}</strong>
                <span className="hint">{stageText(stage)}</span>
              </div>
            </li>
          );
        })}
      </ol>
    </article>
  );
}
