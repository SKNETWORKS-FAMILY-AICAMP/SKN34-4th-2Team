# 학생 챗봇 평가

`eval_cases.json`과 `hard_eval_cases.json`은 과거 Luna 실험에서 만든
supervisor 분류 회귀 사례다. 기대값은 당시 동작을 기록한 것이므로 새 모델이나
정책을 적용할 때 실패 사례를 검토하고, 기대값을 무조건 정답으로 간주하지 않는다.

현재 운영 supervisor에 대한 실제 모델 평가:

```powershell
python -m chatbot.evaluation.evaluate_supervisor
python -m chatbot.evaluation.evaluate_supervisor --cases chatbot/evaluation/hard_eval_cases.json
```

실행 시 OpenAI API 호출과 비용이 발생한다. 기본 실행은 외부 DB에 쓰지 않으며
사례별 결과와 지연 시간을 화면에 출력한다. `--output`을 지정한 경우에만
지정한 로컬 JSON 파일을 생성한다. 운영 엔드포인트와 독립적으로 supervisor의
프롬프트·라우팅만 평가하므로 챗봇 E2E 검증을 대신하지 않는다.
