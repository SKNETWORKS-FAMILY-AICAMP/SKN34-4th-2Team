import 'package:flutter/widgets.dart';

import '../theme/app_space.dart';

/// 좁게일 때 글자를 조금 줄인다.
///
/// 화면마다 글자 크기를 직접 박아 두었지만 글자 배율은 그 위에 곱해지므로
/// 여기 한 곳에서 전부 줄어든다. 기기에서 키워 둔 글자 크기도 그대로 살려
/// 그 위에 곱한다.
class CompactTextScale extends StatelessWidget {
  const CompactTextScale({
    super.key,
    required this.compact,
    required this.child,
  });

  final bool compact;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    if (!compact) return child;
    final media = MediaQuery.of(context);
    return MediaQuery(
      data: media.copyWith(
        textScaler: TextScaler.linear(
          media.textScaler.scale(1) * AppSpace.compactTextRatio,
        ),
      ),
      child: child,
    );
  }
}
