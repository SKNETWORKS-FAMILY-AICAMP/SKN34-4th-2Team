import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/theme/app_colors.dart';
import '../../../core/utils/date_utils.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/providers/qual_exam_providers.dart';
import '../utils/qual_exam_utils.dart';
import 'widgets/qual_exam_timeline.dart';
import '../../../core/theme/app_space.dart';

/// 자격 시험 일정 전체 — 타임라인 + 검색
class QualExamSchedulesScreen extends ConsumerStatefulWidget {
  const QualExamSchedulesScreen({super.key});

  @override
  ConsumerState<QualExamSchedulesScreen> createState() =>
      _QualExamSchedulesScreenState();
}

class _QualExamSchedulesScreenState
    extends ConsumerState<QualExamSchedulesScreen> {
  final _searchController = TextEditingController();

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final schedules = ref.watch(qualExamSchedulesProvider);

    return RefreshIndicator(
      onRefresh: () async => ref.invalidate(qualExamSchedulesProvider),
      child: schedules.when(
        loading: () => ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: [
            SizedBox(height: AppSpace.s(120)),
            Center(child: CircularProgressIndicator(strokeWidth: 2)),
          ],
        ),
        error: (e, _) => ListView(
          physics: const AlwaysScrollableScrollPhysics(),
          children: [ErrorView(message: e.toString())],
        ),
        data: (result) {
          final filtered = QualExamUtils.prepareUpcoming(
            result.items,
            keyword: _searchController.text,
          );
          final grouped = QualExamUtils.groupByMonth(filtered);
          final monthKeys = grouped.keys.toList();

          return ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: EdgeInsets.all(AppSpace.s(16)),
            children: [
              Center(
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 560),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      TextField(
                        controller: _searchController,
                        decoration: const InputDecoration(
                          isDense: true,
                          hintText: '자격명·회차 검색 (예: 정보처리, 기능사, 107)',
                          prefixIcon: Icon(Icons.search, size: 20),
                        ),
                        onChanged: (_) => setState(() {}),
                      ),
                      SizedBox(height: AppSpace.s(10)),
                      Text(
                        '${result.year}년 · 다가오는 ${filtered.length}건',
                        style: TextStyle(
                          fontSize: 12,
                          color: AppColors.textSecondary,
                        ),
                      ),
                      SizedBox(height: AppSpace.s(16)),
                      if (filtered.isEmpty)
                        Padding(
                          padding: EdgeInsets.symmetric(vertical: AppSpace.s(48)),
                          child: Center(
                            child: Text(
                              '조건에 맞는 시험 일정이 없습니다',
                              style: TextStyle(color: AppColors.textSecondary),
                            ),
                          ),
                        )
                      else
                        ...monthKeys.map((month) {
                          final items = grouped[month]!;
                          return Padding(
                            padding: EdgeInsets.only(bottom: AppSpace.s(20)),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Padding(
                                  padding: EdgeInsets.only(bottom: AppSpace.s(10)),
                                  child: Text(
                                    month,
                                    style: TextStyle(
                                      fontWeight: FontWeight.w600,
                                      fontSize: 13,
                                      color: AppColors.textSecondary,
                                    ),
                                  ),
                                ),
                                Card(
                                  child: Padding(
                                    padding: EdgeInsets.fromLTRB(
                                      AppSpace.s(12),
                                      AppSpace.s(16),
                                      AppSpace.s(16),
                                      AppSpace.s(12),
                                    ),
                                    child: QualExamTimeline(items: items),
                                  ),
                                ),
                              ],
                            ),
                          );
                        }),
                      if (result.syncedAt != null) ...[
                        SizedBox(height: AppSpace.s(8)),
                        Text(
                          '출처: 한국산업인력공단 공공데이터 · '
                          '갱신 ${AppDateUtils.formatDateTime(result.syncedAt!)}',
                          style: TextStyle(
                            fontSize: 10,
                            color: AppColors.textHint,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}
