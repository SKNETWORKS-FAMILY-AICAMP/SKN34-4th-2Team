import { useState } from 'react';

import type { PracticeSet } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { NotebookFileMenu } from './NotebookFileMenu';
import { MINI_PROBLEMS } from './notebookExamples';
import { canPromptInput } from './pythonRunner';
import type { Notebook } from './useNotebook';

/** 노트북 도구 줄 — 모두 실행 · 중단 · 변수 초기화 · 셀 추가 · 입력값 · 파일 · 단축키 */
export function NotebookToolbar({ nb, set }: { nb: Notebook; set: PracticeSet | undefined }) {
  const [showStdin, setShowStdin] = useState(false);
  return (
    <>
      <div className="py-toolbar">
        <button type="button" className="btn btn--filled btn--sm" onClick={nb.runAll} disabled={nb.busy}>
          <Icon name="fast_forward" size={18} />
          모두 실행
        </button>
        {nb.busy && (
          <button type="button" className="btn btn--danger btn--sm" onClick={nb.stop}>
            <Icon name="stop" size={18} />
            중단
          </button>
        )}
        <button type="button" className="btn btn--outline btn--sm" onClick={nb.resetKernel} title="모든 변수를 비우고 실행 번호를 1부터 다시 셉니다">
          <Icon name="restart_alt" size={18} />
          변수 초기화
        </button>
        <button type="button" className="btn btn--outline btn--sm" onClick={() => nb.addCellAfter(nb.activeId)}>
          <Icon name="add" size={18} />
          코드
        </button>
        <button type="button" className="btn btn--outline btn--sm" onClick={() => nb.addCellAfter(nb.activeId, 'markdown')}>
          <Icon name="notes" size={18} />
          마크다운
        </button>
        <ProblemPicker nb={nb} />
        <button
          type="button"
          className={`btn btn--outline btn--sm${showStdin ? ' py-toolbar__on' : ''}`}
          onClick={() => setShowStdin((v) => !v)}
          aria-expanded={showStdin}
        >
          <Icon name="keyboard" size={18} />
          입력값{nb.stdinLines ? ` · ${nb.stdinLines}줄` : ''}
        </button>
        <span className="py-grow" />
        <NotebookFileMenu nb={nb} set={set} />
        <ShortcutHelp />
      </div>

      {showStdin && (
        <section className="py-stdin">
          <label htmlFor="py-stdin">
            {canPromptInput ? (
              <>
                미리 적어 두는 입력값 — 비워 두면 <code>input()</code>이 셀 아래에 입력칸을 띄워 물어봐요. 적어 두면 그 줄부터 먼저 써요.
              </>
            ) : (
              <>
                입력값 — <code>input()</code>이 위에서부터 한 줄씩 읽어요. 셀을 실행할 때마다 첫 줄부터 다시 읽습니다.
              </>
            )}
          </label>
          <textarea id="py-stdin" value={nb.stdin} onChange={(e) => nb.setStdin(e.target.value)} rows={3} spellCheck={false} />
        </section>
      )}
    </>
  );
}

/** 연습 문제 넣기 — 목록에서 고르거나 아무거나 하나 */
function ProblemPicker({ nb }: { nb: Notebook }) {
  const [open, setOpen] = useState(false);
  const pick = (id?: string) => {
    const p = id ? MINI_PROBLEMS.find((m) => m.id === id) : MINI_PROBLEMS[Math.floor(Math.random() * MINI_PROBLEMS.length)];
    if (p) nb.addMiniProblem(p);
    setOpen(false);
  };
  return (
    <span className="py-picker">
      <button type="button" className="btn btn--filled btn--sm py-picker__main" onClick={() => pick()} title="연습 문제 하나를 아래에 넣습니다">
        <Icon name="fitness_center" size={18} />
        연습 문제 풀기
      </button>
      <button type="button" className="btn btn--filled btn--sm py-picker__more" onClick={() => setOpen((v) => !v)} aria-label="문제 고르기" aria-expanded={open}>
        <Icon name="expand_more" size={18} />
      </button>
      {open && (
        <ul className="py-picker__menu" role="menu">
          {MINI_PROBLEMS.map((m) => (
            <li key={m.id}>
              <button type="button" role="menuitem" onClick={() => pick(m.id)}>
                {m.title}
              </button>
            </li>
          ))}
        </ul>
      )}
    </span>
  );
}

function ShortcutHelp() {
  return (
    <details className="py-keys">
      <summary>단축키</summary>
      <dl>
        <dt>Shift + Enter</dt>
        <dd>실행하고 다음 셀로</dd>
        <dt>Ctrl + Enter</dt>
        <dd>실행하고 그 자리에</dd>
        <dt>Alt + Enter</dt>
        <dd>실행하고 아래에 새 셀</dd>
        <dt>Tab / Shift + Tab</dt>
        <dd>들여쓰기 / 내어쓰기</dd>
        <dt>Ctrl + /</dt>
        <dd>주석 켜고 끄기</dd>
        <dt>Ctrl + Space</dt>
        <dd>자동완성 목록 열기</dd>
        <dt>두 번 누르기</dt>
        <dd>마크다운 셀 편집</dd>
      </dl>
    </details>
  );
}
