# 실습 문제 검증기

공부방 실습 문제를 **학생 브라우저와 같은 Pyodide**로 실행한다. 여기서 통과한 코드는 브라우저에서도 돈다.

「코드를 받아 돌리고 결과를 돌려준다」만 한다. 무엇이 통과인지는 `study_notes/practice/verify.py`가 정한다.

```powershell
cd practice_verifier
npm install        # pyodide 314.0.7 고정. 브라우저도 같은 버전을 써야 한다
npm test
```

## 주고받는 것

```jsonc
// 표준입력
{"jobs": [{"id": "p0:run1", "steps": ["def f(): ...", "assert f() == 1"], "timeoutMs": 3000}]}
// 표준출력
{"version": "314.0.7", "results": [{"id": "p0:run1", "ok": false, "stdout": "",
  "error": {"type": "AssertionError", "message": "", "step": 1}, "timedOut": false, "ms": 2}]}
```

`steps`는 같은 변수 공간에서 이어서 돈다(학생 코드 → 숨긴 테스트). 작업마다 변수 공간은 새로 만든다.

## 막아 둔 것

| 무엇 | 어떻게 |
|---|---|
| 무한 루프 | 실행 시작부터 시간을 재고, 넘기면 워커를 `terminate` 하고 새로 띄운다 |
| JS·Node로 나가기 | `js`, `pyodide`, `pyodide_js`, `micropip` import 차단 |
| `input()` | 표준입력을 오류로 둔다 |
| 출력 폭주 | 2만 자에서 자른다 |

**메모리와 네트워크는 막지 않았다.** 패키지(numpy·pandas)를 처음 쓸 때 CDN에서 받기 때문이다. 지금은 우리 LLM이 만든 코드만 돌리므로 이 정도로 둔다. Docker로 옮길 때 컨테이너에서 메모리 제한을 걸고, 패키지를 이미지에 미리 받아 둔 뒤 네트워크를 끊는다.
