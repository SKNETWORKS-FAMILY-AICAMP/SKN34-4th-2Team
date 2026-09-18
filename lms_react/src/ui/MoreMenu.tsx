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
  /** 지우기처럼 되돌릴 수 없는 것은 붉게 보인다. */
  danger?: boolean;
  onSelect(): void;
}

export function MoreMenu({
  items,
  label = '더보기',
  icon = 'more_horiz',
  children,
}: {
  items: MoreMenuItem[];
  label?: string;
  icon?: string;
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

  return (
    <span className="more" ref={root}>
      <button
        type="button"
        className="icon-btn"
        aria-label={label}
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((v) => !v);
        }}
      >
        {children ?? <Icon name={icon} size={20} />}
      </button>

      {open && (
        <div className="more__pop" role="menu">
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              role="menuitem"
              className={`more__item${item.danger === true ? ' more__item--danger' : ''}`}
              onClick={(e) => {
                e.stopPropagation();
                setOpen(false);
                item.onSelect();
              }}
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </span>
  );
}
