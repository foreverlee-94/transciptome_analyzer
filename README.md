# Lung Metadata Explorer

로컬에 있는 대용량 단일세포 h5ad 데이터셋들의 메타데이터를 읽어서, 브라우저에서
검색/정렬/필터할 수 있는 정적 HTML 리포트로 만들어주는 도구입니다.

## 다루는 데이터

| 컬렉션 | 경로 | 파일 수 | 비고 |
|---|---|---|---|
| CZI CELLxGENE 폐(Lung) 데이터셋 | `D:\CZI-CellXGene-Lung-datasets` | 120개 h5ad | 표준 CELLxGENE 스키마 (disease/tissue/assay/cell_type 등) |
| Tahoe-100M 약물 처리 스크린 | `D:\tahoe-100m-dataset` | 14개 plate h5ad | 세포주 50종 × 약물 스크리닝 (drug/cell_line/plate 등) |

두 컬렉션은 스키마가 완전히 달라서 리포트 안에서 탭으로 분리되어 있습니다.

## 핵심 설계: 발현행렬은 절대 읽지 않는다

h5ad는 HDF5 컨테이너입니다. 이 프로젝트는 `h5py`로 파일을 열어 `obs`/`var`/`uns`
안의 가벼운 데이터셋(카테고리 목록, 스칼라 값, shape 속성)만 골라 읽고, 발현행렬
(`X`, `raw.X`)이나 세포별 `BARCODE`처럼 수십억 개 원소를 가진 배열은 절대 열지
않습니다. 그 덕분에 45GB, 심지어 300GB가 넘는 파일도 파일당 0.02~0.3초 만에
메타데이터 추출이 끝납니다.

## 사용법

```bash
uv sync                 # 의존성 설치 (h5py)
uv run python main.py   # metadata.json 추출 + report.html 생성
```

생성된 `report.html`을 브라우저로 열면 됩니다. 인터넷 연결이나 CDN 없이 동작하도록
데이터를 HTML 안에 그대로 임베드했습니다.

- `extract_metadata.py`: 두 컬렉션을 각각 스캔해서 `metadata.json`을 만듭니다.
- `generate_report.py`: `metadata.json`을 읽어 `report.html`(탭 UI)을 만듭니다.

## 리포트 구성

### CZI CELLxGENE 폐(Lung) 탭
- 요약 통계, 검색창, 질환/Assay/Organism 드롭다운 필터, 정렬 가능한 표
- 행 클릭 시 상세 모달(전체 cell type/조직/성별/발달단계/citation 등)

질환/조건 필터는 파일명에서 뽑은 값이 아니라 h5ad 안의 실제 `obs_disease` 값을
씁니다. 파일명 슬러그는 잘려있는 경우가 있어서(예: `small-cell-lung-carc`) 필터에
빈 값/잘린 값이 섞이는 문제가 있었기 때문입니다.

### Tahoe-100M 탭
- Plate(파일) 단위 표: 세포 수, 유전자 수, 약물 수, 세포주 수, 샘플(well) 수,
  QC 통과율 등
- **세포주 참조 테이블**: Tahoe-100M은 plate마다 세포주 50종이 동일하게 풀링되어
  있어서 plate 단위로는 "조직"을 필터링할 수 없습니다. 대신 세포주 단위로 별도
  테이블을 만들고, [Cellosaurus](https://www.cellosaurus.org) API로 조회한 공식
  조직 기원(derived-from-site/disease) 정보를 붙여서 "조직 기원 = lung" 같은
  필터가 실제로 동작하게 했습니다 (50개 중 15개가 폐 유래 세포주).

## 참고

- CZI CELLxGENE Discover: https://cellxgene.cziscience.com
- Tahoe-100M: Vevo Therapeutics / Parse Biosciences 약물 처리 단일세포 스크린
- Cellosaurus: https://www.cellosaurus.org
