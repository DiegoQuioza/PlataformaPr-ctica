import base64
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Request,Response, UploadFile, status, Body
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any

from automations.medioambiente.riles.automatizaciones.lectorPdf.main import (
    export_analysis_to_json,
    process_pdf_bytes,
)
import automations.medioambiente.riles.automatizaciones.Envio_correos.main as MailingService

from paths import STATIC_DIR, TEMPLATES_DIR

import pandas as pd 
import io

from .database import Base, engine, get_db

from .models import(
  AnalisisAguaModel,
  PDFInboxModel,
  ParametroModel,
  MailingModel,
  EvaluacionParametrosModel,
  File_b64_Model,
  calcular_estado_parametro,
  parse_float_val,
  MAPEO_NOMBRES_COLUMNAS
  )

from .schemas import (
  AnalisisAguaSchema,
  PDFInboxSchema, 
  ParametroCreate,
  ParametroResponse,
  ParametroUpdate,
  File_b64_Schema
  )

Base.metadata.create_all(bind=engine)

router = APIRouter(prefix="/riles", tags=["Automatización de riles"])

templates = Jinja2Templates(directory=TEMPLATES_DIR)
router.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@router.post(
    "/api/v1/process-pdf",
    summary="Procesar un único PDF",
    status_code=status.HTTP_200_OK,
)
async def process_single_pdf(file: UploadFile = File(...)):
  if not file.filename.lower().endswith(".pdf"):
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="El archivo proporcionado no es un PDF válido.",
    )

  file_bytes = await file.read()
  result = process_pdf_bytes(file_bytes=file_bytes, filename=file.filename)

  if not result:
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=(
            "No se pudo identificar el laboratorio o procesar el archivo"
            f" '{file.filename}'."
        ),
    )

  return {"status": "exito", "data": result}


@router.post(
    "/api/v1/process-multiple-pdfs",
    summary="Procesar múltiples archivos PDF",
    status_code=status.HTTP_200_OK,
    openapi_extra={
        "requestBody": {
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "files": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "format": "binary",
                                },
                                "description": (
                                    "Lista de archivos PDF a procesar"
                                ),
                            }
                        },
                        "required": ["files"],
                    }
                }
            }
        }
    },
)
async def process_multiple_pdfs(files: List[UploadFile] = File(...)):
  if not files:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Debes adjuntar al menos un archivo PDF.",
    )

  files_data = []
  for file in files:
    if file.filename and file.filename.lower().endswith(".pdf"):
      try:
        content = await file.read()
        pdf_base64 = base64.b64encode(content).decode("utf-8")
        files_data.append((content, file.filename, pdf_base64))
      finally:
        await file.close()

  if not files_data:
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Ninguno de los archivos adjuntos es un PDF válido.",
    )

  response = export_analysis_to_json(files_data)
  return response

@router.post("/api/v1/save-pdf-b64", status_code=status.HTTP_201_CREATED)
async def save_pdf_b64(
  payload: File_b64_Schema,
  db: Session = Depends(get_db)
) -> Dict[str, Any]:
  try:
    # 1. Verificar que el análisis asociado exista en la base de datos
    analisis_existente = (
      db.query(AnalisisAguaModel)
      .filter(AnalisisAguaModel.id == payload.id_analisis)
      .first()
    )
    
    if not analisis_existente:
      raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"No se encontró el análisis con ID {payload.id_analisis}"
      )

    # 2. Manejar la relación 1:1 (Insertar o Actualizar si ya existe)
    registro_b64 = (
      db.query(File_b64_Model)
      .filter(File_b64_Model.id_analisis == payload.id_analisis)
      .first()
    )

    if registro_b64:
      registro_b64.b64 = payload.b64
    else:
      registro_b64 = File_b64_Model(
        id_analisis=payload.id_analisis,
        b64=payload.b64
      )
      db.add(registro_b64)

    db.commit()
    db.refresh(registro_b64)

    return {
      "status": "success",
      "message": "Archivo Base64 guardado correctamente.",
      "id": registro_b64.id,
      "id_analisis": registro_b64.id_analisis
    }

  except HTTPException:
    raise
  except Exception as e:
    db.rollback()
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=f"Error al guardar el archivo Base64: {str(e)}"
    )

@router.get(
    "/api/v1/download-pdf-b64/{id_analisis}", status_code=status.HTTP_200_OK
)
async def download_pdf_b64(id_analisis: int, db: Session = Depends(get_db)):
  try:
    # 1. Buscar el registro en la base de datos por el id_analisis
    registro_b64 = (
        db.query(File_b64_Model)
        .filter(File_b64_Model.id_analisis == id_analisis)
        .first()
    )

    if not registro_b64 or not registro_b64.b64:
      raise HTTPException(
          status_code=status.HTTP_404_NOT_FOUND,
          detail=f"No se encontró un archivo PDF para el análisis ID {id_analisis}",
      )

    # 2. Decodificar la cadena Base64 a bytes binarios
    # Si la cadena incluye el prefijo 'data:application/pdf;base64,', se limpia primero
    cadena_b64 = registro_b64.b64
    if "," in cadena_b64:
      cadena_b64 = cadena_b64.split(",")[1]                                     

    pdf_bytes = base64.b64decode(cadena_b64)

    # 3. Retornar los bytes formateados como respuesta de descarga de PDF
    headers = {
        "Content-Disposition": f"attachment; filename=analisis_{id_analisis}.pdf"
    }

    return Response(
        content=pdf_bytes, media_type="application/pdf", headers=headers
    )

  except HTTPException:
    raise
  except Exception as e:
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Error al generar la descarga del archivo: {str(e)}",
    )

@router.get(
    "/api/v1/get-pdf-b64/{id_analisis}", status_code=status.HTTP_200_OK
)
def get_pdf_b64(id_analisis: int, db: Session = Depends(get_db))-> str:
  registro_b64 = (
      db.query(File_b64_Model)
      .filter(File_b64_Model.id_analisis == id_analisis)
      .first()
  )
  if not registro_b64:
    return ""
  return registro_b64.b64

@router.post("/api/v1/evaluar-analisis/{id_analisis}", status_code=status.HTTP_201_CREATED)
async def evaluar_analisis(id_analisis: int, db: Session = Depends(get_db)):
  analisis = db.query(AnalisisAguaModel).filter(AnalisisAguaModel.id == id_analisis).first()
  if not analisis:
    raise HTTPException(
      status_code=status.HTTP_404_NOT_FOUND,
      detail=f"No se encontró el análisis con ID {id_analisis}"
    )

  evaluacion_existente = db.query(EvaluacionParametrosModel).filter(
    EvaluacionParametrosModel.id_analisis == id_analisis
  ).first()

  if evaluacion_existente:
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="Este análisis ya fue evaluado previamente."
    )

  reglas_db = db.query(ParametroModel).all()
  if not reglas_db:
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail="No hay parámetros configurados en la tabla parametros."
    )

  evaluacion_dict = {"id_analisis": id_analisis}
  supera_ratio_global = False

  for regla in reglas_db:
    campo_nombre = MAPEO_NOMBRES_COLUMNAS.get(regla.parametro)
    if not campo_nombre or not hasattr(analisis, campo_nombre):
      continue

    valor_raw = getattr(analisis, campo_nombre, None)
    valor_num = parse_float_val(valor_raw)

    if valor_num is not None:
      estado = calcular_estado_parametro(valor_num, regla)
      evaluacion_dict[campo_nombre] = estado

      if estado == 2:
        supera_ratio_global = True
    else:
      evaluacion_dict[campo_nombre] = None

  if supera_ratio_global:
    nueva_evaluacion = EvaluacionParametrosModel(**evaluacion_dict)
    db.add(nueva_evaluacion)
    db.commit()
    db.refresh(nueva_evaluacion)

    return {
      "status": "created",
      "message": "Se detectaron parámetros que superan el ratio permitido. Registro guardado.",
      "evaluacion_id": nueva_evaluacion.id,
      "detalle": evaluacion_dict
    }

  return {
    "status": "ignored",
    "message": "Ningún parámetro superó el ratio de tolerancia. No se creó registro.",
    "detalle": evaluacion_dict
  }

def procesar_evaluacion_analisis(
  analisis: AnalisisAguaModel, 
  reglas_db: List[ParametroModel], 
  db: Session
) -> EvaluacionParametrosModel:
  """
  Aplica la evaluación a un análisis y agrega siempre la entidad a la sesión
  sin hacer db.commit() para preservar la transacción atómica.
  """
  evaluacion_dict = {"id_analisis": analisis.id}

  # Normalizar diccionario de mapeo (minúsculas y sin espacios extra)
  mapeo_normalizado = {
    k.strip().lower(): v for k, v in MAPEO_NOMBRES_COLUMNAS.items()
  }

  for regla in reglas_db:
    if not regla.parametro:
      continue

    nombre_parametro_db = regla.parametro.strip().lower()
    campo_nombre = mapeo_normalizado.get(nombre_parametro_db)

    if not campo_nombre or not hasattr(analisis, campo_nombre):
      continue

    valor_raw = getattr(analisis, campo_nombre, None)
    valor_num = parse_float_val(valor_raw)

    if valor_num is not None:
      estado = calcular_estado_parametro(valor_num, regla)
      evaluacion_dict[campo_nombre] = estado
    else:
      evaluacion_dict[campo_nombre] = None

  # Se instancia y agrega a la sesión siempre, independientemente de los valores
  nueva_evaluacion = EvaluacionParametrosModel(**evaluacion_dict)
  db.add(nueva_evaluacion)

  return nueva_evaluacion

@router.get("/api/v1/get-pdf-data", status_code=status.HTTP_200_OK)
async def get_pdf_data(
    analysis_id: int | None = None,
    db: Session = Depends(get_db)
  ):
  try:
    return db.query(AnalisisAguaModel).filter(AnalisisAguaModel.id == analysis_id).all()
  
  except Exception as e:
    db.rollback()
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=f"Error al consultar los datos de ${analysis_id}: {str(e)}",
    )


@router.post("/api/v1/save-pdf-data", status_code=status.HTTP_201_CREATED)
async def save_pdf_data(
  payload: List[AnalisisAguaSchema], db: Session = Depends(get_db)
):
  try:
    reglas_db = db.query(ParametroModel).all()
    if not reglas_db:
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="No hay parámetros de norma configurados en la base de datos."
      )

    registros_creados = 0

    for item in payload:
      item_dict = item.model_dump()
      item_dict.pop("id", None)

      contenido_b64 = item_dict.pop("b64", None)

      nuevo_registro = AnalisisAguaModel(**item_dict)
      db.add(nuevo_registro)

      # 1. Forzar persistencia inmediata para que SQLite incremente la PK y asigne la nueva ID
      db.flush()
      db.refresh(nuevo_registro)

      if contenido_b64:
        nuevo_b64 = File_b64_Model(
          id_analisis=nuevo_registro.id,
          b64=contenido_b64
        )
        db.add(nuevo_b64)

      # 2. Verificar o limpiar registros previos si id_analisis en evaluacion_parametros es UNIQUE / PK
      evaluacion_existente = (
        db.query(EvaluacionParametrosModel)
        .filter(EvaluacionParametrosModel.id_analisis == nuevo_registro.id)
        .first()
      )

      if evaluacion_existente:
        db.delete(evaluacion_existente)
        db.flush()

      # Crear Mailing asociado
      nuevo_mailing = MailingModel(id_analisis=nuevo_registro.id)
      db.add(nuevo_mailing)

      # Generar y agregar registro de evaluación
      procesar_evaluacion_analisis(
        analisis=nuevo_registro, reglas_db=reglas_db, db=db
      )

      registros_creados += 1

    db.commit()

    return {
      "status": "success",
      "message": f"Se guardaron {registros_creados} registros correctamente.",
      "count": registros_creados,
    }

  except Exception as e:
    db.rollback()
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=f"Error al guardar en la base de datos: {str(e)}",
    )

@router.delete("/api/v1/delete-pdf-data", status_code=status.HTTP_201_CREATED)
async def delete_pdf_data(db: Session = Depends(get_db)
):
  try:
    um_rows_deleted = db.query(AnalisisAguaModel).delete(synchronize_session=False)
    db.commit()

    return {
        "status": "success",
        "message": (
            f"Se Eliminaron {um_rows_deleted} registros, de la tabla analisis_agua"
        )

    }

  except Exception as e:
    db.rollback()
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Error al guardar en la base de datos: {str(e)}",
    )

@router.post("/api/v1/set-inbox-params",status_code=status.HTTP_201_CREATED)
def set_inbox(
  payload: List[PDFInboxSchema], db: Session = Depends(get_db)
):
  """
  Esta función está pensada para trabajar con el worker.
  guarda los resultados de los pdf extraidos de correos a una base de datos
  """
  try:
    nuevos_registros = [
      PDFInboxModel(**item.model_dump()) 
      for item in payload
    ]

    # Insertamos todos los registros en una sola operación
    db.add_all(nuevos_registros)
    db.commit()

    cantidad = len(nuevos_registros)

    return {
      "status": "success",
      "message": f"Se guardaron {cantidad} registros correctamente.",
      "count": cantidad,
    }
  except Exception as e:
    db.rollback()
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=f"Error al guardar en la base de datos: {str(e)}",
    )

@router.patch("/api/v1/deactivate-inbox", status_code=status.HTTP_200_OK)
def deactivate_inbox(payload: List[str] = Body(...), db: Session = Depends(get_db)):
  """
  Recibe una lista de id_correo y los marca como inactivos en la BD.
  """
  print(payload)
  
  if not payload:
    return {
      "status": "success",
      "message": "No se enviaron IDs para inactivar.",
      "count": 0
    }

  try:
    updated_rows = db.query(PDFInboxModel).filter(
      PDFInboxModel.id_correo.in_(payload)
    ).update(
      {PDFInboxModel.is_active: False}, 
      synchronize_session=False
    )

    db.commit()

    return {
      "status": "success",
      "message": f"Se marcaron {updated_rows} registros como inactivos correctamente.",
      "count": updated_rows
    }
  except Exception as e:
    db.rollback()
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=f"Error al inactivar los registros: {str(e)}"
    )
  
@router.get("/api/v1/get-inbox",status_code=status.HTTP_200_OK)
def get_inbox_params(db: Session = Depends(get_db)):
  try:
    items = db.query(PDFInboxModel).filter(PDFInboxModel.is_active == True).all()
    return items
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/v1/get-deactivated-inbox",status_code=status.HTTP_200_OK)
def get_deactivated_inbox_ids(db: Session = Depends(get_db)):
  try:
    items = db.query(PDFInboxModel.id_correo).filter(PDFInboxModel.is_active == False).all()
    correos = [row[0] for row in items]
    return correos
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/v1/get-opened-inbox",status_code=status.HTTP_200_OK)
def get_opened_inbox_ids(db: Session = Depends(get_db)):
  try:  
    items = db.query(PDFInboxModel.id_correo).all()
    correos = [row[0] for row in items]
    return correos
  except Exception as e:
    raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/v1/clear-inbox", status_code=status.HTTP_200_OK)
def clear_inbox_table(db: Session = Depends(get_db)):
  try:
    # Elimina todos los registros de la tabla pdf_inbox
    num_rows_deleted = db.query(PDFInboxModel).delete(synchronize_session=False)
    db.commit()

    return {
      "status": "success",
      "message": f"Se eliminaron {num_rows_deleted} registros de la tabla.",
      "count": num_rows_deleted
    }
  except Exception as e:
    db.rollback()
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=f"Error al vaciar la tabla: {str(e)}"
    )
  
@router.post(
  "/api/v1/parameter-limits",
  summary="Cargar límites de parámetros desde Excel/CSV",
  status_code=status.HTTP_201_CREATED,
  response_model=List[ParametroResponse],
)
async def set_parameters_limits(
  file: UploadFile = File(...),
  db: Session = Depends(get_db)
):
  if not (file.filename.endswith(".xlsx") or file.filename.endswith(".csv")):
    raise HTTPException(
      status_code=status.HTTP_400_BAD_REQUEST,
      detail="El archivo debe ser formato .xlsx o .csv"
    )

  contents = await file.read()

  if file.filename.endswith(".xlsx"):
    df = pd.read_excel(io.BytesIO(contents))
  else:
    df = pd.read_csv(io.BytesIO(contents))

  # Normalización de nombres de columnas
  df.columns = df.columns.str.strip()

  column_mapping = {
    "Parámetro": "parametro",
    "Unidad": "unidad",
    "Expresión": "expresion",
    "Mínimo": "minimo",
    "Maximo": "maximo",
    "Tolerancia Mínimo (-)": "tolerancia_minimo",
    "Tolerancia Maximo (+)": "tolerancia_maximo",
  }

  df = df.rename(columns=column_mapping)

  # Formateo de números decimales (comas a puntos)
  numeric_cols = [
    "minimo",
    "maximo",
    "tolerancia_minimo",
    "tolerancia_maximo",
  ]
  
  for col in numeric_cols:
    if col in df.columns:
      df[col] = (
        df[col]
        .astype(str)
        .str.replace(",", ".")
        .str.strip()
      )
      df[col] = pd.to_numeric(df[col], errors="coerce")

  # Limpieza de valores nulos/NaN para compatibilidad con Pydantic
  df = df.where(pd.notnull(df), None)

  records = df.to_dict(orient="records")
  nuevos_parametros = []

  db.query(ParametroModel).delete()

  for record in records:
    param_data = ParametroCreate(**record)
    db_param = ParametroModel(**param_data.model_dump())
    db.add(db_param)
    nuevos_parametros.append(db_param)

  db.commit()

  for param in nuevos_parametros:
    db.refresh(param)

  return nuevos_parametros

@router.put(
  "/api/v1/parameter-limits/{param_id}",
  summary="Actualizar un parámetro por ID",
  status_code=status.HTTP_200_OK,
  response_model=ParametroResponse,
)
async def update_parameter_limit(
  param_id: int,
  param_data: ParametroUpdate,
  db: Session = Depends(get_db),
):
  db_param = db.query(ParametroModel).filter(ParametroModel.id == param_id).first()

  if not db_param:
    raise HTTPException(
      status_code=status.HTTP_404_NOT_FOUND,
      detail=f"El parámetro con ID {param_id} no existe.",
    )

  update_data = param_data.model_dump(exclude_unset=True)

  for key, value in update_data.items():
    setattr(db_param, key, value)

  db.commit()
  db.refresh(db_param)

  return db_param

@router.get(
  "/api/v1/parameter-limits",
  summary="Obtener todos los parámetros",
  status_code=status.HTTP_200_OK,
  response_model=List[ParametroResponse],
)
async def get_parameters_limits(db: Session = Depends(get_db)):
  return db.query(ParametroModel).all()


@router.get(
    "/api/v1/tolerance",
    summary="Obtener nivel de tolerancia",
    status_code=status.HTTP_200_OK,
)
async def get_analysis_tolerance(
    analysis_id: int | None = None,
    local_id: int | None = None,
    db: Session = Depends(get_db),
):
  query = db.query(AnalisisAguaModel, EvaluacionParametrosModel).join(
      EvaluacionParametrosModel,
      AnalisisAguaModel.id == EvaluacionParametrosModel.id_analisis,
  )

  if analysis_id is not None:
    query = query.filter(AnalisisAguaModel.id == analysis_id)
  elif local_id is not None:
    query = query.filter(AnalisisAguaModel.local_id == local_id)
  else:
    return []

  consulta = query.all()
  resultado_final = []

  # Lista explícita de las columnas de evaluación (excluyendo IDs y metadata)
  columnas_evaluacion = [
      c.key
      for c in EvaluacionParametrosModel.__table__.columns
      if c.key not in ("id", "id_analisis")
  ]

  for analisis, evaluacion in consulta:
    parametros_tolerables = []
    parametros_extremos = []
    parametros_correctos = []

    for parametro in columnas_evaluacion:
      # getattr fuerza a SQLAlchemy a traer el valor correcto sin depender del __dict__
      estado = getattr(evaluacion, parametro, None)

      if estado is None:
        continue

      valor_raw = getattr(analisis, parametro, None)
      valor_parsed = parse_float_val(valor_raw)

      detalle_parametro = {
          "parametro": parametro,
          "estado": estado,
          "valor": valor_parsed,
      }

      if estado == 1:
        parametros_tolerables.append(detalle_parametro)
      elif estado == 2:
        parametros_extremos.append(detalle_parametro)
      else:
        parametros_correctos.append(detalle_parametro)

    es_tolerable = len(parametros_extremos) == 0

    resultado_final.append({
        "analysis_id": analisis.id,
        "tolerable": es_tolerable,
        "cant_parametros_tolerables": len(parametros_tolerables),
        "cant_parametros_extremos": len(parametros_extremos),
        "parametros_tolerables": parametros_tolerables,
        "parametros_extremos": parametros_extremos,
        "parametros_correctos": parametros_correctos,
    })

  return resultado_final

@router.get("/api/v1/get-mailing-queue", status_code=status.HTTP_200_OK)
def get_mailing_queue(db: Session = Depends(get_db)):
  try:
    return db.query(MailingModel).filter(MailingModel.status=="PENDIENTE").all()
  except Exception as e:
    db.rollback()
    raise HTTPException(
      status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
      detail=f"Error al consultar tabla mailing: {str(e)}",
    )

@router.delete("/api/v1/delete-mailing-queue", status_code=status.HTTP_201_CREATED)
async def delete_mailing_queue(db: Session = Depends(get_db)
):
  try:
    um_rows_deleted = db.query(MailingModel).delete(synchronize_session=False)
    db.commit()

    return {
        "status": "success",
        "message": (
            f"Se Eliminaron {um_rows_deleted} registros, de la tabla mailing"
        )
    }
  except Exception as e:
    db.rollback()
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Error al guardar en la base de datos: {str(e)}",
    )

@router.delete("/api/v1/delete-param-eval", status_code=status.HTTP_201_CREATED)
async def delete_parameter_evaluation(db: Session = Depends(get_db)
):
  try:
    um_rows_deleted = db.query(EvaluacionParametrosModel).delete(synchronize_session=False)
    db.commit()

    return {
        "status": "success",
        "message": (
            f"Se Eliminaron {um_rows_deleted} registros, de la tabla evaluacion_parametros"
        )
    }
  except Exception as e:
    db.rollback()
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Error al guardar en la base de datos: {str(e)}",
    )

@router.post("/api/v1/send-analysis-mailing", status_code=status.HTTP_201_CREATED)
async def send_analysis_mailing(
  analysis_id: int, 
  db: Session = Depends(get_db)
):
  # 1. Agregar await para resolver las corrutinas y pasar la sesión de BD (db)
  res_tolerance = await get_analysis_tolerance(analysis_id=analysis_id, db=db)
  res_pdf_data = await get_pdf_data(analysis_id=analysis_id, db=db)
  res_download_b64 = get_pdf_b64(id_analisis=analysis_id,db=db)

  if not res_tolerance or not res_pdf_data:
    raise HTTPException(
      status_code=status.HTTP_404_NOT_FOUND,
      detail=f"No se encontraron datos para el análisis {analysis_id}"
    )

  # 2. Mapear 'res_pdf_data' si devuelve un objeto SQLAlchemy ORM a un diccionario
  first_pdf = res_pdf_data[0]
  pdf_dict = first_pdf.__dict__ if hasattr(first_pdf, "__dict__") else first_pdf

  tolerance_dict = res_tolerance[0] if isinstance(res_tolerance, list) else {}
  
  # 3. Unificar los datos en la estructura final
  data = {
    **tolerance_dict,
    **pdf_dict,
    "b64": res_download_b64}


  # 4. Enviar a la función de correo
  MailingService.run(data)

  return {"status": "success", "message": f"Correo enviado para el análisis {analysis_id}"}

@router.get("/")
async def inicio(request: Request):
  datos = {"titulo": "Panel de Lectura de pdf Riles | Medioambiente"}
  return templates.TemplateResponse(
      request=request, name="riles/main.html", context=datos
  )

@router.get("/upload")
async def upload(request: Request):
  datos = {"titulo": "Panel de Lectura de pdf Riles | Medioambiente"}
  return templates.TemplateResponse(
      request=request, name="riles/uploadFiles.html", context=datos
  )

@router.get("/inbox")
async def inbox(request: Request):
  datos = {"titulo": "Panel de Lectura de pdf Riles | Medioambiente"}
  return templates.TemplateResponse(
      request=request, name="riles/inbox.html", context=datos
  )

@router.get("/parameter-limits")
async def parameter_limits(request: Request):
  datos = {"titulo": "Limites de parámetros para riles | Medioambiente"}
  return templates.TemplateResponse(
      request=request, name="riles/paramlimits.html", context=datos
  )