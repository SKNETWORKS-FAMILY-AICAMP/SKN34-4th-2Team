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
import { getDb, resetDb } from '../data/store';
import { DemoAccounts } from '../data/seed';
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
