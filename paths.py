from pathlib import Path
# Raíz absoluta del proyecto
ROOT_DIR = Path(__file__).resolve().parent


# Directorio para Bases de datos
DB_DIR = ROOT_DIR / "data"

# Directorios principales del backend
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DOCS_DIR = ROOT_DIR / "docs"
PLUGINS_DIR = ROOT_DIR / "plugins"

AUTOMATIONS = ROOT_DIR / "automations"
BACKGROUND_PROCESSES_DIR = ROOT_DIR / "background_processes"
MEDIOAMBIENTE_DIR = AUTOMATIONS / "medioambiente"
SOSTENIBILIDAD_DIR = AUTOMATIONS / "sostenibilidad"

def get_venv_command():
  print(f'(Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned) ; (& "{ROOT_DIR}\\venv\Scripts\Activate.ps1")')