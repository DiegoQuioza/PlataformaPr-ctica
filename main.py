import os
import sys
# Garantizar que el directorio raíz 'hola' esté en el sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
  sys.path.insert(0, BASE_DIR)

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from datetime import datetime

# Librerías de Scheduler de procesos en segundo plano
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio

# Importar rutas centralizadas desde paths.py
from paths import TEMPLATES_DIR, STATIC_DIR, DB_DIR,PLUGINS_DIR

# Importar módulos de endpoints
# from routes.documentation import router as doc_router
from core.plugin_manager import PluginManager


from pydantic import BaseModel, Field

# from functools import partialf
from pytz import timezone # O usa zoneinfo en Python 3.9+

# Importar funciones y modelos desde tu gestor bp_crawler
from core.bp_crawler import (
    get_background_proceses,
    get_bp_schedule_by_id,
    update_columna_orm,
    add_schedule_to_process,
    delete_schedule_to_process,
    SessionLocal,
    BackgroundProcessModel,
    ProcessScheduleModel,
    ExecutionStatus,
    update_schedule_to_process
)

from core.scheduler_service import (
    scheduler,
    load_schedules_from_db,
    register_single_job,
    remove_single_job,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
  # 1. Cargar la base de datos al scheduler al iniciar
  load_schedules_from_db()

  # 2. Iniciar el scheduler
  scheduler.start()
  print("Scheduler iniciado correctamente.")

  yield

  # 3. Apagar al cerrar FastAPI
  scheduler.shutdown()
  print("Scheduler detenido.")


# Única instancia de FastAPI para toda la app
app = FastAPI(
  title="Automatizaciones | Sostenibilidad",
  lifespan=lifespan
)

plugin_manager = PluginManager(app=app, plugins_dir=PLUGINS_DIR)
plugin_manager.discover_and_load()

# Configurar motor Jinja2 unificado que busca en /templates globales y en cada plugin
templates = plugin_manager.get_jinja_templates(
    global_templates_dir=TEMPLATES_DIR
)

# Estáticos globales opcionales
if STATIC_DIR.exists():
  app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Imprimir resumen de inicialización en consola
print("=" * 60)
print(
    f"🚀 [PLUGIN ENGINE] Carga finalizada. {len(plugin_manager.loaded_plugins)} routers integrados:"
)
for loaded in plugin_manager.loaded_plugins:
  print(f"  ├─ {loaded}")
print("=" * 60)

# Endpoint raíz principal
@app.get("/")
async def inicio(request: Request):
  datos = {
    "titulo": "Panel de Automatizaciones | Sostenibilidad"
  }
  return templates.TemplateResponse(
    request=request,
    name="index.html",
    context=datos
  )

# Endpoint global de automatizaciones (lee el arbol OpenAPI de toda la app)
@app.get("/automatizaciones")
def automatizaciones(request: Request):
  openapi = app.openapi()
  arbol = {} 
  for path, methods in openapi["paths"].items():
    for method, info in methods.items():
      tags = info.get("tags", ["Sin categoría"])
      for tag in tags:
        arbol.setdefault(tag, []).append({
          "titulo": info.get("summary") or path,
          "descripcion": info.get("description"),
          "ruta": path,
          "metodo": method.upper()
        })

  return templates.TemplateResponse(
    request, 
    name="automatizaciones.html", 
    context={"titulo": "Automatizaciones", "arbol": arbol}
  )

@app.get("/background-processes")
def background_proceses(request: Request):
  procesos = get_background_proceses()
  return templates.TemplateResponse(
    request,
    name = "background-processes.html",
    context={"titulo":"Procesos en segundo plano", "procesos":procesos}
  )

@app.get("/background-processes-all")
def all_background_proceses():
  procesos = get_background_proceses()
  return procesos

@app.get("/background-process-schedule/{process_id}")
def read_bp_schedule_by_id(process_id: str):
  resultado = get_bp_schedule_by_id(process_id)

  if "error" in resultado:
    raise HTTPException(status_code=404, detail=resultado["error"])

  return resultado

@app.post("/background-process-schedule/{process_id}")
def enable_or_disable_schedule_by_id(process_id: str):
  resultado = get_bp_schedule_by_id(process_id)

  if "error" in resultado:
    raise HTTPException(status_code=404, detail=resultado["error"])

  Actualstatus = resultado["enabled"]
  Newstatus = not Actualstatus
  update_columna_orm(process_id,Newstatus)

  return get_bp_schedule_by_id(process_id)

class ScheduleCreate(BaseModel):
  hour: int = Field(..., ge=0, le=23, description="Hora en formato 24h (0-23)")
  minute: int = Field(..., ge=0, le=59, description="Minuto (0-59)")


@app.post("/background-process-schedule/{process_id}/add")
def create_schedule_endpoint(process_id: str, schedule: ScheduleCreate):
  resultado = add_schedule_to_process(
      process_id=process_id, hour=schedule.hour, minute=schedule.minute
  )

  if "error" in resultado:
    raise HTTPException(status_code=400, detail=resultado["error"])

  db = SessionLocal()
  try:
    process = (
        db.query(BackgroundProcessModel)
        .filter(BackgroundProcessModel.id == process_id)
        .first()
    )
    sched = (
        db.query(ProcessScheduleModel)
        .filter(
            ProcessScheduleModel.process_id == process_id,
            ProcessScheduleModel.hour == schedule.hour,
            ProcessScheduleModel.minute == schedule.minute,
        )
        .first()
    )

    if process and sched and process.enabled:
      register_single_job(process, sched)
  finally:
    db.close()

  return resultado

@app.delete("/background-process-schedule/item/{scheduleId}")
def delete_schedule_endpoint(scheduleId: int):
  db = SessionLocal()
  process_id = None
  try:
    sched = (
        db.query(ProcessScheduleModel)
        .filter(ProcessScheduleModel.id == scheduleId)
        .first()
    )
    if sched:
      process_id = sched.process_id
  finally:
    db.close()

  delete_schedule_to_process(scheduleId)

  if process_id:
    remove_single_job(process_id, scheduleId)

  return {"message": "Horario eliminado correctamente"}

@app.put("/background-process-schedule/item/{scheduleId}")
def update_schedule_endpoint(scheduleId: int, schedule: ScheduleCreate):
  resultado = update_schedule_to_process(
      schedule_id=scheduleId, hour=schedule.hour, minute=schedule.minute
  )

  if "error" in resultado:
    raise HTTPException(status_code=400, detail=resultado["error"])

  return resultado

if __name__ == "__main__":
  uvicorn.run(
    "main:app",
    host="0.0.0.0",
    port=8000,
    reload=True
  )