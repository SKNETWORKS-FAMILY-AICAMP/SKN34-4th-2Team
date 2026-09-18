import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'app_appearance_provider.dart';

const _kSidebarDarkPaletteKey = 'sidebar_dark_palette_v1';

/// 어두운 사이드바 색 후보. 설정 탭에서 고른다.
class SideRailDarkPalette {
  const SideRailDarkPalette({
    required this.id,
    required this.label,
    required this.background,
    required this.border,
    required this.accent,
    required this.muted,
    required this.action,
    required this.actionDark,
    required this.actionLight,
  });

  final String id;
  final String label;
  final Color background;
  final Color border;
  final Color accent;
  final Color muted;

  /// 밝은 본문에서 버튼·링크에 쓰는 접근성 대비가 확보된 대표색.
  final Color action;
  final Color actionDark;
  final Color actionLight;
}

const kSideRailDarkPalettes = <SideRailDarkPalette>[
  SideRailDarkPalette(
    id: 'soft_slate',
    label: '1 Soft Slate',
    background: Color(0xFF0F172A),
    border: Color(0xFF1E293B),
    accent: Color(0xFF38BDF8),
    muted: Color(0xFF94A3B8),
    action: Color(0xFF0284C7),
    actionDark: Color(0xFF0369A1),
    actionLight: Color(0xFFE0F2FE),
  ),
  SideRailDarkPalette(
    id: 'charcoal',
    label: '2 Charcoal',
    background: Color(0xFF111827),
    border: Color(0xFF1F2937),
    accent: Color(0xFF00C2D4),
    muted: Color(0xFF94A3B8),
    action: Color(0xFF0891B2),
    actionDark: Color(0xFF0E7490),
    actionLight: Color(0xFFCFFAFE),
  ),
  SideRailDarkPalette(
    id: 'brand_navy',
    label: '3 Brand Navy',
    background: Color(0xFF0B2A6F),
    border: Color(0xFF1E3A8A),
    accent: Color(0xFF60A5FA),
    muted: Color(0xFF94A3B8),
    action: Color(0xFF2563EB),
    actionDark: Color(0xFF1D4ED8),
    actionLight: Color(0xFFDBEAFE),
  ),
  SideRailDarkPalette(
    id: 'soft_cinematic',
    label: '4 Soft Cinematic',
    background: Color(0xFF0B1224),
    border: Color(0xFF1E2538),
    accent: Color(0xFF00C2D4),
    muted: Color(0xFF94A3B8),
    action: Color(0xFF7C3AED),
    actionDark: Color(0xFF6D28D9),
    actionLight: Color(0xFFEDE9FE),
  ),
  SideRailDarkPalette(
    id: 'mid_slate',
    label: '5 Mid Slate',
    background: Color(0xFF1E293B),
    border: Color(0xFF334155),
    accent: Color(0xFF00C2D4),
    muted: Color(0xFFCBD5E1),
    action: Color(0xFF0F766E),
    actionDark: Color(0xFF115E59),
    actionLight: Color(0xFFCCFBF1),
  ),
  // 푸른 기가 없는 무채색 회색. 2 Charcoal은 이름과 달리 남색에 가깝다.
  SideRailDarkPalette(
    id: 'graphite',
    label: '6 Graphite',
    background: Color(0xFF2B2B2B),
    border: Color(0xFF3A3A3A),
    accent: Color(0xFFD4D4D4),
    muted: Color(0xFFA3A3A3),
    action: Color(0xFF404040),
    actionDark: Color(0xFF262626),
    actionLight: Color(0xFFEDEDED),
  ),
];

/// 사이드바가 어두운가. 화면 테마 설정에서 끌어온다.
///
/// 예전에는 여기에 스위치가 따로 있었다. 이제 설정 탭 한 곳에서 정하고,
/// 사이드바만 어둡게도 전체를 어둡게도 그 한 곳에서 고른다.
final sideRailDarkModeProvider = Provider<bool>(
  (ref) => ref.watch(appThemeModeProvider).isRailDark,
);

/// 사이드바 색 팔레트. 설정 탭에서 고른다.
class SideRailDarkPaletteIndex extends Notifier<int> {
  @override
  int build() {
    Future<void>(() async {
      final prefs = await SharedPreferences.getInstance();
      if (!ref.mounted) return;
      final saved = prefs.getInt(_kSidebarDarkPaletteKey) ?? 0;
      state = saved.clamp(0, kSideRailDarkPalettes.length - 1);
    });
    return 0;
  }

  Future<void> cycle() async {
    state = (state + 1) % kSideRailDarkPalettes.length;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_kSidebarDarkPaletteKey, state);
  }

  Future<void> setIndex(int index) async {
    final next = index.clamp(0, kSideRailDarkPalettes.length - 1);
    if (state == next) return;
    state = next;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setInt(_kSidebarDarkPaletteKey, state);
  }
}

final sideRailDarkPaletteIndexProvider =
    NotifierProvider<SideRailDarkPaletteIndex, int>(
      SideRailDarkPaletteIndex.new,
    );

final sideRailDarkPaletteProvider = Provider<SideRailDarkPalette>((ref) {
  final index = ref.watch(sideRailDarkPaletteIndexProvider);
  return kSideRailDarkPalettes[index];
});
