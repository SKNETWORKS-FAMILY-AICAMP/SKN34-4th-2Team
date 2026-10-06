import { fetch as expoFetch } from 'expo/fetch';

import { API_BASE, http, refreshAccess } from './http';
import { useSessionStore } from './sessionStore';

export interface Posting {
  jobId: string;
  company: string;
  title: string;
  region: string;
  career: string;
  employmentType: string;
  deadline: string | null;
  techStack: string[];
  description?: string;
  url?: string;
}

export async function fetchPosting(jobId: string): Promise<Record<string, unknown>> {
  const { data } = await http.get<Record<string, unknown>>(`/postings/${encodeURIComponent(jobId)}`);
  return data;
}

export async function fetchApplyLink(jobId: string): Promise<string> {
  const { data } = await http.get<{ url?: string }>(`/postings/${encodeURIComponent(jobId)}/apply-link`);
  return data.url ?? '';
}

export async function featuredPostings(): Promise<Posting[]> {
  const { data } = await http.get<{ postings?: Posting[] }>('/featured-postings');
  return data.postings ?? [];
}

export interface CoachReply {
  reply: string;
  jobs: Posting[];
  suggestions: string[];
}

export async function askCoach(message: string, resumeId: string | null): Promise<CoachReply> {
  const { data } = await http.post<{
    reply?: string;
    jobs?: Record<string, unknown>[];
    suggestions?: string[];
  }>('/jobs/chat', { message, resumeId, lastJobIds: [] });
  return {
    reply: data.reply ?? '',
    suggestions: data.suggestions ?? [],
    jobs: (data.jobs ?? []).map((job) => ({
      jobId: String(job.jobId ?? job.job_id ?? ''),
      company: String(job.company ?? ''),
      title: String(job.title ?? ''),
      region: String(job.region ?? ''),
      career: String(job.career ?? ''),
      employmentType: String(job.employmentType ?? job.employment_type ?? ''),
      deadline: job.deadline == null ? null : String(job.deadline),
      techStack: Array.isArray(job.techStack) ? (job.techStack as string[]) : [],
    })),
  };
}

export async function askChatbot(message: string): Promise<string> {
  const { data } = await http.post<{ answer?: string }>('/chat', { message });
  return data.answer ?? '';
}

/** 화면을 나갔다 와도 대화가 남게 메모리에만 둔다 — 로그아웃하면 비운다 */
export const chatHistory = new Map<string, { role: 'me' | 'bot'; text: string }[]>();

async function openChatStream(message: string, retried = false): Promise<Response | null> {
  const access = useSessionStore.getState().access;
  let response: Response;
  try {
    response = (await expoFetch(`${API_BASE}/chat/stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/x-ndjson',
        ...(access ? { Authorization: `Bearer ${access}` } : {}),
      },
      body: JSON.stringify({ message }),
    })) as unknown as Response;
  } catch {
    return null;
  }
  if (response.status === 401 && !retried) {
    try {
      await refreshAccess();
    } catch {
      return null;
    }
    return openChatStream(message, true);
  }
  const ndjson = response.headers.get('content-type')?.includes('application/x-ndjson');
  return response.ok && ndjson && response.body ? response : null;
}

/** 웹 ChatbotHost 와 같은 NDJSON 스트림 — 열리지 않으면 `/chat` 한 번에 받기로 물러난다 */
export async function streamChatbot(message: string, onToken: (text: string) => void): Promise<string> {
  const response = await openChatStream(message);
  if (!response?.body) {
    const answer = (await askChatbot(message)) || '답변을 받지 못했습니다.';
    onToken(answer);
    return answer;
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let text = '';
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      if (!line.trim()) continue;
      let event: { type: string; content?: string; message?: string };
      try {
        event = JSON.parse(line) as typeof event;
      } catch {
        throw new Error('답변을 읽지 못했습니다.');
      }
      if (event.type === 'token' && event.content) {
        text += event.content;
        onToken(text);
      }
      if (event.type === 'error') throw new Error(event.message || '답변 생성 중 오류가 발생했습니다.');
      if (event.type === 'done') return text || '답변을 받지 못했습니다.';
    }
    if (done) {
      if (!text) throw new Error('답변 전송이 중단됐습니다.');
      return text;
    }
  }
}

export interface AssistantAction {
  id: string;
  type: string;
  title?: string;
  content?: string;
  signature?: string;
  targets?: { uid: string; name: string }[];
}

export async function askAssistant(messages: { role: 'user' | 'assistant'; content: string }[], context: string, cohortId: string) {
  const { data } = await http.post<{ reply?: string; actions?: AssistantAction[]; context?: string }>('/admin/assistant', {
    messages,
    context,
    cohortId,
  });
  return { reply: data.reply ?? '', actions: data.actions ?? [], context: data.context ?? '' };
}

export async function executeAssistant(action: AssistantAction, cohortId: string): Promise<void> {
  await http.post('/admin/assistant/execute', { action, cohortId });
  const { queryClient, queryKeys } = await import('./query');
  await queryClient.invalidateQueries({ queryKey: queryKeys.bootstrap });
}
