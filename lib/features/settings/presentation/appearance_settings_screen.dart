import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../shared/providers/app_appearance_provider.dart';
import '../../../shared/providers/side_rail_theme_provider.dart';

/// 화면 설정. 테마와 색, 밀도를 한자리에서 고른다.
///
/// 예전에는 사이드바 맨 위에 토글 두 개가 붙어 있었다. 메뉴 위에 앉아 자리를
/// 차지하면서도 무엇을 바꾸는지 알기 어려웠다.
class AppearanceSettingsScreen extends ConsumerWidget {
  const AppearanceSettingsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final mode = ref.watch(appThemeModeProvider);
    final density = ref.watch(appDensityProvider);
    final paletteIndex = ref.watch(sideRailDarkPaletteIndexProvider);

    return Scaffold(
      body: Align(
        alignment: Alignment.topCenter,
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 720),
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 40),
            children: [
              Text(
                '화면 설정',
                style: TextStyle(
                  fontSize: 20,
                  fontWeight: FontWeight.bold,
                  color: AppColors.textPrimary,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                '이 기기에만 저장됩니다. 다른 기기에서는 따로 고르면 됩니다.',
                style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
              ),
              const SizedBox(height: 20),

              _SettingGroup(
                title: '화면 테마',
                child: Column(
                  children: [
                    for (final value in AppThemeMode.values)
                      _ChoiceTile(
                        label: value.label,
                        description: value.description,
                        selected: mode == value,
                        onTap: () =>
                            ref.read(appThemeModeProvider.notifier).set(value),
                        leading: _ThemeSwatch(mode: value),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 16),

              // 밝은 테마에서도 사이드바 강조색이 버튼·링크 색으로 쓰인다.
              // 그래서 어두운 사이드바가 아닐 때도 고를 수 있게 둔다.
              _SettingGroup(
                title: '사이드바 색',
                subtitle: mode == AppThemeMode.light
                    ? '버튼과 링크 색도 여기를 따릅니다.'
                    : null,
                child: Column(
                  children: [
                    for (var i = 0; i < kSideRailDarkPalettes.length; i++)
                      _ChoiceTile(
                        label: kSideRailDarkPalettes[i].label,
                        selected: paletteIndex == i,
                        onTap: () => ref
                            .read(sideRailDarkPaletteIndexProvider.notifier)
                            .setIndex(i),
                        leading: _PaletteSwatch(
                          palette: kSideRailDarkPalettes[i],
                        ),
                      ),
                  ],
                ),
              ),
              const SizedBox(height: 16),

              _SettingGroup(
                title: '밀도',
                child: Column(
                  children: [
                    for (final value in AppDensity.values)
                      _ChoiceTile(
                        label: value.label,
                        description: value.description,
                        selected: density == value,
                        onTap: () =>
                            ref.read(appDensityProvider.notifier).set(value),
                        leading: _DensitySwatch(density: value),
                      ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SettingGroup extends StatelessWidget {
  const _SettingGroup({
    required this.title,
    required this.child,
    this.subtitle,
  });

  final String title;
  final String? subtitle;
  final Widget child;

  @override
  Widget build(BuildContext context) => Container(
    decoration: BoxDecoration(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(14),
      border: Border.all(color: AppColors.border),
    ),
    padding: const EdgeInsets.fromLTRB(16, 14, 16, 8),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          title,
          style: TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w700,
            color: AppColors.textPrimary,
          ),
        ),
        if (subtitle != null) ...[
          const SizedBox(height: 2),
          Text(
            subtitle!,
            style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
          ),
        ],
        const SizedBox(height: 8),
        child,
      ],
    ),
  );
}

class _ChoiceTile extends StatelessWidget {
  const _ChoiceTile({
    required this.label,
    required this.selected,
    required this.onTap,
    required this.leading,
    this.description,
  });

  final String label;
  final String? description;
  final bool selected;
  final VoidCallback onTap;
  final Widget leading;

  @override
  Widget build(BuildContext context) => Material(
    color: Colors.transparent,
    borderRadius: BorderRadius.circular(10),
    child: InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(10),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 10),
        child: Row(
          children: [
            leading,
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    label,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  if (description != null)
                    Text(
                      description!,
                      style: TextStyle(
                        fontSize: 12,
                        color: AppColors.textSecondary,
                      ),
                    ),
                ],
              ),
            ),
            Icon(
              selected
                  ? Icons.radio_button_checked
                  : Icons.radio_button_unchecked,
              size: 20,
              color: selected ? AppColors.primary : AppColors.textHint,
            ),
          ],
        ),
      ),
    ),
  );
}

/// 테마를 고르기 전에 어떤 모양인지 보여 주는 작은 그림.
class _ThemeSwatch extends StatelessWidget {
  const _ThemeSwatch({required this.mode});

  final AppThemeMode mode;

  @override
  Widget build(BuildContext context) {
    final railDark = mode.isRailDark;
    final bodyDark = mode.isDark;
    return Container(
      width: 40,
      height: 28,
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: Row(
        children: [
          Container(
            width: 13,
            color: railDark ? const Color(0xFF1E293B) : const Color(0xFFF3F5F9),
          ),
          Expanded(
            child: Container(
              color: bodyDark ? const Color(0xFF0F1216) : Colors.white,
            ),
          ),
        ],
      ),
    );
  }
}

class _PaletteSwatch extends StatelessWidget {
  const _PaletteSwatch({required this.palette});

  final SideRailDarkPalette palette;

  @override
  Widget build(BuildContext context) => Container(
    width: 40,
    height: 28,
    decoration: BoxDecoration(
      color: palette.background,
      borderRadius: BorderRadius.circular(6),
      border: Border.all(color: AppColors.border),
    ),
    alignment: Alignment.center,
    child: Container(
      width: 14,
      height: 4,
      decoration: BoxDecoration(
        color: palette.accent,
        borderRadius: BorderRadius.circular(2),
      ),
    ),
  );
}

/// 줄 간격이 어떻게 달라지는지 줄 수로 보여 준다.
class _DensitySwatch extends StatelessWidget {
  const _DensitySwatch({required this.density});

  final AppDensity density;

  @override
  Widget build(BuildContext context) {
    final gap = switch (density) {
      AppDensity.compact => 2.0,
      AppDensity.comfortable => 5.0,
      AppDensity.auto => 3.5,
    };
    return Container(
      width: 40,
      height: 28,
      decoration: BoxDecoration(
        color: AppColors.surfaceVariant,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: AppColors.border),
      ),
      alignment: Alignment.center,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < 3; i++) ...[
            if (i > 0) SizedBox(height: gap),
            Container(width: 22, height: 2, color: AppColors.textHint),
          ],
        ],
      ),
    );
  }
}
