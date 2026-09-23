/**
 * 수집한 공고 원문을 읽기 좋은 덩어리로 정리한다.
 *
 * 수집기는 채용 사이트 화면의 글을 줄 단위로 떠 온다. 그래서
 * - 사람인: 글머리표(ㆍ · • -)가 혼자 한 줄이고 내용이 다음 줄에 온다
 * - 잡코리아: 글자 꾸밈 단위로 문장이 조각난다(`Python\n프로그래밍 숙련\n:\n객체지향\n,\n…`)
 * - 소제목 앞에 이모지(📋 주요업무)가 붙는다
 * 원문 글자는 바꾸지 않고 줄만 다시 잇는다.
 */
export type PostingBlock =
  | { type: 'heading'; text: string }
  | { type: 'sub'; text: string }
  | { type: 'item'; text: string }
  | { type: 'text'; text: string };

/** 혼자 있으면 「다음 줄이 목록 한 항목」이라는 표시 */
const BULLET = /^[ㆍ·•‧∙◦○●■□▪▫※▶►▷✔✓☑✅◆◇★☆\-–—*]$/;
/** 줄 앞에 붙은 글머리표 */
const LEADING_BULLET = /^[ㆍ·•‧∙◦○●■□▪▫※▶►▷✔✓☑✅◆◇★☆\-–—*]\s*/;
/** 번호 표시만 있는 줄: 1. / 1) / ① */
const NUMBER = /^(?:\d{1,2}[.)]|[①-⑳])$/;
const LEADING_NUMBER = /^(?:\d{1,2}[.)]|[①-⑳])\s*/;

const SECTION_WORDS = [
  '상세요강', '모집부문', '모집분야', '포지션및자격요건', '포지션', '담당업무', '주요업무', '업무내용', '하는일',
  '자격요건', '지원자격', '필수요건', '필수사항', '우대사항', '우대조건', '우대요건', '기술스택', '스킬', '사용기술',
  '근무조건', '근무환경', '근무지', '근무지역', '근무시간', '급여', '복지', '복리후생', '복지및혜택', '혜택',
  '채용절차', '전형절차', '접수기간', '접수방법', '제출서류', '유의사항', '기타사항', '참고사항', '회사소개', '기업소개',
];

/** 이모지 · 괄호 · 콜론을 뗀 제목 글자 */
function headingCore(line: string): string {
  return line
    .replace(/\p{Extended_Pictographic}|\uFE0F|\u200D/gu, '')
    .replace(/^[[【<〈《(]\s*|\s*[\]】>〉》)]$/g, '')
    .replace(/[:：]\s*$/, '')
    .trim();
}

function isHeading(line: string): boolean {
  const core = headingCore(line);
  if (core === '' || core.length > 20) return false;
  if (SECTION_WORDS.includes(core.replace(/[\s·&]/g, ''))) return true;
  // 「[주요 업무]」처럼 괄호로 싼 짧은 줄, 이모지로 시작하는 짧은 줄도 소제목으로 본다
  return (/^\s*[[【]/.test(line) && /[\]】]\s*$/.test(line)) || /^\p{Extended_Pictographic}/u.test(line.trim());
}

/** 앞말에 붙여 쓰는 조각: 문장 부호로 시작하거나 부호만 있는 줄 */
const ATTACH_TIGHT = /^[,.:;)\]」』’”%!?·/]/;
/** 이 글자로 끝나면 다음 줄을 띄우지 않고 붙인다 */
const OPENS = /[([「『‘“/·]$/;
/** 조사 · 어미로 시작하는 조각은 앞말에 바로 붙는다(하이브랩\n은 → 하이브랩은) */
const PARTICLE = /^(?:은|는|이|가|을|를|의|에|에서|로|으로|와|과|도|만|할|하는|한|된|되는|입니다|합니다)(?=\s|$|[.,])/;
const SENTENCE_END = /(?:[.!?。]|다|요|니다|함|음|임)$/;
/** 조사로 끝났으면 문장이 이어진다(하이브랩은 → 다음 줄) */
const ENDS_WITH_PARTICLE = /(?:은|는|을|를|의|와|과|로|에|이|가)$/;

function joinPiece(prev: string, piece: string): string {
  if (prev === '') return piece;
  if (ATTACH_TIGHT.test(piece)) return prev + (piece.startsWith(':') ? piece.replace(/^:\s*/, ': ') : piece);
  if (OPENS.test(prev)) return prev + piece;
  if (PARTICLE.test(piece)) return prev + piece;
  if (/:$/.test(prev)) return `${prev} ${piece}`;
  return `${prev} ${piece}`;
}

function normalize(line: string): string {
  return line.replace(/[\u00a0\t\r]/g, ' ').replace(/\s{2,}/g, ' ').trim();
}

export function formatPostingText(raw: string): PostingBlock[] {
  const lines = raw.split('\n').map(normalize).filter((l) => l !== '');
  const blocks: PostingBlock[] = [];
  /** 목록 항목 · 번호 소제목은 다음 표시나 소제목이 나올 때까지 줄을 이어 붙인다 */
  let open: PostingBlock | null = null;

  const close = () => {
    if (open !== null && open.text.trim() !== '') blocks.push({ ...open, text: open.text.trim() });
    open = null;
  };

  for (const line of lines) {
    // 소제목 옆에 있던 이모지만 한 줄로 떨어져 나온 것. 앞 항목에 붙으면 글 끝에 그림이 남는다
    if (/\p{Extended_Pictographic}/u.test(line) && line.replace(/\p{Extended_Pictographic}|\uFE0F|\u200D|\s/gu, '') === '') continue;
    if (isHeading(line) && !(open !== null && open.text === '')) {
      close();
      // 「상세요강」은 사이트의 본문 머리말이라 아래에 딸린 내용이 없다
      if (headingCore(line).replace(/\s/g, '') !== '상세요강') blocks.push({ type: 'heading', text: headingCore(line) });
      continue;
    }
    if (BULLET.test(line)) {
      close();
      open = { type: 'item', text: '' };
      continue;
    }
    if (NUMBER.test(line)) {
      close();
      open = { type: 'sub', text: `${line} ` };
      continue;
    }
    if (LEADING_BULLET.test(line) && !/^-?\d/.test(line)) {
      close();
      open = { type: 'item', text: line.replace(LEADING_BULLET, '') };
      continue;
    }
    if (LEADING_NUMBER.test(line) && open?.type !== 'sub') {
      close();
      open = { type: 'sub', text: line };
      continue;
    }
    if (open !== null) {
      // 번호 소제목은 첫 조각만 제목이다. 그 뒤 줄은 목록이 이어 받는다
      if (open.type === 'sub' && open.text.trim() !== '' && !/[\d.)①-⑳]\s*$/.test(open.text) && !ATTACH_TIGHT.test(line)) {
        close();
        blocks.push({ type: 'text', text: line });
        continue;
      }
      open.text = joinPiece(open.text.trimEnd(), line);
      continue;
    }
    // 자유 글: 조각난 문장만 앞 줄에 잇는다
    const last = blocks[blocks.length - 1];
    if (
      last !== undefined &&
      last.type === 'text' &&
      (ATTACH_TIGHT.test(line) ||
        OPENS.test(last.text) ||
        /:$/.test(last.text) ||
        PARTICLE.test(line) ||
        ENDS_WITH_PARTICLE.test(last.text) ||
        (!SENTENCE_END.test(last.text) && (line.length <= 6 || last.text.length <= 6 || line.startsWith('('))))
    ) {
      last.text = joinPiece(last.text, line);
      continue;
    }
    blocks.push({ type: 'text', text: line });
  }
  close();
  return blocks;
}
