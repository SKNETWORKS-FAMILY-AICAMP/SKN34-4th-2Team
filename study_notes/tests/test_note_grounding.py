"""노트가 수업 자료에 없는 것을 지어내지 않았는지 — 코드 블록 표시 · 본문 이름 대조. LLM 없음."""

from __future__ import annotations

import unittest

from study_notes.grounding import MISSING_HEAD, NOT_FROM_LESSON, ground_report, significant_lines

MATERIAL = """### 01_cnn.ipynb
[CODE CELL 3]
conv_layer = nn.Conv2d(in_channels=1, out_channels=4, kernel_size=3, stride=1, padding='same')
x = F.relu(conv_layer(input_tensor))
print(x.shape)
model = YOLO('yolo11n.pt')
"""


class CodeBlockTests(unittest.TestCase):
    def test_reshaped_lesson_code_is_not_marked(self) -> None:
        note = "## 핵심 코드\n```python\nconv_layer = nn.Conv2d(\n    in_channels=1,\n    out_channels=4,\n    kernel_size=3, stride=1, padding='same'\n)\nprint(x.shape)\n```"
        out, stats = ground_report(note, MATERIAL)
        self.assertNotIn(NOT_FROM_LESSON, out)
        self.assertEqual((1, 0), (stats.code_blocks, stats.marked_blocks))

    def test_code_not_in_lesson_is_marked_not_removed(self) -> None:
        note = "```python\nmodel.fit(train_loader, epochs=50)\ntorch.save(model.state_dict(), 'best.pt')\n```"
        out, stats = ground_report(note, MATERIAL)
        self.assertIn("model.fit(train_loader", out, "지우지 않는다")
        self.assertTrue(out.rstrip().endswith(NOT_FROM_LESSON))
        self.assertEqual(1, stats.marked_blocks)

    def test_diagram_blocks_are_not_code(self) -> None:
        note = "```\n입력: 1 × 28 × 28\n→ Conv1: 64 × 28 × 28\n```"
        out, stats = ground_report(note, MATERIAL)
        self.assertEqual(note, out)
        self.assertEqual(0, stats.code_blocks)
        self.assertEqual([], significant_lines("→ Linear: 10\n# 설명"))


class NameTests(unittest.TestCase):
    def test_names_in_the_material_pass(self) -> None:
        note = "- `nn.Conv2d` 에 `padding` 을 주고 `F.relu()` 를 거친다. 모델은 `yolo11n.pt`."
        out, stats = ground_report(note, MATERIAL)
        self.assertEqual(note, out)
        self.assertEqual([], stats.missing)
        self.assertEqual(4, stats.names)

    def test_names_not_in_the_material_are_listed_at_the_end_not_removed(self) -> None:
        note = "- `nn.Conv2d` 다음에 `nn.BatchNorm2d` 를 붙이고 `best_model.pt` 로 저장한다."
        out, stats = ground_report(note, MATERIAL)
        self.assertIn("nn.BatchNorm2d` 를 붙이고", out, "본문은 그대로")
        self.assertIn(f"{MISSING_HEAD} `nn.BatchNorm2d`, `best_model.pt`", out)
        self.assertEqual(["nn.BatchNorm2d", "best_model.pt"], stats.missing)

    def test_python_builtins_are_not_checked(self) -> None:
        _, stats = ground_report("- 정의 전에 쓰면 `NameError` 가 나고, `len()` 으로 길이를 잰다.", MATERIAL)
        self.assertEqual((0, []), (stats.names, stats.missing))

    def test_values_and_code_block_contents_are_not_names(self) -> None:
        note = "- 범위는 `0~1`, 모양은 `(N, 1, H, W)` 다.\n```python\nunknown_func()\n```"
        _, stats = ground_report(note, MATERIAL)
        self.assertEqual(0, stats.names)


if __name__ == "__main__":
    unittest.main()
