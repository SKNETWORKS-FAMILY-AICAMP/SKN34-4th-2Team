import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/utils/date_utils.dart';
import '../../../../shared/models/user_model.dart';
import '../../theme/mileage_theme.dart';
import '../../../../core/theme/app_space.dart';

export 'mileage_credit_card.dart';

class MileagePageHeader extends StatelessWidget {
  const MileagePageHeader({
    super.key,
    required this.user,
    this.cohortName,
    this.subtitle = '적립 내역을 확인하고 상품을 교환하세요.',
  });

  final UserModel user;
  final String? cohortName;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(
        MileageLayout.pagePaddingH,
        AppSpace.s(8),
        MileageLayout.pagePaddingH,
        AppSpace.s(0),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '마일리지',
                  style: TextStyle(
                    fontSize: 22,
                    fontWeight: FontWeight.bold,
                    color: AppColors.textPrimary,
                  ),
                ),
                SizedBox(height: AppSpace.s(2)),
                Text(
                  subtitle,
                  style: TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 13,
                  ),
                ),
              ],
            ),
          ),
          Column(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(
                user.displayName,
                style: const TextStyle(
                  fontWeight: FontWeight.w600,
                  fontSize: 12,
                ),
              ),
              if (cohortName != null && cohortName!.isNotEmpty)
                ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 160),
                  child: Text(
                    cohortName!,
                    style: TextStyle(
                      color: AppColors.textSecondary,
                      fontSize: 10,
                    ),
                    textAlign: TextAlign.right,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ],
          ),
        ],
      ),
    );
  }
}

/// 컴팩트 2탭 세그먼트
class MileageSegmentTabs extends StatelessWidget {
  const MileageSegmentTabs({
    super.key,
    required this.tabs,
    required this.selectedIndex,
    required this.onSelected,
  });

  final List<String> tabs;
  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: MileageLayout.pagePaddingH),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            maxWidth: MileageLayout.maxContentWidth,
            minWidth: 320,
          ),
          child: SizedBox(
            width: double.infinity,
            height: AppSpace.row(40),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: AppColors.surface,
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: AppColors.border),
              ),
              child: Row(
                children: [
                  for (var i = 0; i < tabs.length; i++) ...[
                    if (i > 0)
                      Container(width: 1, color: AppColors.border),
                    Expanded(
                      child: _SegmentTab(
                        label: tabs[i],
                        selected: selectedIndex == i,
                        isFirst: i == 0,
                        isLast: i == tabs.length - 1,
                        onTap: () => onSelected(i),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _SegmentTab extends StatelessWidget {
  const _SegmentTab({
    required this.label,
    required this.selected,
    required this.isFirst,
    required this.isLast,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final bool isFirst;
  final bool isLast;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected ? AppColors.textPrimary : Colors.transparent,
      borderRadius: BorderRadius.horizontal(
        left: isFirst ? const Radius.circular(19) : Radius.zero,
        right: isLast ? const Radius.circular(19) : Radius.zero,
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.horizontal(
          left: isFirst ? const Radius.circular(19) : Radius.zero,
          right: isLast ? const Radius.circular(19) : Radius.zero,
        ),
        child: Center(
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: AppSpace.s(8)),
            child: Text(
              label,
              maxLines: 1,
              softWrap: false,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 13,
                fontWeight: FontWeight.w600,
                // 선택 칸은 글씨색으로 칠한다. 그 위 글씨는 바탕색이어야 라이트에서는
                // 검정 칸에 흰 글씨, 다크에서는 밝은 칸에 어두운 글씨가 된다.
                color: selected ? AppColors.surface : AppColors.textPrimary,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class MileageTagChip extends StatelessWidget {
  const MileageTagChip({
    super.key,
    required this.label,
    required this.color,
  });

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(6), vertical: AppSpace.s(2)),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 10,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class MileageFilterChipRow extends StatelessWidget {
  const MileageFilterChipRow({
    super.key,
    required this.options,
    required this.selected,
    required this.onSelected,
    this.label,
  });

  final String? label;
  final List<(String value, String label)> options;
  final String selected;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (label != null) ...[
          Text(
            label!,
            style: TextStyle(
              fontWeight: FontWeight.w600,
              fontSize: 12,
              color: AppColors.textSecondary,
            ),
          ),
          SizedBox(height: AppSpace.s(6)),
        ],
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: options.map((opt) {
            final isSelected = selected == opt.$1;
            return FilterChip(
              label: Text(opt.$2),
              selected: isSelected,
              onSelected: (_) => onSelected(opt.$1),
              selectedColor: MileageColors.chipBg,
              checkmarkColor: MileageColors.primary,
              labelStyle: TextStyle(
                color:
                    isSelected ? MileageColors.primary : AppColors.textPrimary,
                fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                fontSize: 12,
              ),
              side: BorderSide(
                color: isSelected ? MileageColors.primary : AppColors.border,
              ),
              showCheckmark: false,
              visualDensity: VisualDensity.compact,
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              padding: EdgeInsets.symmetric(horizontal: AppSpace.s(2)),
            );
          }).toList(),
        ),
      ],
    );
  }
}

/// 날짜 필터 — 2줄 레이아웃
class MileageDateFilterBar extends StatelessWidget {
  const MileageDateFilterBar({
    super.key,
    required this.startDate,
    required this.endDate,
    required this.onPickStart,
    required this.onPickEnd,
    required this.onPresetMonth,
    required this.onPresetAll,
    required this.presetMonthSelected,
    required this.presetAllSelected,
  });

  final DateTime? startDate;
  final DateTime? endDate;
  final VoidCallback onPickStart;
  final VoidCallback onPickEnd;
  final VoidCallback onPresetMonth;
  final VoidCallback onPresetAll;
  final bool presetMonthSelected;
  final bool presetAllSelected;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: MileageLayout.pagePaddingH),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: MileageLayout.maxContentWidth),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Expanded(
                    child: _DateField(
                      label: '시작일',
                      date: startDate,
                      onTap: onPickStart,
                    ),
                  ),
                  Padding(
                    padding: EdgeInsets.symmetric(horizontal: AppSpace.s(6)),
                    child: Text('~', style: TextStyle(fontSize: 13)),
                  ),
                  Expanded(
                    child: _DateField(
                      label: '종료일',
                      date: endDate,
                      onTap: onPickEnd,
                    ),
                  ),
                ],
              ),
              SizedBox(height: AppSpace.s(8)),
              Wrap(
                spacing: 6,
                runSpacing: 6,
                alignment: WrapAlignment.end,
                children: [
                  _SmallPresetChip(
                    label: '1개월',
                    selected: presetMonthSelected,
                    onTap: onPresetMonth,
                  ),
                  _SmallPresetChip(
                    label: '전체',
                    selected: presetAllSelected,
                    onTap: onPresetAll,
                  ),
                  FilledButton(
                    style: FilledButton.styleFrom(
                      backgroundColor: AppColors.primary,
                      minimumSize: const Size(0, 32),
                      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(14)),
                      textStyle: const TextStyle(fontSize: 12),
                    ),
                    onPressed: () {},
                    child: const Text('조회'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _DateField extends StatelessWidget {
  const _DateField({
    required this.label,
    required this.date,
    required this.onTap,
  });

  final String label;
  final DateTime? date;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: InputDecorator(
        decoration: InputDecoration(
          labelText: label,
          labelStyle: const TextStyle(fontSize: 12),
          border: const OutlineInputBorder(),
          contentPadding: EdgeInsets.symmetric(horizontal: AppSpace.s(10), vertical: AppSpace.s(6)),
          suffixIcon: const Icon(Icons.calendar_today, size: 16),
          isDense: true,
        ),
        child: Text(
          date != null ? AppDateUtils.toDateKey(date!) : '-',
          style: const TextStyle(fontSize: 12),
        ),
      ),
    );
  }
}

class _SmallPresetChip extends StatelessWidget {
  const _SmallPresetChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: selected ? AppColors.primary : AppColors.surfaceVariant,
      borderRadius: BorderRadius.circular(6),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(6),
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpace.s(10), vertical: AppSpace.s(6)),
          child: Text(
            label,
            style: TextStyle(
              fontSize: 11,
              color: selected ? Colors.white : AppColors.textPrimary,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ),
    );
  }
}

/// 마일리지 페이지 공통 스크롤 래퍼
class MileagePageScroll extends StatelessWidget {
  const MileagePageScroll({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: EdgeInsets.only(bottom: AppSpace.s(32)),
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: MileageLayout.maxContentWidth + 40),
          child: child,
        ),
      ),
    );
  }
}
