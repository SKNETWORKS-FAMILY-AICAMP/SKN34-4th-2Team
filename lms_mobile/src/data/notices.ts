import { useQuery } from '@tanstack/react-query';
import type { AlertPopup, Notice, Post, PostComment, ScheduledNotice } from '@web/domain/types';

import { http, readApiError } from './http';
import { patchBootstrap, queryClient, queryKeys, useDb } from './query';

async function refresh(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: queryKeys.bootstrap });
}

export function useNotices(): Notice[] {
  return useDb()?.notices ?? [];
}

// 소통 피드 — 웹과 같은 서버 표(posts · post_comments · post_likes, /posts). 학생은 자기 기수 글만 받는다.
const postKey = ['posts'] as const;

type Dated<T> = Omit<T, 'createdAt'> & { createdAt?: string };
const withDate = <T extends { createdAt?: Date }>(row: Dated<T>): T =>
  ({ ...row, createdAt: row.createdAt ? new Date(row.createdAt) : undefined }) as T;

export async function refreshPosts(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: postKey });
}

async function postCall(request: () => Promise<unknown>): Promise<void> {
  try {
    await request();
  } catch (error) {
    throw new Error(await readApiError(error));
  }
  await refreshPosts();
}

export function usePosts(): Post[] {
  const { data } = useQuery({
    queryKey: [...postKey, 'list'],
    queryFn: async () => (await http.get<{ posts: Dated<Post>[] }>('/posts')).data.posts.map((row) => withDate<Post>(row)),
  });
  return data ?? [];
}

export function useComments(postId: string): PostComment[] {
  const { data } = useQuery({
    queryKey: [...postKey, 'comments', postId],
    queryFn: async () =>
      (await http.get<{ comments: Dated<PostComment>[] }>(`/posts/${postId}/comments`)).data.comments.map((row) =>
        withDate<PostComment>(row),
      ),
  });
  return data ?? [];
}

export function useScheduled(): ScheduledNotice[] {
  return useDb()?.scheduledNotices ?? [];
}

export function useAlerts(): AlertPopup[] {
  return useDb()?.alertPopups ?? [];
}

export async function saveNotice(input: {
  id?: string;
  title: string;
  content: string;
  isFavorite: boolean;
  cohortId: string;
}): Promise<void> {
  try {
    if (input.id) await http.patch(`/notices/${input.id}`, input);
    else await http.post('/notices', input);
    await refresh();
  } catch (error) {
    throw new Error(await readApiError(error));
  }
}

export async function removeNotice(id: string): Promise<void> {
  patchBootstrap((db) => ({ notices: db.notices.filter((notice) => notice.id !== id) }));
  try {
    await http.delete(`/notices/${id}`);
    await refresh();
  } catch (error) {
    throw new Error(await readApiError(error));
  }
}

export async function saveScheduled(
  notice: Partial<ScheduledNotice> & { title: string; content: string; cohortId: string },
): Promise<void> {
  const body = {
    title: notice.title,
    content: notice.content,
    cohortId: notice.cohortId,
    isFavorite: notice.isFavorite ?? false,
    repeatType: notice.repeatType ?? 'once',
    publishTime: notice.publishTime ?? '09:00',
    weekday: notice.weekday ?? 1,
    isActive: notice.isActive ?? true,
  };
  await call(() => (notice.id ? http.patch(`/scheduled-notices/${notice.id}`, body) : http.post('/scheduled-notices', body)));
}

export async function removeScheduled(id: string): Promise<void> {
  await call(() => http.delete(`/scheduled-notices/${id}`));
}

export async function publishScheduled(id: string): Promise<void> {
  await call(() => http.post('/scheduled-notices/publish', { ids: [id] }));
}

export async function saveAlert(
  popup: Partial<AlertPopup> & { title: string; content: string; cohortId: string },
): Promise<void> {
  await call(() => (popup.id ? http.patch(`/alert-popups/${popup.id}`, popup) : http.post('/alert-popups', popup)));
}

export async function removeAlert(id: string): Promise<void> {
  await call(() => http.delete(`/alert-popups/${id}`));
}

/** 서버의 오류 문장을 그대로 화면에 올린다 */
async function call(request: () => Promise<unknown>): Promise<void> {
  try {
    await request();
  } catch (error) {
    throw new Error(await readApiError(error));
  }
  await refresh();
}

export function markAlertRead(popupId: string): void {
  void http.post(`/alert-popups/${popupId}/read`).catch(() => undefined);
}

export async function dismissAlertToday(popupId: string, dateKey: string): Promise<void> {
  await http.post(`/alert-popups/${popupId}/dismiss`, { dateKey });
}

export async function addPost(content: string): Promise<void> {
  await postCall(() => http.post('/posts', { content }));
}

export async function removePost(id: string): Promise<void> {
  await postCall(() => http.delete(`/posts/${id}`));
}

/** 한 사람이 한 글에 한 번 — 다시 누르면 취소(서버) */
export async function likePost(id: string): Promise<void> {
  await postCall(() => http.post(`/posts/${id}/like`));
}

export async function addComment(postId: string, content: string): Promise<void> {
  await postCall(() => http.post(`/posts/${postId}/comments`, { content }));
}

export async function removeComment(postId: string, commentId: string): Promise<void> {
  await postCall(() => http.delete(`/posts/${postId}/comments/${commentId}`));
}
