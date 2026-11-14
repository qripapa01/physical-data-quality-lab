# 물리 데이터 품질 점검 보고서 (초안)

- 작성일: 2026-11-14
- 작성 방식: template (판정은 규칙 기반 코드, 문장은 템플릿)
- 상태: 초안 - 담당 연구원 검토·승인 필요

## 1. 점검 개요
- 대상: 252개 파일, 기기 3종 (fan, pump, valve)
- 샘플링레이트: 8000, 16000 Hz
- 판정: PASS 244, WARN 4, FAIL 4

## 2. 주요 발견
- 샘플링레이트 불일치 (FAIL): 1건
- 클리핑 (FAIL): 1건
- DC 오프셋 (WARN): 1건
- 끊김/정지 구간 (FAIL): 1건
- 내용이 같은 중복 파일 (FAIL): 1건
- 같은 기기·도메인 대비 통계적 이상치 (WARN): 9건

## 3. 원인 추정
- section_00_source_test_normal_0007_demo.wav (fan): 샘플링레이트 불일치 - 8000 Hz != 16000 Hz (원인은 수집 장비·저장 과정 확인 필요)
- section_00_source_train_normal_0003_demo.wav (fan): 클리핑 - 0.6157 > 0.01 (원인은 수집 장비·저장 과정 확인 필요)
- section_00_source_train_normal_0005_demo.wav (pump): 끊김/정지 구간 - 300ms > 100.0ms (원인은 수집 장비·저장 과정 확인 필요)
- section_00_target_test_normal_0002_demo.wav (valve): 내용이 같은 중복 파일 - section_00_target_test_normal_0001_demo.wav 와 내용 동일 (원인은 수집 장비·저장 과정 확인 필요)
- section_00_source_train_normal_0003_demo.wav (fan): DC 오프셋 - 0.02214 > 0.01 (원인은 수집 장비·저장 과정 확인 필요)
- section_00_source_train_normal_0003_demo.wav (fan): 같은 기기·도메인 대비 통계적 이상치 - rms_dbfs robust z = 14.7 (원인은 수집 장비·저장 과정 확인 필요)

## 4. 조치 권고
- FAIL 파일은 학습 데이터에서 제외하고 원천 기관에 재수집을 요청함
- WARN 파일은 담당 연구원이 청취·파형 확인 후 사용 여부를 결정함

## 5. 한계와 다음 단계
- 기준값은 예시값이며 센서·용도별로 전문가 검토가 필요함
- 추정 SNR은 비교용 지표로 절대값이 아님
- 통계적 이상치 경고 9건 중 4건은 '이상(anomaly)' 라벨 파일임. 데이터 결함이 아니라 실제 고장음일 수 있으므로 제외하지 말고 사람이 구분해야 함

## 부록. 숫자 자동 대조 결과
- 보고서의 모든 숫자가 요약 데이터와 일치함
