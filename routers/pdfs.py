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

@router.post("/qa-pdf/{pdf_id}", response_model=schemas.PDFQuestionAnswer)
def qa_pdf(pdf_id: int, question_request: schemas.QuestionRequest, db: Session = Depends(get_db)):
    pdf = crud.read_pdf(db, pdf_id)
    if not pdf:
        raise HTTPException(status_code=404, detail="PDF no encontrado")
    
    try:
        # Obtener la URL del PDF
        pdf_url = pdf.file
        
        # Verificar si la URL es válida
        if not pdf_url or not pdf_url.startswith("http"):
            raise HTTPException(status_code=400, detail="URL del PDF no válida")
        
        # Imprimir la URL para depuración
        print(f"Intentando descargar PDF desde: {pdf_url}")
        
        # Descargar el PDF desde Cloudinary
        response = requests.get(pdf_url, stream=True)
        
        # Verificar si la descarga fue exitosa
        if response.status_code != 200:
            # Intentar con una URL alternativa (sin el .pdf duplicado al final)
            if pdf_url.endswith(".pdf.pdf"):
                pdf_url = pdf_url[:-4]  # Eliminar el último ".pdf"
                print(f"Intentando URL alternativa: {pdf_url}")
                response = requests.get(pdf_url, stream=True)
                
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=500, 
                        detail=f"Error al descargar el PDF: {response.status_code} {response.reason}"
                    )
            else:
                raise HTTPException(
                    status_code=500, 
                    detail=f"Error al descargar el PDF: {response.status_code} {response.reason}"
                )
        
        # Guardar el PDF temporalmente
        temp_pdf_path = f"/tmp/{pdf_id}.pdf"
        with open(temp_pdf_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        # Extraer texto del PDF
        text = extract_text_from_pdf(temp_pdf_path)
        
        # Eliminar el archivo temporal
        os.remove(temp_pdf_path)
        
        if not text:
            raise HTTPException(status_code=500, detail="No se pudo extraer texto del PDF")
        
        # Crear el prompt para Gemini
        prompt = f"""
        Basándote en el siguiente contenido de un PDF, responde a la pregunta.
        
        Contenido del PDF:
        {text[:10000]}  # Limitamos a 10000 caracteres para evitar exceder el límite de tokens
        
        Pregunta: {question_request.question}
        
        Respuesta:
        """
        
        # Obtener respuesta de Gemini
        response = get_gemini_response(prompt)
        
        return {"answer": response}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al procesar el PDF: {str(e)}")