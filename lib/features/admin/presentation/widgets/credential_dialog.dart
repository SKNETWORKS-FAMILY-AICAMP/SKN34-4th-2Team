import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../../core/theme/app_colors.dart';
import '../../../../core/theme/app_space.dart';

Future<void> showCredentialDialog(
  BuildContext context, {
  required String displayName,
  required String email,
  required String password,
  String personLabel = '학생',
}) {
  return showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (ctx) => AlertDialog(
      title: const Text('계정 생성 완료'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            '$displayName $personLabel의 로그인 정보입니다.\n아래 내용을 전달해주세요.',
            style: TextStyle(
              fontSize: 13,
              color: AppColors.textSecondary,
            ),
          ),
          SizedBox(height: AppSpace.s(16)),
          _CopyTile(label: '아이디 (이메일)', value: email),
          SizedBox(height: AppSpace.s(8)),
          _CopyTile(label: '비밀번호', value: password),
          SizedBox(height: AppSpace.s(12)),
          Container(
            padding: EdgeInsets.all(AppSpace.s(10)),
            decoration: BoxDecoration(
              color: AppColors.surfaceVariant,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              '관리 페이지에서 비밀번호를 다시 발급할 수 있습니다.',
              style: TextStyle(fontSize: 11, color: AppColors.textSecondary),
            ),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx),
          child: const Text('확인'),
        ),
      ],
    ),
  );
}

class _CopyTile extends StatelessWidget {
  const _CopyTile({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.all(AppSpace.s(12)),
      decoration: BoxDecoration(
        border: Border.all(color: AppColors.border),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        children: [
          Expanded(
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
                SizedBox(height: AppSpace.s(4)),
                SelectableText(
                  value,
                  style: const TextStyle(
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                  ),
                ),
              ],
            ),
          ),
          IconButton(
            tooltip: '복사',
            icon: const Icon(Icons.copy, size: 18),
            onPressed: () {
              Clipboard.setData(ClipboardData(text: value));
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(content: Text('$label 복사됨')),
              );
            },
          ),
        ],
      ),
    );
  }
}
