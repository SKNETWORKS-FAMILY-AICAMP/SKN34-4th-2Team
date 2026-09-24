import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { RoutePaths } from '../../app/routePaths';
import { readApiError } from '../../data/http';
import {
  fetchPracticeJob,
  fetchPracticeQuota,
  refreshAfterPractice,
  type PracticeJob,
  type PracticeQuota,
} from '../../data/repository';
import { Icon } from '../../ui/Icon';
import { Button } from '../../ui/components';

/** 만드는 중이면 이만큼마다 끝났는지 묻는다 — LLM 출제 + 검증에 몇 분 걸린다 */
const POLL_MS = 5000;

/**
 * 「문제 만들기」 — 노트 화면과 연습장이 같이 쓴다.
 * 누르면 서버가 일(job)을 먼저 돌려주고 뒤에서 만든다. 다 되면 「문제 풀기」로 그 세트를 연다.
 * 만든 세트는 만든 학생만 보고, 공부방 「내가 만든 문제」에도 모인다.
 */
export function MakeProblems({
  start,
  idleLabel,
  hint,
}: {
  start: () => Promise<PracticeJob>;
  idleLabel: string;
  hint: string;
}) {
  const [quota, setQuota] = useState<PracticeQuota | null>(null);
  const [job, setJob] = useState<PracticeJob | null>(null);
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    fetchPracticeQuota()
      .then(setQuota)
      .catch(() => undefined);
  }, []);

  const jobId = job?.status === 'running' ? job.id : null;
  useEffect(() => {
    if (!jobId) return;
    const timer = window.setInterval(() => {
      fetchPracticeJob(jobId)
        .then(async (next) => {
          if (next.status === 'done') await refreshAfterPractice();
          setJob(next);
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [jobId]);

  const go = async () => {
    setStarting(true);
    setError('');
    try {
      setJob(await start());
      setQuota((q) => (q ? { ...q, used: q.used + 1 } : q));
    } catch (e) {
      setError(await readApiError(e));
    } finally {
      setStarting(false);
    }
  };

  const left = quota ? Math.max(0, quota.limit - quota.used) : null;

  return (
    <div className="make-problems">
      <Icon name="auto_awesome" size={18} />
      <div className="make-problems__body">
        {job?.status === 'running' ? (
          <span>
            <strong>{job.label}</strong>로 문제를 만들고 있어요. 출제하고 실제로 돌려 확인하느라 몇 분 걸려요 — 다른 화면에 가도 계속 만들어요.
          </span>
        ) : job?.status === 'done' && job.setId ? (
          <span>
            <strong>{job.label}</strong> — {job.message} 공부방 「내가 만든 문제」에도 있어요.
          </span>
        ) : job?.status === 'failed' ? (
          <span className="make-problems__error">{job.message || '문제를 만들지 못했어요.'}</span>
        ) : (
          <span className="hint">
            {hint}
            {left !== null && ` 오늘 ${left}번 더 만들 수 있어요.`}
          </span>
        )}
        {error !== '' && <span className="make-problems__error">{error}</span>}
      </div>
      {job?.status === 'done' && job.setId ? (
        <Link className="btn btn--filled btn--sm" to={`${RoutePaths.studyRoomPlayground}?set=${encodeURIComponent(job.setId)}`}>
          문제 풀기
          <Icon name="arrow_forward" size={16} />
        </Link>
      ) : (
        <Button size="sm" variant="outline" disabled={starting || job?.status === 'running' || left === 0} onClick={() => void go()}>
          {job?.status === 'running' ? '만드는 중…' : job?.status === 'failed' ? '다시 만들기' : idleLabel}
        </Button>
      )}
    </div>
  );
}
