/**
 * 실습 문제 데모 데이터 — 34기 multimodal 저장소의 9/11 · 9/14 · 9/15 수업으로
 * study_notes/practice 가 실제로 만들고(gpt-5.6-luna) Pyodide 314.0.7 로 검증한 결과 그대로다.
 * 손으로 고치지 않는다. 다시 만들 땐 python -m study_notes.practice.trial 결과로 바꾼다.
 */
import type { PracticeSet } from '../domain/types';
import { DemoConfig } from './seed';

type SeedSet = Omit<PracticeSet, 'cohortId'>;

const sets: SeedSet[] = [
  {
    "id": "ps-mm-0911",
    "sourceTitle": "multimodal",
    "lessonDate": "2026-09-11",
    "dayLabel": "멀티모달 1일차",
    "title": "CNN · ViT · CLIP",
    "files": [
      "01_cnn/01_cnn.ipynb",
      "01_cnn/02_pretrained_cnn_models.ipynb",
      "01_cnn/03_object_detection_yolo.ipynb",
      "02_ViT/01_vision_transformer.ipynb",
      "03_vision_language_model/01_CLIP.ipynb"
    ],
    "model": "gpt-5.6-luna",
    "problems": [
      {
        "kind": "concept",
        "topic": "CNN의 채널과 필터",
        "prompt": "다음 설명 중 CNN의 채널과 필터에 대한 내용으로 옳은 것은 무엇인가요?",
        "sourceFiles": [
          "01_cnn/01_cnn.ipynb"
        ],
        "explanation": "수업 자료에서는 입력 Image의 채널 수가 필터의 채널 수가 된다고 설명합니다. 또한 필터의 개수는 출력 Feature Map의 채널 수를 결정합니다.",
        "choices": [
          "입력 이미지의 채널 수와 필터의 채널 수는 서로 달라야 한다.",
          "필터의 개수는 입력 이미지의 채널 수를 결정한다.",
          "필터의 개수는 출력 Feature Map의 채널 수가 된다.",
          "하나의 필터를 사용하면 여러 개의 출력값이 항상 동시에 나온다."
        ],
        "answerIndex": 2,
        "starterCode": "",
        "expectedStdout": "",
        "blankAnswers": [],
        "referenceSolution": "",
        "hiddenTests": "",
        "packages": []
      },
      {
        "kind": "concept",
        "topic": "Top-5 정확도와 오류율",
        "prompt": "Top-5 정확도가 93.3%일 때 Top-5 오류율은 얼마인가요?",
        "sourceFiles": [
          "01_cnn/02_pretrained_cnn_models.ipynb"
        ],
        "explanation": "Top-5 오류율은 1에서 Top-5 정확도를 뺀 값입니다. 따라서 1 - 0.933 = 0.067이므로 오류율은 6.7%입니다.",
        "choices": [
          "6.7%",
          "7.7%",
          "93.3%",
          "100%"
        ],
        "answerIndex": 0,
        "starterCode": "",
        "expectedStdout": "",
        "blankAnswers": [],
        "referenceSolution": "",
        "hiddenTests": "",
        "packages": []
      },
      {
        "kind": "code_output",
        "topic": "합성곱과 풀링 후 Feature Map 크기",
        "prompt": "다음 코드를 실행했을 때 출력 결과를 쓰세요. 첫 번째 합성곱은 same padding으로 공간 크기를 유지하고, 두 번째 합성곱은 valid padding을 사용합니다.",
        "sourceFiles": [
          "01_cnn/01_cnn.ipynb"
        ],
        "explanation": "첫 번째 same padding 합성곱 뒤의 크기는 28×28입니다. 두 번째 valid 합성곱으로 26×26이 되고, 2×2 stride 2 풀링 후 13×13이 되므로 출력은 32 13 13입니다.",
        "choices": [],
        "answerIndex": null,
        "starterCode": "height = 28\nwidth = 28\nchannels = 32\n\n# kernel=3, valid padding, stride=1\nheight = (height - 3) // 1 + 1\nwidth = (width - 3) // 1 + 1\n\n# kernel=2, stride=2인 max pooling\nheight = height // 2\nwidth = width // 2\n\nprint(channels, height, width)",
        "expectedStdout": "32 13 13",
        "blankAnswers": [],
        "referenceSolution": "",
        "hiddenTests": "",
        "packages": []
      },
      {
        "kind": "code_blank",
        "topic": "합성곱 출력 크기 공식",
        "prompt": "valid 또는 padding이 주어진 합성곱의 한 변 출력 크기를 계산하도록 빈칸을 채우세요.",
        "sourceFiles": [
          "01_cnn/01_cnn.ipynb"
        ],
        "explanation": "합성곱 출력 크기는 (입력 크기 + 2×패딩 - 커널 크기) // 스트라이드 + 1로 계산합니다. padding이 0이면 valid 방식이고, 입력 크기를 유지하려면 same padding처럼 패딩을 적용합니다.",
        "choices": [],
        "answerIndex": null,
        "starterCode": "def conv_output_size(input_size, kernel_size, stride, padding):\n    return __1__\n\nprint(conv_output_size(28, 3, 1, 0))\nprint(conv_output_size(28, 3, 1, 1))",
        "expectedStdout": "",
        "blankAnswers": [
          "(input_size + 2 * padding - kernel_size) // stride + 1"
        ],
        "referenceSolution": "def conv_output_size(input_size, kernel_size, stride, padding):\n    return (input_size + 2 * padding - kernel_size) // stride + 1\n\nprint(conv_output_size(28, 3, 1, 0))\nprint(conv_output_size(28, 3, 1, 1))",
        "hiddenTests": "assert conv_output_size(28, 3, 1, 0) == 26\nassert conv_output_size(28, 3, 1, 1) == 28\nassert conv_output_size(32, 5, 2, 0) == 14",
        "packages": []
      },
      {
        "kind": "code_fix",
        "topic": "맥스 풀링 연산",
        "prompt": "다음 함수는 2×2 영역마다 가장 큰 값을 선택해야 하지만, 실행하면 작은 값이 선택됩니다. 맥스 풀링이 올바르게 동작하도록 버그 한 곳을 고치세요.",
        "sourceFiles": [
          "01_cnn/01_cnn.ipynb"
        ],
        "explanation": "맥스 풀링은 각 영역에서 가장 큰 값을 선택하는 연산입니다. 따라서 window의 최솟값을 고르는 min(window)을 최댓값을 고르는 max(window)로 바꿔야 합니다.",
        "choices": [],
        "answerIndex": null,
        "starterCode": "def max_pool2x2(matrix):\n    result = []\n    for row in range(0, len(matrix), 2):\n        pooled_row = []\n        for col in range(0, len(matrix[0]), 2):\n            window = [\n                matrix[row][col], matrix[row][col + 1],\n                matrix[row + 1][col], matrix[row + 1][col + 1]\n            ]\n            pooled_row.append(min(window))\n        result.append(pooled_row)\n    return result\n\nx = [[1, 4, 2, 3], [5, 6, 7, 0], [8, 2, 9, 1], [3, 4, 5, 6]]\nprint(max_pool2x2(x))",
        "expectedStdout": "",
        "blankAnswers": [],
        "referenceSolution": "def max_pool2x2(matrix):\n    result = []\n    for row in range(0, len(matrix), 2):\n        pooled_row = []\n        for col in range(0, len(matrix[0]), 2):\n            window = [\n                matrix[row][col], matrix[row][col + 1],\n                matrix[row + 1][col], matrix[row + 1][col + 1]\n            ]\n            pooled_row.append(max(window))\n        result.append(pooled_row)\n    return result\n\nx = [[1, 4, 2, 3], [5, 6, 7, 0], [8, 2, 9, 1], [3, 4, 5, 6]]\nprint(max_pool2x2(x))",
        "hiddenTests": "assert max_pool2x2([[1, 4], [5, 6]]) == [[6]]\nassert max_pool2x2([[1, 2, 3, 4], [5, 6, 7, 8], [9, 0, 2, 1], [3, 4, 5, 6]]) == [[6, 8], [9, 6]]",
        "packages": []
      },
      {
        "kind": "code_write",
        "topic": "2×2 맥스 풀링 함수",
        "prompt": "입력 2차원 리스트에 kernel size 2, stride 2인 맥스 풀링을 적용하는 함수를 작성하세요. 각 2×2 영역의 최댓값을 모아 결과 2차원 리스트를 반환해야 합니다.",
        "sourceFiles": [
          "01_cnn/01_cnn.ipynb"
        ],
        "explanation": "2×2 맥스 풀링은 입력을 2칸씩 이동하면서 각 2×2 영역을 만들고, 그 안의 최댓값을 결과에 추가합니다. 수업의 Max Pooling처럼 공간 크기를 줄이면서 주요한 높은 값을 남기는 방식입니다.",
        "choices": [],
        "answerIndex": null,
        "starterCode": "def max_pool2x2(matrix):\n    \"\"\"2차원 리스트에 2x2 stride 2 맥스 풀링을 적용한다.\"\"\"\n    pass",
        "expectedStdout": "",
        "blankAnswers": [],
        "referenceSolution": "def max_pool2x2(matrix):\n    \"\"\"2차원 리스트에 2x2 stride 2 맥스 풀링을 적용한다.\"\"\"\n    result = []\n    for row in range(0, len(matrix), 2):\n        pooled_row = []\n        for col in range(0, len(matrix[0]), 2):\n            window = [\n                matrix[row][col], matrix[row][col + 1],\n                matrix[row + 1][col], matrix[row + 1][col + 1]\n            ]\n            pooled_row.append(max(window))\n        result.append(pooled_row)\n    return result",
        "hiddenTests": "assert max_pool2x2([[1, 4], [5, 6]]) == [[6]]\nassert max_pool2x2([[1, 2, 3, 4], [5, 6, 7, 8], [9, 0, 2, 1], [3, 4, 5, 6]]) == [[6, 8], [9, 6]]\nassert max_pool2x2([[0, -1], [-2, -3]]) == [[0]]",
        "packages": []
      }
    ]
  },
  {
    "id": "ps-mm-0914",
    "sourceTitle": "multimodal",
    "lessonDate": "2026-09-14",
    "dayLabel": "멀티모달 2일차",
    "title": "BLIP · Stable Diffusion · VQA",
    "files": [
      "03_vision_language_model/02_BLIP.ipynb",
      "03_vision_language_model/03_Llama3.2_vision_vqa.ipynb",
      "04_image_generation/01_stable_diffusion.ipynb",
      "04_image_generation/02_openai_vision_api.ipynb",
      "05_multimodal_rag/01_simple_multimodal_rag.ipynb",
      "05_multimodal_rag/02_video_rag_frame_extraction.ipynb"
    ],
    "model": "gpt-5.6-luna",
    "problems": [
      {
        "kind": "concept",
        "topic": "BLIP의 학습 목적",
        "prompt": "다음 중 BLIP의 주요 사전학습 목적에 해당하지 않는 것은 무엇인가요?",
        "sourceFiles": [
          "03_vision_language_model/02_BLIP.ipynb"
        ],
        "explanation": "BLIP은 이미지와 텍스트의 임베딩을 가깝게 만드는 ITC, 이미지와 텍스트의 짝을 판단하는 ITM, 이미지를 참고해 문장을 생성하는 LM을 함께 학습합니다. 이미지 픽셀을 같은 값으로 만드는 손실은 수업 자료에 나온 BLIP의 목적이 아닙니다.",
        "choices": [
          "Image-Text Contrastive(ITC) Loss",
          "Image-Text Matching(ITM) Loss",
          "Language Modeling(LM) Loss",
          "이미지의 픽셀을 무조건 같은 값으로 만드는 손실"
        ],
        "answerIndex": 3,
        "starterCode": "",
        "expectedStdout": "",
        "blankAnswers": [],
        "referenceSolution": "",
        "hiddenTests": "",
        "packages": []
      },
      {
        "kind": "concept",
        "topic": "Stable Diffusion의 생성 과정",
        "prompt": "Stable Diffusion의 생성 단계에 대한 설명으로 가장 알맞은 것은 무엇인가요?",
        "sourceFiles": [
          "04_image_generation/01_stable_diffusion.ipynb"
        ],
        "explanation": "Stable Diffusion은 잠재 공간에서 완전한 노이즈로부터 시작해 역방향 과정으로 노이즈를 점차 제거합니다. 텍스트 프롬프트의 의미를 반영하면서 최종적으로 이미지를 복원합니다.",
        "choices": [
          "완전한 노이즈에서 시작해 여러 단계로 노이즈를 제거한다.",
          "텍스트를 무시하고 항상 같은 이미지만 출력한다.",
          "이미지를 바로 픽셀 공간에서만 처리하며 잠재 공간을 사용하지 않는다.",
          "생성 과정에서 노이즈를 점점 추가하기만 한다."
        ],
        "answerIndex": 0,
        "starterCode": "",
        "expectedStdout": "",
        "blankAnswers": [],
        "referenceSolution": "",
        "hiddenTests": "",
        "packages": []
      },
      {
        "kind": "code_output",
        "topic": "확산 모델의 순방향 수식",
        "prompt": "다음 코드를 실행했을 때 출력되는 값을 적으세요. 확산 모델의 순방향 수식에서 한 단계의 x_t를 계산합니다.",
        "sourceFiles": [
          "04_image_generation/01_stable_diffusion.ipynb"
        ],
        "explanation": "순방향 수식은 x_t = √α_t x_(t-1) + √(1-α_t) ε입니다. 주어진 값을 대입하면 약 1.118이므로 round를 적용한 출력은 1.12입니다.",
        "choices": [],
        "answerIndex": null,
        "starterCode": "import numpy as np\n\nalpha_t = 0.8\nx_prev = 1.0\nepsilon = 0.5\nx_t = np.sqrt(alpha_t) * x_prev + np.sqrt(1 - alpha_t) * epsilon\nprint(round(float(x_t), 2))",
        "expectedStdout": "1.12",
        "blankAnswers": [],
        "referenceSolution": "",
        "hiddenTests": "",
        "packages": [
          "numpy"
        ]
      },
      {
        "kind": "code_blank",
        "topic": "확산 모델 순방향 계산식",
        "prompt": "확산 모델의 순방향 과정 수식에 맞도록 빈칸을 채우세요. 이전 이미지 값과 가우시안 노이즈를 alpha_t 비율로 결합해야 합니다.",
        "sourceFiles": [
          "04_image_generation/01_stable_diffusion.ipynb"
        ],
        "explanation": "수업 자료의 순방향 수식은 이전 값에 √alpha_t를 곱한 항과 노이즈에 √(1-alpha_t)를 곱한 항의 합입니다. alpha_t가 1이면 노이즈 항이 0이 되고, alpha_t가 0이면 노이즈만 남습니다.",
        "choices": [],
        "answerIndex": null,
        "starterCode": "import numpy as np\n\ndef forward_step(x_prev, alpha_t, epsilon):\n    \"\"\"확산 순방향 과정에서 한 단계의 x_t를 계산한다.\"\"\"\n    return __1__",
        "expectedStdout": "",
        "blankAnswers": [
          "np.sqrt(alpha_t) * x_prev + np.sqrt(1 - alpha_t) * epsilon"
        ],
        "referenceSolution": "import numpy as np\n\ndef forward_step(x_prev, alpha_t, epsilon):\n    \"\"\"확산 순방향 과정에서 한 단계의 x_t를 계산한다.\"\"\"\n    return np.sqrt(alpha_t) * x_prev + np.sqrt(1 - alpha_t) * epsilon",
        "hiddenTests": "assert round(float(forward_step(1.0, 0.8, 0.5)), 6) == round(1.118033988749895, 6)\nassert forward_step(2.0, 1.0, 10.0) == 2.0\nassert round(float(forward_step(0.0, 0.0, 3.0)), 6) == 3.0",
        "packages": [
          "numpy"
        ]
      },
      {
        "kind": "code_fix",
        "topic": "ITM 매칭 결과 판정",
        "prompt": "ITM 로짓의 순서는 [not_matched, matched]입니다. 다음 함수는 매칭된 입력을 'Not matched'로 판정하는 증상이 있습니다. 잘못된 비교를 하나만 고쳐서 수정하세요.",
        "sourceFiles": [
          "03_vision_language_model/02_BLIP.ipynb"
        ],
        "explanation": "ITM 출력은 [not_matched, matched] 순서이므로 두 번째 값인 itm_scores[1]이 더 클 때 매칭으로 판정해야 합니다. 두 값이 같을 때는 matched가 아니므로 'Not matched'가 됩니다.",
        "choices": [],
        "answerIndex": null,
        "starterCode": "def get_match_label(itm_scores):\n    # itm_scores 순서: [not_matched, matched]\n    return 'Matched' if itm_scores[0] > itm_scores[1] else 'Not matched'",
        "expectedStdout": "",
        "blankAnswers": [],
        "referenceSolution": "def get_match_label(itm_scores):\n    # itm_scores 순서: [not_matched, matched]\n    return 'Matched' if itm_scores[1] > itm_scores[0] else 'Not matched'",
        "hiddenTests": "assert get_match_label([0.2, 0.8]) == 'Matched'\nassert get_match_label([0.9, 0.1]) == 'Not matched'\nassert get_match_label([0.5, 0.5]) == 'Not matched'",
        "packages": []
      },
      {
        "kind": "code_write",
        "topic": "이미지 ID로 질문 조회",
        "prompt": "질문 데이터에서 주어진 image_id와 일치하는 질문만 찾아 question_id와 question 필드로 구성된 리스트를 반환하는 함수를 작성하세요. 일치하는 질문이 없으면 빈 리스트를 반환해야 합니다.",
        "sourceFiles": [
          "03_vision_language_model/03_Llama3.2_vision_vqa.ipynb"
        ],
        "explanation": "수업의 헬퍼 함수는 data에서 questions 목록을 가져온 뒤 image_id가 일치하는 항목만 남깁니다. 반환할 때는 각 항목에서 question_id와 question만 골라내며, 일치 항목이 없으면 리스트 컴프리헨션 결과가 빈 리스트가 됩니다.",
        "choices": [],
        "answerIndex": null,
        "starterCode": "def get_questions_by_image_id(data, image_id):\n    \"\"\"image_id에 해당하는 질문 목록을 반환한다.\"\"\"\n    pass",
        "expectedStdout": "",
        "blankAnswers": [],
        "referenceSolution": "def get_questions_by_image_id(data, image_id):\n    \"\"\"image_id에 해당하는 질문 목록을 반환한다.\"\"\"\n    questions = data.get('questions', [])\n    return [\n        {\n            'question_id': q['question_id'],\n            'question': q['question']\n        }\n        for q in questions\n        if q.get('image_id') == image_id\n    ]",
        "hiddenTests": "sample = {'questions': [{'question_id': 1, 'image_id': 10, 'question': '무엇이 있나요?'}, {'question_id': 2, 'image_id': 20, 'question': '몇 개인가요?'}, {'question_id': 3, 'image_id': 10, 'question': '색은 무엇인가요?'}]}\nassert get_questions_by_image_id(sample, 10) == [{'question_id': 1, 'question': '무엇이 있나요?'}, {'question_id': 3, 'question': '색은 무엇인가요?'}]\nassert get_questions_by_image_id(sample, 20) == [{'question_id': 2, 'question': '몇 개인가요?'}]\nassert get_questions_by_image_id(sample, 99) == []",
        "packages": []
      }
    ]
  },
  {
    "id": "ps-mm-0915",
    "sourceTitle": "multimodal",
    "lessonDate": "2026-09-15",
    "dayLabel": "멀티모달 3일차",
    "title": "영상 RAG — 프레임 추출 · 캡션 · 검색",
    "files": [
      "05_multimodal_rag/02_video_rag_frame_extraction.ipynb",
      "05_multimodal_rag/03_video_rag_image_caption.ipynb",
      "05_multimodal_rag/04_video_rag_indexing.ipynb",
      "05_multimodal_rag/05_video_rag_retrieval_generation.ipynb"
    ],
    "model": "gpt-5.6-luna",
    "problems": [
      {
        "kind": "concept",
        "topic": "OpenCV와 PIL의 색상 채널 순서",
        "prompt": "OpenCV로 읽은 컬러 이미지 배열을 PIL Image로 변환하기 전에 수행해야 하는 작업은 무엇인가요?",
        "sourceFiles": [
          "05_multimodal_rag/02_video_rag_frame_extraction.ipynb"
        ],
        "explanation": "OpenCV는 기본적으로 컬러 이미지를 BGR 순서로 다룹니다. PIL Image는 RGB 순서를 사용하므로, `cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)`로 변환한 뒤 `Image.fromarray()`를 사용해야 색상이 올바르게 표시됩니다.",
        "choices": [
          "BGR에서 RGB로 색상 채널 순서를 변환한다.",
          "RGB에서 BGR로 색상 채널 순서를 변환한다.",
          "이미지 배열의 프레임 수를 계산한다.",
          "이미지를 Base64 문자열로 인코딩한다."
        ],
        "answerIndex": 0,
        "starterCode": "",
        "expectedStdout": "",
        "blankAnswers": [],
        "referenceSolution": "",
        "hiddenTests": "",
        "packages": []
      },
      {
        "kind": "concept",
        "topic": "Video RAG의 검색 및 생성 흐름",
        "prompt": "Video RAG에서 사용자의 질문에 답하기까지의 흐름으로 가장 알맞은 것은 무엇인가요?",
        "sourceFiles": [
          "05_multimodal_rag/04_video_rag_indexing.ipynb",
          "05_multimodal_rag/05_video_rag_retrieval_generation.ipynb"
        ],
        "explanation": "검색 단계에서는 `vector_store.similarity_search()`로 질문과 유사한 문서를 찾습니다. 이후 `build_context()`로 검색 결과를 문자열로 합치고, 질문과 context를 체인에 전달하여 구조화된 답변을 생성합니다.",
        "choices": [
          "질문을 벡터 검색하고, 검색 결과를 context로 구성한 뒤, LLM 체인에 전달한다.",
          "질문을 바로 이미지 파일로 저장한 뒤, 파일명을 LLM에 전달한다.",
          "모든 동영상 프레임을 먼저 하나의 이미지로 합친 뒤, 파일 크기만 비교한다.",
          "검색 결과를 사용하지 않고 항상 미리 정해진 답변을 출력한다."
        ],
        "answerIndex": 0,
        "starterCode": "",
        "expectedStdout": "",
        "blankAnswers": [],
        "referenceSolution": "",
        "hiddenTests": "",
        "packages": []
      },
      {
        "kind": "code_output",
        "topic": "프레임 간격에 따른 추출 개수",
        "prompt": "동영상의 프레임 인덱스가 0부터 9까지이고, 3프레임마다 한 장씩 저장한다고 할 때 다음 코드의 출력을 쓰세요.",
        "sourceFiles": [
          "05_multimodal_rag/02_video_rag_frame_extraction.ipynb"
        ],
        "explanation": "저장되는 프레임 인덱스는 0, 3, 6, 9입니다. 따라서 저장 개수는 4개이고, 마지막으로 저장되는 인덱스는 9입니다.",
        "choices": [],
        "answerIndex": null,
        "starterCode": "frame_count = 10\nframe_interval = 3\nsaved = [idx for idx in range(frame_count) if idx % frame_interval == 0]\nprint(len(saved))\nprint(saved[-1])",
        "expectedStdout": "4\n9",
        "blankAnswers": [],
        "referenceSolution": "",
        "hiddenTests": "",
        "packages": []
      },
      {
        "kind": "code_blank",
        "topic": "정규식으로 프레임 번호 추출",
        "prompt": "프레임 파일명에서 `_frame` 뒤의 숫자를 추출하고 `.jpg`로 끝나는지 확인하도록 빈칸을 채우세요.",
        "sourceFiles": [
          "05_multimodal_rag/03_video_rag_image_caption.ipynb"
        ],
        "explanation": "정규식의 `\\d+`는 하나 이상의 숫자를 의미하고, 괄호로 감싼 부분은 캡처 그룹이 됩니다. 따라서 `match.group(1)`로 프레임 번호 문자열을 얻은 뒤 `int()`로 정수로 변환합니다.",
        "choices": [],
        "answerIndex": null,
        "starterCode": "import re\n\ndef extract_frame_no(frame_file):\n    match = re.search(__1__, frame_file)\n    return int(match.group(1))\n\nprint(extract_frame_no('alpinist_frame00300.jpg'))",
        "expectedStdout": "",
        "blankAnswers": [
          "r'_frame(\\d+)\\.jpg'"
        ],
        "referenceSolution": "import re\n\ndef extract_frame_no(frame_file):\n    match = re.search(r'_frame(\\d+)\\.jpg', frame_file)\n    return int(match.group(1))\n\nprint(extract_frame_no('alpinist_frame00300.jpg'))",
        "hiddenTests": "assert extract_frame_no('skiing_frame00030.jpg') == 30\nassert extract_frame_no('alpinist_frame00300.jpg') == 300\nassert extract_frame_no('video_frame7.jpg') == 7",
        "packages": []
      },
      {
        "kind": "code_fix",
        "topic": "프레임 파일명의 0 패딩",
        "prompt": "검색 결과의 프레임 번호가 300일 때 실제 파일명은 `skiing_frame00300.jpg`이어야 합니다. 하지만 현재 코드는 `skiing_frame0300.jpg`를 만들어 파일을 찾지 못합니다. 파일명의 프레임 번호 서식 지정자를 수정하세요.",
        "sourceFiles": [
          "05_multimodal_rag/04_video_rag_indexing.ipynb",
          "05_multimodal_rag/05_video_rag_retrieval_generation.ipynb"
        ],
        "explanation": "프레임 번호는 5자리 폭으로 지정하고 부족한 자리는 0으로 채워야 합니다. 따라서 `:04d`를 `:05d`로 바꾸면 300이 `00300`으로 표현됩니다. 파일 확장자 제거는 표준 문자열 메서드만 사용했습니다.",
        "choices": [],
        "answerIndex": null,
        "starterCode": "def get_frame_filename(video_filename, frame_no):\n    video_basename = video_filename.rsplit('.', 1)[0]\n    return f'{video_basename}_frame{int(frame_no):04d}.jpg'\n\nprint(get_frame_filename('skiing.mp4', 300))",
        "expectedStdout": "",
        "blankAnswers": [],
        "referenceSolution": "def get_frame_filename(video_filename, frame_no):\n    video_basename = video_filename.rsplit('.', 1)[0]\n    return f'{video_basename}_frame{int(frame_no):05d}.jpg'\n\nprint(get_frame_filename('skiing.mp4', 300))",
        "hiddenTests": "assert get_frame_filename('skiing.mp4', 300) == 'skiing_frame00300.jpg'\nassert get_frame_filename('alpinist.mp4', 0) == 'alpinist_frame00000.jpg'\nassert get_frame_filename('skiing.mp4', 30) == 'skiing_frame00030.jpg'",
        "packages": []
      },
      {
        "kind": "code_write",
        "topic": "비디오 메타데이터로 프레임 이미지 경로 구성",
        "prompt": "비디오 파일명과 프레임 번호를 이용해 프레임 이미지의 전체 경로를 반환하는 함수를 작성하세요. 비디오 확장자를 제거하고, 프레임 번호는 정수로 변환한 뒤 5자리 0 패딩을 적용해야 합니다. 경로는 `base_path/frame_dir/비디오이름/파일명` 순서로 구성합니다.",
        "sourceFiles": [
          "05_multimodal_rag/05_video_rag_retrieval_generation.ipynb"
        ],
        "explanation": "확장자는 문자열의 마지막 점을 기준으로 제거하고, 프레임 번호는 `int(float(...))`으로 정수화합니다. 이후 5자리 0 패딩 파일명을 만든 뒤 각 경로 요소를 `/`로 연결합니다. 파일 시스템 모듈 없이도 주어진 POSIX 경로 형식을 구성할 수 있습니다.",
        "choices": [],
        "answerIndex": null,
        "starterCode": "def get_frame_image_path(video_filename, frame_no, base_path='/data', frame_dir='frames'):\n    \"\"\"비디오 메타데이터로 프레임 이미지의 전체 경로를 반환한다.\"\"\"\n    pass",
        "expectedStdout": "",
        "blankAnswers": [],
        "referenceSolution": "def get_frame_image_path(video_filename, frame_no, base_path='/data', frame_dir='frames'):\n    \"\"\"비디오 메타데이터로 프레임 이미지의 전체 경로를 반환한다.\"\"\"\n    video_basename = video_filename.rsplit('.', 1)[0]\n    frame_no = int(float(frame_no))\n    filename = f'{video_basename}_frame{frame_no:05d}.jpg'\n    return f'{base_path.rstrip(\"/\")}/{frame_dir}/{video_basename}/{filename}'",
        "hiddenTests": "assert get_frame_image_path('skiing.mp4', 30) == '/data/frames/skiing/skiing_frame00030.jpg'\nassert get_frame_image_path('alpinist.mp4', '300.0') == '/data/frames/alpinist/alpinist_frame00300.jpg'\nassert get_frame_image_path('skiing.mp4', 0, base_path='/videos') == '/videos/frames/skiing/skiing_frame00000.jpg'",
        "packages": []
      }
    ]
  }
];

export const seedPracticeSets: PracticeSet[] = sets.map((s) => ({ ...s, cohortId: DemoConfig.cohortId }));
