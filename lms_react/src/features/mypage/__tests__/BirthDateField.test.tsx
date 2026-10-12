import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, expect, it, vi } from 'vitest';

import { BirthDateField } from '../MyPageScreen';

const hosts: HTMLElement[] = [];
afterEach(() => hosts.splice(0).forEach((h) => h.remove()));

function mount(value: string | undefined, onSave = vi.fn()) {
  const host = document.createElement('div');
  document.body.appendChild(host);
  hosts.push(host);
  const root = createRoot(host);
  act(() => root.render(<BirthDateField value={value} onSave={onSave} />));
  const input = host.querySelector('input') as HTMLInputElement;
  const type = (text: string) =>
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, text);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
  const blur = () => act(() => input.dispatchEvent(new FocusEvent('focusout', { bubbles: true })));
  const rerender = (next: string | undefined) => act(() => root.render(<BirthDateField value={next} onSave={onSave} />));
  return { input, type, blur, rerender, onSave };
}

it('연도를 한 자리씩 쳐도 칸을 벗어날 때 한 번만 저장한다', () => {
  const f = mount('1986-10-10');
  for (const v of ['0001-10-10', '0019-10-10', '0199-10-10', '1990-10-10']) f.type(v);
  expect(f.onSave).not.toHaveBeenCalled();
  expect(f.input.value).toBe('1990-10-10');
  f.blur();
  expect(f.onSave).toHaveBeenCalledTimes(1);
  expect(f.onSave).toHaveBeenCalledWith('1990-10-10');
});

it('1900년 전 · 미래 날짜는 저장하지 않고 원래 값으로 돌린다', () => {
  const f = mount('1986-10-10');
  f.type('0198-10-10');
  f.blur();
  f.type('2999-01-01');
  f.blur();
  expect(f.onSave).not.toHaveBeenCalled();
  expect(f.input.value).toBe('1986-10-10');
});

it('지우면 빈 값으로 저장하고, 서버 값이 바뀌면 칸이 따라간다', () => {
  const f = mount('1986-10-10');
  f.type('');
  f.blur();
  expect(f.onSave).toHaveBeenCalledWith('');
  f.rerender('1991-01-02');
  expect(f.input.value).toBe('1991-01-02');
});
