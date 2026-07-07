"""
CZI CELLxGENE 폐(lung) 데이터셋 h5ad 파일들의 메타데이터를 추출한다.

핵심 설계 원칙: h5ad는 HDF5 컨테이너이므로, 발현행렬(X/raw.X)은 전혀 읽지 않고
obs/var/uns 안의 "가벼운" 데이터셋(카테고리 목록, 스칼라 값, shape 속성)만
h5py로 직접 읽는다. 이렇게 하면 45GB짜리 파일도 metadata 추출은 수 초 내로 끝난다.
"""

from __future__ import annotations

import json
import re
import sys
import traceback
from datetime import datetime
from pathlib import Path

import h5py

DATA_DIR = Path(r"D:\CZI-CellXGene-Lung-datasets")
OUTPUT_JSON = Path(__file__).parent / "metadata.json"

# CELLxGENE 표준 스키마에서 관심있는 obs 카테고리형 컬럼들
CATEGORICAL_OBS_COLUMNS = [
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

UNS_SCALAR_FIELDS = [
    "title",
    "schema_version",
    "schema_reference",
    "citation",
    "organism",
    "default_embedding",
]

FILENAME_RE = re.compile(
    r"^(?P<disease>.+?)__(?P<title>.+)__(?P<uuid>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\.h5ad$"
)


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


def extract_one(path: Path) -> dict:
    m = FILENAME_RE.match(path.name)
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
        "disease_group_list": disease_slug.split("+"),
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
                for col in CATEGORICAL_OBS_COLUMNS:
                    record[f"obs_{col}"] = read_categories(obs, col)
                record["n_donors"] = (
                    len(record["obs_donor_id"]) if record.get("obs_donor_id") else None
                )
                record["pct_primary_data"] = is_primary_data_ratio(obs)
            else:
                for col in CATEGORICAL_OBS_COLUMNS:
                    record[f"obs_{col}"] = None
                record["n_donors"] = None
                record["pct_primary_data"] = None

            if "uns" in f:
                uns = f["uns"]
                for field in UNS_SCALAR_FIELDS:
                    record[f"uns_{field}"] = read_uns_scalar(uns, field)
            else:
                for field in UNS_SCALAR_FIELDS:
                    record[f"uns_{field}"] = None

            record["encoding_version"] = decode(f.attrs.get("encoding-version"))
    except Exception as exc:  # noqa: BLE001
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()

    return record


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def main() -> None:
    if not DATA_DIR.exists():
        print(f"데이터 디렉토리를 찾을 수 없습니다: {DATA_DIR}", file=sys.stderr)
        sys.exit(1)

    files = sorted(DATA_DIR.glob("*.h5ad"))
    print(f"{len(files)}개의 h5ad 파일을 발견했습니다. 메타데이터 추출을 시작합니다...")

    records = []
    for i, path in enumerate(files, start=1):
        print(f"[{i}/{len(files)}] {path.name}")
        rec = extract_one(path)
        rec["file_size_human"] = human_size(rec["file_size_bytes"])
        records.append(rec)

    n_ok = sum(1 for r in records if r["status"] == "ok")
    n_err = len(records) - n_ok
    print(f"완료: 성공 {n_ok}건, 실패 {n_err}건")

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_dir": str(DATA_DIR),
        "n_datasets": len(records),
        "datasets": records,
    }
    OUTPUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"메타데이터 저장 완료: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
