import { useEffect, useState, type FormEvent } from 'react';

import { readApiError } from '../../data/http';
import {
  addGithubOwner,
  fetchGithubOwners,
  removeGithubOwner,
  setStudySourceActive,
  syncStudySources,
  useStudySources,
  type GithubOwner,
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
 */
export function StudySourcesPanel({ cohortId }: { cohortId: string }) {
  const sources = useStudySources().filter((s) => !s.cohortId || s.cohortId === cohortId);
  const [owners, setOwners] = useState<GithubOwner[] | null>(null);
  const [owner, setOwner] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');

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
