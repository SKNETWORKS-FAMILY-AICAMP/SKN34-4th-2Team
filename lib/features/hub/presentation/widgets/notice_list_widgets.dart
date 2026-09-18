import 'package:flutter/material.dart';
import 'package:flutter_markdown_plus/flutter_markdown_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/date_utils.dart';
import '../../../../shared/models/notice_model.dart';
import 'board_ui.dart';
import '../../../../core/theme/app_space.dart';

String noticeTimeAgo(DateTime? dt) {
  if (dt == null) return '';
  final diff = DateTime.now().difference(dt);
  if (diff.inDays > 6) return AppDateUtils.formatDateTime(dt);
  if (diff.inDays > 0) return '${diff.inDays}일 전';
  if (diff.inHours > 0) return '${diff.inHours}시간 전';
  if (diff.inMinutes > 0) return '${diff.inMinutes}분 전';
  return '방금';
}

/// 한 줄 컴팩트 공지 행 — [아이콘] [제목] [공지 · N분 전] [>]
class StudentNoticeRow extends StatelessWidget {
  const StudentNoticeRow({
    super.key,
    required this.notice,
    this.onTap,
    this.trailing,
  });

  final NoticeModel notice;
  final VoidCallback? onTap;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final isFavorite = notice.isFavorite;
    final isDiscord = notice.isFromDiscord;

    final (icon, iconColor) = switch ((isFavorite, isDiscord)) {
      (true, _) => (Icons.star_rounded, BoardUi.favorite),
      (_, true) => (Icons.discord, BoardUi.discordChipText),
      _ => (Icons.campaign_outlined, AppColors.textSecondary),
    };

    final meta = [
      notice.displayLabel,
      if (notice.createdAt != null) noticeTimeAgo(notice.createdAt),
    ].where((s) => s.isNotEmpty).join(' · ');

    return Material(
      color: isFavorite
          ? AppColors.tint(const Color(0xFFFFFBEB))
          : Colors.transparent,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpace.s(14),
            vertical: AppSpace.s(11),
          ),
          child: Row(
            children: [
              Icon(icon, size: 18, color: iconColor),
              SizedBox(width: AppSpace.s(10)),
              Expanded(
                child: Text(
                  notice.title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                    color: AppColors.textPrimary,
                  ),
                ),
              ),
              SizedBox(width: AppSpace.s(8)),
              Text(
                meta,
                style: TextStyle(
                  fontSize: 11,
                  color: AppColors.textHint,
                ),
              ),
              if (trailing != null) trailing!,
              Icon(
                Icons.chevron_right_rounded,
                size: 18,
                color: AppColors.textHint,
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// 컴팩트 공지 목록 (구분선 포함)
class StudentNoticeRowList extends StatelessWidget {
  const StudentNoticeRowList({
    super.key,
    required this.notices,
    required this.onTap,
    this.maxVisibleRows,
    this.trailingBuilder,
  });

  final List<NoticeModel> notices;
  final ValueChanged<NoticeModel> onTap;

  /// 지정 시 이 개수만큼만 박스 높이를 고정하고 내부 스크롤
  final int? maxVisibleRows;
  final Widget? Function(NoticeModel notice)? trailingBuilder;

  static double get _rowHeight => AppSpace.row(42);
  static const _dividerHeight = 1.0;

  double? get _maxHeight {
    if (maxVisibleRows == null || notices.length <= maxVisibleRows!) {
      return null;
    }
    final rows = maxVisibleRows!;
    return rows * _rowHeight + (rows - 1) * _dividerHeight;
  }

  @override
  Widget build(BuildContext context) {
    final children = <Widget>[
      for (var i = 0; i < notices.length; i++) ...[
        if (i > 0) const Divider(height: _dividerHeight, thickness: 1),
        SizedBox(
          height: _rowHeight,
          child: StudentNoticeRow(
            notice: notices[i],
            onTap: () => onTap(notices[i]),
            trailing: trailingBuilder?.call(notices[i]),
          ),
        ),
      ],
    ];

    final listBody = _maxHeight != null
        ? SizedBox(
            height: _maxHeight,
            child: ListView(
              padding: EdgeInsets.zero,
              physics: const ClampingScrollPhysics(),
              children: children,
            ),
          )
        : Column(mainAxisSize: MainAxisSize.min, children: children);

    return Container(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppColors.border),
        boxShadow: [
          BoxShadow(
            color: AppColors.shadow,
            blurRadius: 16,
            offset: Offset(0, 4),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: listBody,
    );
  }
}

/// 대시보드·목록용 컴팩트 공지 타일
class StudentNoticeTile extends StatelessWidget {
  const StudentNoticeTile({
    super.key,
    required this.notice,
    this.onTap,
    this.showChevron = true,
  });

  final NoticeModel notice;
  final VoidCallback? onTap;
  final bool showChevron;

  @override
  Widget build(BuildContext context) {
    final isFavorite = notice.isFavorite;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(14),
        child: Ink(
          decoration: BoxDecoration(
            color: isFavorite
                ? AppColors.tint(const Color(0xFFFFFBEB))
                : AppColors.surface,
            borderRadius: BorderRadius.circular(14),
            border: Border.all(
              color: isFavorite ? BoardUi.favoriteBorder : AppColors.border,
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: isFavorite ? 0.04 : 0.03),
                blurRadius: 10,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Padding(
            padding: EdgeInsets.fromLTRB(
              AppSpace.s(14),
              AppSpace.s(14),
              AppSpace.s(12),
              AppSpace.s(14),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _NoticeIconBadge(notice: notice),
                SizedBox(width: AppSpace.s(12)),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: Text(
                              notice.title,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 15,
                                fontWeight: FontWeight.w700,
                                height: 1.3,
                                color: AppColors.textPrimary,
                              ),
                            ),
                          ),
                          if (isFavorite) ...[
                            SizedBox(width: AppSpace.s(8)),
                            const BoardMetaChip(
                              label: '중요',
                              variant: BoardMetaChipVariant.favorite,
                            ),
                          ],
                        ],
                      ),
                      SizedBox(height: AppSpace.s(6)),
                      Text(
                        notice.content,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 13,
                          height: 1.5,
                          color: AppColors.textSecondary,
                        ),
                      ),
                      SizedBox(height: AppSpace.s(10)),
                      Row(
                        children: [
                          BoardMetaChip(
                            label: notice.displayLabel,
                            variant: notice.isFromDiscord
                                ? BoardMetaChipVariant.discord
                                : BoardMetaChipVariant.neutral,
                          ),
                          SizedBox(width: AppSpace.s(8)),
                          Text(
                            noticeTimeAgo(notice.createdAt),
                            style: TextStyle(
                              fontSize: 11,
                              color: AppColors.textHint,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                if (showChevron) ...[
                  SizedBox(width: AppSpace.s(4)),
                  Padding(
                    padding: EdgeInsets.only(top: AppSpace.s(2)),
                    child: Icon(
                      Icons.chevron_right_rounded,
                      size: 20,
                      color: AppColors.textHint,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _NoticeIconBadge extends StatelessWidget {
  const _NoticeIconBadge({required this.notice});

  final NoticeModel notice;

  @override
  Widget build(BuildContext context) {
    final isFavorite = notice.isFavorite;
    final isDiscord = notice.isFromDiscord;

    final (bg, fg, icon) = switch ((isFavorite, isDiscord)) {
      (true, _) => (
        BoardUi.favoriteBadgeBg,
        BoardUi.favorite,
        Icons.star_rounded,
      ),
      (_, true) => (
        BoardUi.discordChipBg,
        BoardUi.discordChipText,
        Icons.discord,
      ),
      _ => (
        AppColors.primaryLight,
        AppColors.textSecondary,
        Icons.campaign_outlined,
      ),
    };

    return Container(
      width: 40,
      height: AppSpace.row(40),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Icon(icon, size: 20, color: fg),
    );
  }
}

/// 공지 카드 — 학생·관리자 공용 (Figma 스타일)
class NoticeCard extends StatelessWidget {
  const NoticeCard({
    super.key,
    required this.notice,
    this.onTap,
    this.trailing,
    this.compact = false,
  });

  final NoticeModel notice;
  final VoidCallback? onTap;
  final Widget? trailing;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    if (trailing == null) {
      return Padding(
        padding: EdgeInsets.only(
          bottom: compact ? AppSpace.s(8) : AppSpace.s(10),
        ),
        child: StudentNoticeTile(
          notice: notice,
          onTap: onTap,
          showChevron: false,
        ),
      );
    }

    return Container(
      margin: EdgeInsets.only(
        bottom: compact ? AppSpace.s(10) : AppSpace.s(12),
      ),
      decoration: BoardUi.cardDecoration(
        isFavorite: notice.isFavorite,
        isDiscord: notice.isFromDiscord,
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Padding(
            padding: EdgeInsets.all(compact ? AppSpace.s(12) : AppSpace.s(16)),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _NoticeIconBadge(notice: notice),
                SizedBox(width: compact ? 10 : 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              notice.title,
                              style: TextStyle(
                                fontWeight: FontWeight.w700,
                                fontSize: compact ? 14 : 15,
                                color: AppColors.textPrimary,
                              ),
                            ),
                          ),
                          if (notice.isFavorite)
                            const BoardMetaChip(
                              label: '중요',
                              variant: BoardMetaChipVariant.favorite,
                            ),
                        ],
                      ),
                      SizedBox(height: compact ? 4 : 6),
                      Text(
                        notice.content,
                        maxLines: compact ? 2 : 3,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: compact ? 12 : 13,
                          height: 1.45,
                          color: AppColors.textSecondary,
                        ),
                      ),
                      SizedBox(height: compact ? 8 : 10),
                      Row(
                        children: [
                          BoardMetaChip(
                            label: notice.displayLabel,
                            variant: notice.isFromDiscord
                                ? BoardMetaChipVariant.discord
                                : BoardMetaChipVariant.neutral,
                          ),
                          SizedBox(width: AppSpace.s(8)),
                          Text(
                            _metaLine(notice),
                            style: TextStyle(
                              fontSize: 11,
                              color: AppColors.textHint,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                ?trailing,
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _metaLine(NoticeModel notice) {
    final parts = <String>[
      if (notice.authorName.isNotEmpty) notice.authorName,
      if (notice.createdAt != null) noticeTimeAgo(notice.createdAt),
    ];
    return parts.join(' · ');
  }
}

/// 공지 상세 보기
class NoticeDetailSheet extends StatelessWidget {
  const NoticeDetailSheet({super.key, required this.notice});

  final NoticeModel notice;

  static Future<void> show(BuildContext context, NoticeModel notice) {
    return showDialog<void>(
      context: context,
      useSafeArea: true,
      builder: (_) => NoticeDetailSheet(notice: notice),
    );
  }

  @override
  Widget build(BuildContext context) {
    final screenHeight = MediaQuery.sizeOf(context).height;
    return Dialog(
      insetPadding: EdgeInsets.symmetric(
        horizontal: AppSpace.s(24),
        vertical: AppSpace.s(32),
      ),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
      clipBehavior: Clip.antiAlias,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: 800,
          maxHeight: screenHeight * 0.84,
        ),
        child: Column(
          children: [
            Expanded(
              child: ListView(
                padding: EdgeInsets.fromLTRB(
                  AppSpace.s(24),
                  AppSpace.s(14),
                  AppSpace.s(24),
                  AppSpace.s(32),
                ),
                children: [
                  Center(
                    child: Container(
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(
                        color: AppColors.border,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  SizedBox(height: AppSpace.s(20)),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _NoticeIconBadge(notice: notice),
                      SizedBox(width: AppSpace.s(12)),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              notice.title,
                              style: const TextStyle(
                                fontSize: 20,
                                fontWeight: FontWeight.bold,
                                height: 1.35,
                              ),
                            ),
                            SizedBox(height: AppSpace.s(8)),
                            Wrap(
                              spacing: 8,
                              runSpacing: 6,
                              children: [
                                if (notice.isFavorite)
                                  const BoardMetaChip(
                                    label: '중요 공지',
                                    variant: BoardMetaChipVariant.favorite,
                                  ),
                                BoardMetaChip(
                                  label: notice.displayLabel,
                                  variant: notice.isFromDiscord
                                      ? BoardMetaChipVariant.discord
                                      : BoardMetaChipVariant.neutral,
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: AppSpace.s(12)),
                  Text(
                    '${notice.authorName}'
                    '${notice.createdAt != null ? ' · ${AppDateUtils.formatDateTime(notice.createdAt!)}' : ''}',
                    style: TextStyle(
                      fontSize: 12,
                      color: AppColors.textSecondary,
                    ),
                  ),
                  SizedBox(height: AppSpace.s(20)),
                  const Divider(height: 1),
                  SizedBox(height: AppSpace.s(20)),
                  MarkdownBody(
                    data: notice.content.replaceAll(
                      RegExp(r'^\s*•\s+', multiLine: true),
                      '- ',
                    ),
                    selectable: true,
                    softLineBreak: true,
                    onTapLink: (_, href, _) {
                      if (href == null) return;
                      launchUrl(
                        Uri.parse(href),
                        mode: LaunchMode.externalApplication,
                      );
                    },
                    styleSheet: MarkdownStyleSheet(
                      p: TextStyle(
                        fontSize: 15,
                        height: 1.8,
                        color: AppColors.textPrimary,
                      ),
                      listBullet: TextStyle(
                        fontSize: 15,
                        height: 1.8,
                        color: AppColors.textPrimary,
                      ),
                      strong: TextStyle(
                        color: AppColors.textPrimary,
                        fontWeight: FontWeight.w800,
                      ),
                      a: TextStyle(
                        color: AppColors.primary,
                        decoration: TextDecoration.underline,
                        decorationColor: AppColors.primary,
                      ),
                    ),
                  ),
                  if (notice.imageUrl != null &&
                      notice.imageUrl!.isNotEmpty) ...[
                    SizedBox(height: AppSpace.s(20)),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(12),
                      child: Image.network(
                        notice.imageUrl!,
                        width: double.infinity,
                        fit: BoxFit.contain,
                        errorBuilder: (_, _, _) => Container(
                          height: 120,
                          alignment: Alignment.center,
                          color: AppColors.surfaceVariant,
                          child: const Text('이미지를 불러오지 못했습니다.'),
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            Container(
              width: double.infinity,
              padding: EdgeInsets.symmetric(
                horizontal: AppSpace.s(24),
                vertical: AppSpace.s(12),
              ),
              decoration: BoxDecoration(
                color: AppColors.surface,
                border: Border(top: BorderSide(color: AppColors.border)),
              ),
              child: Align(
                alignment: Alignment.centerRight,
                child: TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('닫기'),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
