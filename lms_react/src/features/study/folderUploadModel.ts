/**
 * 폴더 올리기 확인 화면의 계산 — 서버 계획(study_notes/upload_plan.py plan_import)을 받아
 * 줄로 묶고(날짜별 · 지난 자료는 큰 주제 폴더별), 강사가 고친 날짜를 반영하고, 올릴 묶음(100개씩)을 만든다.
 * 화면(FolderImport.tsx)은 이 결과를 그리기만 한다.
 *
 * 첫 버전은 「두 날에 걸친 파일」을 나누지 않는다 — 고른 한 날짜(기본 첫 날짜)로 통째로 넣는다.
 */

export type Basis = 'name' | 'content' | 'round' | 'time' | 'pick' | 'split';
export type FileStatus = 'new' | 'update' | 'same';

export interface PlanFile {
  path: string;
  blob: string;
  size: number;
  basis: Basis;
  date: string | null;
  round?: number;
  dates?: string[];
  estimate?: string;
  status: FileStatus;
  /** 노트북 셀마다 첫 줄 — 나누는 지점을 고를 때 보인다 */
  cells?: string[];
  /** 두 날에 걸친 파일 — 날짜 근거와 둘째 날부터 시작하는 셀(노트북이 아니면 null: 한 날짜로만) */
  from?: 'name' | 'content';
  cutCells?: number[] | null;
}

/** 두 날에 걸친 파일을 어떻게 넣나 — 나눠 넣기(날짜마다 앞 셀들) · 한 날짜로(통째로) */
export interface SplitChoice {
  mode: 'split' | 'single';
  dates: string[];
  /** cuts[k] = dates[k + 1] 이 시작하는 셀 번호 */
  cuts: number[];
  /** 강사가 「두 날에 나누기」로 직접 나눈 노트북 */
  manual?: boolean;
}

export type SplitState = Record<string, SplitChoice>;

/** 셀로 나눌 수 있나 — 셀이 둘 이상인 노트북 */
export function canSplit(f: PlanFile): boolean {
  return f.path.toLowerCase().endsWith('.ipynb') && (f.cells?.length ?? 0) >= 2;
}

/** 서버가 찾은 두 날 파일 — 셀로 나눌 수 있으면 나눠 넣기가 기본, 아니면 첫 날짜로 통째로 */
export function initialSplits(subject: PlanSubject): SplitState {
  const out: SplitState = {};
  for (const f of subject.files) {
    if (f.basis !== 'split' || !f.dates?.length || f.status === 'same') continue;
    out[f.path] = f.cutCells?.length
      ? { mode: 'split', dates: [...f.dates], cuts: [...f.cutCells] }
      : { mode: 'single', dates: [...f.dates], cuts: [] };
  }
  return out;
}

/** 「두 날에 나누기(셀로)」 — 첫날은 지금 날짜, 둘째 날은 비워 두고 가운데 셀에서 나눈다 */
export function manualSplit(f: PlanFile, firstDate: string): SplitChoice {
  return { mode: 'split', dates: [firstDate, ''], cuts: [Math.max(1, Math.floor((f.cells?.length ?? 2) / 2))], manual: true };
}

/** 나누기가 올릴 수 있는 상태인가 — 날짜가 다 있고 앞에서 뒤로, 셀도 앞에서 뒤로 */
export function splitProblem(choice: SplitChoice, cal: PlanCalendar, cellCount: number): string {
  if (choice.mode === 'single') return '';
  if (choice.dates.some((d) => !d)) return '두 날에 나눈 파일의 날짜를 골라 주세요.';
  if (choice.dates.some((d, i) => i > 0 && d <= choice.dates[i - 1])) return '두 날에 나눈 파일은 앞 날짜가 먼저여야 해요.';
  if (choice.dates.some((d) => d > cal.today)) return '앞으로 올 날짜가 있어요.';
  if (choice.cuts.some((c, i) => c <= 0 || c >= cellCount || (i > 0 && c <= choice.cuts[i - 1]))) return '나누는 셀을 앞에서 뒤로 골라 주세요.';
  return '';
}

export interface PlanWarning {
  kind: string;
  date?: string;
  text: string;
}

export interface PlanSubject {
  name: string;
  source: { id: string | null; kind: 'upload' | 'github' | null } | null;
  topic: string | null;
  topicBy: 'dates' | 'name' | 'picked' | null;
  start: string;
  classDays: string[];
  files: PlanFile[];
  counts: { files: number; same: number; dated: number; past: number; estimated: number };
  warnings: PlanWarning[];
}

export interface PlanTopic {
  id: string;
  topic: string;
  unit: string;
  first: string;
  last: string;
  count: number;
}

export interface PlanCalendar {
  today: string;
  start: string;
  end: string;
  holidays: Record<string, string>;
  classDays: string[];
  extraDays: string[];
}

export interface ImportPlan {
  what: 'subject' | 'cohort';
  root: string;
  skipped: number;
  subjects: PlanSubject[];
  topics: PlanTopic[];
  calendarWarnings: PlanWarning[];
  calendar: PlanCalendar;
}

/** 파일마다 지금 고른 수업 날짜(null = 날짜 없이 지난 자료) */
export type DateChoice = Record<string, string | null>;

export const MAX_BATCH_FILES = 100;
export const MAX_BATCH_BYTES = 20 * 1024 * 1024;

const natural = new Intl.Collator('ko', { numeric: true });

export function initialDates(subject: PlanSubject): DateChoice {
  const out: DateChoice = {};
  for (const f of subject.files) out[f.path] = f.date ?? (f.basis === 'split' && f.dates?.length ? f.dates[0] : null);
  return out;
}

/** 「커리큘럼으로 날짜 채우기」 — 날짜 없는 파일에 추정 날짜. 이미 고른 날짜는 그대로 */
export function withEstimates(subject: PlanSubject, dates: DateChoice): DateChoice {
  const out = { ...dates };
  for (const f of subject.files) if (out[f.path] == null && f.estimate) out[f.path] = f.estimate;
  return out;
}

/** 추정을 되돌린다 — 추정 날짜 그대로인 파일만 지난 자료로 */
export function withoutEstimates(subject: PlanSubject, dates: DateChoice): DateChoice {
  const out = { ...dates };
  for (const f of subject.files) if (f.estimate && out[f.path] === f.estimate && f.date == null) out[f.path] = null;
  return out;
}

/** 서버가 날짜를 찾은 파일인가(이름 · 회차 · 파일 안 · 수정 시각 · 두 날) — 아니면 지난 자료 줄로 묶는다 */
function foundDate(f: PlanFile): boolean {
  return f.date != null || f.basis === 'split';
}

export interface ReviewRow {
  key: string;
  kind: 'date' | 'past';
  /** 줄의 날짜 — 지난 자료 줄은 파일들이 같은 날짜일 때만, 아니면 '' */
  date: string;
  /** 지난 자료 줄의 폴더(큰 주제 → 안쪽), 파일 하나면 null */
  folder: string | null;
  depth: number;
  files: PlanFile[];
  basis: Basis;
  mixed: boolean;
  estimated: boolean;
  /** 펼치면 생기는 안쪽 칸 수 */
  inner: number;
  /** 두 날에 나눈 파일의 그날 몫 — 날짜는 「두 날에 걸친 파일」 칸에서 고친다 */
  part?: boolean;
}

/** 지난 자료를 묶을 칸 — 펼치지 않은 가장 바깥 폴더(큰 주제 → 안쪽 폴더 → 파일) */
function pastKey(path: string, expanded: Set<string>): { folder: string | null; depth: number } {
  const parts = path.split('/');
  for (let i = 1; i < parts.length; i += 1) {
    const folder = parts.slice(0, i).join('/');
    if (!expanded.has(folder)) return { folder, depth: i };
  }
  return { folder: null, depth: parts.length };
}

export function reviewRows(subject: PlanSubject, dates: DateChoice, expanded: Set<string>, splits: SplitState = {}): ReviewRow[] {
  const rows = new Map<string, ReviewRow>();
  for (const f of subject.files) {
    if (f.status === 'same') continue;
    const split = splits[f.path];
    if (split?.mode === 'split') {
      // 나눠 넣는 파일 — 날짜마다 그 날 몫으로(날짜는 아래 「두 날에 걸친 파일」에서 고친다)
      for (const day of split.dates) {
        const key = `d|${day}|part`;
        const row = rows.get(key) ?? { key, kind: 'date' as const, date: day, folder: null, depth: 0, basis: 'split' as const, part: true, files: [], mixed: false, estimated: false, inner: 0 };
        row.files.push(f);
        rows.set(key, row);
      }
      continue;
    }
    const date = dates[f.path] ?? null;
    let key: string;
    let base: Omit<ReviewRow, 'files' | 'mixed' | 'estimated' | 'inner'>;
    if (foundDate(f)) {
      key = `d|${date ?? ''}|${f.basis}`;
      base = { key, kind: 'date', date: date ?? '', folder: null, depth: 0, basis: f.basis };
    } else {
      const { folder, depth } = pastKey(f.path, expanded);
      key = `p|${folder ?? f.path}`;
      base = { key, kind: 'past', date: '', folder, depth, basis: f.basis };
    }
    const row = rows.get(key) ?? { ...base, files: [], mixed: false, estimated: false, inner: 0 };
    row.files.push(f);
    rows.set(key, row);
  }
  for (const row of rows.values()) {
    if (row.kind === 'past') {
      const picked = new Set(row.files.map((f) => dates[f.path] ?? ''));
      row.date = picked.size === 1 ? [...picked][0] : '';
      row.mixed = picked.size > 1;
      row.estimated = row.date !== '' && row.files.every((f) => f.estimate === dates[f.path]);
      row.inner = row.folder ? new Set(row.files.map((f) => f.path.slice(row.folder!.length + 1).split('/')[0])).size : 0;
    }
  }
  const order = (r: ReviewRow) => (r.kind === 'date' ? `0|${r.date || '9999'}` : `1|${r.folder ?? r.files[0].path}`);
  return [...rows.values()].sort((a, b) => natural.compare(order(a), order(b)));
}

/** 줄의 날짜를 바꾼다 — 그 줄 파일 모두. ''면 날짜 없이(지난 자료) */
export function setRowDate(dates: DateChoice, row: ReviewRow, date: string): DateChoice {
  const out = { ...dates };
  for (const f of row.files) out[f.path] = date || null;
  return out;
}

const WEEKEND = ['일요일', '', '', '', '', '', '토요일'];

/** 고른 날짜가 수업 없는 날이면 묻는 말 — 막지 않는다(공휴일 표 · 커리큘럼도 틀릴 수 있다) */
export function dayNotice(date: string, cal: PlanCalendar): string {
  if (!date) return '';
  if (date > cal.today) return '앞으로 올 날짜로는 올릴 수 없어요.';
  if (cal.extraDays.includes(date)) return '';
  const holiday = cal.holidays[date];
  if (holiday) return `${holiday} — 수업한 날이 맞나요?`;
  const weekend = WEEKEND[new Date(`${date}T12:00:00`).getDay()];
  if (weekend) return `${weekend} — 수업한 날이 맞나요?`;
  if (cal.classDays.length && !cal.classDays.includes(date)) return '커리큘럼엔 수업이 없는 날이에요. 보강이었나요?';
  return '';
}

/** 올릴 파일 하나 — 과목 안 경로 · 날짜(null = 지난 자료) · 크기. upto 가 있으면 노트북의 앞 셀 upto 개만(두 날 나누기) */
export interface UploadItem {
  path: string;
  date: string | null;
  size: number;
  upto?: number;
}

/** 올릴 것 — 지난번과 같은 파일은 빼고. 지난 자료 먼저, 그다음 날짜 순(서버도 그 순서로 커밋한다).
 *  나눠 넣는 노트북은 날짜마다 한 번씩 — 앞 날짜엔 그날까지의 셀만, 마지막 날짜엔 전체. 그래서 노트 · 출제가
 *  날마다 「새로 생긴 셀」만 그날 수업으로 본다(이어 쓴 노트북을 매일 올린 것과 같다). */
export function uploadItems(subject: PlanSubject, dates: DateChoice, splits: SplitState = {}): UploadItem[] {
  const items: UploadItem[] = [];
  for (const f of subject.files) {
    if (f.status === 'same') continue;
    const split = splits[f.path];
    if (split?.mode === 'split') {
      split.dates.forEach((day, k) => {
        const last = k === split.dates.length - 1;
        items.push({ path: f.path, date: day, size: f.size, ...(last ? {} : { upto: split.cuts[k] }) });
      });
      continue;
    }
    items.push({ path: f.path, date: dates[f.path] ?? null, size: f.size });
  }
  return items.sort((a, b) => (a.date ?? '').localeCompare(b.date ?? '') || natural.compare(a.path, b.path));
}

/** 한 번에 보낼 묶음 — 100개(Django 가 받는 파일 수) · 20MB 까지. 순서를 지킨다 */
export function batches(items: UploadItem[], maxFiles = MAX_BATCH_FILES, maxBytes = MAX_BATCH_BYTES): UploadItem[][] {
  const out: UploadItem[][] = [];
  let cur: UploadItem[] = [];
  let bytes = 0;
  for (const item of items) {
    if (cur.length && (cur.length >= maxFiles || bytes + item.size > maxBytes)) {
      out.push(cur);
      cur = [];
      bytes = 0;
    }
    cur.push(item);
    bytes += item.size;
  }
  if (cur.length) out.push(cur);
  return out;
}

/** 서버 /study-sources/upload/commit 의 manifest — 번호는 이 묶음에서 보내는 파일 순서 */
export function manifest(batch: UploadItem[]): { paths: string[]; days: { date: string; files: number[] }[]; past: number[] } {
  const days = new Map<string, number[]>();
  const past: number[] = [];
  batch.forEach((item, i) => {
    if (item.date) days.set(item.date, [...(days.get(item.date) ?? []), i]);
    else past.push(i);
  });
  return { paths: batch.map((i) => i.path), days: [...days].map(([date, files]) => ({ date, files })), past };
}

/** 과목 안 경로 → 고른 파일의 경로(맨 위 폴더 · 과목 폴더 붙임) */
export function pickedPathOf(plan: Pick<ImportPlan, 'what' | 'root'>, subject: string, rest: string): string {
  return plan.what === 'subject' ? `${plan.root}/${rest}` : `${plan.root}/${subject}/${rest}`;
}

/** 이 과목을 올릴 수 있나 — GitHub 과목과 이름이 같으면 서버가 막는다(폴더 이름을 바꿔 다시) */
export function blockedReason(subject: PlanSubject, dates: DateChoice, cal: PlanCalendar, splits: SplitState = {}): string {
  if (subject.source?.kind === 'github') return 'GitHub로 연결된 과목과 이름이 같아요. 폴더 이름을 바꿔 다시 골라 주세요.';
  if (Object.values(dates).some((d) => d && d > cal.today)) return '앞으로 올 날짜가 있어요.';
  for (const f of subject.files) {
    const split = splits[f.path];
    const problem = split ? splitProblem(split, cal, f.cells?.length ?? 0) : '';
    if (problem) return `${f.path}: ${problem}`;
  }
  return '';
}

// ── 오늘 수업 올리기(4-3에서 쓴다) — 서버 plan_daily ──

export interface DailyFile {
  path: string;
  blob: string;
  size: number;
  status: 'same' | 'update' | 'pick' | 'new';
  target?: string;
  options?: string[];
  folder?: string;
  why?: string;
}

export interface DailyPlan {
  date: string;
  files: DailyFile[];
  folders: string[];
  warnings: PlanWarning[];
  counts: { files: number; same: number; pick: number };
  topic: string | null;
  topics: PlanTopic[];
}

/** 강사가 고친 것 — 같은 이름이 여럿일 때 어느 파일인지(target, '__new' 면 새 파일), 새 파일 넣을 폴더 */
export interface DailyChoice {
  target?: string;
  folder?: string;
}

export const NEW_FILE = '__new';

/** 그 파일이 저장소 어디로 가나 — null 이면 올리지 않는다(지난번과 같음 · 아직 못 고름) */
export function dailyFinalPath(f: DailyFile, choice: DailyChoice | undefined): string | null {
  if (f.status === 'same') return null;
  if (f.status === 'update') return f.target ?? f.path;
  const picked = choice?.target ?? '';
  if (f.status === 'pick' && picked && picked !== NEW_FILE) return picked;
  if (f.status === 'pick' && !picked) return null;
  // 새 파일 — 고른(또는 추천) 폴더 아래에 파일 이름으로
  const folder = (choice?.folder ?? f.folder ?? '').replace(/\/+$/, '');
  const base = f.path.split('/').pop() ?? f.path;
  return folder ? `${folder}/${base}` : base;
}

/** 아직 고르지 않은 줄(같은 이름이 여럿인데 어느 파일인지 안 고름) */
export function dailyPending(files: DailyFile[], choices: Record<string, DailyChoice>): number {
  return files.filter((f) => f.status === 'pick' && !choices[f.path]?.target).length;
}

/** 오늘 수업 올리기에서 올릴 것 — {올릴 파일 경로(고른 경로), 저장소 안 경로}. 같은 곳에 둘이 가면 뒤엣것은 뺀다 */
export function dailyUploads(files: DailyFile[], choices: Record<string, DailyChoice>): { from: string; to: string; size: number }[] {
  const seen = new Set<string>();
  const out: { from: string; to: string; size: number }[] = [];
  for (const f of files) {
    const to = dailyFinalPath(f, choices[f.path]);
    if (!to || seen.has(to)) continue;
    seen.add(to);
    out.push({ from: f.path, to, size: f.size });
  }
  return out;
}

/** 새 파일을 넣을 수 있는 폴더 — 저장소의 폴더 + 그날 날짜 폴더 */
export function dailyFolders(plan: Pick<DailyPlan, 'folders' | 'date'>): string[] {
  return [...plan.folders, `${plan.date}/`];
}

/** 폴더째 골랐으면 맨 위(고른 폴더 이름)를 뗀다 — 그 안의 구조가 저장소 안 경로 */
export function dailyPickedPath(path: string, fromFolder: boolean): string {
  return fromFolder && path.includes('/') ? path.slice(path.indexOf('/') + 1) : path;
}
