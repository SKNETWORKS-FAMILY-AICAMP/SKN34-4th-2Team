import {defineSecret} from "firebase-functions/params";
import {onRequest} from "firebase-functions/v2/https";
import * as logger from "firebase-functions/logger";

import {admin, db} from "./firebase";
import {
  applyAttendanceFromForm,
  findStudentForAttendance,
  hasAttendanceAnswers,
  parseAttendanceAnswers,
} from "./attendanceForm";

export const googleFormWebhookSecret = defineSecret("GOOGLE_FORM_WEBHOOK_SECRET");

interface WebhookPayload {
  cohortId?: string;
  taskId?: string;
  email?: string;
  responseId?: string;
  answers?: Record<string, unknown>;
}

function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

/**
 * Google Apps Script → Firebase
 * POST JSON: { cohortId, taskId?, email?, responseId?, answers? }
 * Header: X-Webhook-Secret
 *
 * answers: 구글폼 문항 제목 → 응답 값 (출석 유형/공가 등)
 * email: 상담 시 등록한 personalEmail (Gmail) 우선, 없으면 이름 매칭
 */
export const googleFormWebhook = onRequest(
  {
    region: "asia-northeast3",
    secrets: [googleFormWebhookSecret],
    cors: false,
    invoker: "public",
  },
  async (req, res) => {
    if (req.method !== "POST") {
      res.status(405).send("Method Not Allowed");
      return;
    }

    const secret = req.get("X-Webhook-Secret");
    if (!secret || secret !== googleFormWebhookSecret.value()) {
      res.status(401).json({error: "Unauthorized"});
      return;
    }

    const body = req.body as WebhookPayload;
    const {cohortId, taskId, responseId, answers} = body;
    const email = body.email ? normalizeEmail(body.email) : "";
    const parsed = parseAttendanceAnswers(answers);
    const isAttendance = hasAttendanceAnswers(answers);

    if (!cohortId) {
      res.status(400).json({error: "cohortId is required"});
      return;
    }
    if (!taskId && !isAttendance) {
      res.status(400).json({
        error: "taskId, email are required (or attendance answers)",
      });
      return;
    }

    try {
      const userDoc = await findStudentForAttendance({
        cohortId,
        email,
        name: parsed.name,
      });
      if (!userDoc) {
        logger.warn("Google form submit: user not found", {
          email,
          name: parsed.name,
          taskId,
        });
        res.status(404).json({error: "User not found for email/name"});
        return;
      }

      const userId = userDoc.id;
      const userData = userDoc.data();
      const userDisplayName =
        (userData?.displayName as string | undefined) ?? parsed.name ?? "";

      let attendanceStatus: string | null = null;
      if (isAttendance) {
        attendanceStatus = await applyAttendanceFromForm({
          cohortId,
          userId,
          userDisplayName,
          parsed,
          responseId,
          answers,
        });
      }

      if (taskId) {
        const taskRef = db
          .collection("cohorts")
          .doc(cohortId)
          .collection("formTasks")
          .doc(taskId);
        const taskDoc = await taskRef.get();
        if (taskDoc.exists) {
          const responseRef = taskRef.collection("responses").doc(userId);
          const existing = await responseRef.get();
          const batch = db.batch();
          batch.set(
            responseRef,
            {
              userId,
              userEmail: email,
              userDisplayName,
              taskId,
              cohortId,
              source: "google_form",
              googleResponseId: responseId ?? null,
              answers: answers ?? {},
              submittedAt: admin.firestore.FieldValue.serverTimestamp(),
            },
            {merge: true},
          );
          if (!existing.exists) {
            batch.update(taskRef, {
              responseCount: admin.firestore.FieldValue.increment(1),
            });
          }
          await batch.commit();
        }
      }

      logger.info("Google form response recorded", {
        cohortId,
        taskId,
        userId,
        attendanceStatus,
      });
      res.status(200).json({
        ok: true,
        userId,
        attendanceStatus,
        message: attendanceStatus
          ? `Submission recorded (${attendanceStatus})`
          : "Submission recorded",
      });
    } catch (error) {
      logger.error("Google form webhook failed", error);
      res.status(500).json({error: "Internal error"});
    }
  },
);
