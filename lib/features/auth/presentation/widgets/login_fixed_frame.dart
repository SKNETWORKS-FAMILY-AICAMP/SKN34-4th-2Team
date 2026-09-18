import 'package:flutter/material.dart';

import 'login_brand_stage.dart';

/// 로그인 구도를 창 크기에 다시 배치하지 않는다.
/// 가장 큰 창(전체화면)에서는 카드·로고를 원래 논리 픽셀 그대로 그리고,
/// 창이 줄면 그 프레임을 비율 유지한 채 맞춘다.
class LoginFixedFrame extends StatefulWidget {
  const LoginFixedFrame({super.key, required this.child});

  final Widget child;

  @override
  State<LoginFixedFrame> createState() => _LoginFixedFrameState();
}

class _LoginFixedFrameState extends State<LoginFixedFrame> {
  Size? _origin;

  @override
  Widget build(BuildContext context) {
    return LoginStageWash(
      child: LayoutBuilder(
        builder: (context, constraints) {
          final view = Size(constraints.maxWidth, constraints.maxHeight);
          final origin = _resolveOrigin(view);
          final scale = _containScale(view, origin);
          final fitted = Size(origin.width * scale, origin.height * scale);

          return Center(
            child: SizedBox(
              width: fitted.width,
              height: fitted.height,
              child: ClipRect(
                child: FittedBox(
                  fit: BoxFit.fill,
                  alignment: Alignment.center,
                  child: SizedBox.fromSize(
                    size: origin,
                    child: MediaQuery(
                      data: MediaQuery.of(context).copyWith(
                        size: origin,
                        textScaler: TextScaler.noScaling,
                        padding: EdgeInsets.zero,
                        viewPadding: EdgeInsets.zero,
                        viewInsets: EdgeInsets.zero,
                      ),
                      child: widget.child,
                    ),
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  /// 창이 커지면 그 크기를 원래 프레임으로 다시 잡는다. 줄면 유지한다.
  Size _resolveOrigin(Size view) {
    if (!_usable(view)) return _origin ?? view;

    final current = _origin;
    if (current == null ||
        (view.width + 1 >= current.width && view.height + 1 >= current.height)) {
      _origin = view;
      return view;
    }
    return current;
  }

  static bool _usable(Size size) => size.width >= 320 && size.height >= 320;

  static double _containScale(Size view, Size canvas) {
    if (view.width <= 0 || view.height <= 0) return 1;
    if (canvas.width <= 0 || canvas.height <= 0) return 1;
    final scale = (view.width / canvas.width) < (view.height / canvas.height)
        ? view.width / canvas.width
        : view.height / canvas.height;
    if (!scale.isFinite || scale <= 0) return 1;
    // 원래 크기보다 키우지 않는다. 창이 작을 때만 줄인다.
    return scale > 1 ? 1 : scale;
  }
}
