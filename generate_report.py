"""
metadata.json을 읽어서 검토용 단일 HTML 파일(report.html)을 생성한다.

- 외부 네트워크 의존성 없음 (CDN 미사용): 로컬에서 인터넷 연결 없이 바로 열람 가능.
- 데이터는 HTML 안에 JSON으로 통째로 임베드하여 file:// 로 열어도 CORS 문제 없이 동작.
- 정렬/검색/필터(질환군, organism, assay)와 행 클릭 시 상세 모달을 순수 JS로 구현.
"""

from __future__ import annotations

import json
from pathlib import Path

METADATA_JSON = Path(__file__).parent / "metadata.json"
OUTPUT_HTML = Path(__file__).parent / "report.html"


def build_html(payload: dict) -> str:
    datasets = payload["datasets"]

    # 요약 통계
    total_cells = sum(d.get("n_cells") or 0 for d in datasets)
    total_size = sum(d.get("file_size_bytes") or 0 for d in datasets)
    disease_set = sorted({dg for d in datasets for dg in d.get("disease_group_list", [])})
    assay_set = sorted({a for d in datasets for a in (d.get("obs_assay") or [])})
    organism_set = sorted({d.get("uns_organism") for d in datasets if d.get("uns_organism")})

    data_json = json.dumps(datasets, ensure_ascii=False)
    disease_options = "".join(f'<option value="{d}">{d}</option>' for d in disease_set)
    assay_options = "".join(f'<option value="{a}">{a}</option>' for a in assay_set)
    organism_options = "".join(f'<option value="{o}">{o}</option>' for o in organism_set)

    total_size_gb = total_size / (1024 ** 3)

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CZI CELLxGENE 폐(Lung) 데이터셋 메타데이터 리뷰</title>
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
  hr.sep {{ border: none; border-top: 1px solid var(--border); margin: 16px 0; }}
  .status-error {{ color: var(--warn); font-weight: 600; }}
  footer {{ padding: 20px 28px 50px; color: var(--text-dim); font-size: 12px; }}
</style>
</head>
<body>

<header>
  <h1>CZI CELLxGENE 폐(Lung) 데이터셋 메타데이터 리뷰</h1>
  <div class="sub">생성 시각: {payload['generated_at']} &middot; 원본 경로: {payload['source_dir']}</div>
</header>

<div class="stats">
  <div class="stat-card"><div class="value">{len(datasets)}</div><div class="label">데이터셋 (h5ad 파일)</div></div>
  <div class="stat-card"><div class="value">{total_cells:,}</div><div class="label">총 세포 수 (n_cells 합)</div></div>
  <div class="stat-card"><div class="value">{total_size_gb:,.1f} GB</div><div class="label">총 파일 크기</div></div>
  <div class="stat-card"><div class="value">{len(disease_set)}</div><div class="label">질환/조건 카테고리</div></div>
  <div class="stat-card"><div class="value">{len(assay_set)}</div><div class="label">Assay 종류</div></div>
</div>

<div class="toolbar">
  <input type="text" id="searchBox" placeholder="파일명 / 제목 / cell type / donor 등 검색...">
  <select id="diseaseFilter"><option value="">전체 질환/조건</option>{disease_options}</select>
  <select id="assayFilter"><option value="">전체 Assay</option>{assay_options}</select>
  <select id="organismFilter"><option value="">전체 Organism</option>{organism_options}</select>
  <span class="count" id="rowCount"></span>
</div>

<table id="dataTable">
  <thead>
    <tr>
      <th data-key="disease_group">질환/조건 <span class="arrow"></span></th>
      <th data-key="filename_title">데이터셋 제목 <span class="arrow"></span></th>
      <th data-key="uns_organism">Organism <span class="arrow"></span></th>
      <th data-key="n_cells" class="num">세포 수 <span class="arrow"></span></th>
      <th data-key="n_genes" class="num">유전자 수 <span class="arrow"></span></th>
      <th data-key="n_donors" class="num">Donor 수 <span class="arrow"></span></th>
      <th data-key="obs_tissue">조직 <span class="arrow"></span></th>
      <th data-key="obs_assay">Assay <span class="arrow"></span></th>
      <th data-key="file_size_bytes" class="num">파일 크기 <span class="arrow"></span></th>
    </tr>
  </thead>
  <tbody id="tableBody"></tbody>
</table>

<div class="modal-backdrop" id="modalBackdrop">
  <div class="modal">
    <button class="close-btn" id="closeModalBtn">닫기</button>
    <h2 id="modalTitle"></h2>
    <div class="modal-sub" id="modalFilename"></div>
    <div class="kv-grid" id="modalBody"></div>
  </div>
</div>

<footer>extract_metadata.py 로 h5ad 파일의 obs/var/uns 메타데이터만 읽어 생성되었습니다 (발현행렬 X는 로드하지 않음).</footer>

<script>
const DATA = {data_json};

let sortKey = 'disease_group';
let sortDir = 1;

function fmtNum(n) {{
  return (n === null || n === undefined) ? '-' : n.toLocaleString('en-US');
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

function matchesFilters(d) {{
  const q = document.getElementById('searchBox').value.trim().toLowerCase();
  const disease = document.getElementById('diseaseFilter').value;
  const assay = document.getElementById('assayFilter').value;
  const organism = document.getElementById('organismFilter').value;

  if (disease && !(d.disease_group_list || []).includes(disease)) return false;
  if (assay && !(d.obs_assay || []).includes(assay)) return false;
  if (organism && d.uns_organism !== organism) return false;

  if (q) {{
    const haystack = [
      d.filename, d.filename_title, d.uns_title, d.disease_group,
      ...(d.obs_cell_type || []), ...(d.obs_donor_id || []),
      ...(d.obs_tissue || []), ...(d.obs_assay || [])
    ].join(' ').toLowerCase();
    if (!haystack.includes(q)) return false;
  }}
  return true;
}}

function getSortValue(d, key) {{
  const v = d[key];
  if (Array.isArray(v)) return v.join(', ');
  return v;
}}

function render() {{
  const rows = DATA.filter(matchesFilters);
  rows.sort((a, b) => {{
    let va = getSortValue(a, sortKey);
    let vb = getSortValue(b, sortKey);
    if (va === null || va === undefined) va = '';
    if (vb === null || vb === undefined) vb = '';
    if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * sortDir;
    return String(va).localeCompare(String(vb)) * sortDir;
  }});

  const tbody = document.getElementById('tableBody');
  tbody.innerHTML = rows.map((d, idx) => {{
    const realIdx = DATA.indexOf(d);
    const statusBadge = d.status === 'error' ? ' <span class="status-error">[오류]</span>' : '';
    return `<tr data-idx="${{realIdx}}">
      <td>${{tagList(d.disease_group_list, 'disease')}}</td>
      <td class="title-cell">
        <div class="title-main">${{d.uns_title || d.filename_title}}${{statusBadge}}</div>
        <div class="title-sub">${{d.filename}}</div>
      </td>
      <td>${{d.uns_organism || '-'}}</td>
      <td class="num">${{fmtNum(d.n_cells)}}</td>
      <td class="num">${{fmtNum(d.n_genes)}}</td>
      <td class="num">${{fmtNum(d.n_donors)}}</td>
      <td>${{tagList(d.obs_tissue)}}</td>
      <td>${{tagList(d.obs_assay)}}</td>
      <td class="num">${{fmtSize(d.file_size_bytes)}}</td>
    </tr>`;
  }}).join('');

  document.getElementById('rowCount').textContent = `${{rows.length}} / ${{DATA.length}} 개 표시 중`;

  tbody.querySelectorAll('tr').forEach(tr => {{
    tr.addEventListener('click', () => openModal(DATA[parseInt(tr.dataset.idx, 10)]));
  }});
}}

function kv(label, value) {{
  return `<div class="k">${{label}}</div><div class="v">${{value}}</div>`;
}}

function openModal(d) {{
  document.getElementById('modalTitle').textContent = d.uns_title || d.filename_title;
  document.getElementById('modalFilename').textContent = d.filename;

  const citation = d.uns_citation
    ? d.uns_citation.replace(/(https?:\\/\\/[^\\s]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>')
    : '-';

  const rows = [
    kv('Dataset ID', d.dataset_id || '-'),
    kv('질환/조건', tagList(d.disease_group_list, 'disease')),
    kv('Organism', d.uns_organism || '-'),
    kv('세포 수', fmtNum(d.n_cells)),
    kv('유전자 수', fmtNum(d.n_genes)),
    kv('Donor 수', fmtNum(d.n_donors)),
    kv('Primary data 비율', d.pct_primary_data !== null && d.pct_primary_data !== undefined ? (d.pct_primary_data * 100).toFixed(1) + '%' : '-'),
    kv('조직 (tissue)', tagList(d.obs_tissue)),
    kv('조직 타입', tagList(d.obs_tissue_type)),
    kv('Assay', tagList(d.obs_assay)),
    kv('Cell type 종류 수', d.obs_cell_type ? d.obs_cell_type.length : '-'),
    kv('Cell types', tagList(d.obs_cell_type)),
    kv('성별 (sex)', tagList(d.obs_sex)),
    kv('인종/민족', tagList(d.obs_self_reported_ethnicity)),
    kv('발달 단계', tagList(d.obs_development_stage)),
    kv('Suspension type', tagList(d.obs_suspension_type)),
    kv('Schema version', d.uns_schema_version || '-'),
    kv('기본 임베딩', d.uns_default_embedding || '-'),
    kv('파일 크기', fmtSize(d.file_size_bytes)),
    kv('Citation', citation),
  ].join('');

  document.getElementById('modalBody').innerHTML = rows;
  document.getElementById('modalBackdrop').classList.add('open');
}}

document.getElementById('closeModalBtn').addEventListener('click', () => {{
  document.getElementById('modalBackdrop').classList.remove('open');
}});
document.getElementById('modalBackdrop').addEventListener('click', (e) => {{
  if (e.target.id === 'modalBackdrop') e.currentTarget.classList.remove('open');
}});

document.querySelectorAll('thead th[data-key]').forEach(th => {{
  th.addEventListener('click', () => {{
    const key = th.dataset.key;
    if (sortKey === key) {{ sortDir *= -1; }} else {{ sortKey = key; sortDir = 1; }}
    document.querySelectorAll('thead .arrow').forEach(a => a.textContent = '');
    th.querySelector('.arrow').textContent = sortDir === 1 ? '▲' : '▼';
    render();
  }});
}});

['searchBox'].forEach(id => document.getElementById(id).addEventListener('input', render));
['diseaseFilter', 'assayFilter', 'organismFilter'].forEach(id => document.getElementById(id).addEventListener('change', render));

render();
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
