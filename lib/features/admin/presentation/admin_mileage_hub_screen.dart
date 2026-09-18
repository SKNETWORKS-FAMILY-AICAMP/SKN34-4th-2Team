import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../mileage/theme/mileage_theme.dart';
import 'widgets/admin_page_layout.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 마일리지 CMS 허브
class AdminMileageHubScreen extends StatelessWidget {
  const AdminMileageHubScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return adminPageWrapper(
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text(
              '마일리지 관리',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            SizedBox(height: AppSpace.s(4)),
            Text(
              '상품 등록, 구매 요청 처리, 마일리지 지급 및 기수 설정을 관리합니다.',
              style: TextStyle(color: AppColors.textSecondary, fontSize: 13),
            ),
            SizedBox(height: AppSpace.s(16)),
            _HubCard(
              icon: Icons.inventory_2_outlined,
              title: '상품 관리',
              subtitle: '교환 상품 등록·수정·삭제',
              onTap: () => context.go(RoutePaths.adminMileageProducts),
            ),
            _HubCard(
              icon: Icons.shopping_cart_checkout_outlined,
              title: '구매 요청 처리',
              subtitle: '학생 구매 요청 승인·반려·수정 요청',
              onTap: () => context.go(RoutePaths.adminMileageRequests),
            ),
            _HubCard(
              icon: Icons.payments_outlined,
              title: '마일리지 지급/차감',
              subtitle: '학생별 수동 마일리지 조정',
              onTap: () => context.go(RoutePaths.adminMileageAdjust),
            ),
            _HubCard(
              icon: Icons.tune,
              title: '기수 설정',
              subtitle: '카테고리 한도 · 미션 적립 안내',
              onTap: () => context.go(RoutePaths.adminMileageSettings),
            ),
          ],
        ),
      ),
    );
  }
}

class _HubCard extends StatelessWidget {
  const _HubCard({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.only(bottom: AppSpace.s(8)),
      child: ListTile(
        dense: true,
        visualDensity: VisualDensity.compact,
        leading: CircleAvatar(
          radius: 16,
          backgroundColor: MileageColors.chipBg,
          child: Icon(icon, color: MileageColors.primary, size: 18),
        ),
        title: Text(
          title,
          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
        ),
        subtitle: Text(subtitle, style: const TextStyle(fontSize: 12)),
        trailing: const Icon(Icons.chevron_right, size: 20),
        onTap: onTap,
      ),
    );
  }
}
