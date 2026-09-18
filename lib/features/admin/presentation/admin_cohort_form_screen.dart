import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../core/constants/cohort_status.dart';
import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/utils/date_utils.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/cohort_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../auth/providers/auth_providers.dart';
import '../../curriculum/data/curriculum_repository.dart';
import '../../curriculum/providers/curriculum_providers.dart';
import 'widgets/admin_page_layout.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 기수 생성 / 수정
class AdminCohortFormScreen extends ConsumerStatefulWidget {
  const AdminCohortFormScreen({super.key, this.cohortId});

  final String? cohortId;

  bool get isEditing => cohortId != null && cohortId!.isNotEmpty;

  @override
  ConsumerState<AdminCohortFormScreen> createState() =>
      _AdminCohortFormScreenState();
}

class _AdminCohortFormScreenState extends ConsumerState<AdminCohortFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _termController = TextEditingController();
  final _descriptionController = TextEditingController();
  final _classroomController = TextEditingController();

  DateTime? _startDate;
  DateTime? _endDate;
  CohortStatus _status = CohortStatus.upcoming;
  CohortModel? _existing;
  bool _loaded = false;
  bool _isSaving = false;
  bool _isUploadingPdf = false;

  @override
  void dispose() {
    _nameController.dispose();
    _termController.dispose();
    _descriptionController.dispose();
    _classroomController.dispose();
    super.dispose();
  }

  Future<void> _pickAndUploadCurriculumPdf() async {
    final cohortId = widget.cohortId;
    final uid = ref.read(sessionUidProvider).value;
    if (cohortId == null || uid == null) return;

    final picked = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['pdf'],
    );
    if (picked.isEmpty || !mounted) return;

    final file = picked.first;
    final bytes = await file.readAsBytes();
    if (!mounted) return;
    if (bytes.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('파일을 읽을 수 없습니다.')),
      );
      return;
    }
    if (bytes.length > kCurriculumPdfMaxBytes) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('PDF는 20MB 이하만 업로드할 수 있습니다.')),
      );
      return;
    }

    setState(() => _isUploadingPdf = true);
    try {
      final repo = ref.read(curriculumRepositoryProvider);
      final url = await repo.uploadPdf(
        cohortId: cohortId,
        fileName: file.name,
        bytes: bytes,
      );
      await repo.saveFullPdf(
        cohortId: cohortId,
        pdfUrl: url,
        fileName: file.name,
        updatedBy: uid,
      );
      ref.invalidate(curriculumMetaForCohortProvider(cohortId));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('커리큘럼 PDF가 등록되었습니다.')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('PDF 업로드 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _isUploadingPdf = false);
    }
  }

  Future<void> _clearCurriculumPdf() async {
    final cohortId = widget.cohortId;
    final uid = ref.read(sessionUidProvider).value;
    if (cohortId == null || uid == null) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('커리큘럼 PDF 삭제'),
        content: const Text('등록된 PDF를 삭제할까요? 학생 대시보드에서도 더 이상 보이지 않습니다.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('취소'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('삭제'),
          ),
        ],
      ),
    );
    if (confirmed != true || !mounted) return;

    setState(() => _isUploadingPdf = true);
    try {
      await ref
          .read(curriculumRepositoryProvider)
          .clearFullPdf(
            cohortId: cohortId,
            updatedBy: uid,
          );
      ref.invalidate(curriculumMetaForCohortProvider(cohortId));
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('커리큘럼 PDF가 삭제되었습니다.')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('삭제 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _isUploadingPdf = false);
    }
  }

  Future<void> _openCurriculumPdf(String url) async {
    final uri = Uri.tryParse(url);
    if (uri == null) return;
    final ok = await launchUrl(uri, mode: LaunchMode.externalApplication);
    if (!ok && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('PDF를 열 수 없습니다.')),
      );
    }
  }

  void _load(CohortModel c) {
    if (_loaded) return;
    _loaded = true;
    _existing = c;
    _nameController.text = c.name;
    _termController.text = (_termOf(c)?.toString()) ?? '';
    _descriptionController.text = c.description ?? '';
    _classroomController.text = c.classroomName ?? '';
    _startDate = c.startDate;
    _endDate = c.endDate;
    _status = c.status;
  }

  int? _termOf(CohortModel c) {
    if (c.termNumber != null) return c.termNumber;
    final idMatch = RegExp(r'(\d+)$').firstMatch(c.cohortId);
    if (idMatch != null) return int.tryParse(idMatch.group(1)!);
    final nameMatch = RegExp(r'(\d+)기').firstMatch(c.name);
    return nameMatch != null ? int.tryParse(nameMatch.group(1)!) : null;
  }

  Future<void> _pickDate({required bool isStart}) async {
    final initial = isStart
        ? (_startDate ?? DateTime.now())
        : (_endDate ?? _startDate ?? DateTime.now());
    final firstDate = isStart ? DateTime(2020) : (_startDate ?? DateTime(2020));
    var initialDate = initial;
    if (initialDate.isBefore(firstDate)) initialDate = firstDate;
    final picked = await showDatePicker(
      context: context,
      initialDate: initialDate,
      firstDate: firstDate,
      lastDate: DateTime(2035),
    );
    if (picked == null) return;
    setState(() {
      if (isStart) {
        _startDate = picked;
        if (_endDate != null && _endDate!.isBefore(picked)) {
          _endDate = picked;
        }
      } else {
        _endDate = picked;
      }
    });
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    if (_startDate == null || _endDate == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('시작일과 종료일을 선택해주세요.')),
      );
      return;
    }
    if (_endDate!.isBefore(_startDate!)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('종료일은 시작일 이후여야 합니다.')),
      );
      return;
    }

    final term = widget.isEditing
        ? (_existing != null ? _termOf(_existing!) : null) ??
              int.tryParse(_termController.text.trim())
        : int.tryParse(_termController.text.trim());
    if (term == null || term <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('유효한 기수 번호를 입력하세요.')),
      );
      return;
    }

    setState(() => _isSaving = true);
    try {
      final repo = ref.read(lmsRepositoryProvider);
      final description = _descriptionController.text.trim();
      final classroom = _classroomController.text.trim();
      final base =
          _existing ??
          CohortModel(
            cohortId: 'cohort_$term',
            name: _nameController.text.trim(),
            termNumber: term,
          );
      final cohort = base.copyWith(
        name: _nameController.text.trim(),
        description: description.isEmpty ? null : description,
        startDate: _startDate,
        endDate: _endDate,
        status: _status,
        termNumber: term,
        classroomName: classroom.isEmpty ? null : classroom,
      );

      if (widget.isEditing) {
        await repo.updateCohort(cohort);
      } else {
        await repo.createCohort(cohort);
        selectCohort(ref, cohort.cohortId);
      }

      ref.invalidate(allCohortsAdminProvider);
      ref.invalidate(cohortsStreamProvider);

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              widget.isEditing ? '기수 정보가 수정되었습니다.' : '기수가 생성되었습니다.',
            ),
          ),
        );
        context.go(RoutePaths.adminCohorts);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('저장 실패: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (widget.isEditing) {
      final cohorts = ref.watch(allCohortsAdminProvider);
      return cohorts.when(
        loading: () => const Scaffold(
          body: Center(child: CircularProgressIndicator()),
        ),
        error: (e, _) => Scaffold(
          appBar: AppBar(),
          body: ErrorView(message: e.toString()),
        ),
        data: (list) {
          final c = list
              .where((x) => x.cohortId == widget.cohortId)
              .firstOrNull;
          if (c == null) {
            return Scaffold(
              appBar: AppBar(),
              body: const Center(child: Text('기수를 찾을 수 없습니다')),
            );
          }
          _load(c);
          return _buildForm();
        },
      );
    }
    return _buildForm();
  }

  Widget _buildForm() {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go(RoutePaths.adminCohorts),
        ),
        title: Text(widget.isEditing ? '기수 수정' : '기수 생성'),
        actions: [
          if (!_isSaving)
            TextButton(
              onPressed: _save,
              child: Text(widget.isEditing ? '저장' : '생성'),
            ),
        ],
      ),
      body: SingleChildScrollView(
        child: adminPageWrapper(
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  widget.isEditing ? '기수 정보 수정' : '새 기수 등록',
                  style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.bold,
                    color: AppColors.textPrimary,
                  ),
                ),
                SizedBox(height: AppSpace.s(20)),
                TextFormField(
                  controller: _termController,
                  keyboardType: TextInputType.number,
                  enabled: !widget.isEditing,
                  decoration: InputDecoration(
                    labelText: '기수 번호 *',
                    hintText: '예: 36',
                    helperText: widget.isEditing
                        ? '기수 번호는 수정할 수 없습니다'
                        : 'cohort_36 형식으로 ID가 생성됩니다',
                  ),
                  validator: (v) {
                    if (widget.isEditing) return null;
                    final n = int.tryParse(v ?? '');
                    if (n == null || n <= 0) {
                      return '유효한 기수 번호를 입력하세요';
                    }
                    return null;
                  },
                ),
                SizedBox(height: AppSpace.s(16)),
                TextFormField(
                  controller: _nameController,
                  decoration: const InputDecoration(
                    labelText: '기수명 *',
                    hintText: 'SK네트웍스 Family AI 캠프 36기',
                  ),
                  validator: (v) =>
                      v == null || v.trim().isEmpty ? '기수명을 입력하세요' : null,
                ),
                SizedBox(height: AppSpace.s(16)),
                TextFormField(
                  controller: _classroomController,
                  decoration: const InputDecoration(
                    labelText: '강의실 (선택)',
                    hintText: '예: 3층 A실',
                  ),
                ),
                SizedBox(height: AppSpace.s(16)),
                TextFormField(
                  controller: _descriptionController,
                  maxLines: 2,
                  decoration: const InputDecoration(
                    labelText: '설명 (선택)',
                  ),
                ),
                SizedBox(height: AppSpace.s(20)),
                const Text(
                  '운영 기간',
                  style: TextStyle(fontWeight: FontWeight.w600),
                ),
                SizedBox(height: AppSpace.s(8)),
                Row(
                  children: [
                    Expanded(
                      child: _DateTile(
                        label: '시작일',
                        value: _startDate,
                        onTap: () => _pickDate(isStart: true),
                      ),
                    ),
                    SizedBox(width: AppSpace.s(12)),
                    Expanded(
                      child: _DateTile(
                        label: '종료일',
                        value: _endDate,
                        onTap: () => _pickDate(isStart: false),
                      ),
                    ),
                  ],
                ),
                SizedBox(height: AppSpace.s(20)),
                const Text(
                  '운영 상태',
                  style: TextStyle(fontWeight: FontWeight.w600),
                ),
                SizedBox(height: AppSpace.s(8)),
                SegmentedButton<CohortStatus>(
                  segments: const [
                    ButtonSegment(
                      value: CohortStatus.upcoming,
                      label: Text('예정'),
                    ),
                    ButtonSegment(
                      value: CohortStatus.active,
                      label: Text('진행중'),
                    ),
                    ButtonSegment(
                      value: CohortStatus.archived,
                      label: Text('종료'),
                    ),
                  ],
                  selected: {_status},
                  onSelectionChanged: (s) => setState(() => _status = s.first),
                ),
                SizedBox(height: AppSpace.s(8)),
                Text(
                  switch (_status) {
                    CohortStatus.upcoming => '예정: 학생 등록·세팅 가능, 드롭다운에서 선택 가능',
                    CohortStatus.active => '진행중: 현재 운영 기수',
                    CohortStatus.archived => '종료: 조회 전용, 드롭다운에서 숨김',
                  },
                  style: TextStyle(
                    fontSize: 12,
                    color: AppColors.textSecondary,
                  ),
                ),
                if (widget.isEditing) ...[
                  SizedBox(height: AppSpace.s(28)),
                  _CurriculumPdfSection(
                    cohortId: widget.cohortId!,
                    isBusy: _isUploadingPdf,
                    onUpload: _pickAndUploadCurriculumPdf,
                    onClear: _clearCurriculumPdf,
                    onOpen: _openCurriculumPdf,
                  ),
                ] else ...[
                  SizedBox(height: AppSpace.s(28)),
                  Text(
                    '커리큘럼 PDF는 기수 생성 후 수정 화면에서 등록할 수 있습니다.',
                    style: TextStyle(
                      fontSize: 12,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
                SizedBox(height: AppSpace.s(32)),
                if (_isSaving)
                  const Center(child: CircularProgressIndicator())
                else
                  FilledButton(
                    onPressed: _save,
                    style: FilledButton.styleFrom(
                      minimumSize: const Size.fromHeight(48),
                    ),
                    child: Text(widget.isEditing ? '저장' : '기수 생성'),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _CurriculumPdfSection extends ConsumerWidget {
  const _CurriculumPdfSection({
    required this.cohortId,
    required this.isBusy,
    required this.onUpload,
    required this.onClear,
    required this.onOpen,
  });

  final String cohortId;
  final bool isBusy;
  final VoidCallback onUpload;
  final VoidCallback onClear;
  final void Function(String url) onOpen;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final metaAsync = ref.watch(curriculumMetaForCohortProvider(cohortId));

    return AdminFormSection(
      title: '커리큘럼 PDF',
      children: [
        Text(
          '이 기수 학생 대시보드의 「PDF 보기」 버튼으로 열립니다.',
          style: TextStyle(fontSize: 12, color: AppColors.textSecondary),
        ),
        SizedBox(height: AppSpace.s(12)),
        metaAsync.when(
          loading: () => Padding(
            padding: EdgeInsets.symmetric(vertical: AppSpace.s(12)),
            child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
          ),
          error: (e, _) => Text('불러오기 실패: $e'),
          data: (meta) {
            final hasPdf = meta?.hasFullPdf == true;
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                if (hasPdf) ...[
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: Icon(
                      Icons.picture_as_pdf,
                      color: AppColors.error,
                    ),
                    title: Text(
                      meta!.fullPdfFileName ?? '커리큘럼 PDF',
                      style: const TextStyle(fontWeight: FontWeight.w600),
                    ),
                    subtitle: const Text('등록됨 · 학생에게 공개'),
                    trailing: IconButton(
                      tooltip: '열기',
                      onPressed: () => onOpen(meta.fullPdfUrl!),
                      icon: const Icon(Icons.open_in_new),
                    ),
                  ),
                  SizedBox(height: AppSpace.s(8)),
                ] else
                  Padding(
                    padding: EdgeInsets.only(bottom: AppSpace.s(12)),
                    child: Text(
                      '아직 등록된 PDF가 없습니다.',
                      style: TextStyle(color: AppColors.textSecondary),
                    ),
                  ),
                if (isBusy)
                  Padding(
                    padding: EdgeInsets.symmetric(vertical: AppSpace.s(8)),
                    child: Center(child: CircularProgressIndicator()),
                  )
                else
                  Wrap(
                    spacing: 8,
                    runSpacing: 8,
                    children: [
                      FilledButton.icon(
                        onPressed: onUpload,
                        icon: Icon(
                          hasPdf ? Icons.swap_horiz : Icons.upload_file,
                          size: 18,
                        ),
                        label: Text(hasPdf ? 'PDF 교체' : 'PDF 등록'),
                      ),
                      if (hasPdf)
                        OutlinedButton.icon(
                          onPressed: onClear,
                          icon: const Icon(Icons.delete_outline, size: 18),
                          label: const Text('삭제'),
                        ),
                    ],
                  ),
              ],
            );
          },
        ),
      ],
    );
  }
}

class _DateTile extends StatelessWidget {
  const _DateTile({
    required this.label,
    required this.value,
    required this.onTap,
  });

  final String label;
  final DateTime? value;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surfaceVariant,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(color: AppColors.border),
      ),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpace.s(12), vertical: AppSpace.s(14)),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                label,
                style: TextStyle(
                  fontSize: 11,
                  color: AppColors.textSecondary,
                ),
              ),
              Text(
                value != null ? AppDateUtils.formatDisplay(value!) : '날짜 선택',
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  color: value != null
                      ? AppColors.textPrimary
                      : AppColors.textHint,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
