import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/mileage_constants.dart';
import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/mileage_models.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../../shared/providers/mileage_providers.dart';
import '../../auth/providers/auth_providers.dart';
import '../theme/mileage_theme.dart';
import 'mileage_cart_actions.dart';
import 'widgets/mileage_product_dialogs.dart';
import 'widgets/mileage_widgets.dart';
import '../../../core/theme/app_space.dart';

/// 마일리지 교환소
class MileageShopScreen extends ConsumerStatefulWidget {
  const MileageShopScreen({super.key});

  @override
  ConsumerState<MileageShopScreen> createState() => _MileageShopScreenState();
}

class _MileageShopScreenState extends ConsumerState<MileageShopScreen> {
  String _categoryFilter = 'all';
  String _sort = 'default';
  final _searchController = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final userAsync = ref.watch(currentUserProvider);
    final cohortName = ref.watch(effectiveCohortNameProvider);
    final cohortEnd = ref.watch(effectiveCohortEndDateProvider);
    final productsAsync = ref.watch(mileageProductsProvider);
    final usageAsync = ref.watch(mileageCategoryUsageProvider);
    final cartAsync = ref.watch(mileageCartProvider);
    final cartCount = cartAsync.value?.items.length ?? 0;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        backgroundColor: AppColors.background,
        elevation: 0,
        scrolledUnderElevation: 0,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          tooltip: '뒤로',
          onPressed: () => context.pop(),
        ),
        title: const Text('마일리지 교환소'),
      ),
      floatingActionButton: cartCount > 0
          ? FloatingActionButton.extended(
              backgroundColor: MileageColors.primary,
              elevation: 2,
              extendedPadding: EdgeInsets.symmetric(horizontal: AppSpace.s(12)),
              onPressed: () => context.push(RoutePaths.mileageCart),
              icon: Badge(
                label: Text('$cartCount', style: const TextStyle(fontSize: 10)),
                child: const Icon(Icons.shopping_cart_outlined, size: 18),
              ),
              label: const Text('장바구니', style: TextStyle(fontSize: 13)),
            )
          : null,
      body: userAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(message: e.toString()),
        data: (user) {
          if (user == null) return const SizedBox.shrink();

          return RefreshIndicator(
            onRefresh: () async {
              ref.invalidate(mileageProductsProvider);
              ref.invalidate(mileageCategoryUsageProvider);
            },
            child: MileagePageScroll(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  MileagePageHeader(
                    user: user,
                    cohortName: cohortName,
                    subtitle: '상품을 선택해 장바구니에 담으세요.',
                  ),
                  const SizedBox(height: MileageLayout.sectionGap),
                  MileageCreditCard(
                    balance: user.mileageBalance,
                    holderName: user.displayName,
                    validThru: cohortEnd?.add(const Duration(days: 14)),
                  ),
                  const SizedBox(height: MileageLayout.sectionGap),
                  usageAsync.when(
                    loading: () => Padding(
                      padding: EdgeInsets.all(AppSpace.s(24)),
                      child: Center(child: CircularProgressIndicator()),
                    ),
                    error: (e, _) => ErrorView(message: e.toString()),
                    data: (usages) => Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: MileageLayout.pagePaddingH,
                      ),
                      child: LayoutBuilder(
                        builder: (context, constraints) {
                          final isWide = constraints.maxWidth > 700;
                          if (isWide) {
                            return Row(
                              children: usages
                                  .map(
                                    (u) => Expanded(
                                      child: Padding(
                                        padding: EdgeInsets.only(
                                          right: AppSpace.s(8),
                                        ),
                                        child: _CategoryLimitCard(usage: u),
                                      ),
                                    ),
                                  )
                                  .toList(),
                            );
                          }
                          return Column(
                            children: usages
                                .map(
                                  (u) => Padding(
                                    padding: EdgeInsets.only(bottom: AppSpace.s(8)),
                                    child: _CategoryLimitCard(usage: u),
                                  ),
                                )
                                .toList(),
                          );
                        },
                      ),
                    ),
                  ),
                  const SizedBox(height: MileageLayout.sectionGap),
                  Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: MileageLayout.pagePaddingH,
                    ),
                    child: MileageFilterChipRow(
                      selected: _categoryFilter,
                      onSelected: (v) => setState(() => _categoryFilter = v),
                      options: const [
                        ('all', '전체'),
                        ('gifticon', '기프티콘'),
                        ('book', '도서'),
                        ('onlineCourse', '인터넷 강의'),
                      ],
                    ),
                  ),
                  SizedBox(height: AppSpace.s(8)),
                  Padding(
                    padding: const EdgeInsets.symmetric(
                      horizontal: MileageLayout.pagePaddingH,
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        MileageFilterChipRow(
                          label: '정렬',
                          selected: _sort,
                          onSelected: (v) => setState(() => _sort = v),
                          options: const [
                            ('default', '기본'),
                            ('high', '높은 순'),
                            ('low', '낮은 순'),
                          ],
                        ),
                        SizedBox(height: AppSpace.s(8)),
                        TextField(
                          controller: _searchController,
                          decoration: InputDecoration(
                            hintText: '상품 검색',
                            isDense: true,
                            border: OutlineInputBorder(),
                            prefixIcon: Icon(Icons.search, size: 18),
                            contentPadding: EdgeInsets.symmetric(
                              horizontal: AppSpace.s(12),
                              vertical: AppSpace.s(10),
                            ),
                          ),
                          style: const TextStyle(fontSize: 13),
                          onChanged: (v) => setState(() => _query = v.trim()),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: MileageLayout.sectionGap),
                  productsAsync.when(
                    loading: () => Padding(
                      padding: EdgeInsets.all(AppSpace.s(40)),
                      child: Center(child: CircularProgressIndicator()),
                    ),
                    error: (e, _) => ErrorView(message: e.toString()),
                    data: (products) {
                      var list = _filterProducts(products);
                      list = _sortProducts(list);

                      if (list.isEmpty) {
                        return Padding(
                          padding: EdgeInsets.all(AppSpace.s(40)),
                          child: Center(
                            child: Text('등록된 상품이 없습니다.\n관리자에게 문의해 주세요.'),
                          ),
                        );
                      }

                      return Padding(
                        padding: const EdgeInsets.symmetric(
                          horizontal: MileageLayout.pagePaddingH,
                        ),
                        child: LayoutBuilder(
                          builder: (context, constraints) {
                            final crossCount = constraints.maxWidth > 900
                                ? 4
                                : constraints.maxWidth > 600
                                ? 3
                                : 2;
                            return GridView.builder(
                              shrinkWrap: true,
                              physics: const NeverScrollableScrollPhysics(),
                              gridDelegate:
                                  SliverGridDelegateWithFixedCrossAxisCount(
                                    crossAxisCount: crossCount,
                                    mainAxisSpacing: 10,
                                    crossAxisSpacing: 10,
                                    childAspectRatio: 0.78,
                                  ),
                              itemCount: list.length,
                              itemBuilder: (_, i) => _ProductCard(
                                product: list[i],
                                usage: usageForCategory(
                                  usageAsync.value,
                                  list[i].category,
                                ),
                                mileageBalance: user.mileageBalance,
                                onTap: () => _onProductTap(
                                  context,
                                  list[i],
                                  user.mileageBalance,
                                  usageAsync.value,
                                ),
                              ),
                            );
                          },
                        ),
                      );
                    },
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  List<MileageProductModel> _filterProducts(
    List<MileageProductModel> products,
  ) {
    return products.where((p) {
      if (_categoryFilter != 'all' && p.category != _categoryFilter) {
        return false;
      }
      if (_query.isNotEmpty &&
          !p.name.toLowerCase().contains(_query.toLowerCase())) {
        return false;
      }
      return true;
    }).toList();
  }

  List<MileageProductModel> _sortProducts(List<MileageProductModel> products) {
    final list = [...products];
    switch (_sort) {
      case 'high':
        list.sort((a, b) => _priceOf(b).compareTo(_priceOf(a)));
      case 'low':
        list.sort((a, b) => _priceOf(a).compareTo(_priceOf(b)));
      default:
        break;
    }
    return list;
  }

  int _priceOf(MileageProductModel p) =>
      p.isCustomPrice ? 0 : (p.fixedPrice ?? 0);

  Future<void> _onProductTap(
    BuildContext context,
    MileageProductModel product,
    int balance,
    List<MileageCategoryUsageModel>? usages,
  ) async {
    final usage = usageForCategory(usages, product.category);
    if (usage == null) return;

    if (product.isCustomPrice) {
      await showCustomProductDialog(
        context,
        product: product,
        usage: usage,
        mileageBalance: balance,
        onAdd: (link, price) async {
          await addItemToMileageCart(
            ref,
            item: MileageCartItemModel(
              productId: product.id,
              productName: product.name,
              category: product.category,
              pricingType: product.pricingType,
              unitPrice: price,
              purchaseLink: link,
            ),
          );
          if (context.mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('장바구니에 담았습니다.')),
            );
          }
        },
      );
    } else {
      await showFixedProductDialog(
        context,
        product: product,
        onAdd: (quantity) async {
          await addItemToMileageCart(
            ref,
            item: MileageCartItemModel(
              productId: product.id,
              productName: product.name,
              category: product.category,
              pricingType: product.pricingType,
              unitPrice: product.fixedPrice ?? 0,
              quantity: quantity,
            ),
          );
          if (context.mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(content: Text('장바구니에 담았습니다.')),
            );
          }
        },
      );
    }
  }
}

class _CategoryLimitCard extends StatelessWidget {
  const _CategoryLimitCard({required this.usage});

  final MileageCategoryUsageModel usage;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(AppSpace.s(12)),
      decoration: BoxDecoration(
        border: Border.all(color: AppColors.border),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                _iconFor(usage.category),
                size: 16,
                color: MileageColors.categoryTagColor(usage.category),
              ),
              SizedBox(width: AppSpace.s(4)),
              Text(
                usage.categoryLabel,
                style: const TextStyle(
                  fontWeight: FontWeight.w600,
                  fontSize: 13,
                ),
              ),
              const Spacer(),
              Text(
                '한도 ${formatMileageM(usage.limit)}',
                style: TextStyle(
                  fontSize: 10,
                  color: AppColors.textSecondary,
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpace.s(8)),
          Text(
            formatMileageM(usage.remaining),
            style: const TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
          Text(
            '추가 신청 가능',
            style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
          ),
          SizedBox(height: AppSpace.s(4)),
          Text(
            '승인 ${formatMileageM(usage.approved)} · '
            '대기 ${formatMileageM(usage.pending)} · '
            '수정요청 ${formatMileageM(usage.modifyRequested)}',
            style: TextStyle(fontSize: 10, color: AppColors.textSecondary),
          ),
        ],
      ),
    );
  }

  IconData _iconFor(String category) => switch (category) {
    MileageCategories.gifticon => Icons.card_giftcard,
    MileageCategories.book => Icons.menu_book_outlined,
    MileageCategories.onlineCourse => Icons.play_circle_outline,
    _ => Icons.shopping_bag_outlined,
  };
}

class _ProductCard extends StatelessWidget {
  const _ProductCard({
    required this.product,
    required this.usage,
    required this.mileageBalance,
    required this.onTap,
  });

  final MileageProductModel product;
  final MileageCategoryUsageModel? usage;
  final int mileageBalance;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final tagColor = MileageColors.categoryTagColor(product.category);

    return Material(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(12),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          decoration: BoxDecoration(
            border: Border.all(color: AppColors.border),
            borderRadius: BorderRadius.circular(12),
          ),
          padding: EdgeInsets.all(AppSpace.s(10)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              MileageTagChip(
                label: product.categoryLabel,
                color: tagColor,
              ),
              SizedBox(height: AppSpace.s(6)),
              Expanded(
                child: Center(
                  child:
                      product.imageUrl != null && product.imageUrl!.isNotEmpty
                      ? Image.network(
                          product.imageUrl!,
                          height: AppSpace.row(44),
                          errorBuilder: (_, _, _) => _placeholderIcon(),
                        )
                      : _placeholderIcon(),
                ),
              ),
              Text(
                product.name,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  fontWeight: FontWeight.w600,
                  fontSize: 12,
                ),
              ),
              SizedBox(height: AppSpace.s(6)),
              if (product.isCustomPrice)
                Text(
                  '가격 직접 입력',
                  style: TextStyle(
                    color: MileageColors.primary,
                    fontWeight: FontWeight.w600,
                    fontSize: 13,
                  ),
                )
              else
                Row(
                  children: [
                    Icon(
                      Icons.monetization_on_outlined,
                      size: 16,
                      color: MileageColors.primary,
                    ),
                    SizedBox(width: AppSpace.s(4)),
                    Text(
                      formatMileageM(product.fixedPrice ?? 0),
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        color: MileageColors.primary,
                      ),
                    ),
                  ],
                ),
              if (usage != null) ...[
                SizedBox(height: AppSpace.s(6)),
                Text(
                  '잔여 ${formatMileageM(usage!.remaining)}',
                  style: TextStyle(
                    fontSize: 10,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _placeholderIcon() {
    return Icon(
      product.category == MileageCategories.onlineCourse
          ? Icons.play_circle_outline
          : product.category == MileageCategories.book
          ? Icons.menu_book_outlined
          : Icons.card_giftcard,
      size: 36,
      color: AppColors.textHint,
    );
  }
}
