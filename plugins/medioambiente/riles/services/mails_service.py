import csv
import io
from typing import Dict, List, Optional, Union
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .models import LocalMailModel
from .schemas import LocalMailBase, LocalMailSchema


class LocalMailService:

  @staticmethod
  def get_all_mails(
      db: Session, skip: int = 0, limit: int = 100
  ) -> List[LocalMailModel]:
    """Obtiene el listado paginado de todos los correos registrados."""
    try:
      return db.query(LocalMailModel).offset(skip).limit(limit).all()
    except SQLAlchemyError as e:
      raise HTTPException(
          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
          detail=f"Error al obtener correos: {str(e)}",
      )

  @staticmethod
  def get_mail_by_id(
      db: Session, id_local_mail: int
  ) -> Optional[LocalMailModel]:
    """Obtiene un registro de correo específico por su ID primario."""
    mail_record = (
        db.query(LocalMailModel)
        .filter(LocalMailModel.id_local_mail == id_local_mail)
        .first()
    )
    if not mail_record:
      raise HTTPException(
          status_code=status.HTTP_404_NOT_FOUND,
          detail=f"No se encontró el registro de correo con ID {id_local_mail}",
      )
    return mail_record

  @staticmethod
  def get_mails_by_local(
      db: Session, id_local: str, mail_type: Optional[str] = None
  ) -> List[LocalMailModel]:
    """Obtiene los correos de un local específico, con opción de filtrar por tipo ('local' o 'sanitaria')."""
    try:
      query = db.query(LocalMailModel).filter(
          LocalMailModel.id_local == str(id_local)          
      )
      if mail_type:
        query = query.filter(LocalMailModel.mail_type == mail_type)
      return query.all()
    except SQLAlchemyError as e:
      raise HTTPException(
          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
          detail=f"Error al consultar correos del local {id_local}: {str(e)}",
      )


  @staticmethod
  def create_mail(
      db: Session, mail_data: LocalMailBase
  ) -> LocalMailModel:
    """Crea un nuevo registro de correo para un local."""
    try:
      new_mail = LocalMailModel(
          id_local=mail_data.id_local,
          mail=mail_data.mail.strip().lower(),
          mail_type=mail_data.mail_type.strip().lower(),
      )
      db.add(new_mail)
      db.commit()
      db.refresh(new_mail)
      return new_mail
    except SQLAlchemyError as e:
      db.rollback()
      raise HTTPException(
          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
          detail=f"Error al registrar el correo: {str(e)}",
      )

  @staticmethod
  def update_mail(
      db: Session, id_local_mail: int, mail_data: LocalMailBase
  ) -> LocalMailModel:
    """Actualiza un registro de correo existente."""
    mail_record = LocalMailService.get_mail_by_id(db, id_local_mail)

    try:
      mail_record.id_local = mail_data.id_local
      mail_record.mail = mail_data.mail.strip().lower()
      mail_record.mail_type = mail_data.mail_type.strip().lower()

      db.commit()
      db.refresh(mail_record)
      return mail_record
    except SQLAlchemyError as e:
      db.rollback()
      raise HTTPException(
          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
          detail=f"Error al actualizar el correo: {str(e)}",
      )

  @staticmethod
  def delete_mail(db: Session, id_local_mail: int) -> dict:
    """Elimina un registro de correo por su ID."""
    mail_record = LocalMailService.get_mail_by_id(db, id_local_mail)

    try:
      db.delete(mail_record)
      db.commit()
      return {
          "status": "success",
          "message": (
              f"Registro de correo con ID {id_local_mail} eliminado"
              " correctamente."
          ),
      }
    except SQLAlchemyError as e:
      db.rollback()
      raise HTTPException(
          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
          detail=f"Error al eliminar el correo: {str(e)}",
      )

  @staticmethod
  def _parse_csv_file(file: UploadFile) -> List[Dict[str, str]]:
    """Procesa un archivo CSV delimitado por comas (,) y retorna una lista de diccionarios válidos."""
    if not file.filename.lower().endswith('.csv'):
      raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="El archivo debe tener extensión .csv",
    )

    try:
      content = file.file.read().decode('utf-8-sig')
      csv_reader = csv.DictReader(io.StringIO(content), delimiter=';')

      required_columns = {'id_local', 'mail', 'mail_type'}
      if not csv_reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo CSV está vacío o corrupto.",
        )

      fieldnames = {field.strip() for field in csv_reader.fieldnames if field}
      if not required_columns.issubset(fieldnames):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "El CSV separado por comas debe contener las cabeceras:"
                " id_local, mail, mail_type"
            ),
        )

      records = []
      for row in csv_reader:
        clean_row = {
            key.strip(): value.strip()
            for key, value in row.items()
            if key and value
        }

        if (
            clean_row.get('id_local')
            and clean_row.get('mail')
            and clean_row.get('mail_type')
        ):
          records.append({
              'id_local': str(clean_row['id_local']),
              'mail': str(clean_row['mail']).lower(),
              'mail_type': str(clean_row['mail_type']).lower(),
          })

      return records

    except HTTPException:
      raise
    except Exception as e:
      raise HTTPException(
          status_code=status.HTTP_400_BAD_REQUEST,
          detail=f"Error al procesar la lectura del archivo CSV: {str(e)}",
      )

  @staticmethod
  def bulk_insert_from_csv(
      db: Session, file: UploadFile
  ) -> Dict[str, Union[str, int]]:
    """Carga masiva: Agrega los registros del CSV a la tabla sin borrar la información existente."""
    records = LocalMailService._parse_csv_file(file)

    if not records:
      raise HTTPException(
          status_code=status.HTTP_400_BAD_REQUEST,
          detail="El archivo CSV no contiene registros válidos para insertar.",
      )

    try:
      new_objects = [LocalMailModel(**data) for data in records]

      db.bulk_save_objects(new_objects)
      db.commit()

      return {
          "status": "success",
          "message": "Carga masiva completada exitosamente.",
          "inserted_count": len(new_objects),
      }

    except SQLAlchemyError as e:
      db.rollback()
      raise HTTPException(
          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
          detail=f"Error de base de datos durante la carga masiva: {str(e)}",
      )

  @staticmethod
  def delete_all(
      db: Session
  ):
    """Se eliminan TODOS los registros actuales"""
    try:
      db.query(LocalMailModel).delete()
      db.commit()
      return {
          "status": "success",
          "message": (
              "Tabla 'local_mail' reiniciada"
              " CSV."
          )
      }

    except SQLAlchemyError as e:
      db.rollback()
      raise HTTPException(
          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
          detail=(
              "Error de base de datos durante la sobrescritura total:"
              f" {str(e)}"
          ),
      )

  @staticmethod
  def update_all_from_csv(
      db: Session, file: UploadFile
  ) -> Dict[str, Union[str, int]]:
    """Actualización total: Elimina TODOS los registros actuales e inserta los datos del CSV."""
    records = LocalMailService._parse_csv_file(file)

    if not records:
      raise HTTPException(
          status_code=status.HTTP_400_BAD_REQUEST,
          detail="El archivo CSV no contiene registros válidos para actualizar.",
      )

    try:
      db.query(LocalMailModel).delete()

      new_objects = [LocalMailModel(**data) for data in records]
      db.bulk_save_objects(new_objects)

      db.commit()

      return {
          "status": "success",
          "message": (
              "Tabla 'local_mail' reiniciada e importada con éxito desde el"
              " CSV."
          ),
          "inserted_count": len(new_objects),
      }

    except SQLAlchemyError as e:
      db.rollback()
      raise HTTPException(
          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
          detail=(
              "Error de base de datos durante la sobrescritura total:"
              f" {str(e)}"
          ),
      )
    
  @staticmethod
  def export_to_csv(db: Session) -> io.StringIO:
    """Exporta todos los registros de la tabla 'local_mail' a un buffer CSV delimitado por punto y coma (;)."""
    try:
      records = db.query(LocalMailModel).all()

      output = io.StringIO()
      fieldnames = ["id_local", "mail", "mail_type"]
      writer = csv.DictWriter(
          output, fieldnames=fieldnames, delimiter=";", lineterminator="\n"
      )

      writer.writeheader()
      for record in records:
        writer.writerow({
            "id_local": record.id_local,
            "mail": record.mail,
            "mail_type": record.mail_type,
        })

      output.seek(0)
      return output

    except SQLAlchemyError as e:
      raise HTTPException(
          status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
          detail=f"Error al exportar correos a CSV: {str(e)}",
      )