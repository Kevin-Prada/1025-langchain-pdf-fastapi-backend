import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = "postgresql://neondb_owner:npg_d5jVEZOqr4nw@ep-plain-mode-a8tq1tu6-pooler.eastus2.azure.neon.tech/neondb?sslmode=require"

engine = create_engine(
    DATABASE_URL
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()