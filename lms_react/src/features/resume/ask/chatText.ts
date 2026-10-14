/**
 * 챗봇 답을 화면에 그릴 조각으로 나눈다 — `ai_coach/data/chat_text.dart` 그대로.
 *
 * 모델은 강조에 `**별표**`를 쓰고 항목에 `- `를 붙인다. 글자 그대로 그리면 별표가 보여
 * 오히려 읽기 나빴다. 비교나 준비 순서처럼 나란한 것을 나란히 보여 주는 답이 많아 항목은
 * 살린다. 마크다운을 다 읽지는 않는다 — 굵게와 항목 줄만 본다.
 */
export interface ChatSpan {
  text: string;
  bold: boolean;
}

export interface ChatBlock {
  spans: ChatSpan[];
  bullet: boolean;
}

const BULLETS = ['- ', '• ', '* ', '– '];

/** 답 한 편을 덩어리로 나눈다. 빈 줄은 덩어리 사이 여백이라 버린다. */
export function parseChatText(text: string): ChatBlock[] {
  const blocks: ChatBlock[] = [];
  for (const raw of text.split('\n')) {
    let body = raw.trim();
    if (body === '') continue;
    let bullet = false;
    for (const marker of BULLETS) {
      // 점 하나만 있던 줄은 다듬고 나면 기호만 남는다. 항목이되 내용이 없다.
      if (body === marker.trim()) {
        bullet = true;
        body = '';
        break;
      }
      if (body.startsWith(marker)) {
        bullet = true;
        body = body.slice(marker.length).trim();
        break;
      }
    }
    if (body === '') continue;
    blocks.push({ spans: parseChatSpans(body), bullet });
  }
  return blocks;
}

/** 한 줄을 굵은 조각과 보통 조각으로 나눈다. 짝이 안 맞는 별표는 글자로 둔다. */
export function parseChatSpans(line: string): ChatSpan[] {
  const spans: ChatSpan[] = [];
  let rest = line;
  for (;;) {
    const open = rest.indexOf('**');
    if (open < 0) break;
    const close = rest.indexOf('**', open + 2);
    if (close < 0) break;
    if (open > 0) spans.push({ text: rest.slice(0, open), bold: false });
    const inner = rest.slice(open + 2, close);
    if (inner !== '') spans.push({ text: inner, bold: true });
    rest = rest.slice(close + 2);
  }
  if (rest !== '') spans.push({ text: rest, bold: false });
  return spans;
}
