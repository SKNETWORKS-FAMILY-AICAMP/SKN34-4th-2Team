import type { PracticeProblem, PracticeSet } from '../../domain/types';
import type { Cell } from './notebookModel';
import { KIND_LABEL } from './practiceLabels';
import type { TableData } from './pythonProtocol';

/**
 * 연습장 ↔ 파일 — Jupyter .ipynb(nbformat 4)와 셀 구분 주석이 달린 .py(`# %%`, VS Code · Jupytext 형식).
 *
 * 내보내기: 코드·마크다운 셀은 그대로, 문제 셀은 「문제 설명 마크다운 + 내가 쓴 코드」 두 칸으로 푼다.
 *           숨긴 테스트·모범답안은 내보내지 않는다. .ipynb 에는 지금 화면의 출력(글·값·표·그림)도 담는다.
 * 불러오기: 코드·마크다운 셀만 받는다. 출력은 버린다 — 다시 실행하면 나온다.
 *           브라우저에서 못 도는 줄(`!pip`, `%matplotlib`)은 주석으로 바꿔 둔다.
 *
 * 화면·실행기에는 기대지 않는 순수 함수만 둔다.
 */

export interface ImportedCell {
  type: 'code' | 'markdown';
  source: string;
}

export interface ImportedNotebook {
  cells: ImportedCell[];
  /** 불러오면서 손댄 것 — 주석 처리한 줄 수 등. 사용자에게 한 줄로 알린다 */
  notes: string[];
}

/** 이보다 큰 파일은 받지 않는다 — 출력 그림이 잔뜩 박힌 노트북은 수십 MB 가 된다 */
export const MAX_IMPORT_BYTES = 8 * 1024 * 1024;
export const MAX_IMPORT_CELLS = 400;

// ── 내보내기 ─────────────────────────────────────────────

/** 문제 셀 하나를 파일에 적을 두 칸으로 */
function problemParts(problem: PracticeProblem, number: number, code: string): ImportedCell[] {
  const head = `### 문제 ${number} · ${KIND_LABEL[problem.kind]} · ${problem.topic}\n\n${problem.prompt.trim()}`;
  if (problem.kind === 'concept') {
    const choices = problem.choices.map((c, i) => `- ${'ABCD'[i]}. ${c}`).join('\n');
    return [{ type: 'markdown', source: `${head}\n\n${choices}` }];
  }
  if (problem.kind === 'code_output') {
    return [
      { type: 'markdown', source: `${head}\n\n출력을 예상해 본 뒤 아래 셀을 실행해 확인하세요.` },
      { type: 'code', source: problem.starterCode },
    ];
  }
  return [
    { type: 'markdown', source: head },
    { type: 'code', source: code },
  ];
}

/** 셀들을 파일에 적을 순서대로 편다. 문제 셀은 세트가 있어야 설명을 붙일 수 있다 */
export function flattenCells(cells: Cell[], set: PracticeSet | undefined): { cell: ImportedCell; from: Cell | null }[] {
  const out: { cell: ImportedCell; from: Cell | null }[] = [];
  for (const c of cells) {
    if (c.type === 'problem') {
      const problem = c.problemIndex != null ? set?.problems[c.problemIndex] : undefined;
      if (!problem) continue;
      const parts = problemParts(problem, (c.problemIndex ?? 0) + 1, c.code);
      // 출력은 코드 칸에만 붙인다 — 문제 셀은 따로 출력을 들고 있지 않다
      for (const p of parts) out.push({ cell: p, from: null });
      continue;
    }
    out.push({ cell: { type: c.type === 'markdown' ? 'markdown' : 'code', source: c.code }, from: c });
  }
  return out;
}

/** Jupyter 는 source 를 줄 배열로 둔다. 마지막 줄만 \n 이 없다 */
function sourceLines(text: string): string[] {
  if (text === '') return [];
  const lines = text.split('\n');
  return lines.map((l, i) => (i < lines.length - 1 ? `${l}\n` : l)).filter((l, i, all) => !(i === all.length - 1 && l === ''));
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function tableHtml(t: TableData): string {
  const head = `<tr><th>${escapeHtml(t.indexName)}</th>${t.columns.map((c) => `<th>${escapeHtml(c)}</th>`).join('')}</tr>`;
  const body = t.rows.map((r, i) => `<tr><th>${escapeHtml(t.index[i] ?? '')}</th>${r.map((v) => `<td>${escapeHtml(v)}</td>`).join('')}</tr>`).join('');
  return `<table class="dataframe"><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

function tableText(t: TableData): string {
  const rows = [[t.indexName, ...t.columns], ...t.rows.map((r, i) => [t.index[i] ?? '', ...r])];
  return rows.map((r) => r.join('  ')).join('\n');
}

type Output = Record<string, unknown>;

function outputsOf(c: Cell): Output[] {
  const outs: Output[] = [];
  const stdout = c.lines.filter((l) => l.kind === 'out').map((l) => l.text).join('\n');
  const stderr = c.lines.filter((l) => l.kind === 'err').map((l) => l.text).join('\n');
  if (stdout) outs.push({ output_type: 'stream', name: 'stdout', text: sourceLines(`${stdout}\n`) });
  if (stderr) outs.push({ output_type: 'stream', name: 'stderr', text: sourceLines(`${stderr}\n`) });
  for (const img of c.images) {
    const b64 = img.replace(/^data:image\/png;base64,/, '');
    outs.push({ output_type: 'display_data', data: { 'image/png': b64, 'text/plain': ['<Figure>'] }, metadata: {} });
  }
  if (c.table) {
    outs.push({
      output_type: 'execute_result',
      execution_count: c.count,
      data: { 'text/html': [tableHtml(c.table)], 'text/plain': sourceLines(tableText(c.table)) },
      metadata: {},
    });
  } else if (c.value !== null) {
    outs.push({ output_type: 'execute_result', execution_count: c.count, data: { 'text/plain': sourceLines(c.value) }, metadata: {} });
  }
  return outs;
}

export function toIpynb(cells: Cell[], set: PracticeSet | undefined): string {
  const flat = flattenCells(cells, set);
  const nb = {
    nbformat: 4,
    nbformat_minor: 5,
    metadata: {
      kernelspec: { name: 'python3', display_name: 'Python 3', language: 'python' },
      language_info: { name: 'python' },
      playdata: set ? { set: set.id, lessonDate: set.lessonDate, title: set.title } : {},
    },
    cells: flat.map(({ cell, from }, i) =>
      cell.type === 'markdown'
        ? { cell_type: 'markdown', id: `cell-${i + 1}`, metadata: {}, source: sourceLines(cell.source) }
        : {
            cell_type: 'code',
            id: `cell-${i + 1}`,
            metadata: {},
            execution_count: from?.count ?? null,
            source: sourceLines(cell.source),
            outputs: from ? outputsOf(from) : [],
          },
    ),
  };
  return `${JSON.stringify(nb, null, 1)}\n`;
}

/** `# %%` 로 셀을 가른 .py — VS Code · PyCharm · Jupytext 가 셀로 읽는다 */
export function toPy(cells: Cell[], set: PracticeSet | undefined): string {
  const flat = flattenCells(cells, set);
  const blocks = flat.map(({ cell }) => {
    if (cell.type === 'markdown') {
      const body = cell.source.split('\n').map((l) => (l ? `# ${l}` : '#')).join('\n');
      return `# %% [markdown]\n${body}`;
    }
    return `# %%\n${cell.source.replace(/\n+$/, '')}`;
  });
  return `${blocks.join('\n\n')}\n`;
}

/** 내려받을 파일 이름 — 세트면 날짜를 붙인다 */
export function exportFileName(set: PracticeSet | undefined, ext: 'ipynb' | 'py'): string {
  if (!set) return `python-playground.${ext}`;
  if (set.id === 'retry') return `retry-problems.${ext}`;
  return `review-${set.lessonDate}.${ext}`;
}

// ── 불러오기 ─────────────────────────────────────────────

/** 브라우저에서 못 도는 줄 — 셸 명령(!pip)과 IPython 매직(%matplotlib, %%time) */
const MAGIC = /^(\s*)([!%].*)$/;

function softenMagics(source: string): { source: string; changed: number } {
  let changed = 0;
  const lines = source.split('\n').map((line) => {
    const m = MAGIC.exec(line);
    if (!m) return line;
    changed += 1;
    return `${m[1]}# (연습장에서는 못 씀) ${m[2]}`;
  });
  return { source: lines.join('\n'), changed };
}

function joinSource(src: unknown): string {
  if (Array.isArray(src)) return src.map(String).join('');
  return typeof src === 'string' ? src : '';
}

export class NotebookFileError extends Error {}

export function parseIpynb(text: string): ImportedNotebook {
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    throw new NotebookFileError('노트북 파일(JSON)을 읽지 못했어요. 파일이 깨졌을 수 있어요.');
  }
  const nb = data as { nbformat?: number; cells?: unknown; worksheets?: unknown };
  if (!nb || typeof nb !== 'object') throw new NotebookFileError('노트북 파일이 아니에요.');
  if (nb.worksheets !== undefined || (nb.nbformat !== undefined && nb.nbformat < 4)) {
    throw new NotebookFileError('아주 옛날 형식(nbformat 3)이에요. Jupyter 에서 한 번 열어 저장한 뒤 올려 주세요.');
  }
  if (!Array.isArray(nb.cells)) throw new NotebookFileError('셀이 없는 노트북이에요.');

  const cells: ImportedCell[] = [];
  let magics = 0;
  let raws = 0;
  for (const raw of nb.cells as { cell_type?: string; source?: unknown }[]) {
    const source = joinSource(raw?.source);
    if (raw?.cell_type === 'markdown') cells.push({ type: 'markdown', source });
    else if (raw?.cell_type === 'code') {
      const soft = softenMagics(source);
      magics += soft.changed;
      cells.push({ type: 'code', source: soft.source });
    } else if (raw?.cell_type === 'raw') {
      raws += 1;
      cells.push({ type: 'markdown', source: '```\n' + source + '\n```' });
    }
  }
  return finish(cells, magics, raws);
}

/** .py — `# %%` 가 있으면 셀로 가르고, 없으면 통째로 한 셀 */
export function parsePy(text: string): ImportedNotebook {
  const src = text.replace(/\r\n?/g, '\n');
  const marker = /^# ?%%(.*)$/;
  const lines = src.split('\n');
  if (!lines.some((l) => marker.test(l))) {
    const soft = softenMagics(src.replace(/\n+$/, ''));
    return finish(soft.source.trim() ? [{ type: 'code', source: soft.source }] : [], soft.changed, 0);
  }

  const cells: ImportedCell[] = [];
  let magics = 0;
  let current: { type: 'code' | 'markdown'; lines: string[] } | null = null;
  const flush = () => {
    if (!current) return;
    const body = current.lines.join('\n').replace(/^\n+|\n+$/g, '');
    if (current.type === 'markdown') {
      cells.push({ type: 'markdown', source: body.split('\n').map((l) => l.replace(/^# ?/, '')).join('\n') });
    } else if (body.trim()) {
      const soft = softenMagics(body);
      magics += soft.changed;
      cells.push({ type: 'code', source: soft.source });
    }
  };
  for (const line of lines) {
    const m = marker.exec(line);
    if (m) {
      flush();
      current = { type: /\[markdown\]|\[md\]/i.test(m[1]) ? 'markdown' : 'code', lines: [] };
    } else {
      // 첫 표시 앞의 줄(주석·import)도 코드 셀 하나로 받는다
      if (!current) current = { type: 'code', lines: [] };
      current.lines.push(line);
    }
  }
  flush();
  return finish(cells, magics, 0);
}

function finish(cells: ImportedCell[], magics: number, raws: number): ImportedNotebook {
  if (cells.length === 0) throw new NotebookFileError('불러올 셀이 없어요.');
  if (cells.length > MAX_IMPORT_CELLS) throw new NotebookFileError(`셀이 너무 많아요(${cells.length}개). ${MAX_IMPORT_CELLS}개까지 받아요.`);
  const notes: string[] = [];
  if (magics) notes.push(`브라우저에서 못 도는 줄(!pip · %매직) ${magics}개를 주석으로 바꿨어요`);
  if (raws) notes.push(`raw 셀 ${raws}개는 글 칸으로 넣었어요`);
  return { cells, notes };
}

/** 파일 이름으로 형식을 고른다 */
export function parseNotebookFile(name: string, text: string): ImportedNotebook {
  const lower = name.toLowerCase();
  if (lower.endsWith('.ipynb')) return parseIpynb(text);
  if (lower.endsWith('.py')) return parsePy(text);
  throw new NotebookFileError('.ipynb 나 .py 파일만 불러올 수 있어요.');
}
