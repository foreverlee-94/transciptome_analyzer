"""
metadata.json(여러 컬렉션)을 읽어서 검토용 단일 HTML 파일(report.html)을 생성한다.

- 외부 네트워크 의존성 없음 (CDN 미사용): 로컬에서 인터넷 연결 없이 바로 열람 가능.
- 데이터는 HTML 안에 JSON으로 통째로 임베드하여 file:// 로 열어도 CORS 문제 없이 동작.
- 컬렉션(CZI Lung / Tahoe-100M)마다 스키마가 전혀 달라서, 탭으로 분리하고 각 탭은
  공용 JS 팩토리(buildPanel)로 검색/정렬/필터/상세모달을 구성한다.
"""

from __future__ import annotations

import json
from pathlib import Path

METADATA_JSON = Path(__file__).parent / "metadata.json"
OUTPUT_HTML = Path(__file__).parent / "report.html"


def get_collection(payload: dict, collection_id: str) -> dict:
    for c in payload["collections"]:
        if c["id"] == collection_id:
            return c
    return {"id": collection_id, "name": collection_id, "source_dir": "", "n_datasets": 0, "datasets": []}


def build_html(payload: dict) -> str:
    czi = get_collection(payload, "czi_lung")
    tahoe = get_collection(payload, "tahoe_100m")

    czi_datasets = czi["datasets"]
    tahoe_datasets = tahoe["datasets"]

    # --- CZI 요약 통계 / 필터 옵션 ---
    czi_total_cells = sum(d.get("n_cells") or 0 for d in czi_datasets)
    czi_total_size = sum(d.get("file_size_bytes") or 0 for d in czi_datasets)
    # 파일명에서 뽑은 disease_group_list는 원본 파일명 자체가 잘려있는 경우가 있어
    # (예: "small-cell-lung-carc", "squamous-cell-lung-c") 필터/표시에는 h5ad 안의
    # 실제 obs_disease(잘리지 않은 정식 질환명) 값을 사용한다.
    disease_set = sorted({dg for d in czi_datasets for dg in (d.get("obs_disease") or [])})
    assay_set = sorted({a for d in czi_datasets for a in (d.get("obs_assay") or [])})
    organism_set = sorted({d.get("uns_organism") for d in czi_datasets if d.get("uns_organism")})

    # --- Tahoe-100M 요약 통계 / 필터 옵션 ---
    tahoe_total_cells = sum(d.get("n_cells") or 0 for d in tahoe_datasets)
    tahoe_total_size = sum(d.get("file_size_bytes") or 0 for d in tahoe_datasets)
    drug_set = sorted({dr for d in tahoe_datasets for dr in (d.get("obs_drug") or [])})
    cell_name_set = sorted({c for d in tahoe_datasets for c in (d.get("obs_cell_name") or [])})

    def options(values: list[str]) -> str:
        return "".join(f'<option value="{v}">{v}</option>' for v in values)

    czi_json = json.dumps(czi_datasets, ensure_ascii=False)
    tahoe_json = json.dumps(tahoe_datasets, ensure_ascii=False)

    czi_total_size_gb = czi_total_size / (1024 ** 3)
    tahoe_total_size_gb = tahoe_total_size / (1024 ** 3)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>단일세포 h5ad 데이터셋 메타데이터 리뷰</title>
<style>
  :root {{
    --bg: #0f1117;
    --panel: #171a23;
    --panel-2: #1e222d;
    --border: #2a2f3d;
    --text: #e6e8ee;
    --text-dim: #97a0b3;
    --accent: #5b9dff;
    --accent-2: #7ee0c1;
    --warn: #ff6b6b;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: -apple-system, "Segoe UI", "Malgun Gothic", sans-serif;
    background: var(--bg);
    color: var(--text);
  }}
  header {{
    padding: 20px 28px;
    border-bottom: 1px solid var(--border);
    background: linear-gradient(180deg, #151824, #0f1117);
  }}
  header h1 {{ margin: 0 0 4px; font-size: 20px; }}
  header .sub {{ color: var(--text-dim); font-size: 13px; }}

  .tab-bar {{
    display: flex;
    gap: 8px;
    padding: 14px 28px 0;
  }}
  .tab-btn {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-bottom: none;
    color: var(--text-dim);
    padding: 10px 18px;
    border-radius: 10px 10px 0 0;
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
  }}
  .tab-btn.active {{ color: var(--text); background: var(--panel-2); }}

  .panel {{ display: none; border-top: 1px solid var(--border); }}
  .panel.active {{ display: block; }}

  .stats {{
    display: flex;
    gap: 12px;
    padding: 16px 28px;
    flex-wrap: wrap;
  }}
  .stat-card {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px 18px;
    min-width: 140px;
  }}
  .stat-card .value {{ font-size: 22px; font-weight: 700; color: var(--accent-2); }}
  .stat-card .label {{ font-size: 12px; color: var(--text-dim); margin-top: 2px; }}

  .toolbar {{
    display: flex;
    gap: 10px;
    padding: 0 28px 16px;
    flex-wrap: wrap;
    align-items: center;
  }}
  .toolbar input[type=text], .toolbar select {{
    background: var(--panel-2);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 8px 10px;
    border-radius: 8px;
    font-size: 13px;
  }}
  .toolbar input[type=text] {{ min-width: 260px; }}
  .toolbar .count {{ color: var(--text-dim); font-size: 13px; margin-left: auto; }}

  table {{
    width: calc(100% - 56px);
    margin: 0 28px 40px;
    border-collapse: collapse;
    font-size: 13px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
  }}
  thead th {{
    position: sticky;
    top: 0;
    background: var(--panel-2);
    text-align: left;
    padding: 10px 12px;
    cursor: pointer;
    color: var(--text-dim);
    font-weight: 600;
    white-space: nowrap;
    border-bottom: 1px solid var(--border);
  }}
  thead th:hover {{ color: var(--text); }}
  thead th .arrow {{ opacity: 0.5; font-size: 10px; margin-left: 4px; }}
  tbody td {{
    padding: 9px 12px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }}
  tbody tr {{ cursor: pointer; }}
  tbody tr:hover {{ background: #202536; }}
  .tag {{
    display: inline-block;
    background: #26314a;
    color: var(--accent);
    border-radius: 6px;
    padding: 1px 7px;
    font-size: 11px;
    margin: 1px 2px 1px 0;
  }}
  .tag.disease {{ background: #3a2430; color: #ff9db3; }}
  .tag.drug {{ background: #2a3a26; color: #a8e06a; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .title-cell {{ max-width: 340px; }}
  .title-main {{ font-weight: 600; }}
  .title-sub {{ color: var(--text-dim); font-size: 11px; }}

  .modal-backdrop {{
    display: none;
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.6);
    z-index: 50;
    align-items: flex-start;
    justify-content: center;
    padding: 40px 20px;
    overflow-y: auto;
  }}
  .modal-backdrop.open {{ display: flex; }}
  .modal {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 14px;
    max-width: 760px;
    width: 100%;
    padding: 24px 28px 28px;
  }}
  .modal h2 {{ margin: 0 0 2px; font-size: 18px; }}
  .modal .modal-sub {{ color: var(--text-dim); font-size: 12px; margin-bottom: 16px; word-break: break-all; }}
  .modal .close-btn {{
    float: right;
    background: var(--panel-2);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: 8px;
    padding: 6px 12px;
    cursor: pointer;
  }}
  .kv-grid {{
    display: grid;
    grid-template-columns: 170px 1fr;
    gap: 6px 14px;
    font-size: 13px;
    margin-top: 10px;
  }}
  .kv-grid .k {{ color: var(--text-dim); }}
  .kv-grid .v {{ word-break: break-word; }}
  .kv-grid .v a {{ color: var(--accent); }}
  .status-error {{ color: var(--warn); font-weight: 600; }}
  footer {{ padding: 20px 28px 50px; color: var(--text-dim); font-size: 12px; }}
</style>
</head>
<body>

<header>
  <h1>단일세포 h5ad 데이터셋 메타데이터 리뷰</h1>
  <div class="sub">생성 시각: {payload['generated_at']}</div>
</header>

<div class="tab-bar">
  <button class="tab-btn active" data-panel="panel-czi">CZI CELLxGENE 폐(Lung) ({len(czi_datasets)})</button>
  <button class="tab-btn" data-panel="panel-tahoe">Tahoe-100M 약물 처리 스크린 ({len(tahoe_datasets)})</button>
</div>

<!-- ================= CZI CELLxGENE Lung 패널 ================= -->
<div class="panel active" id="panel-czi">
  <div class="stats">
    <div class="stat-card"><div class="value">{len(czi_datasets)}</div><div class="label">데이터셋 (h5ad 파일)</div></div>
    <div class="stat-card"><div class="value">{czi_total_cells:,}</div><div class="label">총 세포 수 (n_cells 합)</div></div>
    <div class="stat-card"><div class="value">{czi_total_size_gb:,.1f} GB</div><div class="label">총 파일 크기</div></div>
    <div class="stat-card"><div class="value">{len(disease_set)}</div><div class="label">질환/조건 카테고리</div></div>
    <div class="stat-card"><div class="value">{len(assay_set)}</div><div class="label">Assay 종류</div></div>
  </div>
  <div class="toolbar">
    <input type="text" id="czi-search" placeholder="파일명 / 제목 / cell type / donor 등 검색...">
    <select id="czi-diseaseFilter"><option value="">전체 질환/조건</option>{options(disease_set)}</select>
    <select id="czi-assayFilter"><option value="">전체 Assay</option>{options(assay_set)}</select>
    <select id="czi-organismFilter"><option value="">전체 Organism</option>{options(organism_set)}</select>
    <span class="count" id="czi-count"></span>
  </div>
  <table id="czi-table"><thead><tr></tr></thead><tbody></tbody></table>
  <div class="modal-backdrop" id="czi-modalBackdrop">
    <div class="modal">
      <button class="close-btn" id="czi-closeModalBtn">닫기</button>
      <h2 id="czi-modalTitle"></h2>
      <div class="modal-sub" id="czi-modalSub"></div>
      <div class="kv-grid" id="czi-modalBody"></div>
    </div>
  </div>
  <footer>원본 경로: {czi['source_dir']} &middot; obs/var/uns 메타데이터만 읽어 생성 (발현행렬 X는 로드하지 않음)</footer>
</div>

<!-- ================= Tahoe-100M 패널 ================= -->
<div class="panel" id="panel-tahoe">
  <div class="stats">
    <div class="stat-card"><div class="value">{len(tahoe_datasets)}</div><div class="label">Plate (h5ad 파일)</div></div>
    <div class="stat-card"><div class="value">{tahoe_total_cells:,}</div><div class="label">총 세포 수 (n_cells 합)</div></div>
    <div class="stat-card"><div class="value">{tahoe_total_size_gb:,.1f} GB</div><div class="label">총 파일 크기</div></div>
    <div class="stat-card"><div class="value">{len(drug_set)}</div><div class="label">고유 약물 종류</div></div>
    <div class="stat-card"><div class="value">{len(cell_name_set)}</div><div class="label">고유 세포주 종류</div></div>
  </div>
  <div class="toolbar">
    <input type="text" id="tahoe-search" placeholder="파일명 / 약물 / 세포주 등 검색...">
    <select id="tahoe-drugFilter"><option value="">전체 약물</option>{options(drug_set)}</select>
    <select id="tahoe-cellLineFilter"><option value="">전체 세포주</option>{options(cell_name_set)}</select>
    <span class="count" id="tahoe-count"></span>
  </div>
  <table id="tahoe-table"><thead><tr></tr></thead><tbody></tbody></table>
  <div class="modal-backdrop" id="tahoe-modalBackdrop">
    <div class="modal">
      <button class="close-btn" id="tahoe-closeModalBtn">닫기</button>
      <h2 id="tahoe-modalTitle"></h2>
      <div class="modal-sub" id="tahoe-modalSub"></div>
      <div class="kv-grid" id="tahoe-modalBody"></div>
    </div>
  </div>
  <footer>원본 경로: {tahoe['source_dir']} &middot; obs 메타데이터만 읽어 생성 (발현행렬 X 및 세포별 BARCODE는 로드하지 않음)</footer>
</div>

<script>
const CZI_DATA = {czi_json};
const TAHOE_DATA = {tahoe_json};

function fmtNum(n) {{
  return (n === null || n === undefined) ? '-' : n.toLocaleString('en-US');
}}
function fmtPct(n) {{
  return (n === null || n === undefined) ? '-' : (n * 100).toFixed(1) + '%';
}}
function fmtSize(bytes) {{
  if (bytes === null || bytes === undefined) return '-';
  const units = ['B','KB','MB','GB','TB'];
  let i = 0, v = bytes;
  while (v >= 1024 && i < units.length - 1) {{ v /= 1024; i++; }}
  return v.toFixed(2) + ' ' + units[i];
}}
function tagList(arr, cls) {{
  if (!arr || arr.length === 0) return '<span style="color:var(--text-dim)">-</span>';
  return arr.map(v => `<span class="tag ${{cls||''}}">${{v}}</span>`).join('');
}}
function kv(label, value) {{
  return `<div class="k">${{label}}</div><div class="v">${{value}}</div>`;
}}
function getSortValue(d, key) {{
  const v = d[key];
  if (Array.isArray(v)) return v.join(', ');
  return v;
}}

// 공용 패널 팩토리: 검색창 + 드롭다운 필터 + 정렬 가능한 표 + 상세 모달을
// 컬럼/필터/모달 필드 설정(config)만 바꿔서 여러 컬렉션에 재사용한다.
function buildPanel(cfg) {{
  let sortKey = cfg.defaultSortKey;
  let sortDir = 1;

  const table = document.getElementById(cfg.tableId);
  const theadRow = table.querySelector('thead tr');
  theadRow.innerHTML = cfg.columns.map(c =>
    `<th data-key="${{c.key}}" class="${{c.numeric ? 'num' : ''}}">${{c.label}} <span class="arrow"></span></th>`
  ).join('');

  theadRow.querySelectorAll('th').forEach((th, i) => {{
    th.addEventListener('click', () => {{
      const key = cfg.columns[i].key;
      if (sortKey === key) {{ sortDir *= -1; }} else {{ sortKey = key; sortDir = 1; }}
      theadRow.querySelectorAll('.arrow').forEach(a => a.textContent = '');
      th.querySelector('.arrow').textContent = sortDir === 1 ? '▲' : '▼';
      render();
    }});
  }});

  function matchesFilters(d) {{
    const q = document.getElementById(cfg.searchId).value.trim().toLowerCase();
    for (const f of cfg.filters) {{
      const val = document.getElementById(f.selectId).value;
      if (val && !f.match(d, val)) return false;
    }}
    if (q && !cfg.searchMatch(d, q)) return false;
    return true;
  }}

  function render() {{
    const rows = cfg.data.filter(matchesFilters);
    rows.sort((a, b) => {{
      let va = getSortValue(a, sortKey);
      let vb = getSortValue(b, sortKey);
      if (va === null || va === undefined) va = '';
      if (vb === null || vb === undefined) vb = '';
      if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * sortDir;
      return String(va).localeCompare(String(vb)) * sortDir;
    }});

    const tbody = table.querySelector('tbody');
    tbody.innerHTML = rows.map(d => {{
      const idx = cfg.data.indexOf(d);
      const statusBadge = d.status === 'error' ? ' <span class="status-error">[오류]</span>' : '';
      const cells = cfg.columns.map(c =>
        `<td class="${{c.numeric ? 'num' : ''}} ${{c.cellClass || ''}}">${{c.render(d, statusBadge)}}</td>`
      ).join('');
      return `<tr data-idx="${{idx}}">${{cells}}</tr>`;
    }}).join('');

    document.getElementById(cfg.countId).textContent = `${{rows.length}} / ${{cfg.data.length}} 개 표시 중`;

    tbody.querySelectorAll('tr').forEach(tr => {{
      tr.addEventListener('click', () => openModal(cfg.data[parseInt(tr.dataset.idx, 10)]));
    }});
  }}

  function openModal(d) {{
    document.getElementById(cfg.modalTitleId).textContent = cfg.modalTitle(d);
    document.getElementById(cfg.modalSubId).textContent = d.filename;
    document.getElementById(cfg.modalBodyId).innerHTML = cfg.modalFields.map(f => kv(f.label, f.render(d))).join('');
    document.getElementById(cfg.modalBackdropId).classList.add('open');
  }}

  document.getElementById(cfg.closeBtnId).addEventListener('click', () => {{
    document.getElementById(cfg.modalBackdropId).classList.remove('open');
  }});
  document.getElementById(cfg.modalBackdropId).addEventListener('click', (e) => {{
    if (e.target.id === cfg.modalBackdropId) e.currentTarget.classList.remove('open');
  }});

  document.getElementById(cfg.searchId).addEventListener('input', render);
  cfg.filters.forEach(f => document.getElementById(f.selectId).addEventListener('change', render));

  render();
}}

// --- CZI CELLxGENE Lung 패널 설정 ---
buildPanel({{
  data: CZI_DATA,
  tableId: 'czi-table',
  searchId: 'czi-search',
  countId: 'czi-count',
  modalTitleId: 'czi-modalTitle',
  modalSubId: 'czi-modalSub',
  modalBodyId: 'czi-modalBody',
  modalBackdropId: 'czi-modalBackdrop',
  closeBtnId: 'czi-closeModalBtn',
  defaultSortKey: 'obs_disease',
  filters: [
    {{ selectId: 'czi-diseaseFilter', match: (d, v) => (d.obs_disease || []).includes(v) }},
    {{ selectId: 'czi-assayFilter', match: (d, v) => (d.obs_assay || []).includes(v) }},
    {{ selectId: 'czi-organismFilter', match: (d, v) => d.uns_organism === v }},
  ],
  searchMatch: (d, q) => [
    d.filename, d.filename_title, d.uns_title, d.disease_group,
    ...(d.obs_disease || []), ...(d.obs_cell_type || []), ...(d.obs_donor_id || []),
    ...(d.obs_tissue || []), ...(d.obs_assay || [])
  ].join(' ').toLowerCase().includes(q),
  columns: [
    {{ key: 'obs_disease', label: '질환/조건', render: d => tagList(d.obs_disease, 'disease') }},
    {{ key: 'filename_title', label: '데이터셋 제목', cellClass: 'title-cell', render: (d, badge) =>
      `<div class="title-main">${{d.uns_title || d.filename_title}}${{badge}}</div><div class="title-sub">${{d.filename}}</div>` }},
    {{ key: 'uns_organism', label: 'Organism', render: d => d.uns_organism || '-' }},
    {{ key: 'n_cells', label: '세포 수', numeric: true, render: d => fmtNum(d.n_cells) }},
    {{ key: 'n_genes', label: '유전자 수', numeric: true, render: d => fmtNum(d.n_genes) }},
    {{ key: 'n_donors', label: 'Donor 수', numeric: true, render: d => fmtNum(d.n_donors) }},
    {{ key: 'obs_tissue', label: '조직', render: d => tagList(d.obs_tissue) }},
    {{ key: 'obs_assay', label: 'Assay', render: d => tagList(d.obs_assay) }},
    {{ key: 'file_size_bytes', label: '파일 크기', numeric: true, render: d => fmtSize(d.file_size_bytes) }},
  ],
  modalTitle: d => d.uns_title || d.filename_title,
  modalFields: [
    {{ label: 'Dataset ID', render: d => d.dataset_id || '-' }},
    {{ label: '질환/조건', render: d => tagList(d.obs_disease, 'disease') }},
    {{ label: 'Organism', render: d => d.uns_organism || '-' }},
    {{ label: '세포 수', render: d => fmtNum(d.n_cells) }},
    {{ label: '유전자 수', render: d => fmtNum(d.n_genes) }},
    {{ label: 'Donor 수', render: d => fmtNum(d.n_donors) }},
    {{ label: 'Primary data 비율', render: d => fmtPct(d.pct_primary_data) }},
    {{ label: '조직 (tissue)', render: d => tagList(d.obs_tissue) }},
    {{ label: '조직 타입', render: d => tagList(d.obs_tissue_type) }},
    {{ label: 'Assay', render: d => tagList(d.obs_assay) }},
    {{ label: 'Cell type 종류 수', render: d => d.obs_cell_type ? d.obs_cell_type.length : '-' }},
    {{ label: 'Cell types', render: d => tagList(d.obs_cell_type) }},
    {{ label: '성별 (sex)', render: d => tagList(d.obs_sex) }},
    {{ label: '인종/민족', render: d => tagList(d.obs_self_reported_ethnicity) }},
    {{ label: '발달 단계', render: d => tagList(d.obs_development_stage) }},
    {{ label: 'Suspension type', render: d => tagList(d.obs_suspension_type) }},
    {{ label: 'Schema version', render: d => d.uns_schema_version || '-' }},
    {{ label: '기본 임베딩', render: d => d.uns_default_embedding || '-' }},
    {{ label: '파일 크기', render: d => fmtSize(d.file_size_bytes) }},
    {{ label: 'Citation', render: d => d.uns_citation
        ? d.uns_citation.replace(/(https?:\\/\\/[^\\s]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>')
        : '-' }},
  ],
}});

// --- Tahoe-100M 패널 설정 ---
buildPanel({{
  data: TAHOE_DATA,
  tableId: 'tahoe-table',
  searchId: 'tahoe-search',
  countId: 'tahoe-count',
  modalTitleId: 'tahoe-modalTitle',
  modalSubId: 'tahoe-modalSub',
  modalBodyId: 'tahoe-modalBody',
  modalBackdropId: 'tahoe-modalBackdrop',
  closeBtnId: 'tahoe-closeModalBtn',
  defaultSortKey: 'plate_num',
  filters: [
    {{ selectId: 'tahoe-drugFilter', match: (d, v) => (d.obs_drug || []).includes(v) }},
    {{ selectId: 'tahoe-cellLineFilter', match: (d, v) => (d.obs_cell_name || []).includes(v) }},
  ],
  searchMatch: (d, q) => [
    d.filename, `plate ${{d.plate_num}}`,
    ...(d.obs_drug || []), ...(d.obs_cell_name || []), ...(d.obs_cell_line || [])
  ].join(' ').toLowerCase().includes(q),
  columns: [
    {{ key: 'plate_num', label: 'Plate', numeric: true, render: (d, badge) => `Plate ${{d.plate_num}}${{badge}}` }},
    {{ key: 'filename', label: '파일명', cellClass: 'title-cell', render: d =>
      `<div class="title-sub">${{d.filename}}</div>` }},
    {{ key: 'n_cells', label: '세포 수', numeric: true, render: d => fmtNum(d.n_cells) }},
    {{ key: 'n_genes', label: '유전자 수', numeric: true, render: d => fmtNum(d.n_genes) }},
    {{ key: 'n_drugs', label: '약물 수', numeric: true, render: d => fmtNum(d.n_drugs) }},
    {{ key: 'n_cell_lines', label: '세포주 수', numeric: true, render: d => fmtNum(d.n_cell_lines) }},
    {{ key: 'n_samples', label: '샘플(well) 수', numeric: true, render: d => fmtNum(d.n_samples) }},
    {{ key: 'pct_pass_filter_full', label: 'Full-filter 통과율', numeric: true, render: d => fmtPct(d.pct_pass_filter_full) }},
    {{ key: 'file_size_bytes', label: '파일 크기', numeric: true, render: d => fmtSize(d.file_size_bytes) }},
  ],
  modalTitle: d => `Plate ${{d.plate_num}}`,
  modalFields: [
    {{ label: 'Dataset ID', render: d => d.dataset_id || '-' }},
    {{ label: 'Plate 번호', render: d => d.plate_num ?? '-' }},
    {{ label: '세포 수', render: d => fmtNum(d.n_cells) }},
    {{ label: '유전자 수', render: d => fmtNum(d.n_genes) }},
    {{ label: 'Full-filter 통과율', render: d => fmtPct(d.pct_pass_filter_full) }},
    {{ label: '약물 수', render: d => fmtNum(d.n_drugs) }},
    {{ label: '약물 목록', render: d => tagList(d.obs_drug, 'drug') }},
    {{ label: '세포주 수', render: d => fmtNum(d.n_cell_lines) }},
    {{ label: '세포주 목록 (common name)', render: d => tagList(d.obs_cell_name) }},
    {{ label: '세포주 목록 (Cellosaurus ID)', render: d => tagList(d.obs_cell_line) }},
    {{ label: '샘플(well) 수', render: d => fmtNum(d.n_samples) }},
    {{ label: 'Sublibrary 수', render: d => fmtNum(d.n_sublibraries) }},
    {{ label: '세포주기 phase', render: d => tagList(d.obs_phase) }},
    {{ label: 'Pass filter 등급', render: d => tagList(d.obs_pass_filter) }},
    {{ label: '파일 크기', render: d => fmtSize(d.file_size_bytes) }},
  ],
}});

document.querySelectorAll('.tab-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.panel).classList.add('active');
  }});
}});
</script>
</body>
</html>
"""


def main() -> None:
    if not METADATA_JSON.exists():
        raise SystemExit(f"{METADATA_JSON} 가 없습니다. 먼저 extract_metadata.py를 실행하세요.")
    payload = json.loads(METADATA_JSON.read_text(encoding="utf-8"))
    html = build_html(payload)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    print(f"리포트 생성 완료: {OUTPUT_HTML}")


if __name__ == "__main__":
    main()
