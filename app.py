import math, re
from flask import Flask, request, render_template_string

app = Flask(__name__)

# ====== Límites fijos (inamovibles) ======
LIMITS_EQD2 = {"VEJIGA":85.0,"RECTO":75.0,"SIGMOIDE":75.0,"INTESTINO":75.0}

# ====== Aliases ROI EN/ES ======
ALIASES = {
    "VEJIGA":[re.compile(p,re.I) for p in [r"\bbladder\b", r"\bvejig"]],
    "RECTO":[re.compile(p,re.I) for p in [r"\brectum\b", r"\brecto\b"]],
    "SIGMOIDE":[re.compile(p,re.I) for p in [r"\bsigmoid\b", r"\bbowel[_\s-]?large\b", r"\bsigmoide\b"]],
    "INTESTINO":[re.compile(p,re.I) for p in [r"\bbowel[_\s-]?small\b", r"\bsmall\s*bowel\b", r"\bintestin[oa]"]],
}

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
.table th,.table td{padding:10px;border-bottom:1px solid rgba(255,255,255,.1);text-align:left;font-size:14px}
.section{margin-top:22px}
.section h3{margin:6px 0 8px 0;color:#a5f3fc;font-size:18px}
.note{color:#94a3b8;font-size:12px}
.warn{color:var(--err);font-weight:600}
.ok{color:var(--ok);font-weight:600}
.fixed{opacity:.9}
.small{font-size:12px;color:var(--muted)}
"""

PAGE = """
<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>RT Externa → Dmax HDR + Plan Real</title><style>{{css}}</style></head>
<body><div class="container"><div class="card">
  <h1><span style="color:#67e8f9">Pipeline</span> <span class="badge">DVH → Resultados → Oncentra</span></h1>
  <p class="lead">Paso 1: cargá el <b>DVH acumulado</b> para obtener el D2cc de RT externa y el <b>Dmax/sesión sugerido</b>. Paso 2: pegá la tabla del planificador (Oncentra) y calculamos el cuadro final.</p>

  <!-- PASO 1 -->
  <form method="post" action="/cargar_dvh" enctype="multipart/form-data">
    <div class="section">
      <h3>Paso 1 — Cargar DVH</h3>
      <div class="grid">
        <label>fx_rt (fracciones RT externa)
          <input class="input" type="number" name="fx_rt" min="1" step="1" value="{{fx_rt}}">
        </label>
        <label>N sesiones HDR a planificar
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
<table class="table">
  <thead>
    <tr>
      <th>Órgano</th>
      <th>D2cc RT ext (Gy)</th>
      <th>EQD2 RT ext (Gy)</th>
      <th>Límite EQD2</th>
      <th>D máx/sesión (Gy)</th>
      <th>Estado</th>
    </tr>
  </thead>
  <tbody>
    {% for r in results %}
    <tr>
      <td>{{r.roi}}</td>
      <td>{{r.D_ext if r.D_ext is not none else "-"}}</td>
      <td>{{"%.2f"|format(r.eqd2_ext)}}</td>
      <td>{{"%.2f"|format(r.limit)}}</td>
      <td>{{"%.2f"|format(r.dmax_session)}}</td>
      <td>{% if r.flag == "ok" %}<span class="ok">✅ Con margen</span>{% else %}<span class="warn">⚠️ Sin margen</span>{% endif %}</td>
    </tr>
    {% endfor %}
  </tbody>
</table>
    <p class="note">EQD2 EBRT = D_total · (1 + d_rt/αβ) / (1 + 2/αβ). Dmax/sesión resuelve la cuadrática con el remanente.</p>
  </div>

  <!-- PASO 2 -->
  <form method="post" action="/calcular_hdr">
    <input type="hidden" name="fx_rt" value="{{fx_rt}}">
    <input type="hidden" name="n_hdr" value="{{n_hdr}}">
    {% for r in results %}
      <input type="hidden" name="EBRT_{{loop.index0}}_roi" value="{{r.roi}}">
      <input type="hidden" name="EBRT_{{loop.index0}}_eqd2" value="{{'%.4f'|format(r.eqd2_ext)}}">
      <input type="hidden" name="EBRT_{{loop.index0}}_limit" value="{{'%.2f'|format(r.limit)}}">
    {% endfor %}

    <div class="section">
      <h3>Paso 2 — Pegar tabla del planificador (HDR OAR @ 2&nbsp;cc)</h3>
      <p class="small">Formato: "ROI | Dose [%] | Dose [Gy] | Volume [%] | Volume [ccm]". Tomamos filas con Volume≈2.00&nbsp;cc.</p>
      <textarea name="planner_paste" placeholder="ROI    Dose[%]   Dose[Gy]   Volume[%]   Volume[ccm]
VEJIGA  65.03     5.2026     0.91       2.00
RECTO   63.26     5.0607     2.64       2.00
SIGMOIDE 41.78    3.3422     5.44       2.00"></textarea>
      <div class="row" style="margin-top:12px">
        <button class="btn btn-primary" type="submit">Calcular</button>
      </div>
    </div>
  </form>
  {% endif %}

  {% if plan_real %}
  <div class="section">
    <h3>Plan Real Completo RT Externa + HDR</h3>
    <table class="table">
      <thead>
        <tr>
          <th>ROI</th>
          <th>D2cc EBRT (Gy)</th>
          <th>EQD2 EBRT (Gy)</th>
          <th>Dose HDR@2cc (Gy)</th>
          <th>EQD2 HDR (Gy)</th>
          <th>EQD2 TOTAL (Gy)</th>
          <th>Límite (Gy)</th>
          <th>Estado</th>
        </tr>
      </thead>
      <tbody>
        {% for r in plan_real %}
        <tr>
          <td>{{r.roi}}</td>
          <td>{{"%.2f"|format(r.d2cc_ebrt)}}</td>
          <td>{{"%.2f"|format(r.eqd2_ebrt)}}</td>
          <td>{{"%.2f"|format(r.hdr_dose)}}</td>
          <td>{{"%.2f"|format(r.eqd2_hdr)}}</td>
          <td>{{"%.2f"|format(r.eqd2_total)}}</td>
          <td>{{"%.2f"|format(r.limit)}}</td>
          <td>{% if r.eqd2_total <= r.limit %}<span class="ok">✅ Con margen</span>{% else %}<span class="warn">⚠️ Excede</span>{% endif %}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <p class="note">Para EQD2 HDR usamos α/β=3 y consideramos la dosis pegada como una sesión (podemos ampliar a múltiples fracciones cuando quieras).</p>
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
    for k in ("VEJIGA","RECTO","SIGMOIDE","INTESTINO"):
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

# ====== Estado en memoria simple (para demo) ======
def build_organs_autofill(d2map):
    rows=[]
    for key,label in [("VEJIGA","Vejiga"),("RECTO","Recto"),("SIGMOIDE","Sigmoide"),("INTESTINO","Intestino")]:
        rows.append({"key":key.lower(),"label":label,"autoval":("" if d2map.get(key) is None else f"{d2map[key]:.2f}"),"limit":LIMITS_EQD2[key]})
    return rows

# ====== Rutas ======
@app.route("/", methods=["GET"])
def home():
    return render_template_string(PAGE, css=CSS, fx_rt=25, n_hdr=3, step1=False)

@app.route("/cargar_dvh", methods=["POST"])
def cargar_dvh():
    fx_rt = int(fnum(request.form.get("fx_rt"),25))
    n_hdr = int(fnum(request.form.get("n_hdr"),3))
    d2_autofill = {}
    file = request.files.get("dvhfile")
    if file and file.filename:
        txt = file.read().decode("latin1", errors="ignore")
        tables = parse_eclipse_dvh_text(txt)
        # mapear a nuestros 4 órganos
        idx = {name.lower(): name for name in tables.keys()}
        def find_match(target):
            for low, orig in idx.items():
                if any(p.search(low) for p in ALIASES[target]): return orig
            return None
        for organ in ("VEJIGA","RECTO","SIGMOIDE","INTESTINO"):
            nm = find_match(organ)
            d2 = dose_at_volume_cc(tables[nm],2.0) if nm else None
            d2_autofill[organ] = round(d2,2) if d2 is not None else None

    # armar resultados de paso 1 (EQD2 EBRT y Dmax/sesión)
    results=[]
    Row=lambda **k:type("Row",(),k)
    for organ,label in [("VEJIGA","Vejiga"),("RECTO","Recto"),("SIGMOIDE","Sigmoide"),("INTESTINO","Intestino")]:
        D_ext = d2_autofill.get(organ)
        ab=3.0; limit=LIMITS_EQD2[organ]
        d_rt=(D_ext/fx_rt) if (D_ext is not None and fx_rt>0) else 0.0
        eqd2_ext = eqd2_from_total_with_fraction(D_ext, d_rt, ab) if D_ext is not None else 0.0
        hdr_prev=0.0; used=eqd2_ext+hdr_prev
        rem=max(0.0,limit-used); dmax=solve_hdr_dose_per_session(rem,n_hdr,ab)
        flag="ok" if rem>0 else "warn"
        results.append(Row(roi=label, D_ext=(f"{D_ext:.2f}" if D_ext is not None else None),
                           fx_rt=fx_rt,d_rt=d_rt,ab=ab,eqd2_ext=eqd2_ext,hdr_prev=hdr_prev,
                           used=used,limit=limit,rem=rem,N=n_hdr,dmax_session=dmax,flag=flag))

    return render_template_string(PAGE, css=CSS, fx_rt=fx_rt, n_hdr=n_hdr,
                                  step1=True, results=results)

@app.route("/calcular_hdr", methods=["POST"])
def calcular_hdr():
    fx_rt = int(fnum(request.form.get("fx_rt"),25))
    n_hdr = int(fnum(request.form.get("n_hdr"),3))
    # recuperar EBRT del paso 1
    ebrt=[]
    for i in range(4):
        roi=request.form.get(f"EBRT_{i}_roi")
        if not roi: continue
        eqd2=fnum(request.form.get(f"EBRT_{i}_eqd2"))
        ebrt.append((roi,eqd2))
    limits_map={ "Vejiga":LIMITS_EQD2["VEJIGA"], "Recto":LIMITS_EQD2["RECTO"],
                 "Sigmoide":LIMITS_EQD2["SIGMOIDE"], "Intestino":LIMITS_EQD2["INTESTINO"] }

    # parsear pegado
    planner_rows=parse_planner_paste(request.form.get("planner_paste",""))

    # armar plan real (simple: tomamos la dosis pegada como UNA sesión)
    plan=[]
    Row=lambda **k:type("Row",(),k)
    # indexar HDR por órgano mapeado
    hdr_by = {}
    for r in planner_rows:
        if r["mapped"]:
            hdr_by[r["mapped"]]=r["dose_gy"]

    # map EN/ES para mostrar como en paso1
    es_name={"VEJIGA":"Vejiga","RECTO":"Recto","SIGMOIDE":"Sigmoide","INTESTINO":"Intestino"}

    for key in ("VEJIGA","RECTO","SIGMOIDE","INTESTINO"):
        display=es_name[key]
        hdr_dose = hdr_by.get(key)
        # buscar eqd2_ebrt del paso1 por display
        eqd2_ebrt = next((v for (roi,v) in ebrt if roi==display), 0.0)
        d2cc_ebrt = None  # no lo necesitamos para el cuadro final, pero podés incluirlo
        eqd2_hdr = eqd2_from_single_fraction(hdr_dose,3.0) if hdr_dose is not None else 0.0
        eqd2_total = eqd2_ebrt + eqd2_hdr
        limit = limits_map[display]
        plan.append(Row(roi=display, d2cc_ebrt=(0.0 if d2cc_ebrt is None else d2cc_ebrt),
                        eqd2_ebrt=eqd2_ebrt, hdr_dose=(hdr_dose or 0.0),
                        eqd2_hdr=eqd2_hdr, eqd2_total=eqd2_total, limit=limit))

    # Para re-render, reconstruimos resultados de paso1 (solo para que permanezcan visibles)
    results=[]
    for (roi,eqd2) in ebrt:
        limit = limits_map[roi]; rem=max(0.0,limit-eqd2); dmax=solve_hdr_dose_per_session(rem,n_hdr,3.0)
        results.append(type("Row",(),{"roi":roi,"D_ext":"-","fx_rt":fx_rt,"d_rt":0.0,"ab":3.0,
                                      "eqd2_ext":eqd2,"hdr_prev":0.0,"used":eqd2,"limit":limit,
                                      "rem":rem,"N":n_hdr,"dmax_session":dmax,
                                      "flag":"ok" if rem>0 else "warn"}))

    return render_template_string(PAGE, css=CSS, fx_rt=fx_rt, n_hdr=n_hdr,
                                  step1=True, results=results, plan_real=plan)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
