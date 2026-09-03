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
    """Escanea la carpeta de plugins, monta estáticos recursivamente e importa routers."""
    if not self.plugins_dir.exists() or not self.plugins_dir.is_dir():
      raise FileNotFoundError(
          f"El directorio de plugins no existe en: {self.plugins_dir}"
      )

    # 1. Montar estáticos globales de la raíz si existen (hola/static -> 'static')
    root_static = self.plugins_dir.parent / "static"
    if root_static.exists() and root_static.is_dir():
      self.app.mount(
          "/static",
          StaticFiles(directory=str(root_static)),
          name="static",
      )

    # 2. Recorrer plugins y sus subdirectorios
    for plugin_path in self.plugins_dir.iterdir():
      if plugin_path.is_dir() and not plugin_path.name.startswith(("_", ".")):
        self._load_plugin(plugin_path)

  def _load_plugin(self, plugin_path: Path):
    plugin_name = plugin_path.name
    package_prefix = f"plugins.{plugin_name}"

    # --- 1. Escaneo Recursivo de Carpetas 'static' dentro del Plugin ---
    for static_dir in plugin_path.rglob("static"):
      if static_dir.is_dir():
        # Obtiene la ruta relativa desde 'plugins/'
        # Ej: plugins/medioambiente/riles/static -> partes: ('medioambiente', 'riles', 'static')
        rel_parts = static_dir.relative_to(self.plugins_dir).parts
        
        # Nombre identificador para url_for (ej: 'static_medioambiente_riles')
        mount_name = "static_" + "_".join(rel_parts[:-1])
        
        # Prefijo de URL HTTP (ej: '/static/medioambiente/riles')
        url_prefix = "/static/" + "/".join(rel_parts[:-1])

        self.app.mount(
            url_prefix,
            StaticFiles(directory=str(static_dir)),
            name=mount_name,
        )

    # --- 2. Escaneo Recursivo de Carpetas 'pages' y 'templates' ---
    for target_dir in ["pages", "templates"]:
      for t_dir in plugin_path.rglob(target_dir):
        if t_dir.is_dir():
          self.template_dirs.append(t_dir)

    # --- 3. Importar Módulo Raíz del Plugin ---
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
    all_dirs = []
    
    # Prioridad: plantillas del plugin (pages/templates)
    all_dirs.extend([str(d) for d in self.template_dirs])

    # Fallback: plantillas globales (hola/templates)
    if global_templates_dir and global_templates_dir.exists():
      all_dirs.append(str(global_templates_dir))

    return Jinja2Templates(directory=all_dirs)