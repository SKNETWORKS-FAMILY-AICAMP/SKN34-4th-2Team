import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/routing/route_paths.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/widgets/app_dropdown.dart';
import '../../../core/widgets/loading_widgets.dart';
import '../../../shared/models/inflearn_package_model.dart';
import '../../../shared/providers/cohort_providers.dart';
import '../../../shared/providers/lms_providers.dart';
import '../../study_room/presentation/widgets/inflearn_package_card.dart';
import '../../study_room/presentation/widgets/study_room_layout.dart';
import '../../../core/theme/app_space.dart';

/// 관리자 — 인프런 강의 패키지 생성/수정
class AdminInflearnPackageFormScreen extends ConsumerStatefulWidget {
  const AdminInflearnPackageFormScreen({
    super.key,
    this.packageId,
  });

  final String? packageId;

  bool get isEditing => packageId != null && packageId!.isNotEmpty;

  @override
  ConsumerState<AdminInflearnPackageFormScreen> createState() =>
      _AdminInflearnPackageFormScreenState();
}

class _CourseField {
  _CourseField({String title = '', String url = ''})
      : title = TextEditingController(text: title),
        url = TextEditingController(text: url);

  final TextEditingController title;
  final TextEditingController url;

  void dispose() {
    title.dispose();
    url.dispose();
  }
}

class _UnitField {
  _UnitField({String name = '', List<_CourseField>? courses})
      : name = TextEditingController(text: name),
        courses = courses ?? [_CourseField()];

  final TextEditingController name;
  final List<_CourseField> courses;

  void dispose() {
    name.dispose();
    for (final c in courses) {
      c.dispose();
    }
  }
}

class _AdminInflearnPackageFormScreenState
    extends ConsumerState<AdminInflearnPackageFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final _titleController = TextEditingController();
  final _subjectController = TextEditingController();
  final _summaryController = TextEditingController();
  final _sortOrderController = TextEditingController(text: '0');

  InflearnPackageType _type = InflearnPackageType.review;
  bool _useUnits = true;
  bool _isSaving = false;
  bool _loaded = false;
  bool _isPublished = false;
  DateTime? _publishedAt;

  final List<_UnitField> _units = [_UnitField(name: 'Python')];
  final List<_CourseField> _flatCourses = [_CourseField()];

  @override
  void dispose() {
    _titleController.dispose();
    _subjectController.dispose();
    _summaryController.dispose();
    _sortOrderController.dispose();
    for (final u in _units) {
      u.dispose();
    }
    for (final c in _flatCourses) {
      c.dispose();
    }
    super.dispose();
  }

  void _loadPackage(InflearnPackageModel p) {
    if (_loaded) return;
    _loaded = true;
    _titleController.text = p.title;
    _subjectController.text = p.subject;
    _summaryController.text = p.summary ?? '';
    _sortOrderController.text = '${p.sortOrder}';
    _type = p.type;
    _isPublished = p.isPublished;
    _publishedAt = p.publishedAt;

    for (final u in _units) {
      u.dispose();
    }
    _units.clear();
    for (final c in _flatCourses) {
      c.dispose();
    }
    _flatCourses.clear();

    if (p.hasUnits) {
      _useUnits = true;
      for (final unit in p.units) {
        _units.add(
          _UnitField(
            name: unit.name,
            courses: unit.courses
                .map((c) => _CourseField(title: c.title, url: c.url))
                .toList(),
          ),
        );
      }
      if (_units.isEmpty) _units.add(_UnitField());
    } else {
      _useUnits = false;
      for (final course in p.courses) {
        _flatCourses.add(
          _CourseField(title: course.title, url: course.url),
        );
      }
      if (_flatCourses.isEmpty) _flatCourses.add(_CourseField());
    }
  }

  List<InflearnUnitModel> _buildUnits() {
    return _units
        .where((u) => u.name.text.trim().isNotEmpty)
        .map(
          (u) => InflearnUnitModel(
            name: u.name.text.trim(),
            courses: u.courses
                .where((c) => c.title.text.trim().isNotEmpty)
                .map(
                  (c) => InflearnCourseModel(
                    title: c.title.text.trim(),
                    url: c.url.text.trim(),
                  ),
                )
                .toList(),
          ),
        )
        .where((u) => u.courses.isNotEmpty)
        .toList();
  }

  List<InflearnCourseModel> _buildFlatCourses() {
    return _flatCourses
        .where((c) => c.title.text.trim().isNotEmpty)
        .map(
          (c) => InflearnCourseModel(
            title: c.title.text.trim(),
            url: c.url.text.trim(),
          ),
        )
        .toList();
  }

  InflearnPackageModel _buildModel({required String id}) {
    final sortOrder = int.tryParse(_sortOrderController.text.trim()) ?? 0;
    return InflearnPackageModel(
      id: id,
      title: _titleController.text.trim(),
      subject: _subjectController.text.trim(),
      type: _type,
      summary: _summaryController.text.trim().isEmpty
          ? null
          : _summaryController.text.trim(),
      units: _useUnits ? _buildUnits() : const [],
      courses: _useUnits ? const [] : _buildFlatCourses(),
      isPublished: _isPublished,
      sortOrder: sortOrder,
      publishedAt: _publishedAt,
    );
  }

  Future<void> _save({required bool publish}) async {
    if (!_formKey.currentState!.validate()) return;

    final cohortId = ref.read(effectiveCohortIdProvider);
    if (cohortId == null) return;

    if (_useUnits && _buildUnits().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('단원과 강의를 1개 이상 등록해주세요.')),
      );
      return;
    }
    if (!_useUnits && _buildFlatCourses().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('강의를 1개 이상 등록해주세요.')),
      );
      return;
    }

    setState(() => _isSaving = true);
    try {
      final repo = ref.read(lmsRepositoryProvider);
      final now = DateTime.now();

      if (widget.isEditing) {
        final updates = <String, dynamic>{
          'title': _titleController.text.trim(),
          'subject': _subjectController.text.trim(),
          'type': _type.value,
          'summary': _summaryController.text.trim(),
          'units': _useUnits
              ? _buildUnits().map((u) => u.toMap()).toList()
              : <Map<String, dynamic>>[],
          'courses': _useUnits
              ? <Map<String, dynamic>>[]
              : _buildFlatCourses().map((c) => c.toMap()).toList(),
          'sortOrder': int.tryParse(_sortOrderController.text.trim()) ?? 0,
        };
        if (publish) {
          updates['isPublished'] = true;
          updates['publishedAt'] = _publishedAt ?? now;
        }
        await repo.updateInflearnPackage(
          cohortId: cohortId,
          packageId: widget.packageId!,
          updates: updates,
        );
      } else {
        final model = _buildModel(id: '').copyWith(
          isPublished: publish,
          publishedAt: publish ? now : null,
        );
        await repo.createInflearnPackage(cohortId: cohortId, package: model);
      }

      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(publish ? '패키지가 공개되었습니다.' : '저장되었습니다.')),
      );
      context.go(RoutePaths.adminStudyRoom);
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
    final packages = ref.watch(inflearnPackagesProvider);

    if (widget.isEditing) {
      return packages.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => ErrorView(message: e.toString()),
        data: (list) {
          InflearnPackageModel? pkg;
          for (final p in list) {
            if (p.id == widget.packageId) {
              pkg = p;
              break;
            }
          }
          if (pkg == null) {
            return const Center(child: Text('패키지를 찾을 수 없습니다.'));
          }
          _loadPackage(pkg);
          return _buildForm();
        },
      );
    }

    return _buildForm();
  }

  Widget _buildForm() {
    final preview = _buildModel(id: 'preview');

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => context.go(RoutePaths.adminStudyRoom),
        ),
        title: Text(widget.isEditing ? '패키지 수정' : '패키지 등록'),
      ),
      body: SingleChildScrollView(
        child: studyRoomContentWrapper(
          child: Form(
            key: _formKey,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                TextFormField(
                  controller: _titleController,
                  decoration: const InputDecoration(
                    labelText: '패키지 제목 *',
                    hintText: '예: 프로그래밍과 데이터 기초 예복습',
                  ),
                  validator: (v) =>
                      v == null || v.trim().isEmpty ? '제목을 입력하세요' : null,
                ),
                SizedBox(height: AppSpace.s(12)),
                TextFormField(
                  controller: _subjectController,
                  decoration: const InputDecoration(
                    labelText: '교과목 *',
                    hintText: '예: 프로그래밍과 데이터 기초',
                  ),
                  validator: (v) =>
                      v == null || v.trim().isEmpty ? '교과목을 입력하세요' : null,
                ),
                SizedBox(height: AppSpace.s(12)),
                AppDropdownField<InflearnPackageType>(
                  value: _type,
                  decoration: const InputDecoration(labelText: '유형'),
                  items: [
                    for (final t in InflearnPackageType.values)
                      AppDropdownItem(value: t, label: t.label),
                  ],
                  onChanged: (v) {
                    if (v != null) setState(() => _type = v);
                  },
                ),
                SizedBox(height: AppSpace.s(12)),
                TextFormField(
                  controller: _summaryController,
                  maxLines: 3,
                  decoration: const InputDecoration(
                    labelText: '안내 문구 (선택)',
                    hintText: '공지에 포함된 안내 문구를 입력하세요.',
                  ),
                ),
                SizedBox(height: AppSpace.s(12)),
                TextFormField(
                  controller: _sortOrderController,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(
                    labelText: '정렬 순서',
                    hintText: '숫자가 작을수록 위에 표시',
                  ),
                ),
                SizedBox(height: AppSpace.s(20)),
                SegmentedButton<bool>(
                  segments: const [
                    ButtonSegment(
                      value: true,
                      label: Text('단원별 (표 형태)'),
                      icon: Icon(Icons.table_rows, size: 16),
                    ),
                    ButtonSegment(
                      value: false,
                      label: Text('단순 목록'),
                      icon: Icon(Icons.list, size: 16),
                    ),
                  ],
                  selected: {_useUnits},
                  onSelectionChanged: (s) =>
                      setState(() => _useUnits = s.first),
                ),
                SizedBox(height: AppSpace.s(16)),
                if (_useUnits) _buildUnitsEditor() else _buildFlatEditor(),
                SizedBox(height: AppSpace.s(24)),
                const Text(
                  '미리보기',
                  style: TextStyle(fontSize: 14, fontWeight: FontWeight.w600),
                ),
                SizedBox(height: AppSpace.s(8)),
                InflearnPackageCard(package: preview, showDraft: true),
                SizedBox(height: AppSpace.s(24)),
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton(
                        onPressed: _isSaving ? null : () => _save(publish: false),
                        child: const Text('임시 저장'),
                      ),
                    ),
                    SizedBox(width: AppSpace.s(12)),
                    Expanded(
                      child: FilledButton(
                        onPressed: _isSaving ? null : () => _save(publish: true),
                        child: _isSaving
                            ? const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Text('공개'),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildUnitsEditor() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (var i = 0; i < _units.length; i++) ...[
          Card(
            elevation: 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
              side: BorderSide(color: AppColors.border),
            ),
            child: Padding(
              padding: EdgeInsets.all(AppSpace.s(12)),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Row(
                    children: [
                      Expanded(
                        child: TextFormField(
                          controller: _units[i].name,
                          decoration: InputDecoration(
                            labelText: '단원 ${i + 1}',
                            hintText: '예: Python, Data base',
                          ),
                        ),
                      ),
                      if (_units.length > 1)
                        IconButton(
                          icon: const Icon(Icons.delete_outline),
                          onPressed: () {
                            setState(() {
                              _units[i].dispose();
                              _units.removeAt(i);
                            });
                          },
                        ),
                    ],
                  ),
                  SizedBox(height: AppSpace.s(8)),
                  for (var j = 0; j < _units[i].courses.length; j++)
                    _courseRow(
                      _units[i].courses[j],
                      onRemove: _units[i].courses.length > 1
                          ? () {
                              setState(() {
                                _units[i].courses[j].dispose();
                                _units[i].courses.removeAt(j);
                              });
                            }
                          : null,
                    ),
                  Align(
                    alignment: Alignment.centerLeft,
                    child: TextButton.icon(
                      onPressed: () {
                        setState(() => _units[i].courses.add(_CourseField()));
                      },
                      icon: const Icon(Icons.add, size: 18),
                      label: const Text('강의 추가'),
                    ),
                  ),
                ],
              ),
            ),
          ),
          SizedBox(height: AppSpace.s(8)),
        ],
        OutlinedButton.icon(
          onPressed: () => setState(() => _units.add(_UnitField())),
          icon: const Icon(Icons.add),
          label: const Text('단원 추가'),
        ),
      ],
    );
  }

  Widget _buildFlatEditor() {
    return Column(
      children: [
        for (var i = 0; i < _flatCourses.length; i++)
          _courseRow(
            _flatCourses[i],
            onRemove: _flatCourses.length > 1
                ? () {
                    setState(() {
                      _flatCourses[i].dispose();
                      _flatCourses.removeAt(i);
                    });
                  }
                : null,
          ),
        Align(
          alignment: Alignment.centerLeft,
          child: TextButton.icon(
            onPressed: () => setState(() => _flatCourses.add(_CourseField())),
            icon: const Icon(Icons.add, size: 18),
            label: const Text('강의 추가'),
          ),
        ),
      ],
    );
  }

  Widget _courseRow(_CourseField field, {VoidCallback? onRemove}) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpace.s(8)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            flex: 2,
            child: TextFormField(
              controller: field.title,
              decoration: const InputDecoration(
                labelText: '강의명',
                hintText: '인프런 강의 제목',
              ),
            ),
          ),
          SizedBox(width: AppSpace.s(8)),
          Expanded(
            flex: 3,
            child: TextFormField(
              controller: field.url,
              decoration: const InputDecoration(
                labelText: 'URL',
                hintText: 'https://www.inflearn.com/...',
              ),
            ),
          ),
          if (onRemove != null)
            IconButton(
              icon: const Icon(Icons.close, size: 18),
              onPressed: onRemove,
            ),
        ],
      ),
    );
  }
}
