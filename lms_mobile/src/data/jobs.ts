import { http } from './http';

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
