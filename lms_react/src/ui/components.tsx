import {
  forwardRef,
  useEffect,
  useId,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react';

/**
 * 공통 위젯 — Flutter `core/widgets/`와 화면들이 반복해 쓰던 조각들.
 *
 * Material 위젯을 하나씩 옮기는 대신, 이 앱이 실제로 쓰는 모양만 남겼다.
 */

// ── 버튼 ──────────────────────────────────────────────

type ButtonVariant = 'filled' | 'outline' | 'text' | 'danger';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: 'sm' | 'md';
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'filled', size = 'md', icon, children, className = '', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type="button"
      className={`btn btn--${variant} btn--${size} ${className}`.trim()}
      {...rest}
    >
      {icon !== undefined && <span className="btn__icon" aria-hidden>{icon}</span>}
      {children}
    </button>
  );
});

// ── 카드 ──────────────────────────────────────────────

interface CardProps {
  title?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  className?: string;
  padded?: boolean;
}

export const Card = forwardRef<HTMLDivElement, CardProps>(function Card(
  { title, actions, children, className = '', padded = true },
  ref,
) {
  return (
    <section ref={ref} className={`card ${padded ? '' : 'card--flush'} ${className}`.trim()}>
      {(title !== undefined || actions !== undefined) && (
        <header className="card__head">
          {typeof title === 'string' ? <h2 className="card__title">{title}</h2> : title}
          {actions !== undefined && <div className="card__actions">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
});

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div>
        <h1 className="page-head__title">{title}</h1>
        {description !== undefined && <p className="page-head__desc">{description}</p>}
      </div>
      {actions !== undefined && <div className="page-head__actions">{actions}</div>}
    </header>
  );
}

// ── 표시 조각 ──────────────────────────────────────────

export function Badge({
  children,
  tone = 'neutral',
  color,
}: {
  children: ReactNode;
  tone?: 'neutral' | 'primary' | 'success' | 'warning' | 'error' | 'info';
  /** 상태색을 직접 줄 때 (출결 상태 등) */
  color?: string;
}) {
  const style = color === undefined ? undefined : { color, borderColor: color };
  return (
    <span className={`badge badge--${tone}`} style={style}>
      {children}
    </span>
  );
}

export function StatTile({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: ReactNode;
  sub?: string;
  tone?: 'primary' | 'success' | 'warning' | 'error';
}) {
  return (
    <div className={`stat-tile${tone === undefined ? '' : ` stat-tile--${tone}`}`}>
      <span className="stat-tile__label">{label}</span>
      <strong className="stat-tile__value">{value}</strong>
      {sub !== undefined && <span className="stat-tile__sub">{sub}</span>}
    </div>
  );
}

export function EmptyState({ icon = '🗒', message, action }: { icon?: string; message: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <span className="empty__icon" aria-hidden>{icon}</span>
      <p className="empty__msg">{message}</p>
      {action}
    </div>
  );
}

export function Avatar({ name, photoUrl, size = 32 }: { name: string; photoUrl?: string; size?: number }) {
  const style = { width: size, height: size, fontSize: size * 0.42 };
  if (photoUrl !== undefined && photoUrl !== '') {
    return <img className="avatar" src={photoUrl} alt={name} style={style} />;
  }
  return (
    <span className="avatar avatar--initial" style={style} aria-hidden>
      {name.slice(0, 1)}
    </span>
  );
}

// ── 탭 ────────────────────────────────────────────────

export interface TabItem {
  id: string;
  label: string;
  count?: number;
}

export function Tabs({
  items,
  active,
  onChange,
}: {
  items: TabItem[];
  active: string;
  onChange(id: string): void;
}) {
  return (
    <div className="tabs" role="tablist">
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          role="tab"
          aria-selected={item.id === active}
          className={`tabs__tab${item.id === active ? ' tabs__tab--on' : ''}`}
          onClick={() => onChange(item.id)}
        >
          {item.label}
          {item.count !== undefined && <span className="tabs__count">{item.count}</span>}
        </button>
      ))}
    </div>
  );
}

// ── 입력 ──────────────────────────────────────────────

interface FieldProps {
  label?: string;
  hint?: string;
  error?: string;
  children: ReactNode;
}

export function Field({ label, hint, error, children }: FieldProps) {
  return (
    <label className="field">
      {label !== undefined && <span className="field__label">{label}</span>}
      {children}
      {error !== undefined ? (
        <span className="field__error">{error}</span>
      ) : (
        hint !== undefined && <span className="field__hint">{hint}</span>
      )}
    </label>
  );
}

export const TextInput = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function TextInput({ className = '', ...rest }, ref) {
    return <input ref={ref} className={`input ${className}`.trim()} {...rest} />;
  },
);

export const TextArea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function TextArea({ className = '', rows = 4, ...rest }, ref) {
    return <textarea ref={ref} rows={rows} className={`input input--area ${className}`.trim()} {...rest} />;
  },
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className = '', children, ...rest }, ref) {
    return (
      <select ref={ref} className={`input input--select ${className}`.trim()} {...rest}>
        {children}
      </select>
    );
  },
);

export function Checkbox({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange(next: boolean): void;
  label: ReactNode;
}) {
  return (
    <label className="checkbox">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>{label}</span>
    </label>
  );
}

export function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange(next: boolean): void;
  label?: string;
}) {
  return (
    <label className="toggle">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle__track" aria-hidden />
      {label !== undefined && <span className="toggle__label">{label}</span>}
    </label>
  );
}

// ── 표 ────────────────────────────────────────────────

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  empty = '표시할 항목이 없습니다.',
}: {
  columns: {
    key: string;
    header: ReactNode;
    width?: string;
    align?: 'left' | 'right' | 'center';
    render(row: T, index: number): ReactNode;
  }[];
  rows: T[];
  rowKey(row: T): string;
  onRowClick?(row: T): void;
  empty?: string;
}) {
  if (rows.length === 0) return <EmptyState message={empty} />;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={{ width: c.width, textAlign: c.align ?? 'left' }}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr
              key={rowKey(row)}
              className={onRowClick === undefined ? undefined : 'table__row--clickable'}
              onClick={onRowClick === undefined ? undefined : () => onRowClick(row)}
            >
              {columns.map((c) => (
                <td key={c.key} style={{ textAlign: c.align ?? 'left' }}>
                  {c.render(row, index)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── 대화상자 ───────────────────────────────────────────

export function Dialog({
  title,
  children,
  actions,
  onClose,
  width = 480,
}: {
  title: string;
  children: ReactNode;
  actions?: ReactNode;
  onClose(): void;
  width?: number;
}) {
  const labelId = useId();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="dialog-scrim" onClick={onClose}>
      <div
        className="dialog"
        style={{ width }}
        role="dialog"
        aria-modal
        aria-labelledby={labelId}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="dialog__head">
          <h2 id={labelId} className="dialog__title">{title}</h2>
          <button type="button" className="dialog__close" onClick={onClose} aria-label="닫기">
            ✕
          </button>
        </header>
        <div className="dialog__body">{children}</div>
        {actions !== undefined && <footer className="dialog__actions">{actions}</footer>}
      </div>
    </div>
  );
}

// ── 잡동사니 ───────────────────────────────────────────

export function Row({ children, gap = 8, wrap = true }: { children: ReactNode; gap?: number; wrap?: boolean }) {
  return (
    <div className="row" style={{ gap, flexWrap: wrap ? 'wrap' : 'nowrap' }}>
      {children}
    </div>
  );
}

export function Spacer() {
  return <span className="spacer" />;
}

export function Chip({
  children,
  selected = false,
  onClick,
}: {
  children: ReactNode;
  selected?: boolean;
  onClick?(): void;
}) {
  if (onClick === undefined) {
    return <span className={`chip${selected ? ' chip--on' : ''}`}>{children}</span>;
  }
  return (
    <button type="button" className={`chip${selected ? ' chip--on' : ''}`} onClick={onClick}>
      {children}
    </button>
  );
}

export function ProgressBar({ value, max = 100 }: { value: number; max?: number }) {
  const pct = max === 0 ? 0 : Math.min(100, Math.round((value / max) * 100));
  return (
    <div className="progress" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
      <span className="progress__fill" style={{ width: `${pct}%` }} />
    </div>
  );
}
