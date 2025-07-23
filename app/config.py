import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key')

    # الآن إجباري وجود DATABASE_URL (لـ PostgreSQL)
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL').replace("postgres://", "postgresql://")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    QR_FOLDER = os.path.join(os.getcwd(), 'app', 'static', 'qr')
    PDF_FOLDER = os.path.join('app', 'static', 'pdfs')
