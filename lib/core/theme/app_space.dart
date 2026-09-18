/// 화면 여백. 밀도 설정이 좁게면 줄어든 값을 돌려준다.
///
/// 화면마다 `EdgeInsets.all(16)`, `SizedBox(height: 12)` 같은 숫자를 직접 박아
/// 두어 테마 값만으로는 촘촘해지지 않았다. 화면 전체를 확대·축소하는 방식도
/// 해봤지만 글자까지 같이 줄어 촘촘하다기보다 작아 보였고, 최대 폭이 정해진
/// 목록은 오히려 좌우가 더 비었다. 여기서는 여백을 줄이고, 글자는
/// [CompactTextScale]이 따로 조금 줄인다. 폭은 건드리지 않는다.
///
/// 색 이름([AppColors])과 같은 방식이다. 앱 루트가 설정을 보고 [apply]를
/// 부른 뒤 화면을 새로 그린다.
abstract final class AppSpace {
  static bool _compact = false;

  /// 좁게일 때 여백에 곱하는 값.
  static const compactRatio = 0.65;

  /// 좁게일 때 글자에 곱하는 값. 여백만큼 줄이면 읽기 힘들어 덜 줄인다.
  static const compactTextRatio = 0.9;

  /// 지금 좁게인가.
  static bool get isCompact => _compact;

  /// 앱 루트에서만 부른다.
  static void apply({required bool compact}) => _compact = compact;

  /// 좁게일 때 줄·탭 바·버튼 높이에 곱하는 값. 글자가 들어가야 해서 여백보다 덜 줄인다.
  static const compactRowRatio = 0.82;

  /// 줄·탭 바·버튼처럼 높이를 박아 둔 칸.
  ///
  /// 여백만 감쌌을 때 공지 목록이 그대로였다. 줄 높이가 42로 묶여 있어 안쪽
  /// 여백이 줄어도 줄이 납작해지지 않았다.
  static double row(double value) {
    if (!_compact) return value;
    return (value * compactRowRatio).roundToDouble();
  }

  /// 여백 하나. 4 이하는 정렬을 맞추는 값이라 그대로 둔다.
  static double s(double value) {
    if (!_compact || value <= 4) return value;
    return (value * compactRatio).roundToDouble();
  }
}
