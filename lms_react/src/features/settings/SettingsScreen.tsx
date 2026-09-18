import {
  railPalettes,
  useAppearance,
  type Density,
  type ThemeMode,
} from '../../app/appearance';
import { resetDb } from '../../data/store';
import { Icon } from '../../ui/Icon';

/**
 * 화면 설정 — features/settings/presentation/appearance_settings_screen.dart
 *
 * 테마·사이드바 색·밀도를 고른다. 고른 값은 이 기기에만 남는다.
 */
const themes: { id: ThemeMode; label: string; desc: string }[] = [
  { id: 'light', label: '라이트', desc: '전체를 밝게' },
  { id: 'railDark', label: '사이드바 다크', desc: '본문은 밝게, 사이드바만 어둡게' },
  { id: 'dark', label: '전체 다크', desc: '전체를 어둡게' },
];

const densities: { id: Density; label: string; desc: string }[] = [
  { id: 'auto', label: '자동', desc: '화면 크기에 맞춥니다' },
  { id: 'normal', label: '보통', desc: '넓은 여백' },
  { id: 'compact', label: '좁게', desc: '한 화면에 더 많이' },
];

export function SettingsScreen() {
  const { theme, palette, density, setTheme, setPalette, setDensity } = useAppearance();

  return (
    <div className="settings">
      <header className="page-head">
        <div>
          <h1 className="page-head__title">화면 설정</h1>
          <p className="page-head__desc">이 기기에만 저장됩니다. 다른 기기에서는 따로 고르면 됩니다.</p>
        </div>
      </header>

      <section className="panel settings__card">
        <h2 className="settings__title">화면 테마</h2>
        {themes.map((item) => (
          <label key={item.id} className={`opt${theme === item.id ? ' opt--on' : ''}`}>
            <span className={`opt__preview opt__preview--${item.id}`} aria-hidden />
            <span className="opt__text">
              <strong>{item.label}</strong>
              <span>{item.desc}</span>
            </span>
            <input
              type="radio"
              name="theme"
              checked={theme === item.id}
              onChange={() => setTheme(item.id)}
            />
          </label>
        ))}
      </section>

      <section className="panel settings__card">
        <h2 className="settings__title">사이드바 색</h2>
        <p className="settings__sub">버튼과 링크 색도 여기를 따릅니다.</p>
        {railPalettes.map((item) => (
          <label key={item.id} className={`opt${palette === item.id ? ' opt--on' : ''}`}>
            <span className="opt__swatch" style={{ background: item.background }} aria-hidden>
              <i style={{ background: item.accent }} />
            </span>
            <span className="opt__text">
              <strong>
                {item.id} {item.name}
              </strong>
            </span>
            <input
              type="radio"
              name="palette"
              checked={palette === item.id}
              onChange={() => setPalette(item.id)}
            />
          </label>
        ))}
      </section>

      <section className="panel settings__card">
        <h2 className="settings__title">밀도</h2>
        {densities.map((item) => (
          <label key={item.id} className={`opt${density === item.id ? ' opt--on' : ''}`}>
            <span className="opt__icon" aria-hidden>
              <Icon name={item.id === 'compact' ? 'density_small' : 'density_medium'} size={20} />
            </span>
            <span className="opt__text">
              <strong>{item.label}</strong>
              <span>{item.desc}</span>
            </span>
            <input
              type="radio"
              name="density"
              checked={density === item.id}
              onChange={() => setDensity(item.id)}
            />
          </label>
        ))}
      </section>

      <section className="panel settings__card">
        <h2 className="settings__title">프로토타입 데이터</h2>
        <p className="settings__sub">
          이 프로토타입의 데이터는 메모리에만 있습니다. 새로고침하면 처음 상태로 돌아갑니다.
        </p>
        <button type="button" className="btn btn--danger btn--md settings__reset" onClick={resetDb}>
          데모 데이터 초기화
        </button>
      </section>
    </div>
  );
}
