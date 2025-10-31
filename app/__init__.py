# app/__init__.py
from datetime import datetime
import os
from flask import Flask
from flask_login import current_user
from flask_wtf.csrf import generate_csrf

# الامتدادات الموحَّدة
from app.extensions import db, mail, login_manager, csrf
from dotenv import load_dotenv
load_dotenv()                        # يقرأ .env تلقائيًا

# ─── كاش + ضغط ─────────────────────────────────────────────
from flask_caching import Cache      # ← كاش صفحات

cache = Cache(config={
    'CACHE_TYPE': 'RedisCache',
    'CACHE_REDIS_URL': os.getenv('REDIS_URL')
})
# ─── اختياري: Flask‑Migrate ───────────────────────────────
try:
    from flask_migrate import Migrate
    MIGRATE_AVAILABLE = True
except ImportError:
    MIGRATE_AVAILABLE = False

migrate_ext = None  # سيُهيَّأ لاحقًا إذا توفّر Flask‑Migrate


# ─── factory function ──────────────────────────────────────
def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.jinja_env.filters['safe_dt'] = lambda v, fmt="%Y-%m-%d": (v.strftime(fmt) if v else "—")
    # 1) الإعدادات الأساسيّة
    app.config.from_object('app.config.Config')
    app.config.setdefault('SECRET_KEY', 'dev-secret-key')

    # 1‑B) تحميل instance/config.py (إن وُجد)
    try:
        app.config.from_pyfile('config.py')
    except FileNotFoundError:
        pass

    # ——— إعداد البريد ———
    app.config.update(
        MAIL_SERVER   = os.getenv('MAIL_SERVER', 'smtp-relay.brevo.com'),
        MAIL_PORT     = int(os.getenv('MAIL_PORT', 587)),
        MAIL_USE_TLS  = os.getenv('MAIL_USE_TLS', 'true').lower() == 'true',
        MAIL_USERNAME = os.getenv('BREVO_SMTP_USERNAME'),
        MAIL_PASSWORD = os.getenv('BREVO_SMTP_PASSWORD'),
        MAIL_DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER', 'no-reply@jumlat.com'),
    )

    # مسارات ثابتة
    app.config.setdefault('BASE_URL',       'https://jumlat.com')
    app.config.setdefault('PDF_FOLDER',     os.path.join('app', 'static', 'pdfs'))
    app.config.setdefault('QR_FOLDER',      os.path.join('app', 'static', 'qr'))
    app.config.setdefault('INVOICE_FOLDER', os.path.join('app', 'static', 'invoices'))

    # إعداد مفاتيح S3
    app.config['AWS_ACCESS_KEY_ID']     = os.getenv('AWS_ACCESS_KEY_ID')
    app.config['AWS_SECRET_ACCESS_KEY'] = os.getenv('AWS_SECRET_ACCESS_KEY')
    app.config['AWS_S3_BUCKET_NAME']    = os.getenv('AWS_S3_BUCKET_NAME')
    app.config['AWS_S3_REGION']         = os.getenv('AWS_S3_REGION', 'us-east-1')

    # ——— إعداد Redis Cache (سريع) ———
    app.config.setdefault('CACHE_TYPE',        'redis')
    app.config.setdefault('CACHE_REDIS_URL',   os.getenv('REDIS_URL', 'redis://localhost:6379/0'))
    app.config.setdefault('CACHE_DEFAULT_TIMEOUT', 300)   # 5 دقائق

    # 2) تهيئة الامتدادات
    db.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    csrf.init_app(app)

    cache.init_app(app)   # ← تشغيل الكاش

    # 2‑B) Flask‑Migrate
    if MIGRATE_AVAILABLE:
        global migrate_ext
        migrate_ext = Migrate()
        migrate_ext.init_app(app, db)

    # 3) تحميل المستخدم
    from app.models import User
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # 4) csrf_token في القوالب
    @app.context_processor
    def inject_csrf():
        return dict(csrf_token=generate_csrf)

    # 5) تسجيل Blueprints
    from app.routes.factory   import factory_bp
    from app.routes.promoter  import promoter_bp
    from app.routes.auth      import auth_bp
    from app.routes.public    import public_bp
    from app.routes.admin     import admin_bp

    app.register_blueprint(admin_bp   , url_prefix='/admin')
    app.register_blueprint(factory_bp , url_prefix='/factory')
    app.register_blueprint(promoter_bp, url_prefix='/promoter')
    app.register_blueprint(auth_bp    , url_prefix='/auth')
    app.register_blueprint(public_bp)

    # 6) إنشاء الجداول والمجلّدات عند التشغيل الأول
    with app.app_context():
        db.create_all()
        os.makedirs(app.config['PDF_FOLDER'],     exist_ok=True)
        os.makedirs(app.config['QR_FOLDER'],      exist_ok=True)
        os.makedirs(app.config['INVOICE_FOLDER'], exist_ok=True)

    # 7) انتظار دفعات العمولة
    from app.models import VoucherBatch
    @app.context_processor
    def inject_waiting_batches():
        count = 0
        try:
            if current_user.is_authenticated and hasattr(current_user, "factory_id"):
                count = (VoucherBatch.query
                         .filter(VoucherBatch.factory_id == current_user.factory_id)
                         .filter(VoucherBatch.status.in_(["awaiting_payment", "payment_rejected"]))
                         .count())
        except Exception:
            pass
        return dict(waiting_batches=count)

    return app
