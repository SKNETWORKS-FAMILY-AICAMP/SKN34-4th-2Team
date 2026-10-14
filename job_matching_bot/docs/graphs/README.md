# 구조 그래프 원본

노션 "채용공고 추천봇 그래프" 페이지에 올린 그림의 Mermaid 원본이다. 구조가 바뀌면
여기서 고치고 다시 렌더해 노션 이미지를 교체한다.

```powershell
cd job_matching_bot/docs/graphs
foreach ($f in Get-ChildItem *.mmd) { npx -y @mermaid-js/mermaid-cli -i $f.Name -o ($f.BaseName + ".png") -b white -s 3 -w 1600 }
```

| 파일 | 그림 |
|---|---|
| `1_overview.mmd` | 전체 구조 — 적재 · 추천 · 첨삭 |
| `2_ingest.mmd` | 적재 파이프라인 — 공식 API / 크롤링 |
| `3_nightly.mmd` | 야간 배치 |
| `4_recommend.mmd` | 추천 5단계 |
| `5_handoff.mmd` | 추천 → 첨삭 |
