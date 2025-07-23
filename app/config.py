import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key')

    # URI لـ PostgreSQL (Heroku أو RDS)
    SQLALCHEMY_DATABASE_URI = (
        os.getenv('DATABASE_URL')
        .replace("postgres://", "postgresql://", 1)
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ── Pooling ───────────────────────────────────────────────────
    # ضبط حجم الـ pool وعدد الاتصالات المؤقتة
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 5,         # عدد الاتصالات الدائمة
        "max_overflow": 2,      # عدد الاتصالات المؤقتة فوق pool_size
        "pool_timeout": 30,     # ثانية انتظار قبل رفع TimeoutError
        "pool_recycle": 1800,   # إعادة فتح الاتصال بعد مرور 1800 ثانية
    }

    # مسارات المجلدات الثابتة
    QR_FOLDER     = os.path.join(os.getcwd(), 'app', 'static', 'qr')
    PDF_FOLDER    = os.path.join(os.getcwd(), 'app', 'static', 'pdfs')
    INVOICE_FOLDER = os.path.join(os.getcwd(), 'app', 'static', 'invoices')

    # S3 (إذا تستخدمه)
    AWS_ACCESS_KEY_ID     = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_S3_BUCKET_NAME    = os.getenv('AWS_S3_BUCKET_NAME')
    AWS_S3_REGION         = os.getenv('AWS_S3_REGION', 'us-east-1')
