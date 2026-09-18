import { useState } from 'react';


import { dismissAlertToday, useAlertPopups, useDb } from '../../data/repository';
import { dateKeyOf } from '../../data/seed';
import { useSession } from '../auth/session';
import { Button, Dialog } from '../../ui/components';

/**
 * 알림 팝업 — features/shell/widgets/alert_popup_host.dart
 *
 * 관리자가 띄운 팝업을 로그인 직후 한 번 보여 준다. 「오늘 하루 보지 않기」는
 * 날짜별로 기억한다.
 */
const SHOWN_KEY = 'lms_react_alert_shown';

function readShown(): string[] {
  try {
    return JSON.parse(window.sessionStorage.getItem(SHOWN_KEY) ?? '[]') as string[];
  } catch {
    return [];
  }
}

function remember(ids: string[]): void {
  try {
    window.sessionStorage.setItem(SHOWN_KEY, JSON.stringify(ids));
  } catch {
    /* 무시 */
  }
}

export function AlertPopupHost() {
  const { user } = useSession();
  const popups = useAlertPopups();
  const dismissals = useDb((db) => (user === null ? {} : db.alertDismissals[user.uid] ?? {}));
  // 화면을 옮길 때마다 다시 뜨지 않게 한 세션에 한 번만 보여 준다.
  const [closed, setClosed] = useState<string[]>(() => readShown());

  if (user === null) return null;

  const today = dateKeyOf(new Date());
  const nowHm = new Date().toTimeString().slice(0, 5);

  const visible = popups.filter((p) => {
    if (!p.isActive) return false;
    if (dismissals[p.id] === today) return false;
    if (closed.includes(p.id)) return false;
    if (p.startTime !== undefined && nowHm < p.startTime) return false;
    if (p.endTime !== undefined && nowHm > p.endTime) return false;
    return true;
  });

  const popup = visible[0];
  if (popup === undefined) return null;

  return (
    <Dialog
      title={popup.title}
      onClose={() => setClosed((c) => {
                const next = [...c, popup.id];
                remember(next);
                return next;
              })}
      actions={
        <>
          <Button
            variant="text"
            onClick={() => {
              dismissAlertToday(user.uid, popup.id);
              setClosed((c) => {
                const next = [...c, popup.id];
                remember(next);
                return next;
              });
            }}
          >
            오늘 하루 보지 않기
          </Button>
          <Button onClick={() => setClosed((c) => {
                const next = [...c, popup.id];
                remember(next);
                return next;
              })}>확인</Button>
        </>
      }
    >
      <p className="muted" style={{ whiteSpace: 'pre-wrap' }}>
        {popup.content}
      </p>
      {popup.linkUrl !== undefined && (
        <a href={popup.linkUrl} target="_blank" rel="noreferrer">
          자세히 보기
        </a>
      )}
      <span className="hint">{popup.authorName}</span>
    </Dialog>
  );
}
