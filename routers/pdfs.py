from typing import List
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
import schemas
import crud
from database import SessionLocal
from uuid import uuid4
import google.generativeai as genai
from config import Settings
from PyPDF2 import PdfReader
import requests
from io import BytesIO
import os
import cloudinary
import cloudinary.uploader
import cloudinary.api

# Configurar Gemini
genai.configure(api_key=Settings().GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

router = APIRouter(prefix="/pdfs")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("", response_model=schemas.PDFResponse, status_code=status.HTTP_201_CREATED)
def create_pdf(pdf: schemas.PDFRequest, db: Session = Depends(get_db)):
    return crud.create_pdf(db, pdf)

@router.post("/upload", response_model=schemas.PDFResponse, status_code=status.HTTP_201_CREATED)
def upload_pdf(file: UploadFile = File(...), db: Session = Depends(get_db)):
    file_name = f"{uuid4()}-{file.filename}"
    return crud.upload_pdf(db, file, file_name)

@router.get("", response_model=List[schemas.PDFResponse])
def get_pdfs(selected: bool = None, db: Session = Depends(get_db)):
    return crud.read_pdfs(db, selected)

@router.get("/{id}", response_model=schemas.PDFResponse)
def get_pdf_by_id(id: int, db: Session = Depends(get_db)):
    pdf = crud.read_pdf(db, id)
    if pdf is None:
        raise HTTPException(status_code=404, detail="PDF not found")
    return pdf

@router.put("/{id}", response_model=schemas.PDFResponse)
def update_pdf(id: int, pdf: schemas.PDFRequest, db: Session = Depends(get_db)):
    updated_pdf = crud.update_pdf(db, id, pdf)
    if updated_pdf is None:
        raise HTTPException(status_code=404, detail="PDF not found")
    return updated_pdf

@router.delete("/{id}", status_code=status.HTTP_200_OK)
def delete_pdf(id: int, db: Session = Depends(get_db)):
    if not crud.delete_pdf(db, id):
        raise HTTPException(status_code=404, detail="PDF not found")
    return {"message": "PDF successfully deleted"}

@router.post('/summarize-text')
async def summarize_text(text: str):
    prompt = f"Proporciona un resumen para el siguiente texto: {text}"
    response = model.generate_content(prompt)
    return {'summary': response.text}

@router.post("/qa-pdf/{id}")
def qa_pdf_by_id(id: int, question_request: schemas.QuestionRequest, db: Session = Depends(get_db)):
    pdf = crud.read_pdf(db, id)
    if pdf is None:
        raise HTTPException(status_code=404, detail="PDF not found")
    
    # Descargar el PDF desde Cloudinary
    try:
        # Configurar Cloudinary
        cloudinary_instance = Settings.setup_cloudinary()
        
        # Obtener la URL del PDF
        pdf_url = pdf.file
        print(f"URL del PDF: {pdf_url}")
        
        # Intentar descargar el PDF directamente
        response = requests.get(pdf_url)
        
        # Si falla, intentar con una URL alternativa
        if response.status_code != 200:
            # Verificar si la URL termina con .pdf.pdf
            if pdf_url.endswith('.pdf.pdf'):
                alt_url = pdf_url[:-4]  # Eliminar el último .pdf
                print(f"Intentando URL alternativa: {alt_url}")
                response = requests.get(alt_url)
        
        # Si sigue fallando, intentar con la API de Cloudinary
        if response.status_code != 200:
            # Extraer el public_id de la URL
            parts = pdf_url.split('/upload/')
            if len(parts) > 1:
                version_and_path = parts[1]
                # Extraer la versión y el path
                version_parts = version_and_path.split('/', 1)
                if len(version_parts) > 1:
                    path = version_parts[1]
                    # Eliminar la extensión .pdf o .pdf.pdf
                    if path.endswith('.pdf.pdf'):
                        path = path[:-8]
                    elif path.endswith('.pdf'):
                        path = path[:-4]
                    
                    print(f"Public ID: {path}")
                    
                    # Generar una URL firmada
                    signed_url = cloudinary.utils.cloudinary_url(path, resource_type="raw")[0]
                    print(f"URL firmada: {signed_url}")
                    
                    response = requests.get(signed_url)
        
        # Si todavía falla, intentar con resource_type="image"
        if response.status_code != 200:
            signed_url = cloudinary.utils.cloudinary_url(path, resource_type="image")[0]
            print(f"URL firmada (image): {signed_url}")
            response = requests.get(signed_url)
        
        # Si sigue fallando, lanzar una excepción
        if response.status_code != 200:
            raise HTTPException(
                status_code=500,
                detail=f"No se pudo descargar el PDF: {response.status_code} {response.reason}"
            )
        
        # Guardar el PDF temporalmente
        temp_pdf_path = f"/tmp/{id}.pdf"
        with open(temp_pdf_path, 'wb') as f:
            f.write(response.content)
        
        # Extraer texto del PDF
        try:
            pdf_reader = PdfReader(temp_pdf_path)
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text()
        except Exception as pdf_error:
            raise HTTPException(
                status_code=500,
                detail=f"Error al extraer texto del PDF: {str(pdf_error)}"
            )
        finally:
            # Eliminar el archivo temporal
            if os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)
        
        if not text:
            raise HTTPException(status_code=500, detail="No se pudo extraer texto del PDF")
        
        # Si el texto es muy largo, podemos truncarlo para Gemini
        if len(text) > 100000:  # Ajustar según los límites de Gemini
            text = text[:100000]
        
        # Crear prompt para Gemini
        prompt = f"""
        Basado en el siguiente contenido del PDF "{pdf.name}":
        
        {text}
        
        Responde a la siguiente pregunta: {question_request.question}
        """
        
        # Obtener respuesta de Gemini
        response = model.generate_content(prompt)
        
        return {"answer": response.text}
    
    except Exception as e:
        import traceback
        print(f"Error completo: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error al procesar el PDF: {str(e)}")