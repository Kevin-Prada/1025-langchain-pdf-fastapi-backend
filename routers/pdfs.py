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
        response = requests.get(pdf.file)
        response.raise_for_status()
        
        # Extraer texto del PDF
        pdf_file = BytesIO(response.content)
        pdf_reader = PdfReader(pdf_file)
        
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
        
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
        raise HTTPException(status_code=500, detail=f"Error al procesar el PDF: {str(e)}")