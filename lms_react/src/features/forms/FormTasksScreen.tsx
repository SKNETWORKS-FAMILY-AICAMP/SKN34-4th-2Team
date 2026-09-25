import { markFormResponded, useFormResponses, useFormTasks } from '../../data/repository';
import { toTime } from '../../utils/format';
import type { FormTask } from '../../domain/types';
import { StudentTargets } from '../../tour/targets';
import { useTourTarget } from '../../tour/useTourTarget';
import { Icon } from '../../ui/Icon';
import { PageHeader } from '../../ui/components';
import { formatDate } from '../../utils/format';
import { useCurrentUser } from '../auth/session';

/**
 * 설문 · 제출 — features/forms/presentation/form_tasks_screen.dart
 *
 * 머리글이 없다. 좁은 한 줄기(520px)로 「해야 할 설문」과 「제출 완료」가 차례로 선다.
 * 카드 하나에 구글폼으로 가는 문과 노션 가이드가 붙는다.
 */
const DAY = 24 * 60 * 60 * 1000;

export function FormTasksScreen() {
  const user = useCurrentUser();
  const tasks = useFormTasks().filter((t) => t.published);
  const responses = useFormResponses();
  const ref = useTourTarget(StudentTargets.navForms);

  const isDone = (task: FormTask) =>
    responses.some((r) => r.taskId === task.id && r.userId === user.uid);

  // 마감이 지난 미제출 설문은 보이지 않는다 — 더 낼 수 없어 목록만 덮는다(대시보드와 같은 기준)
  const pending = tasks.filter((t) => !isDone(t) && toTime(t.dueAt) >= Date.now());
  const done = tasks.filter((t) => isDone(t));

  return (
    <div className="form-page" ref={ref}>
      <PageHeader title="설문 · 제출" description="기수에서 요청한 설문과 과제를 기한 안에 제출하세요." />
      {pending.length === 0 && done.length === 0 ? (
        <p className="form-page__empty">지금 제출할 설문·과제가 없습니다.</p>
      ) : (
        <div className="form-page__column">
          {pending.length > 0 && (
            <>
              <h2 className="form-page__label">해야 할 설문</h2>
              {pending.map((task) => (
                <FormTaskCard key={task.id} task={task} done={false} />
              ))}
            </>
          )}
          {done.length > 0 && (
            <>
              <h2 className="form-page__label">제출 완료</h2>
              {done.map((task) => (
                <FormTaskCard key={task.id} task={task} done />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

/** widgets/form_task_card.dart */
function FormTaskCard({ task, done }: { task: FormTask; done: boolean }) {
  const dueMs = toTime(task.dueAt);
  const overdue = !done && dueMs < Date.now();
  const remaining = Math.max(0, Math.ceil((dueMs - Date.now()) / DAY));
  const tone = done ? 'ok' : overdue ? 'bad' : 'wait';
  const label = done ? '제출 완료' : overdue ? '마감' : '미제출';
  const user = useCurrentUser();

  return (
    <article className="form-card">
      <header className="form-card__head">
        <div>
          <strong className="form-card__title">{task.title}</strong>
          {task.description !== '' && (
            <p className="form-card__desc" title={task.description}>
              {task.description}
            </p>
          )}
        </div>
        <span className={`form-chip form-chip--${tone}`}>{label}</span>
      </header>

      <p className={`form-card__due${overdue ? ' form-card__due--over' : ''}`}>
        <Icon name="schedule" size={14} />
        마감 {formatDate(task.dueAt)}
        {/* 마감이 지났으면 D-날짜는 뺀다 — 원본은 0 으로 막아 「D-0」이 남았다. 오른쪽 「마감」 표시로 충분하다 */}
        {!done && !overdue && ` · D-${remaining}`}
      </p>

      <div className="form-card__actions">
        <a
          className="btn btn--filled btn--sm"
          href={task.formUrl}
          target="_blank"
          rel="noreferrer"
          onClick={() => {
            if (!done) markFormResponded(task.id, user);
          }}
        >
          <Icon name="description" size={16} />
          구글폼 작성
        </a>
        {task.notionGuideUrl !== undefined && task.notionGuideUrl !== '' && (
          <a
            className="btn btn--outline btn--sm"
            href={task.notionGuideUrl}
            target="_blank"
            rel="noreferrer"
          >
            <Icon name="menu_book" size={16} />
            노션 가이드
          </a>
        )}
      </div>
    </article>
  );
}
