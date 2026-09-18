import 'package:flutter/material.dart';

/// 코스모스 블루 톤 팔레트.
///
/// 값이 **고정이 아니다.** [apply]로 어두운 화면을 켜면 같은 이름이 다른 색을
/// 돌려준다. 화면 코드 1,200여 곳이 이 이름들을 부르고 있어, 이름을 그대로 두고
/// 값만 바꾸는 편이 화면마다 색을 갈아 끼우는 것보다 훨씬 적게 건드린다.
///
/// 대신 `const`로 쓸 수 없다. 값이 실행 중에 정해지기 때문이다. 바뀌지 않는 색
/// (로그인 화면의 시네마틱 크롬 등)은 아래쪽에 `const`로 남겨 두었다.
///
/// 색을 바꾼 뒤에는 화면을 다시 그려야 한다. 앱 루트가 테마 설정을 지켜보다가
/// [apply]를 부르고 트리를 새로 만든다.
abstract final class AppColors {
  static bool _dark = false;

  // 설정에서 고른 강조색. 버튼·링크·선택 표시가 모두 이것을 따른다.
  static const _defaultAccent = Color(0xFF0055FF);
  static const _defaultAccentDark = Color(0xFF0044CC);
  static const _defaultAccentLight = Color(0xFFE8F0FF);
  static const _defaultRail = Color(0xFF0B2A6F);
  static Color _accent = _defaultAccent;
  static Color _accentDark = _defaultAccentDark;
  static Color _accentLight = _defaultAccentLight;
  static Color _rail = _defaultRail;

  /// 지금 어두운 화면인가.
  static bool get isDark => _dark;

  /// 앱 루트에서만 부른다. 화면 코드가 직접 부르지 않는다.
  ///
  /// 강조색을 넘기지 않으면 원래 파랑으로 돌아간다. 예전에는 테마를 거치는
  /// 버튼만 고른 색을 따르고, 화면 코드가 [primary]를 직접 부르는 260곳은
  /// 파랑에 머물렀다. 한 화면 안에서 버튼은 보라, 칩은 파랑이 되었다.
  static void apply({
    required bool dark,
    Color? accent,
    Color? accentDark,
    Color? accentLight,
    Color? rail,
  }) {
    _dark = dark;
    _accent = accent ?? _defaultAccent;
    _accentDark = accentDark ?? _defaultAccentDark;
    _accentLight = accentLight ?? _defaultAccentLight;
    _rail = rail ?? _defaultRail;
  }

  static Color _pick(Color light, Color dark) => _dark ? dark : light;

  /// 어두운 화면의 강조색·상태색 밝기를 맞춘다.
  ///
  /// 이 색들은 두 가지로 쓰인다. 어두운 바탕 위의 글씨·아이콘으로, 그리고 흰
  /// 글씨를 얹는 채움 바탕으로. 너무 밝히면 흰 글씨가 사라지고(챗봇 머리가
  /// 그랬다), 너무 어두우면 바탕에 묻힌다. 둘 다 견디는 밝기가 있다.
  ///
  /// 상대 휘도 0.18이면 흰 글씨와 4.5:1, 어두운 바탕(#171A1F)과 3.8:1이 나온다.
  /// 색조와 채도는 두고 밝기만 찾아 맞춘다. HSL 밝기는 색조마다 눈에 보이는
  /// 밝기가 달라(노랑은 밝고 파랑은 어둡다) 휘도로 잰다.
  static Color _balanced(Color color, {double luminance = 0.18}) {
    final hsl = HSLColor.fromColor(color);
    var low = 0.0, high = 1.0;
    for (var i = 0; i < 24; i++) {
      final mid = (low + high) / 2;
      if (hsl.withLightness(mid).toColor().computeLuminance() < luminance) {
        low = mid;
      } else {
        high = mid;
      }
    }
    return hsl.withLightness((low + high) / 2).toColor();
  }

  /// 옅은 틴트 배경을 어두운 화면에 맞춰 옮긴다.
  ///
  /// 화면 곳곳에 `Color(0xFFEFF6FF)`처럼 옅은 색을 직접 박아 둔 배경이 백여
  /// 곳 있다. 그대로 두면 어두운 화면에서 흰 칸이 되고, 테마를 따라 밝아진
  /// 글씨가 그 위에서 사라진다. 하나하나 이름을 붙이는 대신 색조는 살리고
  /// 밝기만 뒤집는다. 노란 칸은 어두운 황토가, 파란 칸은 짙은 남색이 된다.
  static Color tint(Color light) {
    if (!_dark) return light;
    final hsl = HSLColor.fromColor(light);
    // 흰색에 가까울수록 더 어둡게. 0.97 → 약 0.12, 0.89 → 약 0.17.
    final lightness = (0.10 + (1 - hsl.lightness) * 0.6).clamp(0.08, 0.26);
    return hsl
        .withLightness(lightness)
        .withSaturation(hsl.saturation * 0.45)
        .toColor();
  }

  // ── 브랜드 ────────────────────────────────────────────────
  // 설정에서 고른 강조색을 따른다. 어두운 바탕에서는 같은 색이 가라앉아
  // 읽히지 않으므로 색조는 두고 밝기만 끌어올린다.
  static Color get primary => _dark ? _balanced(_accent) : _accent;
  static Color get primaryDark =>
      _dark ? _balanced(_accentDark, luminance: 0.13) : _accentDark;
  static Color get primaryLight => _dark ? tint(_accentLight) : _accentLight;
  static Color get secondary =>
      _pick(const Color(0xFF6B7280), const Color(0xFF9AA3AF));

  // ── 바탕 ──────────────────────────────────────────────────
  static Color get background =>
      _pick(const Color(0xFFF8F9FB), const Color(0xFF0F1216));
  static Color get surface => _pick(Colors.white, const Color(0xFF171A1F));
  static Color get surfaceVariant =>
      _pick(const Color(0xFFF3F5F9), const Color(0xFF1F232A));

  // ── 글자 ──────────────────────────────────────────────────
  static Color get textPrimary =>
      _pick(const Color(0xFF111827), const Color(0xFFE8EAED));
  static Color get textSecondary =>
      _pick(const Color(0xFF6B7280), const Color(0xFF9AA3AF));
  static Color get textHint =>
      _pick(const Color(0xFF9CA3AF), const Color(0xFF6B7280));

  // ── 선 ────────────────────────────────────────────────────
  static Color get border =>
      _pick(const Color(0xFFE5E7EB), const Color(0xFF2A2F37));
  static Color get divider =>
      _pick(const Color(0xFFF3F4F6), const Color(0xFF232830));

  // ── 상태 ──────────────────────────────────────────────────
  static Color get success => _dark
      ? _balanced(const Color(0xFF16A34A))
      : const Color(0xFF16A34A);
  static Color get warning =>
      _pick(const Color(0xFFF59E0B), const Color(0xFFFBBF24));
  static Color get error => _dark
      ? _balanced(const Color(0xFFDC2626))
      : const Color(0xFFDC2626);
  /// 공가·안내 같은 **뜻이 있는 파랑**이다. 강조색을 따라가지 않는다.
  /// 강조색이 청록이면 공가가 외출(청록)과 구분되지 않는다.
  static Color get info => _dark
      ? _balanced(const Color(0xFF0055FF))
      : const Color(0xFF0055FF);

  /// 사이드바 바탕색. 마일리지 카드처럼 사이드바와 결을 맞춰야 하는 곳이 쓴다.
  static Color get sidebar => _rail;
  static const sidebarIconInactive = Color(0xFF94A3B8);

  // ── 상태 뱃지 ─────────────────────────────────────────────
  static Color get badgeOpen => info;
  static Color get badgeLate => warning;
  static Color get badgeClosed =>
      _pick(const Color(0xFF4B5563), const Color(0xFF6B7280));

  /// 카드 그림자. 어두운 화면에서는 더 짙어야 테두리가 보인다.
  static Color get shadow =>
      _pick(const Color(0x1A0F172A), const Color(0x66000000));

  // ── 바뀌지 않는 색 ────────────────────────────────────────
  // 로그인·셸의 시네마틱 크롬은 원래 어두운 화면이라 테마를 타지 않는다.
  // `const`로 남겨 두면 상수 자리에서 그대로 쓸 수 있다.
  static const cinematicBg = Color(0xFF05070F);
  static const cinematicSurface = Color(0xFF0B1224);
  static const cinematicBorder = Color(0xFF1E2538);
  static const cinematicAccent = Color(0xFF00C2D4);
  static const cinematicAccentAlt = Color(0xFF7B5CFF);
  static const cinematicMuted = Color(0xFF94A3B8);
}
