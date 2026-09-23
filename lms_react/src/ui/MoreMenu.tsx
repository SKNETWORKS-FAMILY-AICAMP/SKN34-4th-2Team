import { useEffect, useRef, useState, type ReactNode } from 'react';

import { Icon } from './Icon';

/**
 * 「···」 메뉴 — Flutter PopupMenuButton 자리
 *
 * 누르면 아래로 짧은 목록이 열리고, 하나를 고르면 닫힌다. 바깥을 누르거나
 * Esc를 눌러도 닫힌다.
 */
export interface MoreMenuItem {
  key: string;
  label: string;
  /** 항목 아래 작은 글씨. 무엇이 일어나는지 한 줄로. */
  hint?: string;
  /** 항목 앞에 아이콘 이름 (Material Symbols). */
  icon?: string;
  /** 이 항목 위에 가는 줄을 긋는다. 성격이 다른 묶음을 가른다. */
  divider?: boolean;
  /** 지우기처럼 되돌릴 수 없는 것은 붉게 보인다. */
  danger?: boolean;
  onSelect(): void;
}

export function MoreMenu({
  items,
  label = '더보기',
  icon = 'more_horiz',
  className,
  align = 'right',
  children,
}: {
  items: MoreMenuItem[];
  label?: string;
  icon?: string;
  /**
   * 여는 단추의 클래스. 비우면 아이콘 단추(`icon-btn`)다.
   * 글자가 있는 단추로 열려면 `btn btn--outline btn--sm` 처럼 준다.
   */
  className?: string;
  /** 목록을 단추의 어느 쪽에 맞출지. 도구 줄 왼쪽에 있는 단추는 `left`. */
  align?: 'left' | 'right';
  /** 단추 자리를 직접 그릴 때 쓴다. */
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const iconOnly = className === undefined;
  return (
    <span className="more" ref={root}>
      <button
        type="button"
        className={className ?? 'icon-btn'}
        aria-label={iconOnly ? label : undefined}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        {children ?? <Icon name={icon} size={iconOnly ? 20 : 18} />}
        {!iconOnly && children === undefined && label}
        {!iconOnly && <Icon name="expand_more" size={18} className="more__caret" />}
      </button>

      {open && (
        <div className={`more__pop more__pop--${align}`} role="menu">
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              role="menuitem"
              className={[
                'more__item',
                item.danger === true ? 'more__item--danger' : '',
                item.divider === true ? 'more__item--divider' : '',
                item.hint !== undefined ? 'more__item--hinted' : '',
              ]
                .filter(Boolean)
                .join(' ')}
              onClick={(e) => {
                e.stopPropagation();
                setOpen(false);
                item.onSelect();
              }}
            >
              {item.icon !== undefined && <Icon name={item.icon} size={18} className="more__icon" />}
              <span className="more__text">
                {item.label}
                {item.hint !== undefined && <small>{item.hint}</small>}
              </span>
            </button>
          ))}
        </div>
      )}
    </span>
  );
}
