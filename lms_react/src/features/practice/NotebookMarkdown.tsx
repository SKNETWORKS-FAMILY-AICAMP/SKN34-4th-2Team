import type { ReactNode } from 'react';

/**
 * 노트북 마크다운 셀 표시기.
 *
 * HTML 문자열을 끼워 넣지 않고 React 요소로만 만든다 — 학생이 쓴 글에 태그가 있어도 글자로 보인다.
 * 다루는 것: 제목(#~######), 목록(-, *, 1.), 인용(>), 코드 블록(```), 구분선(---),
 * 인라인 코드·굵게·기울임·링크(http/https 만). 표·중첩 목록·수식은 다루지 않는다.
 */
export function NotebookMarkdown({ source }: { source: string }) {
  return <div className="nb-md">{renderBlocks(source)}</div>;
}

type Block =
  | { kind: 'heading'; level: number; text: string }
  | { kind: 'code'; lang: string; text: string }
  | { kind: 'quote'; lines: string[] }
  | { kind: 'list'; ordered: boolean; items: string[] }
  | { kind: 'hr' }
  | { kind: 'para'; lines: string[] };

export function parseBlocks(source: string): Block[] {
  const lines = source.replace(/\r\n/g, '\n').split('\n');
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const fence = /^```(\w*)\s*$/.exec(line.trim());
    if (fence) {
      const body: string[] = [];
      i += 1;
      while (i < lines.length && lines[i].trim() !== '```') body.push(lines[i++]);
      i += 1; // 닫는 ``` (없으면 끝까지)
      blocks.push({ kind: 'code', lang: fence[1], text: body.join('\n') });
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) {
      blocks.push({ kind: 'heading', level: heading[1].length, text: heading[2].trim() });
      i += 1;
      continue;
    }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) {
      blocks.push({ kind: 'hr' });
      i += 1;
      continue;
    }
    if (/^>\s?/.test(line)) {
      const quote: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) quote.push(lines[i++].replace(/^>\s?/, ''));
      blocks.push({ kind: 'quote', lines: quote });
      continue;
    }
    const bullet = /^\s*[-*+]\s+/;
    const numbered = /^\s*\d+[.)]\s+/;
    if (bullet.test(line) || numbered.test(line)) {
      const ordered = numbered.test(line);
      const marker = ordered ? numbered : bullet;
      const items: string[] = [];
      while (i < lines.length && marker.test(lines[i])) items.push(lines[i++].replace(marker, ''));
      blocks.push({ kind: 'list', ordered, items });
      continue;
    }
    if (line.trim() === '') {
      i += 1;
      continue;
    }
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !/^(#{1,6}\s|```|>|\s*[-*+]\s+|\s*\d+[.)]\s+)/.test(lines[i])
    ) {
      para.push(lines[i++].trim());
    }
    if (para.length === 0) {
      // 위 조건에 걸리지 않은 한 줄 — 문단으로 두고 넘어간다.
      para.push(lines[i++].trim());
    }
    blocks.push({ kind: 'para', lines: para });
  }
  return blocks;
}

function renderBlocks(source: string): ReactNode[] {
  return parseBlocks(source).map((block, i) => {
    switch (block.kind) {
      case 'heading': {
        const Tag = `h${Math.min(block.level + 1, 6)}` as 'h2';
        return <Tag key={i}>{inline(block.text)}</Tag>;
      }
      case 'code':
        return (
          <pre key={i} className="nb-md__code">
            <code>{block.text}</code>
          </pre>
        );
      case 'quote':
        return <blockquote key={i}>{inline(block.lines.join(' '))}</blockquote>;
      case 'list': {
        const items = block.items.map((item, k) => <li key={k}>{inline(item)}</li>);
        return block.ordered ? <ol key={i}>{items}</ol> : <ul key={i}>{items}</ul>;
      }
      case 'hr':
        return <hr key={i} />;
      case 'para':
        return <p key={i}>{inline(block.lines.join(' '))}</p>;
    }
  });
}

/** 인라인: `코드`, **굵게**, *기울임* / _기울임_, [글](http주소) */
export function inline(text: string): ReactNode[] {
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*|__[^_]+__)|(\*[^*\s][^*]*\*|_[^_\s][^_]*_)|(\[[^\]]+\]\([^)\s]+\))/g;
  const out: ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (let m = re.exec(text); m; m = re.exec(text)) {
    if (m.index > last) out.push(text.slice(last, m.index));
    const token = m[0];
    if (m[1]) out.push(<code key={key++}>{token.slice(1, -1)}</code>);
    else if (m[2]) out.push(<strong key={key++}>{inline(token.slice(2, -2))}</strong>);
    else if (m[3]) out.push(<em key={key++}>{inline(token.slice(1, -1))}</em>);
    else {
      const link = /^\[([^\]]+)\]\(([^)\s]+)\)$/.exec(token)!;
      const href = link[2];
      out.push(
        /^https?:\/\//.test(href) ? (
          <a key={key++} href={href} target="_blank" rel="noreferrer">
            {link[1]}
          </a>
        ) : (
          token
        ),
      );
    }
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}
