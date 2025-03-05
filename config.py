import os
import cloudinary
import cloudinary.uploader
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_HOST: str
    DATABASE_NAME: str
    DATABASE_USER: str
    DATABASE_PASSWORD: str
    DATABASE_PORT: int
    DATABASE_URL: str = "postgresql://neondb_owner:npg_d5jVEZOqr4nw@ep-plain-mode-a8tq1tu6-pooler.eastus2.azure.neon.tech/neondb?sslmode=require"
    app_name: str = "Full Stack PDF CRUD App"
    CLOUDINARY_URL: str = "cloudinary://175786421248115:LvO2ZGWpKMNzuVXrmcMgyC_HlPk@dyje6aftb"
    GEMINI_API_KEY: str = "AIzaSyDJrVuMpsP2aicUn0Oc_g5gDaezR5Z4MIo"

    @staticmethod
    def setup_cloudinary():
        cloudinary.config(
            cloud_name="dyje6aftb",
            api_key="175786421248115",
            api_secret="LvO2ZGWpKMNzuVXrmcMgyC_HlPk"
        )
        return cloudinary

    class Config:
        env_file = ".env"
        extra = "ignore"
