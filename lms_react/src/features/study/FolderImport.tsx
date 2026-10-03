import { useEffect, useMemo, useRef, useState } from 'react';

import { readApiError } from '../../data/http';
import { commitFolderUpload, planFolderUpload, refreshAfterFolderUpload } from '../../data/repository';
import { Icon } from '../../ui/Icon';
import { Badge, Button, ProgressBar, Row, Select } from '../../ui/components';
import { readPicked, type PickedFile } from './folderFiles';
import {
  batches,
  blockedReason,
  dayNotice,
  initialDates,
  manifest,
  pickedPathOf,
  reviewRows,
  setRowDate,
  uploadItems,
  withEstimates,
  withoutEstimates,
  type Basis,
  type DateChoice,
  type ImportPlan,
  type PlanSubject,
  type ReviewRow,
} from './folderUploadModel';

/**
 * 폴더 올리기 — 처음 가져오기(GitHub 없이). 폴더 고르기 → 브라우저에서 읽기(지문 · 앞부분 글) → 서버 계획 → 확인 → 100개씩 올리기.
 *
 * 날짜 단서가 없는 파일은 「날짜 없이 지난 자료」로 가져온다(막지 않는다). 날짜별 노트 · 복습 문제가 필요하면 큰 주제마다 날짜를 고르거나
 * 「커리큘럼으로 날짜 채우기」. 커리큘럼 · 공휴일은 틀릴 수 있어 고른 날짜가 수업 없는 날이면 묻기만 한다.
 * 오늘부터는 과목의 「오늘 수업 올리기」로 올린 날이 수업 날짜가 된다.
 */

type Stage = 'pick' | 'reading' | 'review' | 'uploading' | 'done';

const BASIS_LABEL: Record<Basis, string> = {
  name: '이름에서 찾음',
  content: '파일 안에서 찾음',
  round: '회차로 셈',
  time: '수정 날짜 · 확인',
  pick: '',
  split: '두 날에 걸친 파일 · 첫 날짜로',
};

const short = (d: string) => (d ? `${Number(d.slice(5, 7))}/${Number(d.slice(8))}` : '-');

interface SubjectState {
  dates: DateChoice;
  expanded: Set<string>;
}

interface Uploaded {
  name: string;
  created: boolean;
  days: string[];
  past: number;
  same: number;
}

export function FolderImport({ cohortId, onDone }: { cohortId: string; onDone(): void }) {
  const input = useRef<HTMLInputElement>(null);
  const [stage, setStage] = useState<Stage>('pick');
  const [picked, setPicked] = useState<PickedFile[]>([]);
  const [readDone, setReadDone] = useState(0);
  const [plan, setPlan] = useState<ImportPlan | null>(null);
  const [state, setState] = useState<Record<string, SubjectState>>({});
  const [topics, setTopics] = useState<Record<string, string>>({});
  const [error, setError] = useState('');
  const [progress, setProgress] = useState({ done: 0, total: 0, label: '' });
  const [uploaded, setUploaded] = useState<Uploaded[]>([]);

  useEffect(() => {
    // 폴더 고르기 — React 는 webkitdirectory 를 모른다
    input.current?.setAttribute('webkitdirectory', '');
  }, []);

  const rows = useMemo(() => picked.flatMap((p) => (p.row ? [p.row] : [])), [picked]);
  const notLesson = picked.length - rows.length;

  const makePlan = async (what?: 'subject' | 'cohort', nextTopics = topics) => {
    setError('');
    try {
      const next = await planFolderUpload<ImportPlan>({ cohortId, mode: 'import', files: rows, what, topics: nextTopics });
      setPlan(next);
      setState((cur) =>
        Object.fromEntries(
          next.subjects.map((s) => [s.name, { dates: initialDates(s), expanded: cur[s.name]?.expanded ?? new Set<string>() }]),
        ),
      );
      setStage('review');
    } catch (e) {
      setError(await readApiError(e));
      setStage('pick');
    }
  };

  const pick = async (files: File[]) => {
    if (!files.length) return;
    setStage('reading');
    setError('');
    setReadDone(0);
    const read = await readPicked(files, (done) => setReadDone(done));
    setPicked(read);
    if (!read.some((p) => p.row)) {
      setError('수업 파일(.ipynb · .py · .md · .sql · .html · .css · .js)을 찾지 못했어요.');
      setStage('pick');
      return;
    }
  };

  // 읽기가 끝나면 계획
  useEffect(() => {
    if (stage === 'reading' && picked.length && rows.length) void makePlan();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [picked]);

  const update = (name: string, change: (s: SubjectState) => SubjectState) =>
    setState((cur) => ({ ...cur, [name]: change(cur[name]) }));

  const blocked = plan ? plan.subjects.map((s) => blockedReason(s, state[s.name]?.dates ?? {}, plan.calendar)).filter(Boolean) : [];

  const upload = async () => {
    if (!plan) return;
    const byPath = new Map(picked.map((p) => [p.path, p.file]));
    const work = plan.subjects.map((s) => ({ s, parts: batches(uploadItems(s, state[s.name].dates)) }));
    const total = work.reduce((n, w) => n + w.parts.reduce((m, p) => m + p.length, 0), 0);
    setStage('uploading');
    setError('');
    setProgress({ done: 0, total, label: '' });
    const done: Uploaded[] = [];
    let sent = 0;
    try {
      for (const { s, parts } of work) {
        let sourceId = s.source?.kind === 'upload' ? s.source.id ?? '' : '';
        let created = false;
        const days = new Set<string>();
        let past = 0;
        for (const part of parts) {
          setProgress({ done: sent, total, label: s.name });
          const files = part.map((item) => {
            const file = byPath.get(pickedPathOf(plan, s.name, item.path));
            if (!file) throw new Error(`${item.path} 파일을 다시 읽지 못했어요. 폴더를 다시 골라 주세요.`);
            return file;
          });
          const result = await commitFolderUpload({ cohortId, sourceId, name: s.name, manifest: manifest(part), files });
          sourceId = result.source.id;
          created = created || result.source.created;
          for (const c of result.commits) {
            if (!c.sha) continue;
            if (c.date) days.add(c.date);
            else past += c.changed.length;
          }
          sent += part.length;
          setProgress({ done: sent, total, label: s.name });
        }
        done.push({ name: s.name, created, days: [...days].sort(), past, same: s.counts.same });
      }
      setUploaded(done);
      setStage('done');
      await refreshAfterFolderUpload();
    } catch (e) {
      // 앞 묶음은 이미 올라갔다 — 같은 파일은 서버가 건너뛰므로 다시 올리기를 눌러도 겹치지 않는다
      setUploaded(done);
      setError(await readApiError(e));
      setStage('review');
    }
  };

  if (stage === 'done') {
    return (
      <div className="fu">
        <div className="callout callout--success" role="status">
          과목 {uploaded.length}개를 올렸어요. 날짜를 고른 파일은 그 날짜 수업으로, 나머지는 날짜 없이 지난 자료로 들어갔어요.
          오늘부터는 과목의 「오늘 수업 올리기」로 그날 파일만 올리면 올린 날이 수업 날짜가 돼요.
        </div>
        <ul className="fu__done">
          {uploaded.map((u) => (
            <li key={u.name}>
              <strong>{u.name}</strong> {u.created ? <Badge tone="primary">새 과목</Badge> : <Badge>이어서 올림</Badge>}
              <span className="hint">
                {u.days.length ? `수업 ${u.days.length}일(${u.days.map(short).join(', ')})` : '날짜별 수업 없음'} · 지난 자료 {u.past}개
                {u.same ? ` · 지난번과 같아 건너뜀 ${u.same}개` : ''}
              </span>
            </li>
          ))}
        </ul>
        <Row gap={8}>
          <Button size="sm" onClick={onDone}>
            닫기
          </Button>
        </Row>
      </div>
    );
  }

  return (
    <div className="fu">
      {(stage === 'pick' || stage === 'reading') && (
        <div className="fu__pick">
          <p className="hint">
            수업 자료 폴더를 고르세요. 과목 폴더(예: python_basic) 하나도, 과목 폴더 여럿이 든 기수 폴더도 돼요. 파일은 이 브라우저에서 먼저
            읽어 날짜를 찾고, 확인한 뒤에 올려요. 데이터 · 그림 · 숨김 파일(.ipynb_checkpoints 등)은 빼요.
          </p>
          <Row gap={8}>
            <Button icon={<Icon name="folder_open" size={18} />} disabled={stage === 'reading'} onClick={() => input.current?.click()}>
              폴더 고르기
            </Button>
            {stage === 'reading' && (
              <span className="hint" role="status">
                읽는 중… {readDone}개
              </span>
            )}
          </Row>
          <input
            ref={input}
            type="file"
            multiple
            hidden
            aria-label="수업 자료 폴더"
            onChange={(e) => {
              const files = [...(e.target.files ?? [])];
              e.target.value = '';
              void pick(files);
            }}
          />
        </div>
      )}
      {error !== '' && <div className="callout callout--error">{error}</div>}

      {plan && (stage === 'review' || stage === 'uploading') && (
        <>
          <Row gap={6}>
            <Badge>과목 {plan.subjects.length}</Badge>
            <Badge>파일 {plan.subjects.reduce((n, s) => n + s.counts.files, 0)}</Badge>
            {plan.subjects.some((s) => s.counts.same) && (
              <Badge>지난번과 같아 건너뜀 {plan.subjects.reduce((n, s) => n + s.counts.same, 0)}</Badge>
            )}
            {notLesson + plan.skipped > 0 && <Badge>수업 파일이 아니라 뺀 것 {notLesson + plan.skipped}</Badge>}
          </Row>
          <div className="callout fu__what">
            <span>
              「{plan.root}」을 <b>{plan.what === 'subject' ? '과목 하나' : `여러 과목(${plan.subjects.length}개)이 든 기수 폴더`}</b>로 봤어요.
            </span>
            <Button variant="text" size="sm" disabled={stage === 'uploading'} onClick={() => void makePlan(plan.what === 'subject' ? 'cohort' : 'subject')}>
              {plan.what === 'subject' ? '여러 과목으로 보기' : '과목 하나로 보기'}
            </Button>
          </div>
          {plan.calendarWarnings.map((w, i) => (
            <div key={i} className="callout callout--warning">
              {w.text}
            </div>
          ))}
          {plan.subjects.map((s) => (
            <SubjectReview
              key={s.name}
              plan={plan}
              subject={s}
              state={state[s.name]}
              disabled={stage === 'uploading'}
              onDates={(dates) => update(s.name, (cur) => ({ ...cur, dates }))}
              onExpand={(folder) => update(s.name, (cur) => ({ ...cur, expanded: new Set([...cur.expanded, folder]) }))}
              onTopic={(topic) => {
                const next = { ...topics, [s.name]: topic };
                setTopics(next);
                void makePlan(plan.what, next);
              }}
            />
          ))}
          {stage === 'uploading' ? (
            <div className="fu__progress" role="status">
              <ProgressBar value={progress.done} max={progress.total} />
              <span className="hint">
                올리는 중 {progress.done}/{progress.total} · {progress.label} — 창을 닫지 마세요
              </span>
            </div>
          ) : (
            <Row gap={8}>
              <Button disabled={blocked.length > 0} onClick={() => void upload()}>
                확정하고 올리기
              </Button>
              <Button variant="outline" onClick={() => { setPlan(null); setPicked([]); setStage('pick'); }}>
                다시 고르기
              </Button>
              <span className="hint">{blocked[0] ?? '날짜를 고르지 않은 파일은 지난 자료로 가져와요.'}</span>
            </Row>
          )}
        </>
      )}
    </div>
  );
}

function SubjectReview({
  plan,
  subject: s,
  state,
  disabled,
  onDates,
  onExpand,
  onTopic,
}: {
  plan: ImportPlan;
  subject: PlanSubject;
  state: SubjectState | undefined;
  disabled: boolean;
  onDates(dates: DateChoice): void;
  onExpand(folder: string): void;
  onTopic(topic: string): void;
}) {
  if (!state) return null;
  const rows = reviewRows(s, state.dates, state.expanded);
  const topic = plan.topics.find((t) => t.id === s.topic);
  const estimable = s.files.some((f) => f.estimate && state.dates[f.path] == null);
  const estimated = s.files.some((f) => f.estimate && f.date == null && state.dates[f.path] === f.estimate);
  const pastCount = rows.filter((r) => r.kind === 'past' && !r.date).reduce((n, r) => n + r.files.length, 0);
  return (
    <section className="fu__subject" aria-label={s.name}>
      <div className="fu__head">
        <Icon name="folder" size={18} />
        <strong>{s.name}</strong>
        <span className="hint">파일 {s.counts.files}개</span>
        {s.source?.kind === 'upload' && <Badge>이미 올린 과목 · 바뀐 파일만 더해요</Badge>}
        {s.source?.kind === 'github' && <Badge tone="error">GitHub 과목과 이름이 같아요</Badge>}
      </div>
      <div className="fu__topic">
        <span className="hint">커리큘럼 과목</span>
        <Select
          aria-label={`${s.name} 커리큘럼 과목`}
          value={s.topic ?? ''}
          disabled={disabled || plan.topics.length === 0}
          onChange={(e) => onTopic(e.target.value)}
        >
          <option value="">{plan.topics.length ? '고르지 않음' : '커리큘럼 없음'}</option>
          {plan.topics.map((t) => (
            <option key={t.id} value={t.id}>
              {t.topic} ({short(t.first)}~{short(t.last)}, 수업 {t.count}일)
            </option>
          ))}
        </Select>
        {topic && s.topicBy !== 'picked' && <span className="hint">{s.topicBy === 'dates' ? '수업 날짜로 맞췄어요' : '이름으로 맞췄어요'} · 틀리면 바꿔 주세요</span>}
        {(estimable || estimated) && (
          <Button
            variant="outline"
            size="sm"
            disabled={disabled}
            onClick={() => onDates(estimated ? withoutEstimates(s, state.dates) : withEstimates(s, state.dates))}
          >
            {estimated ? '채운 날짜 되돌리기' : '커리큘럼으로 날짜 채우기'}
          </Button>
        )}
      </div>
      {pastCount > 0 && (
        <p className="hint fu__tip">
          날짜 단서가 없는 파일은 <b>날짜 없이 지난 자료</b>로 가져와요. 수업 파일 보기 · 폴더 노트 · 과목 요약은 바로 돼요. 날짜별 노트 · 복습
          문제가 필요하면 큰 주제마다 날짜를 고르세요(선택) — 며칠에 걸친 폴더는 펼쳐서 나눠요.
        </p>
      )}
      <ul className="fu__rows">
        {rows.map((row) => (
          <RowLine key={row.key} row={row} plan={plan} disabled={disabled} onDate={(d) => onDates(setRowDate(state.dates, row, d))} onExpand={onExpand} />
        ))}
      </ul>
    </section>
  );
}

function RowLine({
  row,
  plan,
  disabled,
  onDate,
  onExpand,
}: {
  row: ReviewRow;
  plan: ImportPlan;
  disabled: boolean;
  onDate(date: string): void;
  onExpand(folder: string): void;
}) {
  const notice = dayNotice(row.date, plan.calendar);
  const past = row.kind === 'past';
  const where = past ? (row.folder ? `${row.depth === 1 ? '큰 주제' : '안쪽 폴더'} ${row.folder}` : `파일 ${row.files[0].path}`) : '';
  const state = past
    ? row.mixed ? '날짜가 섞였어요' : row.estimated ? '커리큘럼 추정 · 확인' : row.date ? '직접 고름' : '날짜 없음 · 지난 자료'
    : BASIS_LABEL[row.basis];
  const tone = notice || row.estimated || row.basis === 'time' ? ' fu__row--check' : past && !row.date ? ' fu__row--past' : '';
  return (
    <li className={`fu__row${tone}`}>
      <input
        type="date"
        className="input fu__date"
        value={row.date}
        min={plan.calendar.start}
        max={plan.calendar.today}
        disabled={disabled}
        aria-label={`${where || row.files[0].path} 수업 날짜`}
        onChange={(e) => onDate(e.target.value)}
      />
      <span className="fu__badges">
        <span className="fu__basis">{[where, state].filter(Boolean).join(' · ')}</span>
        {notice && <span className="fu__notice">{notice}</span>}
      </span>
      <span className="fu__files hint">
        <b>{row.files.length}개</b> · {row.files.slice(0, 3).map((f) => f.path).join(' · ')}
        {row.files.length > 3 ? ' …' : ''}
        {past && row.folder && row.files.length > 1 && (
          <button type="button" className="fu__more" disabled={disabled} onClick={() => onExpand(row.folder!)}>
            펼치기 — {row.inner > 1 ? `안쪽 ${row.inner}개` : '파일마다'}
          </button>
        )}
      </span>
    </li>
  );
}
