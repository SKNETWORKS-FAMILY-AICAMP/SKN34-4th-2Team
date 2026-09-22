import { useState } from 'react';

import { Icon } from '../../ui/Icon';
import type { Notebook } from './useNotebook';

/** 노트북 도구 줄 — 모두 실행 · 중단 · 변수 초기화 · 셀 추가 · 입력값 · 단축키 */
export function NotebookToolbar({ nb }: { nb: Notebook }) {
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
        <ShortcutHelp />
      </div>

      {showStdin && (
        <section className="py-stdin">
          <label htmlFor="py-stdin">
            입력값 — <code>input()</code>이 위에서부터 한 줄씩 읽어요. 셀을 실행할 때마다 첫 줄부터 다시 읽습니다.
          </label>
          <textarea id="py-stdin" value={nb.stdin} onChange={(e) => nb.setStdin(e.target.value)} rows={3} spellCheck={false} />
        </section>
      )}
    </>
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
