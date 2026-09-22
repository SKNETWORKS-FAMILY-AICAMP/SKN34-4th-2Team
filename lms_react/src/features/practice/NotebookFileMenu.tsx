import { useRef, useState } from 'react';

import type { PracticeSet } from '../../domain/types';
import { Icon } from '../../ui/Icon';
import {
  exportFileName,
  MAX_IMPORT_BYTES,
  NotebookFileError,
  parseNotebookFile,
  toIpynb,
  toPy,
  type ImportedNotebook,
} from './notebookFile';
import type { Notebook } from './useNotebook';

interface Pending {
  name: string;
  file: ImportedNotebook;
}

/**
 * 파일 — 수업 노트북(.ipynb)·스크립트(.py)를 올려 돌리고, 지금 노트북을 파일로 가져간다.
 * 파일은 이 브라우저 안에서만 읽는다. 서버로 가지 않는다.
 */
export function NotebookFileMenu({ nb, set }: { nb: Notebook; set: PracticeSet | undefined }) {
  const input = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState('');

  const download = (ext: 'ipynb' | 'py') => {
    const text = ext === 'ipynb' ? toIpynb(nb.cells, set) : toPy(nb.cells, set);
    const blob = new Blob([text], { type: ext === 'ipynb' ? 'application/x-ipynb+json' : 'text/x-python' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = exportFileName(set, ext);
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    setOpen(false);
  };

  const pick = async (f: File | undefined) => {
    setError('');
    setPending(null);
    if (!f) return;
    try {
      if (f.size > MAX_IMPORT_BYTES) throw new NotebookFileError('파일이 너무 커요(8MB 까지). 출력을 지우고 저장한 뒤 올려 주세요.');
      const file = parseNotebookFile(f.name, await f.text());
      setPending({ name: f.name, file });
    } catch (e) {
      setError(e instanceof NotebookFileError ? e.message : '파일을 읽지 못했어요.');
    } finally {
      if (input.current) input.current.value = '';
    }
  };

  const apply = (how: 'replace' | 'append') => {
    if (!pending) return;
    nb.importCells(pending.file.cells, how, pending.name);
    setPending(null);
  };

  const codeCells = pending?.file.cells.filter((c) => c.type === 'code').length ?? 0;

  return (
    <>
      <span className="py-picker py-file">
        <button type="button" className="btn btn--outline btn--sm" onClick={() => input.current?.click()} title=".ipynb · .py 파일을 불러옵니다">
          <Icon name="upload_file" size={18} />
          불러오기
        </button>
        <button type="button" className="btn btn--outline btn--sm" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-haspopup="menu">
          <Icon name="download" size={18} />
          내려받기
        </button>
        {open && (
          <ul className="py-picker__menu" role="menu">
            <li>
              <button type="button" role="menuitem" onClick={() => download('ipynb')}>
                Jupyter 노트북 (.ipynb) · 출력 포함
              </button>
            </li>
            <li>
              <button type="button" role="menuitem" onClick={() => download('py')}>
                파이썬 파일 (.py) · # %% 셀 구분
              </button>
            </li>
          </ul>
        )}
        <input
          ref={input}
          type="file"
          accept=".ipynb,.py,application/x-ipynb+json,text/x-python"
          hidden
          onChange={(e) => void pick(e.target.files?.[0])}
          aria-label="노트북 파일 고르기"
        />
      </span>

      {(pending || error) && (
        <div className={`py-import${error ? ' py-import--error' : ''}`} role="status">
          <Icon name={error ? 'error' : 'description'} size={18} />
          {error ? (
            <span className="py-import__text">{error}</span>
          ) : (
            pending && (
              <span className="py-import__text">
                <span>
                  <strong>{pending.name}</strong> · 셀 {pending.file.cells.length}개 (코드 {codeCells})
                </span>
                {pending.file.notes.map((n) => (
                  <small key={n}>{n}</small>
                ))}
                <small>출력은 가져오지 않아요. 불러온 뒤 「모두 실행」하면 다시 나옵니다.</small>
              </span>
            )
          )}
          <span className="py-grow" />
          {pending && !set && (
            <button type="button" className="btn btn--filled btn--sm" onClick={() => apply('replace')}>
              이 파일로 바꾸기
            </button>
          )}
          {pending && (
            <button type="button" className={`btn btn--${set ? 'filled' : 'outline'} btn--sm`} onClick={() => apply('append')}>
              끝에 붙이기
            </button>
          )}
          <button type="button" className="btn btn--text btn--sm" onClick={() => { setPending(null); setError(''); }}>
            {error ? '닫기' : '취소'}
          </button>
        </div>
      )}
    </>
  );
}
