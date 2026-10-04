import { useDeferredValue, useRef, useState, type MutableRefObject, type ReactNode } from 'react';

import type { WebGrade } from '../../data/repository';
import type { PracticeAttempt, PracticeKind, PracticeProblem, PracticeReport, PracticeReportReason } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { CodeEditor } from './CodeEditor';
import { NotebookMarkdown } from './NotebookMarkdown';
import { OutputTable } from './OutputTable';
import { KIND_LABEL } from './practiceLabels';
import {
  gradeOutput,
  gradeReport,
  outputMatches,
  remainingBlanks,
  splitTests,
  type GradeReport,
  type TestStatus,
} from './practiceGrading';
import type { RunResult, TableData } from './pythonProtocol';
import { runJs } from './jsRunner';
import { HIDE_AT, REASON_LABEL } from './reports';
import { sqlSchema } from './sqlDialect';
import { expectedAsTable, gradeSql, parseExpected, sqlProblemSteps, type ExpectedTable } from './sqlGrading';
import type { TutorSnapshot } from './TutorContext';
import { gradeWebScript } from './webScriptGrader';

export { KIND_LABEL };

const KIND_HINT: Partial<Record<PracticeKind, string>> = {
  code_blank: '`__1__` 자리를 알맞은 식으로 바꾸고 채점하세요. 같은 결과를 내는 다른 식도 정답입니다.',
  code_fix: '먼저 실행해서 증상을 보고, 한 곳을 고친 뒤 채점하세요.',
  code_write: '함수를 완성하고 채점하세요. 실행해 보거나 아래 빈 셀에서 불러 시험해 봐도 됩니다.',
  code_scratch: '문제에 적힌 함수를 빈 칸에서부터 작성하세요. 이름이 같아야 채점됩니다. 막히면 「뼈대 받기」로 이름·인자를 받을 수 있어요.',
  sql_query: '예제 테이블에 조회문을 쓰고 채점하세요. 결과의 값·열 순서가 기대 결과와 같으면 정답이에요(열 이름은 안 봐요). 수업의 MySQL 문법 그대로 써도 돼요.',
  web_task: 'HTML · CSS 를 요구대로 고치고 채점하세요. 오른쪽 미리보기는 고칠 때마다 바뀌어요. 채점은 서버가 검사 항목마다 봐요.',
};
// sql_query 중 테이블 만들기(기대 결과에 확인 문장이 있는 것)
const DDL_HINT =
  '`CREATE TABLE` 문을 쓰고 채점하세요. 아래 확인 문장을 돌린 결과가 기대 결과와 같으면 정답이에요 — 제약을 어긴 행은 빠져야 해요. 수업의 MySQL 문법 그대로 써도 돼요.';

/** 이만큼 틀리면 모범답안을 볼 수 있게 한다 */
const REVEAL_AFTER_TRIES = 2;

type Line = { kind: 'out' | 'err' | 'sys'; text: string };

/**
 * 연습장 안의 문제 셀.
 *
 * - 실행: 노트북 세션에서 돈다. 여기서 만든 함수를 아래 빈 셀에서 불러 시험할 수 있다.
 * - 채점: 새 변수 공간에서 [학생 코드, 숨긴 테스트] 를 돌린다. 노트북의 다른 변수가 섞이지 않는다.
 */
export function ProblemCell({
  problem,
  number,
  code,
  attempt,
  note,
  myReport,
  onReport,
  onCodeChange,
  onAttempt,
  runInSession,
  grade,
  runSql,
  gradeSql: gradeSqlSteps,
  gradeWeb,
  onFocus,
  focusSignal,
  onRunAndNext,
  onAskTutor,
  tutorReader,
  markedLines,
}: {
  problem: PracticeProblem;
  number: number;
  code: string;
  attempt: PracticeAttempt | undefined;
  /** 머리에 덧붙일 글 — 다시 풀 문제의 원래 수업 */
  note?: string;
  /** 내가 이 문제에 남긴 「이상해요」 신고 */
  myReport?: PracticeReport;
  onReport?: (reason: PracticeReportReason, note: string) => void;
  onCodeChange: (code: string) => void;
  onAttempt: (passed: boolean) => void;
  runInSession: (code: string) => Promise<RunResult>;
  grade: (steps: string[]) => Promise<RunResult>;
  /** SQL 문제 — 실행(노트북 세션 DB) · 채점(새 DB). steps 는 문장 목록 JSON */
  runSql?: (steps: string[]) => Promise<RunResult>;
  gradeSql?: (steps: string[]) => Promise<RunResult>;
  /** 웹 실습 — 서버(jsdom)가 그 문제의 검사문으로 채점한다. 검사문은 브라우저에 없다 */
  gradeWeb?: (html: string) => Promise<WebGrade>;
  onFocus: () => void;
  focusSignal: number;
  onRunAndNext: () => void;
  /** 튜터 패널을 이 문제로 연다 */
  onAskTutor?: () => void;
  /** 튜터가 물을 때 읽을 지금 코드 · 출력 · 채점 — 여기서 채워 둔다 */
  tutorReader?: MutableRefObject<(() => TutorSnapshot) | null>;
  /** 튜터가 가리킨 줄 */
  markedLines?: number[];
}) {
  const [pick, setPick] = useState<number | null>(null);
  const [answer, setAnswer] = useState('');
  const [submitted, setSubmitted] = useState<boolean | null>(null);
  // 출력 예상 — 글자는 다르지만 값이 같아 맞힌 것(표기만 다름). 실제 출력을 같이 보여 준다
  const [looseMatch, setLooseMatch] = useState(false);
  const [lines, setLines] = useState<Line[]>([]);
  const [value, setValue] = useState<string | null>(null);
  const [table, setTable] = useState<TableData | null>(null);
  const [report, setReport] = useState<GradeReport | null>(null);
  const [working, setWorking] = useState<'run' | 'grade' | null>(null);
  const [showSolution, setShowSolution] = useState(false);
  const [reporting, setReporting] = useState(false);

  const tests = splitTests(problem.hiddenTests);
  const passed = attempt?.passed ?? false;
  const tries = attempt?.tries ?? 0;
  const canReveal = problem.referenceSolution !== '' && (passed || tries >= REVEAL_AFTER_TRIES);
  const isSql = problem.kind === 'sql_query';
  const isCode =
    problem.kind === 'code_blank' ||
    problem.kind === 'code_fix' ||
    problem.kind === 'code_write' ||
    problem.kind === 'code_scratch' ||
    isSql;
  const setupSql = problem.setupSql ?? '';
  const expected = isSql ? parseExpected(problem.expectedStdout) : null;
  // 테이블 만들기 문제 — 학생 CREATE TABLE 뒤에 확인 문장을 돌린다(sqlGrading.ts)
  const checkSql = expected?.after ?? '';
  const isWeb = problem.kind === 'web_task';
  // JS 코드 문제 — 파이썬과 같은 종류, 브라우저 Web Worker 에서 돈다(jsRunner.ts)
  const isJs = problem.packages?.length === 1 && problem.packages[0] === 'js';
  // 스크립트가 있는 웹 실습 — 브라우저 iframe 이 채점한다(webScriptGrader.ts). 서버 채점은 스크립트 없는 것만
  const isWebJs = isWeb && problem.packages?.length === 1 && problem.packages[0] === 'web-js';
  const codeLanguage = isSql ? 'sql' : isWeb ? 'html' : isJs ? 'javascript' : 'python';
  const [webReport, setWebReport] = useState<WebGrade | null>(null);
  // 미리보기는 칠 때마다 다시 그리지 않고 조금 늦춰 따라간다
  const preview = useDeferredValue(code);

  // 튜터는 물을 때 읽는다 — 그 사이 고친 코드 · 새 출력이 가야 한다
  const snapshot = useRef<TutorSnapshot>({ code: '', run: '', grade: '' });
  snapshot.current = {
    code: problem.kind === 'code_output' ? problem.starterCode : isCode || isWeb ? code : '',
    run: [
      ...lines.map((l) => l.text),
      ...(value !== null ? [`Out: ${value}`] : []),
      ...(table ? [`결과 ${table.shape[0]}행: ${table.columns.join(' | ')}`, ...table.rows.slice(0, 5).map((r) => r.join(' | '))] : []),
    ].join('\n'),
    grade: webReport
      ? `${webReport.passed ? '통과' : '실패'} · ${webReport.error || webReport.checks.map((c) => `${c.ok ? '✓' : '✗'} ${c.message}`).join(' / ')}`
      : report
      ? `${report.passed ? '통과' : '실패'} · ${report.headline}${report.detail ? `\n${report.detail}` : ''}`
      : submitted !== null
        ? `${submitted ? '정답' : '오답'} · 학생 답: ${problem.kind === 'concept' ? 'ABCD'[pick ?? 0] : answer}`
        : '',
  };
  if (tutorReader) tutorReader.current = () => snapshot.current;

  const run = async () => {
    if (working) return;
    setWorking('run');
    setLines([]);
    setValue(null);
    setTable(null);
    if (isSql) {
      await runSqlProblem();
      return;
    }
    const source = problem.kind === 'code_output' ? problem.starterCode : code;
    const r = isJs ? await runJs([source]) : await runInSession(source);
    const out: Line[] = r.stdout ? [{ kind: 'out', text: r.stdout.replace(/\n$/, '') }] : [];
    if (r.timedOut) out.push({ kind: 'err', text: '시간 제한에 걸려 멈췄어요.' });
    else if (r.stopped) out.push({ kind: 'err', text: '실행을 중단했어요.' });
    else if (r.error) {
      const blanks = r.error.type === 'NameError' && /__\d__/.test(r.error.message);
      out.push({
        kind: 'err',
        text: blanks ? '빈칸이 아직 남아 있어요.' : `${r.error.line ? `${r.error.line}번째 줄 · ` : ''}${r.error.type}: ${r.error.message}`,
      });
    } else if (!r.stdout && r.value === null) out.push({ kind: 'sys', text: '(출력 없음)' });
    setLines(out);
    setValue(r.value);
    setWorking(null);
  };

  /** SQL 문제 실행 — 예제 테이블을 다시 만들고 조회문을 돌려 표를 보인다 */
  const runSqlProblem = async () => {
    if (!runSql) return;
    const { steps, notes } = sqlProblemSteps(setupSql, code, checkSql);
    const r = await runSql(steps);
    const out: Line[] = notes.length ? [{ kind: 'sys', text: `MySQL 문법을 SQLite 에 맞췄어요 — ${notes.join(' · ')}` }] : [];
    if (r.stdout) out.push({ kind: 'out', text: r.stdout.replace(/\n$/, '') });
    if (r.timedOut) out.push({ kind: 'err', text: '시간 제한에 걸려 멈췄어요.' });
    else if (r.error) {
      const where = r.error.step === 0 ? '예제 테이블 · ' : checkSql && r.error.step === 2 ? '확인 문장 · ' : '';
      out.push({ kind: 'err', text: `${where}${r.error.type}: ${r.error.message}` });
    }
    setLines(out);
    setTable(r.table);
    setWorking(null);
  };

  const gradeCode = async () => {
    if (working) return;
    if (isSql) {
      if (!gradeSqlSteps || !expected) return;
      setWorking('grade');
      const r = await gradeSqlSteps(sqlProblemSteps(setupSql, code, checkSql).steps);
      const verdict = gradeSql(expected, r);
      setReport({ passed: verdict.passed, statuses: [], headline: verdict.headline, detail: verdict.detail });
      setTable(r.table);
      if (!r.stopped) onAttempt(verdict.passed);
      setWorking(null);
      return;
    }
    const left = remainingBlanks(code);
    if (problem.kind === 'code_blank' && left.length) {
      setReport({ passed: false, statuses: tests.map((): TestStatus => 'skip'), headline: `빈칸 ${left.join(', ')}이 남아 있어요`, detail: '' });
      return;
    }
    setWorking('grade');
    const r = isJs ? await runJs([code, problem.hiddenTests]) : await grade([code, problem.hiddenTests]);
    const next = gradeReport(tests, r);
    setReport(next);
    if (!r.stopped) onAttempt(next.passed);
    setWorking(null);
  };

  const submitChoice = () => {
    if (pick === null) return;
    const ok = pick === problem.answerIndex;
    setSubmitted(ok);
    onAttempt(ok);
  };

  const gradeWebCode = async () => {
    if (working || (!gradeWeb && !isWebJs)) return;
    setWorking('grade');
    try {
      const r = isWebJs ? await gradeWebScript(code, problem.hiddenTests) : await gradeWeb!(code);
      setWebReport(r);
      // 채점 자체를 못 했으면(서버 · 데모) 시도로 세지 않는다
      if (!r.error) onAttempt(r.passed);
    } catch {
      setWebReport({ passed: false, checks: [], error: '채점하지 못했어요. 잠시 후 다시 해 보세요.' });
    }
    setWorking(null);
  };

  const submitOutput = async () => {
    if (!answer.trim() || working) return;
    setWorking('grade');
    // JS 는 글자 그대로만 — 값 비교(ast.literal_eval)는 파이썬 표기용이다
    const verdict = isJs ? (outputMatches(answer, problem.expectedStdout) ? 'exact' : 'wrong') : await gradeOutput(answer, problem.expectedStdout, grade);
    setWorking(null);
    setLooseMatch(verdict === 'value');
    setSubmitted(verdict !== 'wrong');
    onAttempt(verdict !== 'wrong');
  };

  return (
    <div className={`pb${passed ? ' pb--passed' : ''}`}>
      <div className="pb__head">
        <span className="pb__num">문제 {number}</span>
        <span className="pb__kind">{KIND_LABEL[problem.kind]}{isJs || isWebJs ? ' · JavaScript' : ''}</span>
        <span className="pb__topic">{problem.topic}</span>
        {note && <span className="pb__note">{note}</span>}
        <span className="py-grow" />
        {passed ? (
          <span className="pb__state pb__state--ok">
            <Icon name="check_circle" size={16} fill />
            통과
          </span>
        ) : tries > 0 ? (
          <span className="pb__state pb__state--no">{tries}번 시도</span>
        ) : null}
        {onAskTutor && (
          <button type="button" className="pb__tutor" onClick={onAskTutor} title="힌트를 한 단계씩 받아요">
            <Icon name="school" size={15} />
            튜터에게 묻기
          </button>
        )}
        {onReport && (
          <button
            type="button"
            className={`pb__flag${myReport ? ' pb__flag--sent' : ''}`}
            onClick={() => setReporting((v) => !v)}
            aria-expanded={reporting}
            title={myReport ? '신고를 고치거나 다시 봅니다' : '문제가 이상하면 알려 주세요'}
          >
            <Icon name="flag" size={15} fill={Boolean(myReport)} />
            {myReport ? '신고했어요' : '이상해요'}
          </button>
        )}
      </div>

      {reporting && onReport && (
        <ReportForm
          number={number}
          current={myReport}
          onSend={(reason, memo) => {
            onReport(reason, memo);
            setReporting(false);
          }}
          onClose={() => setReporting(false)}
        />
      )}

      <div className="pb__prompt">
        <NotebookMarkdown source={problem.prompt} />
        {checkSql ? (
          <p className="pb__hint">{inlineHint(DDL_HINT)}</p>
        ) : (
          KIND_HINT[problem.kind] && <p className="pb__hint">{inlineHint(KIND_HINT[problem.kind]!)}</p>
        )}
        {isJs && <p className="pb__hint">JavaScript 로 풀어요. 「실행」하면 `console.log` 출력이 아래에 보여요.</p>}
        {isWebJs && <p className="pb__hint">미리보기에서 버튼을 눌러 보며 스크립트를 확인할 수 있어요. 채점은 이 브라우저에서 해요.</p>}
      </div>

      {isSql && <SqlProblemInfo number={number} setupSql={setupSql} expected={expected} />}

      {problem.kind === 'concept' && (
        <div className="pb__choices" role="radiogroup" aria-label={`문제 ${number} 보기`}>
          {problem.choices.map((choice, i) => {
            const decided = submitted !== null;
            const cls =
              decided && i === problem.answerIndex
                ? ' pb__choice--right'
                : decided && i === pick
                  ? ' pb__choice--wrong'
                  : i === pick
                    ? ' pb__choice--picked'
                    : '';
            return (
              <label key={i} className={`pb__choice${cls}`}>
                <input
                  type="radio"
                  name={`pb-${number}`}
                  checked={pick === i}
                  disabled={decided}
                  onChange={() => setPick(i)}
                />
                <span className="pb__choice-key">{'ABCD'[i]}</span>
                <NotebookMarkdown source={choice} />
              </label>
            );
          })}
          <div className="pb__actions">
            {submitted === null ? (
              <button type="button" className="btn btn--filled btn--sm" onClick={submitChoice} disabled={pick === null}>
                <Icon name="check" size={18} />
                정답 확인
              </button>
            ) : (
              <button type="button" className="btn btn--outline btn--sm" onClick={() => { setSubmitted(null); setPick(null); }}>
                다시 풀기
              </button>
            )}
          </div>
        </div>
      )}

      {problem.kind === 'code_output' && (
        <>
          <CodeEditor value={problem.starterCode} readOnly minLines={2} label={`문제 ${number} 코드`} markedLines={markedLines} language={codeLanguage} />
          <div className="pb__answer">
            <label htmlFor={`pb-answer-${number}`}>출력을 그대로 적어 보세요</label>
            <textarea
              id={`pb-answer-${number}`}
              value={answer}
              rows={2}
              spellCheck={false}
              readOnly={submitted !== null}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="예: 12"
            />
            <small>줄바꿈·띄어쓰기·대소문자까지 출력 그대로 적어요. 리스트·딕셔너리 같은 값은 쉼표 뒤 띄어쓰기·따옴표 종류가 달라도 돼요.</small>
          </div>
          <div className="pb__actions">
            {submitted === null ? (
              <button type="button" className="btn btn--filled btn--sm" onClick={submitOutput} disabled={!answer.trim() || working !== null}>
                <Icon name="check" size={18} />
                제출
              </button>
            ) : (
              <>
                <button type="button" className="btn btn--outline btn--sm" onClick={run} disabled={working !== null}>
                  <Icon name="play_arrow" size={18} />
                  실행해서 확인
                </button>
                <button type="button" className="btn btn--text btn--sm" onClick={() => { setSubmitted(null); setLooseMatch(false); setAnswer(''); setLines([]); }}>
                  다시 풀기
                </button>
              </>
            )}
            {submitted === null && <span className="pb__note">제출하면 실행해 볼 수 있어요</span>}
          </div>
        </>
      )}

      {isCode && (
        <>
          <CodeEditor
            value={code}
            onChange={onCodeChange}
            onRun={run}
            onRunAndNext={() => {
              run();
              onRunAndNext();
            }}
            onFocus={onFocus}
            focusSignal={focusSignal}
            markedLines={markedLines}
            minLines={3}
            label={`문제 ${number} 코드`}
            language={codeLanguage}
            sqlSchema={isSql ? () => sqlSchema([setupSql]) : undefined}
          />
          <div className="pb__actions">
            <button type="button" className="btn btn--outline btn--sm" onClick={run} disabled={working !== null}>
              <Icon name="play_arrow" size={18} />
              실행
            </button>
            <button type="button" className="btn btn--filled btn--sm" onClick={gradeCode} disabled={working !== null}>
              <Icon name={working === 'grade' ? 'hourglass_top' : 'task_alt'} size={18} />
              {working === 'grade' ? '채점 중…' : isSql ? '채점 · 결과 비교' : `채점 · 테스트 ${tests.length}개`}
            </button>
            <button
              type="button"
              className="btn btn--text btn--sm"
              onClick={() => { onCodeChange(problem.starterCode); setReport(null); setLines([]); setValue(null); }}
            >
              {problem.kind === 'code_scratch' ? '뼈대 받기' : '처음 코드로'}
            </button>
            {canReveal && (
              <button type="button" className="btn btn--text btn--sm" onClick={() => setShowSolution((v) => !v)}>
                {showSolution ? '모범답안 숨기기' : '모범답안 보기'}
              </button>
            )}
          </div>
        </>
      )}

      {isWeb && (
        <>
          {/* 셀 폭을 보고 나란히 둘지 위아래로 쌓을지 정한다(styles.css 의 컨테이너 쿼리) — 튜터가 열리면 셀이 좁아진다 */}
          <div className="pb-web">
            <div className="pb-web__grid">
              <CodeEditor
                value={code}
                onChange={(next) => {
                  onCodeChange(next);
                  setWebReport(null);
                }}
                onRun={gradeWebCode}
                onRunAndNext={onRunAndNext}
                onFocus={onFocus}
                focusSignal={focusSignal}
                markedLines={markedLines}
                minLines={8}
                label={`문제 ${number} HTML · CSS`}
                language="html"
              />
              <div className="pb-web__preview">
                <span className="pb-web__label">미리보기 · 고칠 때마다 바뀌어요</span>
                {/* sandbox 빈 값 — 학생이 쓴 <script> · 링크 이동 · 폼 보내기를 막는다. 채점은 서버가 따로 한다 */}
                {/* 스크립트 있는 문제는 눌러 볼 수 있게 allow-scripts 만 — 이 페이지(부모)에는 닿지 못한다 */}
                <iframe title={`문제 ${number} 미리보기`} sandbox={isWebJs ? 'allow-scripts' : ''} srcDoc={preview} />
              </div>
            </div>
          </div>
          <div className="pb__actions">
            <button type="button" className="btn btn--filled btn--sm" onClick={gradeWebCode} disabled={working !== null || (!gradeWeb && !isWebJs)}>
              <Icon name={working === 'grade' ? 'hourglass_top' : 'task_alt'} size={18} />
              {working === 'grade' ? '채점 중…' : '채점'}
            </button>
            <button
              type="button"
              className="btn btn--text btn--sm"
              onClick={() => {
                onCodeChange(problem.starterCode);
                setWebReport(null);
              }}
            >
              처음 코드로
            </button>
            {canReveal && (
              <button type="button" className="btn btn--text btn--sm" onClick={() => setShowSolution((v) => !v)}>
                {showSolution ? '모범답안 숨기기' : '모범답안 보기'}
              </button>
            )}
          </div>
        </>
      )}

      {webReport && (
        <Verdict
          ok={webReport.passed}
          title={
            webReport.error ||
            (webReport.passed
              ? `정답이에요 · 검사 ${webReport.checks.length}개 모두 통과`
              : `검사 ${webReport.checks.length}개 중 ${webReport.checks.filter((c) => c.ok).length}개 통과`)
          }
        >
          {webReport.checks.length > 0 && (
            <ul className="pb__tests">
              {webReport.checks.map((c, i) => (
                <li key={i} className={`pb__test pb__test--${c.ok ? 'pass' : 'fail'}`}>
                  <Icon name={c.ok ? 'check_circle' : 'cancel'} size={16} />
                  <span>{c.message}</span>
                </li>
              ))}
            </ul>
          )}
          {webReport.passed && <NotebookMarkdown source={problem.explanation} />}
          {!webReport.passed && !webReport.error && tries < REVEAL_AFTER_TRIES && problem.referenceSolution && (
            <p className="pb__muted">두 번 틀리면 모범답안을 볼 수 있어요.</p>
          )}
          <SourceLink files={problem.sourceFiles} />
        </Verdict>
      )}

      {(lines.length > 0 || value !== null || table) && (
        <div className="py-nb-out">
          {lines.map((l, i) => (
            <div key={i} className={`py-line--${l.kind}`}>
              {l.text}
            </div>
          ))}
          {value !== null && (
            <div className="py-nb-out__value">
              <span className="py-nb-out__label">Out</span>
              <span>{value}</span>
            </div>
          )}
          {table && <OutputTable table={table} label="내 결과" />}
        </div>
      )}

      {submitted !== null && (
        <Verdict ok={submitted} title={submitted ? '정답입니다' : problem.kind === 'concept' ? `정답은 ${'ABCD'[problem.answerIndex ?? 0]}입니다` : '다시 생각해 보세요'}>
          {problem.kind === 'code_output' && !submitted && (
            <p>
              내 답 <code>{answer.replace(/\n/g, ' ⏎ ')}</code> · 실행 결과 <code>{problem.expectedStdout.replace(/\n/g, ' ⏎ ')}</code>
            </p>
          )}
          {problem.kind === 'code_output' && submitted && looseMatch && (
            <p>
              값은 같고 표기만 달라요 · 실제 출력 <code>{problem.expectedStdout.replace(/\n/g, ' ⏎ ')}</code>
            </p>
          )}
          <NotebookMarkdown source={problem.explanation} />
          <SourceLink files={problem.sourceFiles} />
        </Verdict>
      )}

      {report && (
        <Verdict ok={report.passed} title={report.headline}>
          {report.detail && <p className="pb__detail">{report.detail}</p>}
          {tests.length > 0 && (
            <ul className="pb__tests">
              {tests.map((t, i) => (
                <li key={i} className={`pb__test pb__test--${report.statuses[i]}`}>
                  <Icon name={report.statuses[i] === 'pass' ? 'check_circle' : report.statuses[i] === 'fail' ? 'cancel' : 'remove_circle_outline'} size={16} />
                  <span>테스트 {i + 1}</span>
                  {report.statuses[i] === 'fail' && <code>{t.expr}</code>}
                  {report.statuses[i] === 'skip' && <span className="pb__muted">실행 안 함</span>}
                </li>
              ))}
            </ul>
          )}
          {report.passed && <NotebookMarkdown source={problem.explanation} />}
          {!report.passed && tries < REVEAL_AFTER_TRIES && problem.referenceSolution && (
            <p className="pb__muted">두 번 틀리면 모범답안을 볼 수 있어요.</p>
          )}
          <SourceLink files={problem.sourceFiles} />
        </Verdict>
      )}

      {showSolution && canReveal && (
        <div className="pb__solution">
          <span className="pb__muted">모범답안</span>
          <CodeEditor
            value={problem.referenceSolution}
            readOnly
            minLines={2}
            label={`문제 ${number} 모범답안`}
            language={codeLanguage}
          />
        </div>
      )}
    </div>
  );
}

/** SQL 문제 — 예제 테이블 이름 · 열, 펼쳐 보는 스크립트, (테이블 만들기면) 확인 문장, 기대 결과 표 */
function SqlProblemInfo({ number, setupSql, expected }: { number: number; setupSql: string; expected: ExpectedTable | null }) {
  const [open, setOpen] = useState(false);
  const tables = Object.entries(sqlSchema([setupSql]));
  const after = expected?.after ?? '';
  return (
    <div className="pb__sql">
      {tables.length > 0 && (
        <p className="pb__sql-tables">
          <Icon name="database" size={15} />
          <span>{after ? '미리 있는 테이블' : '예제 테이블'}</span>
          {tables.map(([name, cols]) => (
            <code key={name}>
              {name}({cols.join(', ')})
            </code>
          ))}
          <button type="button" className="btn btn--text btn--sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
            {open ? '스크립트 숨기기' : '스크립트 보기'}
          </button>
        </p>
      )}
      {open && <CodeEditor value={setupSql} readOnly minLines={2} label={`문제 ${number} 예제 테이블`} language="sql" />}
      {after && (
        <>
          <p className="pb__sql-tables">
            <Icon name="fact_check" size={15} />
            <span>채점할 때 내 테이블에 이 문장을 돌려요</span>
          </p>
          <CodeEditor value={after} readOnly minLines={2} label={`문제 ${number} 확인 문장`} language="sql" />
        </>
      )}
      {expected && (
        <OutputTable
          table={expectedAsTable(expected)}
          label={after ? '확인 문장의 결과가 이렇게 나와야 해요' : expected.ordered ? '기대 결과 (순서도 같아야 해요)' : '기대 결과'}
        />
      )}
    </div>
  );
}

/** 「이 문제 이상해요」 — 이유 하나 고르고 한 줄 덧붙인다. 한 사람 한 번, 다시 보내면 고쳐진다. */
function ReportForm({
  number,
  current,
  onSend,
  onClose,
}: {
  number: number;
  current: PracticeReport | undefined;
  onSend: (reason: PracticeReportReason, note: string) => void;
  onClose: () => void;
}) {
  const [reason, setReason] = useState<PracticeReportReason>(current?.reason ?? 'unclear');
  const [memo, setMemo] = useState(current?.note ?? '');
  const reasons = Object.keys(REASON_LABEL) as PracticeReportReason[];
  return (
    <form
      className="pb__report"
      onSubmit={(e) => {
        e.preventDefault();
        onSend(reason, memo.trim());
      }}
    >
      <p className="pb__report-title">
        <Icon name="flag" size={16} />
        문제 {number}, 어디가 이상한가요?
      </p>
      <div className="pb__report-reasons" role="radiogroup" aria-label="신고 이유">
        {reasons.map((r) => (
          <label key={r} className={`pb__report-reason${reason === r ? ' pb__report-reason--on' : ''}`}>
            <input type="radio" name={`pb-report-${number}`} checked={reason === r} onChange={() => setReason(r)} />
            {REASON_LABEL[r]}
          </label>
        ))}
      </div>
      <input
        type="text"
        value={memo}
        maxLength={120}
        onChange={(e) => setMemo(e.target.value)}
        placeholder="한 줄 덧붙이기 (선택)"
        aria-label="신고 메모"
      />
      <div className="pb__actions">
        <button type="submit" className="btn btn--filled btn--sm">
          <Icon name="send" size={16} />
          {current ? '신고 고치기' : '보내기'}
        </button>
        <button type="button" className="btn btn--text btn--sm" onClick={onClose}>
          닫기
        </button>
        <span className="pb__muted">{HIDE_AT}명이 신고하면 잠시 숨기고 강사가 확인해요. 채점에는 영향이 없어요.</span>
      </div>
    </form>
  );
}

function Verdict({ ok, title, children }: { ok: boolean; title: string; children?: ReactNode }) {
  return (
    <div className={`pb__verdict pb__verdict--${ok ? 'ok' : 'no'}`} role="status">
      <Icon name={ok ? 'check_circle' : 'cancel'} size={20} fill />
      <div>
        <strong>{title}</strong>
        {children}
      </div>
    </div>
  );
}

function SourceLink({ files }: { files: string[] }) {
  if (!files.length) return null;
  return (
    <p className="pb__source">
      <Icon name="description" size={14} />
      근거: {files.map((f) => f.split('/').pop()).join(', ')}
    </p>
  );
}

/** 힌트 안의 `코드` 만 칠한다 */
function inlineHint(text: string) {
  return text.split(/(`[^`]+`)/).map((part, i) => (part.startsWith('`') ? <code key={i}>{part.slice(1, -1)}</code> : part));
}
