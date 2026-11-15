# 자연어 질문 -> SPARQL 결과

정확도: 10/10 (manual)

## Q01 [정답] 전체 녹음 파일은 몇 개인가?

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX dqv:  <http://www.w3.org/ns/dqv#>
PREFIX pdq:  <https://github.com/qripapa01/physical-data-quality-lab/ontology#>
SELECT (COUNT(DISTINCT ?obs) AS ?n) WHERE {
  ?obs a pdq:AudioRecording .
}
```

- LLM 결과: [[252]]
- 정답: [[252]]

## Q02 [정답] FAIL 판정을 받은 녹음 파일은 몇 개인가?

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX dqv:  <http://www.w3.org/ns/dqv#>
PREFIX pdq:  <https://github.com/qripapa01/physical-data-quality-lab/ontology#>
SELECT (COUNT(DISTINCT ?obs) AS ?n) WHERE {
  ?obs a pdq:AudioRecording ;
       pdq:verdict "FAIL" .
}
```

- LLM 결과: [[4]]
- 정답: [[4]]

## Q03 [정답] 기계별로 FAIL 판정 파일이 몇 개씩 있는가? (FAIL이 있는 기계만)

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX dqv:  <http://www.w3.org/ns/dqv#>
PREFIX pdq:  <https://github.com/qripapa01/physical-data-quality-lab/ontology#>
SELECT ?machine (COUNT(DISTINCT ?obs) AS ?n) WHERE {
  ?obs a pdq:AudioRecording ;
       pdq:verdict "FAIL" ;
       sosa:hasFeatureOfInterest ?m .
  ?m rdfs:label ?machine .
}
GROUP BY ?machine
ORDER BY DESC(?n)
```

- LLM 결과: [['fan', 2], ['valve', 1], ['pump', 1]]
- 정답: [['fan', 2], ['valve', 1], ['pump', 1]]

## Q04 [정답] 클리핑 비율이 가장 높은 녹음 파일 1개의 경로와 그 클리핑 비율은?

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX dqv:  <http://www.w3.org/ns/dqv#>
PREFIX pdq:  <https://github.com/qripapa01/physical-data-quality-lab/ontology#>
SELECT ?path ?clipRatio WHERE {
  ?obs a pdq:AudioRecording ;
       pdq:filePath ?path .
  ?mm dqv:computedOn ?obs ;
      dqv:isMeasurementOf pdq:clip_ratio ;
      dqv:value ?clipRatio .
}
ORDER BY DESC(?clipRatio)
LIMIT 1
```

- LLM 결과: [['data\\demo\\fan\\train\\section_00_source_train_normal_0003_demo.wav', 0.6157083]]
- 정답: [['data\\demo\\fan\\train\\section_00_source_train_normal_0003_demo.wav', 0.6157083]]

## Q05 [정답] 정확성 품질 차원에 속하는 문제 기록은 모두 몇 건인가?

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX dqv:  <http://www.w3.org/ns/dqv#>
PREFIX pdq:  <https://github.com/qripapa01/physical-data-quality-lab/ontology#>
SELECT (COUNT(DISTINCT ?issue) AS ?n) WHERE {
  ?issue a pdq:QualityIssue ;
         pdq:violatesRule ?rule .
  ?rule pdq:checksMetric ?metric .
  ?metric dqv:inDimension pdq:Accuracy .
}
```

- LLM 결과: [[11]]
- 정답: [[11]]

## Q06 [정답] 가장 많이 위반된 품질 규칙의 이름과 위반 건수는?

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX dqv:  <http://www.w3.org/ns/dqv#>
PREFIX pdq:  <https://github.com/qripapa01/physical-data-quality-lab/ontology#>
SELECT ?ruleName (COUNT(DISTINCT ?issue) AS ?n) WHERE {
  ?issue a pdq:QualityIssue ;
         pdq:violatesRule ?rule .
  ?rule rdfs:label ?ruleName .
  FILTER(LANG(?ruleName) = "ko")
}
GROUP BY ?ruleName
ORDER BY DESC(?n)
LIMIT 1
```

- LLM 결과: [['같은 기기·도메인 대비 통계적 이상치', 9]]
- 정답: [['같은 기기·도메인 대비 통계적 이상치', 9]]

## Q07 [정답] 이상(anomaly) 라벨이 붙은 녹음 파일 중 품질 문제 기록이 하나라도 있는 파일은 몇 개인가?

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX dqv:  <http://www.w3.org/ns/dqv#>
PREFIX pdq:  <https://github.com/qripapa01/physical-data-quality-lab/ontology#>
SELECT (COUNT(DISTINCT ?obs) AS ?n) WHERE {
  ?obs a pdq:AudioRecording ;
       pdq:label "anomaly" ;
       pdq:hasIssue ?issue .
}
```

- LLM 결과: [[4]]
- 정답: [[4]]

## Q08 [정답] 샘플링레이트가 16000Hz가 아닌 녹음 파일의 경로는?

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX dqv:  <http://www.w3.org/ns/dqv#>
PREFIX pdq:  <https://github.com/qripapa01/physical-data-quality-lab/ontology#>
SELECT DISTINCT ?path WHERE {
  ?obs a pdq:AudioRecording ;
       pdq:filePath ?path .
  ?mm dqv:computedOn ?obs ;
      dqv:isMeasurementOf pdq:sample_rate ;
      dqv:value ?sr .
  FILTER(?sr != 16000)
}
```

- LLM 결과: [['data\\demo\\fan\\test\\section_00_source_test_normal_0007_demo.wav']]
- 정답: [['data\\demo\\fan\\test\\section_00_source_test_normal_0007_demo.wav']]

## Q09 [정답] pump 기계의 녹음 파일 중 판정이 PASS가 아닌 파일의 경로와 판정은?

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX dqv:  <http://www.w3.org/ns/dqv#>
PREFIX pdq:  <https://github.com/qripapa01/physical-data-quality-lab/ontology#>
SELECT ?path ?verdict WHERE {
  ?obs a pdq:AudioRecording ;
       sosa:hasFeatureOfInterest ?m ;
       pdq:filePath ?path ;
       pdq:verdict ?verdict .
  ?m rdfs:label "pump" .
  FILTER(?verdict != "PASS")
}
```

- LLM 결과: [['data\\demo\\pump\\train\\section_00_source_train_normal_0005_demo.wav', 'FAIL']]
- 정답: [['data\\demo\\pump\\train\\section_00_source_train_normal_0005_demo.wav', 'FAIL']]

## Q10 [정답] train 폴더의 normal 0003번 fan 파일은 어떤 규칙을 위반했는가? 규칙 이름과 심각도를 알려줘.

```sparql
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX dqv:  <http://www.w3.org/ns/dqv#>
PREFIX pdq:  <https://github.com/qripapa01/physical-data-quality-lab/ontology#>
SELECT ?ruleName ?severity WHERE {
  ?obs a pdq:AudioRecording ;
       sosa:hasFeatureOfInterest ?m ;
       pdq:split "train" ;
       pdq:label "normal" ;
       pdq:filePath ?path ;
       pdq:hasIssue ?issue .
  ?m rdfs:label "fan" .
  FILTER(CONTAINS(?path, "normal_0003"))
  ?issue pdq:violatesRule ?rule ;
         pdq:severity ?severity .
  ?rule rdfs:label ?ruleName .
  FILTER(LANG(?ruleName) = "ko")
}
```

- LLM 결과: [['클리핑', 'FAIL'], ['DC 오프셋', 'WARN'], ['같은 기기·도메인 대비 통계적 이상치', 'WARN'], ['같은 기기·도메인 대비 통계적 이상치', 'WARN'], ['같은 기기·도메인 대비 통계적 이상치', 'WARN']]
- 정답: [['클리핑', 'FAIL'], ['DC 오프셋', 'WARN'], ['같은 기기·도메인 대비 통계적 이상치', 'WARN'], ['같은 기기·도메인 대비 통계적 이상치', 'WARN'], ['같은 기기·도메인 대비 통계적 이상치', 'WARN']]
