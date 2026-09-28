import { useEffect, useRef, useState, type DragEvent } from 'react';

import { nextId } from '../../data/store';
import { Icon } from '../../ui/Icon';
import { Button } from '../../ui/components';
import { reviewApi } from '../resume/review/reviewApi';
import type { CompanyQuestion } from './companyQuestions';

/**
 * 캡처 · 지원서 양식 PDF 에서 자기소개서 문항 뽑기 — 회사 사이트가 로그인해야 문항을 보여 주거나,
 * 문항이 이미지 · 첨부 양식 안에 있을 때.
 *
 * 고르기 · 끌어다 놓기 · Ctrl+V 로 이미지를 세 장까지, 또는 PDF 한 개를 받는다. 글이 든 PDF 는 서버가 글을 꺼내
 * 읽고, 스캔 PDF 는 페이지 이미지를 읽는다. 서버(question_extract.py)가 이미지 속 글을 옮겨 적고,
 * 그 글에 실제로 있는 문항과 글자 수만 돌려준다. 결과는 붙여넣기와 같은 「확인하고 고치기」 목록으로 간다.
 * 이미지는 저장하지 않는다.
 */
const MAX_IMAGES = 3;
const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/webp'];
const PDF = 'application/pdf';
// 지원서 캡처는 세로로 길다. 폭만 줄인다 — 높이까지 맞춰 줄이면 글자가 뭉개져 못 읽는다
const MAX_WIDTH = 1600;

async function shrink(file: File): Promise<Blob> {
  if (typeof createImageBitmap !== 'function') return file;
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, MAX_WIDTH / bitmap.width);
  if (scale === 1 && file.size <= 2_000_000) {
    bitmap.close();
    return file;
  }
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return new Promise((resolve) => canvas.toBlob((blob) => resolve(blob ?? file), 'image/jpeg', 0.9));
}

interface Picked {
  blob: Blob;
  url: string;
  name: string;
}

export function CaptureUpload({ onParsed }: { onParsed(questions: CompanyQuestion[], dropped: number): void }) {
  const [images, setImages] = useState<Picked[]>([]);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [over, setOver] = useState(false);
  const [link, setLink] = useState('');
  const input = useRef<HTMLInputElement>(null);
  const imagesRef = useRef(images);
  imagesRef.current = images;

  const add = async (files: File[]) => {
    // PDF 는 한 개만, 캡처와 섞지 않는다. 새 PDF 를 고르면 앞서 고른 것을 바꾼다
    const pdf = files.find((f) => f.type === PDF);
    if (pdf !== undefined) {
      setError(files.length > 1 ? 'PDF 는 한 개만, 캡처와 따로 올려 주세요. 첫 PDF 만 담았어요.' : null);
      imagesRef.current.forEach((i) => URL.revokeObjectURL(i.url));
      setImages([{ blob: pdf, url: '', name: pdf.name }]);
      return;
    }
    const usable = files.filter((f) => IMAGE_TYPES.includes(f.type));
    if (usable.length < files.length) {
      setError('PNG · JPG · WEBP 이미지나 PDF 만 올릴 수 있어요. Word · 한글 양식은 PDF 로 저장해 올려 주세요.');
    } else {
      setError(null);
    }
    // PDF 를 담아 둔 채 캡처를 고르면 캡처로 바꾼다
    const kept = imagesRef.current.filter((i) => i.blob.type !== PDF);
    const room = MAX_IMAGES - kept.length;
    if (usable.length > room) setError(`캡처는 ${MAX_IMAGES}장까지 올릴 수 있어요.`);
    const next = await Promise.all(usable.slice(0, Math.max(0, room)).map(async (f) => ({ blob: await shrink(f), name: f.name })));
    setImages(
      [...kept, ...next.map(({ blob, name }) => ({ blob, name, url: URL.createObjectURL(blob) }))].slice(0, MAX_IMAGES),
    );
  };

  // 캡처 도구로 찍고 바로 Ctrl+V — 글을 붙여 넣는 칸은 건드리지 않게 이미지가 있을 때만 가로챈다
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const files = Array.from(e.clipboardData?.files ?? []).filter((f) => f.type.startsWith('image/'));
      if (files.length === 0) return;
      e.preventDefault();
      void add(files);
    };
    document.addEventListener('paste', onPaste);
    return () => document.removeEventListener('paste', onPaste);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 떠날 때 미리보기 주소를 돌려준다
  useEffect(() => () => imagesRef.current.forEach((i) => i.url !== '' && URL.revokeObjectURL(i.url)), []);

  const remove = (target: Picked) => {
    if (target.url !== '') URL.revokeObjectURL(target.url);
    setImages((list) => list.filter((i) => i !== target));
  };

  const drop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setOver(false);
    void add(Array.from(e.dataTransfer.files));
  };

  const read = async (fromLink = false) => {
    if (reading || (fromLink ? link.trim() === '' : images.length === 0)) return;
    setReading(true);
    setError(null);
    try {
      const data = fromLink
        ? await reviewApi.extractQuestionsFromLink(link.trim())
        : await reviewApi.extractQuestions(images.map((i) => i.blob));
      const list = Array.isArray(data.questions) ? (data.questions as { question?: unknown; limit?: unknown }[]) : [];
      onParsed(
        list.map((q) => ({
          id: nextId('cq'),
          question: String(q.question ?? ''),
          limit: typeof q.limit === 'number' ? q.limit : null,
          answer: '',
        })),
        Number(data.dropped ?? 0),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : '캡처를 읽지 못했어요. 잠시 후 다시 시도해 주세요.');
    } finally {
      setReading(false);
    }
  };

  return (
    <div className="apply-tabpanel" role="tabpanel">
      <div
        className={`apply-drop${over ? ' is-over' : ''}`}
        role="button"
        tabIndex={0}
        onClick={() => input.current?.click()}
        onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={drop}
      >
        <Icon name="add_photo_alternate" size={30} />
        <span>
          <b>문항이 보이는 화면 캡처</b>나 <b>지원서 양식 PDF</b>를 끌어다 놓거나 눌러서 골라 주세요
        </span>
        <span className="hint">
          Ctrl+V 로 캡처를 바로 붙여 넣어도 돼요 · 캡처 {MAX_IMAGES}장 또는 PDF 1개 · Word · 한글 양식은 PDF 로 저장해 올려 주세요
        </span>
        <input
          ref={input}
          type="file"
          accept={[...IMAGE_TYPES, PDF].join(',')}
          multiple
          hidden
          onChange={(e) => {
            void add(Array.from(e.target.files ?? []));
            e.target.value = '';
          }}
        />
      </div>

      {images.length > 0 && (
        <ul className="apply-thumbs">
          {images.map((image, i) => (
            <li key={`${image.name}-${i}`}>
              {image.blob.type === PDF ? (
                <span className="apply-thumbs__pdf" title={image.name}>
                  <Icon name="picture_as_pdf" size={28} />
                  <span>{image.name}</span>
                </span>
              ) : (
                <img src={image.url} alt={`캡처 ${i + 1}`} />
              )}
              <button type="button" className="icon-btn" aria-label={`${image.name} 빼기`} onClick={() => remove(image)}>
                <Icon name="close" size={16} />
              </button>
            </li>
          ))}
        </ul>
      )}

      <div>
        <Button variant="outline" onClick={() => void read()} disabled={reading || images.length === 0}>
          <Icon name="document_scanner" size={18} />
          {reading ? '읽는 중… (5~10초)' : '문항 읽기'}
        </Button>
      </div>

      {/* 공고에 첨부된 지원서 양식 — 내려받지 않고 링크로 */}
      <form
        className="apply-attach-link"
        onSubmit={(e) => {
          e.preventDefault();
          void read(true);
        }}
      >
        <span className="apply-label">또는 공고 첨부파일 링크</span>
        <input
          className="apply-q-input"
          type="url"
          value={link}
          onChange={(e) => setLink(e.target.value)}
          placeholder="https://…saramin.co.kr/…/attach5.pdf"
          aria-label="공고 첨부파일 링크"
        />
        <Button type="submit" variant="outline" disabled={reading || link.trim() === ''}>
          <Icon name="link" size={18} />
          링크로 읽기
        </Button>
      </form>
      {error !== null && <p className="apply-error">{error}</p>}
    </div>
  );
}
