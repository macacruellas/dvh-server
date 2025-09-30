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
<h1>DVH → <span style="color:#67e8f9">Dmax por órgano</span></h1>
<p class="lead">Subí un DVH (.csv / .txt). Soporta exportes de Oncentra en español (con “Estructura: …”).</p>
<form method="post" action="/upload" enctype="multipart/form-data">
  <input class="input" type="file" name="file" required>
  <div class="row">
    <button class="btn btn-primary" type="submit" name="action" value="preview">Ver tabla</button>
    <button class="btn btn-ghost" type="submit" name="action" value="download">Descargar CSV</button>
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
  <thead><tr><th>Órgano / ROI</th><th>Dmax (Gy)</th></tr></thead>
  <tbody>{% for r in rows %}<tr><td>{{r[0]}}</td><td>{{"%.3f"|format(r[1])}}</td></tr>{% endfor %}</tbody>
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

@app.route("/upload", methods=["POST"])
def upload():
    try:
        f = request.files.get("file")
        if not f:
            return render_template_string(PAGE, css=CSS, rows=None, error="Falta archivo.")

        raw = f.read()
        text = raw.decode("utf-8", errors="ignore")

        # 1) Intentar parser Oncentra TXT
        if "Estructura:" in text:
            rows = parse_oncentra_txt(text)
            if rows:
                action = (request.form.get("action") or "preview").lower()
                if action == "download":
                    out = io.StringIO(); out.write("ROI,Dmax_Gy\n")
                    for roi, dm in rows: out.write(f"{roi},{dm:.3f}\n")
                    return send_file(io.BytesIO(out.getvalue().encode("utf-8")),
                                     mimetype="text/csv",
                                     as_attachment=True,
                                     download_name="dmax_por_organo.csv")
                return render_template_string(PAGE, css=CSS, rows=rows, error=None)
            # si no hubo filas, intentar CSV

        # 2) Intentar como CSV genérico
        sep, dec = autodetect_sep_dec(text)
        try:
            df = pd.read_csv(io.StringIO(text), sep=sep, decimal=dec)
        except Exception:
            # probar el otro separador
            sep = "," if sep == ";" else ";"
            dec = "." if dec == "," else ","
            df = pd.read_csv(io.StringIO(text), sep=sep, decimal=dec)

        rows = compute_dmax_from_csv(df)
        action = (request.form.get("action") or "preview").lower()
        if action == "download":
            out = io.StringIO(); out.write("ROI,Dmax_Gy\n")
            for roi, dm in rows: out.write(f"{roi},{dm:.3f}\n")
            return send_file(io.BytesIO(out.getvalue().encode("utf-8")),
                             mimetype="text/csv",
                             as_attachment=True,
                             download_name="dmax_por_organo.csv")
        return render_template_string(PAGE, css=CSS, rows=rows, error=None)

    except Exception as e:
        return render_template_string(PAGE, css=CSS, rows=None, error=str(e)), 400

if __name__ == "__main__":
    # accesible desde tu red local
    app.run(host="0.0.0.0", port=5000, debug=False)
