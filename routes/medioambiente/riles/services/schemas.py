from datetime import datetime
from typing import Any, Dict, Optional
from enum import Enum
from pydantic import BaseModel, field_validator, ConfigDict
from typing import Optional
from decimal import Decimal
from .models import StoreModule, Formato, EstadoConvenio


class PDFDataItem(BaseModel):
  name_archivo: str

  class Config:
    extra = "allow"


class AnalisisAguaSchema(BaseModel):
  empresa: Optional[str] = None
  local_id: Optional[str] = None
  local_nombre: Optional[str] = None
  local_region: Optional[str] = None
  local_comuna: Optional[str] = None
  local_direccion: Optional[str] = None
  local_rpm: Optional[str] = None
  local_convenio: Optional[str] = None
  laboratorio: Optional[str] = None
  fecha_emision: Optional[datetime] = None
  fecha_muestreo: Optional[datetime] = None
  tipo_muestreo: Optional[str] = None
  tipo_monitoreo:Optional[str] = None
  aceites_grasas: Optional[str] = None
  ph: Optional[str] = None
  dbo5: Optional[str] = None
  dqo: Optional[str] = None
  fosforo: Optional[str] = None
  nitrogeno_amoniacal: Optional[str] = None
  poder_espumogeno: Optional[str] = None
  solidos_sedimentables: Optional[str] = None
  solidos_suspendidos_totales: Optional[str] = None
  volumen_de_descarga_diaria: Optional[str] = None
  volumen_de_descarga_mensual: Optional[str] = None
  aluminio: Optional[str] = None
  arsenico: Optional[str] = None
  boro: Optional[str] = None
  cadmio: Optional[str] = None
  cianuro: Optional[str] = None
  zinc: Optional[str] = None
  cobre: Optional[str] = None
  cromo_total: Optional[str] = None
  cromo_hexavalente: Optional[str] = None
  hidrocarburos_totales: Optional[str] = None
  manganeso: Optional[str] = None
  mercurio: Optional[str] = None
  niquel: Optional[str] = None
  plomo: Optional[str] = None
  sulfatos: Optional[str] = None
  sulfuros: Optional[str] = None
  b64: Optional[str] = None

  @field_validator("fecha_emision", "fecha_muestreo", mode="before")
  @classmethod
  def parsear_fechas(cls, v):
    if v is None or isinstance(v, datetime):
      return v

    if isinstance(v, str):
      v = v.strip()
      # Si el string queda vacío tras el strip, retornamos None
      if not v:
        return None

      try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
      except ValueError:
        pass

      formatos = [
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
      ]
      for fmt in formatos:
        try:
          return datetime.strptime(v, fmt)
        except ValueError:
          continue

    return None

  model_config = ConfigDict(from_attributes=True)


class PDFInboxSchema(BaseModel):

  id_correo:Optional[str] =None 
  id_file:Optional[str] =None
  parameters: Dict[str, Any]
  is_active:bool=False

  class Config:
    from_attributes = True

class ParametroBase(BaseModel):
  parametro: str
  unidad: Optional[str] = None
  expresion: Optional[str] = None
  minimo: Optional[Decimal] = None
  maximo: Optional[Decimal] = None
  tolerancia_minimo: Optional[Decimal] = None
  tolerancia_maximo: Optional[Decimal] = None


class ParametroCreate(ParametroBase):
  pass


class ParametroUpdate(BaseModel):
  parametro: Optional[str] = None
  unidad: Optional[str] = None
  expresion: Optional[str] = None
  minimo: Optional[Decimal] = None
  maximo: Optional[Decimal] = None
  tolerancia_minimo: Optional[Decimal] = None
  tolerancia_maximo: Optional[Decimal] = None


class ParametroResponse(ParametroBase):
  id: int

  model_config = ConfigDict(from_attributes=True)

class File_b64_Schema(BaseModel):
  id_analisis: int
  b64: str

  model_config = ConfigDict(from_attributes=True)

class StoreBase(BaseModel):
  dirreccion: str
  nombre: str
  region: str
  comuna: str
  rpm: int
  empresa_distribuidora: str
  formato: Formato
  convenio: EstadoConvenio

  @field_validator("rpm", mode="before")
  @classmethod
  def parse_rpm(cls, v: str | int) -> int:
    if isinstance(v, str):
      v = v.strip()
      return int(v) if v else 0
    return v or 0


class StoreCreate(StoreBase):
  id_local: str


class StoreResponse(StoreBase):
  id_local: str

  model_config = ConfigDict(from_attributes=True)


class LocalMailBase(BaseModel):
  id_local: str
  mail: str
  mail_type: str


class LocalMailSchema(LocalMailBase):
  id_local_mail: int

  model_config = {
    "from_attributes": True
  }  # Sintaxis moderna para Pydantic v2

