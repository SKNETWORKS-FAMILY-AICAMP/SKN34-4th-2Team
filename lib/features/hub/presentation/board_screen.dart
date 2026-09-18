import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/post_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../onboarding/domain/onboarding_target_registry.dart';
import '../../onboarding/student/student_onboarding_keys.dart';
import 'widgets/board_ui.dart';
import 'widgets/notice_list_widgets.dart';
import '../../../core/theme/app_space.dart';

/// 게시판 — 공지 + 소통 피드 탭 (학생용)
class BoardScreen extends ConsumerStatefulWidget {
  const BoardScreen({super.key});

  @override
  ConsumerState<BoardScreen> createState() => _BoardScreenState();
}

class _BoardScreenState extends ConsumerState<BoardScreen>
    with SingleTickerProviderStateMixin {
  late TabController _tabController;
  final _postController = TextEditingController();
  final _searchController = TextEditingController();
  String _query = '';

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    _postController.dispose();
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: BoardUi.listBackground,
      child: Column(
        children: [
          BoardTabBar(
            controller: _tabController,
            tabs: const ['공지사항', '소통 피드'],
          ),
          AnimatedBuilder(
            animation: _tabController,
            builder: (context, _) {
              if (_tabController.index != 0) {
                return const SizedBox.shrink();
              }
              return _BoardSearchBar(
                controller: _searchController,
                query: _query,
                onChanged: (value) => setState(() => _query = value.trim()),
                onClear: () {
                  _searchController.clear();
                  setState(() => _query = '');
                },
              );
            },
          ),
          Expanded(
            child: TabBarView(
              controller: _tabController,
              children: [
                _NoticesTab(query: _query),
                _FeedTab(controller: _postController),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _BoardSearchBar extends StatelessWidget {
  const _BoardSearchBar({
    required this.controller,
    required this.query,
    required this.onChanged,
    required this.onClear,
  });

  final TextEditingController controller;
  final String query;
  final ValueChanged<String> onChanged;
  final VoidCallback onClear;

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.surface,
      padding: EdgeInsets.fromLTRB(AppSpace.s(20), AppSpace.s(12), AppSpace.s(20), AppSpace.s(12)),
      child: TextField(
        controller: controller,
        onChanged: onChanged,
        style: const TextStyle(fontSize: 13),
        decoration: InputDecoration(
          hintText: '공지 제목·내용·작성자 검색',
          hintStyle: TextStyle(fontSize: 13, color: AppColors.textHint),
          prefixIcon: const Icon(Icons.search, size: 20),
          suffixIcon: query.isEmpty
              ? null
              : IconButton(
                  icon: const Icon(Icons.clear, size: 18),
                  onPressed: onClear,
                ),
          filled: true,
          fillColor: BoardUi.listBackground,
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: BorderSide.none,
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: BorderSide.none,
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(10),
            borderSide: BorderSide(color: AppColors.primary),
          ),
          contentPadding: EdgeInsets.symmetric(vertical: AppSpace.s(0)),
        ),
      ),
    );
  }
}

class _NoticesTab extends ConsumerWidget {
  const _NoticesTab({required this.query});

  final String query;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notices = ref.watch(noticesStreamProvider);

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(noticesStreamProvider),
      child: notices.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(message: e.toString()),
        data: (list) {
          final q = query.toLowerCase();
          final filtered = q.isEmpty
              ? list
              : list
                    .where(
                      (n) =>
                          n.title.toLowerCase().contains(q) ||
                          n.content.toLowerCase().contains(q) ||
                          n.authorName.toLowerCase().contains(q),
                    )
                    .toList();

          if (filtered.isEmpty) {
            return ListView(
              physics: const AlwaysScrollableScrollPhysics(),
              children: [
                SizedBox(height: AppSpace.s(48)),
                EmptyView(
                  message: q.isEmpty ? '등록된 공지가 없습니다.' : '검색 결과가 없습니다.',
                  icon: q.isEmpty
                      ? Icons.campaign_outlined
                      : Icons.search_off_rounded,
                ),
              ],
            );
          }

          final favorites = filtered.where((n) => n.isFavorite).toList();
          final regular = filtered.where((n) => !n.isFavorite).toList();

          return Align(
            alignment: Alignment.topCenter,
            child: ConstrainedBox(
              constraints: const BoxConstraints(
                maxWidth: BoardUi.contentMaxWidth,
              ),
              child: KeyedSubtree(
                key: OnboardingTargetRegistry.keyOf(
                  StudentOnboardingTargets.boardNotices,
                ),
                child: ListView(
                  physics: const AlwaysScrollableScrollPhysics(),
                  padding: EdgeInsets.fromLTRB(AppSpace.s(20), AppSpace.s(16), AppSpace.s(20), AppSpace.s(28)),
                  children: [
                    if (favorites.isNotEmpty) ...[
                      const _SectionHeader(
                        icon: Icons.star_rounded,
                        iconColor: BoardUi.favorite,
                        title: '중요 공지',
                      ),
                      SizedBox(height: AppSpace.s(8)),
                      StudentNoticeRowList(
                        notices: favorites,
                        onTap: (notice) =>
                            NoticeDetailSheet.show(context, notice),
                      ),
                      SizedBox(height: AppSpace.s(20)),
                    ],
                    if (regular.isNotEmpty) ...[
                      const _SectionHeader(
                        icon: Icons.campaign_outlined,
                        title: '전체 공지',
                      ),
                      SizedBox(height: AppSpace.s(8)),
                      StudentNoticeRowList(
                        notices: regular,
                        onTap: (notice) =>
                            NoticeDetailSheet.show(context, notice),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({
    required this.icon,
    required this.title,
    this.iconColor,
  });

  final IconData icon;
  final String title;
  final Color? iconColor;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 16, color: iconColor ?? AppColors.textSecondary),
        SizedBox(width: AppSpace.s(6)),
        Text(
          title,
          style: TextStyle(
            fontWeight: FontWeight.w600,
            fontSize: 14,
            color: AppColors.textPrimary,
          ),
        ),
      ],
    );
  }
}

class _FeedTab extends ConsumerWidget {
  const _FeedTab({required this.controller});
  final TextEditingController controller;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final posts = ref.watch(postsStreamProvider);
    final user = ref.watch(currentUserSyncProvider);

    return Column(
      children: [
        Container(
          color: AppColors.surface,
          padding: EdgeInsets.fromLTRB(AppSpace.s(20), AppSpace.s(12), AppSpace.s(12), AppSpace.s(12)),
          child: Row(
            children: [
              Expanded(
                child: TextField(
                  controller: controller,
                  decoration: InputDecoration(
                    hintText: '무엇이든 물어보세요...',
                    hintStyle: TextStyle(color: AppColors.textHint),
                    filled: true,
                    fillColor: BoardUi.listBackground,
                    isDense: true,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: BorderSide.none,
                    ),
                    contentPadding: EdgeInsets.symmetric(
                      horizontal: AppSpace.s(14),
                      vertical: AppSpace.s(12),
                    ),
                  ),
                ),
              ),
              SizedBox(width: AppSpace.s(8)),
              IconButton(
                icon: Icon(Icons.send_rounded, color: AppColors.primary),
                onPressed: user == null
                    ? null
                    : () async {
                        final content = controller.text.trim();
                        if (content.isEmpty) return;
                        await ref
                            .read(lmsRepositoryProvider)
                            .createPost(
                              cohortId: ref.read(effectiveCohortIdProvider)!,
                              authorId: user.uid,
                              authorName: user.displayName,
                              content: content,
                            );
                        controller.clear();
                      },
              ),
            ],
          ),
        ),
        Expanded(
          child: posts.when(
            loading: () => const Center(child: CircularProgressIndicator()),
            error: (e, _) => ErrorView(message: e.toString()),
            data: (list) {
              if (list.isEmpty) {
                return const EmptyView(
                  message: '게시글이 없습니다.',
                  icon: Icons.forum_outlined,
                );
              }
              return ListView.builder(
                padding: EdgeInsets.fromLTRB(AppSpace.s(20), AppSpace.s(12), AppSpace.s(20), AppSpace.s(20)),
                itemCount: list.length,
                itemBuilder: (_, i) => _PostTile(post: list[i], ref: ref),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _PostTile extends StatelessWidget {
  const _PostTile({required this.post, required this.ref});
  final PostModel post;
  final WidgetRef ref;

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(currentUserSyncProvider);
    final canDelete =
        user != null && (user.uid == post.authorId || user.isAdmin);

    return Container(
      margin: EdgeInsets.only(bottom: AppSpace.s(10)),
      decoration: BoardUi.cardDecoration(),
      child: Padding(
        padding: EdgeInsets.all(AppSpace.s(14)),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 16,
                  backgroundColor: AppColors.primaryLight,
                  child: Text(
                    post.authorName.isNotEmpty ? post.authorName[0] : '?',
                    style: TextStyle(
                      color: AppColors.primary,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
                SizedBox(width: AppSpace.s(10)),
                Text(
                  post.authorName,
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                const Spacer(),
                if (canDelete)
                  IconButton(
                    visualDensity: VisualDensity.compact,
                    icon: const Icon(Icons.delete_outline, size: 18),
                    color: AppColors.textHint,
                    onPressed: () => ref
                        .read(lmsRepositoryProvider)
                        .deletePost(
                          ref.read(effectiveCohortIdProvider)!,
                          post.id,
                        ),
                  ),
              ],
            ),
            SizedBox(height: AppSpace.s(10)),
            Text(
              post.content,
              style: const TextStyle(fontSize: 14, height: 1.5),
            ),
          ],
        ),
      ),
    );
  }
}
