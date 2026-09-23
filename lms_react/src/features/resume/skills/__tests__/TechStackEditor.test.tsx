import { act, useState } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import type { ResumeContent } from '../../../../domain/types';
import { allSkills, canonicalSkill, searchSkills } from '../skillCatalog';
import { TechStackEditor } from '../TechStackEditor';

type TechItem = ResumeContent['techStack'][number];
(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

describe('기술 후보 — skill_catalog.dart', () => {
  it('기본 목록이 앞에 손으로 정한 순서로, 표기가 같으면 하나만', () => {
    expect(allSkills.slice(0, 3)).toEqual(['Python', 'Java', 'JavaScript']);
    expect(allSkills.filter((s) => s.toLowerCase() === 'python')).toHaveLength(1);
    expect(allSkills).not.toContain('딥러닝');
  });
  it('검색은 앞이 맞는 것 먼저, 별칭은 영문 표기로 맞춘다', () => {
    expect(searchSkills('py')[0]).toBe('Python');
    expect(canonicalSkill(' 딥러닝 ')).toBe('Deep Learning');
    expect(canonicalSkill('pytorch')).toBe('PyTorch');
  });
});

let host: HTMLDivElement;
let root: Root;
let latest: TechItem[] = [];

function Harness({ initial }: { initial: TechItem[] }) {
  const [items, setItems] = useState(initial);
  latest = items;
  let n = 0;
  return <TechStackEditor items={items} readOnly={false} onChange={setItems} newId={() => `t${++n}${Date.now()}`} />;
}

beforeEach(() => {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
});

afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

const button = (text: string, scope = 'button') =>
  [...host.querySelectorAll(scope)].find((b) => b.textContent?.trim().endsWith(text)) as HTMLButtonElement;

describe('기술스택 편집기', () => {
  it('태그로 보여 주고, 누르면 숙련도 타일, 후보를 누르면 추가 · 다시 누르면 뺀다', async () => {
    act(() => root.render(<Harness initial={[{ id: 'a', name: 'Python', level: '고급' }]} />));
    expect(host.querySelector('.skill-tag')?.textContent).toContain('Python · 고급');

    await act(async () => button('Python · 고급').click());
    expect(host.textContent).toContain('Python 숙련도');
    expect(host.querySelector('.level-tile.is-selected')?.textContent).toContain('고급');
    // 같은 단계를 다시 누르면 지운다
    await act(async () => (host.querySelector('.level-tile.is-selected') as HTMLButtonElement).click());
    expect(latest[0].level).toBe('');

    await act(async () => button('Java', '.skill-pick').click());
    expect(latest.map((x) => x.name)).toEqual(['Python', 'Java']);
    await act(async () => button('Java', '.skill-pick').click());
    expect(latest.map((x) => x.name)).toEqual(['Python']);
  });

  it('후보에 없으면 직접 추가한다', async () => {
    act(() => root.render(<Harness initial={[]} />));
    const input = host.querySelector('.tech-editor__search input') as HTMLInputElement;
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      setter.call(input, '사내툴X');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => button("'사내툴X' 추가", '.skill-pick').click());
    expect(latest.map((x) => x.name)).toEqual(['사내툴X']);
  });
});
