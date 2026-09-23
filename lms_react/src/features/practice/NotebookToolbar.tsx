import { useState } from 'react';

import type { PracticeSet } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { MoreMenu } from '../../ui/MoreMenu';
import { startPracticeFromFile } from '../../data/repository';
import { MakeProblems } from './MakeProblems';
import { useNotebookFile } from './NotebookFileMenu';
import { toPy } from './notebookFile';
import { EXAMPLES, MINI_HEADING, MINI_LEVELS, MINI_PROBLEMS } from './notebookExamples';
import { canPromptInput } from './pythonRunner';
import type { Notebook } from './useNotebook';

/**
 * 노트북 도구 줄.
 *
 * 한 번에 보이는 건 여섯 개다 — 모두 실행 · 셀 추가 · 연습 문제 · 문제 만들기 · 입력값 · 「···」.
 * 예전에는 단추 아홉 개에 예시 칩 여섯 개까지 한 줄에 다 나와 있었다. 자주 누르는 것만
 * 남기고, 셀 종류와 예시는 「셀 추가」 안으로, 가끔 쓰는 것(변수 초기화 · 파일 · 단축키)은
 * 「···」 안으로 넣었다. 셀 추가는 노트북 맨 아래 줄에도 있다.
 */
export function NotebookToolbar({ nb, set }: { nb: Notebook; set: PracticeSet | undefined }) {
  const [showStdin, setShowStdin] = useState(false);
  const [showKeys, setShowKeys] = useState(false);
  const file = useNotebookFile(nb, set);
  const [making, setMaking] = useState(false);

  return (
    <>
      <div className="py-toolbar">
        <span className="py-toolbar__run">
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
        </span>

        <MoreMenu
          label="셀 추가"
          icon="add"
          align="left"
          className="btn btn--outline btn--sm"
          items={[
            { key: 'code', icon: 'code', label: '코드 셀', onSelect: () => nb.addCellAfter(nb.activeId) },
            { key: 'markdown', icon: 'notes', label: '마크다운 셀', onSelect: () => nb.addCellAfter(nb.activeId, 'markdown') },
            ...EXAMPLES.map((e, i) => ({
              key: e.id,
              icon: e.type === 'markdown' ? 'notes' : 'code',
              label: e.label,
              hint: e.source,
              divider: i === 0,
              onSelect: () => nb.addExample(e.code, e.type),
            })),
          ]}
        />

        <ProblemPicker nb={nb} />

        {/* 연습장의 주 기능이라 「···」 안에 두지 않는다 — 지금 셀(불러온 파일 포함)로 AI 가 복습 문제를 만든다 */}
        <button
          type="button"
          className={`btn btn--outline btn--sm${making ? ' py-toolbar__on' : ''}`}
          onClick={() => setMaking((v) => !v)}
          aria-expanded={making}
          title="지금 셀로 복습 문제 6개를 만들어요 · 나만 봐요"
        >
          <Icon name="auto_awesome" size={18} />
          문제 만들기
        </button>

        <span className="py-grow" />

        <button
          type="button"
          className={`btn btn--outline btn--sm${showStdin ? ' py-toolbar__on' : ''}`}
          onClick={() => setShowStdin((v) => !v)}
          aria-expanded={showStdin}
        >
          <Icon name="keyboard" size={18} />
          입력값{nb.stdinLines ? ` · ${nb.stdinLines}줄` : ''}
        </button>

        <MoreMenu
          label="더 보기"
          items={[
            { key: 'reset', icon: 'restart_alt', label: '변수 초기화', hint: '모든 변수를 비우고 실행 번호를 1부터', onSelect: nb.resetKernel },
            { key: 'open', icon: 'upload_file', label: '불러오기…', hint: '.ipynb · .py 파일', divider: true, onSelect: file.openPicker },
            { key: 'ipynb', icon: 'download', label: '내려받기 · .ipynb', hint: 'Jupyter 노트북 · 출력 포함', onSelect: () => file.download('ipynb') },
            { key: 'py', icon: 'download', label: '내려받기 · .py', hint: '# %% 로 셀 구분', onSelect: () => file.download('py') },
            { key: 'keys', icon: 'keyboard_command_key', label: showKeys ? '단축키 닫기' : '단축키', divider: true, onSelect: () => setShowKeys((v) => !v) },
          ]}
        />

        {file.input}
        {file.panel}
      </div>

      {making && (
        <div className="py-make">
          <MakeProblems
            start={() => startPracticeFromFile(nb.fileName ?? (set ? `review-${set.lessonDate}.py` : 'playground.py'), toPy(nb.cells, set))}
            idleLabel="이 노트북으로 만들기"
            hint={`지금 열린 노트북${nb.fileName ? `(${nb.fileName})` : ''}의 셀로 복습 문제 6개를 만들어요. 만든 문제는 나만 봐요.`}
          />
          <button type="button" className="icon-btn" aria-label="닫기" onClick={() => setMaking(false)}>
            <Icon name="close" size={18} />
          </button>
        </div>
      )}

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

      {showKeys && <ShortcutHelp onClose={() => setShowKeys(false)} />}
    </>
  );
}

/**
 * 연습 문제 넣기 — 누르면 **아직 안 푼 것 중 가장 쉬운 것**, 화살표로는 골라서.
 *
 * 목록이 쉬운 순서라 처음 누르면 기초부터 차례로 나온다. 노트북에 이미 든 문제는
 * 설명 셀 머리글로 알아본다 — 저장했다 다시 연 노트북에서도 이어진다.
 */
function ProblemPicker({ nb }: { nb: Notebook }) {
  const done = new Set(
    nb.cells
      .filter((c) => c.type === 'markdown' && c.code.startsWith(MINI_HEADING))
      .map((c) => c.code.slice(MINI_HEADING.length).split('\n')[0].trim()),
  );
  const next = MINI_PROBLEMS.find((m) => !done.has(m.title)) ?? MINI_PROBLEMS[0];
  const pick = (id?: string) => {
    const p = id ? MINI_PROBLEMS.find((m) => m.id === id) : next;
    if (p) nb.addMiniProblem(p);
  };
  return (
    <span className="py-picker">
      <button
        type="button"
        className="btn btn--outline btn--sm py-picker__main"
        onClick={() => pick()}
        title={`다음 문제 · ${MINI_LEVELS[next.level]} · ${next.title}`}
      >
        <Icon name="fitness_center" size={18} />
        연습 문제 풀기
      </button>
      <MoreMenu
        label="문제 고르기"
        align="left"
        className="btn btn--outline btn--sm py-picker__more"
        items={MINI_PROBLEMS.map((m, i) => ({
          key: m.id,
          label: m.title,
          heading: i === 0 || MINI_PROBLEMS[i - 1].level !== m.level ? MINI_LEVELS[m.level] : undefined,
          divider: i > 0 && MINI_PROBLEMS[i - 1].level !== m.level,
          done: done.has(m.title),
          onSelect: () => pick(m.id),
        }))}
      >
        <Icon name="expand_more" size={18} />
      </MoreMenu>
    </span>
  );
}

function ShortcutHelp({ onClose }: { onClose(): void }) {
  return (
    <section className="py-keys" aria-label="단축키">
      <div className="py-keys__head">
        <Icon name="keyboard_command_key" size={18} />
        <span>단축키</span>
        <span className="py-grow" />
        <button type="button" className="icon-btn" onClick={onClose} aria-label="단축키 닫기">
          <Icon name="close" size={18} />
        </button>
      </div>
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
    </section>
  );
}
