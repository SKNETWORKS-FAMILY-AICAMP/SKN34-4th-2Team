import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/mileage_constants.dart';
import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/mileage_models.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/mileage_providers.dart';
import '../../mileage/theme/mileage_theme.dart';
import '../data/mileage_seed_data.dart';
import 'widgets/admin_page_layout.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 마일리지 상품 CRUD
class AdminMileageProductsScreen extends ConsumerWidget {
  const AdminMileageProductsScreen({super.key});

  Future<void> _seedProducts(WidgetRef ref, BuildContext context) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;

    final existing = ref.read(allMileageProductsProvider).value ?? [];
    final existingNames = existing.map((p) => p.name).toSet();

    var created = 0;
    for (final product in MileageSeedProducts.defaults()) {
      if (existingNames.contains(product.name)) continue;
      await ref
          .read(mileageRepositoryProvider)
          .saveMileageProduct(
            cohortId: cohortId,
            product: product,
          );
      created++;
    }

    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            created > 0
                ? '시드 상품 $created개를 등록했습니다.'
                : '이미 모든 시드 상품이 등록되어 있습니다.',
          ),
        ),
      );
    }
  }

  Future<void> _delete(
    WidgetRef ref,
    BuildContext context,
    MileageProductModel product,
  ) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('상품 삭제'),
        content: Text('「${product.name}」 상품을 삭제할까요?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(backgroundColor: AppColors.error),
            child: const Text('삭제'),
          ),
        ],
      ),
    );
    if (ok != true) return;

    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;

    await ref
        .read(mileageRepositoryProvider)
        .deleteMileageProduct(
          cohortId,
          product.id,
        );
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final productsAsync = ref.watch(allMileageProductsProvider);

    return adminPageWrapper(
      child: productsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(message: e.toString()),
        data: (list) {
          return SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                LayoutBuilder(
                  builder: (context, constraints) {
                    final isWide = constraints.maxWidth > 520;
                    if (isWide) {
                      return Row(
                        children: [
                          IconButton(
                            visualDensity: VisualDensity.compact,
                            onPressed: () =>
                                context.go(RoutePaths.adminMileage),
                            icon: const Icon(Icons.arrow_back, size: 20),
                          ),
                          const Text(
                            '상품 관리',
                            style: TextStyle(
                              fontSize: 20,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          const Spacer(),
                          OutlinedButton(
                            style: mileageOutlinedButtonStyle(),
                            onPressed: () => _seedProducts(ref, context),
                            child: const Text('시드 상품'),
                          ),
                          SizedBox(width: AppSpace.s(8)),
                          FilledButton.icon(
                            style: mileagePrimaryButtonStyle(),
                            onPressed: () => context.push(
                              RoutePaths.adminMileageProductsCreate,
                            ),
                            icon: const Icon(Icons.add, size: 16),
                            label: const Text('등록'),
                          ),
                        ],
                      );
                    }
                    return Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          children: [
                            IconButton(
                              visualDensity: VisualDensity.compact,
                              onPressed: () =>
                                  context.go(RoutePaths.adminMileage),
                              icon: const Icon(Icons.arrow_back, size: 20),
                            ),
                            const Text(
                              '상품 관리',
                              style: TextStyle(
                                fontSize: 20,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                        Wrap(
                          spacing: 8,
                          runSpacing: 8,
                          children: [
                            OutlinedButton(
                              style: mileageOutlinedButtonStyle(),
                              onPressed: () => _seedProducts(ref, context),
                              child: const Text('시드 상품'),
                            ),
                            FilledButton.icon(
                              style: mileagePrimaryButtonStyle(),
                              onPressed: () => context.push(
                                RoutePaths.adminMileageProductsCreate,
                              ),
                              icon: const Icon(Icons.add, size: 16),
                              label: const Text('등록'),
                            ),
                          ],
                        ),
                      ],
                    );
                  },
                ),
                SizedBox(height: AppSpace.s(12)),
                if (list.isEmpty)
                  Padding(
                    padding: EdgeInsets.all(AppSpace.s(32)),
                    child: Center(
                      child: Text('등록된 상품이 없습니다.\n「시드 상품 등록」으로 기본 상품을 추가하세요.'),
                    ),
                  )
                else
                  ...list.map((p) {
                    return Padding(
                      padding: EdgeInsets.only(bottom: AppSpace.s(6)),
                      child: Card(
                        margin: EdgeInsets.zero,
                        child: ListTile(
                          dense: true,
                          visualDensity: VisualDensity.compact,
                          title: Text(
                            p.name,
                            style: const TextStyle(
                              fontWeight: FontWeight.w600,
                              fontSize: 14,
                            ),
                          ),
                          subtitle: Text(
                            '${MileageCategories.labelOf(p.category)} · '
                            '${p.isCustomPrice ? "가격 직접 입력" : formatMileageM(p.fixedPrice ?? 0)} · '
                            '정렬 ${p.sortOrder}',
                            style: const TextStyle(fontSize: 12),
                          ),
                          trailing: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Transform.scale(
                                scale: 0.85,
                                child: Switch(
                                  value: p.isActive,
                                  onChanged: (v) async {
                                    final cohortId = ref.read(
                                      effectiveCohortIdProvider,
                                    );
                                    if (cohortId == null) return;
                                    await ref
                                        .read(mileageRepositoryProvider)
                                        .saveMileageProduct(
                                          cohortId: cohortId,
                                          product: MileageProductModel(
                                            id: p.id,
                                            name: p.name,
                                            description: p.description,
                                            imageUrl: p.imageUrl,
                                            category: p.category,
                                            pricingType: p.pricingType,
                                            fixedPrice: p.fixedPrice,
                                            isActive: v,
                                            sortOrder: p.sortOrder,
                                          ),
                                        );
                                  },
                                ),
                              ),
                              IconButton(
                                visualDensity: VisualDensity.compact,
                                icon: const Icon(Icons.edit_outlined, size: 20),
                                onPressed: () => context.push(
                                  RoutePaths.adminMileageProductEditPath(p.id),
                                ),
                              ),
                              IconButton(
                                visualDensity: VisualDensity.compact,
                                icon: Icon(
                                  Icons.delete_outline,
                                  color: AppColors.error,
                                  size: 20,
                                ),
                                onPressed: () => _delete(ref, context, p),
                              ),
                            ],
                          ),
                        ),
                      ),
                    );
                  }),
              ],
            ),
          );
        },
      ),
    );
  }
}
