import os
from datetime import datetime, timedelta

# ── WHATSAPP ──────────────────────────────────────────────────
VERIFY_TOKEN    = os.environ.get("VERIFY_TOKEN", "Mina_Giann_2026")
ACCESS_TOKEN    = os.environ.get("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
WA_API_URL      = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"

# ── BASE DE DATOS ─────────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL")

# ── IA ────────────────────────────────────────────────────────
ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
MODELO_IA     = "claude-sonnet-4-5"

# ── ZONA HORARIA PERÚ ─────────────────────────────────────────
def hora_peru():
    return datetime.utcnow() - timedelta(hours=5)

def fecha_hora_str():
    return hora_peru().strftime("%d/%m/%Y %H:%M")

# ── ROLES ─────────────────────────────────────────────────────
ROLES = {
    "GEOLOGO":    "Geólogo Nexa",
    "PERFORISTA": "Perforista / Contratista",
    "SGS":        "Técnico SGS",
    "CERTIMIN":   "Certimin",
    "MODELADOR":  "Modelador / Estimador",
    "GERENCIA":   "Gerencia",
    "ADMIN":      "Administrador",
}

# ── FLUJOS DEL BOT ────────────────────────────────────────────
FLUJOS = {
    "MATRICULA":       "1",
    "PERFORACION":     "2",
    "SGS":             "3",
    "CERTIMIN":        "4",
    "MODELAMIENTO":    "5",
    "CONSULTA":        "6",
    "DESCARGA_EXCEL":  "7",
    "ANULAR_SGS":      "8",   # nuevo — anular registros SGS
    "FOTO":            "9",
    "BATCH_GEOLOGO":   "10",  # nuevo — registrar batch Fusion
    "CONSOLIDADO_PERF": "12",  # nuevo — consolidado con empresa/turno/fecha
    "REPORTE_SGS":     "11",
}

# ── TIMEOUT DE SESIÓN (minutos) ───────────────────────────────
SESION_TIMEOUT_MIN = 30

# ── DIÁMETROS DE PERFORACIÓN ──────────────────────────────────
DIAMETROS = ["BQ", "NQ", "HQ", "PQ"]

# ── ETAPAS SGS ────────────────────────────────────────────────
ETAPAS_SGS = {
    "1": "LOGUEO",
    "2": "MUESTREO",
    "3": "RQD",
    "4": "FOTOGRAFIA",
    "5": "DENSIDAD",
}
