import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/theme/app_layout.dart';
import '../../../../shared/models/user_model.dart';
import '../../../../core/theme/app_space.dart';

/// 기록실 페이지 최대 너비
abstract final class RecordLayout {
  static const maxContentWidth = AppLayout.list;
  static const horizontalPadding = 24.0;
  static const verticalPadding = 20.0;
}

/// 기록실 공통 — 중앙 정렬 + max-width
class RecordPageScaffold extends StatelessWidget {
  const RecordPageScaffold({
    super.key,
    required this.user,
    this.cohortName,
    required this.body,
    this.bottom,
  });

  final UserModel user;
  final String? cohortName;
  final Widget body;
  final Widget? bottom;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              maxWidth: RecordLayout.maxContentWidth,
            ),
            child: Padding(
              padding: EdgeInsets.fromLTRB(
                RecordLayout.horizontalPadding,
                RecordLayout.verticalPadding,
                RecordLayout.horizontalPadding,
                AppSpace.s(12),
              ),
              child: RecordPageHeader(user: user, cohortName: cohortName),
            ),
          ),
        ),
        Expanded(
          child: Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
              constraints: const BoxConstraints(
                maxWidth: RecordLayout.maxContentWidth,
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: RecordLayout.horizontalPadding,
                ),
                child: body,
              ),
            ),
          ),
        ),
        if (bottom != null)
          Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
              constraints: const BoxConstraints(
                maxWidth: RecordLayout.maxContentWidth,
              ),
              child: Padding(
                padding: EdgeInsets.fromLTRB(
                  RecordLayout.horizontalPadding,
                  AppSpace.s(0),
                  RecordLayout.horizontalPadding,
                  RecordLayout.verticalPadding,
                ),
                child: bottom!,
              ),
            ),
          ),
      ],
    );
  }
}

/// 기록실 헤더 — 제목(좌) + 프로필(우)
class RecordPageHeader extends StatelessWidget {
  const RecordPageHeader({
    super.key,
    required this.user,
    this.cohortName,
  });

  final UserModel user;
  final String? cohortName;

  @override
  Widget build(BuildContext context) {
    final initial = user.displayName.isNotEmpty ? user.displayName[0] : '?';

    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '기록실',
                style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                  color: AppColors.textPrimary,
                ),
              ),
              SizedBox(height: AppSpace.s(6)),
              Text(
                '블로그, 스터디, 자격증 기록을 제출하고 관리하세요.',
                style: TextStyle(
                  fontSize: 13,
                  color: AppColors.textSecondary.withValues(alpha: 0.9),
                  height: 1.4,
                ),
              ),
            ],
          ),
        ),
        SizedBox(width: AppSpace.s(16)),
        Container(
          padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12), vertical: AppSpace.s(8)),
          decoration: BoxDecoration(
            color: AppColors.surfaceVariant,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: AppColors.border),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircleAvatar(
                radius: 16,
                backgroundColor: AppColors.primaryLight,
                child: Text(
                  initial,
                  style: TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.bold,
                    color: AppColors.primary,
                  ),
                ),
              ),
              SizedBox(width: AppSpace.s(8)),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    user.displayName,
                    style: const TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  if (cohortName != null)
                    Text(
                      cohortName!,
                      style: TextStyle(
                        fontSize: 11,
                        color: AppColors.textSecondary,
                      ),
                    ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// 제출 폼 카드 컨테이너
class RecordFormPanel extends StatelessWidget {
  const RecordFormPanel({
    super.key,
    required this.title,
    required this.child,
    this.actions,
  });

  final String title;
  final Widget child;
  final Widget? actions;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpace.s(24)),
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
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(
              fontSize: 20,
              fontWeight: FontWeight.w700,
              color: AppColors.textPrimary,
            ),
          ),
          SizedBox(height: AppSpace.s(20)),
          child,
          if (actions != null) ...[
            SizedBox(height: AppSpace.s(28)),
            actions!,
          ],
        ],
      ),
    );
  }
}

/// 안내 배너
class RecordInfoBanner extends StatelessWidget {
  const RecordInfoBanner({super.key, required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(14), vertical: AppSpace.s(12)),
      decoration: BoxDecoration(
        color: AppColors.primaryLight,
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline, size: 18, color: AppColors.primary),
          SizedBox(width: AppSpace.s(10)),
          Expanded(
            child: Text(
              message,
              style: TextStyle(
                fontSize: 13,
                color: AppColors.primaryDark,
                height: 1.45,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// 폼 하단 이전 / 제출 버튼
class RecordFormActions extends StatelessWidget {
  const RecordFormActions({
    super.key,
    required this.onBack,
    this.onSubmit,
    this.submitting = false,
    this.submitEnabled = true,
    this.submitLabel = '제출',
  });

  final VoidCallback onBack;
  final VoidCallback? onSubmit;
  final bool submitting;
  final bool submitEnabled;
  final String submitLabel;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        OutlinedButton(
          onPressed: submitting ? null : onBack,
          style: OutlinedButton.styleFrom(
            minimumSize: const Size(88, 40),
            side: BorderSide(color: AppColors.border),
          ),
          child: const Text('이전'),
        ),
        if (onSubmit != null) ...[
          SizedBox(width: AppSpace.s(10)),
          FilledButton(
            onPressed: (submitting || !submitEnabled) ? null : onSubmit,
            style: FilledButton.styleFrom(
              minimumSize: const Size(88, 40),
              backgroundColor: AppColors.primary,
              foregroundColor: Colors.white,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
            ),
            child: submitting
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : Text(submitLabel),
          ),
        ],
      ],
    );
  }
}

/// 폼 필드 라벨
class RecordFieldLabel extends StatelessWidget {
  const RecordFieldLabel(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpace.s(8)),
      child: Text(
        text,
        style: const TextStyle(
          fontWeight: FontWeight.w600,
          fontSize: 14,
        ),
      ),
    );
  }
}

InputDecoration recordInputDecoration({String? hint}) => InputDecoration(
  hintText: hint,
  filled: true,
  fillColor: AppColors.surfaceVariant,
  contentPadding: EdgeInsets.symmetric(horizontal: AppSpace.s(14), vertical: AppSpace.s(12)),
  border: OutlineInputBorder(
    borderRadius: BorderRadius.circular(10),
    borderSide: BorderSide(color: AppColors.border),
  ),
  enabledBorder: OutlineInputBorder(
    borderRadius: BorderRadius.circular(10),
    borderSide: BorderSide(color: AppColors.border),
  ),
);
