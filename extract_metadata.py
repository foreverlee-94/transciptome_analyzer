"""
여러 단일세포 h5ad 컬렉션의 메타데이터를 추출한다.

- CZI CELLxGENE 폐(lung) 데이터셋 (D:\\CZI-CellXGene-Lung-datasets, 표준 CELLxGENE 스키마)
- Tahoe-100M 약물 처리 스크린 (D:\\tahoe-100m-dataset, 세포주+약물 스키마)

핵심 설계 원칙: h5ad는 HDF5 컨테이너이므로, 발현행렬(X/raw.X)이나 세포별 바코드처럼
거대한 배열은 전혀 읽지 않고 obs/var/uns 안의 "가벼운" 데이터셋(카테고리 목록, 스칼라 값,
shape 속성)만 h5py로 직접 읽는다. 이렇게 하면 수십 GB짜리 파일도 metadata 추출은
수 초 내로 끝난다.
"""

from __future__ import annotations

import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

import h5py

CZI_DATA_DIR = Path(r"D:\CZI-CellXGene-Lung-datasets")
TAHOE_DATA_DIR = Path(r"D:\tahoe-100m-dataset")
OUTPUT_JSON = Path(__file__).parent / "metadata.json"

# --- CZI CELLxGENE 표준 스키마에서 관심있는 obs 카테고리형 컬럼들 ---
CZI_CATEGORICAL_OBS_COLUMNS = [
    "disease",
    "tissue",
    "tissue_type",
    "assay",
    "cell_type",
    "sex",
    "self_reported_ethnicity",
    "development_stage",
    "suspension_type",
    "donor_id",
]

CZI_UNS_SCALAR_FIELDS = [
    "title",
    "schema_version",
    "schema_reference",
    "citation",
    "organism",
    "default_embedding",
]

CZI_FILENAME_RE = re.compile(
    r"^(?P<disease>.+?)__(?P<title>.+)__(?P<uuid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\.h5ad$"
)

# --- Tahoe-100M 스키마 (약물 처리 스크린, obs_metadata_descriptions.tsv 기준) ---
# BARCODE / BARCODE_SUB_LIB_ID 는 세포당 고유 식별자라 카테고리 수가 n_cells에
# 육박해 일부러 제외한다 (읽어봤자 리뷰에 무의미하고 느려짐).
TAHOE_CATEGORICAL_OBS_COLUMNS = [
    "drug",
    "drugname_drugconc",
    "cell_line",
    "cell_name",
    "sample",
    "sublibrary",
    "plate",
    "pass_filter",
    "phase",
]

TAHOE_FILENAME_RE = re.compile(r"plate(?P<plate_num>\d+)", re.IGNORECASE)


def decode(value):
    """h5py에서 나온 bytes/np.bytes_ 값을 str로, numpy 스칼라를 파이썬 타입으로 변환."""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "item"):
        return value.item()
    return value


def read_categories(obs_group: h5py.Group, column: str) -> list[str] | None:
    """categorical 컬럼의 categories 배열만 읽는다 (codes 배열은 읽지 않음 -> 저비용)."""
    if column not in obs_group:
        return None
    node = obs_group[column]
    if isinstance(node, h5py.Group) and node.attrs.get("encoding-type") == "categorical":
        cats = node["categories"][()]
        return sorted({decode(c) for c in cats})
    if isinstance(node, h5py.Dataset):
        # 카테고리형이 아니라 일반 컬럼으로 저장된 경우 (드묾) - 너무 크면 건너뜀
        if node.shape[0] > 2000:
            return None
        vals = node[()]
        return sorted({decode(v) for v in vals})
    return None


def categorical_value_fraction(obs_group: h5py.Group, column: str, target_value: str) -> float | None:
    """categorical 컬럼에서 특정 값(target_value)이 차지하는 비율을 구한다.

    codes 배열 전체를 읽지만 int8/int16 등 정수 배열이라 n_obs 바이트 수준으로 가볍다.
    """
    if column not in obs_group:
        return None
    node = obs_group[column]
    if not (isinstance(node, h5py.Group) and node.attrs.get("encoding-type") == "categorical"):
        return None
    cats = [decode(c) for c in node["categories"][()]]
    if target_value not in cats:
        return None
    target_code = cats.index(target_value)
    codes = node["codes"][()]
    if codes.size == 0:
        return None
    return float((codes == target_code).sum()) / float(codes.size)


def read_uns_scalar(uns_group: h5py.Group, field: str):
    if field not in uns_group:
        return None
    node = uns_group[field]
    if isinstance(node, h5py.Dataset) and node.shape == ():
        return decode(node[()])
    return None


def get_x_shape(f: h5py.File) -> tuple[int | None, int | None]:
    if "X" not in f:
        return None, None
    x = f["X"]
    if isinstance(x, h5py.Dataset):
        return int(x.shape[0]), int(x.shape[1])
    shape = x.attrs.get("shape")
    if shape is not None:
        return int(shape[0]), int(shape[1])
    return None, None


def is_primary_data_ratio(obs_group: h5py.Group) -> float | None:
    if "is_primary_data" not in obs_group:
        return None
    node = obs_group["is_primary_data"]
    if not isinstance(node, h5py.Dataset):
        return None
    # bool 배열 하나 전체를 읽어도 n_obs 바이트 수준이라 가벼움
    arr = node[()]
    if arr.size == 0:
        return None
    return float(arr.sum()) / float(arr.size)


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


# ---------------------------------------------------------------------------
# CZI CELLxGENE 폐(lung) 컬렉션
# ---------------------------------------------------------------------------


def extract_czi_one(path: Path) -> dict:
    m = CZI_FILENAME_RE.match(path.name)
    if m:
        disease_slug = m.group("disease")
        title_slug = m.group("title")
        uuid = m.group("uuid")
    else:
        disease_slug, title_slug, uuid = path.stem, path.stem, ""

    record: dict = {
        "filename": path.name,
        "dataset_id": uuid,
        "disease_group": disease_slug,
        "disease_group_list": [d for d in disease_slug.split("+") if d.strip()],
        "filename_title": title_slug.replace("-", " "),
        "file_size_bytes": path.stat().st_size,
        "status": "ok",
        "error": None,
    }

    try:
        with h5py.File(path, "r") as f:
            n_obs, n_vars = get_x_shape(f)
            record["n_cells"] = n_obs
            record["n_genes"] = n_vars

            if "obs" in f:
                obs = f["obs"]
                for col in CZI_CATEGORICAL_OBS_COLUMNS:
                    record[f"obs_{col}"] = read_categories(obs, col)
                record["n_donors"] = (
                    len(record["obs_donor_id"]) if record.get("obs_donor_id") else None
                )
                record["pct_primary_data"] = is_primary_data_ratio(obs)
            else:
                for col in CZI_CATEGORICAL_OBS_COLUMNS:
                    record[f"obs_{col}"] = None
                record["n_donors"] = None
                record["pct_primary_data"] = None

            if "uns" in f:
                uns = f["uns"]
                for field in CZI_UNS_SCALAR_FIELDS:
                    record[f"uns_{field}"] = read_uns_scalar(uns, field)
            else:
                for field in CZI_UNS_SCALAR_FIELDS:
                    record[f"uns_{field}"] = None

            record["encoding_version"] = decode(f.attrs.get("encoding-version"))
    except Exception as exc:  # noqa: BLE001
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()

    return record


def extract_czi_collection() -> dict:
    if not CZI_DATA_DIR.exists():
        print(f"데이터 디렉토리를 찾을 수 없습니다: {CZI_DATA_DIR}", file=sys.stderr)
        return {
            "id": "czi_lung",
            "name": "CZI CELLxGENE 폐(Lung) 데이터셋",
            "source_dir": str(CZI_DATA_DIR),
            "n_datasets": 0,
            "datasets": [],
        }

    files = sorted(CZI_DATA_DIR.glob("*.h5ad"))
    print(f"[CZI Lung] {len(files)}개의 h5ad 파일을 발견했습니다. 메타데이터 추출을 시작합니다...")

    records = []
    for i, path in enumerate(files, start=1):
        print(f"[CZI Lung {i}/{len(files)}] {path.name}")
        rec = extract_czi_one(path)
        rec["file_size_human"] = human_size(rec["file_size_bytes"])
        records.append(rec)

    n_ok = sum(1 for r in records if r["status"] == "ok")
    print(f"[CZI Lung] 완료: 성공 {n_ok}건, 실패 {len(records) - n_ok}건")

    return {
        "id": "czi_lung",
        "name": "CZI CELLxGENE 폐(Lung) 데이터셋",
        "source_dir": str(CZI_DATA_DIR),
        "n_datasets": len(records),
        "datasets": records,
    }


# ---------------------------------------------------------------------------
# Tahoe-100M 약물 처리 스크린 컬렉션
# ---------------------------------------------------------------------------


def extract_tahoe_one(path: Path) -> dict:
    m = TAHOE_FILENAME_RE.search(path.name)
    plate_num = m.group("plate_num") if m else None

    record: dict = {
        "filename": path.name,
        "dataset_id": path.stem,
        "plate_num": int(plate_num) if plate_num else None,
        "file_size_bytes": path.stat().st_size,
        "status": "ok",
        "error": None,
    }

    try:
        with h5py.File(path, "r") as f:
            n_obs, n_vars = get_x_shape(f)
            record["n_cells"] = n_obs
            record["n_genes"] = n_vars

            if "obs" in f:
                obs = f["obs"]
                for col in TAHOE_CATEGORICAL_OBS_COLUMNS:
                    record[f"obs_{col}"] = read_categories(obs, col)
                record["n_drugs"] = len(record["obs_drug"]) if record.get("obs_drug") else None
                record["n_cell_lines"] = (
                    len(record["obs_cell_line"]) if record.get("obs_cell_line") else None
                )
                record["n_samples"] = len(record["obs_sample"]) if record.get("obs_sample") else None
                record["n_sublibraries"] = (
                    len(record["obs_sublibrary"]) if record.get("obs_sublibrary") else None
                )
                record["pct_pass_filter_full"] = categorical_value_fraction(obs, "pass_filter", "full")
            else:
                for col in TAHOE_CATEGORICAL_OBS_COLUMNS:
                    record[f"obs_{col}"] = None
                record["n_drugs"] = None
                record["n_cell_lines"] = None
                record["n_samples"] = None
                record["n_sublibraries"] = None
                record["pct_pass_filter_full"] = None

            record["encoding_version"] = decode(f.attrs.get("encoding-version"))
    except Exception as exc:  # noqa: BLE001
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()

    return record


def extract_tahoe_collection() -> dict:
    if not TAHOE_DATA_DIR.exists():
        print(f"데이터 디렉토리를 찾을 수 없습니다: {TAHOE_DATA_DIR}", file=sys.stderr)
        return {
            "id": "tahoe_100m",
            "name": "Tahoe-100M 약물 처리 스크린",
            "source_dir": str(TAHOE_DATA_DIR),
            "n_datasets": 0,
            "datasets": [],
        }

    files = sorted(TAHOE_DATA_DIR.glob("*.h5ad"))
    print(f"[Tahoe-100M] {len(files)}개의 h5ad 파일을 발견했습니다. 메타데이터 추출을 시작합니다...")

    records = []
    for i, path in enumerate(files, start=1):
        print(f"[Tahoe-100M {i}/{len(files)}] {path.name}")
        rec = extract_tahoe_one(path)
        rec["file_size_human"] = human_size(rec["file_size_bytes"])
        records.append(rec)
    records.sort(key=lambda r: (r["plate_num"] is None, r["plate_num"]))

    n_ok = sum(1 for r in records if r["status"] == "ok")
    print(f"[Tahoe-100M] 완료: 성공 {n_ok}건, 실패 {len(records) - n_ok}건")

    return {
        "id": "tahoe_100m",
        "name": "Tahoe-100M 약물 처리 스크린",
        "source_dir": str(TAHOE_DATA_DIR),
        "n_datasets": len(records),
        "datasets": records,
    }


def main() -> None:
    collections = [extract_czi_collection(), extract_tahoe_collection()]

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "collections": collections,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"메타데이터 저장 완료: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
