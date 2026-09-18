import {defineSecret, defineString} from "firebase-functions/params";
import {onCall, HttpsError} from "firebase-functions/v2/https";
import {onSchedule} from "firebase-functions/v2/scheduler";
import * as logger from "firebase-functions/logger";

import {admin, db} from "./firebase";
export const discordBotToken = defineSecret("DISCORD_BOT_TOKEN");
export const discordCohortId = defineString("DISCORD_COHORT_ID", {
  default: "cohort_34",
  description: "Discord 공지를 동기화할 기수 ID",
});

const DISCORD_CHANNELS = [
  {
    id: "1505777394886246501",
    label: "매니저 공지",
    type: "manager",
  },
  {
    id: "1505777394886246502",
    label: "캠퍼스 Q&A",
    type: "campus",
  },
] as const;

interface DiscordMessage {
  id: string;
  content: string;
  author: {username: string; bot?: boolean};
  timestamp: string;
}

function noticeTitle(content: string): string {
  const trimmed = content.trim();
  if (!trimmed) return "디스코드 공지";
  const firstLine = trimmed.split("\n")[0].trim();
  return firstLine.length > 80 ? `${firstLine.slice(0, 80)}…` : firstLine;
}

async function fetchChannelMessages(
  channelId: string,
  token: string,
  limit = 25,
): Promise<DiscordMessage[]> {
  const response = await fetch(
    `https://discord.com/api/v10/channels/${channelId}/messages?limit=${limit}`,
    {headers: {Authorization: `Bot ${token}`}},
  );

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Discord API ${response.status}: ${body}`);
  }

  return response.json() as Promise<DiscordMessage[]>;
}

export async function syncDiscordNoticesToFirestore(
  token: string,
  cohortId: string,
): Promise<{synced: number; channels: number}> {
  const cohortRef = db.collection("cohorts").doc(cohortId);
  const cohortDoc = await cohortRef.get();
  if (!cohortDoc.exists) {
    throw new HttpsError("not-found", `기수 '${cohortId}'를 찾을 수 없습니다.`);
  }

  let synced = 0;
  let batch = db.batch();
  let batchCount = 0;

  const commitBatch = async () => {
    if (batchCount === 0) return;
    await batch.commit();
    batch = db.batch();
    batchCount = 0;
  };

  for (const channel of DISCORD_CHANNELS) {
    const messages = await fetchChannelMessages(channel.id, token);
    for (const message of messages) {
      if (message.author.bot || !message.content.trim()) continue;

      const docId = `discord_${message.id}`;
      const noticeRef = cohortRef.collection("notices").doc(docId);
      batch.set(
        noticeRef,
        {
          title: noticeTitle(message.content),
          content: message.content.trim(),
          authorId: "discord",
          authorName: message.author.username,
          isFavorite: channel.type === "manager",
          priority: channel.type === "manager" ? 1 : 0,
          source: "discord",
          channelLabel: channel.label,
          discordMessageId: message.id,
          discordChannelId: channel.id,
          discordChannelType: channel.type,
          createdAt: admin.firestore.Timestamp.fromDate(
            new Date(message.timestamp),
          ),
          updatedAt: admin.firestore.FieldValue.serverTimestamp(),
        },
        {merge: true},
      );
      synced++;
      batchCount++;

      if (batchCount >= 400) {
        await commitBatch();
      }
    }
  }

  await commitBatch();

  return {synced, channels: DISCORD_CHANNELS.length};
}

const discordSyncOptions = {
  region: "asia-northeast3" as const,
  secrets: [discordBotToken],
};

/**
 * 5분마다 디스코드 공지 채널 → Firestore notices 동기화
 */
export const syncDiscordNotices = onSchedule(
  {
    ...discordSyncOptions,
    schedule: "every 5 minutes",
    timeZone: "Asia/Seoul",
  },
  async () => {
    const token = discordBotToken.value();
    const cohortId = discordCohortId.value();
    try {
      const result = await syncDiscordNoticesToFirestore(token, cohortId);
      logger.info("Discord notices synced", result);
    } catch (error) {
      logger.error("Discord sync failed", error);
      throw error;
    }
  },
);

/**
 * 관리자 수동 동기화 (테스트용)
 */
export const syncDiscordNoticesNow = onCall(discordSyncOptions, async (request) => {
  if (!request.auth) {
    throw new HttpsError("unauthenticated", "인증이 필요합니다.");
  }

  const caller = await db.collection("users").doc(request.auth.uid).get();
  if (!caller.exists || caller.data()?.role !== "admin") {
    throw new HttpsError("permission-denied", "관리자만 실행할 수 있습니다.");
  }

  const cohortId =
    (request.data as {cohortId?: string})?.cohortId ?? discordCohortId.value();
  const token = discordBotToken.value();
  const result = await syncDiscordNoticesToFirestore(token, cohortId);

  return {
    message: "디스코드 공지 동기화가 완료되었습니다.",
    ...result,
    cohortId,
  };
});
