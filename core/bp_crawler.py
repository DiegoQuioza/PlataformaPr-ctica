import enum
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path
from sqlalchemy import (
  Column,
  Integer,
  String,
  Boolean,
  DateTime,
  ForeignKey,
  Enum,
  CheckConstraint,
  create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from paths import BACKGROUND_PROCESSES_DIR, DB_DIR

# ------------------------------------------------------------------
# 1. Configuración de la Base de Datos
# ------------------------------------------------------------------
PROCESSES_DB_PATH = DB_DIR / "processes_registry.db"
DATABASE_URL = f"sqlite:///{PROCESSES_DB_PATH.as_posix()}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class ExecutionStatus(str, enum.Enum):
  PENDING = "PENDING"
  RUNNING = "RUNNING"
  SUCCESS = "SUCCESS"
  FAILED = "FAILED"

class BackgroundProcessModel(Base):
  __tablename__ = "background_processes"

  id = Column(String(100), primary_key=True)
  clave_modulo = Column(String(255), nullable=False)
  name = Column(String(255), nullable=False)
  description = Column(String(500), nullable=True)
  category = Column(String(100), nullable=True)
  version = Column(String(50), nullable=True)
  enabled = Column(Boolean, default=False, nullable=False)
  last_run = Column(DateTime, nullable=True)
  updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

  schedules = relationship(
      "ProcessScheduleModel",
      back_populates="process",
      cascade="all, delete-orphan",
  )


class ProcessScheduleModel(Base):
  __tablename__ = "process_schedules"

  id = Column(Integer, primary_key=True, autoincrement=True)
  process_id = Column(
      String(100),
      ForeignKey("background_processes.id", ondelete="CASCADE"),
      nullable=False,
  )

  hour = Column(Integer, nullable=False)
  minute = Column(Integer, nullable=False)

  status = Column(
      Enum(ExecutionStatus), default=ExecutionStatus.PENDING, nullable=False
  )
  last_executed_at = Column(DateTime, nullable=True)
  created_at = Column(DateTime, default=datetime.now)

  __table_args__ = (
      CheckConstraint("hour >= 0 AND hour <= 23", name="check_valid_hour"),
      CheckConstraint(
          "minute >= 0 AND minute <= 59", name="check_valid_minute"
      ),
  )

  process = relationship("BackgroundProcessModel", back_populates="schedules")


Base.metadata.create_all(bind=engine)

# ------------------------------------------------------------------
# 3. Sincronización y Carga Dinámica
# ------------------------------------------------------------------
bp_dir = BACKGROUND_PROCESSES_DIR

str_bp_dir = str(bp_dir.resolve())
if str_bp_dir not in sys.path:
  sys.path.insert(0, str_bp_dir)


def sync_processes_to_db(diccionario_funciones):
  """Guarda y actualiza la metadata y los horarios por defecto en la BD."""
  db = SessionLocal()
  try:
    for clave, data in diccionario_funciones.items():
      meta = data["metadata"]
      process_id = meta.get("id", clave)

      db_process = (
          db.query(BackgroundProcessModel)
          .filter(BackgroundProcessModel.id == process_id)
          .first()
      )

      if not db_process:
        db_process = BackgroundProcessModel(
            id=process_id,
            clave_modulo=clave,
            name=meta.get("name", process_id),
            description=meta.get("description", ""),
            category=meta.get("category", "general"),
            version=meta.get("version", "1.0.0"),
            enabled=meta.get("enabled", False),
        )
        db.add(db_process)
      else:
        db_process.clave_modulo = clave
        db_process.name = meta.get("name", db_process.name)
        db_process.description = meta.get("description", db_process.description)
        db_process.category = meta.get("category", db_process.category)
        db_process.version = meta.get("version", db_process.version)

      # Actualizar la metadata en memoria con el estado real almacenado en la BD
      db.flush()
      meta["enabled"] = db_process.enabled
      meta["id"] = db_process.id

      # Registrar horarios predefinidos desde la metadata (si existen)
      schedules_config = meta.get("schedules", [])
      if schedules_config:
        for sched in schedules_config:
          hour = sched.get("hour")
          minute = sched.get("minute")

          if hour is not None and minute is not None:
            existing_schedule = (
                db.query(ProcessScheduleModel)
                .filter(
                    ProcessScheduleModel.process_id == process_id,
                    ProcessScheduleModel.hour == hour,
                    ProcessScheduleModel.minute == minute,
                )
                .first()
            )

            if not existing_schedule:
              new_schedule = ProcessScheduleModel(
                  process_id=process_id, hour=hour, minute=minute
              )
              db.add(new_schedule)

    db.commit()
  except Exception as e:
    db.rollback()
    print(f"Error al sincronizar procesos en la base de datos: {e}")
  finally:
    db.close()


def get_background_proceses():
  diccionario_funciones = {}

  for archivo in bp_dir.rglob("worker.py"):
    if archivo.name.startswith("__"):
      continue

    ruta_relativa = archivo.relative_to(bp_dir)
    archivo_metadata = archivo.parent / "metadata.json"

    metadata = {}
    if archivo_metadata.exists():
      try:
        with open(archivo_metadata, "r", encoding="utf-8") as f:
          metadata = json.load(f)
      except Exception as e:
        print(f"Error leyendo {archivo_metadata}: {e}")

    # Clave interna estándar (ej: "modulo_a/worker")
    clave_modulo = str(ruta_relativa.with_suffix("")).replace("\\", "/")

    # Construir el nombre de importación completo incluyendo el directorio base
    # Ejemplo: "background_processes.modulo_a.worker"
    partes_ruta = [bp_dir.name] + list(ruta_relativa.with_suffix("").parts)
    nombre_modulo_completo = ".".join(partes_ruta)

    spec = importlib.util.spec_from_file_location(
        nombre_modulo_completo, archivo
    )
    if spec and spec.loader:
      modulo = importlib.util.module_from_spec(spec)

      # Asignar paquete para soportar importaciones relativas dentro de worker.py
      modulo.__package__ = nombre_modulo_completo.rsplit(".", 1)[0]
      sys.modules[nombre_modulo_completo] = modulo

      try:
        spec.loader.exec_module(modulo)

        # Extraer la función 'run'
        func_run = getattr(modulo, "run", None)
        if callable(func_run):
          diccionario_funciones[clave_modulo] = {
              "run": func_run,
              "metadata": metadata,
          }
        else:
          print(
              f"Advertencia: {archivo} se cargó pero no tiene una función"
              " 'run' ejecutable."
          )

      except Exception as e:
        print(f"Error al ejecutar/cargar el módulo {archivo}: {e}")
        sys.modules.pop(nombre_modulo_completo, None)

  sync_processes_to_db(diccionario_funciones)

  return diccionario_funciones


def get_bp_schedule_by_id(process_id: str) -> dict:
  db = SessionLocal()
  try:
    process = (
        db.query(BackgroundProcessModel)
        .filter(BackgroundProcessModel.id == process_id)
        .first()
    )

    if not process:
      return {"error": f"Proceso con ID '{process_id}' no fue encontrado."}

    resultado = {
        "id": process.id,
        "clave_modulo": process.clave_modulo,
        "name": process.name,
        "description": process.description,
        "category": process.category,
        "version": process.version,
        "enabled": process.enabled,
        "last_run": process.last_run.isoformat() if process.last_run else None,
        "updated_at": (
            process.updated_at.isoformat() if process.updated_at else None
        ),
        "schedules": [
            {
                "id": sched.id,
                "hour": sched.hour,
                "minute": sched.minute,
                "status": (
                    sched.status.value
                    if isinstance(sched.status, ExecutionStatus)
                    else sched.status
                ),
                "last_executed_at": (
                    sched.last_executed_at.isoformat()
                    if sched.last_executed_at
                    else None
                ),
            }
            for sched in process.schedules
        ],
    }

    return resultado
  finally:
    db.close()


def update_columna_orm(process_id: str, nuevo_estado: bool):
  db = SessionLocal()
  try:
    process = (
        db.query(BackgroundProcessModel)
        .filter(BackgroundProcessModel.id == process_id)
        .first()
    )

    if process:
      process.enabled = nuevo_estado
      db.commit()
  except Exception as e:
    db.rollback()
    print(f"Error al actualizar estado: {e}")
  finally:
    db.close()

def add_schedule_to_process(process_id: str, hour: int, minute: int) -> dict:
  """Agrega un nuevo horario (hora y minuto) a un proceso existente."""
  # 1. Validaciones básicas de hora y minuto
  if not (0 <= hour <= 23):
    return {"error": "La hora debe estar en el rango de 0 a 23."}
  if not (0 <= minute <= 59):
    return {"error": "El minuto debe estar en el rango de 0 a 59."}

  db = SessionLocal()
  try:
    # 2. Verificar que el proceso exista
    process = (
        db.query(BackgroundProcessModel)
        .filter(BackgroundProcessModel.id == process_id)
        .first()
    )

    if not process:
      return {"error": f"Proceso con ID '{process_id}' no fue encontrado."}

    # 3. Evitar duplicar el mismo horario para este proceso
    existing_schedule = (
        db.query(ProcessScheduleModel)
        .filter(
            ProcessScheduleModel.process_id == process_id,
            ProcessScheduleModel.hour == hour,
            ProcessScheduleModel.minute == minute,
        )
        .first()
    )

    if existing_schedule:
      return {
          "error": (
              f"El horario {hour:02d}:{minute:02d} ya existe para este"
              " proceso."
          )
      }

    # 4. Crear y guardar el nuevo horario
    new_schedule = ProcessScheduleModel(
        process_id=process_id, hour=hour, minute=minute
    )
    db.add(new_schedule)
    db.commit()
    db.refresh(new_schedule)

    return {
        "id": new_schedule.id,
        "process_id": new_schedule.process_id,
        "hour": new_schedule.hour,
        "minute": new_schedule.minute,
        "status": new_schedule.status.value,
        "message": "Horario agregado exitosamente.",
    }
  
  except Exception as e:
    db.rollback()
    return {"error": f"Error al guardar el horario: {str(e)}"}
  finally:
    db.close()

def delete_schedule_to_process(scheduleId: int):
  db = SessionLocal()
  try:
    db.query(ProcessScheduleModel).filter(
        ProcessScheduleModel.id == scheduleId
    ).delete(synchronize_session=False)
    db.commit()
    return "listo"
  except Exception as e:
    db.rollback()
    print(f"Error al eliminar horario: {e}")
    raise e
  finally:
    db.close()

def update_schedule_to_process(schedule_id: int, hour: int, minute: int) -> dict:
  """Actualiza la hora y minuto de un horario existente."""
  if not (0 <= hour <= 23):
    return {"error": "La hora debe estar en el rango de 0 a 23."}
  if not (0 <= minute <= 59):
    return {"error": "El minuto debe estar en el rango de 0 a 59."}

  db = SessionLocal()
  try:
    schedule = (
        db.query(ProcessScheduleModel)
        .filter(ProcessScheduleModel.id == schedule_id)
        .first()
    )

    if not schedule:
      return {"error": f"El horario con ID {schedule_id} no existe."}

    # Validar duplicados para el mismo proceso
    existing = (
        db.query(ProcessScheduleModel)
        .filter(
            ProcessScheduleModel.process_id == schedule.process_id,
            ProcessScheduleModel.hour == hour,
            ProcessScheduleModel.minute == minute,
            ProcessScheduleModel.id != schedule_id,
        )
        .first()
    )

    if existing:
      return {"error": f"Ya existe un horario a las {hour:02d}:{minute:02d}."}

    schedule.hour = hour
    schedule.minute = minute
    db.commit()

    return {"message": "Horario actualizado correctamente."}
  except Exception as e:
    db.rollback()
    return {"error": f"Error al actualizar el horario: {str(e)}"}
  finally:
    db.close()