import type {
  AttendanceIssue,
  AttendanceIssueType,
  AttendanceRequestStatus,
  AttendanceStatusCode,
  OfficialLeaveType,
} from '../../domain/types';
import { toCsv, type ExportTable } from '../export/tableExport';

/**
 * 출결 신청 — 예전 구글폼(예외 출결) 문항을 그대로 옮겼다. 서버 규칙은 lms_api/lms/attendance_requests.py 와 같다.
 */

export const IssueTypes: AttendanceIssueType[] = ['late', 'earlyLeave', 'outing', 'absent'];

export const IssueTypeLabels: Record<AttendanceIssueType, string> = {
  late: '지각',
  earlyLeave: '조퇴',
  outing: '외출',
  absent: '결석',
};

export const LeaveTypes: OfficialLeaveType[] = ['vacation', 'sick', 'interview', 'reserve', 'cert', 'other'];

export const LeaveTypeLabels: Record<OfficialLeaveType, string> = {
  vacation: '휴가',
  sick: '병가',
  interview: '면접',
  reserve: '예비군·민방위',
  cert: '자격증',
  other: '기타',
};

export const RequestStatusLabels: Record<AttendanceRequestStatus, string> = {
  submitted: '확인 대기',
  approved: '승인',
  rejected: '반려',
};

export const RequestStatusTones: Record<AttendanceRequestStatus, 'warning' | 'success' | 'error'> = {
  submitted: 'warning',
  approved: 'success',
  rejected: 'error',
};

/** 유형별로 받는 시각 칸 */
export function timeFieldsFor(type: AttendanceIssueType): { from?: string; to?: string } {
  switch (type) {
    case 'late':
      return { from: '입실 (예정) 시각' };
    case 'earlyLeave':
      return { from: '퇴실 시각' };
    case 'outing':
      return { from: '외출 시각', to: '복귀 시각' };
    default:
      return {};
  }
}

export interface AttendanceRequestDraft {
  id?: string;
  dateKey: string;
  issueType: AttendanceIssueType;
  timeFrom?: string;
  timeTo?: string;
  reason: string;
  officialLeaveUsed: boolean;
  officialLeaveType?: OfficialLeaveType;
  officialLeaveOther?: string;
  /** 고칠 때 붙어 있던 증빙을 뗀다 */
  removeEvidence?: boolean;
}

/** 서버 PAST_DAYS · FUTURE_DAYS 와 같다 */
export const REQUEST_PAST_DAYS = 31;
export const REQUEST_FUTURE_DAYS = 62;

function shiftDateKey(dateKey: string, days: number): string {
  const [y, m, d] = dateKey.split('-').map(Number);
  const moved = new Date(Date.UTC(y, m - 1, d + days));
  return moved.toISOString().slice(0, 10);
}

export function requestDateRange(today: string): { min: string; max: string } {
  return { min: shiftDateKey(today, -REQUEST_PAST_DAYS), max: shiftDateKey(today, REQUEST_FUTURE_DAYS) };
}

export const EVIDENCE_MAX_BYTES = 10 * 1024 * 1024;
export const EVIDENCE_ACCEPT = 'image/jpeg,image/png,image/gif,image/webp,image/heic,application/pdf';

/** 제출 전에 막을 것 — 서버도 같은 규칙으로 한 번 더 본다 */
export function draftError(draft: AttendanceRequestDraft, file?: File | null): string | null {
  if (draft.dateKey === '') return '발생일을 골라 주세요.';
  const fields = timeFieldsFor(draft.issueType);
  if (fields.from !== undefined && !draft.timeFrom) return `${fields.from}을 적어 주세요.`;
  if (fields.to !== undefined && !draft.timeTo) return `${fields.to}을 적어 주세요.`;
  if (draft.issueType === 'outing' && draft.timeFrom && draft.timeTo && draft.timeTo <= draft.timeFrom) {
    return '복귀 시각은 외출 시각보다 늦어야 합니다.';
  }
  if (draft.officialLeaveUsed && draft.officialLeaveType === undefined) return '공가 유형을 골라 주세요.';
  if (draft.officialLeaveUsed && draft.officialLeaveType === 'other' && !draft.officialLeaveOther?.trim()) {
    return '기타 공가 내용을 적어 주세요.';
  }
  if (draft.reason.trim() === '') return '사유를 적어 주세요.';
  if (draft.reason.length > 1000) return '사유는 1000자까지 적을 수 있습니다.';
  if (file && file.size > EVIDENCE_MAX_BYTES) return '증빙 파일은 10MB 이하만 올릴 수 있습니다.';
  return null;
}

function leaveName(type: string | undefined, other: string | undefined): string {
  if (type === 'other') return other || '기타';
  return LeaveTypeLabels[type as OfficialLeaveType] ?? type ?? '기타';
}

/** 서버 issue_label 과 같은 한 줄 요약 — 「조퇴 15:00 · 공가(병가)」 */
export function requestLabel(r: Pick<
  AttendanceIssue,
  'issueType' | 'timeFrom' | 'timeTo' | 'officialLeaveUsed' | 'officialLeaveType' | 'officialLeaveOther'
>): string {
  const base = IssueTypeLabels[r.issueType as AttendanceIssueType] ?? r.issueType;
  const time = r.timeFrom && r.timeTo ? ` ${r.timeFrom}~${r.timeTo}` : r.timeFrom ? ` ${r.timeFrom}` : '';
  const leave = r.officialLeaveUsed ? ` · 공가(${leaveName(r.officialLeaveType, r.officialLeaveOther)})` : '';
  return `${base}${time}${leave}`;
}

export function labelOf(r: AttendanceIssue): string {
  return r.label ?? requestLabel(r);
}

const STATUS_WEIGHT: Record<string, number> = { officialLeave: 5, absent: 4, earlyLeave: 3, late: 2, outing: 1 };

/** 승인하면 출석부에 들어갈 상태 — 같은 날 여러 건이면 가장 무거운 것 */
export function resultingStatus(requests: AttendanceIssue[]): AttendanceStatusCode | undefined {
  const statuses = requests.map((r) =>
    r.officialLeaveUsed ? 'officialLeave' : (IssueTypes as string[]).includes(r.issueType) ? r.issueType : undefined,
  );
  const best = statuses
    .filter((s): s is string => s !== undefined)
    .sort((a, b) => (STATUS_WEIGHT[b] ?? 0) - (STATUS_WEIGHT[a] ?? 0))[0];
  return best as AttendanceStatusCode | undefined;
}

function stamp(at: Date | undefined): string {
  if (at === undefined) return '';
  return at.toLocaleString('sv-SE', { timeZone: 'Asia/Seoul' }).slice(0, 16);
}

export function requestsTable(rows: AttendanceIssue[], nameOf: (uid: string) => string): ExportTable {
  const header = ['발생일', '이름', '유형', '시각', '공가', '사유', '증빙', '상태', '처리 메모', '제출 시각', '처리 시각'];
  const lines = rows.map((r) => [
    r.dateKey,
    nameOf(r.userId),
    IssueTypeLabels[r.issueType as AttendanceIssueType] ?? r.issueType,
    r.timeFrom && r.timeTo ? `${r.timeFrom}~${r.timeTo}` : (r.timeFrom ?? ''),
    r.officialLeaveUsed ? leaveName(r.officialLeaveType, r.officialLeaveOther) : '',
    r.reason ?? '',
    r.evidenceName ?? '',
    RequestStatusLabels[r.status],
    r.reviewComment ?? '',
    stamp(r.submittedAt),
    stamp(r.reviewedAt),
  ]);
  return { title: '출결 신청', header, rows: lines };
}

/** 엑셀에서 바로 열리게 BOM 을 붙인다 */
export function requestsToCsv(rows: AttendanceIssue[], nameOf: (uid: string) => string): string {
  return toCsv(requestsTable(rows, nameOf));
}
