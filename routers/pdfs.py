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
        try:
            response = requests.get(pdf_url)
            print(f"Respuesta directa: {response.status_code}")
            
            # Si falla, intentar con una URL alternativa
            if response.status_code != 200:
                # Verificar si la URL termina con .pdf.pdf
                if pdf_url.endswith('.pdf.pdf'):
                    alt_url = pdf_url[:-4]  # Eliminar el último .pdf
                    print(f"Intentando URL alternativa: {alt_url}")
                    response = requests.get(alt_url)
                    print(f"Respuesta alternativa: {response.status_code}")
            
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
                        
                        # Intentar descargar directamente desde Cloudinary usando la API
                        try:
                            # Intentar obtener el recurso para verificar que existe
                            resource = cloudinary.api.resource(path, resource_type="raw")
                            print(f"Recurso encontrado: {resource}")
                            
                            # Generar una URL firmada
                            signed_url = cloudinary.utils.cloudinary_url(path, resource_type="raw")[0]
                            print(f"URL firmada: {signed_url}")
                            
                            response = requests.get(signed_url)
                            print(f"Respuesta URL firmada: {response.status_code}")
                        except Exception as cloud_error:
                            print(f"Error al obtener recurso raw: {str(cloud_error)}")
                            
                            # Intentar con resource_type="image"
                            try:
                                resource = cloudinary.api.resource(path, resource_type="image")
                                print(f"Recurso imagen encontrado: {resource}")
                                
                                signed_url = cloudinary.utils.cloudinary_url(path, resource_type="image")[0]
                                print(f"URL firmada (image): {signed_url}")
                                
                                response = requests.get(signed_url)
                                print(f"Respuesta URL firmada (image): {response.status_code}")
                            except Exception as img_error:
                                print(f"Error al obtener recurso image: {str(img_error)}")
                                
                                # Intentar con resource_type="auto"
                                try:
                                    # Intentar descargar directamente
                                    direct_url = f"https://res.cloudinary.com/{Settings().CLOUDINARY_CLOUD_NAME}/raw/upload/{path}"
                                    print(f"Intentando URL directa: {direct_url}")
                                    response = requests.get(direct_url)
                                    print(f"Respuesta URL directa: {response.status_code}")
                                except Exception as auto_error:
                                    print(f"Error al descargar directamente: {str(auto_error)}")
            
            # Si sigue fallando, intentar subir el PDF nuevamente
            if response.status_code != 200:
                # Intentar recuperar el PDF original y subirlo de nuevo
                print("Intentando recuperar y resubir el PDF...")
                
                # Modificar la URL en la base de datos para usar el nuevo PDF
                # Esto es solo un ejemplo, necesitarías implementar la lógica real
                # para resubir el PDF y actualizar la URL en la base de datos
                
                raise HTTPException(
                    status_code=500,
                    detail="No se pudo descargar el PDF. Por favor, sube el archivo nuevamente."
                )
            
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
            
        except requests.exceptions.RequestException as req_error:
            print(f"Error de solicitud HTTP: {str(req_error)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al descargar el PDF: {str(req_error)}"
            )
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error completo: {error_trace}")
        raise HTTPException(status_code=500, detail=f"Error al procesar el PDF: {str(e)}")