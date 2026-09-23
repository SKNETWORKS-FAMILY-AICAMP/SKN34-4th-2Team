import { useEffect, useState, type FormEvent } from 'react';

import { readApiError } from '../../data/http';
import {
  addGithubOwner,
  fetchGithubOwners,
  fetchPracticeAuto,
  refreshAfterPractice,
  removeGithubOwner,
  runPracticeNow,
  setPracticeAuto,
  setStudySourceActive,
  syncStudySources,
  useStudySources,
  type GithubOwner,
  type PracticeAutoRun,
  type PracticeAutoStatus,
  type StudySourceSync,
} from '../../data/repository';
import { Icon } from '../../ui/Icon';
import { Button, Row, Spacer, TextInput, Toggle } from '../../ui/components';
import { formatRelative } from '../../utils/format';

/**
 * 수업 저장소 관리 — 강사(자기 기수)와 관리자(고른 기수)가 같이 쓴다.
 *
 * 기수에 GitHub 조직이나 강사 개인 계정을 연결해 두면 서버가 저장소를 찾아 **바로 공개**로 올린다.
 * 여기서 하는 일은 연결과 숨기기뿐. 숨긴 저장소는 다시 찾아도 숨긴 채로 남는다.
 * 화면을 열 때 한 번 찾는다(서버가 10분에 한 번까지만 GitHub 에 묻는다).
 *
 * 복습 문제는 매일 18:30 에 공개된 저장소마다 그날 새로 올라온 내용으로 자동 출제된다(저장소마다 끌 수 있다).
 * 수업이 일찍 끝났으면 「지금 만들기」. 출제 중이면 10초마다 끝났는지 본다.
 */
const PRACTICE_POLL_MS = 10_000;

export function StudySourcesPanel({ cohortId }: { cohortId: string }) {
  const sources = useStudySources().filter((s) => !s.cohortId || s.cohortId === cohortId);
  const [owners, setOwners] = useState<GithubOwner[] | null>(null);
  const [owner, setOwner] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [practice, setPractice] = useState<PracticeAutoStatus | null>(null);

  const apply = (result: StudySourceSync) => {
    setOwners(result.owners);
    setNotice(result.added.length ? `새 저장소 ${result.added.length}개를 공개로 올렸어요 — ${result.added.join(', ')}` : '');
  };

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError('');
    try {
      await work();
    } catch (e) {
      setError(await readApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const loadPractice = () =>
    fetchPracticeAuto(cohortId)
      .then(setPractice)
      .catch(() => {
        // 출제 상태를 못 읽어도 저장소 관리는 된다
      });

  useEffect(() => {
    void loadPractice();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cohortId]);

  // 출제 중인 저장소가 있으면 끝날 때까지 — 끝나면 새 세트가 화면에 보이게 스냅샷도 다시 받는다
  const running = Object.values(practice?.sources ?? {}).some((p) => p.lastRun?.status === 'running');
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => {
      fetchPracticeAuto(cohortId)
        .then((next) => {
          setPractice(next);
          if (!Object.values(next.sources).some((p) => p.lastRun?.status === 'running')) void refreshAfterPractice();
        })
        .catch(() => undefined);
    }, PRACTICE_POLL_MS);
    return () => window.clearInterval(timer);
  }, [running, cohortId]);

  useEffect(() => {
    let alive = true;
    setOwners(null);
    setNotice('');
    fetchGithubOwners(cohortId)
      .then(async (found) => {
        if (!alive) return;
        setOwners(found);
        if (found.length) {
          const result = await syncStudySources(cohortId);
          if (alive) apply(result);
        }
      })
      .catch(async (e) => {
        const reason = await readApiError(e);
        if (alive) setError(reason);
      });
    return () => {
      alive = false;
    };
  }, [cohortId]);

  const connect = (e: FormEvent) => {
    e.preventDefault();
    if (!owner.trim()) return;
    void run(async () => {
      apply(await addGithubOwner(cohortId, owner.trim()));
      setOwner('');
    });
  };

  const failed = (owners ?? []).filter((o) => o.lastError);
  const lastSync = (owners ?? []).map((o) => o.lastSyncedAt).filter(Boolean).sort().at(-1);

  return (
    <div className="study-sources">
      <div className="study-sources__owners">
        <strong>연결된 GitHub</strong>
        <p className="hint">
          기수 조직이나 강사 개인 계정 이름을 연결하면, 그 안의 저장소가 학생 공부방에 자동으로 올라가요. 올리고 싶지 않은 저장소는 아래에서
          숨기세요. 비공개 저장소는 서버의 GitHub 계정이 읽을 수 있어야 해요 — 강사 개인 저장소라면 그 계정을 협업자(읽기)로 초대해 주세요.
        </p>
        <Row gap={6}>
          {owners === null && <span className="hint">불러오는 중…</span>}
          {owners?.map((o) => (
            <span key={o.id} className={`chip${o.lastError ? ' chip--warn' : ''}`} title={o.lastError || undefined}>
              <Icon name={o.lastError ? 'error' : 'hub'} size={15} />
              {o.owner}
              <button
                type="button"
                className="chip__remove"
                aria-label={`${o.owner} 연결 끊기`}
                disabled={busy}
                onClick={() => void run(async () => setOwners(await removeGithubOwner(o.id)))}
              >
                <Icon name="close" size={14} />
              </button>
            </span>
          ))}
        </Row>
        <form className="study-sources__add" onSubmit={connect}>
          <TextInput
            id="study-source-owner"
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
            placeholder="예: skn-ai34-260616 또는 강사 GitHub 계정"
            aria-label="GitHub 조직 또는 계정"
          />
          <Button type="submit" disabled={busy || !owner.trim()}>
            연결
          </Button>
        </form>
        <Row gap={8}>
          <Button variant="outline" size="sm" disabled={busy || !owners?.length} onClick={() => void run(async () => apply(await syncStudySources(cohortId, true)))}>
            <Icon name="refresh" size={16} />
            {busy ? '찾는 중…' : '저장소 새로 찾기'}
          </Button>
          {lastSync && <span className="hint">마지막으로 찾은 때 {formatRelative(new Date(lastSync))}</span>}
        </Row>
        {notice !== '' && <div className="callout" role="status">{notice}</div>}
        {failed.map((o) => (
          <div key={o.id} className="callout callout--error">
            {o.owner}: {o.lastError}
          </div>
        ))}
        {error !== '' && <div className="callout callout--error">{error}</div>}
        <p className="hint">
          <Icon name="schedule" size={14} /> 복습 문제는 매일 <strong>18:30</strong>에 공개된 저장소마다 그날 새로 올라온 수업 내용으로 자동
          출제돼요. 저녁 늦게 올린 커밋은 다음 날 출제 때 그 날짜로 이어서 채워요.
        </p>
        {practice && !practice.practiceReady && (
          <div className="callout callout--error">복습 문제 저장소(practice 스키마)가 없어 출제할 수 없어요. practice_schema.sql 을 실행하세요.</div>
        )}
      </div>

      {sources.length === 0 ? (
        <p className="hint">아직 올라간 저장소가 없어요. GitHub 조직이나 계정을 연결하세요.</p>
      ) : (
        sources.map((src) => (
          <div key={src.id} className={`media-row${src.isActive ? '' : ' media-row--off'}`}>
            <span className="media-row__main media-row__main--plain">
              <span className="media-row__body">
                <strong>{src.title}</strong>
                <a className="media-row__repo" href={src.repoUrl} target="_blank" rel="noreferrer">
                  {src.repoUrl.replace(/^https?:\/\/github\.com\//, '')}
                </a>
                <span className="hint">
                  {src.branch}
                  {src.allowedPrefixes.length > 0 && ` · ${src.allowedPrefixes.join(', ')}`}
                </span>
                <PracticeLine
                  enabled={practice?.sources[src.id]?.enabled ?? true}
                  lastRun={practice?.sources[src.id]?.lastRun ?? null}
                  disabled={busy || !src.isActive || practice === null}
                  onToggle={(next) =>
                    void run(async () => {
                      await setPracticeAuto(src.id, next);
                      await loadPractice();
                    })
                  }
                  onRunNow={() =>
                    void run(async () => {
                      await runPracticeNow(src.id);
                      await loadPractice();
                    })
                  }
                />
              </span>
            </span>
            <Spacer />
            <Toggle
              checked={src.isActive}
              label={src.isActive ? '공개' : '숨김'}
              onChange={(next) => void run(() => setStudySourceActive(src.id, next))}
            />
          </div>
        ))
      )}
    </div>
  );
}

/** 저장소 한 줄 아래 — 자동 출제 켜기 · 마지막 출제 · 지금 만들기 */
function PracticeLine({
  enabled,
  lastRun,
  disabled,
  onToggle,
  onRunNow,
}: {
  enabled: boolean;
  lastRun: PracticeAutoRun | null;
  disabled: boolean;
  onToggle(next: boolean): void;
  onRunNow(): void;
}) {
  const running = lastRun?.status === 'running';
  return (
    <span className="source-practice">
      <Toggle checked={enabled} label="복습 문제 자동 출제" onChange={(next) => !disabled && onToggle(next)} />
      <span className={`hint${lastRun?.status === 'failed' ? ' source-practice__error' : ''}`}>{runText(lastRun)}</span>
      <button type="button" className="btn btn--text btn--sm" disabled={disabled || running} onClick={onRunNow}>
        {running ? '출제 중…' : '지금 만들기'}
      </button>
    </span>
  );
}

function runText(run: PracticeAutoRun | null): string {
  if (!run) return '아직 출제 전';
  if (run.status === 'running') return '출제 중이에요 — 몇 분 걸려요';
  const when = run.finishedAt ? formatRelative(new Date(run.finishedAt)) : '';
  if (run.status === 'failed') return `출제 실패 ${when} — ${run.message || '이유를 알 수 없어요'}`;
  if (run.problems === 0) return `마지막 확인 ${when} · 새로 올라온 수업 내용이 없었어요`;
  const days = run.dates.map((d) => d.slice(5).replace('-', '/')).join(', ');
  return `마지막 출제 ${when} · ${days} 수업 ${run.problems}문제`;
}
