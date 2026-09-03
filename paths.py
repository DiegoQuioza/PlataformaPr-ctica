import sys
from pathlib import Path

def get_bundle_dir() -> Path:
  """
  Retorna la ruta raíz absoluta de los recursos (estáticos, templates, plugins).
  Resuelve correctamente tanto en entorno de desarrollo como dentro del paquete
  generado por PyInstaller (_MEIPASS).
  """
  if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    return Path(sys._MEIPASS).resolve()
  return Path(__file__).resolve().parent

def get_execution_dir() -> Path:
  """
  Retorna el directorio de ejecución real en disco donde reside el script o el .exe.
  Útil para guardar datos persistentes (bases de datos SQLite, logs, descargas).
  """
  if getattr(sys, "frozen", False):
    return Path(sys.executable).resolve().parent
  return Path(__file__).resolve().parent

# --- Directorio Raíz Dinámico de Recursos ---
ROOT_DIR = get_bundle_dir()

# --- Directorio Raíz de Datos Persistentes ---
EXECUTION_DIR = get_execution_dir()

# Directorio para Bases de datos y archivos modificables (Fuera del bundle temporal)
DB_DIR = EXECUTION_DIR / "data"

# Directorios principales de la aplicación (Recursos empaquetados)
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DOCS_DIR = ROOT_DIR / "docs"
PLUGINS_DIR = ROOT_DIR / "plugins"

AUTOMATIONS_DIR = ROOT_DIR / "automations"
BACKGROUND_PROCESSES_DIR = ROOT_DIR / "background_processes"
MEDIOAMBIENTE_DIR = AUTOMATIONS_DIR / "medioambiente"
SOSTENIBILIDAD_DIR = AUTOMATIONS_DIR / "sostenibilidad"

def print_venv_activation_command() -> None:
  """
  Imprime el comando estandarizado para activar el entorno virtual en PowerShell Windows.
  """
  venv_script = EXECUTION_DIR / "venv" / "Scripts" / "Activate.ps1"
  cmd = f'(Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned) ; (& "{venv_script}")'
  print(cmd)