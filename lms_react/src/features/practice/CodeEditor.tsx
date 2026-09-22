import { useEffect, useRef } from 'react';
import {
  autocompletion,
  closeBrackets,
  closeBracketsKeymap,
  completeFromList,
  completionKeymap,
  type CompletionContext,
  type CompletionResult,
} from '@codemirror/autocomplete';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import { python, pythonLanguage } from '@codemirror/lang-python';
import { bracketMatching, HighlightStyle, indentOnInput, indentUnit, syntaxHighlighting } from '@codemirror/language';
import { EditorState, Prec } from '@codemirror/state';
import {
  drawSelection,
  EditorView,
  highlightActiveLine,
  highlightActiveLineGutter,
  keymap,
  lineNumbers,
  placeholder as placeholderExt,
} from '@codemirror/view';
import { tags as t } from '@lezer/highlight';

/**
 * 파이썬 코드 편집기 — CodeMirror 6.
 *
 * - 괄호·따옴표 자동 닫기, 엔터 때 들여쓰기 유지, `:` 뒤 자동 들여쓰기
 * - 자동완성: 코드 안의 변수·함수 이름, 파이썬 키워드·내장 함수(언어 팩 기본),
 *   그리고 수업에서 자주 쓰는 `np.` `re.` `pd.` 뒤의 함수 이름
 * - 단축키는 Jupyter 와 같다: Ctrl/⌘+Enter 실행, Shift+Enter 실행 후 다음 셀, Alt+Enter 실행 후 아래에 새 셀
 * - Tab·Shift+Tab 들여쓰기/내어쓰기, Ctrl/⌘+/ 주석 켜고 끄기, Ctrl/⌘+Z 되돌리기
 *
 * 색은 styles.css 의 --py-tok-* 변수에서 가져와 밝은·어두운 테마를 따라간다.
 */
export function CodeEditor({
  value,
  onChange,
  onRun,
  onRunAndNext,
  onRunAndInsert,
  onFocus,
  focusSignal,
  language = 'python',
  readOnly = false,
  label = '파이썬 코드',
  minLines = 8,
  placeholder,
}: {
  value: string;
  onChange?: (value: string) => void;
  onRun?: () => void;
  /** Shift+Enter */
  onRunAndNext?: () => void;
  /** Alt+Enter */
  onRunAndInsert?: () => void;
  onFocus?: () => void;
  /** 값이 바뀔 때마다 편집기에 포커스를 준다(노트북에서 다음 셀로 넘어갈 때). */
  focusSignal?: number;
  /** markdown 이면 파이썬 색칠·자동완성·괄호 자동 닫기를 끈다 */
  language?: 'python' | 'markdown';
  readOnly?: boolean;
  label?: string;
  minLines?: number;
  placeholder?: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  // 편집기는 한 번만 만든다. 최신 콜백은 ref 로 넘긴다.
  const latest = useRef({ onChange, onRun, onRunAndNext, onRunAndInsert, onFocus });
  latest.current = { onChange, onRun, onRunAndNext, onRunAndInsert, onFocus };

  useEffect(() => {
    if (!host.current) return;
    const editor = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: value,
        extensions: [
          lineNumbers(),
          highlightActiveLineGutter(),
          highlightActiveLine(),
          history(),
          drawSelection(),
          indentOnInput(),
          indentUnit.of('    '),
          EditorState.tabSize.of(4),
          ...(language === 'python'
            ? [
                bracketMatching(),
                closeBrackets(),
                python(),
                pythonLanguage.data.of({ autocomplete: moduleMembers }),
                autocompletion({ activateOnTyping: true, icons: false }),
                syntaxHighlighting(pyHighlight),
              ]
            : [EditorView.lineWrapping]),
          Prec.highest(
            keymap.of([
              { key: 'Mod-Enter', run: () => fire(latest.current.onRun) },
              { key: 'Shift-Enter', run: () => fire(latest.current.onRunAndNext ?? latest.current.onRun) },
              { key: 'Alt-Enter', run: () => fire(latest.current.onRunAndInsert ?? latest.current.onRun) },
            ]),
          ),
          keymap.of([...closeBracketsKeymap, ...completionKeymap, ...historyKeymap, ...defaultKeymap, indentWithTab]),
          EditorState.readOnly.of(readOnly),
          EditorView.editable.of(!readOnly),
          EditorView.contentAttributes.of({ 'aria-label': label }),
          ...(placeholder ? [placeholderExt(placeholder)] : []),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) latest.current.onChange?.(update.state.doc.toString());
            if (update.focusChanged && update.view.hasFocus) latest.current.onFocus?.();
          }),
          editorTheme,
        ],
      }),
    });
    view.current = editor;
    return () => {
      editor.destroy();
      view.current = null;
    };
    // value 는 처음 한 번만 쓴다. 이후 바깥에서 바뀐 값은 아래 effect 가 넣는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [readOnly, label, placeholder, language]);

  useEffect(() => {
    if (focusSignal === undefined || focusSignal === 0) return;
    const editor = view.current;
    if (!editor) return;
    editor.focus();
    editor.dispatch({ selection: { anchor: editor.state.doc.length } });
    // 새 셀이 화면 밖(도구 줄은 맨 위, 셀은 아래)에 생기면 커서만 옮겨지고 보이지 않는다. 셀을 화면 안으로.
    host.current?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [focusSignal]);

  // 예시 불러오기처럼 바깥에서 값을 바꾼 경우에만 문서를 갈아 끼운다.
  useEffect(() => {
    const editor = view.current;
    if (!editor) return;
    const current = editor.state.doc.toString();
    if (current !== value) {
      editor.dispatch({ changes: { from: 0, to: current.length, insert: value } });
    }
  }, [value]);

  return <div className="py-editor" ref={host} style={{ minHeight: `calc(${minLines} * 1.65em + 28px)` }} />;
}

/** 단축키 처리 — 넘길 함수가 없으면 CodeMirror 기본 동작(줄바꿈)으로 둔다. */
function fire(handler: (() => void) | undefined): boolean {
  if (!handler) return false;
  handler();
  return true;
}

// ── 자동완성: 모듈 뒤 점(.) ─────────────────────────────

/** 수업(numpy·pandas·re)에서 자주 쓰는 것만. 다 넣지 않는다 — 목록이 길면 오히려 못 고른다. */
const MODULE_MEMBERS: Record<string, string[]> = {
  np: ['array', 'zeros', 'ones', 'arange', 'linspace', 'mean', 'sum', 'max', 'min', 'argmax', 'argmin', 'argsort', 'sqrt', 'exp', 'log', 'dot', 'reshape', 'transpose', 'stack', 'concatenate', 'where', 'round', 'random', 'linalg', 'uint8', 'float32', 'isclose', 'clip'],
  numpy: ['array', 'zeros', 'ones', 'arange', 'linspace', 'mean', 'sum', 'argmax', 'sqrt', 'dot', 'reshape', 'where'],
  pd: ['DataFrame', 'Series', 'concat', 'merge', 'to_numeric', 'to_datetime', 'isna', 'cut'],
  re: ['search', 'match', 'fullmatch', 'findall', 'finditer', 'sub', 'split', 'compile', 'IGNORECASE'],
  math: ['sqrt', 'floor', 'ceil', 'log', 'exp', 'pi', 'inf', 'isclose'],
  random: ['seed', 'random', 'randint', 'choice', 'shuffle', 'sample'],
};

function moduleMembers(context: CompletionContext): CompletionResult | null {
  const before = context.matchBefore(/\b(np|numpy|pd|re|math|random)\.\w*$/);
  if (!before) return null;
  const module = before.text.slice(0, before.text.indexOf('.'));
  const options = MODULE_MEMBERS[module].map((name) => ({
    label: name,
    type: /^[A-Z]/.test(name) ? 'class' : 'function',
  }));
  // completeFromList 는 커서 앞 단어(점 뒤)만 바꿔 끼운다.
  return completeFromList(options)(context) as CompletionResult | null;
}

// ── 색과 모양 ─────────────────────────────────────────

const pyHighlight = HighlightStyle.define([
  { tag: [t.keyword, t.controlKeyword, t.definitionKeyword, t.moduleKeyword, t.operatorKeyword], color: 'var(--py-tok-kw)', fontWeight: '600' },
  { tag: [t.string, t.special(t.string)], color: 'var(--py-tok-str)' },
  { tag: [t.number, t.bool, t.null], color: 'var(--py-tok-num)' },
  { tag: t.comment, color: 'var(--py-tok-com)', fontStyle: 'italic' },
  { tag: [t.function(t.variableName), t.function(t.propertyName), t.standard(t.variableName)], color: 'var(--py-tok-fn)' },
  { tag: t.definition(t.variableName), color: 'var(--text-primary)', fontWeight: '600' },
]);

const editorTheme = EditorView.theme({
  '&': {
    backgroundColor: 'var(--py-code-bg)',
    color: 'var(--text-primary)',
    fontSize: '13px',
    height: '100%',
  },
  '&.cm-focused': { outline: 'none' },
  '.cm-scroller': {
    fontFamily: "'JetBrains Mono', ui-monospace, 'Cascadia Code', Consolas, monospace",
    lineHeight: '1.65',
  },
  '.cm-content': { padding: '14px 0', caretColor: 'var(--primary)' },
  '.cm-line': { padding: '0 16px' },
  '.cm-gutters': {
    backgroundColor: 'var(--py-code-bg)',
    color: 'var(--text-hint)',
    border: 'none',
    borderRight: '1px solid var(--divider)',
  },
  '.cm-lineNumbers .cm-gutterElement': { padding: '0 10px 0 12px', minWidth: '32px' },
  '.cm-activeLine': { backgroundColor: 'color-mix(in srgb, var(--primary) 5%, transparent)' },
  '.cm-activeLineGutter': { backgroundColor: 'transparent', color: 'var(--text-secondary)' },
  '.cm-cursor': { borderLeftColor: 'var(--primary)', borderLeftWidth: '2px' },
  '&.cm-focused .cm-selectionBackground, .cm-selectionBackground': {
    backgroundColor: 'color-mix(in srgb, var(--primary) 22%, transparent) !important',
  },
  '.cm-matchingBracket': {
    backgroundColor: 'color-mix(in srgb, var(--primary) 18%, transparent)',
    outline: '1px solid color-mix(in srgb, var(--primary) 40%, transparent)',
  },
  '.cm-placeholder': { color: 'var(--text-hint)' },
  // 자동완성 목록
  '.cm-tooltip': {
    border: '1px solid var(--border)',
    borderRadius: '10px',
    backgroundColor: 'var(--surface)',
    boxShadow: '0 8px 24px var(--shadow)',
    overflow: 'hidden',
  },
  '.cm-tooltip.cm-tooltip-autocomplete > ul': {
    fontFamily: "'JetBrains Mono', ui-monospace, Consolas, monospace",
    fontSize: '12.5px',
    maxHeight: '220px',
    padding: '4px',
  },
  '.cm-tooltip.cm-tooltip-autocomplete > ul > li': { padding: '3px 10px', borderRadius: '6px', lineHeight: '1.6' },
  '.cm-tooltip-autocomplete ul li[aria-selected]': {
    backgroundColor: 'var(--primary-light, color-mix(in srgb, var(--primary) 14%, transparent))',
    color: 'var(--primary)',
  },
  '.cm-completionDetail': { color: 'var(--text-hint)', fontStyle: 'normal', marginLeft: '8px' },
  '.cm-completionMatchedText': { textDecoration: 'none', fontWeight: '700' },
});
