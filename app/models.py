# app/models.py

import random
import secrets
import string
from datetime import datetime
from flask import current_app
from itsdangerous import URLSafeTimedSerializer
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db

# ─────────────────────────────────────────────────────────────────────────────
# 1) جدول المستخدم الأساسي
# ─────────────────────────────────────────────────────────────────────────────
class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id            = db.Column(db.Integer,   primary_key=True)
    username      = db.Column(db.String(64), unique=True, nullable=False)
    email         = db.Column(db.String(120), unique=True, nullable=False)   # جديد
    phone         = db.Column(db.String(20))                                 # اختياري
    password_hash = db.Column(db.Text, nullable=False)
    role          = db.Column(db.String(20), nullable=False)  # factory | promoter | admin
    is_verified   = db.Column(db.Boolean, default=False)                     # للتفعيل
    factory_id    = db.Column(db.Integer, db.ForeignKey('factories.id'))

    # علاقة واحد-إلى-واحد مع المروج (إن وجد)
    promoter = db.relationship('Promoter', back_populates='user', uselist=False)

    @property
    def password(self):
        raise AttributeError("كلمة المرور لا يمكن قراءتها مباشرةً.")

    @password.setter
    def password(self, plain):
        self.password_hash = generate_password_hash(plain)

    def check_password(self, plain):
        return check_password_hash(self.password_hash, plain)

    @property
    def is_promoter(self) -> bool:
        return self.role == 'promoter'

    def generate_token(self, salt, expires_sec=3600):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        return s.dumps(self.email, salt=salt)

    @staticmethod
    def verify_token(token, salt, expires_sec=3600):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        try:
            email = s.loads(token, salt=salt, max_age=expires_sec)
        except Exception:
            return None
        return email

# ─────────────────────────────────────────────────────────────────────────────
# 2) جدول المصانع
# ─────────────────────────────────────────────────────────────────────────────
class Factory(db.Model):
    __tablename__ = 'factories'

    id              = db.Column(db.Integer, primary_key=True)
    name            = db.Column(db.String(128), nullable=False)
    contact_person  = db.Column(db.String(128))
    contact_phone   = db.Column(db.String(32))
    commission_rate = db.Column(db.Float, default=1.0)  # ريال لكل كرتون
       # ✦ جديد
    cr_number   = db.Column(db.String(30))   # السجل التجاري
    vat_number  = db.Column(db.String(30))   # الرقم الضريبي
    vouchers = db.relationship('Voucher', back_populates='factory')


# ─────────────────────────────────────────────────────────────────────────────
# 3) جدول المروِّجين
# ─────────────────────────────────────────────────────────────────────────────
class Promoter(db.Model):
    __tablename__ = 'promoters'

    id      = db.Column(db.Integer, primary_key=True)
    name    = db.Column(db.String(128), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    # روابط ORM
    user     = db.relationship('User',      back_populates='promoter')
    vouchers = db.relationship('Voucher',   back_populates='promoter', lazy='dynamic')
    orders   = db.relationship('Order',     back_populates='promoter', lazy='dynamic')
    earnings = db.relationship('Earning',   back_populates='promoter')
    account_holder_name = db.Column(db.String(100))  # اسم صاحب الحساب البنكي
    bank_name = db.Column(db.String(100))
    iban = db.Column(db.String(24))

# ─────────────────────────────────────────────────────────────────────────────
# 4) جدول السندات
# ─────────────────────────────────────────────────────────────────────────────
class Voucher(db.Model):
    __tablename__ = 'vouchers'

    id                 = db.Column(db.Integer, primary_key=True)
    code               = db.Column(db.String(32), unique=True, nullable=False)
    product            = db.Column(db.String(128), nullable=False)
    quantity           = db.Column(db.Integer, nullable=False)
    city = db.Column(db.String(50), nullable=False, default='الرياض')
    # الوضع الجديد يشمل كافة المراحل
    status             = db.Column(db.String(30), default='pending_admin_review')  # الحالات المتنوعة
    
    created_at         = db.Column(db.DateTime, default=datetime.utcnow)
    qr_path            = db.Column(db.String(256))
    invoice_path       = db.Column(db.String(256))

    factory_id         = db.Column(db.Integer, db.ForeignKey('factories.id'))
    promoter_id        = db.Column(db.Integer, db.ForeignKey('promoters.id'))

    factory_commission = db.Column(db.Float, default=0.0)
    price_per_unit     = db.Column(db.Float, default=0.0)
    vat_rate           = db.Column(db.Float, default=0.15)
    total_price        = db.Column(db.Float, default=0.0)
    batch_id = db.Column(db.Integer, db.ForeignKey("voucher_batch.id"), nullable=True)

    # جديدة 👇
    admin_note         = db.Column(db.String(256))      # سبب رفض أو ملاحظات الإدارة
    payment_proof_url  = db.Column(db.String(256))      # رابط صورة التحويل
    payment_note       = db.Column(db.String(256))      # تعليق بعد مراجعة الإثبات
    payment_account_name = db.Column(db.String(255))
    # علاقات ORM
    factory  = db.relationship('Factory',  back_populates='vouchers')
    promoter = db.relationship('Promoter', back_populates='vouchers')
    order    = db.relationship('Order', back_populates='voucher', uselist=False)
    commission_invoice = db.relationship(
        "CommissionInvoice", backref="voucher", uselist=False
    )


    @staticmethod
    def generate_unique_code(length: int = 8) -> str:
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))
            if not Voucher.query.filter_by(code=code).first():
                return code

    @property
    def promoter_name(self) -> str:
        return self.promoter.user.username if self.promoter else None


# ─────────────────────────────────────────────────────────────────────────────
# 5) جدول الأرباح
# ─────────────────────────────────────────────────────────────────────────────
class Earning(db.Model):
    __tablename__ = 'earnings'

    id              = db.Column(db.Integer, primary_key=True)
    voucher_id      = db.Column(db.Integer, db.ForeignKey('vouchers.id'))
    promoter_id     = db.Column(db.Integer, db.ForeignKey('promoters.id'))
    factory_amount  = db.Column(db.Float, nullable=False)
    promoter_amount = db.Column(db.Float, nullable=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)

    # روابط ORM
    promoter = db.relationship('Promoter', back_populates='earnings')
    voucher  = db.relationship('Voucher', backref=db.backref('earnings', lazy='dynamic'))
    @property
    def related_order(self):
        return self.voucher.order


# ─────────────────────────────────────────────────────────────────────────────
# 6) جدول طلبات السحب
# ─────────────────────────────────────────────────────────────────────────────
class Withdrawal(db.Model):
    __tablename__ = 'withdrawals'

    id           = db.Column(db.Integer, primary_key=True)
    promoter_id  = db.Column(db.Integer, db.ForeignKey('promoters.id'))
    amount       = db.Column(db.Float,  nullable=False)
    status       = db.Column(db.String(20), default='pending')  # pending|approved|rejected
    factory_note = db.Column(db.String(256))                    # سبب الرفض
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)

    dispute      = db.relationship('Dispute', back_populates='withdrawal', uselist=False)
    promoter     = db.relationship('Promoter', backref=db.backref('withdrawals', lazy='dynamic'))


# ─────────────────────────────────────────────────────────────────────────────
# 7) جدول الطلبات النهائية
# ─────────────────────────────────────────────────────────────────────────────
class Order(db.Model):
    __tablename__ = 'orders'

    id             = db.Column(db.Integer, primary_key=True)
    voucher_id     = db.Column(db.Integer, db.ForeignKey('vouchers.id'))
    promoter_id    = db.Column(db.Integer, db.ForeignKey('promoters.id'))

    # الكمية = نفس كمية السند ولا تُعدَّل
    quantity       = db.Column(db.Integer, nullable=False)

    # بيانات العميل / النشاط
    customer_name  = db.Column(db.String(128), nullable=False)
    customer_phone = db.Column(db.String(32),  nullable=False)
    shop_name      = db.Column(db.String(120), nullable=False)

    # المدينة ثابتة = الرياض
    city           = db.Column(db.String(30), nullable=False, default='الرياض')

    # أحد هذين الحقلين على الأقل يجب أن يُملأ
    address_detail = db.Column(db.String(255))   # نص العنوان
    maps_link      = db.Column(db.String(255))   # رابط Google Maps

    cr_number      = db.Column(db.String(50),  nullable=False)  # السجل التجاري
    vat_number     = db.Column(db.String(50),  nullable=False)  # الرقم الضريبي

    preferred_time = db.Column(db.String(80),  nullable=False)  # الوقت المناسب للاستلام
    notes          = db.Column(db.Text)

    # ——— العمود الجديد: رمز تتبّع عام ———
    tracking_token = db.Column(
        db.String(60),
        unique=True,
        nullable=False,
        default=lambda: secrets.token_urlsafe(32)
    )
    status         = db.Column(db.String(20), default='new')    # new | processing | delivered …
    created_at     = db.Column(db.DateTime, default=datetime.utcnow)

    # ── علاقات ORM ───────────────────────────────────────
    voucher   = db.relationship('Voucher',  back_populates='order')
    promoter  = db.relationship('Promoter', back_populates='orders')
    confirmed_earning = db.relationship('ConfirmedEarning',
                                        backref='order',
                                        uselist=False)

# ─────────────────────────────────────────────────────────────────────────────
# 8) جدول التظلم
# ─────────────────────────────────────────────────────────────────────────────
class Dispute(db.Model):
    __tablename__ = 'disputes'

    id            = db.Column(db.Integer, primary_key=True)
    withdrawal_id = db.Column(db.Integer, db.ForeignKey('withdrawals.id'))
    reason        = db.Column(db.Text, nullable=False)
    status        = db.Column(db.String(20), default='open')  # open|resolved
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    withdrawal    = db.relationship('Withdrawal', back_populates='dispute')


# ─────────────────────────────────────────────────────────────────────────────
# 9) جدول سجلات النظام
# ─────────────────────────────────────────────────────────────────────────────
class LogEntry(db.Model):
    __tablename__ = 'log_entries'

    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action     = db.Column(db.String(256), nullable=False)
    timestamp  = db.Column(db.DateTime, default=datetime.utcnow)

    user       = db.relationship('User', backref=db.backref('logs', lazy='dynamic'))

    def __repr__(self):
        return f"<LogEntry {self.id} by {self.user_id or 'anon'} @ {self.timestamp}>"


# ─────────────────────────────────────────────────────────────────────────────
# 10) جدول التقارير
# ─────────────────────────────────────────────────────────────────────────────
class Report(db.Model):
    __tablename__ = 'reports'

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(128), nullable=False)
    payload     = db.Column(db.JSON,       nullable=False)
    created_at  = db.Column(db.DateTime,   default=datetime.utcnow)

    @staticmethod
    def generate_summary():
        from app.models import Factory, Promoter, Voucher, Order
        return {
            'factories_count': Factory.query.count(),
            'promoters_count': Promoter.query.count(),
            'vouchers_new'   : Voucher.query.filter_by(status='new').count(),
            'orders_pending' : Order.query.filter_by(status='new').count(),
        }

    def __repr__(self):
        return f"<Report {self.name} @ {self.created_at}>"



# ─────────────────────────────────────────────────────────────────────────────
# 11) جدول الأرباح المؤكدة (القابلة للسحب فقط)
# ─────────────────────────────────────────────────────────────────────────────
class ConfirmedEarning(db.Model):
    __tablename__ = 'confirmed_earnings'

    id              = db.Column(db.Integer, primary_key=True)
    promoter_id     = db.Column(db.Integer, db.ForeignKey('promoters.id'))
    order_id        = db.Column(db.Integer, db.ForeignKey('orders.id'))
    voucher_id      = db.Column(db.Integer, db.ForeignKey('vouchers.id'))
    amount          = db.Column(db.Float, nullable=False)
    created_at      = db.Column(db.DateTime, default=datetime.utcnow)


    # 🔸 عمولات لم تُربط بعملية تحويل بعد (NULL)، أو تم ربطها بتحويل سابق
    payout_id = db.Column(db.Integer, db.ForeignKey("payout_statuses.id"), nullable=True)

    promoter        = db.relationship('Promoter', backref=db.backref('confirmed_earnings', lazy='dynamic'))
    voucher         = db.relationship('Voucher')



class PayoutStatus(db.Model):
    __tablename__ = 'payout_statuses'

    id          = db.Column(db.Integer, primary_key=True)
    factory_id  = db.Column(db.Integer, db.ForeignKey('factories.id'), nullable=False)
    promoter_id = db.Column(db.Integer, db.ForeignKey('promoters.id'), nullable=False)
    status      = db.Column(db.String(20), default='pending')  # pending | transferring | transferred
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    factory     = db.relationship('Factory')
    promoter    = db.relationship('Promoter')

    def status_label(self):
        return {
            'pending': 'مستحق جديد',
            'transferring': 'جاري التحويل',
            'transferred': 'تم التحويل'
        }.get(self.status, '—')



class CommissionInvoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    voucher_id = db.Column(db.Integer, db.ForeignKey("vouchers.id"), nullable=False, unique=True)
    batch_id   = db.Column(db.Integer, db.ForeignKey("voucher_batch.id"), nullable=True)  # ★ جديد
    invoice_number = db.Column(db.String(50))  # لا يوجد unique=True
    amount = db.Column(db.Numeric(10, 2), nullable=False)  # ✅ أضف هذا السطر
    pdf_url = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
   
    
    batch      = db.relationship("VoucherBatch", backref="commission_invoice", uselist=False)







class VoucherBatch(db.Model):
    __tablename__ = "voucher_batch"

    id = db.Column(db.Integer, primary_key=True)
    factory_id = db.Column(db.Integer, db.ForeignKey("factories.id"), nullable=False)
    product = db.Column(db.String(100), nullable=False)

    # حالة الدفعة: under_review → awaiting_payment → payment_under_review → approved
    status = db.Column(db.String(30), default="under_review")

    payment_proof_url = db.Column(db.Text, nullable=True)
    account_name      = db.Column(db.String(255), nullable=True)
    invoice_url       = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # علاقة بالسندات
    vouchers = db.relationship("Voucher", backref="batch", lazy=True)

    def total_quantity(self):
        return sum(v.quantity for v in self.vouchers)

    def total_commission(self, rate_per_unit=1.0):
        return self.total_quantity() * rate_per_unit
    




class GlobalSetting(db.Model):
    __tablename__ = "global_settings"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(200), nullable=False)
