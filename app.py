import io, re, base64
import numpy as np
import pandas as pd
from flask import Flask, request, render_template_string, send_file

app = Flask(__name__)

CSS = """
:root { --bg:#0f172a; --card:#111827; --muted:#94a3b8; --text:#e5e7eb; --acc:#22d3ee; --acc2:#38bdf8; --err:#f87171; }
*{box-sizing:border-box} body{margin:0;font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Arial;background:radial-gradient(1200px 800px at 20% -10%,#0b1b2b 0%,var(--bg) 45%),var(--bg);color:var(--text)}
.container{max-width:980px;margin:40px auto;padding:0 20px} .card{background:linear-gradient(180deg,rgba(255,255,255,.04),rgba(255,255,255,.02));border:1px solid rgba(255,255,255,.08);border-radius:16px;padding:24px;box-shadow:0 10px 40px rgba(0,0,0,.25)}
h1{margin:0 0 10px;font-size:24px}.lead{margin:0 0 18px;color:var(--muted)} .row{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
.input{width:100%;padding:10px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:#0b1220;color:var(--text)}
.btn{appearance:none;border:none;padding:12px 16px;border-radius:12px;font-weight:600;cursor:pointer}
.btn-primary{background:linear-gradient(180deg,var(--acc),var(--acc2));color:#05232f} .btn-ghost{background:transparent;color:var(--text);border:1px solid rgba(255,255,255,.14)}
.table{width:100%;border-collapse:collapse;margin-top:16px} .table th,.table td{padding:10px;border-bottom:1px solid rgba(255,255,255,.1);text-align:left}
.error{color:var(--err);margin-top:10px}
"""

PAGE = """
<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dmax por órgano (DVH)</title><style>{{css}}</style></head>
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

{% if error %}<div class="error">⚠️ {{error}}</div>{% endif %}

{% if rows %}
<table class="table">
  <thead><tr><th>Órgano / ROI</th><th>Dmax (Gy)</th></tr></thead>
  <tbody>{% for r in rows %}<tr><td>{{r[0]}}</td><td>{{"%.3f"|format(r[1])}}</td></tr>{% endfor %}</tbody>
</table>
{% endif %}

</div></div></body></html>
"""

# --------- Parsing de Oncentra (TXT en español) ---------

ESTRUCTURA_RE = re.compile(r"^\s*Estructura:\s*(.+?)\s*$", re.IGNORECASE)
TABLA_HEADER_RE = re.compile(r"Dosis\s+relativa|\bDosis\s*\[\s*cGy\s*\]|\bProporción\b", re.IGNORECASE)
NUM_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)")

def parse_oncentra_txt(text: str):
    """
    Parsea un TXT exportado por Oncentra en español con bloques por 'Estructura: <NOMBRE>'
    y una tabla con columnas: Dosis relativa [%], Dosis [cGy], Proporción de volumen [%].
    Devuelve lista de tuplas (roi, dmax_gy).
    """
    # normalizar decimales coma→punto (por si acaso)
    text = text.replace(",", ".")
    lines = text.splitlines()

    rois = []            # [(name, dmax_gy)]
    current_roi = None
    in_table = False
    doses_cgy = []
    vols_pct = []

    def flush_roi():
        nonlocal rois, current_roi, doses_cgy, vols_pct
        if current_roi and doses_cgy and vols_pct:
            dmax_gy = compute_dmax_from_arrays(np.array(doses_cgy), np.array(vols_pct))
            rois.append((current_roi, dmax_gy))
        # reset
        current_roi = None
        doses_cgy = []
        vols_pct = []

    for line in lines:
        # ¿nueva estructura?
        m = ESTRUCTURA_RE.match(line)
        if m:
            # cerramos ROI previo
            flush_roi()
            current_roi = m.group(1).strip()
            in_table = False
            continue

        # detectar inicio de tabla
        if TABLA_HEADER_RE.search(line):
            in_table = True
            continue

        if in_table:
            # intentamos extraer 3 números por línea (rel%, cGy, vol%)
            nums = [float(x) for x in NUM_RE.findall(line)]
            if len(nums) >= 3:
                # tomamos los 3 últimos por robustez
                rel_pct, cgy, vol_pct = nums[-3], nums[-2], nums[-1]
                doses_cgy.append(cgy)
                vols_pct.append(vol_pct)
            elif line.strip() == "":
                # línea en blanco: posible fin de tabla
                in_table = False

    # flush del último ROI
    flush_roi()

    # si no encontramos 'Estructura:', devolvemos vacío para que el caller pruebe CSV
    return rois

def compute_dmax_from_arrays(dose_cgy: np.ndarray, vol_pct: np.ndarray) -> float:
    """
    Dmax = última dosis (Gy) con volumen > 0%. Asume DVH acumulativo.
    Si no es estrictamente monótono, se tolera ruido y se toma el último punto con vol>eps.
    """
    # ordenar por dosis por si acaso
    order = np.argsort(dose_cgy)
    d = dose_cgy[order] / 100.0  # cGy → Gy
    v = vol_pct[order]
    eps = 1e-6
    mask = v > eps
    if not np.any(mask):
        return 0.0
    return float(d[mask][-1])

# --------- CSV genérico (por si no es Oncentra TXT) ---------

def autodetect_sep_dec(text):
    sep = ";" if text.count(";") > text.count(",") else ","
    dec = "," if sep == ";" else "."
    return sep, dec

def compute_dmax_from_csv(df):
    # Heurísticas de columnas
    cols = {c.lower(): c for c in df.columns}
    # dosis
    dose_col = next((cols[k] for k in cols if "dose" in k or "dosis" in k or "gy" in k or "cgy" in k), None)
    # volumen (cc o %)
    vol_col = next((cols[k] for k in cols if "%" in k or "percent" in k or "volume" in k or "vol" in k), None)
    # ROI
    roi_col = next((cols[k] for k in cols if "roi" in k or "organ" in k or "estructura" in k or "structure" in k or "name" in k or "órgano" in k), None)

    if dose_col is None or vol_col is None:
        raise ValueError("No se detectaron columnas de dosis/volumen en el CSV.")

    # cGy→Gy si aplica
    dose_series = df[dose_col].astype(str).str.replace(",", ".", regex=False).astype(float)
    if "cgy" in dose_col.lower():
        dose_series = dose_series / 100.0

    vol_series = df[vol_col].astype(str).str.replace(",", ".", regex=False).astype(float)

    def dmax_from(d, v):
        d = np.asarray(d, dtype=float)
        v = np.asarray(v, dtype=float)
        order = np.argsort(d)
        d = d[order]; v = v[order]
        eps = 1e-6
        m = v > eps
        return float(d[m][-1]) if np.any(m) else 0.0

    rows = []
    if roi_col:
        for roi, g in df.groupby(roi_col):
            d = g[dose_col].astype(str).str.replace(",", ".", regex=False).astype(float)
            if "cgy" in dose_col.lower():
                d = d / 100.0
            v = g[vol_col].astype(str).str.replace(",", ".", regex=False).astype(float)
            rows.append((str(roi), dmax_from(d, v)))
    else:
        rows.append(("ROI", dmax_from(dose_series, vol_series)))

    rows.sort(key=lambda x: x[0].lower())
    return rows

# --------- Rutas ---------

@app.route("/", methods=["GET"])
def index():
    return render_template_string(PAGE, css=CSS, rows=None, error=None)

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
