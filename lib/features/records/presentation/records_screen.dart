import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/constants/record_types.dart';
import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/date_utils.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/submission_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../../shared/providers/mission_providers.dart';
import 'widgets/mission_guidance_panel.dart';
import 'widgets/record_page_layout.dart';
import 'widgets/record_status_badge.dart';
import 'widgets/submission_detail_sheet.dart';
import '../../../core/theme/app_space.dart';

/// 기록실 — 제출 목록 + 관리자 승인
class RecordsScreen extends ConsumerStatefulWidget {
  const RecordsScreen({super.key});

  @override
  ConsumerState<RecordsScreen> createState() => _RecordsScreenState();
}

class _RecordsScreenState extends ConsumerState<RecordsScreen> {
  final _searchCtrl = TextEditingController();
  String? _typeFilter;
  String? _statusFilter;

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  List<SubmissionModel> _filter(List<SubmissionModel> list) {
    final q = _searchCtrl.text.trim().toLowerCase();
    return list.where((s) {
      if (_typeFilter != null && s.type != _typeFilter) return false;
      if (_statusFilter != null && s.status != _statusFilter) return false;
      if (q.isEmpty) return true;
      return s.title.toLowerCase().contains(q) ||
          s.userDisplayName.toLowerCase().contains(q) ||
          (s.certType?.toLowerCase().contains(q) ?? false);
    }).toList();
  }

  @override
  Widget build(BuildContext context) {
    final user = ref.watch(currentUserSyncProvider);
    final isAdmin = ref.watch(isAdminProvider);
    final cohortName = ref.watch(effectiveCohortNameProvider);
    final submissionsAsync = isAdmin
        ? ref.watch(allSubmissionsProvider)
        : ref.watch(mySubmissionsProvider);

    if (user == null) {
      return const Center(child: Text('로그인이 필요합니다'));
    }

    return RecordPageScaffold(
      user: user,
      cohortName: cohortName,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          TextField(
            controller: _searchCtrl,
            onChanged: (_) => setState(() {}),
            decoration: InputDecoration(
              hintText: '제목·이름 검색',
              prefixIcon: const Icon(Icons.search, size: 20),
              filled: true,
              fillColor: AppColors.surfaceVariant,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: BorderSide(color: AppColors.border),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: BorderSide(color: AppColors.border),
              ),
              contentPadding: EdgeInsets.symmetric(vertical: AppSpace.s(0)),
            ),
          ),
          SizedBox(height: AppSpace.s(12)),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                _FilterChip(
                  label: '전체',
                  selected: _typeFilter == null,
                  onTap: () => setState(() => _typeFilter = null),
                ),
                ...RecordTypes.all.map(
                  (t) => _FilterChip(
                    label: RecordTypes.labels[t]!,
                    selected: _typeFilter == t,
                    onTap: () => setState(() => _typeFilter = t),
                  ),
                ),
                SizedBox(width: AppSpace.s(8)),
                _FilterChip(
                  label: '대기',
                  selected: _statusFilter == 'pending',
                  onTap: () => setState(
                    () => _statusFilter =
                        _statusFilter == 'pending' ? null : 'pending',
                  ),
                ),
                _FilterChip(
                  label: '승인',
                  selected: _statusFilter == 'approved',
                  onTap: () => setState(
                    () => _statusFilter =
                        _statusFilter == 'approved' ? null : 'approved',
                  ),
                ),
                _FilterChip(
                  label: '반려',
                  selected: _statusFilter == 'rejected',
                  onTap: () => setState(
                    () => _statusFilter =
                        _statusFilter == 'rejected' ? null : 'rejected',
                  ),
                ),
              ],
            ),
          ),
          if (!isAdmin) ...[
            SizedBox(height: AppSpace.s(16)),
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton.icon(
                onPressed: () => context.push(RoutePaths.recordsCreate),
                icon: const Icon(Icons.add, size: 18),
                label: const Text('새로운 기록 추가'),
                style: FilledButton.styleFrom(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpace.s(20),
                    vertical: AppSpace.s(12),
                  ),
                  backgroundColor: AppColors.primary,
                ),
              ),
            ),
          ],
          SizedBox(height: AppSpace.s(12)),
          Expanded(
            child: submissionsAsync.when(
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (e, _) => ErrorView(message: e.toString()),
              data: (list) {
                final filtered = _filter(list);
                return RefreshIndicator(
                  onRefresh: () async {
                    ref.invalidate(mySubmissionsProvider);
                    ref.invalidate(allSubmissionsProvider);
                    ref.invalidate(missionProgressProvider);
                  },
                  child: ListView(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: EdgeInsets.fromLTRB(AppSpace.s(0), AppSpace.s(0), AppSpace.s(14), AppSpace.s(24)),
                    children: [
                      if (!isAdmin) const MissionGuidancePanel(),
                      if (filtered.isEmpty)
                        Padding(
                          padding: EdgeInsets.symmetric(vertical: AppSpace.s(48)),
                          child: Center(
                            child: Text(
                              isAdmin
                                  ? '제출된 기록이 없습니다'
                                  : '아직 제출한 기록이 없습니다',
                              style: TextStyle(
                                color: AppColors.textSecondary,
                              ),
                            ),
                          ),
                        )
                      else
                        ...filtered.map(
                          (s) => _SubmissionCard(
                            submission: s,
                            isAdmin: isAdmin,
                          ),
                        ),
                    ],
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _FilterChip extends StatelessWidget {
  const _FilterChip({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(right: AppSpace.s(8)),
      child: FilterChip(
        label: Text(label, style: const TextStyle(fontSize: 13)),
        selected: selected,
        onSelected: (_) => onTap(),
        selectedColor: AppColors.primaryLight,
        checkmarkColor: AppColors.primary,
        padding: EdgeInsets.symmetric(horizontal: AppSpace.s(4)),
      ),
    );
  }
}

class _SubmissionCard extends ConsumerStatefulWidget {
  const _SubmissionCard({
    required this.submission,
    required this.isAdmin,
  });

  final SubmissionModel submission;
  final bool isAdmin;

  @override
  ConsumerState<_SubmissionCard> createState() => _SubmissionCardState();
}

class _SubmissionCardState extends ConsumerState<_SubmissionCard> {
  bool _busy = false;

  Future<void> _review(String status) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;

    setState(() => _busy = true);
    try {
      await ref.read(lmsRepositoryProvider).reviewSubmission(
            cohortId: cohortId,
            submissionId: widget.submission.id,
            status: status,
          );
      ref.invalidate(allSubmissionsProvider);
      ref.invalidate(mySubmissionsProvider);
      ref.invalidate(missionProgressProvider);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(status == 'approved' ? '승인했습니다' : '반려했습니다'),
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _openDetail() async {
    final action = await showSubmissionDetailSheet(
      context: context,
      submission: widget.submission,
      isAdmin: widget.isAdmin,
    );
    if (!mounted) return;
    if (action == 'approved') {
      await _review('approved');
    } else if (action == 'rejected') {
      await _review('rejected');
    }
  }

  @override
  Widget build(BuildContext context) {
    final s = widget.submission;
    final subtitle = _subtitleOf(s);
    final metaParts = <String>[
      if (widget.isAdmin) s.userDisplayName,
      if (subtitle != null) subtitle,
      if (s.submittedAt != null)
        '제출 ${AppDateUtils.formatDateTime(s.submittedAt!)}',
    ];
    final hasFiles = s.fileUrls.isNotEmpty;
    final hasLink = s.link != null && s.link!.isNotEmpty;

    return Card(
      margin: EdgeInsets.only(bottom: AppSpace.s(8)),
      elevation: 0,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(color: AppColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: _openDetail,
        child: Padding(
          padding: EdgeInsets.fromLTRB(AppSpace.s(12), AppSpace.s(10), AppSpace.s(12), AppSpace.s(10)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    padding:
                        EdgeInsets.symmetric(horizontal: AppSpace.s(7), vertical: AppSpace.s(2)),
                    decoration: BoxDecoration(
                      color: AppColors.surfaceVariant,
                      borderRadius: BorderRadius.circular(5),
                    ),
                    child: Text(
                      s.typeLabel,
                      style: const TextStyle(fontSize: 11, height: 1.2),
                    ),
                  ),
                  if (hasFiles || hasLink) ...[
                    SizedBox(width: AppSpace.s(6)),
                    Icon(
                      hasFiles ? Icons.attach_file : Icons.link,
                      size: 14,
                      color: AppColors.textHint,
                    ),
                    Text(
                      hasFiles ? '${s.fileUrls.length}' : '',
                      style: TextStyle(
                        fontSize: 11,
                        color: AppColors.textHint,
                      ),
                    ),
                  ],
                  const Spacer(),
                  RecordStatusBadge(status: s.status),
                ],
              ),
              SizedBox(height: AppSpace.s(6)),
              Text(
                s.title,
                style: const TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  height: 1.25,
                ),
              ),
              if (metaParts.isNotEmpty) ...[
                SizedBox(height: AppSpace.s(4)),
                Text(
                  metaParts.join(' · '),
                  style: TextStyle(
                    fontSize: 12,
                    color: AppColors.textSecondary,
                    height: 1.3,
                  ),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
              SizedBox(height: AppSpace.s(6)),
              Row(
                children: [
                  TextButton(
                    onPressed: _openDetail,
                    style: TextButton.styleFrom(
                      visualDensity: VisualDensity.compact,
                      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(4)),
                      minimumSize: Size.zero,
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      foregroundColor: AppColors.primary,
                      textStyle: const TextStyle(fontSize: 12),
                    ),
                    child: const Text('상세 보기'),
                  ),
                  const Spacer(),
                  if (widget.isAdmin && s.isPending) ...[
                    OutlinedButton(
                      onPressed: _busy ? null : () => _review('rejected'),
                      style: OutlinedButton.styleFrom(
                        visualDensity: VisualDensity.compact,
                        minimumSize: const Size(0, 32),
                        padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12)),
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        textStyle: const TextStyle(fontSize: 13),
                      ),
                      child: const Text('반려'),
                    ),
                    SizedBox(width: AppSpace.s(6)),
                    FilledButton(
                      onPressed: _busy ? null : () => _review('approved'),
                      style: FilledButton.styleFrom(
                        backgroundColor: AppColors.success,
                        visualDensity: VisualDensity.compact,
                        minimumSize: const Size(0, 32),
                        padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12)),
                        tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                        textStyle: const TextStyle(fontSize: 13),
                      ),
                      child: const Text('승인'),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  String? _subtitleOf(SubmissionModel s) {
    if (s.type == RecordTypes.certification && s.certType != null) {
      return s.certType;
    }
    if (s.type == RecordTypes.study && s.startAt != null && s.endAt != null) {
      final team = s.isTeamStudy == true ? '팀 · ' : '';
      return '$team${AppDateUtils.formatDisplay(s.startAt!)} ~ ${AppDateUtils.formatDisplay(s.endAt!)}';
    }
    if (s.type == RecordTypes.blog) {
      return s.weekLabel ?? s.link;
    }
    if (s.type == RecordTypes.studyCert) {
      final date = s.learningDate != null
          ? AppDateUtils.formatDisplay(s.learningDate!)
          : null;
      return [date, s.learningContent].whereType<String>().join(' · ');
    }
    if (s.type == RecordTypes.precourseQuiz && s.quizScore != null) {
      return '점수 ${s.quizScore}점';
    }
    if (s.isApproved && s.mileageAmount > 0) {
      return '적립 ${s.mileageAmount}M';
    }
    return null;
  }
}
