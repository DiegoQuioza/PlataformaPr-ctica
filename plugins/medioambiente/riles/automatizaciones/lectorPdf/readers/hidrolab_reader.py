import io
from pathlib import Path
import re
from typing import Union, Dict, Any, Optional

from utils.dtos import AnalisisAguaDTO
from utils.data_cleaning import full_parsing, remove_symbol
from utils.models import search_store_id
from utils.utils import get_data_list, print_pdf_results, get_pdf_table, open_pdf


def _parse_values(value):
  caracteresEspeciales = ["<", ">"]
  contieneCaracteresEspeciales = any(c in value for c in caracteresEspeciales)
  if contieneCaracteresEspeciales:
    result = value.split(" ")[1]
    return result
  else:
    result = value.split(" ")[0]
    return result


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

    if muestreoCounter == 0 and actualDate.lower().find("muestreo") > 0:
      numeros = re.findall(patron, actualDate)
      if not numeros:
        numeros = re.findall(patron2, actualDate)
      fechaFinal = "/".join(numeros)
      fechas["muestreo"] = fechaFinal
      muestreoCounter += 1

  return fechas


def _read_pdf_file(
  file_input: Union[str, Path, bytes, io.BytesIO], address, date
):
  with open_pdf(file_input) as pdf:
    mapeo = AnalisisAguaDTO()
    registros = []
    for page in pdf.pages:
      tablas = page.extract_tables()
      if page.page_number == 2:
        for fila in tablas[2]:
          registros.append(_parse_values(fila[1]))

    mapeo.aceites_grasas = registros[1]
    mapeo.dbo = registros[2]
    mapeo.fosforo = registros[3]
    mapeo.nitrogeno_amoniacal = registros[4]
    mapeo.poder_espumogeno = registros[6]
    mapeo.solidos_sedimentables = registros[7]
    mapeo.solidos_suspendidos_totales = registros[8]
    mapeo.laboratorio = "HIDROLAB"
    mapeo.fecha_emision = date["emision"] if date else ""
    if date and date.get("muestreo"):
      mapeo.fecha_muestreo = (
        date["muestreo"].split("/")[1]
        if len(date["muestreo"].split("/")) > 1
        else date["muestreo"]
      )

    valores_encontrados = {}
    for atributo, valor in valores_encontrados.items():
      setattr(mapeo, atributo, full_parsing(valor))

    if address:
      for atributo, valor in address.items():
        if hasattr(mapeo, atributo):
          setattr(mapeo, atributo, valor)

    print(date)
    return mapeo.to_dict()


def hidrolab_reader(file_input: Union[str, Path, bytes, io.BytesIO]):
  direcciones = get_address(file_input)
  fechas = mapping_sendDate(file_input)
  results = _read_pdf_file(file_input, direcciones, fechas)
  return results