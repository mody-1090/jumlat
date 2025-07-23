# app/__init__.py
import os
from datetime import datetime
from flask import Flask
from flask_login import current_user
from flask_wtf.csrf import generate_csrf
from flask_compress import Compress
from flask_caching import Cache
from dotenv import load_dotenv

# امتدادات
from app.extensions import db, mail, login_manager, csrf
try:
    from flask_migrate import Migrate
    MIGRATE_AVAILABLE = True
except ImportError:
    MIGRATE_AVAILABLE = False


# تهيئة المتغيّرات من .env
load_dotenv()


# --- إعداد التخزين المؤقت (Redis) وضغط GZIP ---
cache = Cache()
compress = Compress()


def create_app():
    app = Flask(__name__, instance_relative_config=True)

    # 1) الإعدادات الأساسية
    app.config.from_object("app.config.Config")
    app.config.setdefault("SECRET_KEY", os.getenv("SECRET_KEY", "dev-secret-key"))

    # 1‑B) تحميل instance/config.py
    try:
        app.config.from_pyfile("config.py")
    except FileNotFoundError:
        pass

    # 2) إعداد البريد
    app.config.update(
        MAIL_SERVER=os.getenv("MAIL_SERVER", "smtp-relay.brevo.com"),
        MAIL_PORT=int(os.getenv("MAIL_PORT", 587)),
        MAIL_USE_TLS=os.getenv("MAIL_USE_TLS", "true").lower() == "true",
        MAIL_USERNAME=os.getenv("BREVO_SMTP_USERNAME"),
        MAIL_PASSWORD=os.getenv("BREVO_SMTP_PASSWORD"),
        MAIL_DEFAULT_SENDER=os.getenv("MAIL_DEFAULT_SENDER", "no-reply@jumlat.com"),
    )

    # 3) مسارات ثابتة و S3
    app.config.setdefault("BASE_URL", "http://127.0.0.1:5000")
    app.config.setdefault("PDF_FOLDER", os.path.join("app", "static", "pdfs"))
    app.config.setdefault("QR_FOLDER", os.path.join("app", "static", "qr"))
    app.config.setdefault("INVOICE_FOLDER", os.path.join("app", "static", "invoices"))

    app.config["AWS_ACCESS_KEY_ID"] = os.getenv("AWS_ACCESS_KEY_ID")
    app.config["AWS_SECRET_ACCESS_KEY"] = os.getenv("AWS_SECRET_ACCESS_KEY")
    app.config["AWS_S3_BUCKET_NAME"] = os.getenv("AWS_S3_BUCKET_NAME")
    app.config["AWS_S3_REGION"] = os.getenv("AWS_S3_REGION", "us-east-1")

    # 4) إعداد الكاش
    app.config.setdefault("CACHE_TYPE", "RedisCache")
    app.config.setdefault("CACHE_REDIS_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    app.config.setdefault("CACHE_DEFAULT_TIMEOUT", 300)

    # 5) تهيئة الامتدادات
    db.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    csrf.init_app(app)

    cache.init_app(app)
    compress.init_app(app)

    # 5‑B) Flask‑Migrate (إن وُجد)
    if MIGRATE_AVAILABLE:
        Migrate(app, db)

    # 6) تسجيل الـ Blueprints
    from app.routes.factory import factory_bp
    from app.routes.promoter import promoter_bp
    from app.routes.auth import auth_bp
    from app.routes.public import public_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(factory_bp, url_prefix="/factory")
    app.register_blueprint(promoter_bp, url_prefix="/promoter")
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(public_bp)

    # 7) توفر now() و csrf_token و waiting_batches في القوالب
    app.jinja_env.globals["now"] = datetime.utcnow

    @app.context_processor
    def inject_csrf():
        return dict(csrf_token=generate_csrf)

    from app.models import VoucherBatch

    @app.context_processor
    def inject_waiting_batches():
        count = 0
        if current_user.is_authenticated and hasattr(current_user, "factory_id"):
            count = (
                VoucherBatch.query
                .filter(VoucherBatch.factory_id == current_user.factory_id)
                .filter(VoucherBatch.status.in_(["awaiting_payment", "payment_rejected"]))
                .count()
            )
        return dict(waiting_batches=count)

    # ⚠❌ لا تستدعي db.create_all() هنا في الإنتاج
    return app
