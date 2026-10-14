import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { RoutePaths } from '../../app/routePaths';
import { submitFormResponse, useFormResponses, useFormTasks } from '../../data/repository';
import type { FormAnswer, FormQuestion } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { Button, Card, PageHeader, TextArea, TextInput } from '../../ui/components';
import { formatDate, formatDateTime, toTime } from '../../utils/format';
import { useCurrentUser } from '../auth/session';
import { LONG_MAX, SHORT_MAX, answersError, formatAnswer, type Answers } from './formSurvey';
import './forms.css';

/** LMS 설문 작성 — 마감 전이면 낸 뒤에도 고쳐서 다시 낼 수 있다 */
export function FormFillScreen() {
  const { taskId = '' } = useParams<{ taskId: string }>();
  const user = useCurrentUser();
  const task = useFormTasks().find((t) => t.id === taskId && t.published);
  const mine = useFormResponses(taskId).find((r) => r.userId === user.uid);
  const [answers, setAnswers] = useState<Answers>(() => ({ ...(mine?.answers ?? {}) }));
  const [error, setError] = useState<{ id?: string; message: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);

  if (task === undefined || task.mode !== 'builtin') {
    return (
      <div className="survey-page">
        <PageHeader title="설문" />
        <Card>
          <p className="survey-page__empty">
            {task === undefined ? '설문을 찾을 수 없습니다. 마감되었거나 비공개로 바뀌었을 수 있습니다.' : '이 설문은 외부 폼에서 작성합니다.'}
          </p>
          <Link className="btn btn--outline btn--md" to={RoutePaths.forms}>
            설문 목록으로
          </Link>
        </Card>
      </div>
    );
  }

  const closed = toTime(task.dueAt) < Date.now();
  const set = (id: string, value: FormAnswer | undefined) => {
    setAnswers((prev) => {
      const next = { ...prev };
      if (value === undefined) delete next[id];
      else next[id] = value;
      return next;
    });
    if (error?.id === id) setError(null);
  };

  const submit = () => {
    const problem = answersError(task.questions, answers);
    if (problem) {
      setError(problem);
      document.getElementById(`q-${problem.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    setSaving(true);
    setError(null);
    submitFormResponse(task, answers, user)
      .then(() => setDone(true))
      .catch((err: unknown) => setError({ message: err instanceof Error ? err.message : '제출하지 못했습니다.' }))
      .finally(() => setSaving(false));
  };

  if (done) {
    return (
      <div className="survey-page">
        <Card>
          <div className="survey-done">
            <Icon name="task_alt" size={40} />
            <strong>{mine ? '응답을 고쳤습니다' : '제출했습니다'}</strong>
            <p>마감({formatDate(task.dueAt)}) 전까지는 다시 열어 고칠 수 있습니다.</p>
            <Link className="btn btn--filled btn--md" to={RoutePaths.forms}>
              설문 목록으로
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="survey-page">
      <PageHeader title={task.title} description={task.description || undefined} />
      <div className="survey-page__meta">
        <span className={closed ? 'survey-page__due survey-page__due--over' : 'survey-page__due'}>
          <Icon name="schedule" size={15} />
          마감 {formatDateTime(task.dueAt)}
        </span>
        {mine?.submittedAt && <span>· {formatDateTime(mine.submittedAt)}에 제출함</span>}
        {task.notionGuideUrl && (
          <a className="survey-page__guide" href={task.notionGuideUrl} target="_blank" rel="noreferrer">
            <Icon name="menu_book" size={15} />
            작성 가이드
          </a>
        )}
      </div>

      {closed && (
        <p className="survey-page__notice">
          마감이 지나 더 낼 수 없습니다.{mine ? ' 아래는 제출한 응답입니다.' : ''}
        </p>
      )}

      {task.questions.map((q, i) => (
        <section key={q.id} id={`q-${q.id}`} className={`survey-q${error?.id === q.id ? ' survey-q--error' : ''}`}>
          <header className="survey-q__head">
            <span className="survey-q__no">{i + 1}</span>
            <strong>{q.title}</strong>
            {q.required && <span className="survey-q__req" aria-label="필수">*</span>}
          </header>
          {q.description && <p className="survey-q__desc">{q.description}</p>}
          {closed ? (
            <p className="survey-q__readonly">{formatAnswer(q, answers[q.id]) || '(답 없음)'}</p>
          ) : (
            <QuestionInput q={q} value={answers[q.id]} onChange={(v) => set(q.id, v)} />
          )}
          {error?.id === q.id && <p className="survey-q__error">{error.message}</p>}
        </section>
      ))}

      {!closed && (
        <div className="survey-page__actions">
          {error && error.id === undefined && <p className="survey-q__error">{error.message}</p>}
          <Link className="btn btn--outline btn--md" to={RoutePaths.forms}>
            취소
          </Link>
          <Button onClick={submit} disabled={saving}>
            {saving ? '제출 중…' : mine ? '고쳐서 다시 내기' : '제출'}
          </Button>
        </div>
      )}
    </div>
  );
}

function QuestionInput({
  q,
  value,
  onChange,
}: {
  q: FormQuestion;
  value: FormAnswer | undefined;
  onChange(value: FormAnswer | undefined): void;
}) {
  const name = `answer-${q.id}`;
  switch (q.type) {
    case 'short':
      return (
        <TextInput
          value={typeof value === 'string' ? value : ''}
          maxLength={SHORT_MAX}
          placeholder="답을 입력하세요"
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case 'long':
      return (
        <TextArea
          rows={5}
          value={typeof value === 'string' ? value : ''}
          maxLength={LONG_MAX}
          placeholder="답을 입력하세요"
          onChange={(e) => onChange(e.target.value)}
        />
      );
    case 'date':
      return (
        <TextInput
          type="date"
          className="survey-q__date"
          value={typeof value === 'string' ? value : ''}
          onChange={(e) => onChange(e.target.value || undefined)}
        />
      );
    case 'single':
      return (
        <div className="survey-q__options" role="radiogroup">
          {(q.options ?? []).map((option) => (
            <label key={option} className="survey-q__option">
              <input type="radio" name={name} checked={value === option} onChange={() => onChange(option)} />
              <span>{option}</span>
            </label>
          ))}
          {!q.required && value !== undefined && (
            <button type="button" className="survey-q__clear" onClick={() => onChange(undefined)}>
              선택 지우기
            </button>
          )}
        </div>
      );
    case 'multi': {
      const picked = Array.isArray(value) ? value : [];
      return (
        <div className="survey-q__options">
          {(q.options ?? []).map((option) => (
            <label key={option} className="survey-q__option">
              <input
                type="checkbox"
                checked={picked.includes(option)}
                onChange={(e) =>
                  onChange(e.target.checked ? [...picked, option] : picked.filter((p) => p !== option))
                }
              />
              <span>{option}</span>
            </label>
          ))}
        </div>
      );
    }
    case 'scale': {
      const max = q.scaleMax ?? 5;
      return (
        <div className="survey-scale">
          {q.minLabel && <span className="survey-scale__label">{q.minLabel}</span>}
          <div className="survey-scale__row" role="radiogroup">
            {Array.from({ length: max }, (_, i) => i + 1).map((n) => (
              <button
                key={n}
                type="button"
                role="radio"
                aria-checked={value === n}
                className={`survey-scale__btn${value === n ? ' survey-scale__btn--on' : ''}`}
                onClick={() => onChange(value === n && !q.required ? undefined : n)}
              >
                {n}
              </button>
            ))}
          </div>
          {q.maxLabel && <span className="survey-scale__label">{q.maxLabel}</span>}
        </div>
      );
    }
  }
}
