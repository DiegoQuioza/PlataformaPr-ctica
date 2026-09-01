import io
from pathlib import Path
import re
from typing import Union, Dict, Any, Optional

from utils.dtos import AnalisisAguaDTO
from utils.data_cleaning import full_parsing, remove_symbol
from utils.models import search_store_id
from utils.utils import (
  get_data_list,
  print_pdf_results,
  get_pdf_table,
  extract_lines_by_text,
  extract_text_in_lines
)

mapeo = AnalisisAguaDTO()
laboratorio = "Merieux"


def get_address(file_input: Union[str, Path, bytes, io.BytesIO]):
  def ignore_words(line):
    words_to_ignore = ["lugar", "direccion", "dirección", "muestreo"]
    formated_line = line.lower()
    if formated_line.find(",") >= 0:
      formated_line = formated_line.split(",")[0]
    if formated_line.find("-") >= 0:
      formated_line = formated_line.split("-")[0]

    for wti in words_to_ignore:
      formated_line = formated_line.replace(wti.lower(), "")

    return formated_line

  address_lines = get_data_list(file_input, "store_address")
  print("####################", address_lines)
  for al in address_lines:
    if al.lower().find("plomo") < 0:
      al_formated = ignore_words(al)
      print(al_formated)
      store_data = search_store_id(al_formated)
      print("store_data: ", store_data)
      if store_data:
        return store_data


def mapping_sendDate(file_input: Union[str, Path, bytes, io.BytesIO]):
  dateArray = get_data_list(file_input, "date_keywords")
  patron = r"\d{2}-\d{2}-\d{4}"
  patron2 = r"\d{2}/\d{2}/\d{4}"
  fechas = {
    "emision": "",
    "muestreo": ""
  }
  muestreoCounter = 0
  emisionCounter = 0

  for date in dateArray:
    actualDate: str = date
    if emisionCounter == 0 and actualDate.lower().find("emisión") > 0:
      numeros = re.findall(patron, actualDate)
      if not numeros:
        numeros = re.findall(patron2, actualDate)
      fechaFinal = "/".join(numeros)
      fechas["emision"] = fechaFinal
      emisionCounter += 1

    if muestreoCounter == 0 and actualDate.lower().find("ingreso") > 0:
      numeros = re.findall(patron, actualDate)
      if not numeros:
        numeros = re.findall(patron2, actualDate)
      fechaFinal = "/".join(numeros)
      fechas["muestreo"] = fechaFinal
      muestreoCounter += 1

  return fechas


def mapping_parametros(tabla, date, address):
  def buscar_parametro(kw):
    for i in range(len(tabla)):
      try:
        key = tabla[i][0]

        if key and kw.lower() in key.lower():
          val = tabla[i][0] if len(tabla[i]) < 2 else tabla[i][1]
          if not any(char.isdigit() for char in val):
            if i + 1 < len(tabla):
              val = tabla[i + 1][0]
          return full_parsing(val)
      except:
        pass
    return None

  if address is not None:
    mapeo.empresa = address["empresa"]
    mapeo.local_id = address["local_id"]
    mapeo.local_nombre = address["local_nombre"]
    mapeo.local_region = address["local_region"]
    mapeo.local_comuna = address["local_comuna"]
    mapeo.local_direccion = address["local_direccion"]
    mapeo.local_rpm = address["local_rpm"]
    mapeo.local_convenio = address["local_convenio"]

  mapeo.laboratorio = laboratorio
  mapeo.fecha_emision = date["emision"]
  mapeo.fecha_muestreo = date["muestreo"]
  mapeo.aceites_grasas = buscar_parametro('aceites')
  mapeo.nitrogeno_amoniacal = buscar_parametro('amoniacal')
  mapeo.dbo = buscar_parametro('DBO')
  mapeo.solidos_sedimentables = buscar_parametro('sedimentables')
  mapeo.solidos_suspendidos_totales = buscar_parametro('totales')
  mapeo.poder_espumogeno = buscar_parametro('poder')
  mapeo.fosforo = buscar_parametro('fosforo')
  mapeo.hidrocarburos_totales = buscar_parametro('Hidrocarburos')
  mapeo.manganeso = buscar_parametro('Manganeso')
  mapeo.mercurio = buscar_parametro('mercurio')
  mapeo.niquel = buscar_parametro('níquel')
  mapeo.plomo = buscar_parametro('Plomo')
  mapeo.sulfatos = buscar_parametro('sulfato')
  mapeo.sulfuros = buscar_parametro('sulfuro')
  mapeo.zinc = buscar_parametro('cinc')
  mapeo.cianuro = buscar_parametro('cianuro')
  mapeo.cobre = buscar_parametro('cobre')
  mapeo.cadmio = buscar_parametro('cadmio')
  mapeo.cromo_total = buscar_parametro('cromo')
  mapeo.cromo_hexavalente = buscar_parametro('hexavalente')
  mapeo.boro = buscar_parametro('boro')
  mapeo.arsenico = buscar_parametro('Arsénico')
  mapeo.aluminio = buscar_parametro('aluminio')
  mapeo.ph = buscar_parametro('ph')
  return mapeo.to_dict()


def mappingParametrosText(tabla, dates, address):
  print(address)

  def buscar_parametro(kw):
    for i in range(len(tabla)):
      key = tabla[i][0]
      if key and kw.lower() in key.lower():
        val = tabla[i][0] if len(tabla[i]) < 2 else tabla[i][1]
        if not any(char.isdigit() for char in val):
          if i + 1 < len(tabla):
            val = tabla[i + 1][0]
        return full_parsing(val)
    return None

  if address is not None:
    mapeo.fecha_emision = dates.get("emision")
    mapeo.fecha_muestreo = dates.get("muestreo")
    mapeo.empresa = address["empresa"]
    mapeo.local_id = address["local_id"]
    mapeo.local_nombre = address["local_nombre"]
    mapeo.local_region = address["local_region"]
    mapeo.local_comuna = address["local_comuna"]
    mapeo.local_direccion = address["local_direccion"]
    mapeo.local_rpm = address["local_rpm"]
    mapeo.local_convenio = address["local_convenio"]

  mapeo.laboratorio = laboratorio

  mapeo.fecha_emision = dates["emision"]
  mapeo.fecha_muestreo = dates["muestreo"]
  mapeo.aceites_grasas = buscar_parametro('Aceites y grasas')
  mapeo.nitrogeno_amoniacal = buscar_parametro('Nitrógeno amoniacal')
  mapeo.dbo = buscar_parametro('Demanda bioquímica d')
  mapeo.solidos_sedimentables = buscar_parametro('Sólidos sedimentables')
  mapeo.solidos_suspendidos_totales = buscar_parametro('Sólidos suspendidos')
  mapeo.poder_espumogeno = buscar_parametro('Poder espumógeno')
  mapeo.fosforo = buscar_parametro('Fosforo total')
  mapeo.hidrocarburos_totales = buscar_parametro('Hidrocarburos totales')
  mapeo.manganeso = buscar_parametro('Manganeso')
  mapeo.mercurio = buscar_parametro('mercurio')
  mapeo.niquel = buscar_parametro('níquel')
  mapeo.plomo = buscar_parametro('Plomo')
  mapeo.sulfatos = buscar_parametro('sulfato')
  mapeo.sulfuros = buscar_parametro('sulfuro')
  mapeo.zinc = buscar_parametro('cinc')
  mapeo.cianuro = buscar_parametro('cianuro')
  mapeo.cobre = buscar_parametro('cobre')
  mapeo.cadmio = buscar_parametro('cadmio')
  mapeo.cromo_total = buscar_parametro('cromo')
  mapeo.cromo_hexavalente = buscar_parametro('hexavalente')
  mapeo.boro = buscar_parametro('boro')
  mapeo.arsenico = buscar_parametro('Arsénico')
  mapeo.aluminio = buscar_parametro('aluminio')

  return mapeo.to_dict()


def merieux_reader(file_input: Union[str, Path, bytes, io.BytesIO], lab: str):
  table = get_pdf_table(file_input, lab)
  dates = mapping_sendDate(file_input)
  table = table + [dates] if table else [dates]
  address = get_address(file_input)
  print("address")
  results = mapping_parametros(table, dates, address)

  return results


def merieux_reader_string(file_input: Union[str, Path, bytes, io.BytesIO], ignore: Any = None):
  extract_lines_by_text(file_input, "RENDIC")

  delimiters = {  
    "start": "RESULTADOS QUÍMICOS",
    "row": ",",
    "end": "FECHAS",
  }
  lineas = extract_text_in_lines(file_input)
  tabla = []
  capture = False
  index = 0
  for linea in lineas:
    if linea.find(delimiters["start"]) > -1:
      capture = True

    if capture and linea.find(delimiters["end"]) > -1:
      capture = False

    if capture:
      if not linea[linea.find(delimiters["row"]) - 1].isdigit():
        tabla.append([linea[:linea.find(delimiters["row"])], linea[linea.find(delimiters["row"]) + 1:]])
      else:
        tabla.append([linea])

      index += 1

  dates = mapping_sendDate(file_input)
  address = get_address(file_input)
  result = mappingParametrosText(tabla, dates, address)
  if result["aceites_grasas"] is None:
    raise ValueError("[merieuxReaderString]: DTO Vacío, no se encontraron tablas dentro del archivo")

  return result

# print_pdf_results(merieux_reader("./test pdf/merieux3.pdf","merieux"))
# print_pdf_results(merieux_reader("./test pdf/addr_merieux2.pdf","merieux"))
# print_pdf_results(merieux_reader_string("./test pdf/merieuxEspecial2.pdf","merieuxes"))