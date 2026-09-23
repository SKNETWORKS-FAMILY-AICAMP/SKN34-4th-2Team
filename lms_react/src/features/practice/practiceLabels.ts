import type { PracticeKind } from '../../domain/types';

/** 문제 종류 이름 — 화면 여러 곳(문제 셀·대시보드·강사 화면·파일 내보내기)이 같이 쓴다. 편집기를 끌고 오지 않게 따로 둔다 */
export const KIND_LABEL: Record<PracticeKind, string> = {
  concept: '개념',
  code_output: '출력 예상',
  code_blank: '빈칸 채우기',
  code_fix: '디버깅',
  code_write: '함수 작성',
  code_scratch: '처음부터',
};
