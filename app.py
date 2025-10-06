import math, re
from flask import Flask, request, render_template_string
import pytesseract  # ← no usamos OCR aquí, solo queda configurado si más adelante lo necesitás

# Ajustá la ruta si tu tesseract.exe está en otro lugar (esta es la que vos encontraste)
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\Julieta\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

app = Flask(_name_)

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
        r"\bcolon\b",
        r"\bcolon[_\s-]*sigmoid[eo]\b",
        r"\brecto[_\s-]*sigmoid[eo]\b",
        r"\brectosigmoid[eo]\b",
        r"\bintestino\s+grueso\b",
        r"\bbowel[_\s-]?large\b",
    ]],

    # === INTESTINO DELGADO (SMALL BOWEL) ===
    "INTESTINO":[re.compile(p,re.I) for p in [
        r"\bbowel[_\s-]?small\b",
        r"\bsmall\s*bowel\b",
        r"\bintestino\s+delgado\b",
        r"\bintestino(?!\s+grueso)\b",
        r"\bduoden(?:o|um)\b",
        r"\byeyun(?:o|um)\b",
        r"\bíle(?:on|um)\b",
    ]],

    # === CTV ===
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
.table td { padding:10px; border:1px solid rgba(255,255,255,.15); text-align:left; font-size:14px; }
.table { border-collapse: collapse; border:1px solid rgba(255,255,255,.25); }
.section{margin-top:22px}
.section h3{margin:6px 0 8px 0;color:#a5f3fc;font-size:18px}
.note{color:#94a3b8;font-size:12px}
.warn{color:var(--err);font-weight:600}
.ok{color:var(--ok);font-weight:600}
.fixed{opacity:.9}
.small{font-size:12px;color:var(--muted)}
.eqd2-ok { color: #34d399; font-weight: 600; }
.eqd2-warn { color: #f87171; font-weight: 600; }
.patient-info { font-size: 16px; color: #fb923c; font-weight: 600; margin: 6px 0 12px 0; }
.table th[colspan] { text-align: center; }
/* === Bold para Resumen dosimétrico === */
.table-summary thead th:first-child,
.table-summary thead th:last-child,
.table-summary tbody td:first-child,
.table-summary tbody td:last-child { font-weight: 700; }

/* Mantener el bold aunque el valor tenga color */
.table-summary tbody td:last-child .eqd2-ok,
.table-summary tbody td:last-child .eqd2-warn { font-weight: 700; }
/* === Aumento global de tipografías (+3pt) === */
:root { --inc: 3pt; } /* cambiá este valor si querés más/menos tamaño */

/* Base */
body { font-size: calc(16px + var(--inc)); }

/* Títulos */
h1 { font-size: calc(24px + var(--inc)); }
.section h3 { font-size: calc(18px + var(--inc)); }

/* Tablas */
.table th,
.table td { font-size: calc(14px + var(--inc)); }

/* Botones y detalles */
.btn { font-size: calc(14px + var(--inc)); }
.patient-info { font-size: calc(16px + var(--inc)); }
.small { font-size: calc(12px + var(--inc)); }


"""

PAGE = """
<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title> Servidor braquiterapia </title><style>{{css}}</style></head>
<body><div class="container"><div class="card">
  <h1><span style="color:#67e8f9"> <span class="badge">Cálculo dosimétrico Braquiterapia </span></h1>
 <div class="lead">
  <p></strong> Este servidor permite subir el plan de radioterapia externa con el fin de calcular cuáles serán las dosis máximas permitidas por sesión en la braquiterapia. Una vez que se planifica la braquiterapia, también es posible ingresar los datos correspondientes para obtener la suma total de dosis en EQD2</b>.</p>
</div>

  <!-- PASO 1 -->
 <form method="post" action="/cargar_dvh" enctype="multipart/form-data">
  <div class="grid">
     <label>Número de sesiones RT externa
       <input class="input" type="number" name="fx_rt" min="1" step="1" value="{{fx_rt}}">
     </label>
     <label>Número de sesiones HDR
       <input class="input" type="number" name="n_hdr" min="1" step="1" value="{{n_hdr}}">
     </label>
     
  </div>
 <p class="small"> Para braquiterapia exclusiva, completar con "1" el número de sesiones RT externa, y continuar al Paso 2. </p>
  <div class="section">
    <h3>Límites por órgano </h3>
    <p class="small"> Los límites por órgano corresponden a las dosis máximas recomendadas en EQD2 para cada estructura de riesgo. Estos valores pueden ser modificados; en ese caso, es necesario volver a cargar los archivos para que los cálculos se actualicen correctamente.</p>
    <table class="table">
      <thead>
        <tr><th>Órgano</th><th>Límite EQD2 (Gy)</th></tr>
      </thead>
      <tbody>
        <tr><td>Vejiga</td><td><input class="input" type="number" step="0.01" name="limit_VEJIGA" value="{{ limits['VEJIGA']|default(85.0,true) }}"></td></tr>
        <tr><td>Recto</td><td><input class="input" type="number" step="0.01" name="limit_RECTO" value="{{ limits['RECTO']|default(75.0,true) }}"></td></tr>
        <tr><td>Sigmoide</td><td><input class="input" type="number" step="0.01" name="limit_SIGMOIDE" value="{{ limits['SIGMOIDE']|default(75.0,true) }}"></td></tr>
        <tr><td>Intestino</td><td><input class="input" type="number" step="0.01" name="limit_INTESTINO" value="{{ limits['INTESTINO']|default(75.0,true) }}"></td></tr>
      </tbody>
    </table>
  </div>

  <div class="section">
    <h3>Paso 1 — Cargar DVH Eclipse</h3>
    <p class="small"> Para extraer el DVH desde Eclipse debe abrirse el histograma de dosis, seleccionar los órganos de riesgo junto con el CTV, configurar la visualización en <i>volumen absoluto</i> y <i>dosis absoluta</i>, y luego utilizar la opción de menú desplegable (<i>clic derecho → Exportar histograma</i>) para generar el archivo.</p>
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
    <h3>Dosis de radioterapia externa y cálculo de la dosis permitida en HDR</h3>
    {% if patient_name or patient_id %}
      <p class="patient-info"><b>Paciente:</b> {{ patient_name or "—" }} &nbsp;&nbsp; <b>ID:</b> {{ patient_id or "—" }}</p>
    {% endif %}

    <table class="table">
  <thead>
    <tr>
      <th>Órgano</th>
      <th>RT Externa (Gy)</th>
      <th>EQD2 RT Externa (Gy)</th>
      <th>Dosis max por sesión (Gy)</th>
    </tr>
  </thead>
  <tbody>
    {% for r in results %}
      <tr>
        <td>
          {{ r.roi }}
          {% if r.is_ctv_d95 %}
            <span class="small">(D95)</span>
          {% else %}
            <span class="small">(D2cc)</span>
          {% endif %}
        </td>
        <td>
          {{ r.D_ext if r.D_ext is not none else "-" }}
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
    {% endfor %}
  </tbody>
</table>
    <p class="note">Nota: EQD2 EBRT = D_total · (1 + d_rt/αβ) / (1 + 2/αβ). Dmax/sesión resuelve la cuadrática con el remanente.</p>
  </div>

  
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
  <h3>Paso 2 — Cargar DVH Oncentra</h3>
  <p class="small">Elegí el número de sesiones y subí un archivo por sesión. El cálculo suma dosis y EQD2 automáticamente.</p>

  <div class="row">
    <label><strong>¿Cuántas sesiones HDR se realizaron?</strong>
      <select class="input" name="n_sesiones" id="n_sesiones">
        <option value="1" selected>1</option>
        <option value="2">2</option>
        <option value="3">3</option>
      </select>
    </label>
  </div>

  <div id="sesion-1" class="card" style="margin-top:12px">
    <h4>Sesión 1</h4>
    <div class="grid">
      <label>Archivo Oncentra (txt)
        <input class="input" type="file" name="hdrfile_1" accept=".txt,.dvh,.csv,.log,.dat,.*" required>
      </label>
    </div>
  </div>

  <div id="sesion-2" class="card" style="margin-top:12px; display:none">
    <h4>Sesión 2</h4>
    <div class="grid">
      <label>Archivo Oncentra (txt)
        <input class="input" type="file" name="hdrfile_2" accept=".txt,.dvh,.csv,.log,.dat,.*">
      </label>
    </div>
  </div>

  <div id="sesion-3" class="card" style="margin-top:12px; display:none">
    <h4>Sesión 3</h4>
    <div class="grid">
      <label>Archivo Oncentra (txt)
        <input class="input" type="file" name="hdrfile_3" accept=".txt,.dvh,.csv,.log,.dat,.*">
      </label>
    </div>
  </div>

  <div class="row" style="margin-top:12px">
    <button class="btn btn-primary" type="submit">Calcular</button>
  </div>

  <script>
  (function(){
    const select = document.getElementById('n_sesiones');
    const blocks = [
      document.getElementById('sesion-1'),
      document.getElementById('sesion-2'),
      document.getElementById('sesion-3')
    ];
    const updateVisibility = () => {
      const n = parseInt(select.value, 10);
      blocks.forEach((b, i) => {
        const visible = (i < n);
        b.style.display = visible ? 'block' : 'none';
        const inp = b.querySelector('input[type="file"]');
        if (inp) inp.required = visible;
        if (!visible && inp) { try { inp.value = ''; } catch(e){} }
      });
    };
    select.addEventListener('change', updateVisibility);
    updateVisibility();
  })();
  </script>
</div>

  {% if plan_real %}
  <div class="section">
    <h3>Dosis tratamiento HDR</h3>
    {% if patient_name or patient_id %}
      <p class="patient-info"><b>Paciente:</b> {{ patient_name or "—" }} &nbsp;&nbsp; <b>ID:</b> {{ patient_id or "—" }}</p>
    {% endif %}
    <table class="table table-plan">
      <thead>
        <tr>
          <th rowspan="2">Órgano</th>
          <th colspan="{{n_hdr*2}}">Fracciones HDR</th>
          <th rowspan="2">Total HDR (Gy)</th>
          <th rowspan="2">EQD2 HDR (Gy)</th>
        </tr>
        <tr>
          {% for i in range(1, n_hdr+1) %}
            <th>Dosis {{i}}</th><th>EQD2 {{i}}</th>
          {% endfor %}
        </tr>
      </thead>
      <tbody>
        {% for r in plan_real %}
         <tr>
            <td>
              {{ r.roi }}
              <span class="small">
               {% if 'CTV' in (r.roi|string).upper() %}(D90){% else %}(D2cc){% endif %}
              </span>
            </td>
            {% for i in range(n_hdr) %}
              <td>{{ "%.2f"|format(r.doses[i]) }}</td>
              <td>{{ "%.2f"|format(r.eqd2s[i]) }}</td>
            {% endfor %}
            <td>{{ "%.2f"|format(r.total_dose) }}</td>
            <td>{{ "%.2f"|format(r.eqd2_hdr_total) }}</td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
    <p class="note">Nota: EQD2 por fracción con α/β=3 (OAR) o α/β=10 (CTV). “EQD2 TOTAL” = EQD2 EBRT + EQD2 HDR.</p>
  </div>  {# cierra la sección Paso 2 #}
</form>  {# <<< FALTABA cerrar el form #}
{% endif %}  {# <<< FALTABA cerrar el if step1 #}

  <div class= "section">
<h3>Resumen dosimétrico del tratamiento completo (Radioterapia externa + HDR)</h3>
{% if patient_name or patient_id %}
  <p class="patient-info">
    <b>Paciente:</b> {{ patient_name or "—" }} &nbsp;&nbsp; <b>ID:</b> {{ patient_id or "—" }}
  </p>
{% endif %}

{# Construimos listas CTV y otros SIN usar 'contains' #}
{% set ns = namespace(ctv=[], otros=[]) %}
{% for it in plan_summary %}
  {% if 'CTV' in (it.roi|string).upper() %}
    {% set ns.ctv = ns.ctv + [it] %}
  {% else %}
    {% set ns.otros = ns.otros + [it] %}
  {% endif %}
{% endfor %}
{% set plan_ordenado = ns.ctv + ns.otros %}

<table class="table table-summary">
  <thead>
    <tr>
      <th>Órgano</th>
      <th>EQD2 RT Externa (Gy)</th>
      <th>EQD2 HDR (Gy)</th>
      <th>EQD2 TOTAL (Gy)</th>
    </tr>
  </thead>
  <tbody>
    {% for r in plan_ordenado %}
      <tr>
        <td>
          {{ r.roi }}
          <span class="small" style="font-weight: normal;">
            {% if 'CTV' in (r.roi|string).upper() %}(D90){% else %}(D2cc){% endif %}
          </span>
        </td>
        <td>{{ "%.2f"|format(r.eqd2_ebrt) }}</td>
        <td>{{ "%.2f"|format(r.eqd2_hdr) }}</td>
        <td>
          {% if r.limit is not none %}
            {% if r.eqd2_total > r.limit %}
              <span class="eqd2-warn">{{ "%.2f"|format(r.eqd2_total) }}</span>
            {% else %}
              <span class="eqd2-ok">{{ "%.2f"|format(r.eqd2_total) }}</span>
            {% endif %}
          {% else %}
            {{ "%.2f"|format(r.eqd2_total) }}
          {% endif %}
        </td>
      </tr>
    {% endfor %}
  </tbody>
</table>

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
    if eqd2_remaining <= 0 or N <= 0:
        return 0.0
    t = eqd2_remaining / float(N)
    A = 1.0/ab
    C = - t * (1.0 + 2.0/ab)
    disc = 1.0 - 4.0*A*C
    if disc < 0:
        return 0.0
    d = (-1.0 + math.sqrt(disc)) / (2.0*A)
    return max(0.0, d)

# ====== Normalización de etiquetas ES→EN (para DVH de Eclipse) ======
import re as _re
_norm_rules = [
    (r'^\s*Estructura\s*:',                 'Structure:',  _re.I),
    (r'^\s*Estado\s+de\s+la\s+aprobación\s*:', 'Approval Status:', _re.I),
    (r'^\s*Nombre\s+de\s+paciente\s*:',     'Patient Name         :', _re.I),
    (r'^\s*ID\s+paciente\s*:',              'Patient ID           :', _re.I),
    (r'^\s*Descripción\s*:',                'Description          :', _re.I),
    (r'^\s*Dosis\s*\[\s*cGy\s*\]',          'Dose [cGy]', _re.I),
    (r'Dosis\s+relativa\s*\[\s*%\s*\]',      'Relative dose [%]', _re.I),
    (r'Volumen\s+de\s+estructura\s*\[\s*cm³\s*\]', 'Structure Volume [cm³]', _re.I),
]
def normalize_labels(text: str) -> str:
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
    Estructura flexible: detecta 'ROI:' y lee hasta el próximo 'ROI:'.
    """
    structures = {}
    # tolerante a líneas separadoras con ****, ----, etc.
    for m in re.finditer(r"ROI:\s*([^\r\n]+)\s*(.*?)(?=\nROI:|\Z)", txt, re.S | re.I):
        name = m.group(1).strip()
        block = m.group(2)
        data = []
        for line in block.splitlines():
            nums = re.findall(r"[-+]?\d*[\.,]?\d+", line)
            if len(nums) >= 2:
                # tomar las dos últimas como (dose, volume)
                d = float(nums[-2].replace(",", "."))
                v = float(nums[-1].replace(",", "."))
                data.append((d, v))
        if data:
            structures[name] = data
    return structures

def parse_patient_meta(txt):
    name, pid = None, None
    m = re.search(r'(?:Patient\s*Name|Nombre\s+de\s+paciente)\s*:\s*([^\r\n]+)', txt, re.I)
    if m:
        raw_name = m.group(1).strip()
        clean = re.sub(r'\s*\([^)]*\)', '', raw_name).strip()
        clean = re.sub(r'\s*,\s*$', '', clean)
        name = clean if clean else raw_name
    m = re.search(r'(?:Patient\s*ID|ID\s+paciente)\s*:\s*([^\r\n]+)', txt, re.I)
    if m:
        raw_id = m.group(1).strip()
        mnum = re.search(r'[\w-]+', raw_id)
        pid = mnum.group(0) if mnum else raw_id
    return name, pid

def dose_at_volume_cc(data, target_cc):
    if not data: return None
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

def dose_at_percent_volume(data, percent):
    if not data:
        return None, None, None
    data_sorted = sorted(data, key=lambda x: x[0])
    Vtot = max(v for _, v in data_sorted)
    Vtarget = Vtot * (percent / 100.0)
    for i in range(1, len(data_sorted)):
        d0, v0 = data_sorted[i-1]
        d1, v1 = data_sorted[i]
        if (v0 >= Vtarget >= v1) or (v1 >= Vtarget >= v0):
            if v1 == v0:
                return d1, Vtot, Vtarget
            frac = (Vtarget - v0) / (v1 - v0)
            d = d0 + (d1 - d0) * frac
            return d, Vtot, Vtarget
    idx = min(range(len(data_sorted)), key=lambda i: abs(data_sorted[i][1] - Vtarget))
    d_closest = data_sorted[idx][0]
    return d_closest, Vtot, Vtarget

def build_organs_autofill(d2map):  
    rows=[]
    for key,label in [("VEJIGA","Vejiga"),("RECTO","Recto"),("SIGMOIDE","Sigmoide"),("INTESTINO","Intestino")]:
        rows.append({"key":key.lower(),"label":label,"autoval":("" if d2map.get(key) is None else f"{d2map[key]:.2f}"),"limit":LIMITS_EQD2[key]})
    return rows

def parse_oncentra_session_file(file_storage):
    """ Lee un archivo DVH de Oncentra (file_storage) y devuelve:
    - hdr_d2: dict {"VEJIGA": d2cc_Gy, "RECTO": ..., "SIGMOIDE": ..., "INTESTINO": ...}
    - ctv_d90_gy: float | None"""
    txt = file_storage.read().decode("latin1", errors="ignore")
    tables = parse_oncentra_dvh_text(txt)
    idx = {name.lower(): name for name in tables.keys()}

    def find_match(target):
        for low, orig in idx.items():
            low_norm = _normalize_roi_token(low)
            if any(p.search(low_norm) for p in ALIASES[target]):
                return orig
        return None

    hdr_d2 = {}
    for key in ("VEJIGA", "RECTO", "SIGMOIDE", "INTESTINO"):
        nm = find_match(key)
        d2 = dose_at_volume_cc(tables.get(nm, []), 2.0) if nm else None
        if d2 is not None:
            hdr_d2[key] = round(float(d2), 2)

    ctv_d90_gy = None
    nm_ctv = find_match("CTV")
    if nm_ctv:
        d90, Vtot, Vtarget = dose_at_percent_volume(tables.get(nm_ctv, []), 90.0)
        if d90 is not None:
            ctv_d90_gy = float(d90)

    return hdr_d2, ctv_d90_gy

# ====== Rutas ======
@app.route("/", methods=["GET"])
def home():
    return render_template_string(
        PAGE, css=CSS, fx_rt=25, n_hdr=3, step1=False,
        limits=LIMITS_EQD2,
        ctv_volume_total=None, ctv_d90_gy=None, ctv_d90_cgy=None
    )

@app.route("/cargar_dvh", methods=["POST"])
def cargar_dvh():
    fx_rt = int(fnum(request.form.get("fx_rt"), 25))
    n_hdr = int(fnum(request.form.get("n_hdr"), 3))

    def _clamp(x, lo=0.0, hi=500.0):
        try:
            if x is None: return None
            return max(lo, min(hi, float(x)))
        except:
            return None

    user_limits = {
        "VEJIGA":   _clamp(fnum(request.form.get("limit_VEJIGA"),   LIMITS_EQD2["VEJIGA"])),
        "RECTO":    _clamp(fnum(request.form.get("limit_RECTO"),    LIMITS_EQD2["RECTO"])),
        "SIGMOIDE": _clamp(fnum(request.form.get("limit_SIGMOIDE"), LIMITS_EQD2["SIGMOIDE"])),
        "INTESTINO":_clamp(fnum(request.form.get("limit_INTESTINO"), LIMITS_EQD2["INTESTINO"])),
    }
    for k, default_v in LIMITS_EQD2.items():
        if user_limits.get(k) is None:
            user_limits[k] = default_v

    d2_autofill = {}
    patient_name, patient_id = None, None
    ctv_d95_gy = None
    tables = {}

    file = request.files.get("dvhfile")
    if file and file.filename:
        raw = file.read().decode("latin1", errors="ignore")
        txt = normalize_labels(raw)
        patient_name, patient_id = parse_patient_meta(txt)
        tables = parse_eclipse_dvh_text(txt)
        idx = {name.lower(): name for name in tables.keys()}

        def find_match(target: str):
            for low, orig in idx.items():
                low_norm = _normalize_roi_token(low)
                if any(p.search(low_norm) for p in ALIASES[target]):
                    return orig
            return None

        for organ in ("VEJIGA", "RECTO", "SIGMOIDE", "INTESTINO"):
            nm = find_match(organ if organ != "INTESTINO" else "INTESTINO")
            nm = nm or find_match("SIGMOIDE") if organ=="INTESTINO" else nm  # fallback suave
            d2 = dose_at_volume_cc(tables.get(nm, []), 2.0) if nm else None
            d2_autofill[organ if organ!="INTESTINO" else "INTESTINO"] = round(d2, 2) if d2 is not None else None

        nm_ctv = find_match("CTV")
        if nm_ctv:
            d95, Vtot, Vtarget = dose_at_percent_volume(tables.get(nm_ctv, []), 95.0)
            if d95 is not None:
                ctv_d95_gy = round(d95, 2)

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
        limit = user_limits[organ]
        d_rt = (D_ext / fx_rt) if (D_ext is not None and fx_rt > 0) else 0.0
        eqd2_ext = eqd2_from_total_with_fraction(D_ext, d_rt, ab) if D_ext is not None else 0.0
        rem = max(0.0, limit - eqd2_ext)
        dmax = solve_hdr_dose_per_session(rem, n_hdr, ab)
        results.append(Row(
            roi=label, D_ext=(f"{D_ext:.2f}" if D_ext is not None else None),
            fx_rt=fx_rt, d_rt=d_rt, ab=ab, eqd2_ext=eqd2_ext,
            hdr_prev=0.0, used=eqd2_ext, limit=limit, rem=rem, N=n_hdr,
            dmax_session=dmax, flag=("ok" if rem > 0 else "warn"), is_ctv_d95=False
        ))

    if ctv_d95_gy is not None:
        d_per_fx_ctv = (ctv_d95_gy / fx_rt) if fx_rt > 0 else 0.0
        eqd2_ctv_ext = eqd2_from_total_with_fraction(ctv_d95_gy, d_per_fx_ctv, 10.0)
        results.append(Row(
            roi="CTV", D_ext=f"{ctv_d95_gy:.2f}",
            fx_rt=fx_rt, d_rt=d_per_fx_ctv, ab=10.0,
            eqd2_ext=eqd2_ctv_ext, hdr_prev=0.0, used=0.0,
            limit=None, rem=None, N=n_hdr, dmax_session=None, flag=None, is_ctv_d95=True
        ))

    order_display = ["CTV", "Recto", "Vejiga", "Sigmoide", "Intestino"]
    results.sort(key=lambda r: order_display.index(r.roi) if getattr(r, "roi", None) in order_display else 999)

    return render_template_string(
        PAGE, css=CSS, fx_rt=fx_rt, n_hdr=n_hdr, step1=True, results=results,
        patient_name=patient_name, patient_id=patient_id, limits=user_limits,
        ctv_volume_total=None, ctv_d90_gy=None, ctv_d90_cgy=None
    )
@app.route("/calcular_hdr", methods=["POST"])
def calcular_hdr():
    # ---------- 0) Parámetros base ----------
    fx_rt = int(fnum(request.form.get("fx_rt"), 25))
    n_hdr = int(fnum(request.form.get("n_hdr"), 3))

    # ---------- 1) Recuperar EBRT del Paso 1 ----------
    ebrt = []
    for i in range(4):
        roi = request.form.get(f"EBRT_{i}_roi")
        if not roi:
            continue
        limit_val = request.form.get(f"EBRT_{i}_limit")
        ebrt.append({
            "roi":   roi,  # "Vejiga"/"Recto"/"Sigmoide"/"Intestino"
            "eqd2":  fnum(request.form.get(f"EBRT_{i}_eqd2")),
            "limit": (fnum(limit_val) if limit_val is not None and limit_val != "" else None),
            "dext":  request.form.get(f"EBRT_{i}_dext") or None,
        })

    # CTV (D95) de EBRT si vino oculto
    ctv_d95_hidden  = request.form.get("EBRT_CTV_D95")
    ctv_eqd2_hidden = request.form.get("EBRT_CTV_EQD2")

    # Mapa de límites (OARs) — base y overrides
    limits_map = {
        "Vejiga":    LIMITS_EQD2["VEJIGA"],
        "Recto":     LIMITS_EQD2["RECTO"],
        "Sigmoide":  LIMITS_EQD2["SIGMOIDE"],
        "Intestino": LIMITS_EQD2["INTESTINO"],
    }
    for item in ebrt:
        roi_disp = item.get("roi")
        lim = item.get("limit")
        if roi_disp in limits_map and lim is not None:
            try:
                limits_map[roi_disp] = float(lim)
            except:
                pass

    patient_name = request.form.get("patient_name") or None
    patient_id   = request.form.get("patient_id") or None

    # ---------- 2) Leer N archivos HDR en este mismo POST (sin session) ----------
    try:
        n_ses = int(request.form.get("n_sesiones", "1"))
        n_ses = max(1, min(3, n_ses))
    except:
        n_ses = 1

    hdr_d2_files = []   # lista por archivo: dict D2cc por OAR
    ctv_d90_files = []  # lista por archivo: D90 CTV (Gy) o None

    for i in range(1, n_ses + 1):
        f = request.files.get(f"hdrfile_{i}")
        if not f or not f.filename.strip():
            return f"Falta archivo de la sesión {i}.", 400
        hdr_d2, ctv_d90_gy = parse_oncentra_session_file(f)
        hdr_d2_files.append(hdr_d2)
        ctv_d90_files.append(ctv_d90_gy)

    # La cantidad real de columnas que mostrará la tabla = n_hdr del Paso 1
    n_hdr = int(fnum(request.form.get("n_hdr"), n_hdr))

    # ---------- 2.b) Regla de mapeo archivos -> columnas ----------
    # 1 archivo -> [A, A, A, ...]
    # 2 archivos -> [A, B, B, ...]
    # 3 archivos -> [A, B, C, C, ...] si hubiera más columnas
    def pick_file_index(col_idx: int, n_sesiones: int) -> int:
        if n_sesiones <= 1:
            return 0
        if n_sesiones == 2:
            return 0 if col_idx == 0 else 1
        # n_sesiones >= 3
        return col_idx if col_idx < n_sesiones else n_sesiones - 1

    # ---------- 3) Construir Plan HDR por fracción (una columna por sesión mostrada) ----------
    plan = []
    Row = lambda **k: type("Row", (), k)

    # CTV por columna (α/β = 10)
    any_ctv = any(d is not None for d in ctv_d90_files)
    if any_ctv:
        doses_ctv = []
        for j in range(n_hdr):
            idx = pick_file_index(j, len(ctv_d90_files))
            d = ctv_d90_files[idx] or 0.0
            doses_ctv.append(float(d))
        eqd2s_ctv = [eqd2_from_single_fraction(d, 10.0) for d in doses_ctv]
        eqd2_hdr_ctv_total = sum(eqd2s_ctv)
        eqd2_ebrt_ctv = float(ctv_eqd2_hidden) if ctv_eqd2_hidden else 0.0
        plan.append(Row(
            roi="CTV",
            doses=doses_ctv, eqd2s=eqd2s_ctv,
            total_dose=sum(doses_ctv),
            eqd2_hdr_total=eqd2_hdr_ctv_total,
            eqd2_ebrt=eqd2_ebrt_ctv,
            eqd2_total=eqd2_ebrt_ctv + eqd2_hdr_ctv_total,
            limit=None, is_ctv=True
        ))

    # OARs por columna (α/β = 3)
    order = [("RECTO","Recto"), ("VEJIGA","Vejiga"), ("SIGMOIDE","Sigmoide"), ("INTESTINO","Intestino")]
    for key, display in order:
        per_fx_doses = []
        for j in range(n_hdr):
            idx = pick_file_index(j, len(hdr_d2_files))
            dose = float(hdr_d2_files[idx].get(key, 0.0))
            per_fx_doses.append(dose)

        eqd2s = [eqd2_from_single_fraction(d, 3.0) for d in per_fx_doses]
        total_dose = sum(per_fx_doses)
        eqd2_hdr_total = sum(eqd2s)
        eqd2_ebrt = next((item["eqd2"] for item in ebrt if item["roi"] == display), 0.0)
        eqd2_total = eqd2_ebrt + eqd2_hdr_total
        limit = limits_map.get(display, None)

        plan.append(Row(
            roi=display, doses=per_fx_doses, eqd2s=eqd2s, total_dose=total_dose,
            eqd2_hdr_total=eqd2_hdr_total, eqd2_ebrt=eqd2_ebrt,
            eqd2_total=eqd2_total, limit=limit, is_ctv=False
        ))

    # ---------- 3.c) Resumen dosimétrico ----------
    plan_summary = []
    for r in plan:
        is_ctv = getattr(r, "is_ctv", False)
        roi_name = "CTV" if is_ctv else r.roi
        plan_summary.append({
            "roi": roi_name,
            "eqd2_ebrt": r.eqd2_ebrt,
            "eqd2_hdr":  r.eqd2_hdr_total,
            "eqd2_total": r.eqd2_total,
            "limit": (None if is_ctv else limits_map.get(roi_name)),
        })
    order_display = ["CTV (D90)", "Recto", "Vejiga", "Sigmoide", "Intestino"]
    plan_summary.sort(key=lambda x: order_display.index(x["roi"]) if x["roi"] in order_display else 999)

    # ---------- 4) Reconstruir Tabla 1 (arriba) con los EBRT que vinieron ----------
    results = []
    for item in ebrt:
        roi   = item["roi"]
        eqd2  = item["eqd2"]
        limit = item["limit"]
        dext  = item["dext"]
        if limit is not None:
            rem  = max(0.0, limit - eqd2)
            dmax = solve_hdr_dose_per_session(rem, n_hdr, 3.0)
            flag = "ok" if rem > 0 else "warn"
        else:
            rem = dmax = flag = None
        results.append(type("Row", (), {
            "roi": roi, "D_ext": dext, "fx_rt": fx_rt, "d_rt": 0.0, "ab": 3.0,
            "eqd2_ext": eqd2, "hdr_prev": 0.0, "used": eqd2, "limit": limit,
            "rem": rem, "N": n_hdr, "dmax_session": dmax, "flag": flag,
            "is_ctv_d95": False,
        }))
    if ctv_d95_hidden and not any(getattr(r, "is_ctv_d95", False) for r in results):
        results.append(type("Row", (), {
            "roi": "CTV", "D_ext": ctv_d95_hidden, "fx_rt": fx_rt, "d_rt": 0.0, "ab": 10.0,
            "eqd2_ext": (float(ctv_eqd2_hidden) if ctv_eqd2_hidden else None),
            "hdr_prev": 0.0, "used": 0.0, "limit": None, "rem": None, "N": n_hdr,
            "dmax_session": None, "flag": None, "is_ctv_d95": True,
        }))

    # ---------- 5) Render ----------
    ctv_volume_total = None
    ctv_d90_gy = None
    ctv_d90_cgy = None

    limits_caps = {
        "VEJIGA":    limits_map.get("Vejiga",   LIMITS_EQD2["VEJIGA"]),
        "RECTO":     limits_map.get("Recto",    LIMITS_EQD2["RECTO"]),
        "SIGMOIDE":  limits_map.get("Sigmoide", LIMITS_EQD2["SIGMOIDE"]),
        "INTESTINO": limits_map.get("Intestino",LIMITS_EQD2["INTESTINO"]),
    }

    order_display2 = ["CTV (D95)", "Recto", "Vejiga", "Sigmoide", "Intestino"]
    results.sort(key=lambda r: order_display2.index(r.roi) if getattr(r, "roi", None) in order_display2 else 999)

    return render_template_string(
        PAGE, css=CSS, fx_rt=fx_rt, n_hdr=n_hdr, step1=True,
        results=results, plan_real=plan, plan_summary=plan_summary,
        patient_name=patient_name, patient_id=patient_id,
        ctv_volume_total=ctv_volume_total, ctv_d90_gy=ctv_d90_gy, ctv_d90_cgy=ctv_d90_cgy,
        limits=limits_caps
    )
if _name_ == "_main_":
    print(">> Booting Flask on http://127.0.0.1:5000  (use_reloader=False)")
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
    except Exception as e:
        import traceback
        print(">> Flask crashed!")
        traceback.print_exc()
        raise