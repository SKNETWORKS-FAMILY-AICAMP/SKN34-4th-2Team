import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { RoutePaths, adminFormTaskEditPath } from '../../app/routePaths';
import { deleteFormTask, saveFormTask, useFormResponses, useFormTasks, useStudents } from '../../data/repository';
import type { FormQuestion, FormQuestionType, FormResponse, FormTask, User } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import {
  Badge,
  Button,
  Card,
  Checkbox,
  Chip,
  Dialog,
  Field,
  PageHeader,
  Row,
  Select,
  Spacer,
  TabPage,
  Tabs,
  TextArea,
  TextInput,
  Toggle,
} from '../../ui/components';
import { formatDate, formatDateTime } from '../../utils/format';
import { useCurrentUser } from '../auth/session';
import { ExportMenu } from '../export/ExportMenu';
import {
  QuestionTypeIcons,
  QuestionTypeLabels,
  QuestionTypes,
  changeType,
  formatAnswer,
  newQuestion,
  questionsError,
  responsesTable,
  summarize,
  tidyQuestions,
} from './formSurvey';
import './forms.css';

const toInputDateTime = (d: Date) => {
  const pad = (v: number) => String(v).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

/** 설문 · 제출(관리자) — 목록, 누르면 제출 현황 · 질문별 결과 */
export function AdminFormTasksScreen() {
  const user = useCurrentUser();
  const tasks = useFormTasks();
  const responses = useFormResponses();
  const students = useStudents(user.cohortId).filter((s) => s.isActive);
  const navigate = useNavigate();
  const [detail, setDetail] = useState<FormTask | null>(null);
  const [error, setError] = useState<string | null>(null);

  const remove = (t: FormTask) => {
    const count = responses.filter((r) => r.taskId === t.id).length;
    const warn = count > 0 ? `\n제출한 ${count}명의 응답도 함께 지워집니다.` : '';
    if (!window.confirm(`「${t.title}」 설문을 지울까요?${warn}`)) return;
    setError(null);
    deleteFormTask(t.id).catch((err: unknown) => setError(err instanceof Error ? err.message : '지우지 못했습니다.'));
  };

  return (
    <TabPage
      title="설문 · 제출 관리"
      description="LMS 안에서 설문을 만들거나 외부 폼 링크를 등록하고, 학생별 제출과 응답을 확인합니다."
      actions={
        <Link className="btn btn--filled btn--md" to={RoutePaths.adminFormTasksCreate}>
          <Icon name="add" size={18} />
          설문 만들기
        </Link>
      }
    >
      {error && <p className="survey-admin__error">{error}</p>}
      {tasks.length === 0 ? (
        <div className="list-page__empty">
          <Icon name="assignment" size={44} />
          <p>등록된 설문이 없습니다</p>
        </div>
      ) : (
        <div className="list-page__body">
          {tasks.map((t) => {
            const count = responses.filter((r) => r.taskId === t.id).length;
            return (
              <div key={t.id} className="task-row">
                <button type="button" className="task-row__main" onClick={() => setDetail(t)}>
                  <span className="task-row__icon">
                    <Icon name={t.mode === 'builtin' ? 'fact_check' : 'open_in_new'} size={22} />
                  </span>
                  <span className="task-row__body">
                    <strong>{t.title}</strong>
                    <span className="hint">
                      {t.mode === 'builtin' ? `LMS 설문 · 질문 ${t.questions.length}개` : '외부 폼'} · 마감{' '}
                      {formatDate(t.dueAt)} · 제출 {count}
                      {students.length > 0 ? ` / ${students.length}명` : '명'}
                      {!t.published && ' · 비공개'}
                    </span>
                  </span>
                </button>
                <button type="button" className="icon-btn" aria-label="삭제" onClick={() => remove(t)}>
                  <Icon name="delete" size={20} />
                </button>
                <button
                  type="button"
                  className="icon-btn"
                  aria-label="수정"
                  onClick={() => navigate(adminFormTaskEditPath(t.id))}
                >
                  <Icon name="chevron_right" size={20} />
                </button>
              </div>
            );
          })}
        </div>
      )}

      {detail !== null && (
        <FormResultsDialog
          task={detail}
          responses={responses.filter((r) => r.taskId === detail.id)}
          students={students}
          onClose={() => setDetail(null)}
        />
      )}
    </TabPage>
  );
}

function FormResultsDialog({
  task,
  responses,
  students,
  onClose,
}: {
  task: FormTask;
  responses: FormResponse[];
  students: User[];
  onClose(): void;
}) {
  const builtin = task.mode === 'builtin';
  const [tab, setTab] = useState<'people' | 'questions'>(builtin ? 'questions' : 'people');
  const [open, setOpen] = useState<string | null>(null);
  const byUser = new Map(responses.map((r) => [r.userId, r]));
  const nameOf = (uid: string) => students.find((s) => s.uid === uid)?.displayName ?? byUser.get(uid)?.userDisplayName ?? uid;
  const missing = students.filter((s) => !byUser.has(s.uid)).length;

  const day = new Date().toLocaleDateString('sv-SE', { timeZone: 'Asia/Seoul' });

  return (
    <Dialog
      title={task.title}
      width={760}
      onClose={onClose}
      actions={
        <>
          <ExportMenu size="md" label="결과 내려받기" fileName={`${task.title}_${day}`} build={() => responsesTable(task, responses, students)} />
          <Spacer />
          <Button onClick={onClose}>닫기</Button>
        </>
      }
    >
      <p className="survey-admin__summary">
        제출 {responses.length}명 · 미제출 {missing}명 · 마감 {formatDateTime(task.dueAt)}
        {!builtin && ' · 외부 폼은 링크를 연 학생을 제출로 셉니다'}
      </p>
      {builtin && (
        <Tabs
          items={[
            { id: 'questions', label: '질문별 결과' },
            { id: 'people', label: '학생별 제출', count: responses.length },
          ]}
          active={tab}
          onChange={(id) => setTab(id as 'people' | 'questions')}
        />
      )}

      {tab === 'questions' && builtin ? (
        <div className="survey-results">
          {task.questions.map((q, i) => (
            <QuestionResult key={q.id} index={i} question={q} responses={responses} nameOf={nameOf} />
          ))}
        </div>
      ) : (
        <ul className="list survey-admin__people">
          {students.map((s) => {
            const r = byUser.get(s.uid);
            const expandable = builtin && r !== undefined;
            return (
              <li key={s.uid} className="survey-admin__person">
                <div className="list__item">
                  <span>{s.displayName}</span>
                  <Spacer />
                  {r === undefined ? (
                    <Badge tone="warning">미제출</Badge>
                  ) : (
                    <>
                      <span className="hint">{formatDateTime(r.submittedAt)}</span>
                      <Badge tone="success">제출</Badge>
                      {expandable && (
                        <button
                          type="button"
                          className="icon-btn"
                          aria-label={open === s.uid ? '응답 접기' : '응답 보기'}
                          onClick={() => setOpen(open === s.uid ? null : s.uid)}
                        >
                          <Icon name={open === s.uid ? 'expand_less' : 'expand_more'} size={20} />
                        </button>
                      )}
                    </>
                  )}
                </div>
                {expandable && open === s.uid && (
                  <dl className="survey-admin__answers">
                    {task.questions.map((q) => (
                      <div key={q.id}>
                        <dt>{q.title}</dt>
                        <dd>{formatAnswer(q, r.answers?.[q.id]) || '—'}</dd>
                      </div>
                    ))}
                  </dl>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Dialog>
  );
}

function QuestionResult({
  index,
  question,
  responses,
  nameOf,
}: {
  index: number;
  question: FormQuestion;
  responses: FormResponse[];
  nameOf(uid: string): string;
}) {
  const summary = summarize(question, responses);
  return (
    <section className="survey-result">
      <header className="survey-result__head">
        <strong>
          {index + 1}. {question.title}
        </strong>
        <span className="hint">
          {QuestionTypeLabels[question.type]} · 응답 {summary.answered}명
          {summary.kind === 'scale' && summary.average !== null && ` · 평균 ${summary.average}`}
        </span>
      </header>
      {summary.kind === 'text' ? (
        summary.texts.length === 0 ? (
          <p className="hint">아직 답이 없습니다.</p>
        ) : (
          <ul className="survey-result__texts">
            {summary.texts.map((t) => (
              <li key={t.userId}>
                <span className="survey-result__who">{nameOf(t.userId)}</span>
                <span>{t.text}</span>
              </li>
            ))}
          </ul>
        )
      ) : (
        <ul className="survey-result__bars">
          {summary.tallies.map((t) => {
            const pct = summary.answered === 0 ? 0 : Math.round((t.count / summary.answered) * 100);
            return (
              <li key={t.label}>
                <span className="survey-result__label">{t.label}</span>
                <span className="survey-result__track">
                  <span className="survey-result__fill" style={{ width: `${pct}%` }} />
                </span>
                <span className="survey-result__count">
                  {t.count}명 · {pct}%
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** 설문 만들기 · 고치기 — LMS 설문(질문 편집) 또는 외부 폼 링크 */
export function AdminFormTaskFormScreen() {
  const { taskId } = useParams<{ taskId: string }>();
  const existing = useFormTasks().find((t) => t.id === taskId);
  const responseCount = useFormResponses(taskId ?? '').length;
  const navigate = useNavigate();

  const [mode, setMode] = useState<FormTask['mode']>(existing?.mode ?? 'builtin');
  const [title, setTitle] = useState(existing?.title ?? '');
  const [description, setDescription] = useState(existing?.description ?? '');
  const [formUrl, setFormUrl] = useState(existing?.formUrl ?? '');
  const [questions, setQuestions] = useState<FormQuestion[]>(
    existing?.questions.length ? existing.questions : [newQuestion('short')],
  );
  const [guideUrl, setGuideUrl] = useState(existing?.notionGuideUrl ?? '');
  const [dueAt, setDueAt] = useState(toInputDateTime(existing?.dueAt ?? new Date(Date.now() + 7 * 86400000)));
  const [published, setPublished] = useState(existing?.published ?? true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const patch = (index: number, next: FormQuestion) =>
    setQuestions((prev) => prev.map((q, i) => (i === index ? next : q)));
  const move = (index: number, delta: number) =>
    setQuestions((prev) => {
      const target = index + delta;
      if (target < 0 || target >= prev.length) return prev;
      const next = [...prev];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });

  const save = () => {
    if (title.trim() === '') {
      setError('제목을 입력해 주세요.');
      return;
    }
    if (mode === 'builtin') {
      const problem = questionsError(questions);
      if (problem) {
        setError(problem);
        return;
      }
    } else if (!/^https?:\/\//.test(formUrl.trim())) {
      setError('폼 주소(https://…)를 입력해 주세요.');
      return;
    }
    const due = new Date(dueAt);
    if (Number.isNaN(due.getTime())) {
      setError('마감 일시를 입력해 주세요.');
      return;
    }
    setError(null);
    setSaving(true);
    saveFormTask({
      id: existing?.id ?? '',
      title: title.trim(),
      description: description.trim(),
      mode,
      formUrl: mode === 'external' ? formUrl.trim() : '',
      questions: mode === 'builtin' ? tidyQuestions(questions) : [],
      notionGuideUrl: guideUrl.trim() === '' ? undefined : guideUrl.trim(),
      dueAt: due,
      published,
      responseCount: existing?.responseCount ?? 0,
      createdAt: existing?.createdAt ?? new Date(),
    })
      .then(() => navigate(RoutePaths.adminFormTasks))
      .catch((err: unknown) => setError(err instanceof Error ? err.message : '저장하지 못했습니다.'))
      .finally(() => setSaving(false));
  };

  return (
    <div className="screen__inner survey-builder">
      <PageHeader title={existing === undefined ? '설문 만들기' : '설문 고치기'} />
      <Card>
        <Field label="방식">
          <Row>
            <Chip selected={mode === 'builtin'} onClick={() => setMode('builtin')}>
              LMS 설문(학생이 LMS 에서 답함)
            </Chip>
            <Chip selected={mode === 'external'} onClick={() => setMode('external')}>
              외부 폼 링크(구글폼 등)
            </Chip>
          </Row>
        </Field>
        <Field label="제목">
          <TextInput value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
        </Field>
        <Field label="설명">
          <TextArea rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        {mode === 'external' && (
          <Field label="폼 주소" hint="외부 폼은 학생이 링크를 열면 제출로 표시됩니다(실제 제출 여부는 알 수 없음).">
            <TextInput
              value={formUrl}
              onChange={(e) => setFormUrl(e.target.value)}
              placeholder="https://docs.google.com/forms/..."
            />
          </Field>
        )}
        <Field label="작성 가이드(노션, 선택)">
          <TextInput value={guideUrl} onChange={(e) => setGuideUrl(e.target.value)} placeholder="https://notion.so/..." />
        </Field>
        <Field label="마감 일시">
          <TextInput type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} />
        </Field>
        <Toggle checked={published} onChange={setPublished} label="학생에게 공개" />
      </Card>

      {mode === 'builtin' && (
        <>
          {existing?.mode === 'builtin' && responseCount > 0 && (
            <p className="survey-builder__warn">
              이미 {responseCount}명이 제출했습니다. 질문을 지우거나 보기 글자를 바꾸면 그 부분의 기존 응답은 결과에서
              빠집니다.
            </p>
          )}
          {questions.map((q, i) => (
            <QuestionEditor
              key={q.id}
              index={i}
              total={questions.length}
              question={q}
              onChange={(next) => patch(i, next)}
              onMove={(delta) => move(i, delta)}
              onRemove={() => setQuestions((prev) => prev.filter((_, j) => j !== i))}
            />
          ))}
          <div className="survey-builder__add">
            <span className="hint">질문 추가</span>
            {QuestionTypes.map((type) => (
              <Button
                key={type}
                variant="outline"
                size="sm"
                icon={<Icon name={QuestionTypeIcons[type]} size={16} />}
                onClick={() => setQuestions((prev) => [...prev, newQuestion(type)])}
              >
                {QuestionTypeLabels[type]}
              </Button>
            ))}
          </div>
        </>
      )}

      <div className="survey-builder__footer">
        {error && <p className="survey-admin__error">{error}</p>}
        <Spacer />
        <Button variant="outline" onClick={() => navigate(RoutePaths.adminFormTasks)}>
          취소
        </Button>
        <Button onClick={save} disabled={saving}>
          {saving ? '저장 중…' : '저장'}
        </Button>
      </div>
    </div>
  );
}

function QuestionEditor({
  index,
  total,
  question: q,
  onChange,
  onMove,
  onRemove,
}: {
  index: number;
  total: number;
  question: FormQuestion;
  onChange(next: FormQuestion): void;
  onMove(delta: number): void;
  onRemove(): void;
}) {
  const options = q.options ?? [];
  const setOption = (i: number, value: string) => onChange({ ...q, options: options.map((o, j) => (j === i ? value : o)) });

  return (
    <Card className="survey-editor">
      <div className="survey-editor__top">
        <span className="survey-q__no">{index + 1}</span>
        <TextInput
          className="survey-editor__title"
          value={q.title}
          maxLength={200}
          placeholder="질문 내용 (예: 관심 분야는 무엇인가요?)"
          aria-label={`${index + 1}번 질문 내용`}
          onChange={(e) => onChange({ ...q, title: e.target.value })}
        />
        <Select
          className="survey-editor__type"
          aria-label={`${index + 1}번 질문 종류`}
          value={q.type}
          onChange={(e) => onChange(changeType(q, e.target.value as FormQuestionType))}
        >
          {QuestionTypes.map((type) => (
            <option key={type} value={type}>
              {QuestionTypeLabels[type]}
            </option>
          ))}
        </Select>
      </div>
      <TextInput
        className="survey-editor__desc"
        value={q.description ?? ''}
        maxLength={500}
        placeholder="도움말(선택) — 질문 아래에 작은 글씨로 보입니다"
        aria-label={`${index + 1}번 질문 도움말`}
        onChange={(e) => onChange({ ...q, description: e.target.value })}
      />

      {(q.type === 'single' || q.type === 'multi') && (
        <div className="survey-editor__options">
          {options.map((option, i) => (
            <div key={i} className="survey-editor__option">
              <Icon name={q.type === 'single' ? 'radio_button_unchecked' : 'check_box_outline_blank'} size={18} />
              <TextInput
                value={option}
                maxLength={200}
                placeholder={`보기 ${i + 1}`}
                onChange={(e) => setOption(i, e.target.value)}
              />
              <button
                type="button"
                className="icon-btn"
                aria-label="보기 삭제"
                disabled={options.length <= 2}
                onClick={() => onChange({ ...q, options: options.filter((_, j) => j !== i) })}
              >
                <Icon name="close" size={18} />
              </button>
            </div>
          ))}
          <Button
            variant="text"
            size="sm"
            icon={<Icon name="add" size={16} />}
            onClick={() => onChange({ ...q, options: [...options, ''] })}
          >
            보기 추가
          </Button>
        </div>
      )}

      {q.type === 'scale' && (
        <div className="survey-editor__scale">
          <span className="hint">1 ~</span>
          <Select
            value={q.scaleMax ?? 5}
            onChange={(e) => onChange({ ...q, scaleMax: Number(e.target.value) })}
          >
            {[2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </Select>
          <TextInput
            value={q.minLabel ?? ''}
            maxLength={30}
            placeholder="1 의 뜻(예: 전혀 아님)"
            onChange={(e) => onChange({ ...q, minLabel: e.target.value || undefined })}
          />
          <TextInput
            value={q.maxLabel ?? ''}
            maxLength={30}
            placeholder="끝 점수의 뜻(예: 매우 그렇다)"
            onChange={(e) => onChange({ ...q, maxLabel: e.target.value || undefined })}
          />
        </div>
      )}

      <div className="survey-editor__bottom">
        <Checkbox checked={q.required} onChange={(required) => onChange({ ...q, required })} label="필수" />
        <Spacer />
        <button type="button" className="icon-btn" aria-label="위로" disabled={index === 0} onClick={() => onMove(-1)}>
          <Icon name="arrow_upward" size={18} />
        </button>
        <button
          type="button"
          className="icon-btn"
          aria-label="아래로"
          disabled={index === total - 1}
          onClick={() => onMove(1)}
        >
          <Icon name="arrow_downward" size={18} />
        </button>
        <button type="button" className="icon-btn" aria-label="질문 삭제" disabled={total <= 1} onClick={onRemove}>
          <Icon name="delete" size={18} />
        </button>
      </div>
    </Card>
  );
}
