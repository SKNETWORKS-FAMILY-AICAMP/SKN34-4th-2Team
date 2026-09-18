import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_layout.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/assessment_model.dart';
import '../../../shared/providers/lms_providers.dart';
import 'widgets/assessment_card.dart';
import '../../../core/theme/app_space.dart';

/// 학생 — 성취도평가 목록
class AssessmentsScreen extends ConsumerStatefulWidget {
  const AssessmentsScreen({super.key});

  @override
  ConsumerState<AssessmentsScreen> createState() => _AssessmentsScreenState();
}

class _AssessmentsScreenState extends ConsumerState<AssessmentsScreen> {
  final _search = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final assessments = ref.watch(publishedAssessmentsProvider);
    final submissions = ref.watch(myAssessmentSubmissionsProvider);
    final subMap = {
      for (final s
          in submissions.asData?.value ?? <AssessmentSubmissionModel>[])
        s.assessmentId: s,
    };

    return LayoutBuilder(
      builder: (context, constraints) {
        final width = constraints.maxWidth >= AppLayout.list
            ? AppLayout.list
            : constraints.maxWidth;
        return Align(
          alignment: Alignment.topCenter,
          child: SizedBox(
            width: width,
            height: constraints.maxHeight.isFinite
                ? constraints.maxHeight
                : null,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Padding(
                  padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(12), AppSpace.s(16), AppSpace.s(8)),
                  child: TextField(
                    controller: _search,
                    onChanged: (v) => setState(() => _query = v.trim()),
                    decoration: InputDecoration(
                      hintText: '제목 검색',
                      prefixIcon: const Icon(Icons.search, size: 20),
                      isDense: true,
                      filled: true,
                      fillColor: AppColors.surface,
                      contentPadding: EdgeInsets.symmetric(vertical: AppSpace.s(10)),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                        borderSide: BorderSide(color: AppColors.border),
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(10),
                        borderSide: BorderSide(color: AppColors.border),
                      ),
                    ),
                  ),
                ),
                Expanded(
                  child: assessments.when(
                    loading: () =>
                        const Center(child: CircularProgressIndicator()),
                    error: (e, _) => ErrorView(
                      message: '불러오기 실패: $e',
                      onRetry: () =>
                          ref.invalidate(publishedAssessmentsProvider),
                    ),
                    data: (list) {
                      final filtered = list.where((a) {
                        if (_query.isEmpty) return true;
                        return a.title.toLowerCase().contains(
                          _query.toLowerCase(),
                        );
                      }).toList();
                      if (filtered.isEmpty) {
                        return EmptyView(
                          message: _query.isEmpty
                              ? '등록된 성취도평가가 없습니다.'
                              : '검색 결과가 없습니다.',
                          icon: Icons.quiz_outlined,
                        );
                      }
                      return ListView.separated(
                        padding: EdgeInsets.fromLTRB(AppSpace.s(16), AppSpace.s(4), AppSpace.s(16), AppSpace.s(24)),
                        itemCount: filtered.length,
                        separatorBuilder: (_, __) => SizedBox(height: AppSpace.s(8)),
                        itemBuilder: (context, i) {
                          final a = filtered[i];
                          final sub = subMap[a.id];
                          final completed = sub != null;
                          return AssessmentCard(
                            assessment: a,
                            completed: completed,
                            score: sub?.totalScore,
                            onTap: () {
                              if (completed) {
                                context.push(
                                  RoutePaths.assessmentResultPath(a.id),
                                );
                              } else if (a.isEnded) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text(
                                      '종료된 평가이며 응시 기록이 없습니다.',
                                    ),
                                  ),
                                );
                              } else if (a.isUpcoming) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text('아직 응시 기간이 아닙니다.'),
                                  ),
                                );
                              } else {
                                context.push(
                                  RoutePaths.assessmentTakePath(a.id),
                                );
                              }
                            },
                          );
                        },
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
