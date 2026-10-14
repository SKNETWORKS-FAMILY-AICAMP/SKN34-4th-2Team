/**
 * 수정안에서 실제로 새로 들어간 글자만 굵게 — job_resume_review_dialog.dart 의 _changedRevisionSpans.
 *
 * 원문과 수정안을 LCS 로 비교하므로 앞 · 뒤에 여러 수정이 있어도 바뀌지 않은 가운데 문장이
 * 함께 굵어지지 않는다. 원문에서 지운 글자는 수정안에 보이지 않는다.
 */
export interface DiffSpan {
  text: string;
  changed: boolean;
}

export function changedRevisionSpans(original: string, revision: string): DiffSpan[] {
  if (original === revision) return [{ text: revision, changed: false }];
  const before = Array.from(original);
  const after = Array.from(revision);
  if (before.length === 0) return [{ text: revision, changed: true }];
  if (after.length === 0) return [];
  // 긴 문장을 여러 장 보여도 화면이 무거워지지 않도록 상한을 둔다
  if (before.length * after.length > 300000) return fallbackSpans(before, after);

  const width = after.length + 1;
  const table = new Uint16Array((before.length + 1) * width);
  for (let i = before.length - 1; i >= 0; i--) {
    for (let j = after.length - 1; j >= 0; j--) {
      table[i * width + j] =
        before[i] === after[j]
          ? table[(i + 1) * width + j + 1] + 1
          : Math.max(table[(i + 1) * width + j], table[i * width + j + 1]);
    }
  }
  const chars: string[] = [];
  const changed: boolean[] = [];
  let i = 0;
  let j = 0;
  while (i < before.length && j < after.length) {
    if (before[i] === after[j]) {
      chars.push(after[j]);
      changed.push(false);
      i++;
      j++;
    } else if (table[(i + 1) * width + j] >= table[i * width + j + 1]) {
      i++;
    } else {
      chars.push(after[j]);
      changed.push(true);
      j++;
    }
  }
  while (j < after.length) {
    chars.push(after[j++]);
    changed.push(true);
  }
  return buildSpans(chars, changed);
}

function fallbackSpans(before: string[], after: string[]): DiffSpan[] {
  let prefix = 0;
  while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) prefix++;
  let suffix = 0;
  while (
    suffix < before.length - prefix &&
    suffix < after.length - prefix &&
    before[before.length - 1 - suffix] === after[after.length - 1 - suffix]
  ) {
    suffix++;
  }
  return buildSpans(
    after,
    after.map((_, index) => index >= prefix && index < after.length - suffix),
  );
}

function buildSpans(chars: string[], changed: boolean[]): DiffSpan[] {
  const spans: DiffSpan[] = [];
  let start = 0;
  while (start < chars.length) {
    const isChanged = changed[start];
    let end = start + 1;
    while (end < chars.length && changed[end] === isChanged) end++;
    spans.push({ text: chars.slice(start, end).join(''), changed: isChanged });
    start = end;
  }
  return spans;
}
