import sys
from pathlib import Path
import httpx
from jinja2 import Template
import win32com.client as win32
import premailer
import base64
import os
import tempfile
from typing import List, Dict, Any, Optional


CURRENT_DIR = Path(__file__).resolve().parent

from .envio_correos_config import FILE_TEMPLATE_DIR

BASE_URL = "/medioambiente/riles/api/v1"

def load_template():
  with open(FILE_TEMPLATE_DIR, 'r', encoding='utf-8') as template:
    return template.read()

def set_parameters(params):
  loaded_template_html = load_template()
  mail_template = Template(loaded_template_html)
  if isinstance(params, dict):
    filled_html = mail_template.render(**params)
  else:
    filled_html = mail_template.render(params)

  final_html = premailer.transform(filled_html)
  return final_html

def generate_mail(
      recipients: List[str], subject: str, params: dict
  ) -> str:
    """Envía el correo mediante Outlook a una lista de destinatarios."""
    print()
    if not recipients:
      return "No hay destinatarios configurados para este envío."
    
    temp_file_path = None
    try:
      outlook = win32.Dispatch("outlook.application")
      mail = outlook.CreateItem(0)

      # Agregar múltiples destinatarios separados por punto y coma
      mail.To = "; ".join(recipients)
      mail.Subject = subject
      mail.HTMLBody = set_parameters(params)

      # Adjuntar PDF desde Base64
      b64_string = params.get("b64")
      if b64_string:
        if "," in b64_string:
          b64_string = b64_string.split(",", 1)[1]

        pdf_bytes = base64.b64decode(b64_string)

        temp_dir = tempfile.gettempdir()
        nombre_archivo = f"Analisis_{params.get('local_id', 'RILES')}.pdf"
        temp_file_path = os.path.join(temp_dir, nombre_archivo)

        with open(temp_file_path, "wb") as f:
          f.write(pdf_bytes)

        mail.Attachments.Add(temp_file_path)

      mail.Send()
      return "Enviado con éxito"

    except Exception as e:
      return f"Error al enviar correo: {str(e)}"

    finally:
      if temp_file_path and os.path.exists(temp_file_path):
        try:
          os.remove(temp_file_path)
        except Exception:
          pass


def run(data: dict, recipients: List[str],type:str='local') :

  if not data:
    print("No se recibieron datos para generar el correo.")

  if type == 'local':
    # subject = f"RPM N° {data.get('local_rpm','').split('.')[0]} UNIMARC {data.get('local_nombre', '')} DE MES {data.get('fecha_muestreo', '').strftime('%m/%Y') if data.get('fecha_muestreo') else ''}"
    subject = f"Analisis de Riles - Local: {data.get('local_nombre', '')} - CECO: {data.get('local_id', '')}"
  else:
    subject = f"RPM N° {data.get('local_rpm','').split('.')[0]} UNIMARC {data.get('local_nombre', '')} DE MES {data.get('fecha_muestreo', '').strftime('%m/%Y') if data.get('fecha_muestreo') else ''}"

  resultado = generate_mail(recipients, subject, data)



def testing():
  """Procesa toda la cola de correos obteniendo las IDs y ejecutando run()"""
  with httpx.Client(base_url=BASE_URL) as client:
    request_get_maling_queue = client.get("/get-mailing-queue")
    
    if request_get_maling_queue.status_code != 200:
      print("Error al obtener la cola de envíos")
      return

    response_get_maling_queue = request_get_maling_queue.json()
    
    for item in response_get_maling_queue:
      analysis_id = int(item["id"])
      run(analysis_id, to="dquioza@smu.cl")

if __name__ == "__main__":
  testing()