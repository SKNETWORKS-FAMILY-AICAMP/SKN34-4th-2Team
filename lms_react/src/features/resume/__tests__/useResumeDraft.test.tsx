import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Resume } from '../../../domain/types';
import { useResumeDraft } from '../useResumeDraft';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
const row = (title: string, id = 'r1') => ({ id, title, content: { basicInfo: { name: title } } }) as Resume;
let root: Root | undefined;
let host: HTMLDivElement;
let editor: ReturnType<typeof useResumeDraft>;

afterEach(async () => {
  await act(async () => root?.unmount());
  host?.remove();
  vi.useRealTimers();
});

function mount(server?: Resume) {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  function Editor({ server }: { server?: Resume }) {
    editor = useResumeDraft(server);
    return <span>{editor.resume?.title}</span>;
  }
  const render = async (value?: Resume) => {
    await act(async () => root!.render(<Editor server={value} />));
  };
  return { render, start: () => render(server) };
}

describe('Resume editor bootstrap isolation', () => {
  it('initializes when the first server resume arrives', async () => {
    const view = mount();
    await view.start();
    await view.render(row('server'));
    expect(editor.resume?.title).toBe('server');
  });

  it('keeps title and content while bootstrap refetch returns stale values', async () => {
    const view = mount(row('server'));
    await view.start();
    await act(async () => editor.edit({ title: 'typing', content: row('new name').content }));
    await view.render(row('old poll'));
    expect(editor.resume?.title).toBe('typing');
    expect(editor.resume?.content.basicInfo.name).toBe('new name');
  });

  it('accepts bootstrap updates when there are no local edits', async () => {
    const view = mount(row('first'));
    await view.start();
    await view.render(row('latest'));
    expect(editor.resume?.title).toBe('latest');
  });

  it('keeps dirty input after a failed save without completion acknowledgement', async () => {
    const view = mount(row('server'));
    await view.start();
    await act(async () => editor.edit({ title: 'unsaved' }));
    // A rejected updateResume never calls finishSave.
    await view.render(row('server'));
    expect(editor.resume?.title).toBe('unsaved');
  });

  it('resynchronizes after save and loads persisted values after remount', async () => {
    const view = mount(row('server'));
    await view.start();
    await act(async () => editor.edit({ title: 'saved' }));
    const version = editor.saveVersion();
    await view.render(row('saved'));
    await act(async () => editor.finishSave(version));
    await view.render(row('server latest'));
    expect(editor.resume?.title).toBe('server latest');
    await act(async () => root!.unmount());
    host.remove();
    const reloaded = mount(row('saved'));
    await reloaded.start();
    expect(editor.resume?.title).toBe('saved');
  });

  it('does not clear edits made while a save is in flight', async () => {
    const view = mount(row('server'));
    await view.start();
    await act(async () => editor.edit({ title: 'first' }));
    const version = editor.saveVersion();
    await act(async () => editor.edit({ title: 'second' }));
    await view.render(row('first'));
    await act(async () => editor.finishSave(version));
    expect(editor.resume?.title).toBe('second');
  });

  it('resets dirty state on resume navigation', async () => {
    const view = mount(row('one'));
    await view.start();
    await act(async () => editor.edit({ title: 'dirty' }));
    await view.render(row('two', 'r2'));
    await view.render(row('one'));
    expect(editor.resume?.title).toBe('one');
  });

  it('continues polling and updates other bootstrap consumers while protecting edits', async () => {
    vi.useFakeTimers();
    const query = vi.fn(async () => ({ resume: row('server'), notices: query.mock.calls.length }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
    function Consumer() {
      const { data } = useQuery({ queryKey: ['bootstrap'], queryFn: query, refetchInterval: 100, refetchIntervalInBackground: true });
      editor = useResumeDraft(data?.resume);
      return <span>{data?.notices}</span>;
    }
    await act(async () => root!.render(<QueryClientProvider client={client}><Consumer /></QueryClientProvider>));
    await act(async () => vi.advanceTimersByTimeAsync(10));
    await act(async () => editor.edit({ title: 'typing' }));
    await act(async () => vi.advanceTimersByTimeAsync(350));
    expect(query.mock.calls.length).toBeGreaterThan(1);
    expect(editor.resume?.title).toBe('typing');
    expect(Number(host.textContent)).toBeGreaterThan(1);
    client.clear();
  });
});
