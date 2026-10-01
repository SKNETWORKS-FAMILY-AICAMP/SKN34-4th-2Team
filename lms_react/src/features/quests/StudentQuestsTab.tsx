import { useState } from 'react';

import { submitQuest, uploadRecordEvidence, useQuests, type UploadedEvidence } from '../../data/repository';
import { readApiError } from '../../data/http';
import type { Quest, QuestSubmission } from '../../domain/types';
import { Badge, Button, Dialog, EmptyState, Field, TextArea, TextInput } from '../../ui/components';
import { formatMileage } from '../../utils/format';
import { useCurrentUser } from '../auth/session';
import { EVIDENCE_LABEL, STATUS_LABEL, STATUS_TONE, periodLabel } from './questLabels';

const MAX_FILES = 5;

/** 기록실의 「추가 마일리지 미션」 — 관리자가 만든 미션과 내 제출 상태. 열린 미션이 없으면 감춘다 */
export function StudentQuestsTab() {
  const user = useCurrentUser();
  const { data, isLoading, isError } = useQuests(user.cohortId);
  const [submitting, setSubmitting] = useState<Quest | null>(null);
  const [flash, setFlash] = useState('');

  if (isLoading) return null;
  if (isError || data === undefined) return <p className="field__error quest__pad">마일리지 미션을 불러오지 못했습니다.</p>;

  const mine = data.submissions ?? [];
  const quests = data.quests.filter((q) => q.open || mine.some((s) => s.questId === q.id));
  const earned = mine.reduce((sum, s) => sum + s.grantedAmount, 0);
  if (quests.length === 0 && flash === '') return null;

  return (
    <section className="quest-student">
      <p className="quest-student__summary">
        <strong>추가 마일리지 미션</strong> · 받은 마일리지 <strong>{formatMileage(earned)}</strong>
      </p>
      {flash !== '' && <p className="quest-student__flash">{flash}</p>}
      {quests.length === 0 ? (
        <EmptyState message="지금 참여할 수 있는 미션이 없습니다." />
      ) : (
        <ul className="quest-list">
          {quests.map((q) => {
            const subs = mine.filter((s) => s.questId === q.id);
            const approved = subs.filter((s) => s.status === 'approved').length;
            const pending = subs.some((s) => s.status === 'pending');
            const full = approved >= q.maxCompletions;
            const last: QuestSubmission | undefined = subs[0];
            return (
              <li key={q.id} className="quest-card">
                <header className="quest-card__head">
                  <strong>{q.title}</strong>
                  <span className="quest-card__reward">+{formatMileage(q.reward)}</span>
                </header>
                {q.description !== '' && <p className="quest-card__desc">{q.description}</p>}
                <p className="hint">
                  {periodLabel(q)} · 인증 {EVIDENCE_LABEL[q.evidenceType]} · 완료 {approved}/{q.maxCompletions}회
                  {q.approval === 'auto' ? ' · 제출 즉시 지급' : ' · 승인 후 지급'}
                </p>
                {last !== undefined && (
                  <p className="quest-card__status">
                    <Badge tone={STATUS_TONE[last.status]}>{STATUS_LABEL[last.status]}</Badge>
                    {last.status === 'rejected' && last.reviewComment !== '' && (
                      <span className="hint">사유: {last.reviewComment}</span>
                    )}
                  </p>
                )}
                <div className="quest-card__actions">
                  {full ? (
                    <Badge tone="success">모두 완료</Badge>
                  ) : pending ? (
                    <Button size="sm" variant="outline" disabled>
                      검토 중
                    </Button>
                  ) : q.open ? (
                    <Button size="sm" onClick={() => setSubmitting(q)}>
                      {q.evidenceType === 'none' ? '완료하기' : '인증 제출'}
                    </Button>
                  ) : (
                    <Badge tone="neutral">마감</Badge>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {submitting !== null && (
        <SubmitDialog
          quest={submitting}
          onClose={() => setSubmitting(null)}
          onDone={(s) => {
            setSubmitting(null);
            setFlash(
              s.grantedAmount > 0
                ? `"${submitting.title}" 완료! ${formatMileage(s.grantedAmount)}이 적립되었습니다.`
                : `"${submitting.title}" 인증을 제출했습니다. 승인되면 마일리지가 적립됩니다.`,
            );
          }}
        />
      )}
    </section>
  );
}

function SubmitDialog({
  quest,
  onClose,
  onDone,
}: {
  quest: Quest;
  onClose(): void;
  onDone(submission: QuestSubmission): void;
}) {
  const [text, setText] = useState('');
  const [link, setLink] = useState('');
  const [files, setFiles] = useState<UploadedEvidence[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const upload = async (list: FileList | null) => {
    if (list === null) return;
    setBusy(true);
    setError('');
    try {
      const picked = Array.from(list).slice(0, MAX_FILES - files.length);
      const uploaded: UploadedEvidence[] = [];
      for (const file of picked) uploaded.push(await uploadRecordEvidence(file));
      setFiles((current) => [...current, ...uploaded]);
    } catch (e) {
      setError(await readApiError(e));
    } finally {
      setBusy(false);
    }
  };

  const submit = async () => {
    setBusy(true);
    setError('');
    try {
      onDone(await submitQuest(quest.id, { text, link, fileKeys: files.map((f) => f.key) }));
    } catch (e) {
      setError(await readApiError(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      title={quest.title}
      onClose={onClose}
      width={520}
      actions={
        <>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            취소
          </Button>
          <Button onClick={() => void submit()} disabled={busy}>
            {busy ? '처리 중…' : quest.evidenceType === 'none' ? '완료하기' : '제출'}
          </Button>
        </>
      }
    >
      {quest.description !== '' && <p className="quest-card__desc">{quest.description}</p>}
      {quest.evidenceType === 'text' && (
        <Field label="인증 내용">
          <TextArea rows={5} maxLength={3000} value={text} onChange={(e) => setText(e.target.value)} />
        </Field>
      )}
      {quest.evidenceType === 'link' && (
        <Field label="인증 링크" hint="https:// 로 시작하는 주소">
          <TextInput value={link} maxLength={500} onChange={(e) => setLink(e.target.value)} />
        </Field>
      )}
      {quest.evidenceType === 'file' && (
        <Field label="인증 사진 · 파일" hint={`이미지나 PDF, 10MB 이하 · 최대 ${MAX_FILES}개`}>
          <input
            type="file"
            accept="image/*,application/pdf"
            multiple
            disabled={busy || files.length >= MAX_FILES}
            onChange={(e) => void upload(e.target.files)}
          />
          {files.length > 0 && (
            <ul className="quest-files">
              {files.map((f) => (
                <li key={f.key}>
                  {f.name}
                  <button
                    type="button"
                    className="icon-btn"
                    aria-label={`${f.name} 빼기`}
                    onClick={() => setFiles((current) => current.filter((x) => x.key !== f.key))}
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Field>
      )}
      {quest.evidenceType === 'none' && <p>완료하기를 누르면 바로 처리됩니다.</p>}
      {error !== '' && <p className="field__error">{error}</p>}
    </Dialog>
  );
}
