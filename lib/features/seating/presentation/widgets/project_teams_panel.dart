import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/widgets/loading_widgets.dart';
import '../../../../shared/models/user_model.dart';
import '../../../../shared/providers/cohort_providers.dart';
import '../../data/seating_repository.dart';
import '../../models/project_team_model.dart';
import '../../providers/seating_providers.dart';
import '../../utils/project_team_randomizer.dart';
import '../../../../core/theme/app_space.dart';

/// 좌석 배치 — 프로젝트 팀 구성 탭
class ProjectTeamsPanel extends ConsumerStatefulWidget {
  const ProjectTeamsPanel({super.key, required this.students});

  final List<UserModel> students;

  @override
  ConsumerState<ProjectTeamsPanel> createState() => _ProjectTeamsPanelState();
}

class _ProjectTeamsPanelState extends ConsumerState<ProjectTeamsPanel> {
  String _query = '';
  bool _busy = false;

  Map<String, UserModel> get _byId => {
    for (final s in widget.students) s.uid: s,
  };

  int _visibleMemberCount(ProjectTeamModel team) =>
      team.memberIds.where(_byId.containsKey).length;

  String _visibleSizeLabel(ProjectTeamModel team) {
    final count = _visibleMemberCount(team);
    if (count == 0) return '비어 있음';
    if (count >= ProjectTeamModel.minMembers) return '$count명 · 구성 완료';
    return '$count명 · ${ProjectTeamModel.minMembers}명 이상 권장';
  }

  Future<void> _createTeam(List<ProjectTeamModel> existing) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    final uid = ref.read(currentUserSyncProvider)?.uid;
    if (cohortId == null || uid == null) return;

    final nextNum = existing.length + 1;
    setState(() => _busy = true);
    try {
      await ref
          .read(seatingRepositoryProvider)
          .createProjectTeam(
            cohortId: cohortId,
            name: '$nextNum팀',
            sortOrder: existing.length,
            colorIndex: existing.length,
            updatedBy: uid,
          );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('팀 생성 실패: $e')),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _renameTeam(ProjectTeamModel team) async {
    final controller = TextEditingController(text: team.name);
    final name = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('팀 이름'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(
            labelText: '이름',
            border: OutlineInputBorder(),
          ),
          onSubmitted: (v) => Navigator.pop(context, v.trim()),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('저장'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (name == null || name.isEmpty || name == team.name) return;

    final cohortId = ref.read(effectiveCohortIdProvider);
    final uid = ref.read(currentUserSyncProvider)?.uid;
    if (cohortId == null || uid == null) return;
    await ref
        .read(seatingRepositoryProvider)
        .updateProjectTeam(
          cohortId: cohortId,
          team: team.copyWith(name: name),
          updatedBy: uid,
        );
  }

  Future<void> _deleteTeam(ProjectTeamModel team) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('${team.name} 삭제'),
        content: const Text('팀 구성이 삭제됩니다. 학생 계정은 그대로 둡니다.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
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
        .read(seatingRepositoryProvider)
        .deleteProjectTeam(
          cohortId: cohortId,
          teamId: team.id,
        );
  }

  Future<void> _saveTeam(ProjectTeamModel team) async {
    final cohortId = ref.read(effectiveCohortIdProvider);
    final uid = ref.read(currentUserSyncProvider)?.uid;
    if (cohortId == null || uid == null) return;
    await ref
        .read(seatingRepositoryProvider)
        .updateProjectTeam(
          cohortId: cohortId,
          team: team,
          updatedBy: uid,
        );
  }

  Future<void> _addMember(ProjectTeamModel team, String userId) async {
    if (team.memberIds.contains(userId)) return;
    final activeIds = widget.students.map((student) => student.uid).toSet();
    final validMemberIds = team.memberIds
        .where(activeIds.contains)
        .toList(growable: true);
    await _saveTeam(
      team.copyWith(memberIds: [...validMemberIds, userId]),
    );
  }

  Future<void> _removeMember(ProjectTeamModel team, String userId) async {
    await _saveTeam(
      team.copyWith(
        memberIds: team.memberIds.where((id) => id != userId).toList(),
      ),
    );
  }

  Future<void> _randomizeTeams(List<ProjectTeamModel> existing) async {
    if (widget.students.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('배정할 학생이 없습니다.')),
      );
      return;
    }

    final ok = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('랜덤 팀 구성'),
        content: Text(
          '전체 ${widget.students.length}명을 섞어 팀당 4~5명으로 다시 나눕니다.\n'
          '기존 팀 멤버십은 덮어씁니다.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('구성'),
          ),
        ],
      ),
    );
    if (ok != true) return;

    final cohortId = ref.read(effectiveCohortIdProvider);
    final uid = ref.read(currentUserSyncProvider)?.uid;
    if (cohortId == null || uid == null) return;

    final partitions = ProjectTeamRandomizer.partitionMembers(
      widget.students.map((s) => s.uid).toList(),
    );
    final sortedExisting = [...existing]
      ..sort((a, b) => a.sortOrder.compareTo(b.sortOrder));

    final upserts = <ProjectTeamModel>[];
    for (var i = 0; i < partitions.length; i++) {
      if (i < sortedExisting.length) {
        final t = sortedExisting[i];
        upserts.add(t.copyWith(memberIds: partitions[i], sortOrder: i));
      } else {
        upserts.add(
          ProjectTeamModel(
            id: '',
            name: '${i + 1}팀',
            memberIds: partitions[i],
            sortOrder: i,
            colorIndex: i,
          ),
        );
      }
    }
    final deleteIds = [
      for (var i = partitions.length; i < sortedExisting.length; i++)
        sortedExisting[i].id,
    ];

    setState(() => _busy = true);
    try {
      await ref
          .read(seatingRepositoryProvider)
          .replaceProjectTeams(
            cohortId: cohortId,
            upserts: upserts,
            deleteTeamIds: deleteIds,
            updatedBy: uid,
          );
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${partitions.length}개 팀으로 랜덤 구성했습니다.')),
      );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('랜덤 구성 실패: $e')),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final teamsAsync = ref.watch(projectTeamsProvider);

    return teamsAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => ErrorView(
        message: e.toString(),
        onRetry: () => ref.invalidate(projectTeamsProvider),
      ),
      data: (teams) {
        final assigned = <String>{
          for (final t in teams) ...t.memberIds,
        };
        final unassigned =
            widget.students.where((s) => !assigned.contains(s.uid)).where((s) {
              if (_query.isEmpty) return true;
              return s.displayName.toLowerCase().contains(_query.toLowerCase());
            }).toList()..sort((a, b) => a.displayName.compareTo(b.displayName));

        final completeCount = teams
            .where((t) => _visibleMemberCount(t) >= ProjectTeamModel.minMembers)
            .length;

        final pool = _UnassignedPool(
          students: unassigned,
          query: _query,
          onQueryChanged: (v) => setState(() => _query = v),
          onAddToTeam: (student) async {
            final availableTeams = teams.toList();
            if (availableTeams.isEmpty) {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text('팀이 없습니다. 팀을 먼저 추가하세요.'),
                ),
              );
              return;
            }
            final teamScrollController = ScrollController();
            final target = await showDialog<ProjectTeamModel>(
              context: context,
              builder: (context) => Dialog(
                insetPadding: const EdgeInsets.all(32),
                clipBehavior: Clip.antiAlias,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 560),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Padding(
                        padding: EdgeInsets.fromLTRB(
                          AppSpace.s(20),
                          AppSpace.s(16),
                          AppSpace.s(20),
                          AppSpace.s(12),
                        ),
                        child: Row(
                          children: [
                            Expanded(
                              child: Text(
                                '${student.displayName} 팀 선택',
                                textAlign: TextAlign.center,
                                style: const TextStyle(
                                  fontWeight: FontWeight.w700,
                                  fontSize: 16,
                                ),
                              ),
                            ),
                            IconButton(
                              tooltip: '닫기',
                              onPressed: () => Navigator.pop(context),
                              icon: const Icon(Icons.close),
                            ),
                          ],
                        ),
                      ),
                      ConstrainedBox(
                        constraints: BoxConstraints(
                          maxHeight: MediaQuery.sizeOf(context).height * 0.65,
                        ),
                        child: Scrollbar(
                          controller: teamScrollController,
                          thumbVisibility: true,
                          interactive: true,
                          child: ListView.builder(
                            controller: teamScrollController,
                            shrinkWrap: true,
                            padding: EdgeInsets.only(
                              left: AppSpace.s(8),
                              right: AppSpace.s(16),
                              bottom: AppSpace.s(16),
                            ),
                            itemCount: availableTeams.length,
                            itemBuilder: (context, index) {
                              final t = availableTeams[index];
                              return ListTile(
                                leading: CircleAvatar(
                                  backgroundColor: ProjectTeamColors.softOf(
                                    t.colorIndex,
                                  ),
                                  child: Text(
                                    t.name.isNotEmpty ? t.name[0] : 'T',
                                    style: TextStyle(
                                      color: ProjectTeamColors.accentOf(
                                        t.colorIndex,
                                      ),
                                      fontWeight: FontWeight.w700,
                                    ),
                                  ),
                                ),
                                title: Text(t.name),
                                subtitle: Text(_visibleSizeLabel(t)),
                                onTap: () => Navigator.pop(context, t),
                              );
                            },
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
            teamScrollController.dispose();
            if (target != null) {
              await _addMember(target, student.uid);
            }
          },
        );

        final boards = teams.isEmpty
            ? Padding(
                padding: EdgeInsets.symmetric(vertical: AppSpace.s(48)),
                child: _EmptyTeamsHint(),
              )
            : Column(
                children: [
                  for (var i = 0; i < teams.length; i++) ...[
                    if (i > 0) SizedBox(height: AppSpace.s(12)),
                    _TeamCard(
                      team: teams[i],
                      members: [
                        for (final id in teams[i].memberIds)
                          if (_byId[id] != null) _byId[id]!,
                      ],
                      onRename: () => _renameTeam(teams[i]),
                      onDelete: () => _deleteTeam(teams[i]),
                      onRemoveMember: (uid) => _removeMember(teams[i], uid),
                      onAcceptStudent: (uid) => _addMember(teams[i], uid),
                    ),
                  ],
                ],
              );

        return LayoutBuilder(
          builder: (context, constraints) {
            final wide = constraints.maxWidth >= 960;
            return SingleChildScrollView(
              padding: EdgeInsets.fromLTRB(AppSpace.s(20), AppSpace.s(16), AppSpace.s(20), AppSpace.s(28)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  _HeroBanner(
                    teamCount: teams.length,
                    completeCount: completeCount,
                    unassignedCount: widget.students.length - assigned.length,
                    onAddTeam: _busy ? null : () => _createTeam(teams),
                    onRandomize: _busy ? null : () => _randomizeTeams(teams),
                  ),
                  SizedBox(height: AppSpace.s(16)),
                  if (wide)
                    Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SizedBox(width: 300, child: pool),
                        SizedBox(width: AppSpace.s(16)),
                        Expanded(child: boards),
                      ],
                    )
                  else ...[
                    pool,
                    SizedBox(height: AppSpace.s(12)),
                    boards,
                  ],
                ],
              ),
            );
          },
        );
      },
    );
  }
}

class _HeroBanner extends StatelessWidget {
  const _HeroBanner({
    required this.teamCount,
    required this.completeCount,
    required this.unassignedCount,
    required this.onAddTeam,
    required this.onRandomize,
  });

  final int teamCount;
  final int completeCount;
  final int unassignedCount;
  final VoidCallback? onAddTeam;
  final VoidCallback? onRandomize;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(AppSpace.s(18)),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(18),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [AppColors.sidebar, AppColors.primary],
        ),
        boxShadow: [
          BoxShadow(
            color: AppColors.shadow,
            blurRadius: 18,
            offset: Offset(0, 8),
          ),
        ],
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final narrow = constraints.maxWidth < 520;
          final text = Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                '프로젝트 팀',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                ),
              ),
              SizedBox(height: AppSpace.s(6)),
              Text(
                '팀당 4~5명으로 구성하세요. 배치 편집에서 팀끼리 앉힐 수 있습니다.',
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.85),
                  fontSize: 13,
                  height: 1.4,
                ),
              ),
              SizedBox(height: AppSpace.s(14)),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  _StatPill(label: '팀 $teamCount'),
                  _StatPill(label: '완료 $completeCount'),
                  _StatPill(label: '미배정 $unassignedCount'),
                ],
              ),
            ],
          );
          final buttons = Wrap(
            spacing: 8,
            runSpacing: 8,
            alignment: WrapAlignment.end,
            children: [
              OutlinedButton.icon(
                onPressed: onRandomize,
                style: OutlinedButton.styleFrom(
                  foregroundColor: Colors.white,
                  side: BorderSide(
                    color: Colors.white.withValues(alpha: 0.7),
                  ),
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpace.s(14),
                    vertical: AppSpace.s(14),
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                icon: const Icon(Icons.casino_rounded),
                label: const Text('랜덤 구성'),
              ),
              FilledButton.icon(
                onPressed: onAddTeam,
                style: FilledButton.styleFrom(
                  backgroundColor: AppColors.surface,
                  foregroundColor: AppColors.primaryDark,
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpace.s(16),
                    vertical: AppSpace.s(14),
                  ),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                icon: const Icon(Icons.add_rounded),
                label: const Text('팀 추가'),
              ),
            ],
          );
          if (narrow) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                text,
                SizedBox(height: AppSpace.s(14)),
                Align(alignment: Alignment.centerRight, child: buttons),
              ],
            );
          }
          return Row(
            children: [
              Expanded(child: text),
              SizedBox(width: AppSpace.s(12)),
              buttons,
            ],
          );
        },
      ),
    );
  }
}

class _StatPill extends StatelessWidget {
  const _StatPill({required this.label});
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: AppSpace.s(10), vertical: AppSpace.s(5)),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withValues(alpha: 0.2)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: Colors.white,
          fontSize: 12,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }
}

class _UnassignedPool extends StatelessWidget {
  const _UnassignedPool({
    required this.students,
    required this.query,
    required this.onQueryChanged,
    required this.onAddToTeam,
  });

  final List<UserModel> students;
  final String query;
  final ValueChanged<String> onQueryChanged;
  final ValueChanged<UserModel> onAddToTeam;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border),
        boxShadow: [
          BoxShadow(
            color: AppColors.shadow,
            blurRadius: 12,
            offset: Offset(0, 4),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(AppSpace.s(14), AppSpace.s(14), AppSpace.s(14), AppSpace.s(8)),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      Icons.person_search_rounded,
                      size: 18,
                      color: AppColors.primary,
                    ),
                    SizedBox(width: AppSpace.s(6)),
                    const Text(
                      '미배정 학생',
                      style: TextStyle(fontWeight: FontWeight.w700),
                    ),
                    const Spacer(),
                    Text(
                      '${students.length}명',
                      style: TextStyle(
                        fontSize: 12,
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
                SizedBox(height: AppSpace.s(10)),
                TextField(
                  onChanged: onQueryChanged,
                  decoration: InputDecoration(
                    hintText: '이름 검색',
                    isDense: true,
                    prefixIcon: const Icon(Icons.search, size: 18),
                    filled: true,
                    fillColor: AppColors.surfaceVariant,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: BorderSide.none,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          if (students.isEmpty)
            Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpace.s(28)),
              child: Center(
                child: Text(
                  '모두 팀에 배정되었습니다',
                  style: TextStyle(color: AppColors.textSecondary),
                ),
              ),
            )
          else
            Padding(
              padding: EdgeInsets.fromLTRB(AppSpace.s(8), AppSpace.s(8), AppSpace.s(8), AppSpace.s(12)),
              child: Column(
                children: [
                  for (final s in students)
                    Draggable<String>(
                      data: s.uid,
                      rootOverlay: true,
                      feedback: Material(
                        elevation: 6,
                        borderRadius: BorderRadius.circular(10),
                        child: Container(
                          padding: EdgeInsets.symmetric(
                            horizontal: AppSpace.s(14),
                            vertical: AppSpace.s(10),
                          ),
                          decoration: BoxDecoration(
                            color: AppColors.primary,
                            borderRadius: BorderRadius.circular(10),
                          ),
                          child: Text(
                            s.displayName,
                            style: TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                      ),
                      childWhenDragging: Opacity(
                        opacity: 0.35,
                        child: _StudentTile(
                          name: s.displayName,
                          onAdd: () => onAddToTeam(s),
                        ),
                      ),
                      child: _StudentTile(
                        name: s.displayName,
                        onAdd: () => onAddToTeam(s),
                      ),
                    ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _StudentTile extends StatelessWidget {
  const _StudentTile({required this.name, required this.onAdd});

  final String name;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: EdgeInsets.symmetric(vertical: AppSpace.s(4), horizontal: AppSpace.s(4)),
      elevation: 0,
      color: AppColors.surfaceVariant,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      child: ListTile(
        dense: true,
        contentPadding: EdgeInsets.only(left: AppSpace.s(12), right: AppSpace.s(4)),
        leading: CircleAvatar(
          radius: 14,
          backgroundColor: AppColors.primaryLight,
          child: Text(
            name.isNotEmpty ? name[0] : '?',
            style: TextStyle(
              fontSize: 12,
              color: AppColors.primary,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        title: Text(
          name,
          style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13),
        ),
        trailing: IconButton(
          tooltip: '팀에 추가',
          icon: const Icon(Icons.add_circle_outline, size: 20),
          color: AppColors.primary,
          onPressed: onAdd,
        ),
      ),
    );
  }
}

class _TeamCard extends StatelessWidget {
  const _TeamCard({
    required this.team,
    required this.members,
    required this.onRename,
    required this.onDelete,
    required this.onRemoveMember,
    required this.onAcceptStudent,
  });

  final ProjectTeamModel team;
  final List<UserModel> members;
  final VoidCallback onRename;
  final VoidCallback onDelete;
  final ValueChanged<String> onRemoveMember;
  final ValueChanged<String> onAcceptStudent;

  @override
  Widget build(BuildContext context) {
    final accent = ProjectTeamColors.accentOf(team.colorIndex);
    final soft = ProjectTeamColors.softOf(team.colorIndex);

    return DragTarget<String>(
      onWillAcceptWithDetails: (_) => true,
      onAcceptWithDetails: (details) => onAcceptStudent(details.data),
      builder: (context, candidate, _) {
        final hovering = candidate.isNotEmpty;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          decoration: BoxDecoration(
            color: AppColors.surface,
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: hovering ? accent : AppColors.border,
              width: hovering ? 2 : 1,
            ),
            boxShadow: [
              BoxShadow(
                color: AppColors.shadow,
                blurRadius: 12,
                offset: Offset(0, 4),
              ),
            ],
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Container(
                padding: EdgeInsets.fromLTRB(AppSpace.s(14), AppSpace.s(12), AppSpace.s(8), AppSpace.s(12)),
                decoration: BoxDecoration(
                  color: soft,
                  borderRadius: const BorderRadius.vertical(
                    top: Radius.circular(15),
                  ),
                ),
                child: Row(
                  children: [
                    Container(
                      width: 10,
                      height: 10,
                      decoration: BoxDecoration(
                        color: accent,
                        shape: BoxShape.circle,
                      ),
                    ),
                    SizedBox(width: AppSpace.s(8)),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            team.name,
                            style: TextStyle(
                              fontWeight: FontWeight.w800,
                              fontSize: 15,
                              color: accent,
                            ),
                          ),
                          SizedBox(height: AppSpace.s(2)),
                          Text(
                            members.isEmpty
                                ? '비어 있음'
                                : members.length >= ProjectTeamModel.minMembers
                                ? '${members.length}명 · 구성 완료'
                                : '${members.length}명 · ${ProjectTeamModel.minMembers}명 이상 권장',
                            style: TextStyle(
                              fontSize: 11,
                              color: members.length >= ProjectTeamModel.minMembers
                                  ? AppColors.success
                                  : AppColors.textSecondary,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ),
                    IconButton(
                      tooltip: '이름 변경',
                      onPressed: onRename,
                      icon: const Icon(Icons.edit_outlined, size: 18),
                    ),
                    IconButton(
                      tooltip: '삭제',
                      onPressed: onDelete,
                      icon: const Icon(Icons.delete_outline, size: 18),
                      color: AppColors.error,
                    ),
                  ],
                ),
              ),
              Padding(
                padding: EdgeInsets.fromLTRB(AppSpace.s(12), AppSpace.s(10), AppSpace.s(12), AppSpace.s(12)),
                child: members.isEmpty
                    ? Container(
                        width: double.infinity,
                        padding: EdgeInsets.symmetric(vertical: AppSpace.s(22)),
                        decoration: BoxDecoration(
                          color: AppColors.surfaceVariant,
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: hovering ? accent : Colors.transparent,
                          ),
                        ),
                        child: Text(
                          hovering ? '여기에 놓기' : '학생을 드래그하거나 + 로 추가',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            color: hovering ? accent : AppColors.textHint,
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      )
                    : Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          for (final m in members)
                            InputChip(
                              label: Text(m.displayName),
                              avatar: CircleAvatar(
                                backgroundColor: soft,
                                child: Text(
                                  m.displayName.isNotEmpty
                                      ? m.displayName[0]
                                      : '?',
                                  style: TextStyle(
                                    fontSize: 11,
                                    color: accent,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ),
                              onDeleted: () => onRemoveMember(m.uid),
                              deleteIconColor: AppColors.textSecondary,
                              backgroundColor: soft.withValues(alpha: 0.55),
                              side: BorderSide(
                                color: accent.withValues(alpha: 0.25),
                              ),
                            ),
                          ...List.generate(
                            (ProjectTeamModel.minMembers - members.length)
                                .clamp(0, ProjectTeamModel.minMembers),
                            (_) => Container(
                              width: 36,
                              height: 32,
                              alignment: Alignment.center,
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(
                                  color: AppColors.border,
                                  style: BorderStyle.solid,
                                ),
                                color: AppColors.surfaceVariant,
                              ),
                              child: Icon(
                                Icons.add,
                                size: 14,
                                color: AppColors.textHint,
                              ),
                            ),
                          ),
                        ],
                      ),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _EmptyTeamsHint extends StatelessWidget {
  const _EmptyTeamsHint();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.groups_2_outlined,
            size: 48,
            color: AppColors.textHint.withValues(alpha: 0.8),
          ),
          SizedBox(height: AppSpace.s(12)),
          const Text(
            '아직 팀이 없습니다',
            style: TextStyle(
              fontWeight: FontWeight.w700,
              fontSize: 16,
            ),
          ),
          SizedBox(height: AppSpace.s(6)),
          Text(
            '오른쪽 위 「팀 추가」로 시작해 보세요',
            style: TextStyle(color: AppColors.textSecondary),
          ),
        ],
      ),
    );
  }
}
