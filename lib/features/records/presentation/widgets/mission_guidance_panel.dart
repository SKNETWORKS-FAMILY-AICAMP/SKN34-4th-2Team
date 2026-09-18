import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../shared/models/mission_models.dart';
import '../../../../shared/providers/mission_providers.dart';
import '../../../../core/theme/app_space.dart';

/// 기록실 — 미션 진행 / 다음 목표 안내 (접기·펼치기)
class MissionGuidancePanel extends ConsumerStatefulWidget {
  const MissionGuidancePanel({super.key});

  @override
  ConsumerState<MissionGuidancePanel> createState() =>
      _MissionGuidancePanelState();
}

class _MissionGuidancePanelState extends ConsumerState<MissionGuidancePanel> {
  bool _expanded = true;

  @override
  Widget build(BuildContext context) {
    final async = ref.watch(missionProgressProvider);
    final items = ref.watch(missionGuidanceProvider);

    return Card(
      margin: EdgeInsets.only(bottom: AppSpace.s(16), right: AppSpace.s(2)),
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          InkWell(
            onTap: () => setState(() => _expanded = !_expanded),
            child: Padding(
              padding: EdgeInsets.fromLTRB(AppSpace.s(14), AppSpace.s(12), AppSpace.s(8), AppSpace.s(12)),
              child: Row(
                children: [
                  const Icon(Icons.emoji_events_outlined, size: 20),
                  SizedBox(width: AppSpace.s(8)),
                  const Expanded(
                    child: Text(
                      '마일리지 미션',
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        fontSize: 15,
                      ),
                    ),
                  ),
                  AnimatedRotation(
                    turns: _expanded ? 0.5 : 0,
                    duration: const Duration(milliseconds: 200),
                    child: Icon(
                      Icons.keyboard_arrow_down,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
          ),
          AnimatedCrossFade(
            firstChild: const SizedBox(width: double.infinity),
            secondChild: Padding(
              padding: EdgeInsets.fromLTRB(AppSpace.s(14), AppSpace.s(0), AppSpace.s(14), AppSpace.s(12)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    '기록실에 제출하고 승인되면 규칙에 따라 자동 적립됩니다.',
                    style: TextStyle(
                      fontSize: 12,
                      color: AppColors.textSecondary,
                    ),
                  ),
                  SizedBox(height: AppSpace.s(10)),
                  if (async.isLoading)
                    Padding(
                      padding: EdgeInsets.symmetric(vertical: AppSpace.s(12)),
                      child: Center(
                        child: SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                      ),
                    )
                  else
                    ...items.map((item) => _MissionTile(item: item)),
                ],
              ),
            ),
            crossFadeState: _expanded
                ? CrossFadeState.showSecond
                : CrossFadeState.showFirst,
            duration: const Duration(milliseconds: 200),
            sizeCurve: Curves.easeInOut,
          ),
        ],
      ),
    );
  }
}

class _MissionTile extends StatelessWidget {
  const _MissionTile({required this.item});

  final MissionGuidanceItem item;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpace.s(10)),
      child: Container(
        padding: EdgeInsets.all(AppSpace.s(10)),
        decoration: BoxDecoration(
          color: AppColors.surfaceVariant,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: AppColors.border),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              item.title,
              style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
            ),
            SizedBox(height: AppSpace.s(2)),
            Text(
              item.progressLabel,
              style: TextStyle(
                fontSize: 12,
                color: AppColors.textSecondary,
              ),
            ),
            SizedBox(height: AppSpace.s(2)),
            Text(
              item.statusText,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: AppColors.primary,
              ),
            ),
            SizedBox(height: AppSpace.s(4)),
            Text(
              item.hint,
              style: const TextStyle(fontSize: 12, height: 1.35),
            ),
          ],
        ),
      ),
    );
  }
}
