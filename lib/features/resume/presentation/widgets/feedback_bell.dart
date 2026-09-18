import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/constants/app_constants.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/date_utils.dart';
import '../../../../shared/models/resume_model.dart';
import '../../../../shared/providers/cohort_providers.dart';
import '../../../../shared/providers/lms_providers.dart';
import '../../../../core/theme/app_space.dart';

/// 툴바의 종. 읽지 않은 피드백 수를 배지로 달고, 누르면 아래로 말풍선이 내려온다.
///
/// 말풍선은 **고르는 곳**이다. 누가 어느 항목에 남겼는지만 적고 내용은 보여 주지 않는다.
/// 내용은 항목을 눌러 뜨는 팝업에서 읽는다. 두 곳이 같은 글을 되풀이하지 않게 갈랐다.
///
/// 읽음은 **전문을 연 항목만** 넘어간다. 종을 열거나 배너를 닫는 것으로는 줄지 않는다.
/// 목록만 훑고 지나간 것을 읽었다고 세면, 정작 읽어야 할 말이 숫자와 함께 사라진다.
class FeedbackBell extends ConsumerStatefulWidget {
  const FeedbackBell({
    super.key,
    required this.resume,
    required this.onGoToSection,
    this.openOnStart = false,
  });

  final ResumeModel resume;

  /// 목록에서 「읽으러 가기」나 「다시 보기」로 들어왔을 때. 화면이 뜨자마자 펼친다.
  /// 받은 피드백이 하나라도 있으면 펼친다 — 「다시 보기」는 다 읽은 뒤에 누르는
  /// 버튼이라, 안 읽은 것만 따지면 눌러도 아무 일이 없는 것처럼 보인다.
  final bool openOnStart;

  /// 상세에서 "해당 항목으로 이동"을 눌렀을 때. 이력서를 그 섹션으로 굴린다.
  final ValueChanged<String> onGoToSection;

  @override
  ConsumerState<FeedbackBell> createState() => _FeedbackBellState();
}

class _FeedbackBellState extends ConsumerState<FeedbackBell> {
  final _link = LayerLink();
  final _controller = OverlayPortalController();

  /// 종과 말풍선을 한 무리로 묶는 표. 종을 누르는 것은 "바깥"이 아니다.
  /// 이게 없으면 종을 누를 때 닫기와 열기가 한꺼번에 일어나 창이 깜빡인다.
  final _group = Object();

  bool _open = false;

  @override
  void initState() {
    super.initState();
    // 목록 스트림은 아직 안 왔을 수 있어 이력서 문서의 건수로 판단한다.
    if (widget.openOnStart && widget.resume.feedbackCount > 0) {
      // 첫 프레임 뒤에 연다. build 중에 오버레이를 건드릴 수 없다.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _toggle();
      });
    }
  }

  void _close() {
    if (!_open) return;
    _controller.hide();
    if (mounted) setState(() => _open = false);
  }

  void _toggle() {
    if (_open) {
      _close();
      return;
    }
    _controller.show();
    setState(() => _open = true);
  }

  /// 종은 길잡이다. 읽는 곳은 항목 아래 댓글 한 곳이다.
  /// 읽음도 거기서 넘어간다 — 여기서 미리 넘기면 안 읽고도 숫자가 준다.
  void _goToSection(ResumeFeedbackModel item) {
    _close();
    widget.onGoToSection(item.sectionKey);
  }

  @override
  Widget build(BuildContext context) {
    final feedback = ref.watch(resumeFeedbackProvider(widget.resume.id));
    final items = feedback.maybeWhen(
      data: (l) => l,
      orElse: () => const <ResumeFeedbackModel>[],
    );
    // 안 읽은 건수는 **보는 사람 기준**으로 센다. 학생은 강사의 말을, 검토자는 학생의
    // 답글을 읽어야 한다. 예전에는 건수만 빼서 셌는데, 그러면 검토자가 아무리 읽어도
    // 학생의 숫자를 보고 있어 줄지 않았다.
    final asReviewer = ref.watch(canReviewResumesProvider);
    final unreadItems = unreadFeedback(
      items,
      widget.resume,
      asReviewer: asReviewer,
      viewerId: ref.watch(currentUserSyncProvider)?.uid,
    );
    final unreadIds = {for (final f in unreadItems) f.id};
    final unread = unreadItems.length;

    // OverlayPortal 은 이 위젯이 사라지면 말풍선도 함께 걷는다. OverlayEntry 를 손으로
    // 넣고 빼면, 지우는 데 실패했을 때 화면 위에 아무것도 안 눌리는 막만 남는다.
    // 가장 가까운 Overlay 를 쓴다. 뿌리 오버레이에 매달면 화면(FlutterView)이 바뀌거나
    // 웹에서 핫 리스타트할 때 이미 버려진 화면에 그리려 해 단언문이 매 프레임 터진다.
    // 종은 라우트 안에 있으니 라우트의 오버레이로 충분하다.
    return OverlayPortal(
      controller: _controller,
      // Positioned 로 감싸지 않으면 오버레이가 자식에게 화면 크기를 꽉 채우라고 시킨다.
      // 그러면 눈에 안 보이는 말풍선이 화면 전체를 덮어 아무것도 눌리지 않고,
      // followerAnchor 도 말풍선이 아니라 화면 한가운데를 가리켜 위치까지 어긋난다.
      overlayChildBuilder: (_) => Positioned(
        left: 0,
        top: 0,
        child: CompositedTransformFollower(
          link: _link,
          targetAnchor: Alignment.bottomCenter,
          followerAnchor: Alignment.topCenter,
          offset: const Offset(_FeedbackPopover.followerDx, 6),
          showWhenUnlinked: false,
          child: TapRegion(
            groupId: _group,
            // 화면을 덮는 막을 깔지 않는다. 막을 깔면 열려 있는 동안 다른 곳이 눌리지
            // 않고, 그 막이 남으면 앱이 멈춘 것처럼 보인다.
            onTapOutside: (_) => _close(),
            child: _FeedbackPopover(
              items: items,
              unreadIds: unreadIds,
              onPick: _goToSection,
              onClose: _close,
            ),
          ),
        ),
      ),
      child: TapRegion(
        groupId: _group,
        child: CompositedTransformTarget(
          link: _link,
          child: IconButton(
            tooltip: _open ? '피드백 닫기' : '피드백 열기',
            isSelected: _open,
            onPressed: items.isEmpty && widget.resume.feedbackCount == 0
                ? null
                : _toggle,
            icon: _BellIcon(unread: unread, active: _open || unread > 0),
          ),
        ),
      ),
    );
  }
}

class _BellIcon extends StatelessWidget {
  const _BellIcon({required this.unread, required this.active});

  final int unread;
  final bool active;

  @override
  Widget build(BuildContext context) {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Icon(active ? Icons.notifications : Icons.notifications_none, size: 20),
        if (unread > 0)
          Positioned(
            top: -3,
            right: -4,
            child: Container(
              constraints: const BoxConstraints(minWidth: 16),
              height: 16,
              padding: EdgeInsets.symmetric(horizontal: AppSpace.s(3)),
              decoration: BoxDecoration(
                color: AppColors.error,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppColors.surface, width: 1.5),
              ),
              child: Center(
                child: Text(
                  unread > 9 ? '9+' : '$unread',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 9.5,
                    height: 1,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

/// 종에서 내려오는 목록. 제목 줄만 있고 내용은 없다.
class _FeedbackPopover extends StatelessWidget {
  const _FeedbackPopover({
    required this.items,
    required this.unreadIds,
    required this.onPick,
    required this.onClose,
  });

  static const double width = 314;

  /// 꼬리 한가운데가 말풍선 왼쪽 끝에서 얼마나 떨어져 있나.
  /// 종은 툴바 오른쪽에 있으므로 말풍선은 왼쪽으로 눕고, 꼬리는 오른쪽 가까이에 온다.
  static const double tailFromLeft = width - 30;

  /// 말풍선을 종 기준으로 얼마나 옮길지. `followerAnchor` 가 말풍선 **한가운데**라
  /// 꼬리를 종에 맞추려면 그 차이만큼 밀어야 한다. 이 둘을 따로 적었다가 꼬리가
  /// 156px 왼쪽으로 어긋난 적이 있다. 한 값에서 뽑아 두 번 다시 어긋나지 않게 한다.
  static const double followerDx = width / 2 - tailFromLeft;

  final List<ResumeFeedbackModel> items;

  /// 안 읽은 것의 id. 보는 사람에 따라 다르므로 바깥에서 정해 준다.
  final Set<String> unreadIds;
  final ValueChanged<ResumeFeedbackModel> onPick;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    // Align 으로 감싸면 자식이 화면 크기로 늘어나고, 그러면 followerAnchor 가
    // 말풍선이 아니라 화면 한가운데를 가리켜 위치가 통째로 어긋난다. 자식은 제 크기여야 한다.
    return Material(
      color: Colors.transparent,
      child: SizedBox(
        width: width,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxHeight: 380),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // 꼬리. 종 한가운데에 온다.
              Padding(
                padding: EdgeInsets.only(left: tailFromLeft - AppSpace.s(6)),
                child: CustomPaint(
                  size: const Size(12, 7),
                  painter: _TailPainter(),
                ),
              ),
              // Flexible 이 없으면 목록이 길 때 남은 높이를 넘어서 '13 pixels
              // overflowed' 가 뜬다. 꼬리가 먼저 자리를 차지하기 때문이다.
              Flexible(
                child: Container(
                  decoration: BoxDecoration(
                    color: AppColors.surface,
                    borderRadius: BorderRadius.circular(10),
                    border: Border.all(color: AppColors.border),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.14),
                        blurRadius: 26,
                        offset: const Offset(0, 10),
                      ),
                    ],
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _header(),
                      if (items.isEmpty)
                        Padding(
                          padding: EdgeInsets.fromLTRB(AppSpace.s(13), AppSpace.s(14), AppSpace.s(13), AppSpace.s(16)),
                          child: Text(
                            '아직 피드백이 없습니다.',
                            style: TextStyle(
                              fontSize: 12.5,
                              color: AppColors.textSecondary,
                            ),
                          ),
                        )
                      else
                        Flexible(
                          child: ListView.separated(
                            // 넘칠 때만 구른다. 두세 건이면 내용만큼만 차지한다.
                            shrinkWrap: true,
                            padding: EdgeInsets.zero,
                            itemCount: items.length,
                            separatorBuilder: (_, _) => Divider(
                              height: 1,
                              color: AppColors.tint(const Color(0xFFF1F3F7)),
                            ),
                            itemBuilder: (_, i) => _Row(
                              item: items[i],
                              unread: unreadIds.contains(items[i].id),
                              onTap: () => onPick(items[i]),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _header() {
    final unread = unreadIds.length;
    return Container(
      padding: EdgeInsets.fromLTRB(AppSpace.s(13), AppSpace.s(11), AppSpace.s(8), AppSpace.s(11)),
      decoration: BoxDecoration(
        border: Border(
          bottom: BorderSide(color: AppColors.tint(const Color(0xFFEEF1F5))),
        ),
      ),
      child: Row(
        children: [
          const Text(
            '피드백',
            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 13),
          ),
          SizedBox(width: AppSpace.s(7)),
          if (unread > 0)
            Container(
              padding: EdgeInsets.symmetric(horizontal: AppSpace.s(7), vertical: AppSpace.s(1)),
              decoration: BoxDecoration(
                color: AppColors.primaryLight,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                '$unread',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w700,
                  color: AppColors.primary,
                ),
              ),
            ),
          const Spacer(),
          IconButton(
            visualDensity: VisualDensity.compact,
            iconSize: 18,
            onPressed: onClose,
            icon: Icon(Icons.close, color: AppColors.textHint),
          ),
        ],
      ),
    );
  }
}

/// 한 줄. 누가 남겼는지와 어느 항목에 대한 것인지만.
class _Row extends StatelessWidget {
  const _Row({required this.item, required this.unread, required this.onTap});

  final ResumeFeedbackModel item;
  final bool unread;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final label = sectionLabelOf(item.sectionKey);
    return InkWell(
      onTap: onTap,
      child: Container(
        padding: EdgeInsets.fromLTRB(AppSpace.s(13), AppSpace.s(11), AppSpace.s(11), AppSpace.s(11)),
        decoration: BoxDecoration(
          color: unread ? AppColors.tint(const Color(0xFFFBFCFF)) : null,
          border: Border(
            left: BorderSide(
              color: unread ? AppColors.primary : Colors.transparent,
              width: 3,
            ),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(
                  item.authorName,
                  style: TextStyle(
                    fontSize: 11.5,
                    color: AppColors.textSecondary,
                  ),
                ),
                const Spacer(),
                if (item.createdAt != null)
                  Text(
                    AppDateUtils.formatDisplay(item.createdAt!),
                    style: TextStyle(fontSize: 10.5, color: AppColors.textHint),
                  ),
              ],
            ),
            SizedBox(height: AppSpace.s(5)),
            Row(
              children: [
                Expanded(
                  child: Text.rich(
                    TextSpan(
                      children: [
                        TextSpan(
                          text: label,
                          style: TextStyle(
                            fontWeight: FontWeight.w500,
                            color: AppColors.textPrimary,
                          ),
                        ),
                        TextSpan(
                          text: '에 대한 피드백',
                          style: TextStyle(color: AppColors.textSecondary),
                        ),
                      ],
                    ),
                    style: const TextStyle(fontSize: 13),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                Icon(Icons.chevron_right, size: 16, color: AppColors.textHint),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// 종 한가운데 X 를 주면 말풍선 왼쪽 끝이 놓일 자리.
@visibleForTesting
double popoverLeftFor(double bellCenterX) =>
    bellCenterX + _FeedbackPopover.followerDx - _FeedbackPopover.width / 2;

/// 그때 꼬리 한가운데가 놓일 자리. **종 한가운데와 같아야 한다.**
@visibleForTesting
double tailCenterFor(double bellCenterX) =>
    popoverLeftFor(bellCenterX) + _FeedbackPopover.tailFromLeft;

/// 섹션 키를 사람이 읽는 이름으로. 모르는 키는 그대로 보여 준다.
String sectionLabelOf(String key) =>
    AppConstants.resumeSectionLabels[key] ?? (key.isEmpty ? '이력서' : key);

class _TailPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final path = Path()
      ..moveTo(0, size.height)
      ..lineTo(size.width / 2, 0)
      ..lineTo(size.width, size.height)
      ..close();
    canvas.drawPath(path, Paint()..color = Colors.white);
    canvas.drawPath(
      Path()
        ..moveTo(0, size.height)
        ..lineTo(size.width / 2, 0)
        ..lineTo(size.width, size.height),
      Paint()
        ..color = AppColors.border
        ..style = PaintingStyle.stroke
        ..strokeWidth = 1,
    );
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
