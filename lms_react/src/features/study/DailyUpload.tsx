import { useEffect, useRef, useState } from 'react';

import { readApiError } from '../../data/http';
import { commitFolderUpload, planFolderUpload, refreshAfterFolderUpload } from '../../data/repository';
import { Icon } from '../../ui/Icon';
import { Button, Dialog, ProgressBar, Row, Select } from '../../ui/components';
import { readPicked } from './folderFiles';
import {
  NEW_FILE,
  batches,
  dailyFolders,
  dailyPending,
  dailyPickedPath,
  dailyUploads,
  type DailyChoice,
  type DailyFile,
  type DailyPlan,
} from './folderUploadModel';

/**
 * 오늘 수업 올리기 — 폴더로 올린 과목에 그날 쓴 파일만. 올린 날이 수업 날짜다(기본 오늘, 깜빡하면 어제로).
 *
 * 파일마다 서버가 지난번과 견준다: 같음(건너뜀) · 새 버전(바뀐 부분만 그날 수업) · 같은 이름이 여럿(어느 파일인지 고르기) ·
 * 새 파일(넣을 폴더 추천 — 같은 폴더 → 코드가 비슷한 큰 주제 → 여러 주제에 걸치면 날짜 폴더). 폴더째 고르면 그 안의 구조 그대로.
 * 공휴일 · 커리큘럼 밖 날짜는 막지 않고 묻는다.
 */

const short = (d: string) => `${Number(d.slice(5, 7))}/${Number(d.slice(8))}`;

function localToday(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

type Stage = 'pick' | 'reading' | 'review' | 'uploading' | 'done';

export function DailyUpload({
  cohortId,
  source,
  onClose,
}: {
  cohortId: string;
  source: { id: string; title: string };
  onClose(): void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const [today] = useState(localToday);
  const [date, setDate] = useState(today);
  const [stage, setStage] = useState<Stage>('pick');
  const [files, setFiles] = useState<Map<string, File>>(new Map());
  const [rows, setRows] = useState<Parameters<typeof planFolderUpload>[0]['files']>([]);
  const [plan, setPlan] = useState<DailyPlan | null>(null);
  const [choices, setChoices] = useState<Record<string, DailyChoice>>({});
  const [error, setError] = useState('');
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [sent, setSent] = useState(0);

  useEffect(() => {
    folderInput.current?.setAttribute('webkitdirectory', '');
  }, []);

  const makePlan = async (nextRows: typeof rows, day: string) => {
    setError('');
    try {
      setPlan(await planFolderUpload<DailyPlan>({ cohortId, mode: 'daily', target: source.id, date: day, files: nextRows }));
      setStage('review');
    } catch (e) {
      setError(await readApiError(e));
      setStage(nextRows.length ? 'review' : 'pick');
    }
  };

  const pick = async (picked: File[], fromFolder: boolean) => {
    if (!picked.length) return;
    setStage('reading');
    setError('');
    const read = (await readPicked(picked)).filter((p) => p.row);
    if (!read.length) {
      setError('수업 파일(.ipynb · .py · .md · .sql · .html · .css · .js)을 찾지 못했어요.');
      setStage(plan ? 'review' : 'pick');
      return;
    }
    const nextFiles = new Map<string, File>();
    const nextRows = read.map((p) => {
      const path = dailyPickedPath(p.path, fromFolder);
      nextFiles.set(path, p.file);
      return { ...p.row!, path };
    });
    setFiles(nextFiles);
    setRows(nextRows);
    setChoices({});
    await makePlan(nextRows, date);
  };

  const changeDate = (day: string) => {
    if (!day) return;
    setDate(day);
    // 날짜 폴더 추천 · 수업 없는 날 확인이 날짜에 따라 바뀐다
    if (rows.length) void makePlan(rows, day);
  };

  const choose = (path: string, change: DailyChoice) => setChoices((cur) => ({ ...cur, [path]: { ...cur[path], ...change } }));

  const uploads = plan ? dailyUploads(plan.files, choices) : [];
  const pending = plan ? dailyPending(plan.files, choices) : 0;
  const future = date > today;

  const upload = async () => {
    setStage('uploading');
    setError('');
    const parts = batches(uploads.map((u) => ({ path: u.to, date, size: u.size })));
    const fromOf = new Map(uploads.map((u) => [u.to, u.from]));
    setProgress({ done: 0, total: uploads.length });
    let done = 0;
    try {
      for (const part of parts) {
        await commitFolderUpload({
          cohortId,
          sourceId: source.id,
          manifest: { paths: part.map((p) => p.path), days: [{ date, files: part.map((_, i) => i) }], past: [] },
          files: part.map((p) => files.get(fromOf.get(p.path)!)!),
        });
        done += part.length;
        setProgress({ done, total: uploads.length });
      }
      setSent(done);
      setStage('done');
      await refreshAfterFolderUpload();
    } catch (e) {
      setError(await readApiError(e));
      setStage('review');
    }
  };

  const busy = stage === 'reading' || stage === 'uploading';
  return (
    <Dialog
      title={`오늘 수업 올리기 — ${source.title}`}
      width={720}
      onClose={() => !busy && onClose()}
      actions={
        stage === 'done' ? (
          <Button onClick={onClose}>닫기</Button>
        ) : (
          <>
            <span className="hint fu__daily-hint">
              {pending ? '노란 줄에서 어느 파일인지 골라 주세요.' : uploads.length ? `${uploads.length}개를 ${short(date)} 수업으로 올려요` : ''}
            </span>
            <Button variant="outline" disabled={busy} onClick={onClose}>
              취소
            </Button>
            <Button disabled={busy || !plan || pending > 0 || uploads.length === 0 || future} onClick={() => void upload()}>
              {stage === 'uploading' ? '올리는 중…' : '올리기'}
            </Button>
          </>
        )
      }
    >
      {stage === 'done' ? (
        <div className="callout callout--success" role="status">
          {sent}개를 {short(date)} 수업으로 올렸어요. 18:30 자동 출제 때 그날 늘어난 내용으로 복습 문제와 노트가 만들어져요.
        </div>
      ) : (
        <div className="fu fu--daily">
          <Row gap={8}>
            <label className="fu__day">
              수업 날짜
              <input
                type="date"
                className="input"
                value={date}
                max={today}
                disabled={busy}
                aria-label="수업 날짜"
                onChange={(e) => changeDate(e.target.value)}
              />
            </label>
            <Button size="sm" variant="outline" icon={<Icon name="upload_file" size={16} />} disabled={busy} onClick={() => fileInput.current?.click()}>
              파일 고르기
            </Button>
            <Button size="sm" variant="outline" icon={<Icon name="folder_open" size={16} />} disabled={busy} onClick={() => folderInput.current?.click()}>
              폴더 고르기
            </Button>
          </Row>
          <p className="hint">
            {date === today ? '오늘 수업이면 그대로 두세요. 깜빡하고 다음 날 올리면 어제로 바꿔요.' : `${short(date)} 수업으로 올려요.`} 그날 쓴 파일만
            고르면 돼요 — 지난번과 같은 파일은 건너뛰고, 이어 쓴 노트북은 늘어난 부분만 그날 수업이 돼요.
          </p>
          {plan?.warnings.map((w, i) => (
            <div key={i} className="callout callout--warning">
              {w.text}
            </div>
          ))}
          {error !== '' && <div className="callout callout--error">{error}</div>}
          {stage === 'reading' && <span className="hint" role="status">읽는 중…</span>}
          {plan && (
            <ul className="fu__rows">
              {plan.files.map((f) => (
                <DailyLine key={f.path} file={f} plan={plan} choice={choices[f.path]} disabled={busy} onChoose={(c) => choose(f.path, c)} />
              ))}
            </ul>
          )}
          {stage === 'uploading' && (
            <div className="fu__progress" role="status">
              <ProgressBar value={progress.done} max={progress.total} />
              <span className="hint">
                올리는 중 {progress.done}/{progress.total}
              </span>
            </div>
          )}
          <input
            ref={fileInput}
            type="file"
            multiple
            hidden
            aria-label="수업 파일"
            onChange={(e) => {
              const picked = [...(e.target.files ?? [])];
              e.target.value = '';
              void pick(picked, false);
            }}
          />
          <input
            ref={folderInput}
            type="file"
            multiple
            hidden
            aria-label="수업 폴더"
            onChange={(e) => {
              const picked = [...(e.target.files ?? [])];
              e.target.value = '';
              void pick(picked, true);
            }}
          />
        </div>
      )}
    </Dialog>
  );
}

function DailyLine({
  file: f,
  plan,
  choice,
  disabled,
  onChoose,
}: {
  file: DailyFile;
  plan: DailyPlan;
  choice: DailyChoice | undefined;
  disabled: boolean;
  onChoose(c: DailyChoice): void;
}) {
  if (f.status === 'same') {
    return (
      <li className="fu__row fu__row--past fu__daily">
        <Icon name="check" size={16} />
        <span className="fu__basis">{f.path}</span>
        <span className="fu__files hint">{f.target} 와 내용이 같아요 — 건너뛰어요</span>
      </li>
    );
  }
  if (f.status === 'update') {
    return (
      <li className="fu__row fu__daily">
        <Icon name="sync" size={16} />
        <span className="fu__basis">{f.path}</span>
        <span className="fu__files hint">{f.target} 의 새 버전 — 바뀐 부분만 {short(plan.date)} 수업이 돼요</span>
      </li>
    );
  }
  const asNew = f.status === 'new' || choice?.target === NEW_FILE;
  return (
    <li className={`fu__row fu__daily${f.status === 'pick' && !choice?.target ? ' fu__row--check' : ''}`}>
      <Icon name={f.status === 'pick' ? 'help' : 'add'} size={16} />
      <span className="fu__basis">
        {f.path} {f.status === 'new' && <span className="hint">새 파일</span>}
      </span>
      <span className="fu__files fu__choose">
        {f.status === 'pick' && (
          <Select
            aria-label={`${f.path} 어느 파일인지`}
            value={choice?.target ?? ''}
            disabled={disabled}
            onChange={(e) => onChoose({ target: e.target.value })}
          >
            <option value="">같은 이름이 {f.options?.length}군데 — 어느 파일의 새 버전인가요?</option>
            {f.options?.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
            <option value={NEW_FILE}>새 파일로 넣기</option>
          </Select>
        )}
        {asNew && (
          <>
            <Select
              aria-label={`${f.path} 넣을 폴더`}
              value={choice?.folder ?? f.folder ?? `${plan.date}/`}
              disabled={disabled}
              onChange={(e) => onChoose({ folder: e.target.value })}
            >
              {dailyFolders(plan).map((d) => (
                <option key={d} value={d}>
                  {d.endsWith('/') ? `날짜 폴더 ${d}` : `${'　'.repeat(d.split('/').length - 1)}${d.split('/').pop()}/`}
                </option>
              ))}
              {f.folder && !dailyFolders(plan).includes(f.folder) && <option value={f.folder}>새 폴더 {f.folder}/</option>}
            </Select>
            <span className="hint">에 넣어요{!choice?.folder && f.why ? ` · 추천: ${f.why}` : ''}</span>
          </>
        )}
      </span>
    </li>
  );
}
