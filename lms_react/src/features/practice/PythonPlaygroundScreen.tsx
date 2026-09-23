import { useEffect } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { RoutePaths } from '../../app/routePaths';
import { Icon } from '../../ui/Icon';
import { NotebookCellView } from './NotebookCellView';
import { NotebookToolbar } from './NotebookToolbar';
import { PYODIDE_VERSION } from './pythonProtocol';
import { usePythonRunner, type RunnerStatus } from './pythonRunner';
import { RETRY_SET_ID } from './review';
import { TutorProvider, useTutor } from './TutorContext';
import { TutorPanel } from './TutorPanel';
import { useNotebook } from './useNotebook';
import { usePracticeSetMode, type PracticeSetMode } from './usePracticeSetMode';

const STATUS_TEXT: Record<RunnerStatus, string> = {
  idle: '대기',
  loading: '런타임 불러오는 중',
  ready: '준비됨',
  running: '실행 중',
  error: '불러오지 못함',
};

/**
 * 파이썬 연습장 — 노트북처럼 셀을 나눠 돌린다.
 *
 * ?set= 없이 열면 자유 연습장, ?set=<세트 id> 면 그날 복습 문제, ?set=retry 면 다시 풀 문제.
 * 세트가 바뀌면 통째로 다시 그린다(key).
 *
 * 조각:
 *   useNotebook          셀 상태 · 실행 대기열 · 편집 동작
 *   usePracticeSetMode   어떤 문제 세트인지 · 풀이 기록 · 진행률
 *   NotebookToolbar      도구 줄 · 입력값 · 단축키
 *   NotebookCellView     셀 한 칸(코드·마크다운·문제)과 출력
 *   TutorPanel           오른쪽에 붙는 튜터 — 문제 셀은 힌트, 코드 셀은 설명(서버 LLM)
 *
 * 코드는 이 브라우저 안(Pyodide)에서만 돈다. 튜터에게 물을 때만 그 셀의 코드 · 출력이 서버로 간다.
 */
export function PythonPlaygroundScreen() {
  const [params] = useSearchParams();
  const setId = params.get('set');
  const focus = Number(params.get('focus') ?? 0);
  return (
    <TutorProvider key={setId ?? 'free'}>
      <Playground setId={setId} focusProblem={focus} />
    </TutorProvider>
  );
}

function Playground({ setId, focusProblem }: { setId: string | null; focusProblem: number }) {
  const { runner, status } = usePythonRunner();
  const mode = usePracticeSetMode(setId);
  const nb = useNotebook(runner, mode.set);

  // 성취도평가 결과에서 「복습 문제 n개 풀기」로 들어오면 그 문제로 바로 간다
  useEffect(() => {
    if (!focusProblem) return;
    const cell = nb.cells.find((c) => c.type === 'problem' && c.problemIndex === focusProblem - 1);
    if (cell) {
      nb.setActiveId(cell.id);
      requestAnimationFrame(() => document.querySelector(`[data-cell-id="${cell.id}"]`)?.scrollIntoView({ block: 'start', behavior: 'smooth' }));
    }
    // 처음 한 번만
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const lastId = nb.cells[nb.cells.length - 1]?.id ?? '';

  const tutorOpen = Boolean(useTutor()?.target);

  // 튜터가 열려 있으면 오른쪽 아래 로봇(학습 도우미)을 숨긴다 — 패널 입력칸을 가린다. 패널의 「학습 도우미」 탭으로 연다
  useEffect(() => {
    document.body.classList.toggle('py-tutor-open', tutorOpen);
    return () => document.body.classList.remove('py-tutor-open');
  }, [tutorOpen]);

  return (
    <div className={`py-layout${tutorOpen ? ' py-layout--tutor' : ''}`}>
      <div className="screen__inner py-playground">
        <header className="study-head">
          <PlaygroundTitle mode={mode} />
          <span className={`py-status py-status--${status}`} title={`Pyodide ${PYODIDE_VERSION}`}>
            <span className="py-status__lamp" />
            <span>
              <strong>Python</strong> · {STATUS_TEXT[status]}
            </span>
          </span>
        </header>

        <NotebookToolbar nb={nb} set={mode.set} />

        {setId && !mode.set && (
          <div className="py-kernel-note" role="status">
            <Icon name="info" size={18} />
            <span>
              {setId === RETRY_SET_ID
                ? '다시 풀 문제가 없어요. 틀린 복습 문제가 생기면 여기에 모여요.'
                : '찾는 복습 세트가 없어요. 공부방의 수업 카드에서 다시 골라 주세요.'}
            </span>
          </div>
        )}

        {nb.kernelNote && (
          <div className="py-kernel-note" role="status">
            <Icon name="info" size={18} />
            <span>{nb.kernelNote}</span>
            <button type="button" onClick={nb.dismissKernelNote} aria-label="닫기">
              <Icon name="close" size={16} />
            </button>
          </div>
        )}

        <div className="py-notebook">
          {nb.cells.map((cell, index) => (
            <NotebookCellView key={cell.id} cell={cell} index={index} total={nb.cells.length} nb={nb} mode={mode} />
          ))}
          <div className="py-add-row">
            <button type="button" className="py-add-cell" onClick={() => nb.addCellAfter(lastId)}>
              <Icon name="add" size={18} />
              코드 셀
            </button>
            <button type="button" className="py-add-cell" onClick={() => nb.addCellAfter(lastId, 'markdown')}>
              <Icon name="notes" size={18} />
              마크다운 셀
            </button>
          </div>
        </div>

        <p className="py-foot">
          파일 읽기·인터넷 요청은 쓸 수 없습니다. torch·cv2 같은 모델 라이브러리도 브라우저에서는 돌지 않습니다. 그래프의 한글은 글꼴이 없어 네모로
          나오니 영어로 적어 주세요. 마지막 줄 끝에 <code>;</code>를 붙이면 값 표시를 숨깁니다.
        </p>
      </div>
      <TutorPanel />
    </div>
  );
}

/** 위치 · 제목 · 설명, 문제 세트면 진행 막대 */
function PlaygroundTitle({ mode }: { mode: PracticeSetMode }) {
  const { set, isRetry, passedCount, visibleCount } = mode;
  return (
    <div>
      <nav className="py-crumbs" aria-label="위치">
        <Link to={RoutePaths.studyRoom}>학습실</Link>
        <Icon name="chevron_right" size={16} />
        {set ? (
          <>
            <Link to={RoutePaths.studyRoomNotes}>공부방</Link>
            <Icon name="chevron_right" size={16} />
            <span>{isRetry ? '다시 풀 문제' : '복습 문제'}</span>
          </>
        ) : (
          <span>파이썬 연습장</span>
        )}
      </nav>
      <h1 className="study-head__title">
        {isRetry ? '다시 풀 문제' : set ? `${set.dayLabel} 복습 · ${set.title}` : '파이썬 연습장'}
      </h1>
      <p className="study-head__desc">
        {isRetry && set
          ? `지난 복습에서 통과하지 못한 문제 ${set.problems.length}개입니다. 통과하면 다음에 열 때 목록에서 빠져요.`
          : set
            ? `${set.lessonDate} 수업 코드로 만든 문제 ${set.problems.length}개. 문제 사이에 셀을 추가해 자유롭게 시험해 봐도 됩니다.`
            : '노트북처럼 셀을 나눠 실행합니다. 앞 셀에서 만든 변수는 다음 셀에서 그대로 쓸 수 있어요. 코드는 이 브라우저 안에서만 돕니다.'}
      </p>
      {set && (
        <div className="pb-progress" aria-label={`통과 ${passedCount} / ${visibleCount}`}>
          <div className="pb-progress__bar">
            {set.problems.map((_, i) => {
              if (mode.hiddenOf(i)) return null;
              const a = mode.attemptOf(i);
              return <i key={i} className={a?.passed ? 'ok' : a ? 'no' : ''} />;
            })}
          </div>
          <span>
            통과 <strong>{passedCount}</strong> / {visibleCount}
          </span>
        </div>
      )}
    </div>
  );
}
