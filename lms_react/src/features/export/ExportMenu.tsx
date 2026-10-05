import { useState } from 'react';

import { Icon } from '../../ui/Icon';
import { MoreMenu } from '../../ui/MoreMenu';
import { Button } from '../../ui/components';
import { exportTable, type ExportFormat, type ExportTable } from './tableExport';

const ITEMS: { format: ExportFormat; icon: string; label: string; hint: string }[] = [
  { format: 'xlsx', icon: 'table_view', label: 'Excel (.xlsx)', hint: '머리줄 고정 · 필터 포함' },
  { format: 'csv', icon: 'csv', label: 'CSV', hint: '다른 프로그램으로 옮길 때' },
  { format: 'docx', icon: 'description', label: 'Word (.docx)', hint: '한글(HWP)에서도 열 수 있어요' },
  { format: 'pdf', icon: 'picture_as_pdf', label: 'PDF', hint: '인쇄 창에서 「PDF로 저장」을 고르세요' },
];

/** 「내려받기 ▾」 — 표 하나를 고른 형식으로 내려받는다. 표는 고를 때 만든다. */
export function ExportMenu({
  build,
  fileName,
  disabled = false,
  label = '내려받기',
  size = 'sm',
}: {
  build(): ExportTable;
  /** 확장자 없는 파일 이름 */
  fileName: string;
  disabled?: boolean;
  label?: string;
  size?: 'sm' | 'md';
}) {
  const [busy, setBusy] = useState(false);

  if (disabled || busy) {
    return (
      <Button size={size} variant="outline" disabled icon={<Icon name="download" size={16} />}>
        {busy ? '만드는 중…' : label}
      </Button>
    );
  }

  const run = (format: ExportFormat) => {
    setBusy(true);
    exportTable(build(), fileName, format)
      .catch((err: unknown) => window.alert(err instanceof Error ? err.message : '내려받지 못했습니다.'))
      .finally(() => setBusy(false));
  };

  return (
    <MoreMenu
      label={label}
      icon="download"
      className={`btn btn--outline btn--${size}`}
      items={ITEMS.map((item) => ({ key: item.format, icon: item.icon, label: item.label, hint: item.hint, onSelect: () => run(item.format) }))}
    />
  );
}
