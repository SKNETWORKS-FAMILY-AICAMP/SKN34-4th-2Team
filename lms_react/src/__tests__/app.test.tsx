import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { App } from '../app/App';
import {
  adminRoutes,
  appRoutes,
  fullScreenRoutes,
  instructorRoutes,
  studentRoutes,
} from '../app/routes';
import { getDb, mutate, resetDb } from '../data/store';
import { DemoAccounts, DemoConfig } from '../data/seed';
import { debugReset as resetDismiss } from '../tour/dismissStore';
import { debugReset as resetTargets } from '../tour/targetRegistry';

/**
 * 앱을 통째로 띄워 본다. jsdom은 레이아웃을 하지 않아 사각형이 모두 0이므로,
 * 투어 오버레이가 자리를 잡도록 타깃 크기만 거짓으로 채운다.
 */
let container: HTMLDivElement;
let root: Root;

function stubLayout(): void {
  Element.prototype.getBoundingClientRect = function (this: Element) {
    const rect = { x: 10, y: 10, width: 180, height: 40, top: 10, left: 10, right: 190, bottom: 50 };
    return { ...rect, toJSON: () => rect } as DOMRect;
  };
  Element.prototype.scrollIntoView = () => {};
  window.requestAnimationFrame = (cb: FrameRequestCallback) =>
    window.setTimeout(() => cb(performance.now()), 0);
}

async function flush(times = 12): Promise<void> {
  for (let i = 0; i < times; i++) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }
}

async function render(initialPath = '/'): Promise<void> {
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => {
    root.render(
      <MemoryRouter initialEntries={[initialPath]}>
        <App />
      </MemoryRouter>,
    );
  });
  await flush();
}

function click(label: string, scope: HTMLElement = container): void {
  const el = Array.from(scope.querySelectorAll('button, a')).find(
    (b) => b.textContent?.trim() === label,
  );
  if (el === undefined) throw new Error(`"${label}" 요소가 없다`);
  act(() => {
    el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}

/** 아이콘이 붙은 단추 — 아이콘 글자(리거처)를 빼고 이름을 견준다. */
function press(label: string, scope: HTMLElement = container): void {
  const el = Array.from(scope.querySelectorAll('button')).find((b) => {
    const copy = b.cloneNode(true) as HTMLElement;
    copy.querySelectorAll('.icon').forEach((i) => i.remove());
    return copy.textContent?.trim() === label;
  });
  if (el === undefined) throw new Error(`"${label}" 단추가 없다`);
  act(() => {
    el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  });
}

/** jsdom에는 DragEvent가 없다. 이벤트에 빈 dataTransfer를 붙여 끌어다 놓기를 흉내 낸다. */
async function drag(from: HTMLElement, to: HTMLElement): Promise<void> {
  const fire = (el: HTMLElement, type: string) => {
    const e = new Event(type, { bubbles: true, cancelable: true });
    Object.defineProperty(e, 'dataTransfer', {
      value: { setData: () => {}, effectAllowed: 'move', dropEffect: 'move' },
    });
    act(() => {
      el.dispatchEvent(e);
    });
  };
  fire(from, 'dragstart');
  await flush(2);
  fire(to, 'dragover');
  fire(to, 'drop');
  fire(from, 'dragend');
  await flush(2);
}

/** 투어 오버레이가 화면을 덮고 있으면 먼저 닫는다. */
async function dismissTour(): Promise<void> {
  if (container.querySelector('.tour-card') !== null) {
    click('다시 보지 않기', container.querySelector('.tour-card') as HTMLElement);
    await flush();
  }
}

async function loginAs(role: '학생' | '강사' | '관리자'): Promise<void> {
  // 데모 계정 버튼은 「빠른 로그인 (데모)」 안에 접혀 있다.
  click('빠른 로그인 (데모)');
  click(role);
  await flush();
  await dismissTour();
}

beforeEach(() => {
  resetDb();
  resetDismiss();
  resetTargets();
  window.localStorage.clear();
  stubLayout();
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe('로그인', () => {
  it('로그인 전에는 로그인 화면으로 보낸다', async () => {
    await render('/');
    expect(container.querySelector('.login')).not.toBeNull();
  });

  it('데모 계정 버튼으로 역할별 홈에 도착한다', async () => {
    await render();
    await loginAs('학생');
    expect(container.textContent).toContain('대시보드');
    expect(container.querySelector('.rail')).not.toBeNull();
  });

  it('잘못된 비밀번호는 막는다', async () => {
    await render();
    const inputs = container.querySelectorAll('input');
    act(() => {
      const setValue = (el: HTMLInputElement, value: string) => {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
        setter?.call(el, value);
        el.dispatchEvent(new Event('input', { bubbles: true }));
      };
      setValue(inputs[0] as HTMLInputElement, 'student@playdata.co.kr');
      setValue(inputs[1] as HTMLInputElement, '틀린비밀번호');
    });
    click('로그인');
    await flush();
    expect(container.textContent).toContain('비밀번호가 올바르지 않습니다');
  });
});

describe('역할별 셸', () => {
  it('학생 레일에는 학생 메뉴 10개가 있다', async () => {
    await render();
    await loginAs('학생');
    const labels = Array.from(container.querySelectorAll('.rail__label')).map((el) => el.textContent);
    expect(labels).toContain('이력서 관리');
    expect(labels).toContain('마일리지');
    expect(labels).not.toContain('학생 관리');
  });

  it('관리자 사이드바는 그룹으로 묶여 있다', async () => {
    await render();
    await loginAs('관리자');
    const titles = Array.from(container.querySelectorAll('.rail__group')).map((el) =>
      el.textContent?.replace(/expand_(more|less)/, '').trim(),
    );
    expect(titles).toEqual(['운영 · 인원', '출결 · 공간', '학습 · 평가', '소통 · 리워드', '시스템']);
  });

  it('역할이 맞지 않는 화면은 제 홈으로 돌려보낸다', async () => {
    await render();
    await loginAs('학생');
    // 학생이 관리자 URL로 들어가면 대시보드로 돌아온다.
    await render('/admin/students');
    expect(container.textContent).toContain('대시보드');
    expect(container.textContent).not.toContain('학생 계정을 등록');
  });
});

describe('데이터가 실제로 흐른다', () => {
  it('이력서 버전은 편집 중이 아니라 저장할 때 증가한다', async () => {
    await render('/resume/r-demo-1/edit');
    await loginAs('학생');
    await render('/resume/r-demo-1/edit');

    const before = getDb().resumes.find((resume) => resume.id === 'r-demo-1')!.revisionCount;
    const title = container.querySelector('.resume-doc__field input') as HTMLInputElement;
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      setter?.call(title, '데이터 분석가 이력서');
      title.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await flush();

    expect(getDb().resumes.find((resume) => resume.id === 'r-demo-1')!.revisionCount).toBe(before);
    click('저장');
    await flush();
    expect(getDb().resumes.find((resume) => resume.id === 'r-demo-1')!.revisionCount).toBe(before + 1);
    expect(container.textContent).toContain('저장됨');
  });

  it('이력서 Doc 보기에서 입력칸을 숨기고 PDF 내보내기를 제공한다', async () => {
    await render('/resume/r-demo-1/edit');
    await loginAs('학생');
    await render('/resume/r-demo-1/edit');

    click('Doc');
    await flush();
    expect(container.querySelector('.resume-doc input')).toBeNull();
    expect(container.querySelector('[aria-label="PDF 내보내기"]')).not.toBeNull();
    expect(container.textContent).toContain('미작성');
  });

  it('학생이 기록을 제출하면 관리자 기록실 대기 건수가 는다', async () => {
    const before = getDb().submissions.filter((s) => s.status === 'pending').length;
    await render('/records/create/blog');
    await loginAs('학생');
    await render('/records/create/blog');

    const inputs = container.querySelectorAll('input');
    act(() => {
      const setValue = (el: HTMLInputElement, value: string) => {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
        setter?.call(el, value);
        el.dispatchEvent(new Event('input', { bubbles: true }));
      };
      setValue(inputs[0] as HTMLInputElement, '2주차 회고');
      setValue(inputs[1] as HTMLInputElement, 'https://velog.io/@demo/week2');
    });
    click('제출');
    await flush();

    const after = getDb().submissions.filter((s) => s.status === 'pending');
    expect(after.length).toBe(before + 1);
    expect(after.some((s) => s.title === '2주차 회고')).toBe(true);
  });

  it('소통 피드 게시글에 댓글을 등록한다', async () => {
    await render('/board');
    await loginAs('학생');
    await render('/board');

    click('소통 피드');
    await flush();
    const commentsButton = container.querySelector('button[aria-label="댓글 3"]') as HTMLButtonElement;
    act(() => commentsButton.dispatchEvent(new MouseEvent('click', { bubbles: true })));
    await flush();

    const input = container.querySelector(
      'textarea[aria-label="김하늘 게시글에 댓글 작성"]',
    ) as HTMLTextAreaElement;
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
      setter?.call(input, '조인 실습 정리 감사합니다!');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    click('댓글 등록');
    await flush();

    expect(getDb().postComments.some((comment) => comment.content === '조인 실습 정리 감사합니다!')).toBe(true);
    expect(getDb().posts.find((post) => post.id === 'p1')?.commentCount).toBe(4);
    expect(container.textContent).toContain('댓글 4');
  });

  it('공부방에서 범위를 골라 로컬 수업노트를 만든다', async () => {
    const before = getDb().studyNotes.length;
    await render('/study-room/notes/src1');
    await loginAs('학생');
    await render('/study-room/notes/src1');

    click('2026-09-19');
    click('선택한 범위 정리하기');
    await flush();

    expect(getDb().studyNotes.length).toBe(before + 1);
    expect(getDb().studyNotes.at(-1)?.scopeKey).toBe('date:2026-09-19');
    expect(container.textContent).toContain('2026-09-19 수업 요약');
    expect(container.textContent).toContain('실제 내용 생성은 공부방 API 연결 후');
  });

  it('기록 상세 보기에서 제출 내용과 증빙 상태를 확인한다', async () => {
    await render('/records');
    await loginAs('학생');
    await render('/records');

    click('상세 보기');
    await flush();

    const dialog = container.querySelector('[role="dialog"]') as HTMLElement;
    expect(dialog).not.toBeNull();
    expect(dialog.textContent).toContain('제출 상세');
    expect(dialog.textContent).toContain('제출자');
    expect(dialog.textContent).toContain('팀 스터디');
    expect(dialog.textContent).toContain('첨부된 증빙이 없습니다');

    click('닫기', dialog);
    await flush();
    expect(
      [...container.querySelectorAll('[role="dialog"]')].some((item) => item.textContent?.includes('제출 상세')),
    ).toBe(false);
  });

  it('관리자가 승인하면 학생 화면의 상태도 바뀐다', async () => {
    const before = getDb().submissions.filter((s) => s.status === 'pending').length;
    expect(before).toBeGreaterThan(0);
    await render('/admin/records');
    await loginAs('관리자');
    await render('/admin/records');

    // 기록 카드의 「승인」은 목록에 바로 붙어 있다 — 따로 창이 열리지 않는다.
    const card = container.querySelector('.rec-card') as HTMLElement;
    expect(card).not.toBeNull();
    click('승인', card);
    await flush();

    expect(getDb().submissions.filter((s) => s.status === 'pending').length).toBe(before - 1);
  });

  it('응시 기간이 끝난 평가는 직접 주소로 들어가도 막는다', async () => {
    const submissions = getDb().assessmentSubmissions;
    const ownIndex = submissions.findIndex(
      (submission) => submission.assessmentId === 'a2' && submission.userId === DemoAccounts.studentUid,
    );
    submissions.splice(ownIndex, 1);

    await render('/assessments/a2/take');
    await loginAs('학생');
    await render('/assessments/a2/take');

    expect(container.textContent).toContain('종료된 평가이며 응시 기록이 없습니다.');
    expect(container.textContent).not.toContain('Python에서 리스트를 만드는 기호는?');
  });

  it('미응답 문항이 있으면 확인한 뒤에만 평가를 제출한다', async () => {
    // 데모 학생은 a1 을 이미 제출한 상태로 시작한다(오답 → 복습 연결 시연용). 여기서는 새로 응시한다.
    mutate((db) => ({
      assessmentSubmissions: db.assessmentSubmissions.filter(
        (s) => !(s.assessmentId === 'a1' && s.userId === DemoAccounts.studentUid),
      ),
    }));
    await render('/assessments/a1/take');
    await loginAs('학생');
    await render('/assessments/a1/take');

    // 4문항 — 마지막 문항까지 넘어가야 「제출하기」가 보인다
    for (let i = 0; i < 3; i++) {
      click('다음');
      await flush();
    }
    click('제출하기');
    await flush();

    const dialog = container.querySelector('[role="dialog"]') as HTMLElement;
    expect(dialog.textContent).toContain('4문항이 비어 있습니다. 그대로 제출할까요?');
    expect(getDb().assessmentSubmissions.some(
      (submission) => submission.assessmentId === 'a1' && submission.userId === DemoAccounts.studentUid,
    )).toBe(false);

    click('그대로 제출', dialog);
    await flush();
    expect(container.textContent).toContain('34기 2차 성취도평가 결과');
    expect(getDb().assessmentSubmissions.some(
      (submission) => submission.assessmentId === 'a1' && submission.userId === DemoAccounts.studentUid,
    )).toBe(true);
  });

  it('구매 요청을 승인하면 마일리지가 차감된다', async () => {
    const request = getDb().purchaseRequests.find((r) => r.status === 'pending');
    expect(request).toBeDefined();
    const before = getDb().users.find((u) => u.uid === request!.userId)!.mileageBalance;

    await render('/admin/mileage/requests');
    await loginAs('관리자');
    await render('/admin/mileage/requests');

    const rows = container.querySelectorAll('.table tbody tr');
    act(() => rows[0].dispatchEvent(new MouseEvent('click', { bubbles: true })));
    await flush();
    click('승인', container.querySelector('.dialog') as HTMLElement);
    await flush();

    const after = getDb().users.find((u) => u.uid === request!.userId)!.mileageBalance;
    expect(after).toBe(before - request!.totalAmount);
    expect(getDb().mileageTransactions[0].amount).toBe(-request!.totalAmount);
  });

  it('배치 편집에서 학생을 끌어 앉히고 바꿔 앉혀 확정한다', async () => {
    await render('/admin/seating');
    await loginAs('관리자');
    await render('/admin/seating');
    click('배치 편집');
    await flush();

    const seatOf = (no: string) =>
      Array.from(container.querySelectorAll('.seat-assign__map .seat')).find(
        (el) => el.querySelector('.seat__no')?.textContent === `${no}번`,
      ) as HTMLElement;
    const pool = () => container.querySelector('.seat-pool') as HTMLElement;
    const seeded = getDb().seatingAssignments.find((a) => a.roomId === 'room-302')!;
    const at3 = seeded.assignments['3'];
    const at7 = seeded.assignments['7'];

    // 좌석 → 미배정 목록: 배정이 풀린다.
    expect(container.querySelector('.seat-pool__item')).toBeNull();
    await drag(seatOf('3'), pool());
    const student = container.querySelector('.seat-pool__item') as HTMLElement;
    expect(student.textContent).toContain(seeded.seatNames['3']);

    // 미배정 → 빈 좌석, 그리고 좌석끼리 끌면 서로 바뀐다.
    await drag(student, seatOf('30'));
    await drag(seatOf('30'), seatOf('7'));

    // 시드는 이미 확정돼 있어 단추가 「재확정」이다.
    press('재확정');
    await flush();
    const saved = getDb().seatingAssignments.find((a) => a.roomId === 'room-302')!;
    expect(saved.status).toBe('published');
    expect(saved.assignments['3']).toBeUndefined();
    expect(saved.assignments['7']).toBe(at3);
    expect(saved.assignments['30']).toBe(at7);
    expect(saved.seatNames['7']).toBe(seeded.seatNames['3']);
    expect(getDb().seatingMeta[DemoConfig.cohortId].publishedRoomId).toBe('room-302');
    expect(container.textContent).toContain('좌석 배치가 확정되었습니다.');
  });

  it('틀 설정에서 테이블을 끌어 놓고 저장하면 좌석이 는다', async () => {
    await render('/admin/seating');
    await loginAs('관리자');
    await render('/admin/seating');
    const seatsOf = () => getDb().seatingRooms[0].cells.filter((c) => c.type === 'seat').length;
    const before = seatsOf();

    const chip = Array.from(container.querySelectorAll('.lay-chip')).find((el) =>
      el.textContent?.includes('2인 테이블'),
    ) as HTMLElement;
    // 7×10 격자의 맨 아래 왼쪽 구석은 비어 있다.
    const target = Array.from(container.querySelectorAll<HTMLElement>('.lay-map .lay-empty')).find(
      (el) => el.style.gridRow === '7' && el.style.gridColumn === '1',
    )!;
    await drag(chip, target);
    expect(container.textContent).toContain('저장되지 않은 변경');
    expect(seatsOf()).toBe(before);

    press('틀 저장');
    await flush();
    expect(seatsOf()).toBe(before + 2);
  });

  it('강사가 호명 패널에서 확인을 누르면 저장된다', async () => {
    await render('/instructor');
    await loginAs('강사');
    await render('/instructor');

    click('확인', container.querySelector('.roll-panel') as HTMLElement);
    await flush();
    const confirmed = getDb().seatPresence.filter((p) => p.state === 'confirmed');
    expect(confirmed.length).toBe(1);

    // 확인을 누르면 다음 학생으로 넘어간다.
    click('보류', container.querySelector('.roll-panel') as HTMLElement);
    await flush();
    const held = getDb().seatPresence.filter((p) => p.state === 'held');
    expect(held.length).toBe(1);
    expect(held[0].userId).not.toBe(confirmed[0].userId);
  });

  it('복습 문제 신고 — 2명이 신고하면 숨겨지고 강사 화면에서 다시 보이게 할 수 있다', async () => {
    // 시드: 다른 학생 하나가 9/14 문제 5를 신고해 둔 상태. 데모 학생이 한 번 더 신고한다.
    mutate((db) => ({
      practiceReports: [
        ...db.practiceReports,
        { id: 'pr-t', uid: 'demo-student-001', setId: 'ps-mm-0914', index: 4, reason: 'answer', note: '', createdAt: new Date() },
      ],
    }));
    await render('/instructor');
    await loginAs('강사');
    await render('/instructor/practice');

    expect(container.textContent).toContain('복습 문제 신고');
    expect(container.textContent).toContain('자동 숨김');
    expect(container.textContent).toContain('테스트가 문제 문장과 달라요');

    press('다시 보이기');
    await flush();
    const review = getDb().practiceReviews.find((r) => r.setId === 'ps-mm-0914' && r.index === 4);
    expect(review?.decision).toBe('kept');
    expect(container.textContent).toContain('강사가 다시 보임');
  });
});

describe('라우트 표', () => {
  it('세 역할의 라우트가 모두 등록돼 있다', () => {
    // 이력서 편집과 평가 응시·결과는 셸 밖에 있다 — app_router.dart와 같다.
    expect(studentRoutes.length + fullScreenRoutes.length).toBeGreaterThanOrEqual(21);
    expect(instructorRoutes.length).toBeGreaterThanOrEqual(13);
    expect(adminRoutes.length).toBeGreaterThanOrEqual(35);
    expect(appRoutes.length).toBe(
      studentRoutes.length + instructorRoutes.length + adminRoutes.length,
    );
  });

  it('셸 밖 라우트는 왼쪽 레일 없이 화면을 다 쓴다', () => {
    const paths = fullScreenRoutes.map((r) => r.path);
    expect(paths).toContain('/resume/:resumeId/edit');
    // 이력서 편집은 학생·강사·관리자가 같은 주소로 들어온다.
    expect(fullScreenRoutes.find((r) => r.path === '/resume/:resumeId/edit')?.roles).toBeUndefined();
    expect(appRoutes.some((r) => paths.includes(r.path))).toBe(false);
  });

  it('경로가 겹치지 않는다', () => {
    const paths = [...appRoutes, ...fullScreenRoutes].map((r) => r.path);
    expect(new Set(paths).size).toBe(paths.length);
  });

  it('데모 계정 셋이 모두 로그인 가능하다', () => {
    const emails = getDb().users.filter((u) => u.isActive).map((u) => u.email);
    expect(emails).toContain('admin@playdata.co.kr');
    expect(emails).toContain('instructor@playdata.co.kr');
    expect(emails).toContain('student@playdata.co.kr');
    expect(DemoAccounts.password).toBe('Playdata123!');
  });
});

describe('이용 안내 투어', () => {
  it('로그인하면 역할에 맞는 투어가 1단계부터 뜬다', async () => {
    await render();
    click('빠른 로그인 (데모)');
    click('학생');
    await flush();
    const card = container.querySelector('.tour-card');
    expect(card).not.toBeNull();
    expect(card?.textContent).toContain('대시보드');
    expect(card?.textContent).toContain('1 / 14');
  });

  it('다음을 누르면 스텝의 화면으로 옮겨 간다', async () => {
    await render();
    click('빠른 로그인 (데모)');
    click('학생');
    await flush();
    // 1~3단계는 대시보드, 4단계가 이력서 관리다.
    for (let i = 0; i < 3; i++) {
      click('다음', container.querySelector('.tour-card') as HTMLElement);
      await flush();
    }
    expect(container.querySelector('.tour-card')?.textContent).toContain('이력서 관리');
    expect(container.querySelector('.page-head__title')?.textContent).toBe('이력서 관리');
  });

  it('강사 투어는 12스텝이다', async () => {
    await render();
    click('빠른 로그인 (데모)');
    click('강사');
    await flush();
    expect(container.querySelector('.tour-card')?.textContent).toContain('1 / 12');
  });

  it('다시 보지 않기는 저장된다', async () => {
    await render();
    click('빠른 로그인 (데모)');
    click('관리자');
    await flush();
    expect(container.querySelector('.tour-card')?.textContent).toContain('1 / 17');
    click('다시 보지 않기', container.querySelector('.tour-card') as HTMLElement);
    await flush();
    expect(container.querySelector('.tour-card')).toBeNull();
    expect(window.localStorage.getItem('onboarding_admin_v1_demo-admin-001')).toBe('true');
  });
});
