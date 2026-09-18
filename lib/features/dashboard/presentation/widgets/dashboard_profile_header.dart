import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../shared/models/user_model.dart';
import '../../../../shared/providers/mileage_providers.dart';
import '../../../mileage/presentation/widgets/mileage_credit_card.dart';
import 'dashboard_profile_card.dart';
import '../../../../core/theme/app_space.dart';

/// 대시보드 상단 — 프로필 카드 + 3D 마일리지 카드
class DashboardProfileHeader extends ConsumerWidget {
  const DashboardProfileHeader({super.key, required this.user});

  final UserModel user;

  static const _sideBySideBreakpoint = 600.0;
  /// 카드 내용 overflow 방지 최소 높이 (프로필 높이와 무관)
  static const _minCardHeight = 158.0;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final cohortEnd = ref.watch(effectiveCohortEndDateProvider);
    final validThru = cohortEnd?.add(const Duration(days: 14));

    return LayoutBuilder(
      builder: (context, constraints) {
        final sideBySide = constraints.maxWidth >= _sideBySideBreakpoint;

        if (sideBySide) {
          final mileageSlotWidth = (constraints.maxWidth - 12) * 4 / 9;

          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                flex: 5,
                child: DashboardProfileCard(user: user),
              ),
              SizedBox(width: AppSpace.s(12)),
              Expanded(
                flex: 4,
                child: Align(
                  alignment: Alignment.centerRight,
                  child: _dashboardMileageCard(
                    validThru: validThru,
                    maxWidth: mileageSlotWidth,
                  ),
                ),
              ),
            ],
          );
        }

        return Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            DashboardProfileCard(user: user),
            SizedBox(height: AppSpace.s(12)),
            MileageCreditCard(
              balance: user.mileageBalance,
              holderName: user.displayName,
              validThru: validThru,
              padding: EdgeInsets.zero,
            ),
          ],
        );
      },
    );
  }

  Widget _dashboardMileageCard({
    required DateTime? validThru,
    required double maxWidth,
  }) {
    var height = _minCardHeight;
    var width = height * kMileageCardAspectRatio;
    if (width > maxWidth && maxWidth > 0) {
      width = maxWidth;
      height = width / kMileageCardAspectRatio;
    }

    return MileageCreditCard(
      balance: user.mileageBalance,
      holderName: user.displayName,
      validThru: validThru,
      padding: EdgeInsets.zero,
      fixedSize: Size(width, height),
    );
  }
}
