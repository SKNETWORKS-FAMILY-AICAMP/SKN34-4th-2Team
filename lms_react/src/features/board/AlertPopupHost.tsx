import { useEffect, useState } from 'react';

import { dismissAlertToday, useAlertPopups, useDb } from '../../data/repository';
import { dateKeyOf } from '../../data/seed';
import { useTour } from '../../tour/useTour';
import { Button, Dialog } from '../../ui/components';
import { useSession } from '../auth/session';

/**
 * 알림 팝업 — features/shell/widgets/alert_popup_host.dart
 *
 * 관리자가 띄운 팝업을 로그인 직후 보여 준다. 「오늘 하루 보지 않기」는
 * 날짜별로 기억한다. 온보딩 투어가 떠 있는 동안은 투어가 끝난 뒤에 띄운다.
 */
const SHOWN_KEY_PREFIX = 'lms_react_alert_shown:';

function storageKey(uid: string): string {
  return `${SHOWN_KEY_PREFIX}${uid}`;
}

function readShown(uid: string): string[] {
  try {
    return JSON.parse(window.sessionStorage.getItem(storageKey(uid)) ?? '[]') as string[];
  } catch {
    return [];
  }
}

function remember(uid: string, ids: string[]): void {
  try {
    window.sessionStorage.setItem(storageKey(uid), JSON.stringify(ids));
  } catch {
    /* 무시 */
  }
}

export function AlertPopupHost() {
  const { user } = useSession();
  const tour = useTour();
  const popups = useAlertPopups();
  const dismissals = useDb((db) => (user === null ? {} : db.alertDismissals[user.uid] ?? {}));
  const [closed, setClosed] = useState<string[]>([]);

  // 계정마다 따로 기억한다. (관리자가 닫은 기록이 학생에게 넘어가지 않게)
  useEffect(() => {
    if (user === null) {
      setClosed([]);
      return;
    }
    setClosed(readShown(user.uid));
  }, [user?.uid]);

  // 투어(z-index 1000)가 다이얼로그(900)를 가리므로, 투어가 끝난 뒤에만 띄운다.
  const tourBlocking = tour.active && tour.state !== null;

  if (user === null || tourBlocking) return null;

  const today = dateKeyOf(new Date());
  const nowHm = new Date().toTimeString().slice(0, 5);

  const visible = popups
    .filter((p) => {
      if (!p.isActive) return false;
      if (dismissals[p.id] === today) return false;
      if (closed.includes(p.id)) return false;
      if (p.startTime !== undefined && nowHm < p.startTime) return false;
      if (p.endTime !== undefined && nowHm > p.endTime) return false;
      return true;
    })
    .sort((a, b) => a.sortOrder - b.sortOrder);

  const popup = visible[0];
  if (popup === undefined) return null;

  const closeOne = () => {
    setClosed((c) => {
      const next = [...c, popup.id];
      remember(user.uid, next);
      return next;
    });
  };

  return (
    <Dialog
      title={popup.title}
      onClose={closeOne}
      actions={
        <>
          <Button
            variant="text"
            onClick={() => {
              dismissAlertToday(user.uid, popup.id);
              closeOne();
            }}
          >
            오늘 하루 보지 않기
          </Button>
          <Button onClick={closeOne}>확인</Button>
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
