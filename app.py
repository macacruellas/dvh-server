import math, re
from flask import Flask, request, render_template_string
import pytesseract  # ← no usamos OCR aquí, solo queda configurado si más adelante lo necesitás

# Ajustá la ruta si tu tesseract.exe está en otro lugar (esta es la que vos encontraste)
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\Julieta\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

app = Flask(__name__)

# ====== Límites fijos (inamovibles) ======
LIMITS_EQD2 = {"VEJIGA":85.0,"RECTO":75.0,"SIGMOIDE":75.0,"INTESTINO":75.0}

# ====== Aliases ROI EN/ES ======
ALIASES = {
    "VEJIGA":[re.compile(p,re.I) for p in [r"\bbladder\b", r"\bvejig"]],
    "RECTO":[re.compile(p,re.I) for p in [r"\brectum\b", r"\brecto\b"]],

    # === INTESTINO GRUESO (SIGMOIDE / COLON) ===
    "SIGMOIDE":[re.compile(p,re.I) for p in [
        r"\bsigmoid\b",
        r"\bsigmoide\b",
        r"\bsigma\b",
        r"\bcolon\b",                       # colon “a secas”
        r"\bcolon[_\s-]*sigmoid[eo]\b",     # colon-sigmoide / colon sigmoideo
        r"\brecto[_\s-]*sigmoid[eo]\b",     # recto-sigmoide
        r"\brectosigmoid[eo]\b",            # rectosigmoideo
        r"\bintestino\s+grueso\b",
        r"\bbowel[_\s-]?large\b",           # large bowel
    ]],


    # === INTESTINO DELGADO (SMALL BOWEL) ===
    "INTESTINO":[re.compile(p,re.I) for p in [
        r"\bbowel[_\s-]?small\b",
        r"\bsmall\s*bowel\b",
        r"\bintestino\s+delgado\b",
        r"\bintestino(?!\s+grueso)\b",      # “intestino” solo = delgado
        r"\bduoden(?:o|um)\b",
        r"\byeyun(?:o|um)\b",
        r"\bíle(?:on|um)\b",
    ]],

    # === CTV (igual que ya tenías) ===
    "CTV":[re.compile(p,re.I) for p in [
        r"\bCTV\b",
        r"\bCTV[_\s-]*HR\b",
        r"\bHR[_\s-]*CTV\b",
        r"\bCTVHR\b",
        r"\bCTV[_\s-]*(uterus|utero|útero)\b",
        r"\bvolumen\s*cl[ií]nico"
    ]]
}
  # --- Normalizador de nombres ROI: quita prefijo numérico tipo "1_", "2- ", "3 "
def _normalize_roi_token(s: str) -> str:
    # Pasamos a minúsculas, quitamos espacios y sacamos números iniciales con guiones/underscores
    return re.sub(r'^\s*\d+[_\s\-]*', '', s.strip().lower())
# ====== Helpers de UI ======
CSS = """
:root { --bg:#0f172a; --card:#111827; --muted:#94a3b8; --text:#e5e7eb; --acc:#22d3ee; --acc2:#38bdf8; --err:#f87171; --ok:#34d399; }
*{box-sizing:border-box} body{margin:0;font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Arial;background:radial-gradient(1200px 800px at 20% -10%,#0b1b2b 0%,var(--bg) 45%),var(--bg);color:var(--text)}
.container{max-width:980px;margin:40px auto;padding:0 20px}
.card{background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(255,255,255,.02));border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:24px;box-shadow:0 10px 40px rgba(0,0,0,.25)}
h1{margin:0 0 10px;font-size:24px}
.lead{margin:0 0 18px;color:var(--muted)}
.row{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
.grid{display:grid;gap:12px;grid-template-columns:repeat(2,minmax(0,1fr))}
.grid-5{display:grid;gap:12px;grid-template-columns:repeat(5,minmax(0,1fr))}
.input, textarea{width:100%;padding:10px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:#0b1220;color:var(--text)}
textarea{min-height:140px; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;}
.btn{appearance:none;border:none;padding:12px 16px;border-radius:12px;font-weight:600;cursor:pointer}
.btn-primary{background:linear-gradient(180deg,var(--acc),var(--acc2));color:#05232f}
.table{width:100%;border-collapse:collapse;margin-top:16px}
.table th,
.table td {
  padding:10px;
  border:1px solid rgba(255,255,255,.15); /* línea fina en todas las celdas */
  text-align:left;
  font-size:14px;
}
.table {
  border-collapse: collapse;
  border:1px solid rgba(255,255,255,.25); /* borde exterior un poquito más fuerte */
}
.section{margin-top:22px}
.section h3{margin:6px 0 8px 0;color:#a5f3fc;font-size:18px}
.note{color:#94a3b8;font-size:12px}
.warn{color:var(--err);font-weight:600}
.ok{color:var(--ok);font-weight:600}
.fixed{opacity:.9}
.small{font-size:12px;color:var(--muted)}
.patient-info {
  font-size: 16px;
  color: #fb923c;
  font-weight: 600;
  margin: 6px 0 12px 0;
}
.table th[colspan] {
  text-align: center;
}
/* Resaltar ROI + EQD2 TOTAL */

.table-plan thead tr:first-child th:nth-child(1),
.table-plan thead tr:first-child th:nth-child(2),
.table-plan tbody td:nth-child(1),
.table-plan tbody td:nth-child(2) {
  font-weight: 700;
  font-size: 16px;
  color: #22d3ee;  /* turquesa */
}


"""


PAGE = """
<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>RT Externa → Dmax HDR + Plan Real</title><style>{{css}}</style></head>
<body><div class="container"><div class="card">
  <h1><span style="color:#67e8f9">Pipeline</span> <span class="badge">DVH → Resultados → Oncentra</span></h1>
 <div class="lead">
  <p><strong>Paso 1:</strong> cargá el <b>DVH acumulado de RT externa Eclipse</b>.</p>
  <p><strong>Paso 2:</strong> cargá el <b>DVH de HDR de Oncentra</b>.</p>
</div>

  <!-- PASO 1 -->
  <form method="post" action="/cargar_dvh" enctype="multipart/form-data">
    <div class="section">
      <h3>Paso 1 — Cargar DVH</h3>
      <div class="grid">
       <label>N sesiones RT externa
       <input class="input" type="number" name="fx_rt" min="1" step="1" value="{{fx_rt}}">
       </label>
<label>N sesiones HDR
  <input class="input" type="number" name="n_hdr" min="1" step="1" value="{{n_hdr}}">
</label>

      </div>
      <div class="row" style="margin-top:8px">
        <label>Archivo DVH (texto .txt de Eclipse)
          <input class="input" type="file" name="dvhfile" accept=".txt,.dvh,.csv,.log,.dat,.*">
        </label>
      </div>
      <div class="row" style="margin-top:12px">
        <button class="btn btn-primary" type="submit">Cargar</button>
      </div>
    </div>
  </form>

  {% if step1 %}
  <div class="section">
    <h3>Resultados (RT Externa → Dmax/sesión HDR)</h3>
    {% if patient_name or patient_id %}
  <p class="patient-info">
  <b>Paciente:</b> {{ patient_name or "—" }} &nbsp;&nbsp;
  <b>ID:</b> {{ patient_id or "—" }}
</p>
{% endif %}

<table class="table">
 <thead>
  <tr>
    <th>Órgano</th>
    <th>D2cc RT ext (Gy)</th>
    <th>EQD2 RT ext (Gy)</th>
    <th>D máx/sesión (Gy)</th>
  </tr>
</thead>

  <tbody>
  {% for r in results %}
  <tr>
    <td>{{ r.roi }}</td>

   <td>
  {{ r.D_ext if r.D_ext is not none else "-" }}
  {% if r.is_ctv_d95 %}<span class="small">(D95)</span>{% endif %}
</td>

<td>
  {% if r.eqd2_ext is not none %}
    {{ "%.2f"|format(r.eqd2_ext) }}
  {% else %}
    —
  {% endif %}
</td>

  <td>
    {% if r.is_ctv_d95 %}
      —
    {% else %}
      {{ "%.2f"|format(r.dmax_session) }}
    {% endif %}
  </td>
</tr>

  </tr>
  {% endfor %}
</tbody>

</table>
    <p class="note">EQD2 EBRT = D_total · (1 + d_rt/αβ) / (1 + 2/αβ). Dmax/sesión resuelve la cuadrática con el remanente.</p>
  </div>

  <!-- PASO 2 -->
    <!-- PASO 2 -->
  <form method="post" action="/calcular_hdr" enctype="multipart/form-data">
    <input type="hidden" name="fx_rt" value="{{fx_rt}}">
    <input type="hidden" name="n_hdr" value="{{n_hdr}}">
    <input type="hidden" name="patient_name" value="{{patient_name or ''}}">
    <input type="hidden" name="patient_id"   value="{{patient_id or ''}}">
   {% for r in results if not r.is_ctv_d95 %}
  <input type="hidden" name="EBRT_{{loop.index0}}_roi"   value="{{ r.roi }}">
  <input type="hidden" name="EBRT_{{loop.index0}}_eqd2"  value="{{ ('%.4f'|format(r.eqd2_ext)) if r.eqd2_ext is not none else '' }}">
  <input type="hidden" name="EBRT_{{loop.index0}}_limit" value="{{ ('%.2f'|format(r.limit))    if r.limit    is not none else '' }}">
  <input type="hidden" name="EBRT_{{loop.index0}}_dext"  value="{{ r.D_ext if r.D_ext is not none else '' }}">
{% endfor %}

{# CTV (D95) SOLO una vez #}
{% set ctv_list = results | selectattr('is_ctv_d95') | list %}
{% if ctv_list %}
  {% if ctv_list[0].D_ext %}
    <input type="hidden" name="EBRT_CTV_D95"  value="{{ ctv_list[0].D_ext }}">
  {% endif %}
  {% if ctv_list[0].eqd2_ext is not none %}
    <input type="hidden" name="EBRT_CTV_EQD2" value="{{ '%.4f'|format(ctv_list[0].eqd2_ext) }}">
  {% endif %}
{% endif %}




    <div class="section">
      <h3>Paso 2 — Cargar DVH de HDR (Oncentra)</h3>
      <p class="small">Subí el DVH de Oncentra en modo <b>acumulado</b> (Gy/ccm). Tomamos <b>D@2cc</b> para VEJIGA, RECTO, SIGMOIDE e INTESTINO, y lo replicamos en {{n_hdr}} fracciones.</p>
      <label>Archivo DVH HDR (texto .txt de Oncentra)
        <input class="input" type="file" name="hdrfile" accept=".txt,.dvh,.csv,.log,.dat,.*">
      </label>
      <div class="row" style="margin-top:12px">
        <button class="btn btn-primary" type="submit">Calcular</button>
      </div>
    </div>
  </form>

  {% endif %}

{% if plan_real %}
  <div class="section">
    <h3>Plan Real Completo RT Externa + HDR</h3>
    {% if patient_name or patient_id %}
      <p class="patient-info">
        <b>Paciente:</b> {{ patient_name or "—" }} &nbsp;&nbsp;
        <b>ID:</b> {{ patient_id or "—" }}
      </p>
    {% endif %}
   <table class="table table-plan">
  <thead>
    <tr>
      <th rowspan="2">Órganos</th>
      <th rowspan="2">EQD2 TOTAL (Gy)</th>   <!-- ← LA MOVEMOS ACÁ -->
      <th colspan="{{n_hdr*2}}">Fracciones</th>
      <th rowspan="2">Total (Gy)</th>
      <th rowspan="2">EQD2 HDR (Gy)</th>
      <th rowspan="2">EQD2 Rt Externa (Gy)</th>
      <th rowspan="2">Límite (Gy)</th>
      <th rowspan="2">Estado</th>
    </tr>
    <tr>
      {% for i in range(1, n_hdr+1) %}
        <th>Dosis {{i}}</th>
        <th>EQD2 {{i}}</th>
      {% endfor %}
    </tr>
  </thead>
  <tbody>
    {% for r in plan_real %}
    <tr>
      <td>{{r.roi}}</td>
      <td>{{"%.2f"|format(r.eqd2_total)}}</td>   <!-- ← NUEVA 2DA COLUMNA -->
      {% for i in range(n_hdr) %}
        <td>{{"%.2f"|format(r.doses[i])}}</td>
        <td>{{"%.2f"|format(r.eqd2s[i])}}</td>
      {% endfor %}
      <td>{{"%.2f"|format(r.total_dose)}}</td>
      <td>{{"%.2f"|format(r.eqd2_hdr_total)}}</td>
      <td>{{"%.2f"|format(r.eqd2_ebrt)}}</td>
      <td>
        {% if r.limit is not none %}
          {{"%.2f"|format(r.limit)}}
        {% else %}
          —
        {% endif %}
      </td>
      <td>
        {% if r.is_ctv %}
          —
        {% else %}
          {% if r.eqd2_total <= r.limit %}
            <span class="ok">✅ Con margen</span>
          {% else %}
            <span class="warn">� ️ Excede</span>
          {% endif %}
        {% endif %}
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>

 
    <p class="note">EQD2 por fracción con α/β=3. “Total (Gy)” suma las dosis por fracción; “EQD2 HDR” suma los EQD2 por fracción; “EQD2 TOTAL” = EQD2 EBRT + EQD2 HDR.</p>
  </div>
    <div class="section">
    <h3>Resumen dosimétrico (datos clave)</h3>
    <table class="table">
      <thead>
        <tr>
          <th>Órgano</th>
          <th>EQD2 RT Externa (Gy)</th>
          <th>EQD2 HDR (Gy)</th>
          <th>EQD2 TOTAL (Gy)</th>
        </tr>
      </thead>
      <tbody>
        {% for r in plan_summary %}
        <tr>
          <td>{{ r.roi }}</td>
          <td>{{ "%.2f"|format(r.eqd2_ebrt) }}</td>
          <td>{{ "%.2f"|format(r.eqd2_hdr) }}</td>
          <td>{{ "%.2f"|format(r.eqd2_total) }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <p class="note">La tabla muestra solo valores clave por órgano: EQD2 de RT externa, EQD2 acumulado de HDR y la suma (EQD2 TOTAL).</p>
  </div>
{% endif %}
</div></div></body></html>

"""

# ====== Física ======
def eqd2_from_total_with_fraction(D_total, d_per_fx, ab):
    return (D_total * (1.0 + d_per_fx/ab)) / (1.0 + 2.0/ab)

def eqd2_from_single_fraction(d, ab):
    return (d + d*d/ab) / (1.0 + 2.0/ab)

def solve_hdr_dose_per_session(eqd2_remaining, N, ab):
    if eqd2_remaining <= 0 or N <= 0: return 0.0
    t = eqd2_remaining / float(N)
    A = 1.0/ab; C = - t * (1.0 + 2.0/ab)
    disc = 1.0 - 4.0*A*C
    if disc < 0: return 0.0
    d = (-1.0 + math.sqrt(disc)) / (2.0*A)
    return max(0.0, d)
# ====== Normalización de etiquetas ES→EN (para DVH de Eclipse) ======
import re as _re

_norm_rules = [
    # Bloques / metadatos
    (r'^\s*Estructura\s*:',                 'Structure:',  _re.I),
    (r'^\s*Estado\s+de\s+la\s+aprobación\s*:', 'Approval Status:', _re.I),
    (r'^\s*Nombre\s+de\s+paciente\s*:',     'Patient Name         :', _re.I),
    (r'^\s*ID\s+paciente\s*:',              'Patient ID           :', _re.I),
    (r'^\s*Descripción\s*:',                'Description          :', _re.I),

    # Cabecera de tabla DVH
    (r'^\s*Dosis\s*\[\s*cGy\s*\]',          'Dose [cGy]', _re.I),
    (r'Dosis\s+relativa\s*\[\s*%\s*\]',      'Relative dose [%]', _re.I),
    (r'Volumen\s+de\s+estructura\s*\[\s*cm³\s*\]', 'Structure Volume [cm³]', _re.I),
]

def normalize_labels(text: str) -> str:
    """Convierte etiquetas en español a las que tu parser ya entiende (inglés)."""
    lines = text.splitlines()
    out = []
    for ln in lines:
        s = ln
        for pat, rep, flags in _norm_rules:
            s = _re.sub(pat, rep, s, flags=flags)
        out.append(s)
    return "\n".join(out)



# ====== Parsers ======
def fnum(s, default=0.0):
    if s is None: return default
    s = str(s).strip().replace(",", ".")
    if s == "": return default
    try: return float(s)
    except: return default

def parse_eclipse_dvh_text(txt):
    """Devuelve {name:[(dose_Gy, vol_cc), ...]}"""
    structures = {}
    for m in re.finditer(r"Structure:\s*(.+?)\n(.*?)(?=\nStructure:|\Z)", txt, re.S):
        name = m.group(1).strip()
        block = m.group(2)
        if not re.search(r"Dose\s*\[(?:cGy|Gy)\].*Structure Volume", block, re.I):
            continue
        dose_in_cgy = bool(re.search(r"Dose\s*\[cGy\]", block, re.I))
        data = []
        for line in block.splitlines():
            if not re.search(r"\d", line): continue
            nums = re.findall(r"[-+]?\d*[\.,]?\d+", line)
            if len(nums) >= 3:
                d = float(nums[0].replace(",", "."))
                v = float(nums[2].replace(",", "."))
                if dose_in_cgy: d /= 100.0
                data.append((d, v))
        if data: structures[name] = data
    return structures
def parse_oncentra_dvh_text(txt):
    """
    Devuelve {name:[(dose_Gy, vol_cc), ...]} para archivos DVH de Oncentra.
    Formato esperado:
      ROI: <nombre>
      **************************
      Bin   Dose   Volume
      ...
    """
    structures = {}
    for m in re.finditer(r"ROI:\s*([^\r\n]+)\s*\n\*+\s*\n(.*?)(?=\nROI:|\Z)", txt, re.S | re.I):
        name = m.group(1).strip()
        block = m.group(2)
        data = []
        for line in block.splitlines():
            nums = re.findall(r"[-+]?\d*[\.,]?\d+", line)
            if len(nums) >= 3:
                d = float(nums[-2].replace(",", "."))  # Dose [Gy]
                v = float(nums[-1].replace(",", "."))  # Volume [ccm]
                data.append((d, v))
        if data:
            structures[name] = data
    return structures


def parse_patient_meta(txt):
    """Extrae nombre e ID si vienen en ES o EN."""
    name, pid = None, None

    # name
    m = re.search(r'(?:Patient\s*Name|Nombre\s+de\s+paciente)\s*:\s*([^\r\n]+)', txt, re.I)
    if m:
        raw_name = m.group(1).strip()
        clean = re.sub(r'\s*\([^)]*\)', '', raw_name).strip()
        clean = re.sub(r'\s*,\s*$', '', clean)
        name = clean if clean else raw_name

    # id
    m = re.search(r'(?:Patient\s*ID|ID\s+paciente)\s*:\s*([^\r\n]+)', txt, re.I)
    if m:
        raw_id = m.group(1).strip()
        mnum = re.search(r'[\w-]+', raw_id)
        pid = mnum.group(0) if mnum else raw_id

    return name, pid



def dose_at_volume_cc(data, target_cc):
    for i, (d1, v1) in enumerate(data):
        if v1 <= target_cc:
            if i == 0: return d1
            d0, v0 = data[i-1]
            if v0 == v1: return d1
            frac = (target_cc - v0) / (v1 - v0)
            return d0 + (d1 - d0) * frac
    return None

def map_roi(name):
    low = name.lower()
    for k, pats in ALIASES.items():
        if any(p.search(low) for p in pats): return k
    for k in ("VEJIGA","RECTO","SIGMOIDE","INTESTINO","CTV"):
        if k.lower() in low: return k
    return None

def parse_planner_paste(text):
    """Devuelve filas (roi,dose_gy,vol_cc,mapped) para Volume≈2cc."""
    rows = []
    for raw in text.splitlines():
        if not raw.strip(): continue
        parts = re.split(r"[|;\t]|(?<!\d)\s{2,}(?!\d)", raw.strip())
        if len(parts) < 2: parts = raw.strip().split()
        nums = re.findall(r"[-+]?\d*[\.,]?\d+", raw)
        if len(nums) < 2: continue
        vol_cc = fnum(nums[-1]); dose_gy = fnum(nums[-2])
        roi = parts[0].strip()
        if abs(vol_cc - 2.0) > 0.15: continue
        rows.append({"roi":roi, "dose_gy":dose_gy, "vol_cc":vol_cc, "mapped":map_roi(roi)})
    return rows

# === NUEVO: Dosis en el p% del volumen (p.ej., D90) con registro más cercano e interpolación ===
def dose_at_percent_volume(data, percent):
    """
    data: lista de (dose_Gy, vol_cc) de un DVH acumulado (volumen decrece con la dosis).
    percent: porcentaje de volumen (ej. 90 para D90).
    Devuelve (dose_Gy, Vtotal_cc, Vtarget_cc). Usa interpolación lineal si hay cruce;
    si no hay cruce, toma el registro más cercano.
    """
    if not data: 
        return None, None, None
    # Aseguramos orden por dosis ascendente (típico en exportes)
    data_sorted = sorted(data, key=lambda x: x[0])
    Vtot = max(v for _, v in data_sorted)
    Vtarget = Vtot * (percent / 100.0)

    # Primero intentamos con interpolación exacta entre los dos puntos que rodean Vtarget
    for i in range(1, len(data_sorted)):
        d0, v0 = data_sorted[i-1]
        d1, v1 = data_sorted[i]
        # buscamos cruce: v0 >= Vtarget >= v1 (DVH acumulado: v desciende con dosis)
        if (v0 >= Vtarget >= v1) or (v1 >= Vtarget >= v0):
            if v1 == v0:
                # plano horizontal raro; devolvemos el más cercano por dosis
                return d1, Vtot, Vtarget
            frac = (Vtarget - v0) / (v1 - v0)
            d = d0 + (d1 - d0) * frac
            return d, Vtot, Vtarget

    # Si no hubo cruce (datos muy gruesos), elegimos el volumen más cercano
    idx = min(range(len(data_sorted)), key=lambda i: abs(data_sorted[i][1] - Vtarget))
    d_closest = data_sorted[idx][0]
    return d_closest, Vtot, Vtarget

# ====== Estado en memoria simple (para demo) ======
def build_organs_autofill(d2map):
    rows=[]
    for key,label in [("VEJIGA","Vejiga"),("RECTO","Recto"),("SIGMOIDE","Sigmoide"),("INTESTINO","Intestino")]:
        rows.append({"key":key.lower(),"label":label,"autoval":("" if d2map.get(key) is None else f"{d2map[key]:.2f}"),"limit":LIMITS_EQD2[key]})
    return rows

# ====== Rutas ======
@app.route("/", methods=["GET"])
def home():
    return render_template_string(PAGE, css=CSS, fx_rt=25, n_hdr=3, step1=False,
                                  # === NUEVO: valores nulos de CTV para no romper contexto
                                  ctv_volume_total=None, ctv_d90_gy=None, ctv_d90_cgy=None)

@app.route("/cargar_dvh", methods=["POST"])
def cargar_dvh():
    fx_rt = int(fnum(request.form.get("fx_rt"), 25))
    n_hdr = int(fnum(request.form.get("n_hdr"), 3))

    d2_autofill = {}
    patient_name, patient_id = None, None
    ctv_d95_gy = None  # ← inicializamos fuera de cualquier if/for
    tables = {}

    file = request.files.get("dvhfile")
    if file and file.filename:
        raw = file.read().decode("latin1", errors="ignore")
        txt = normalize_labels(raw)


        # Extraer paciente/ID
        patient_name, patient_id = parse_patient_meta(txt)

        # Parse DVH de Eclipse
        tables = parse_eclipse_dvh_text(txt)

        # Índice para matching de nombres
        idx = {name.lower(): name for name in tables.keys()}

        def find_match(target: str):
            for low, orig in idx.items():
                low_norm = _normalize_roi_token(low)  # normalizamos antes de probar
                if any(p.search(low_norm) for p in ALIASES[target]):
                   return orig
            return None

        # ---- OARs (D@2cc)
        for organ in ("VEJIGA", "RECTO", "SIGMOIDE", "INTESTINO"):
            nm = find_match(organ)
            d2 = dose_at_volume_cc(tables[nm], 2.0) if nm else None
            d2_autofill[organ] = round(d2, 2) if d2 is not None else None

        # ---- CTV (D95 = dosis al 95% del volumen total)
        nm_ctv = find_match("CTV")
        if nm_ctv:
            d95, Vtot, Vtarget = dose_at_percent_volume(tables[nm_ctv], 95.0)
            if d95 is not None:
                ctv_d95_gy = round(d95, 2)

    # ------------------ Armar resultados Tabla 1 ------------------
    results = []
    Row = lambda **k: type("Row", (), k)

    for organ, label in [
        ("VEJIGA", "Vejiga"),
        ("RECTO", "Recto"),
        ("SIGMOIDE", "Sigmoide"),
        ("INTESTINO", "Intestino"),
    ]:
        D_ext = d2_autofill.get(organ)
        ab = 3.0
        limit = LIMITS_EQD2[organ]
        d_rt = (D_ext / fx_rt) if (D_ext is not None and fx_rt > 0) else 0.0
        eqd2_ext = eqd2_from_total_with_fraction(D_ext, d_rt, ab) if D_ext is not None else 0.0
        hdr_prev = 0.0
        used = eqd2_ext + hdr_prev
        rem = max(0.0, limit - used)
        dmax = solve_hdr_dose_per_session(rem, n_hdr, ab)
        flag = "ok" if rem > 0 else "warn"

        results.append(
            Row(
                roi=label,
                D_ext=(f"{D_ext:.2f}" if D_ext is not None else None),
                fx_rt=fx_rt,
                d_rt=d_rt,
                ab=ab,
                eqd2_ext=eqd2_ext,
                hdr_prev=hdr_prev,
                used=used,
                limit=limit,
                rem=rem,
                N=n_hdr,
                dmax_session=dmax,
                flag=flag,
                is_ctv_d95=False,
            )
        )

    # ---- Fila extra: CTV (D95) en Tabla 1 (muestra D95 y su EQD2 EBRT; el resto va con “—”)
    if ctv_d95_gy is not None:
        d_per_fx_ctv = (ctv_d95_gy / fx_rt) if fx_rt > 0 else 0.0
        eqd2_ctv_ext = eqd2_from_total_with_fraction(ctv_d95_gy, d_per_fx_ctv, 10.0)

        results.append(
            Row(
                roi="CTV (D95)",
                D_ext=f"{ctv_d95_gy:.2f}",   # mostramos el D95
                fx_rt=fx_rt,
                d_rt=d_per_fx_ctv,
                ab=10.0,
                eqd2_ext=eqd2_ctv_ext,       # EQD2 RT ext del CTV (α/β=10)
                hdr_prev=0.0,
                used=0.0,
                limit=None,                  # guion en plantilla
                rem=None,
                N=n_hdr,
                dmax_session=None,           # guion en plantilla
                flag=None,                   # guion en plantilla
                is_ctv_d95=True,
            )
        )
        order_display = ["CTV (D95)", "Recto", "Vejiga", "Sigmoide", "Intestino"]
    results.sort(key=lambda r: order_display.index(r.roi) if r.roi in order_display else 999)   
        
            
    # ------------------ Render ------------------
    return render_template_string(
        PAGE,
        css=CSS,
        fx_rt=fx_rt,
        n_hdr=n_hdr,
        step1=True,
        results=results,
        patient_name=patient_name,
        patient_id=patient_id,
        # placeholders para paneles CTV (no usamos aquí)
        ctv_volume_total=None,
        ctv_d90_gy=None,
        ctv_d90_cgy=None,
    )




@app.route("/calcular_hdr", methods=["POST"])
def calcular_hdr():
    fx_rt = int(fnum(request.form.get("fx_rt"), 25))
    n_hdr = int(fnum(request.form.get("n_hdr"), 3))

    # ---------- 1) Recuperar EBRT del Paso 1 (incluye D2cc y límite) ----------
    ebrt = []
    for i in range(4):
        roi = request.form.get(f"EBRT_{i}_roi")
        if not roi:
            continue
        ebrt.append({
            "roi":   roi,
            "eqd2":  fnum(request.form.get(f"EBRT_{i}_eqd2")),
            "limit": fnum(request.form.get(f"EBRT_{i}_limit")) if request.form.get(f"EBRT_{i}_limit") else None,
            "dext":  request.form.get(f"EBRT_{i}_dext") or None,  # D2cc RT ext (Gy) como string
        })

    # CTV (D95) de EBRT si lo mandamos por hidden
    ctv_d95_hidden  = request.form.get("EBRT_CTV_D95")
    ctv_eqd2_hidden = request.form.get("EBRT_CTV_EQD2")

    # Mapa de límites (OARs)
    limits_map = {
        "Vejiga":    LIMITS_EQD2["VEJIGA"],
        "Recto":     LIMITS_EQD2["RECTO"],
        "Sigmoide":  LIMITS_EQD2["SIGMOIDE"],
        "Intestino": LIMITS_EQD2["INTESTINO"],
    }

    # Paciente/ID (pasados desde Paso 1)
    patient_name = request.form.get("patient_name") or None
    patient_id   = request.form.get("patient_id") or None

    # ---------- 2) Leer DVH HDR de Oncentra ----------
    hdrfile = request.files.get("hdrfile")
    hdr_d2 = {}  # D@2cc por órgano (Gy)

    # Resultados CTV (D90) para HDR (opcional)
    ctv_volume_total = None
    ctv_d90_gy = None
    ctv_d90_cgy = None

    if hdrfile and hdrfile.filename:
        txt = hdrfile.read().decode("latin1", errors="ignore")
        tables = parse_oncentra_dvh_text(txt)

        idx = {name.lower(): name for name in tables.keys()}

        def find_match(target):
            for low, orig in idx.items():
                low_norm = _normalize_roi_token(low)  # ← normalizamos antes de probar
                if any(p.search(low_norm) for p in ALIASES[target]):
                    return orig
            return None

        # OARs HDR: D@2cc
        for key in ("VEJIGA", "RECTO", "SIGMOIDE", "INTESTINO"):
            nm = find_match(key)
            d2 = dose_at_volume_cc(tables[nm], 2.0) if nm else None
            if d2 is not None:
                hdr_d2[key] = round(d2, 2)

        # CTV HDR: D90
        nm_ctv = find_match("CTV")
        if nm_ctv:
            d90, Vtot, Vtarget = dose_at_percent_volume(tables[nm_ctv], 90.0)
            if d90 is not None:
                ctv_volume_total = float(Vtot) if Vtot is not None else None
                ctv_d90_gy = float(d90)
                ctv_d90_cgy = float(d90) * 100.0

    # ---------- 3) Construir Plan HDR (tabla de abajo) ----------
    plan = []
    Row = lambda **k: type("Row", (), k)

    # 3.a) Primero CTV si existe (D90 HDR + D95 EBRT)
    if ctv_d90_gy is not None:
        doses_ctv = [ctv_d90_gy] * n_hdr
        eqd2s_ctv = [eqd2_from_single_fraction(d, 10.0) for d in doses_ctv]
        eqd2_hdr_ctv_total = sum(eqd2s_ctv)
        eqd2_ebrt_ctv = float(ctv_eqd2_hidden) if ctv_eqd2_hidden else 0.0

        plan.append(Row(
            roi="CTV (D90)",
            doses=doses_ctv,
            eqd2s=eqd2s_ctv,
            total_dose=sum(doses_ctv),
            eqd2_hdr_total=eqd2_hdr_ctv_total,
            eqd2_ebrt=eqd2_ebrt_ctv,
            eqd2_total=eqd2_ebrt_ctv + eqd2_hdr_ctv_total,
            limit=None,
            is_ctv=True
        ))

    # 3.b) Luego resto de órganos en el orden pedido
    order = [("RECTO","Recto"), ("VEJIGA","Vejiga"), ("SIGMOIDE","Sigmoide"), ("INTESTINO","Intestino")]

    for key, display in order:
        dose = hdr_d2.get(key, 0.0)
        doses = [dose] * n_hdr
        eqd2s = [eqd2_from_single_fraction(d, 3.0) for d in doses]
        total_dose = sum(doses)
        eqd2_hdr_total = sum(eqd2s)
        eqd2_ebrt = next((item["eqd2"] for item in ebrt if item["roi"] == display), 0.0)
        eqd2_total = eqd2_ebrt + eqd2_hdr_total
        limit = limits_map[display]

        plan.append(Row(
            roi=display,
            doses=doses,
            eqd2s=eqd2s,
            total_dose=total_dose,
            eqd2_hdr_total=eqd2_hdr_total,
            eqd2_ebrt=eqd2_ebrt,
            eqd2_total=eqd2_total,
            limit=limit
        ))
    # ---------- 3.c) Resumen dosimétrico (tabla simple) ----------
    plan_summary = []
    for r in plan:
        plan_summary.append({
            "roi": ("CTV (D90)" if getattr(r, "is_ctv", False) else r.roi),
            "eqd2_ebrt": r.eqd2_ebrt,          # EQD2 RT Externa
            "eqd2_hdr":  r.eqd2_hdr_total,     # EQD2 HDR
            "eqd2_total": r.eqd2_total,        # suma
        })

    # Orden igual al resto
    order_display = ["CTV (D90)", "Recto", "Vejiga", "Sigmoide", "Intestino"]
    plan_summary.sort(key=lambda x: order_display.index(x["roi"]) if x["roi"] in order_display else 999)

    # ---------- 4) Reconstruir Tabla 1 COMPLETA (arriba) ----------
    results = []
    for item in ebrt:
        roi   = item["roi"]
        eqd2  = item["eqd2"]
        limit = item["limit"]
        dext  = item["dext"]  # texto "xx.xx" o None

        if limit is not None:
            rem  = max(0.0, limit - eqd2)
            dmax = solve_hdr_dose_per_session(rem, n_hdr, 3.0)
            flag = "ok" if rem > 0 else "warn"
        else:
            rem = dmax = flag = None

        results.append(type("Row", (), {
            "roi": roi,
            "D_ext": dext,          # ← repinta D2cc
            "fx_rt": fx_rt,
            "d_rt": 0.0,
            "ab": 3.0,
            "eqd2_ext": eqd2,
            "hdr_prev": 0.0,
            "used": eqd2,
            "limit": limit,
            "rem": rem,
            "N": n_hdr,
            "dmax_session": dmax,
            "flag": flag,
            "is_ctv_d95": False,
        }))

    # CTV (D95) UNA sola vez si vino
    if ctv_d95_hidden and not any(getattr(r, "is_ctv_d95", False) for r in results):
        results.append(type("Row", (), {
            "roi": "CTV (D95)",
            "D_ext": ctv_d95_hidden,
            "fx_rt": fx_rt,
            "d_rt": 0.0,
            "ab": 10.0,
            "eqd2_ext": (float(ctv_eqd2_hidden) if ctv_eqd2_hidden else None),
            "hdr_prev": 0.0,
            "used": 0.0,
            "limit": None,
            "rem": None,
            "N": n_hdr,
            "dmax_session": None,
            "flag": None,
            "is_ctv_d95": True,
        }))

    # (Opcional) Ordenar la tabla de arriba con el mismo criterio visual
    order_display = ["CTV (D95)", "Recto", "Vejiga", "Sigmoide", "Intestino"]
    results.sort(key=lambda r: order_display.index(r.roi) if getattr(r, "roi", None) in order_display else 999)

    # ---------- 5) Render ----------
    return render_template_string(
        PAGE,
        css=CSS,
        fx_rt=fx_rt,
        n_hdr=n_hdr,
        step1=True,
        results=results,
        plan_real=plan,
        plan_summary=plan_summary,
        patient_name=patient_name,
        patient_id=patient_id,
        ctv_volume_total=ctv_volume_total,
        ctv_d90_gy=ctv_d90_gy,
        ctv_d90_cgy=ctv_d90_cgy
    )


    # Re-render de resultados paso 1 (arriba)
    results = []
    for (roi, eqd2) in ebrt:
        limit = limits_map[roi]
        rem = max(0.0, limit - eqd2)
        dmax = solve_hdr_dose_per_session(rem, n_hdr, 3.0)
        results.append(type("Row", (), {
            "roi": roi, "D_ext": "-", "fx_rt": fx_rt, "d_rt": 0.0, "ab": 3.0,
            "eqd2_ext": eqd2, "hdr_prev": 0.0, "used": eqd2, "limit": limit,
            "rem": rem, "N": n_hdr, "dmax_session": dmax,
            "flag": "ok" if rem > 0 else "warn"
        }))

    # Render
    return render_template_string(
        PAGE, css=CSS, fx_rt=fx_rt, n_hdr=n_hdr,
        step1=True, results=results, plan_real=plan,
        patient_name=patient_name, patient_id=patient_id,
        ctv_volume_total=ctv_volume_total, ctv_d90_gy=ctv_d90_gy, ctv_d90_cgy=ctv_d90_cgy
    )

if __name__ == "__main__":
    print(">> Booting Flask on http://127.0.0.1:5000  (use_reloader=False)")
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    except Exception as e:
        import traceback
        print(">> Flask crashed!")
        traceback.print_exc()
        raise
