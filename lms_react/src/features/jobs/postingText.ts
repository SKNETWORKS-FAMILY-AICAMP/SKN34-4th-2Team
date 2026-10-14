/**
 * 수집한 공고 원문을 읽기 좋은 덩어리로 정리한다.
 *
 * 수집기는 채용 사이트 화면의 글을 줄 단위로 떠 온다. 그래서
 * - 사람인: 글머리표(ㆍ · • -)가 혼자 한 줄이고 내용이 다음 줄에 온다
 * - 잡코리아: 글자 꾸밈 단위로 문장이 조각난다(`Python\n프로그래밍 숙련\n:\n객체지향\n,\n…`)
 * - 소제목 앞에 이모지(📋 주요업무)가 붙는다
 * - 사람인 간편 양식 공고: 본문 대신 `업종<탭>방송사·케이블 > 미디어` 같은 표와,
 *   `선택 : 마케팅·홍보·조사 > 직무·직업 > 브랜드마케팅` 같은 직종 분류가 서른 줄 넘게 온다
 * 원문 글자는 바꾸지 않고 줄만 다시 잇는다. 양식 표는 칸 이름 · 값으로, 직종 분류는 대분류별 묶음으로 모은다.
 */
export type PostingBlock =
  | { type: 'heading'; text: string }
  | { type: 'sub'; text: string }
  /** 직무별로 칸이 되풀이되는 공고의 직무 이름(「Technical Writer」 「차장급 ( 1명 )」) */
  | { type: 'role'; text: string }
  | { type: 'item'; text: string }
  | { type: 'text'; text: string }
  | { type: 'form'; rows: PostingFormRow[] }
  /** 이미지로 된 부분. urls 는 원래 이미지 주소(사람인 이미지 서버), lines 는 거기서 뽑은 글 */
  | { type: 'image'; urls: string[]; lines: string[] };

/** 글 블록 — 양식 표가 아닌 것 */
export type PostingTextBlock = Exclude<PostingBlock, { type: 'form' } | { type: 'image' }>;

// 이미지 속 글(사람인이 뽑아 둔 것)이 시작하고 끝나는 자리. stripDebris 가 코드 껍데기 대신 넣는다
const IMAGE_START = '\u0001이미지글시작';
const IMAGE_END = '\u0001이미지글끝';
const HANGUL = /[가-힣]/;

/** 양식 표 한 행. 직종처럼 분류가 여러 개면 대분류별로 묶는다 */
export type PostingFormRow =
  | { label: string; value: string }
  | { label: string; groups: { name: string; items: string[] }[] };

// 「업종<탭>방송사·케이블 > 미디어」 — 칸 이름은 짧은 말이고 탭으로 값과 나뉜다
const FORM_FIELD = /^([가-힣A-Za-z][가-힣A-Za-z ]{0,9})\t+(.+)$/;
// 「선택 : 대분류 > 중분류 > 소분류」. 중분류(직무·직업 · 전문분야)는 사이트 분류라 버린다
const FORM_CATEGORY = /^선택\s*:\s*(.+?)\s*>\s*.+?\s*>\s*(.+)$/;

/** 혼자 있으면 「다음 줄이 목록 한 항목」이라는 표시 */
const BULLET = /^[ㆍ·•‧∙◦○●■□▪▫※▶►▷✔✓☑✅◆◇★☆º\-–—*]$/;
/** 줄 앞에 붙은 글머리표 */
const LEADING_BULLET = /^[ㆍ·•‧∙◦○●■□▪▫※▶►▷✔✓☑✅◆◇★☆º\-–—*]\s*/;
/** 번호 표시만 있는 줄: 1. / 1) / ① */
// 「01」 「02」처럼 0으로 시작하는 두 자리도 소제목 번호다. 앞 문장 끝에 「… 팀 02」로 붙던 것
const NUMBER = /^(?:\d{1,2}[.)]|0\d|[①-⑳])$/;
/** 번호만 든 소제목(「2. 」) — 다음 줄을 제목으로 받을 차례다 */
const NUMBER_ONLY = /^\s*(?:\d{1,2}[.)]|0\d|[①-⑳])\s*$/;
const LEADING_NUMBER = /^(?:\d{1,2}[.)]|[①-⑳])\s*/;

const SECTION_WORDS = [
  '상세요강', '모집부문', '모집분야', '포지션및자격요건', '포지션', '담당업무', '주요업무', '업무내용', '하는일',
  '자격요건', '자격사항', '지원자격', '필수요건', '필수사항', '우대사항', '우대조건', '우대요건', '기술스택', '스킬', '사용기술',
  '근무조건', '근무환경', '근무지', '근무지역', '근무시간', '급여', '복지', '복리후생', '복지및혜택', '혜택',
  '채용절차', '전형절차', '접수기간', '접수방법', '제출서류', '유의사항', '기타사항', '참고사항', '회사소개', '기업소개',
];

/** 제목 앞 장식 기호(「◎ 근무조건」 「┃ 근무조건」 「■ 담당업무」). 목록 글머리표(ㆍ · • -)는 넣지 않는다 */
// 「??」는 수집할 때 깨진 이모지다(「?? 우대사항」)
const DECOR = /^(?:[◎●○■□▪▫◆◇★☆▶►▷※┃│▣◈❖✔✓☑✅º#]+|\?{2,})\s*/;
/** 섹션 이름 앞에 붙는 한정어(「공통 자격요건」 「그 외 우대사항」) */
const SECTION_PREFIXES = ['공통', '그외', '기타', '추가', '세부', '상세'];
/** 섹션 이름 두 개를 「및」으로 묶은 제목(「지원자격 및 우대사항」) */
const isJoinedSection = (key: string) => {
  const parts = key.split('및');
  return parts.length === 2 && parts.every((p) => SECTION_WORDS.includes(p));
};

/** 이모지 · 장식 기호 · 괄호 · 콜론을 뗀 제목 글자 */
function headingCore(line: string): string {
  return line
    .replace(/\p{Extended_Pictographic}|\uFE0F|\u200D/gu, '')
    .trim()
    .replace(DECOR, '')
    .replace(/^[[【<〈《(]\s*|\s*[\]】>〉》)]$/g, '')
    .replace(/[:：]\s*$/, '')
    .trim();
}

function isHeading(line: string): boolean {
  const core = headingCore(line);
  if (core === '' || core.length > 20) return false;
  const key = core.replace(/[\s·&]/g, '');
  if (SECTION_WORDS.includes(key) || isJoinedSection(key)) return true;
  if (SECTION_PREFIXES.some((p) => key.startsWith(p) && SECTION_WORDS.includes(key.slice(p.length)))) return true;
  // 「[주요 업무]」처럼 괄호로 싼 짧은 줄, 이모지로 시작하는 짧은 줄도 소제목으로 본다
  return (
    (/^\s*[[【]/.test(line) && /[\]】]\s*$/.test(line)) || /^\p{Extended_Pictographic}/u.test(line.trim()) || isCapsHeading(core)
  );
}

/**
 * 「TECH STACK」 「OUR PEOPLE」 「BENEFITS」처럼 영어 대문자로만 된 짧은 줄. 기술 이름(「AWS EC2」 「RDS」 「NGINX」)이
 * 소제목이 되지 않게 글자가 여섯 자 넘고, 두 낱말 이상이면 네 글자 넘는 낱말이, 한 낱말이면 일곱 자 넘어야 한다
 */
function isCapsHeading(core: string): boolean {
  if (!/^[A-Z][A-Z'’&. ]+$/.test(core)) return false;
  const words = core.split(/\s+/).filter((w) => w !== '');
  const letters = (w: string) => w.replace(/[^A-Z]/g, '').length;
  if (letters(core) < 6) return false;
  return words.length >= 2 ? words.some((w) => letters(w) >= 4) : letters(core) >= 7;
}

/** 앞말에 붙여 쓰는 조각: 문장 부호로 시작하거나 부호만 있는 줄 */
const ATTACH_TIGHT = /^[,.:;)\]」』’”%!?·/]/;
/** 이 글자로 끝나면 다음 줄을 띄우지 않고 붙인다 */
const OPENS = /[([「『‘“/·]$/;
/** 조사 · 어미로 시작하는 조각은 앞말에 바로 붙는다(하이브랩\n은 → 하이브랩은) */
const PARTICLE = /^(?:은|는|이|가|을|를|의|에|에서|로|으로|와|과|도|만|할|하는|한|된|되는|입니다|합니다)(?=\s|$|[.,])/;
const SENTENCE_END = /(?:[.!?。]|다|요|니다|함|음|임)$/;
/** 목록 항목이 끝났다 — 문장 끝이거나 「~분 · ~자 · ~것」 같은 항목 끝말 */
const ITEM_END = /(?:[.!?。)]|다|요|니다|함|음|임|분|자|것|님)$/;
/** 조사로 끝났으면 문장이 이어진다(하이브랩은 → 다음 줄) */
const ENDS_WITH_PARTICLE = /(?:은|는|을|를|의|와|과|로|에|이|가)$/;

/** 웹 주소로 끝난 글. 주소 끝의 「/」 뒤에 다음 줄을 붙이지 않는다(「…imagebakery.tv/㈜시아디자인그룹은 …」) */
// 「-」 「_」로 끝나면 줄이 바뀐 긴 주소의 앞부분이라 잇는다(「…/face-analyzer-」 「facial-landmarks…」)
const URL_END = /https?:\/\/\S*[^\s\-_]$/;
/** 구분선만 있는 줄, 줄 앞의 구분선 */
const DIVIDER = /^[-=_*~─━·.]{4,}$/;
const DIVIDER_LEAD = /^[-=_*~─━]{4,}\s*/;
/** 글머리표를 달아도 제목으로 보는 섹션 이름. 항목으로 흔히 쓰는 말(급여 · 복지 · 근무지)은 뺐다 */
const BULLETED_SECTIONS = new Set([
  '주요업무', '담당업무', '업무내용', '자격요건', '지원자격', '자격사항', '필수요건', '필수사항', '우대사항', '우대조건',
  '우대요건', '근무조건', '복리후생', '채용절차', '전형절차', '제출서류', '접수방법', '접수기간', '유의사항', '모집부문', '모집분야',
]);

function joinPiece(prev: string, piece: string): string {
  if (prev === '') return piece;
  if (ATTACH_TIGHT.test(piece)) return prev + (piece.startsWith(':') ? piece.replace(/^:\s*/, ': ') : piece);
  if (OPENS.test(prev) && !URL_END.test(prev)) return prev + piece;
  if (PARTICLE.test(piece)) return prev + piece;
  if (/:$/.test(prev)) return `${prev} ${piece}`;
  return `${prev} ${piece}`;
}

function normalize(line: string): string {
  return line.replace(/[\u00a0\t\r]/g, ' ').replace(/\s{2,}/g, ' ').trim();
}

/** 양식 표 줄이면 칸 이름 · 값(분류면 대분류 · 소분류). 아니면 null. 탭을 지우기 전 줄을 본다 */
function formLine(rawLine: string): { label: string | null; value: string; category: [string, string] | null } | null {
  const text = rawLine.replace(/\r/g, '').trim();
  const field = FORM_FIELD.exec(text);
  const label = field ? field[1].trim() : null;
  // 「근무형태<탭>:<탭>정규직」처럼 값 앞에 쌍점이 붙기도 한다
  const value = field ? normalize(field[2]).replace(/^:\s*/, '') : normalize(text);
  // 「지원자격<탭>및 우대사항」은 표가 아니라 탭에 끊긴 소제목이다. 값이 비었거나 「및」으로 시작하면 글로 둔다
  if (field && (value === '' || /^및(\s|$)/.test(value) || /\s및$/.test(label ?? ''))) return null;
  const category = FORM_CATEGORY.exec(value);
  if (category) return { label, value, category: [category[1], normalize(category[2])] };
  return field ? { label, value, category: null } : null;
}

/**
 * 수집 글에 섞여 온 찌꺼기를 걷어 낸다.
 * - 사람인이 이미지 속 글을 뽑아 둔 결과가 코드 모양 그대로 들어온다(2026-09-30 열린 공고 37건):
 *   `array ('status' => 'success', 'imageUrl' => '…', 'reason' => '', 'text' => '…글…',)`. 이미지 주소와 글만 남긴다
 */
function stripDebris(raw: string): string {
  return raw
    .replace(
      /array\s*\(\s*'status'\s*=>\s*'[^']*',\s*'imageUrl'\s*=>\s*'([^']*)',\s*'reason'\s*=>\s*'[^']*',\s*'text'\s*=>\s*'/g,
      (_, url: string) => `\n${IMAGE_START} ${url}\n`,
    )
    .replace(/'\s*,\s*\r?\n\s*\)/g, `\n${IMAGE_END}\n`)
    .replace(/\\'/g, "'");
}

/** `[` · `자격요건` · `]`처럼 세 줄로 나뉜 대괄호 소제목을 한 줄로 잇는다(잡코리아) */
function joinBrackets(lines: string[]): string[] {
  const out: string[] = [];
  for (let i = 0; i < lines.length; i += 1) {
    const inner = lines[i + 1]?.trim() ?? '';
    if (lines[i].trim() === '[' && lines[i + 2]?.trim() === ']' && inner !== '' && inner.length <= 20) {
      out.push(`[${inner}]`);
      i += 2;
      continue;
    }
    out.push(lines[i]);
  }
  return out;
}

/**
 * 페이지 안 탭 메뉴(「일하는 방식 · 복지 · 회사 소개」)를 뺀다. 뒤에 같은 이름의 소제목이 또 나와 겹쳐 보였다.
 * 「·」 「|」로 나뉜 짧은 조각이 셋 이상이고, 그중 둘 이상이 뒤에서 소제목 · 줄 첫머리로 다시 나오면 메뉴다
 */
function dropMenus(lines: string[]): string[] {
  const keys = lines.map((l) => l.replace(/\s/g, ''));
  return lines.filter((line, i) => {
    const parts = line.split(/\s*[·|｜]\s*/).map((p) => p.replace(/\s/g, ''));
    if (parts.length < 3 || parts.some((p) => p === '' || p.length > 10)) return true;
    const later = keys.slice(i + 1);
    return parts.filter((p) => later.some((k) => k.startsWith(p))).length < 2;
  });
}

/**
 * 바로 앞 구간이 통째로 한 번 더 들어온 것을 뺀다(잡코리아 위즈덤마인드 공고의 「기간과 근무지역」 여섯 줄).
 * 세 줄 넘고 글자도 충분한 구간이 곧바로 다시 나올 때만 뺀다. 직무마다 같은 요건이 되풀이되는 공고는
 * 사이에 직무 이름이 끼어 있어 그대로 둔다
 */
function dropRepeats(lines: string[]): string[] {
  const kept = lines.filter((l) => l.trim() !== '');
  const key = (l: string) => l.replace(/\s/g, '');
  const out: string[] = [];
  for (let i = 0; i < kept.length; ) {
    out.push(kept[i]);
    i += 1;
    for (let k = Math.min(out.length, kept.length - i, 60); k >= 3; k -= 1) {
      const run = out.slice(out.length - k);
      if (run.join('').replace(/\s/g, '').length < 15) break;
      if (run.every((l, j) => key(l) === key(kept[i + j]))) {
        i += k;
        break;
      }
    }
  }
  return out;
}

/** 잡코리아 빈 양식의 채움 문구. 회사가 내용을 안 채우고 올린 것이다 */
const PLACEHOLDER = /^[ㆍ·•\-\s]*상세\s*내용을\s*입력하세요\.?$/;
/** 「( 1명 )」 「( 신입/경력 ○명 )」 — 혼자 있으면 바로 앞 줄이 직무 이름이다 */
const HEADCOUNT = /^\(\s*[^()]{0,15}명\s*\)$/;
const ROLE = '\u0001직무';

/**
 * 직무가 여럿인 공고(「과장 ( 1명 )」 · 「차장급 ( 1명 )」)는 직무마다 같은 칸이 되풀이된다. 직무 이름이
 * 앞 항목 끝에 붙어 버리면 같은 글이 두 번 나온 것처럼 보였다. 직무 이름 + 인원 줄을 소제목 표시로 묶는다
 */
function markRoles(lines: string[]): string[] {
  const out: string[] = [];
  for (const line of lines) {
    const prev = out[out.length - 1];
    const name = prev === undefined ? '' : normalize(prev);
    // 잡코리아 빈 양식: 직무 이름 자리에 「포지션」 제목만 있고 인원이 따라온다. 인원만으로는 뜻이 없어 버린다
    if (HEADCOUNT.test(normalize(line)) && name !== '' && isHeading(name)) continue;
    if (
      HEADCOUNT.test(normalize(line)) &&
      name !== '' &&
      name.length <= 30 &&
      !name.startsWith(ROLE) &&
      !isHeading(name) &&
      !BULLET.test(name) &&
      !LEADING_BULLET.test(name)
    ) {
      out[out.length - 1] = `${ROLE}${name} ${normalize(line)}`;
      continue;
    }
    out.push(line);
  }
  return out;
}

/**
 * 직무별 표 공고(새솔테크: Technical Writer · 사업본부 제품 기획자 · 신사업팀 사업관리 담당자)는 표마다 직무 칸이 있는데,
 * 직무 이름 없이 「자격사항 · 우대사항」만 되풀이돼 보였다. 잡코리아가 직무 칸 글을 낱말마다 줄로 나눠(「사업본부」 「제품 기획자」)
 * 앞 항목에 붙었기 때문이다. 근무조건 표에서는 같은 이름이 한 줄로 온전히 나오고 바로 뒤에 「1) 근무형태」가 온다.
 * 번호 줄 바로 앞의 짧은 이름이 공고 안에 두 번 넘게(조각난 것 포함) 나오면 직무로 보고, 나오는 곳마다 소제목으로 끊는다
 */
function markTableRoles(lines: string[]): string[] {
  const norm = lines.map(normalize);
  const key = (s: string) => s.replace(/\s/g, '');
  // 목록 항목 · 제목 · 번호 · 문장이 아닌 짧은 줄
  const plain = (i: number) => {
    const line = norm[i];
    return (
      line.length >= 2 &&
      line.length <= 30 &&
      !line.startsWith('\u0001') &&
      !isHeading(line) &&
      !BULLET.test(line) &&
      !LEADING_BULLET.test(line) &&
      !NUMBER.test(line) &&
      !LEADING_NUMBER.test(line) &&
      !/[.!?。:]$|(?:다|요)$/.test(line) &&
      !(i > 0 && BULLET.test(norm[i - 1]))
    );
  };
  const names = new Map<string, string>();
  norm.forEach((line, i) => {
    const next = norm[i + 1] ?? '';
    if (plain(i) && line.length >= 3 && (NUMBER.test(next) || /^1[.)]/.test(next))) names.set(key(line), line);
  });
  if (names.size === 0) return lines;

  // 이름마다 나오는 자리: 이어진 줄 1~4개를 붙인 글이 이름과 같은 곳
  const spots = new Map<string, [number, number][]>();
  for (let i = 0; i < norm.length; i += 1) {
    let joined = '';
    for (let k = 0; k < 4 && i + k < norm.length && plain(i + k); k += 1) {
      joined += key(norm[i + k]);
      if (names.has(joined)) spots.set(joined, [...(spots.get(joined) ?? []), [i, k + 1]]);
    }
  }
  const out = [...lines];
  for (const [name, found] of spots) {
    if (found.length < 2) continue;
    for (const [start, count] of found) {
      out[start] = `${ROLE}${names.get(name)}`;
      for (let j = 1; j < count; j += 1) out[start + j] = '';
    }
  }
  return out;
}

/**
 * 수집할 때 공고 대신 받은 사이트 안내 페이지인가. 2026-09-29 잡코리아 수집 한 번이 「접속이 일시적으로 제한」 안내를
 * 글자가 깨진 채(UTF-8 을 Latin-1 로 읽음) 공고 본문으로 저장했다(열린 공고 370건). 원문 대신 안내를 보여 줄 때 쓴다
 */
export function isBrokenBody(raw: string): boolean {
  if (/helpdesk@albamon\.com/.test(raw)) return true;
  // 깨진 한글: ì ë ê í 다음에 제어 영역 글자가 오는 짝이 잔뜩 있다
  return (raw.match(/[ìëêíã][\u0080-¿]/g) ?? []).length >= 20;
}

export function formatPostingText(raw: string): PostingBlock[] {
  const blocks: PostingBlock[] = [];
  /** 목록 항목 · 번호 소제목은 다음 표시나 소제목이 나올 때까지 줄을 이어 붙인다 */
  let open: PostingTextBlock | null = null;

  const close = () => {
    if (open !== null && open.text.trim() !== '') blocks.push({ ...open, text: open.text.trim() });
    open = null;
  };

  /** 이어지는 양식 표. 칸 이름 없이 이어지는 직종 분류 줄은 그 위 분류 칸에 묶는다 */
  let form: Extract<PostingBlock, { type: 'form' }> | null = null;

  /**
   * 이미지 속 글. 포스터를 글자만 뽑아 줄 순서 · 배치가 흐트러져 있어 소제목 · 목록으로 나누지 않고 줄 그대로 둔다.
   * 한글이 없는 줄(영어 번역 · 깨진 영어 · 「-0-0-0-」)과 바로 앞과 같은 줄은 뺀다
   */
  let image: Extract<PostingBlock, { type: 'image' }> | null = null;

  /** 채움 문구만 들어 있던 소제목. 아래에 아무것도 남지 않으면 소제목도 뺀다 */
  const emptied = new Set<PostingBlock>();

  /** 바로 앞 줄이 구분선이었다 — 다음 글을 앞 문단에 잇지 않는다 */
  let afterBreak = false;

  for (const rawLine of markTableRoles(markRoles(dropRepeats(dropMenus(joinBrackets(stripDebris(raw).split('\n'))))))) {
    // 구분선(「-----」 「*****」)은 버리고, 줄 앞에 붙은 구분선은 뗀다
    const plainLine = normalize(rawLine);
    // 구분선은 앞뒤 글을 가르는 경계다. 지우기만 하면 뒤 줄이 앞 항목에 붙었다
    if (DIVIDER.test(plainLine)) {
      close();
      afterBreak = true;
      continue;
    }
    const line = plainLine.replace(DIVIDER_LEAD, '');
    if (line !== plainLine) {
      close();
      afterBreak = true;
    }
    // 사람인 페이지 제목 · 템플릿 꼬리말 · 점핏 광고. 앞 항목에 이어 붙기 전에 뺀다
    if (SITE_TITLE.test(line)) continue;
    const broken = afterBreak;
    afterBreak = false;
    if (line === '') continue;
    if (PLACEHOLDER.test(line)) {
      const last = blocks[blocks.length - 1];
      if (open === null && last?.type === 'heading') emptied.add(last);
      continue;
    }
    if (line.startsWith(IMAGE_START)) {
      close();
      form = null;
      // 이미지 여러 장이 이어지면 한 칸에 모은다
      const last = blocks[blocks.length - 1];
      image = last?.type === 'image' ? last : { type: 'image', urls: [], lines: [] };
      if (image !== last) blocks.push(image);
      // 링크로만 쓴다(화면에 띄우지 않는다 — 사람인 약관의 무단 재제공 금지). 웹 주소만 받는다
      const url = line.slice(IMAGE_START.length).trim();
      if (/^https?:\/\/[^\s"'<>]+$/.test(url) && !image.urls.includes(url)) image.urls.push(url);
      continue;
    }
    if (line === IMAGE_END) {
      image = null;
      continue;
    }
    if (image !== null) {
      const text = line.replace(ROLE, '');
      if (HANGUL.test(text) && image.lines[image.lines.length - 1] !== text) image.lines.push(text);
      continue;
    }
    if (line.startsWith(ROLE)) {
      close();
      form = null;
      blocks.push({ type: 'role', text: line.slice(ROLE.length) });
      continue;
    }
    const cell = formLine(rawLine);
    if (cell !== null) {
      close();
      if (form === null) {
        form = { type: 'form', rows: [] };
        blocks.push(form);
      }
      const last = form.rows[form.rows.length - 1];
      if (cell.category !== null) {
        const [group, item] = cell.category;
        const row =
          cell.label === null && last !== undefined && 'groups' in last ? last : { label: cell.label ?? '분류', groups: [] };
        if (row !== last) form.rows.push(row);
        const found = row.groups.find((g) => g.name === group);
        if (found === undefined) row.groups.push({ name: group, items: [item] });
        else if (!found.items.includes(item)) found.items.push(item);
      } else {
        form.rows.push({ label: cell.label ?? '', value: cell.value });
      }
      continue;
    }
    form = null;
    // 소제목 옆에 있던 이모지만 한 줄로 떨어져 나온 것. 앞 항목에 붙으면 글 끝에 그림이 남는다
    if (/\p{Extended_Pictographic}/u.test(line) && line.replace(/\p{Extended_Pictographic}|\uFE0F|\u200D|\s/gu, '') === '') continue;
    // 글머리표만 있던 줄 다음의 제목 같은 줄은 보통 항목 내용이다. 이모지 · 장식 기호 · 괄호로 꾸민 제목은 그래도 제목이다
    // (「•」 「📋 자격요건」)
    // 대괄호는 넣지 않는다 — 「•」 「[해외법인] …」처럼 항목 머리말로 흔히 쓴다
    const decorated = /^\p{Extended_Pictographic}/u.test(line) || DECOR.test(line);
    // 번호만 든 소제목(「1.」) 다음 줄은 제목이어도 그 번호의 제목이다(「1.」 「모집부문 및 자격요건」)
    const numbered = open !== null && open.type === 'sub' && NUMBER_ONLY.test(open.text);
    if (isHeading(line) && !numbered && !(open !== null && open.text === '' && !decorated)) {
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
    // 글머리표를 단 섹션 이름(「- 주요업무」 「- 자격요건」)은 제목이다. 헤드헌터 공고가 이렇게 쓴다
    // 쌍점이 달린 「- 접수기간 : 채용시 마감」 「- 제출서류 :」는 「항목명 : 값」 항목이라 그대로 둔다
    if (
      LEADING_BULLET.test(line) &&
      !/[:：]/.test(line) &&
      BULLETED_SECTIONS.has(headingCore(line.replace(LEADING_BULLET, '')).replace(/\s/g, ''))
    ) {
      close();
      blocks.push({ type: 'heading', text: headingCore(line.replace(LEADING_BULLET, '')) });
      continue;
    }
    if (LEADING_BULLET.test(line) && !/^-?\d/.test(line)) {
      close();
      open = { type: 'item', text: line.replace(LEADING_BULLET, '') };
      continue;
    }
    // 번호가 붙은 긴 줄은 소제목이 아니라 번호 매긴 문장이다(「3) 반도체 개발 관련 Tool (…) 역량 보유자」). 문단으로 둔다
    if (LEADING_NUMBER.test(line) && line.length > 40 && !(open?.type === 'sub' && NUMBER_ONLY.test(open.text))) {
      close();
      blocks.push({ type: 'text', text: line });
      continue;
    }
    // 번호만 있는 소제목(「2.」)은 다음 줄을 제목으로 받는다. 내용이 든 소제목이면 새 번호에서 끊는다(「2) 급여 … 3) 근무시간」)
    if (LEADING_NUMBER.test(line) && !(open?.type === 'sub' && NUMBER_ONLY.test(open.text))) {
      close();
      open = { type: 'sub', text: line };
      continue;
    }
    // 영어 공고: 한국어 끝말(다 · 요 · 분)이 없어 항목이 끝났는지 모른다. 그대로 두면 뒤 글을 다 삼켰다(1,227자 항목).
    // 영어 항목 뒤의 「Experience & Education:」 같은 머리말은 소제목, 한글 없는 긴 줄은 새 문단이다
    if (open !== null && open.type === 'item' && open.text.trim() !== '' && !HANGUL.test(open.text) && !HANGUL.test(line)) {
      if (/[:：]$/.test(line) && line.length <= 40) {
        close();
        blocks.push({ type: 'sub', text: line.replace(/\s*[:：]$/, '') });
        continue;
      }
      if (line.length > 30) close();
    }
    // 끝난 목록 항목(「… 관심 있는 분」)에 뒤따르는 긴 줄은 새 문단이다. 이어 붙이면 뒤의 소개 · 복지 · 절차를
    // 통째로 삼켰다(로워드 공고의 마지막 우대사항). 짧은 조각 · 조사로 시작하는 줄만 잇는다(잡코리아 조각 글)
    if (
      open !== null &&
      open.type === 'item' &&
      (ITEM_END.test(open.text.trim()) || URL_END.test(open.text)) &&
      line.length > 8 &&
      // 괄호로 여는 줄은 앞 항목의 보충이다(「Adobe 프로그램 능숙자」 「(인디자인, 일러스트, 포토샵)」)
      !line.startsWith('(') &&
      // 괄호로 끝난 항목 뒤 짧은 조각은 문장의 나머지다(「MS Office(PowerPoint, Word, Excel)」 「활용 능력 상급자」)
      !(open.text.trim().endsWith(')') && line.length <= 12) &&
      !ATTACH_TIGHT.test(line) &&
      !PARTICLE.test(line)
    ) {
      close();
    }
    if (open !== null) {
      // 번호 소제목은 첫 조각만 제목이다. 그 뒤 줄은 목록이 이어 받는다
      // 잡코리아는 소제목도 낱말마다 줄을 나눈다(「2.」 「지원」 「자격 및 역량」). 짧은 조각은 제목에 잇는다
      const fragment = line.length <= 10 && open.text.length < 25 && !SENTENCE_END.test(open.text.trim());
      if (
        open.type === 'sub' &&
        open.text.trim() !== '' &&
        !/[\d.)①-⑳]\s*$/.test(open.text) &&
        !ATTACH_TIGHT.test(line) &&
        !fragment
      ) {
        close();
        blocks.push({ type: 'text', text: line });
        continue;
      }
      open.text = joinPiece(open.text.trimEnd(), line);
      continue;
    }
    // 구분선 바로 뒤의 짧은 줄은 섹션 제목이다(「------」 「포지션 소개」)
    if (broken && line.length <= 15 && !SENTENCE_END.test(line) && !/[.:：]$/.test(line)) {
      blocks.push({ type: 'sub', text: line });
      continue;
    }
    // 자유 글: 조각난 문장만 앞 줄에 잇는다
    const last = blocks[blocks.length - 1];
    if (
      last !== undefined &&
      last.type === 'text' &&
      !broken &&
      !URL_END.test(last.text) &&
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
  return tidyHeadings(
    blocks.filter((block, i) => {
      const next = blocks[i + 1];
      return !(emptied.has(block) && (next === undefined || next.type === 'heading' || next.type === 'sub' || next.type === 'role'));
    }),
  );
}

/** 표 머리칸에 쓰이는 말. 섹션 이름에 표에서만 쓰는 칸 이름을 더한다 */
const HEADER_WORDS = new Set([...SECTION_WORDS, '모집인원', '채용인원', '인원', '근무부서', '모집직무', '직무', '구분', '비고']);
/** 사람인 페이지 제목이 본문 첫 줄로 섞여 온다 */
const SITE_TITLE = /^나에게 딱 맞는 커리어만 매치, 사람인!|\|\s*취업, 채용, 커리어 매칭 플랫폼$|^Saramin Recruitment Template$|^이 포지션의 AI 예상 면접 질문이 궁금하다면 점핏에서 확인해보세요!?$/;

/** 섹션 이름만으로 된 칸(「모집부문」 「자격사항 및 우대사항」). 여럿이 붙은 칸이면 combined */
function headerCell(block: PostingBlock): { combined: boolean } | null {
  if (block.type !== 'heading' && block.type !== 'text') return null;
  const parts = block.text.split(/\s*(?:및|,|·|\/)\s*|\s+/).map((p) => p.replace(/[[\]【】:：]/g, '')).filter((p) => p !== '');
  if (parts.length === 0 || !parts.every((p) => HEADER_WORDS.has(p))) return null;
  // 「복지 및 혜택」 「포지션 및 자격요건」은 칸 둘이 아니라 섹션 이름 하나다
  const whole = headingCore(block.text).replace(/[\s·&]/g, '');
  return { combined: parts.length >= 2 && !SECTION_WORDS.includes(whole) };
}

/**
 * 제목이 겹쳐 보이는 것을 정리한다(2026-09-30 공고 200건 중 69건).
 * - 표 머리칸 줄: 「모집부문 · 모집부문 · 담당업무 · 자격사항 및 우대사항」처럼 섹션 이름만 든 칸이 셋 넘게 이어지고
 *   「A 및 B」 칸이 섞여 있으면 표의 머리 줄이다. 첫 제목만 남긴다
 * - 내용 없이 바로 다음 제목이 오는 제목(사람인 양식의 빈 「복지 및 혜택」, 「채용절차」 → 「접수기간」)은 뺀다.
 *   바로 이어 같은 제목이 또 나오는 것도 이것으로 하나만 남는다
 */
function tidyHeadings(blocks: PostingBlock[]): PostingBlock[] {
  const kept: PostingBlock[] = [];
  for (let i = 0; i < blocks.length; i += 1) {
    const block = blocks[i];
    if ('text' in block && SITE_TITLE.test(block.text)) continue;
    if (block.type === 'heading') {
      let j = i;
      let combined = false;
      for (let cell = headerCell(blocks[j]); cell !== null && j < blocks.length; cell = j < blocks.length ? headerCell(blocks[j]) : null) {
        combined ||= cell.combined;
        j += 1;
      }
      if (j - i >= 3 && combined) {
        kept.push(block);
        i = j - 1;
        continue;
      }
    }
    kept.push(block);
  }
  return nestUnderRoles(splitJoinedHeadings(
    kept.filter((block, i) => !(block.type === 'heading' && (kept[i + 1] === undefined || kept[i + 1].type === 'heading'))),
  ));
}

/** 직무 하나에 딸린 칸 이름. 직무 이름 아래에서는 한 단계 낮은 소제목이다 */
const ROLE_SECTIONS = new Set([
  '담당업무', '주요업무', '업무내용', '하는일', '자격요건', '자격사항', '지원자격', '필수요건', '필수사항',
  '우대사항', '우대조건', '우대요건', '기술스택', '스킬', '사용기술',
]);

/**
 * 직무 이름 아래의 「자격사항 · 우대사항」을 소제목으로 낮춘다. 큰 제목으로 두면 직무 이름이 그 위 우대사항에 딸린
 * 줄처럼 보였다. 직무 칸이 아닌 제목(「근무조건」 「복지」)이 나오면 직무가 끝난다
 */
function nestUnderRoles(blocks: PostingBlock[]): PostingBlock[] {
  let inRole = false;
  return blocks.map((block) => {
    if (block.type === 'role') inRole = true;
    if (block.type !== 'heading') return block;
    if (inRole && ROLE_SECTIONS.has(headingCore(block.text).replace(/[\s·&]/g, ''))) return { type: 'sub', text: block.text };
    inRole = false;
    return block;
  });
}

/**
 * 「포지션 및 자격요건」처럼 둘을 묶은 제목 뒤에 「자격요건」이 제 제목으로 또 나오면 겹쳐 보인다(잡코리아 양식).
 * 뒤에서 따로 나오는 쪽을 떼어 「포지션」으로 줄이고, 다 떼이면 제목을 뺀다
 */
function splitJoinedHeadings(blocks: PostingBlock[]): PostingBlock[] {
  const key = (text: string) => headingCore(text).replace(/[\s·&]/g, '');
  const out: PostingBlock[] = [];
  blocks.forEach((block, i) => {
    if (block.type !== 'heading' || !/\s및\s/.test(block.text)) {
      out.push(block);
      return;
    }
    const later = new Set(blocks.slice(i + 1).flatMap((b) => (b.type === 'heading' ? [key(b.text)] : [])));
    const parts = block.text.split(/\s+및\s+/);
    const rest = parts.filter((p) => !later.has(key(p)));
    if (rest.length === parts.length) out.push(block);
    else if (rest.length > 0) out.push({ type: 'heading', text: rest.join(' 및 ') });
  });
  return out;
}
