import 'package:flutter/material.dart';

import '../../../../core/constants/record_types.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../core/theme/app_space.dart';

/// 블로그 주차 가로 선택 칩
class RecordWeekPicker extends StatelessWidget {
  const RecordWeekPicker({
    super.key,
    required this.weeks,
    required this.approvedWeekNumbers,
    required this.selectedWeek,
    required this.onSelected,
  });

  final List<BlogWeekOption> weeks;
  final Set<int> approvedWeekNumbers;
  final int? selectedWeek;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 76,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: weeks.length,
        separatorBuilder: (_, __) => SizedBox(width: AppSpace.s(8)),
        itemBuilder: (_, i) {
          final w = weeks[i];
          final disabled = approvedWeekNumbers.contains(w.weekNumber);
          final selected = selectedWeek == w.weekNumber;

          return Material(
            color: disabled
                ? AppColors.surfaceVariant
                : selected
                ? AppColors.primaryLight
                : AppColors.surface,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
              side: BorderSide(
                color: selected
                    ? AppColors.info
                    : disabled
                    ? AppColors.border
                    : AppColors.border,
                width: selected ? 1.5 : 1,
              ),
            ),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: disabled ? null : () => onSelected(w.weekNumber),
              child: SizedBox(
                width: 96,
                child: Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpace.s(8),
                    vertical: AppSpace.s(10),
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(
                        '${w.weekNumber}주차',
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.w600,
                          color: disabled
                              ? AppColors.textHint
                              : AppColors.textPrimary,
                        ),
                      ),
                      SizedBox(height: AppSpace.s(4)),
                      Text(
                        _shortRange(w),
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 10,
                          color: disabled
                              ? AppColors.textHint
                              : AppColors.textSecondary,
                        ),
                      ),
                      if (disabled)
                        Text(
                          '승인됨',
                          style: TextStyle(
                            fontSize: 9,
                            color: AppColors.success,
                          ),
                        ),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  String _shortRange(BlogWeekOption w) {
    final s = w.start;
    final e = w.end;
    return '${s.month}/${s.day}~${e.month}/${e.day}';
  }
}
