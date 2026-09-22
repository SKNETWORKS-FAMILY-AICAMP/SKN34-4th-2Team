import { markFormResponded, useFormResponses, useFormTasks } from '../../data/repository';
import { toTime } from '../../utils/format';
import type { FormTask } from '../../domain/types';
import { StudentTargets } from '../../tour/targets';
import { useTourTarget } from '../../tour/useTourTarget';
import { Icon } from '../../ui/Icon';
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

  const pending = tasks.filter((t) => !isDone(t));
  const done = tasks.filter((t) => isDone(t));

  return (
    <div className="form-page" ref={ref}>
      {tasks.length === 0 ? (
        <p className="form-page__empty">등록된 설문·제출 과제가 없습니다.</p>
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
          {task.description !== '' && <p className="form-card__desc">{task.description}</p>}
        </div>
        <span className={`form-chip form-chip--${tone}`}>{label}</span>
      </header>

      <p className={`form-card__due${overdue ? ' form-card__due--over' : ''}`}>
        <Icon name="schedule" size={14} />
        마감 {formatDate(task.dueAt)}
        {!done && ` · D-${remaining}`}
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
