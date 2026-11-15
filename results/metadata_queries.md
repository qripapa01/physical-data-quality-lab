# 메타데이터 온톨로지 질의 결과

## E1_rotating_machines
회전 기계(팬·펌프·모터 등)에 해당하는 데이터셋은? (클래스 계층을 따라감: subClassOf*)

```sparql
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX pdq:  <https://github.com/qripapa01/physical-data-quality-lab/ontology#>

SELECT ?dataset ?machineClass WHERE {
  ?ds a pdq:Dataset ; pdq:sourceDocument ?dataset ; pdq:aboutMachine ?m .
  ?m a ?c . ?c rdfs:subClassOf* pdq:RotatingMachine ; rdfs:label ?machineClass .
  FILTER(lang(?machineClass) = "ko")
} ORDER BY ?dataset
```

| dataset   | machineClass   |
|:----------|:---------------|
| D01.txt   | 팬              |
| D02.txt   | 펌프             |
| D04.txt   | 모터             |
| D05.txt   | 베어링            |
| D06.txt   | 컴프레서           |
| D07.txt   | 기어박스           |
| D09.txt   | 팬              |
| D10.txt   | 펌프             |
| D12.txt   | 모터             |

## E2_vibration_datasets
진동을 관측하는 센서를 쓴 데이터셋과 샘플링레이트는?

```sparql
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX pdq:  <https://github.com/qripapa01/physical-data-quality-lab/ontology#>

SELECT ?dataset ?sampleRateHz WHERE {
  ?ds pdq:sourceDocument ?dataset ; pdq:usesSensor ?s .
  ?s sosa:observes pdq:vibration ; pdq:sampleRateHz ?sampleRateHz .
} ORDER BY DESC(?sampleRateHz)
```

| dataset   |   sampleRateHz |
|:----------|---------------:|
| D10.txt   |          51200 |
| D04.txt   |          25600 |
| D05.txt   |          12000 |

## E3_low_rate
샘플링레이트가 10kHz 미만인 데이터셋과 센서 종류는? (저속 신호 확인)

```sparql
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX pdq:  <https://github.com/qripapa01/physical-data-quality-lab/ontology#>

SELECT ?dataset ?sensorClass ?sampleRateHz WHERE {
  ?ds pdq:sourceDocument ?dataset ; pdq:usesSensor ?s .
  ?s pdq:sampleRateHz ?sampleRateHz ; a ?c . ?c rdfs:subClassOf sosa:Sensor ; rdfs:label ?sensorClass .
  FILTER(?sampleRateHz < 10000 && lang(?sensorClass) = "ko")
} ORDER BY ?sampleRateHz
```

| dataset   | sensorClass   |   sampleRateHz |
|:----------|:--------------|---------------:|
| D08.txt   | 온도 센서         |              1 |
| D12.txt   | 전류 센서         |           1000 |

## E4_mismatch
설명서와 실제 데이터가 맞지 않는 데이터셋은?

```sparql
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX sosa: <http://www.w3.org/ns/sosa/>
PREFIX pdq:  <https://github.com/qripapa01/physical-data-quality-lab/ontology#>

SELECT ?dataset ?note WHERE {
  ?ds pdq:sourceDocument ?dataset ; pdq:crossCheckNote ?note .
} ORDER BY ?dataset
```

| dataset   | note                                  |
|:----------|:--------------------------------------|
| D01.txt   | 설명서는 16000Hz 인데 실제 1개 파일은 다름 (8000Hz) |
