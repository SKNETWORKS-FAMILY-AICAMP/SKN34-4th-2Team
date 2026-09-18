import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/theme/app_space.dart';

class RecordFileUpload extends StatelessWidget {
  const RecordFileUpload({
    super.key,
    required this.files,
    required this.onPick,
    required this.onRemove,
    this.multiple = false,
    this.hint = '증빙 이미지를 첨부해 주세요',
  });

  final List<PlatformFile> files;
  final VoidCallback onPick;
  final void Function(int index) onRemove;
  final bool multiple;
  final String hint;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OutlinedButton.icon(
          onPressed: onPick,
          icon: const Icon(Icons.upload_file_outlined),
          label: Text(multiple ? '파일 추가' : '파일 선택'),
          style: OutlinedButton.styleFrom(
            padding: EdgeInsets.symmetric(vertical: AppSpace.s(14)),
            side: BorderSide(color: AppColors.border),
          ),
        ),
        if (files.isEmpty)
          Padding(
            padding: EdgeInsets.only(top: AppSpace.s(8)),
            child: Text(
              hint,
              style: TextStyle(fontSize: 12, color: AppColors.textHint),
            ),
          ),
        ...List.generate(files.length, (i) {
          final f = files[i];
          return ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.insert_drive_file_outlined, size: 20),
            title: Text(f.name, style: const TextStyle(fontSize: 13)),
            trailing: IconButton(
              icon: const Icon(Icons.close, size: 18),
              onPressed: () => onRemove(i),
            ),
          );
        }),
      ],
    );
  }
}

Future<List<PlatformFile>> pickRecordFiles({required bool multiple}) async {
  final files = await FilePicker.pickFiles(
    type: FileType.custom,
    allowedExtensions: ['jpg', 'jpeg', 'png', 'pdf'],
    allowMultiple: multiple,
  );
  return files;
}
