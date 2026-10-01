import type { AlertPopup, Notice, Post, PostComment, ScheduledNotice } from '@web/domain/types';

import { http, readApiError } from './http';
import { patchBootstrap, queryClient, queryKeys, useDb } from './query';

async function refresh(): Promise<void> {
  await queryClient.invalidateQueries({ queryKey: queryKeys.bootstrap });
}

export function useNotices(): Notice[] {
  return useDb()?.notices ?? [];
}

export function usePosts(): Post[] {
  return useDb()?.posts ?? [];
}

export function useComments(postId: string): PostComment[] {
  return (useDb()?.postComments ?? []).filter((comment) => comment.postId === postId);
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
  if (notice.id) await http.patch(`/scheduled-notices/${notice.id}`, body);
  else await http.post('/scheduled-notices', body);
  await refresh();
}

export async function removeScheduled(id: string): Promise<void> {
  await http.delete(`/scheduled-notices/${id}`);
  await refresh();
}

export async function publishScheduled(id: string): Promise<void> {
  await http.post('/scheduled-notices/publish', { ids: [id] });
  await refresh();
}

export async function saveAlert(
  popup: Partial<AlertPopup> & { title: string; content: string; cohortId: string },
): Promise<void> {
  if (popup.id) await http.patch(`/alert-popups/${popup.id}`, popup);
  else await http.post('/alert-popups', popup);
  await refresh();
}

export async function removeAlert(id: string): Promise<void> {
  await http.delete(`/alert-popups/${id}`);
  await refresh();
}

export function markAlertRead(popupId: string): void {
  void http.post(`/alert-popups/${popupId}/read`).catch(() => undefined);
}

export async function dismissAlertToday(popupId: string, dateKey: string): Promise<void> {
  await http.post(`/alert-popups/${popupId}/dismiss`, { dateKey });
}

/** 웹 repository 와 같다. 게시글 쓰기는 아직 서버 명령이 없어 화면 캐시에만 반영된다. */
export function addPost(authorId: string, authorName: string, content: string): void {
  patchBootstrap((db) => ({
    posts: [
      {
        id: `p-${Date.now()}`,
        authorId,
        authorName,
        content,
        likeCount: 0,
        commentCount: 0,
        createdAt: new Date(),
      },
      ...db.posts,
    ],
  }));
}

export function removePost(id: string): void {
  patchBootstrap((db) => ({
    posts: db.posts.filter((post) => post.id !== id),
    postComments: db.postComments.filter((comment) => comment.postId !== id),
  }));
}

export function likePost(id: string): void {
  patchBootstrap((db) => ({
    posts: db.posts.map((post) => (post.id === id ? { ...post, likeCount: post.likeCount + 1 } : post)),
  }));
}

export function addComment(postId: string, authorId: string, authorName: string, content: string): void {
  patchBootstrap((db) => ({
    postComments: [
      ...db.postComments,
      { id: `pc-${Date.now()}`, postId, authorId, authorName, content, createdAt: new Date() },
    ],
    posts: db.posts.map((post) => (post.id === postId ? { ...post, commentCount: post.commentCount + 1 } : post)),
  }));
}
