import { Icon } from '../../ui/Icon';
import { CodeEditor } from './CodeEditor';
import type { Cell, CellType } from './notebookModel';
import { NotebookMarkdown } from './NotebookMarkdown';
import { ProblemCell } from './ProblemCell';
import type { TableData } from './pythonProtocol';
import type { Notebook } from './useNotebook';
import type { PracticeSetMode } from './usePracticeSetMode';

/** 노트북의 셀 한 칸 — 종류에 따라 코드·마크다운 셀 또는 문제 셀을 그린다. */
export function NotebookCellView({
  cell,
  index,
  total,
  nb,
  mode,
}: {
  cell: Cell;
  index: number;
  total: number;
  nb: Notebook;
  mode: PracticeSetMode;
}) {
  if (cell.type === 'problem') return <ProblemCellRow cell={cell} nb={nb} mode={mode} />;
  return <CodeOrMarkdownCell cell={cell} index={index} total={total} nb={nb} />;
}

/** 복습 세트의 문제 셀 — 풀이는 ProblemCell 이, 실행·채점은 노트북의 대기열이 맡는다. */
function ProblemCellRow({ cell, nb, mode }: { cell: Cell; nb: Notebook; mode: PracticeSetMode }) {
  const index = cell.problemIndex ?? 0;
  const problem = mode.set?.problems[index];
  if (!problem) return null;
  const number = index + 1;
  return (
    <article
      className={`py-nb-cell py-nb-cell--problem${cell.id === nb.activeId ? ' py-nb-cell--active' : ''}`}
      onClick={() => nb.setActiveId(cell.id)}
    >
      <div className="py-nb-cell__prompt" aria-label={`문제 ${number}`}>
        Q{number}
      </div>
      <div className="py-nb-cell__main">
        <ProblemCell
          problem={problem}
          number={number}
          code={cell.code}
          attempt={mode.attemptOf(index)}
          note={mode.noteOf(index)}
          onCodeChange={(code) => nb.patch(cell.id, { code })}
          onAttempt={(passed) => mode.record(index, passed)}
          runInSession={nb.runProblemInSession}
          grade={nb.gradeProblem}
          onFocus={() => nb.setActiveId(cell.id)}
          focusSignal={nb.focusSignalOf(cell.id)}
          onRunAndNext={() => nb.focusNext(cell.id)}
        />
        <div className="pb__below">
          <button
            type="button"
            className="py-icon-btn"
            onClick={() => nb.addCellAfter(cell.id)}
            aria-label="아래에 셀 추가"
            title="아래에 시험해 볼 셀 추가"
          >
            <Icon name="add" size={16} />
          </button>
        </div>
      </div>
    </article>
  );
}

/** 코드 셀과 마크다운 셀. 마크다운은 Shift+Enter 로 보기, 두 번 눌러 편집. */
function CodeOrMarkdownCell({ cell, index, total, nb }: { cell: Cell; index: number; total: number; nb: Notebook }) {
  const isMarkdown = cell.type === 'markdown';
  const rendered = isMarkdown && !cell.editing;
  return (
    <article
      className={`py-nb-cell py-nb-cell--${cell.type} py-nb-cell--${cell.state}${cell.id === nb.activeId ? ' py-nb-cell--active' : ''}`}
      onClick={() => nb.setActiveId(cell.id)}
    >
      <div className="py-nb-cell__prompt" aria-label={isMarkdown ? undefined : '실행 번호'}>
        {isMarkdown ? '' : `[${cell.state === 'running' || cell.state === 'queued' ? '*' : cell.count ?? ' '}]`}
      </div>
      <div className="py-nb-cell__main">
        <div className="py-nb-cell__tools">
          <button
            type="button"
            className="py-icon-btn py-icon-btn--run"
            onClick={() => nb.enqueue(cell.id)}
            aria-label={isMarkdown ? '마크다운 보기' : '이 셀 실행'}
            title={isMarkdown ? '보기 (Shift+Enter)' : '이 셀 실행 (Ctrl+Enter)'}
          >
            <Icon name={isMarkdown ? 'visibility' : 'play_arrow'} size={18} />
          </button>
          <select
            className="py-nb-cell__type"
            value={cell.type}
            onChange={(e) => nb.changeType(cell.id, e.target.value as CellType)}
            aria-label="셀 종류"
          >
            <option value="code">코드</option>
            <option value="markdown">마크다운</option>
          </select>
          <span className="py-grow" />
          {cell.ms !== null && cell.ms >= 10 && <span className="py-nb-cell__ms">{(cell.ms / 1000).toFixed(2)}초</span>}
          {rendered && (
            <button type="button" className="py-icon-btn" onClick={() => nb.editMarkdown(cell.id)} aria-label="편집" title="편집">
              <Icon name="edit" size={16} />
            </button>
          )}
          <button type="button" className="py-icon-btn" onClick={() => nb.move(cell.id, -1)} disabled={index === 0} aria-label="위로" title="위로">
            <Icon name="arrow_upward" size={16} />
          </button>
          <button type="button" className="py-icon-btn" onClick={() => nb.move(cell.id, 1)} disabled={index === total - 1} aria-label="아래로" title="아래로">
            <Icon name="arrow_downward" size={16} />
          </button>
          <button type="button" className="py-icon-btn" onClick={() => nb.addCellAfter(cell.id)} aria-label="아래에 셀 추가" title="아래에 셀 추가">
            <Icon name="add" size={16} />
          </button>
          <button type="button" className="py-icon-btn" onClick={() => nb.remove(cell.id)} aria-label="셀 삭제" title="셀 삭제">
            <Icon name="delete" size={16} />
          </button>
        </div>

        {rendered ? (
          <div className="py-nb-md" onDoubleClick={() => nb.editMarkdown(cell.id)} title="두 번 눌러 편집">
            {cell.code.trim() ? (
              <NotebookMarkdown source={cell.code} />
            ) : (
              <span className="py-line--sys">빈 마크다운 셀 — 두 번 눌러 편집</span>
            )}
          </div>
        ) : (
          <CodeEditor
            value={cell.code}
            language={isMarkdown ? 'markdown' : 'python'}
            onChange={(code) => nb.patch(cell.id, { code })}
            onRun={() => nb.enqueue(cell.id)}
            onRunAndNext={() => nb.runAndNext(cell.id)}
            onRunAndInsert={() => nb.runAndInsert(cell.id)}
            onFocus={() => nb.setActiveId(cell.id)}
            focusSignal={nb.focusSignalOf(cell.id)}
            minLines={2}
            label={`셀 ${index + 1} ${isMarkdown ? '마크다운' : '코드'}`}
            placeholder={isMarkdown ? '## 제목, - 목록, **굵게**, `코드` … Shift+Enter 로 보기' : '코드를 입력하고 Shift+Enter'}
          />
        )}

        {!isMarkdown && <CellOutput cell={cell} />}
      </div>
    </article>
  );
}

/** 셀 아래 출력 — print, 그래프, DataFrame 표, 마지막 값(Out) */
function CellOutput({ cell }: { cell: Cell }) {
  if (cell.lines.length === 0 && cell.value === null && !cell.table && cell.images.length === 0) return null;
  return (
    <div className="py-nb-out" aria-live="polite">
      {cell.lines.map((l, i) => (
        <div key={i} className={`py-line--${l.kind}`}>
          {l.kind === 'out' ? l.text.replace(/\n$/, '') : l.text}
        </div>
      ))}
      {cell.images.map((src, i) => (
        <img key={i} className="py-nb-out__img" src={src} alt={`그래프 ${i + 1}`} />
      ))}
      {cell.table && <OutputTable table={cell.table} count={cell.count} />}
      {cell.value !== null && (
        <div className="py-nb-out__value">
          <span className="py-nb-out__label">Out[{cell.count}]</span>
          <span>{cell.value}</span>
        </div>
      )}
    </div>
  );
}

/** DataFrame 표 — 앞 50행까지. 글자로만 그린다. */
function OutputTable({ table, count }: { table: TableData; count: number | null }) {
  const [rows, cols] = table.shape;
  return (
    <div className="py-nb-table">
      <span className="py-nb-out__label">Out[{count}]</span>
      <div className="py-nb-table__scroll">
        <table>
          <thead>
            <tr>
              <th>{table.indexName}</th>
              {table.columns.map((c, i) => (
                <th key={i}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, r) => (
              <tr key={r}>
                <th>{table.index[r]}</th>
                {row.map((v, c) => (
                  <td key={c}>{v}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <span className="py-nb-table__shape">
        {rows}행 × {cols}열{rows > table.rows.length ? ` · 앞 ${table.rows.length}행만 표시` : ''}
      </span>
    </div>
  );
}
