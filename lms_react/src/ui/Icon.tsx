/**
 * 아이콘 — Flutter의 `Icons.*`(Material Symbols) 자리.
 *
 * 앱이 쓰는 것과 같은 글꼴(Material Symbols Rounded)을 그대로 쓴다. 이름도
 * Dart 쪽과 같다: `Icons.dashboard_rounded` → `<Icon name="dashboard" />`.
 */
export function Icon({
  name,
  size = 20,
  fill = false,
  className = '',
}: {
  name: string;
  size?: number;
  /** 채운 아이콘 (선택된 메뉴 등) */
  fill?: boolean;
  className?: string;
}) {
  return (
    <span
      className={`icon ${className}`.trim()}
      style={{
        fontSize: size,
        width: size,
        height: size,
        fontVariationSettings: `'FILL' ${fill ? 1 : 0}, 'wght' 400, 'GRAD' 0, 'opsz' ${size}`,
      }}
      aria-hidden
    >
      {name}
    </span>
  );
}
