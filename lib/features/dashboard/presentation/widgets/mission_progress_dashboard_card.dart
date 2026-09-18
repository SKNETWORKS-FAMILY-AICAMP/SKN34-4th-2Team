import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/routing/route_paths.dart';
import '../../../../core/theme/app_colors.dart';
import '../../../../shared/models/mission_models.dart';
import '../../../../shared/providers/mission_providers.dart';
import '../../../../shared/widgets/app_section_card.dart';
import '../../../../core/theme/app_space.dart';

/// 대시보드 — 마일리지 미션 프로그레스 (LXP 1순위)
class MissionProgressDashboardCard extends ConsumerWidget {
  const MissionProgressDashboardCard({
    super.key,
    this.compact = false,
  });

  /// 오른쪽 사이드바(좁은 폭)용
  final bool compact;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(missionProgressProvider);
    final items = ref.watch(missionGuidanceProvider);

    final sorted = [...items]
      ..sort((a, b) {
        final aDone = a.maxEarn > 0 && a.earned >= a.maxEarn;
        final bDone = b.maxEarn > 0 && b.earned >= b.maxEarn;
        if (aDone == bDone) return 0;
        return aDone ? 1 : -1;
      });
    final visible = sorted.take(compact ? 3 : 4).toList();

    MissionGuidanceItem? nextFocus;
    for (final e in sorted) {
      final done = e.maxEarn > 0 && e.earned >= e.maxEarn;
      if (!done) {
        nextFocus = e;
        break;
      }
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        AppSectionTitle(
          '미션 프로그레스',
          compact: compact,
          trailing: TextButton(
            onPressed: () => context.go(RoutePaths.records),
            style: TextButton.styleFrom(
              foregroundColor: AppColors.primary,
              visualDensity: VisualDensity.compact,
              padding: EdgeInsets.symmetric(horizontal: AppSpace.s(6)),
              minimumSize: Size.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: const Text('기록실', style: TextStyle(fontSize: 12)),
          ),
        ),
        AppSectionCard(
          padding: compact
              ? EdgeInsets.fromLTRB(AppSpace.s(10), AppSpace.s(10), AppSpace.s(10), AppSpace.s(10))
              : EdgeInsets.fromLTRB(AppSpace.s(14), AppSpace.s(12), AppSpace.s(14), AppSpace.s(14)),
          child: async.when(
            loading: () => SizedBox(
              height: compact ? 56 : 72,
              child: const Center(
                child: SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            ),
            error: (e, _) => Text(
              '미션 정보를 불러오지 못했습니다.',
              style: TextStyle(
                fontSize: compact ? 11 : 13,
                color: AppColors.error.withValues(alpha: 0.9),
              ),
            ),
            data: (_) => Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (nextFocus != null) ...[
                  Container(
                    padding: EdgeInsets.fromLTRB(
                      compact ? AppSpace.s(8) : AppSpace.s(12),
                      compact ? AppSpace.s(8) : AppSpace.s(10),
                      compact ? AppSpace.s(8) : AppSpace.s(12),
                      compact ? AppSpace.s(8) : AppSpace.s(10),
                    ),
                    decoration: BoxDecoration(
                      color: AppColors.primaryLight,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(
                        color: AppColors.primary.withValues(alpha: 0.25),
                      ),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Icon(
                              Icons.flag_outlined,
                              size: 16,
                              color: AppColors.primary,
                            ),
                            SizedBox(width: AppSpace.s(6)),
                            Expanded(
                              child: Text(
                                compact
                                    ? '다음 · ${nextFocus.title}'
                                    : '다음 목표 · ${nextFocus.title}',
                                maxLines: compact ? 2 : 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: compact ? 11 : 12,
                                  height: 1.3,
                                  fontWeight: FontWeight.w700,
                                  color: AppColors.textPrimary,
                                ),
                              ),
                            ),
                          ],
                        ),
                        SizedBox(height: AppSpace.s(4)),
                        Text(
                          nextFocus.statusText,
                          maxLines: compact ? 2 : 2,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: compact ? 10 : 12,
                            height: 1.3,
                            fontWeight: FontWeight.w500,
                            color: AppColors.textSecondary,
                          ),
                        ),
                      ],
                    ),
                  ),
                  SizedBox(height: compact ? 10 : 12),
                ] else ...[
                  Text(
                    compact
                        ? '주요 미션을 모두 달성했어요.'
                        : '주요 미션을 모두 달성했어요. 기록실에서 추가 활동을 이어가 보세요.',
                    style: TextStyle(
                      fontSize: compact ? 11 : 12,
                      color: AppColors.textSecondary,
                      height: 1.35,
                    ),
                  ),
                  SizedBox(height: compact ? 10 : 12),
                ],
                ...visible.map(
                  (item) => _MissionProgressRow(
                    item: item,
                    compact: compact,
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _MissionProgressRow extends StatelessWidget {
  const _MissionProgressRow({
    required this.item,
    this.compact = false,
  });

  final MissionGuidanceItem item;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final ratio = item.maxEarn <= 0
        ? 0.0
        : (item.earned / item.maxEarn).clamp(0.0, 1.0);
    final done = item.maxEarn > 0 && item.earned >= item.maxEarn;

    return Padding(
      padding: EdgeInsets.only(bottom: compact ? AppSpace.s(10) : AppSpace.s(12)),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            item.title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: compact ? 12 : 13,
              fontWeight: FontWeight.w700,
              color: AppColors.textPrimary,
            ),
          ),
          SizedBox(height: AppSpace.s(2)),
          Text(
            done ? '완료' : '${_fmt(item.earned)} / ${_fmt(item.maxEarn)}M',
            style: TextStyle(
              fontSize: compact ? 10 : 11,
              fontWeight: FontWeight.w700,
              color: done ? const Color(0xFF166534) : AppColors.primary,
            ),
          ),
          SizedBox(height: AppSpace.s(4)),
          ClipRRect(
            borderRadius: BorderRadius.circular(999),
            child: LinearProgressIndicator(
              value: ratio,
              minHeight: compact ? 6 : 7,
              backgroundColor: AppColors.tint(const Color(0xFFE5E7EB)),
              color: done ? const Color(0xFF22C55E) : AppColors.primary,
            ),
          ),
          if (!compact) ...[
            SizedBox(height: AppSpace.s(4)),
            Text(
              item.progressLabel,
              style: TextStyle(
                fontSize: 11,
                color: AppColors.textSecondary,
              ),
            ),
          ],
        ],
      ),
    );
  }

  String _fmt(int n) {
    final s = n.toString();
    final buf = StringBuffer();
    for (var i = 0; i < s.length; i++) {
      final fromEnd = s.length - i;
      buf.write(s[i]);
      if (fromEnd > 1 && fromEnd % 3 == 1) buf.write(',');
    }
    return buf.toString();
  }
}
