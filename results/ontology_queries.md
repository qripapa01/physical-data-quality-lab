# 온톨로지 질의 결과

## Q1_verdict_by_machine: 기기·도메인별로 파일 수와 FAIL/WARN 수는?

```sparql
SELECT ?machine ?domain (COUNT(?obs) AS ?files)
       (SUM(IF(?v = "FAIL", 1, 0)) AS ?fail) (SUM(IF(?v = "WARN", 1, 0)) AS ?warn)
WHERE {
  ?obs a pdq:AudioRecording ; sosa:hasFeatureOfInterest ?m ; pdq:verdict ?v .
  ?m rdfs:label ?machine .
  OPTIONAL { ?obs pdq:domain ?d }
  BIND(COALESCE(?d, "unknown") AS ?domain)
}
GROUP BY ?machine ?domain ORDER BY ?machine ?domain
```

| machine   | domain   |   files |   fail |   warn |
|:----------|:---------|--------:|-------:|-------:|
| fan       | source   |      60 |      2 |      0 |
| fan       | target   |      24 |      0 |      0 |
| pump      | source   |      60 |      1 |      0 |
| pump      | target   |      24 |      0 |      0 |
| valve     | source   |      60 |      0 |      4 |
| valve     | target   |      24 |      1 |      0 |


## Q2_issues_by_dimension: 품질 차원(완전성/정확성/일관성/유일성)과 규칙별 이슈 수는? (규칙→지표→차원 관계를 따라감)

```sparql
SELECT ?dimension ?rule (COUNT(?issue) AS ?issues)
WHERE {
  ?obs pdq:hasIssue ?issue .
  ?issue pdq:violatesRule ?r .
  ?r rdfs:label ?rule ; pdq:checksMetric ?metric .
  ?metric dqv:inDimension ?dim .
  ?dim rdfs:label ?dimension .
  FILTER(lang(?dimension) = "ko")
}
GROUP BY ?dimension ?rule ORDER BY DESC(?issues)
```

| dimension   | rule                 |   issues |
|:------------|:---------------------|---------:|
| 정확성         | 같은 기기·도메인 대비 통계적 이상치 |        9 |
| 정확성         | 클리핑                  |        1 |
| 정확성         | DC 오프셋               |        1 |
| 유일성         | 내용이 같은 중복 파일         |        1 |
| 완전성         | 끊김/정지 구간             |        1 |
| 일관성         | 샘플링레이트 불일치           |        1 |


## Q3_clipping_over_threshold: 클리핑 비율이 기준(0.001)을 넘는 녹음과 그 기계는?

```sparql
SELECT ?file ?machine ?clip_ratio
WHERE {
  ?mm dqv:isMeasurementOf pdq:clip_ratio ; dqv:computedOn ?obs ; dqv:value ?clip_ratio .
  FILTER(?clip_ratio > 0.001)
  ?obs pdq:filePath ?file ; sosa:hasFeatureOfInterest ?m .
  ?m rdfs:label ?machine .
}
ORDER BY DESC(?clip_ratio) LIMIT 20
```

| file                                                             | machine   |   clip_ratio |
|:-----------------------------------------------------------------|:----------|-------------:|
| data\demo\fan\train\section_00_source_train_normal_0003_demo.wav | fan       |     0.615708 |


## Q4_fail_trace: FAIL 판정을 받은 파일과 그 근거(규칙, 측정 설명)는? (추적성)

```sparql
SELECT ?file ?machine ?rule ?message
WHERE {
  ?obs pdq:hasIssue ?issue ; pdq:filePath ?file ; sosa:hasFeatureOfInterest ?m .
  ?m rdfs:label ?machine .
  ?issue pdq:severity "FAIL" ; pdq:violatesRule ?r ; pdq:message ?message .
  ?r rdfs:label ?rule .
}
ORDER BY ?machine ?file LIMIT 30
```

| file                                                              | machine   | rule         | message                                             |
|:------------------------------------------------------------------|:----------|:-------------|:----------------------------------------------------|
| data\demo\fan\test\section_00_source_test_normal_0007_demo.wav    | fan       | 샘플링레이트 불일치   | 8000 Hz != 16000 Hz                                 |
| data\demo\fan\train\section_00_source_train_normal_0003_demo.wav  | fan       | 클리핑          | 0.6157 > 0.01                                       |
| data\demo\pump\train\section_00_source_train_normal_0005_demo.wav | pump      | 끊김/정지 구간     | 300ms > 100.0ms                                     |
| data\demo\valve\test\section_00_target_test_normal_0002_demo.wav  | valve     | 내용이 같은 중복 파일 | section_00_target_test_normal_0001_demo.wav 와 내용 동일 |

