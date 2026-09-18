import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/date_utils.dart';
import '../../../../shared/models/qual_exam_schedule_model.dart';
import '../../utils/qual_exam_utils.dart';
import '../../../../core/theme/app_space.dart';

/// 타임라인 — D-day + 세로 연결선
class QualExamTimeline extends StatelessWidget {
  const QualExamTimeline({
    super.key,
    required this.items,
    this.compact = false,
  });

  final List<QualExamScheduleModel> items;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (var i = 0; i < items.length; i++)
          _TimelineEntry(
            item: items[i],
            isLast: i == items.length - 1,
            compact: compact,
          ),
      ],
    );
  }
}

class _TimelineEntry extends StatelessWidget {
  const _TimelineEntry({
    required this.item,
    required this.isLast,
    required this.compact,
  });

  final QualExamScheduleModel item;
  final bool isLast;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final days = QualExamUtils.daysUntil(item.nextExamDate);
    final title = QualExamUtils.displayTitle(item);
    final dateLabel = item.nextExamDate != null
        ? AppDateUtils.formatYmd(item.nextExamDate)
        : '일정 미정';

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 52,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _DdayBadge(ymd: item.nextExamDate, days: days),
              if (!isLast)
                Padding(
                  padding: EdgeInsets.symmetric(vertical: AppSpace.s(4)),
                  child: Center(
                    child: Container(
                      width: 2,
                      height: compact ? 36 : 52,
                      color: AppColors.border,
                    ),
                  ),
                ),
            ],
          ),
        ),
        Expanded(
          child: Padding(
            padding: EdgeInsets.only(bottom: isLast ? AppSpace.s(0) : (compact ? AppSpace.s(12) : AppSpace.s(16))),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                  Text(
                    title,
                    maxLines: compact ? 2 : 3,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: compact ? 13 : 14,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  SizedBox(height: AppSpace.s(4)),
                  Text(
                    '${item.nextExamLabel} · $dateLabel',
                    style: TextStyle(
                      fontSize: 12,
                      color: AppColors.textSecondary,
                    ),
                  ),
                  if (!compact && item.docRegStartDt != null) ...[
                    SizedBox(height: AppSpace.s(2)),
                    Text(
                      '필기 접수 ${AppDateUtils.formatYmd(item.docRegStartDt)}'
                      '${item.docRegEndDt != null ? ' ~ ${AppDateUtils.formatYmd(item.docRegEndDt)}' : ''}',
                      style: TextStyle(
                        fontSize: 11,
                        color: AppColors.textHint,
                      ),
                    ),
                  ],
                  if (!compact &&
                      item.docRegStartDt == null &&
                      item.pracRegStartDt != null) ...[
                    SizedBox(height: AppSpace.s(2)),
                    Text(
                      '실기 접수 ${AppDateUtils.formatYmd(item.pracRegStartDt)}'
                      '${item.pracRegEndDt != null ? ' ~ ${AppDateUtils.formatYmd(item.pracRegEndDt)}' : ''}',
                      style: TextStyle(
                        fontSize: 11,
                        color: AppColors.textHint,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
      );
  }
}

class _DdayBadge extends StatelessWidget {
  const _DdayBadge({required this.ymd, required this.days});

  final String? ymd;
  final int days;

  Color get _background {
    if (days == 9999) return AppColors.primaryLight;
    if (days <= 7) return AppColors.error.withValues(alpha: 0.12);
    if (days <= 30) return AppColors.warning.withValues(alpha: 0.15);
    return AppColors.info.withValues(alpha: 0.12);
  }

  Color get _foreground {
    if (days == 9999) return AppColors.textSecondary;
    if (days <= 7) return AppColors.error;
    if (days <= 30) return AppColors.warning;
    return AppColors.info;
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 44,
      padding: EdgeInsets.symmetric(vertical: AppSpace.s(6)),
      decoration: BoxDecoration(
        color: _background,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        QualExamUtils.ddayLabel(ymd),
        textAlign: TextAlign.center,
        style: TextStyle(
          fontSize: 10,
          fontWeight: FontWeight.w700,
          color: _foreground,
          height: 1.1,
        ),
      ),
    );
  }
}
