import * as Print from 'expo-print';
import * as Sharing from 'expo-sharing';

import type { ManualRole } from './content';
import { manualHtml } from './html';

/**
 * 역할에 맞는 모바일 사용 설명서를 PDF 로 만들어 공유 시트로 연다.
 * 공유 시트에서 미리 보기 · 파일에 저장 · 다른 앱으로 보내기를 할 수 있다.
 * 공유를 못 쓰는 기기면 인쇄 미리 보기로 띄운다. 화면 캡처는 src/manual/shots.ts 에 들어 있다.
 */
/** A4 (pt) — iOS 는 CSS @page 여백을 무시해서 여백도 여기서 준다 */
const A4 = { width: 595, height: 842 };
const MARGINS = { top: 44, bottom: 50, left: 42, right: 42 };

export async function openManualPdf(role: ManualRole): Promise<void> {
  const html = manualHtml(role);
  if (await Sharing.isAvailableAsync()) {
    const file = await Print.printToFileAsync({ html, ...A4, margins: MARGINS });
    await Sharing.shareAsync(file.uri, { mimeType: 'application/pdf', UTI: 'com.adobe.pdf', dialogTitle: 'PLAYDATA 모바일 사용 설명서' });
    return;
  }
  await Print.printAsync({ html });
}
