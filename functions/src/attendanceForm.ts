import * as logger from "firebase-functions/logger";

import {db, fieldValue} from "./firebase";

export interface AttendanceAnswers {
  name: string;
  dateKey: string;
  attendanceTypeRaw: string;
  officialLeaveUsed: boolean;
  officialLeaveType: string | null;
  officialLeaveOther: string | null;
  formAttendanceType: string | null;
}

function compact(title: string): string {
  return title.replace(/\s+/g, "");
}

function answerByTitle(
  answers: Record<string, unknown> | undefined,
  needles: string[],
): string {
  if (!answers) return "";
  for (const [title, value] of Object.entries(answers)) {
    const key = compact(title);
    if (needles.some((n) => key.includes(compact(n)))) {
      if (Array.isArray(value)) return value.map(String).join(", ").trim();
      return String(value ?? "").trim();
    }
  }
  return "";
}

export function parseDateKey(raw: string): string | null {
  const t = raw.trim();
  const iso = t.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})/);
  if (iso) {
    const y = iso[1];
    const m = iso[2].padStart(2, "0");
    const d = iso[3].padStart(2, "0");
    return `${y}-${m}-${d}`;
  }
  const date = new Date(t);
  if (!Number.isNaN(date.getTime())) {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }
  return null;
}

export function mapAttendanceType(raw: string): string | null {
  if (raw.includes("지각")) return "late";
  if (raw.includes("조퇴")) return "earlyLeave";
  if (raw.includes("외출")) return "outing";
  if (raw.includes("결석")) return "absent";
  return null;
}

export function mapOfficialLeaveType(raw: string): {
  type: string | null;
  other: string | null;
} {
  if (!raw) return {type: null, other: null};
  if (raw.includes("휴가")) return {type: "vacation", other: null};
  if (raw.includes("병가")) return {type: "sick", other: null};
  if (raw.includes("면접")) return {type: "interview", other: null};
  if (raw.includes("예비군") || raw.includes("민방위")) {
    return {type: "reserve", other: null};
  }
  if (raw.includes("자격증")) return {type: "cert", other: null};
  if (raw.includes("기타")) {
    const extra = raw.replace(/^기타[:：\s]*/, "").trim();
    return {type: "other", other: extra || raw};
  }
  return {type: "other", other: raw};
}

export function parseAttendanceAnswers(
  answers: Record<string, unknown> | undefined,
): AttendanceAnswers {
  const name = answerByTitle(answers, ["이름"]);
  const dateRaw = answerByTitle(answers, ["발생일"]);
  const typeRaw = answerByTitle(answers, ["출석 유형", "출석유형"]);
  const leaveUsedRaw = answerByTitle(answers, [
    "공가 활용 여부",
    "공가활용여부",
  ]);
  const leaveTypeRaw = answerByTitle(answers, ["공가 유형", "공가유형"]);
  const leave = mapOfficialLeaveType(leaveTypeRaw);

  const compactUsed = leaveUsedRaw.replace(/\s+/g, "");
  const officialLeaveUsed =
    compactUsed === "사용" ||
    (compactUsed.includes("사용") && !compactUsed.includes("미사용"));

  return {
    name,
    dateKey: parseDateKey(dateRaw) ?? "",
    attendanceTypeRaw: typeRaw,
    officialLeaveUsed,
    officialLeaveType: leave.type,
    officialLeaveOther: leave.other,
    formAttendanceType: mapAttendanceType(typeRaw),
  };
}

export function resolveStatusFromForm(parsed: AttendanceAnswers): string | null {
  if (!parsed.formAttendanceType && !parsed.officialLeaveUsed) return null;
  if (parsed.officialLeaveUsed) return "officialLeave";
  return parsed.formAttendanceType;
}

export function hasAttendanceAnswers(
  answers: Record<string, unknown> | undefined,
): boolean {
  const parsed = parseAttendanceAnswers(answers);
  return Boolean(parsed.formAttendanceType || parsed.officialLeaveUsed);
}

export async function findStudentForAttendance(opts: {
  cohortId: string;
  email?: string;
  name?: string;
}): Promise<FirebaseFirestore.QueryDocumentSnapshot | FirebaseFirestore.DocumentSnapshot | null> {
  const email = (opts.email ?? "").trim().toLowerCase();
  if (email) {
    const byPersonal = await db
      .collection("users")
      .where("personalEmail", "==", email)
      .limit(5)
      .get();
    const personal = byPersonal.docs.find(
      (d) => d.data()?.cohortId === opts.cohortId,
    );
    if (personal) return personal;

    const byLogin = await db
      .collection("users")
      .where("email", "==", email)
      .limit(5)
      .get();
    const login = byLogin.docs.find(
      (d) => d.data()?.cohortId === opts.cohortId,
    );
    if (login) return login;
  }

  const name = (opts.name ?? "").trim();
  if (name && opts.cohortId) {
    const byName = await db
      .collection("users")
      .where("cohortId", "==", opts.cohortId)
      .where("displayName", "==", name)
      .limit(5)
      .get();
    const students = byName.docs.filter(
      (d) => d.data()?.role === "student" || !d.data()?.role,
    );
    if (students.length === 1) return students[0];
    if (students.length > 1) {
      logger.warn("Attendance form: ambiguous displayName", {
        name,
        cohortId: opts.cohortId,
        count: students.length,
      });
    }
  }

  return null;
}

export async function applyAttendanceFromForm(opts: {
  cohortId: string;
  userId: string;
  userDisplayName: string;
  parsed: AttendanceAnswers;
  responseId?: string;
  answers?: Record<string, unknown>;
}): Promise<string | null> {
  const status = resolveStatusFromForm(opts.parsed);
  if (!status) return null;

  const dateKey =
    opts.parsed.dateKey ||
    new Intl.DateTimeFormat("en-CA", {timeZone: "Asia/Seoul"}).format(
      new Date(),
    );

  const docId = `${opts.userId}_${dateKey}`;
  await db
    .collection("cohorts")
    .doc(opts.cohortId)
    .collection("attendances")
    .doc(docId)
    .set(
      {
        userId: opts.userId,
        userDisplayName: opts.userDisplayName,
        dateKey,
        type: "status",
        status,
        statusSource: "form",
        formAttendanceType: opts.parsed.formAttendanceType,
        officialLeaveUsed: opts.parsed.officialLeaveUsed,
        officialLeaveType: opts.parsed.officialLeaveType,
        officialLeaveOther: opts.parsed.officialLeaveOther,
        formResponseId: opts.responseId ?? null,
        formAnswers: opts.answers ?? {},
        formSubmittedAt: fieldValue.serverTimestamp(),
        timestamp: fieldValue.serverTimestamp(),
        updatedAt: fieldValue.serverTimestamp(),
      },
      {merge: true},
    );

  logger.info("Attendance applied from form", {
    cohortId: opts.cohortId,
    userId: opts.userId,
    dateKey,
    status,
  });
  return status;
}
