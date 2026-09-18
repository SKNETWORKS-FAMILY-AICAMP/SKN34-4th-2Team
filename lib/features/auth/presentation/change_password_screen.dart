import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/role.dart';
import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../providers/auth_providers.dart';
import 'widgets/password_change_panel.dart';
import '../../../core/theme/app_space.dart';

/// 최초 로그인 시 비밀번호 변경 화면
class ChangePasswordScreen extends ConsumerWidget {
  const ChangePasswordScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider).value;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text('비밀번호 변경'),
        centerTitle: true,
      ),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: EdgeInsets.all(AppSpace.s(24)),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 400),
              child: Container(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpace.s(24),
                  vertical: AppSpace.s(28),
                ),
                decoration: BoxDecoration(
                  color: AppColors.surface,
                  borderRadius: BorderRadius.circular(24),
                  boxShadow: [
                    BoxShadow(
                      color: AppColors.shadow,
                      blurRadius: 32,
                      offset: Offset(0, 12),
                    ),
                  ],
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.lock_reset,
                      size: 40,
                      color: AppColors.primary,
                    ),
                    SizedBox(height: AppSpace.s(12)),
                    Text(
                      '보안을 위해 비밀번호를 변경해 주세요.',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 14,
                        color: AppColors.textSecondary,
                      ),
                    ),
                    SizedBox(height: AppSpace.s(8)),
                    Text(
                      '마이페이지에서도 언제든 변경할 수 있습니다.',
                      textAlign: TextAlign.center,
                      style: TextStyle(
                        fontSize: 12,
                        color: AppColors.textHint,
                      ),
                    ),
                    SizedBox(height: AppSpace.s(20)),
                    PasswordChangePanel(
                      compact: true,
                      showSkipButton: true,
                      onSuccess: () {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('비밀번호가 변경되었습니다.')),
                        );
                        final home = RoutePaths.homeFor(
                          user?.role ?? UserRole.student,
                        );
                        context.go(home);
                      },
                      onSkip: () {
                        final home = RoutePaths.homeFor(
                          user?.role ?? UserRole.student,
                        );
                        context.go(home);
                      },
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
