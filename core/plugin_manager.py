import importlib
import inspect
from pathlib import Path
from typing import List
from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


class PluginManager:

  def __init__(self, app: FastAPI, plugins_dir: Path):
    self.app = app
    self.plugins_dir = plugins_dir
    self.template_dirs: List[Path] = []
    self.loaded_plugins: List[str] = []

  def discover_and_load(self):
    """Escanea la carpeta de plugins, importa los routers y monta los estáticos y templates.

    """
    if not self.plugins_dir.exists() or not self.plugins_dir.is_dir():
      raise FileNotFoundError(
          f"El directorio de plugins no existe en: {self.plugins_dir}"
      )

    # Recorrer cada subdirectorio dentro de la carpeta 'plugins'
    for plugin_path in self.plugins_dir.iterdir():
      if plugin_path.is_dir() and not plugin_path.name.startswith(
          ("_", ".")
      ):
        self._load_plugin(plugin_path)

  def _load_plugin(self, plugin_path: Path):
    plugin_name = plugin_path.name
    package_prefix = f"plugins.{plugin_name}"

    # --- 1. Estáticos (sin cambios) ---
    static_dir = plugin_path / "static"
    if static_dir.exists() and static_dir.is_dir():
        mount_path = f"/static/plugins/{plugin_name}"
        self.app.mount(
            mount_path,
            StaticFiles(directory=str(static_dir)),
            name=f"static_{plugin_name}",
        )

    # --- 2. Templates (sin cambios) ---
    templates_dir = plugin_path / "templates"
    if templates_dir.exists() and templates_dir.is_dir():
        self.template_dirs.append(templates_dir)

    # --- 3. Importar SOLO el paquete raíz del plugin ---
    # Su __init__.py ya encadena todo lo demás (medioambiente -> riles -> services -> ...)
    if not (plugin_path / "__init__.py").exists():
        print(f"⚠️  Plugin [{plugin_name}] sin __init__.py, se omite.")
        return

    try:
        module = importlib.import_module(package_prefix)
        for attr_name, attr_value in inspect.getmembers(module):
            if isinstance(attr_value, APIRouter):
                if getattr(attr_value, "_registered_in_app", False):
                    continue
                self.app.include_router(attr_value)
                setattr(attr_value, "_registered_in_app", True)
                self.loaded_plugins.append(
                    f"Plugin [{plugin_name}] -> {package_prefix}:{attr_name}"
                )
    except Exception as e:
        print(f"❌ Error al cargar el plugin {plugin_name}: {e}")

  def get_jinja_templates(self, global_templates_dir: Path = None) -> Jinja2Templates:
    """Crea una instancia unificada de Jinja2Templates capaz de buscar en

    todos los directorios /templates de todos los plugins cargados.
    """
    all_dirs = []
    if global_templates_dir and global_templates_dir.exists():
      all_dirs.append(str(global_templates_dir))

    all_dirs.extend([str(d) for d in self.template_dirs])

    # Jinja2Templates acepta una lista de rutas para buscar plantillas
    return Jinja2Templates(directory=all_dirs)