import { useRef, useState, type FormEvent } from 'react';
import { useSearchParams } from 'react-router-dom';

import { cancelAttendanceRequest, submitAttendanceRequest, useMyAttendanceRequests } from '../../data/repository';
import { dateKeyOf } from '../../data/seed';
import type { AttendanceIssue, AttendanceIssueType, OfficialLeaveType } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import { Badge, Button, Card, Chip, Field, PageHeader, Row, Select, Spacer, TextArea, TextInput } from '../../ui/components';
import { formatDateTime } from '../../utils/format';
import { useCurrentUser } from '../auth/session';
import {
  EVIDENCE_ACCEPT,
  IssueTypeLabels,
  IssueTypes,
  LeaveTypeLabels,
  LeaveTypes,
  REQUEST_FUTURE_DAYS,
  REQUEST_PAST_DAYS,
  RequestStatusLabels,
  RequestStatusTones,
  draftError,
  labelOf,
  requestDateRange,
  timeFieldsFor,
  type AttendanceRequestDraft,
} from './attendanceRequest';
import './attendanceRequest.css';

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function emptyDraft(dateKey: string): AttendanceRequestDraft {
  return { dateKey, issueType: 'late', reason: '', officialLeaveUsed: false };
}

function draftOf(r: AttendanceIssue): AttendanceRequestDraft {
  return {
    id: r.id,
    dateKey: r.dateKey,
    issueType: (IssueTypes as string[]).includes(r.issueType) ? (r.issueType as AttendanceIssueType) : 'absent',
    timeFrom: r.timeFrom,
    timeTo: r.timeTo,
    reason: r.reason ?? '',
    officialLeaveUsed: r.officialLeaveUsed,
    officialLeaveType: (LeaveTypes as string[]).includes(r.officialLeaveType ?? '')
      ? (r.officialLeaveType as OfficialLeaveType)
      : r.officialLeaveUsed
        ? 'other'
        : undefined,
    officialLeaveOther: r.officialLeaveOther,
  };
}

/**
 * 출결 신청(학생) — 예전 구글폼 「예외 출결」을 옮긴 것.
 * 지각 · 조퇴 · 외출 · 결석(공가 포함)을 그날 신청하고, 매니저가 승인하면 출석부에 반영된다.
 */
export function AttendanceRequestScreen() {
  const user = useCurrentUser();
  const [params] = useSearchParams();
  const today = dateKeyOf(new Date());
  const initialDate = DATE_PATTERN.test(params.get('date') ?? '') ? String(params.get('date')) : today;

  const requests = useMyAttendanceRequests(user.uid);
  const [draft, setDraft] = useState<AttendanceRequestDraft>(() => emptyDraft(initialDate));
  const [file, setFile] = useState<File | null>(null);
  const [editing, setEditing] = useState<AttendanceIssue | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const formRef = useRef<HTMLFormElement | null>(null);

  const fields = timeFieldsFor(draft.issueType);
  const todayCount = requests.filter((r) => r.dateKey === today).length;
  const pending = requests.filter((r) => r.status === 'submitted').length;
  const rejected = requests.filter((r) => r.status === 'rejected');
  const { min: minDate, max: maxDate } = requestDateRange(today);
  const duplicate = requests.find(
    (r) => r.id !== draft.id && r.dateKey === draft.dateKey && r.issueType === draft.issueType,
  );

  const patch = (change: Partial<AttendanceRequestDraft>) => {
    setDraft((d) => ({ ...d, ...change }));
    setError(null);
  };

  const reset = (dateKey = today) => {
    setDraft(emptyDraft(dateKey));
    setFile(null);
    setEditing(undefined);
    setError(null);
    if (fileRef.current) fileRef.current.value = '';
  };

  const startEdit = (r: AttendanceIssue) => {
    setEditing(r);
    setDraft(draftOf(r));
    setFile(null);
    setDone(null);
    setError(null);
    if (fileRef.current) fileRef.current.value = '';
    formRef.current?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const clean: AttendanceRequestDraft = {
      ...draft,
      timeFrom: fields.from !== undefined ? draft.timeFrom : undefined,
      timeTo: fields.to !== undefined ? draft.timeTo : undefined,
      officialLeaveType: draft.officialLeaveUsed ? draft.officialLeaveType : undefined,
      officialLeaveOther: draft.officialLeaveUsed && draft.officialLeaveType === 'other' ? draft.officialLeaveOther : undefined,
    };
    const problem =
      draftError(clean, file) ??
      (clean.dateKey < minDate || clean.dateKey > maxDate
        ? `발생일은 ${minDate}부터 ${maxDate}까지 고를 수 있습니다.`
        : duplicate !== undefined
          ? `${duplicate.dateKey} ${IssueTypeLabels[draft.issueType]} 신청이 이미 있습니다. 아래 내역에서 그 신청을 고쳐 주세요.`
          : null);
    if (problem !== null) {
      setError(problem);
      return;
    }
    setSaving(true);
    setError(null);
    submitAttendanceRequest(clean, file, user)
      .then(() => {
        setDone(editing ? '신청을 고쳤습니다. 매니저 확인을 기다려 주세요.' : '신청했습니다. 매니저 확인을 기다려 주세요.');
        reset(clean.dateKey);
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : '신청하지 못했습니다.'))
      .finally(() => setSaving(false));
  };

  const cancel = (r: AttendanceIssue) => {
    if (!window.confirm(`${r.dateKey} ${labelOf(r)} 신청을 취소할까요?`)) return;
    cancelAttendanceRequest(r.id)
      .then(() => {
        if (editing?.id === r.id) reset();
        setDone('신청을 취소했습니다.');
      })
      .catch((err: unknown) => setError(err instanceof Error ? err.message : '취소하지 못했습니다.'));
  };

  return (
    <div className="admin-page attendance-request">
      <PageHeader
        title="출결 신청"
        description="정상 출석 외에 지각 · 조퇴 · 외출 · 결석(공가 포함)이 있으면 그날 신청해 주세요. 매니저가 확인하면 출석부에 반영됩니다."
      />

      <div className="attendance-request__summary">
        <span className={`count-chip${todayCount > 0 ? '' : ' count-chip--none'}`}>오늘 신청 {todayCount}건</span>
        <span className="count-chip">확인 대기 {pending}건</span>
      </div>

      {done !== null && (
        <div className="callout callout--success" role="status">
          {done}
        </div>
      )}

      {rejected.length > 0 && editing === undefined && (
        <div className="callout callout--warning">
          <Row>
            <span>
              반려된 신청이 {rejected.length}건 있습니다. 매니저 메모를 보고 고쳐서 다시 내 주세요.
            </span>
            <Spacer />
            <Button size="sm" variant="outline" onClick={() => startEdit(rejected[0])}>
              {rejected[0].dateKey} {labelOf(rejected[0])} 고치기
            </Button>
          </Row>
        </div>
      )}

      <Card>
        <form ref={formRef} className="attendance-request__form" onSubmit={submit} noValidate>
          <Row>
            <h2 className="section__title">{editing ? '신청 고치기' : '새 신청'}</h2>
            <Spacer />
            {editing && (
              <Button size="sm" variant="text" onClick={() => reset()}>
                고치기 그만
              </Button>
            )}
          </Row>
          {editing?.status === 'rejected' && (
            <div className="callout callout--warning">
              반려된 신청입니다{editing.reviewComment ? ` — ${editing.reviewComment}` : ''}. 고쳐서 내면 다시 확인 대기로 갑니다.
            </div>
          )}

          <div className="attendance-request__grid">
            <Field label="발생일" hint={`${REQUEST_PAST_DAYS}일 전부터 ${REQUEST_FUTURE_DAYS}일 뒤까지`}>
              <TextInput
                type="date"
                min={minDate}
                max={maxDate}
                value={draft.dateKey}
                onChange={(e) => patch({ dateKey: e.target.value })}
              />
            </Field>

            <div className="field">
              <span className="field__label">출결 유형</span>
              <div className="attendance-request__chips" role="radiogroup" aria-label="출결 유형">
                {IssueTypes.map((type) => (
                  <Chip key={type} selected={draft.issueType === type} onClick={() => patch({ issueType: type })}>
                    {IssueTypeLabels[type]}
                  </Chip>
                ))}
              </div>
            </div>

            {fields.from !== undefined && (
              <Field label={fields.from}>
                <TextInput type="time" value={draft.timeFrom ?? ''} onChange={(e) => patch({ timeFrom: e.target.value })} />
              </Field>
            )}
            {fields.to !== undefined && (
              <Field label={fields.to}>
                <TextInput type="time" value={draft.timeTo ?? ''} onChange={(e) => patch({ timeTo: e.target.value })} />
              </Field>
            )}
          </div>

          <div className="attendance-request__grid">
            <div className="field">
              <span className="field__label">공가 활용 여부</span>
              <div className="attendance-request__chips" role="radiogroup" aria-label="공가 활용 여부">
                <Chip selected={!draft.officialLeaveUsed} onClick={() => patch({ officialLeaveUsed: false })}>
                  미사용
                </Chip>
                <Chip selected={draft.officialLeaveUsed} onClick={() => patch({ officialLeaveUsed: true })}>
                  사용
                </Chip>
              </div>
            </div>
            {draft.officialLeaveUsed && (
              <Field label="공가 유형">
                <Select
                  value={draft.officialLeaveType ?? ''}
                  onChange={(e) => patch({ officialLeaveType: (e.target.value || undefined) as OfficialLeaveType | undefined })}
                >
                  <option value="">고르기</option>
                  {LeaveTypes.map((type) => (
                    <option key={type} value={type}>
                      {LeaveTypeLabels[type]}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            {draft.officialLeaveUsed && draft.officialLeaveType === 'other' && (
              <Field label="기타 공가 내용">
                <TextInput
                  value={draft.officialLeaveOther ?? ''}
                  maxLength={100}
                  placeholder="예: 가족 행사"
                  onChange={(e) => patch({ officialLeaveOther: e.target.value })}
                />
              </Field>
            )}
          </div>

          <Field label="사유" hint={`${draft.reason.length} / 1000`}>
            <TextArea
              rows={3}
              maxLength={1000}
              value={draft.reason}
              placeholder="예: 병원 진료로 오후 3시에 조퇴합니다."
              onChange={(e) => patch({ reason: e.target.value })}
            />
          </Field>

          <Field
            label="증빙 파일 (선택)"
            hint={
              editing?.evidenceName && !draft.removeEvidence && file === null
                ? `지금 붙어 있는 파일: ${editing.evidenceName} — 새로 고르면 바뀝니다.`
                : '진단서 · 면접 확인서 등 이미지나 PDF, 10MB 까지'
            }
          >
            <input
              ref={fileRef}
              className="input"
              type="file"
              accept={EVIDENCE_ACCEPT}
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setError(null);
              }}
            />
          </Field>
          {editing?.evidenceName && file === null && (
            <label className="checkbox">
              <input
                type="checkbox"
                checked={draft.removeEvidence === true}
                onChange={(e) => patch({ removeEvidence: e.target.checked })}
              />
              <span>붙어 있던 증빙 떼기</span>
            </label>
          )}

          {duplicate !== undefined && error === null && (
            <div className="callout callout--warning attendance-request__notice">
              {duplicate.dateKey} {IssueTypeLabels[draft.issueType]} 신청이 이미 있습니다
              ({RequestStatusLabels[duplicate.status]}).{' '}
              {duplicate.status === 'approved' ? (
                '승인된 신청은 고칠 수 없으니 바꿔야 하면 매니저에게 알려 주세요.'
              ) : (
                <button type="button" className="btn btn--text btn--sm" onClick={() => startEdit(duplicate)}>
                  그 신청 고치기
                </button>
              )}
            </div>
          )}

          {error !== null && (
            <p className="field__error" role="alert">
              {error}
            </p>
          )}

          <Row>
            <Spacer />
            <Button type="submit" disabled={saving}>
              {saving ? '보내는 중…' : editing ? '고쳐서 내기' : '신청하기'}
            </Button>
          </Row>
        </form>
      </Card>

      <section className="section">
        <h2 className="section__title">내 신청 내역</h2>
        {requests.length === 0 ? (
          <p className="muted">아직 낸 신청이 없습니다.</p>
        ) : (
          <ul className="attendance-request__list">
            {requests.map((r) => (
              <li key={r.id} className="attendance-request__item">
                <div className="attendance-request__item-head">
                  <strong>{r.dateKey}</strong>
                  <span>{labelOf(r)}</span>
                  <Badge tone={RequestStatusTones[r.status]}>{RequestStatusLabels[r.status]}</Badge>
                  <Spacer />
                  {r.status !== 'approved' && (
                    <>
                      <Button size="sm" variant="outline" onClick={() => startEdit(r)}>
                        고치기
                      </Button>
                      <Button size="sm" variant="text" onClick={() => cancel(r)}>
                        취소
                      </Button>
                    </>
                  )}
                </div>
                {r.status === 'approved' && (
                  <span className="hint">출석부에 반영됐습니다. 바꿔야 하면 매니저에게 알려 주세요.</span>
                )}
                {r.reason && <p className="attendance-request__reason">{r.reason}</p>}
                <div className="attendance-request__meta hint">
                  {r.submittedAt && <span>제출 {formatDateTime(r.submittedAt)}</span>}
                  {r.evidenceUrl && (
                    <a href={r.evidenceUrl} target="_blank" rel="noreferrer">
                      <Icon name="attach_file" size={16} />
                      {r.evidenceName ?? '증빙'}
                    </a>
                  )}
                  {r.reviewComment && <span>매니저 메모: {r.reviewComment}</span>}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
