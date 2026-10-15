import { useEffect, useId, useRef, useState } from 'react';

import { Icon } from '../../ui/Icon';
import { NotebookCellView } from './NotebookCellView';
import { NotebookMarkdown } from './NotebookMarkdown';
import { NotebookToolbar } from './NotebookToolbar';
import { KIND_LABEL } from './practiceLabels';
import { PracticeLink, useInPracticeDock } from './PracticeDock';
import { PYODIDE_VERSION } from './pythonProtocol';
import type { RunnerStatus } from './pythonRunner';
import { useTutor } from './TutorContext';
import type { Notebook } from './useNotebook';
import type { PracticeSetMode } from './usePracticeSetMode';
import './focusedPractice.css';

/** 문제를 숨겨도 마운트를 유지한다. 선택 답안·실행 결과와 노트북 세션은 문제 이동 후에도 남는다. */
export function FocusedPracticeNotebook({ nb, mode, focusProblem, focusRequest, status, onFinish }: {
  nb: Notebook;
  mode: PracticeSetMode;
  focusProblem: number;
  focusRequest?: number;
  status: RunnerStatus;
  onFinish: () => void;
}) {
  const set = mode.set!;
  const problems = nb.cells.filter((cell) => cell.type === 'problem' && !mode.hiddenOf(cell.problemIndex ?? 0));
  const [selectedId, setSelectedId] = useState(() => (
    problems.find((cell) => cell.problemIndex === focusProblem - 1) ?? problems[0]
  )?.id ?? '');
  const [showList, setShowList] = useState(false);
  const [showTools, setShowTools] = useState(false);
  const [showScratch, setShowScratch] = useState(false);
  const tutor = useTutor();
  const inDock = useInPracticeDock();
  const selected = problems.find((cell) => cell.id === selectedId) ?? problems[0];
  const position = problems.findIndex((cell) => cell.id === selected?.id);
  const attemptedCount = problems.filter((cell) => mode.attemptOf(cell.problemIndex ?? 0)).length;
  const wrong = problems.filter((cell) => {
    const attempt = mode.attemptOf(cell.problemIndex ?? 0);
    return attempt && !attempt.passed;
  });
  const allAttempted = problems.length > 0 && attemptedCount === problems.length;
  const heading = useRef<HTMLDivElement>(null);
  const listId = useId();
  const setActiveId = nb.setActiveId;
  const tutorInitialized = useRef(false);
  const openTutorFor = tutor?.openFor;

  // 첫 문제를 불러온 뒤 한 번만 연다. 사용자가 접은 뒤에는 문제를 이동해도 다시 열지 않는다.
  useEffect(() => {
    if (!tutorInitialized.current && selected && openTutorFor?.([selected.id])) {
      tutorInitialized.current = true;
    }
  }, [selected?.id, openTutorFor]);

  // 이미 열린 탭을 링크로 다시 열 때도 지정 문제로 이동한다.
  useEffect(() => {
    const cell = problems.find((item) => item.problemIndex === focusProblem - 1);
    if (cell) setSelectedId(cell.id);
    // 셀은 입력마다 바뀌므로 링크의 focus가 바뀔 때만 적용한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusProblem, focusRequest]);

  useEffect(() => {
    if (selected) setActiveId(selected.id);
  }, [selected?.id, setActiveId]);

  // 코드 실험에서 문제 셀로 이동하는 단축키도 선택에 반영한다.
  useEffect(() => {
    if (problems.some((cell) => cell.id === nb.activeId)) setSelectedId(nb.activeId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nb.activeId]);

  const select = (id: string) => {
    setSelectedId(id);
    nb.setActiveId(id);
    setShowList(false);
    heading.current?.scrollIntoView?.({ block: 'start', behavior: 'smooth' });
  };
  const intro = nb.cells[0]?.type === 'markdown' ? nb.cells[0] : undefined;
  const scratch = nb.cells.filter((cell) => cell.type !== 'problem' && cell !== intro);
  const lastId = nb.cells[nb.cells.length - 1]?.id ?? '';
  const title = mode.isRetry ? set.dayLabel : `${set.dayLabel} 복습`;

  return (
    <section className="pf-study" aria-label={title}>
      <header className="pf-head">
        <div className="pf-head__title">
          <h1>{title}</h1>
          <span className="pf-progress" aria-label={`해결 ${mode.passedCount} / ${mode.visibleCount}`}>
            해결 <strong>{mode.passedCount}</strong> / {mode.visibleCount}
          </span>
          <span className="pf-progress" aria-label={`풀이 시도 ${attemptedCount} / ${problems.length}`}>
            풀이 시도 <strong>{attemptedCount}</strong> / {problems.length}
          </span>
        </div>
        <div className="pf-head__actions">
          {!inDock && <PracticeLink setId={null} className="btn btn--outline btn--sm"><Icon name="add" size={17} /> 자유 연습장</PracticeLink>}
          <button type="button" className="btn btn--outline btn--sm" aria-expanded={showList} aria-controls={listId}
            onClick={() => setShowList((value) => !value)}>
            <Icon name="format_list_numbered" size={17} /> 문제 목록
          </button>
          {tutor && <button type="button" className={`btn btn--outline btn--sm${tutor.target ? ' py-toolbar__on' : ''}`}
            aria-expanded={Boolean(tutor.target)} disabled={!selected}
            onClick={() => tutor.target ? tutor.close() : selected && tutor.openFor([selected.id])}>
            <Icon name="school" size={17} /> AI 튜터
          </button>}
          <button type="button" className="btn btn--text btn--sm" aria-expanded={showTools}
            onClick={() => setShowTools((value) => !value)}>
            <Icon name="more_horiz" size={18} /> 추가 도구
          </button>
        </div>
      </header>

      <div className="pf-tools" hidden={!showTools}>
        <p className="muted" title={`Pyodide ${PYODIDE_VERSION}`}>Python · {status === 'running' ? '실행 중' : status === 'loading' ? '불러오는 중' : status === 'error' ? '불러오지 못함' : status === 'ready' ? '준비됨' : '대기'}</p>
        <NotebookToolbar nb={nb} set={set} focused />
      </div>

      <nav className="pf-list" id={listId} aria-label="복습 문제 목록" hidden={!showList}>
        {problems.map((cell) => {
          const index = cell.problemIndex ?? 0;
          const problem = set.problems[index];
          const attempt = mode.attemptOf(index);
          return <button type="button" key={cell.id} aria-current={cell.id === selected?.id ? 'step' : undefined}
            onClick={() => select(cell.id)}>
            <span className="pf-list__number">{index + 1}</span>
            <span className="pf-list__topic"><strong>{problem.topic}</strong><small>{mode.noteOf(index) ?? KIND_LABEL[problem.kind]}</small></span>
            <span className={`pf-list__state${attempt?.passed ? ' pf-list__state--done' : ''}`}>{attempt?.passed ? '완료' : attempt ? '다시 풀기' : '미완료'}</span>
          </button>;
        })}
      </nav>

      <div className="pf-navigation" ref={heading}>
        <div><strong>{selected ? `문제 ${(selected.problemIndex ?? 0) + 1}` : '풀 수 있는 문제가 없어요'}</strong>
          {selected && <span>{KIND_LABEL[set.problems[selected.problemIndex ?? 0].kind]} · {position + 1} / {problems.length}</span>}
        </div>
        <div className="pf-navigation__buttons">
          <button type="button" className="btn btn--outline btn--sm" disabled={position <= 0} onClick={() => select(problems[position - 1].id)}>
            <Icon name="chevron_left" size={17} /> 이전
          </button>
          <button type="button" className="btn btn--outline btn--sm" disabled={position < 0 || position >= problems.length - 1} onClick={() => select(problems[position + 1].id)}>
            다음 <Icon name="chevron_right" size={17} />
          </button>
        </div>
      </div>
      {allAttempted && (
        <section className="pf-completion" aria-label="복습 결과">
          <div className="pf-completion__copy">
            <h2>{wrong.length === 0 ? '모든 문제를 해결했어요!' : '이번 복습 문제를 모두 풀어봤어요'}</h2>
            <p>정답 {mode.passedCount}개 · 오답 {wrong.length}개<span> · 풀이 기록을 유지하고 공부방으로 돌아갑니다.</span></p>
          </div>
          <div className="pf-completion__actions">
            {wrong.length > 0 && <button type="button" className="btn btn--outline btn--sm pf-completion__retry" onClick={() => select(wrong[0].id)}>
              틀린 문제 다시 풀기
            </button>}
            <button type="button" className="btn btn--filled btn--sm" onClick={onFinish}>
              복습 종료 · 공부방으로
            </button>
          </div>
        </section>
      )}
      <div className="pf-problems">
        {nb.cells.filter((cell) => cell.type === 'problem').map((cell) => (
          <div key={cell.id} hidden={cell.id !== selected?.id || mode.hiddenOf(cell.problemIndex ?? 0)}>
            <NotebookCellView cell={cell} index={nb.cells.indexOf(cell)} total={nb.cells.length} nb={nb} mode={mode} focused
              onNext={() => position >= 0 && position < problems.length - 1 && select(problems[position + 1].id)} />
          </div>
        ))}
      </div>

      <details className="pf-details" open={showScratch} onToggle={(event) => setShowScratch(event.currentTarget.open)}>
        <summary><Icon name="terminal" size={17} /> 코드 실험 <span>현재 탭에서 자유롭게 실행</span></summary>
        <div className="pf-scratch">
          {scratch.map((cell) => <NotebookCellView key={cell.id} cell={cell} index={nb.cells.indexOf(cell)} total={nb.cells.length} nb={nb} mode={mode} />)}
          <div className="py-add-row">
            <button type="button" className="py-add-cell" onClick={() => nb.addCellAfter(lastId)}><Icon name="add" size={17} /> 코드 셀</button>
            <button type="button" className="py-add-cell" onClick={() => nb.addCellAfter(lastId, 'sql')}><Icon name="database" size={17} /> SQL 셀</button>
          </div>
        </div>
      </details>
      <details className="pf-details pf-details--guide">
        <summary><Icon name="info" size={17} /> 상세 안내</summary>
        <div className="pf-guide">
          <p>{set.title} · {set.lessonDate}</p>
          {intro && <NotebookMarkdown source={intro.code} />}
          <p>Python·SQL 문제의 실행과 코드 실험은 같은 탭의 실행 상태를 사용하고, 채점은 별도 공간에서 실행합니다. JavaScript·웹 실습의 실행 상태는 코드 실험과 공유하지 않습니다. 자유 연습장은 상단의 + 버튼으로 열 수 있어요.</p>
          <p>파일 읽기·인터넷 요청과 torch·cv2 같은 모델 라이브러리는 브라우저에서 사용할 수 없습니다.</p>
        </div>
      </details>
    </section>
  );
}
