import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/study_source_model.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../auth/providers/auth_providers.dart';
import 'widgets/study_room_layout.dart';
import '../../../core/theme/app_space.dart';

class StudyRoomNotesScreen extends ConsumerStatefulWidget {
  const StudyRoomNotesScreen({super.key});

  @override
  ConsumerState<StudyRoomNotesScreen> createState() =>
      _StudyRoomNotesScreenState();
}

class _StudyRoomNotesScreenState extends ConsumerState<StudyRoomNotesScreen> {
  String? _expandedSourceId;

  @override
  Widget build(BuildContext context) {
    final userAsync = ref.watch(currentUserProvider);
    final cohortName = ref.watch(effectiveCohortNameProvider);
    final sources = ref.watch(activeStudySourcesProvider);
    final notes = ref.watch(readyStudyNotesProvider);

    return userAsync.when(
      loading: () => const Center(child: CircularProgressIndicator()),
      error: (e, _) => ErrorView(message: e.toString()),
      data: (user) {
        if (user == null) return const SizedBox.shrink();
        return SingleChildScrollView(
          child: studyRoomContentWrapper(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: TextButton.icon(
                    onPressed: () => context.go(RoutePaths.studyRoom),
                    icon: const Icon(Icons.arrow_back, size: 18),
                    label: const Text('학습실'),
                  ),
                ),
                StudyRoomPageHeader(
                  user: user,
                  cohortName: cohortName,
                  title: '공부방',
                  subtitle: '수업 저장소를 고르고, 날짜·폴더·파일만 정리하세요.',
                ),
                SizedBox(height: AppSpace.s(20)),
                sources.when(
                  loading: () => Padding(
                    padding: EdgeInsets.all(AppSpace.s(40)),
                    child: Center(child: CircularProgressIndicator()),
                  ),
                  error: (e, _) => ErrorView(message: e.toString()),
                  data: (list) {
                    if (list.isEmpty) {
                      return Padding(
                        padding: EdgeInsets.symmetric(vertical: AppSpace.s(48)),
                        child: Center(
                          child: Text(
                            '등록된 수업 저장소가 없습니다',
                            style: TextStyle(color: AppColors.textSecondary),
                          ),
                        ),
                      );
                    }
                    return Column(
                      children: [
                        for (final source in list) ...[
                          _SourceCard(
                            source: source,
                            notes:
                                notes.asData?.value
                                    .where((note) => note.sourceId == source.id)
                                    .toList() ??
                                const [],
                            notesLoading: notes.isLoading,
                            expanded: _expandedSourceId == source.id,
                            onToggle: () => setState(() {
                              _expandedSourceId = _expandedSourceId == source.id
                                  ? null
                                  : source.id;
                            }),
                            onCreate: () => context.go(
                              RoutePaths.studyRoomNoteSource(source.id),
                            ),
                            onOpenNote: (noteId) => context.go(
                              RoutePaths.studyRoomNoteSource(
                                source.id,
                                noteId: noteId,
                              ),
                            ),
                          ),
                          SizedBox(height: AppSpace.s(12)),
                        ],
                      ],
                    );
                  },
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _SourceCard extends StatelessWidget {
  const _SourceCard({
    required this.source,
    required this.notes,
    required this.notesLoading,
    required this.expanded,
    required this.onToggle,
    required this.onCreate,
    required this.onOpenNote,
  });

  final StudySourceModel source;
  final List<StudyNoteModel> notes;
  final bool notesLoading;
  final bool expanded;
  final VoidCallback onToggle;
  final VoidCallback onCreate;
  final ValueChanged<String> onOpenNote;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: expanded ? AppColors.primary : AppColors.border,
          ),
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          children: [
            InkWell(
              onTap: onToggle,
              child: Padding(
                padding: EdgeInsets.all(AppSpace.s(16)),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            source.title,
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w700,
                              color: AppColors.textPrimary,
                            ),
                          ),
                          SizedBox(height: AppSpace.s(4)),
                          Text(
                            source.repoLabel,
                            style: TextStyle(color: AppColors.textSecondary),
                          ),
                          SizedBox(height: AppSpace.s(4)),
                          Text(
                            source.prefixSummary,
                            style: TextStyle(
                              fontSize: 12,
                              color: AppColors.textHint,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (notes.isNotEmpty)
                      Container(
                        margin: EdgeInsets.only(right: AppSpace.s(10)),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 9,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: AppColors.primary.withValues(alpha: 0.08),
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Text(
                          '노트 ${notes.length}',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w700,
                            color: AppColors.primary,
                          ),
                        ),
                      ),
                    AnimatedRotation(
                      turns: expanded ? 0.25 : 0,
                      duration: const Duration(milliseconds: 180),
                      child: Icon(
                        Icons.chevron_right,
                        color: AppColors.textHint,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            AnimatedSize(
              duration: const Duration(milliseconds: 200),
              alignment: Alignment.topCenter,
              child: expanded
                  ? _ExpandedNotes(
                      notes: notes,
                      loading: notesLoading,
                      onCreate: onCreate,
                      onOpenNote: onOpenNote,
                    )
                  : const SizedBox(width: double.infinity),
            ),
          ],
        ),
      ),
    );
  }
}

class _ExpandedNotes extends StatelessWidget {
  const _ExpandedNotes({
    required this.notes,
    required this.loading,
    required this.onCreate,
    required this.onOpenNote,
  });

  final List<StudyNoteModel> notes;
  final bool loading;
  final VoidCallback onCreate;
  final ValueChanged<String> onOpenNote;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.all(AppSpace.s(16)),
      decoration: BoxDecoration(
        color: AppColors.background,
        border: Border(top: BorderSide(color: AppColors.border)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '만든 수업노트',
                  style: TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w800,
                    color: AppColors.textPrimary,
                  ),
                ),
              ),
              FilledButton.icon(
                onPressed: onCreate,
                icon: const Icon(Icons.add, size: 18),
                label: const Text('새 수업노트 만들기'),
              ),
            ],
          ),
          SizedBox(height: AppSpace.s(12)),
          if (loading)
            const Center(child: CircularProgressIndicator())
          else if (notes.isEmpty)
            Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpace.s(12)),
              child: Text(
                '아직 만든 수업노트가 없습니다.',
                style: TextStyle(color: AppColors.textSecondary),
              ),
            )
          else
            Wrap(
              spacing: AppSpace.s(8),
              runSpacing: AppSpace.s(8),
              children: [
                for (final note in notes)
                  _NoteCard(note: note, onTap: () => onOpenNote(note.id)),
              ],
            ),
        ],
      ),
    );
  }
}

class _NoteCard extends StatelessWidget {
  const _NoteCard({required this.note, required this.onTap});

  final StudyNoteModel note;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final icon = switch (note.scopeType) {
      'date' => Icons.calendar_today_outlined,
      'prefix' => Icons.folder_outlined,
      _ => Icons.description_outlined,
    };
    return Tooltip(
      message: note.displaySubtitle,
      child: Material(
        color: AppColors.primary.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(9),
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(9),
          child: Container(
            width: 180,
            padding: EdgeInsets.symmetric(
              horizontal: AppSpace.s(12),
              vertical: AppSpace.s(9),
            ),
            child: Row(
              children: [
                Icon(icon, size: 18, color: AppColors.primary),
                SizedBox(width: AppSpace.s(8)),
                Expanded(
                  child: Text(
                    note.displayTitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 13,
                      fontWeight: FontWeight.w700,
                      color: AppColors.primary,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
