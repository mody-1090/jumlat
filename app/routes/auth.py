from flask import Blueprint, render_template, redirect, session, url_for, request, flash, current_app
from flask_login import login_user, logout_user, login_required
from itsdangerous import URLSafeTimedSerializer
from app import db
from app.forms.ForgotPasswordForm import ForgotPasswordForm
from app.forms.login_form import LoginForm
from app.forms.register_form import RegisterForm
from app.forms.reset_password_form import ResetPasswordForm
from app.models import User, Factory, Promoter
from app.utils.email import send_email  # تأكد من وجود هذا الملف

auth_bp = Blueprint('auth', __name__)

# ───── التسجيل ─────
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        # 1) إنشاء مستخدم
        user = User(
            username=form.username.data,
            email=form.email.data,
            phone=form.phone.data,
            role=form.role.data
        )
        user.password = form.password.data
        db.session.add(user)
        db.session.flush()

        # 2) مصنع
        if form.role.data == 'factory':
            factory = Factory(
                name=form.factory_name.data,
                contact_person=form.factory_contact.data,
                contact_phone=form.factory_phone.data,
                cr_number=form.cr_number.data,
                vat_number=form.vat_number.data,
                commission_rate=1.0
            )
            db.session.add(factory)
            db.session.flush()
            user.factory_id = factory.id

        # 3) مروج
        if form.role.data == 'promoter':
            promoter = Promoter(
                name=form.username.data,
                user_id=user.id,
                account_holder_name=form.account_holder_name.data,
                bank_name=form.bank_name.data,
                iban=form.iban.data
            )
            db.session.add(promoter)

        db.session.commit()

        # 4) إرسال رابط التفعيل
        token = generate_token(user.email, salt='email-confirm')
        confirm_url = url_for('auth.confirm_email', token=token, _external=True)
        send_email(user.email, "تفعيل حسابك في جُملة", 'public/email/confirm.html',
                   confirm_url=confirm_url, user=user)

        flash('تم إنشاء الحساب. تفقد بريدك لتفعيل الحساب.', 'success')
        return redirect(url_for('auth.activation_sent'))

    return render_template('public/register.html', form=form)

# ───── تسجيل الدخول ─────
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    error = None

    if form.validate_on_submit():
        # البحث بالبريد بدل username
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()
        if user and user.check_password(form.password.data):
            if not user.is_verified:
                flash('رجاءً فعّل بريدك أولًا.', 'warning')
                return redirect(url_for('auth.login'))

            login_user(user)
            next_page = {
                'factory' : url_for('factory.dashboard'),
                'promoter': url_for('promoter.dashboard'),
                'admin'   : url_for('admin.dashboard')
            }.get(user.role, url_for('public.index'))
            return redirect(next_page)

        error = "البريد الإلكتروني أو كلمة المرور غير صحيحة"

    return render_template('public/login.html', form=form, error=error)

# ───── تسجيل الخروج ─────
@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('public.index'))

# ───── تفعيل البريد ─────
@auth_bp.route('/confirm/<token>')
def confirm_email(token):
    email = verify_token(token, salt='email-confirm')
    if not email:
        flash("رابط التفعيل غير صالح أو منتهي.", "danger")
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(email=email).first_or_404()

    if not user.is_verified:
        user.is_verified = True
        db.session.commit()

        # ◀️ أرسل رسالة ببيانات الحساب
        send_email(
            user.email,
            "تم تفعيل حسابك في جُملة",
            'public/email/account_info.html',
            user=user,            # يُستخدم في القالب
            login_url=url_for('auth.login', _external=True)
        )

    # بدلاً من flash ➜ أعرض صفحة نجاح
    return render_template('public/activation_success.html', user=user)

# ───── نسيان كلمة المرور ─────
@auth_bp.route('/forgot', methods=['GET', 'POST'], endpoint='forgot_password')
def forgot_password():
    form = ForgotPasswordForm()

    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user  = User.query.filter_by(email=email).first()
        if user:
            token = generate_token(user.email, salt='reset-password')
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            send_email(user.email, "استعادة كلمة المرور",
                       'public/email/reset.html', reset_url=reset_url)
        flash("إذا كان البريد مسجَّلًا ستصلك رسالة قريبًا.", "info")
        return redirect(url_for('auth.login'))

    return render_template('public/email/forgot.html', form=form)


@auth_bp.route('/reset/<token>', methods=['GET', 'POST'], endpoint='reset_password')
def reset_password(token):
    email = verify_token(token, salt='reset-password')
    if not email:
        flash("الرابط منتهي أو غير صالح.", "danger")
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(email=email).first_or_404()
    form = ResetPasswordForm()

    if form.validate_on_submit():
        user.password = form.password.data
        db.session.commit()
        flash("تم تحديث كلمة المرور بنجاح.", "success")
        return redirect(url_for('auth.login'))

    return render_template('public/reset.html', form=form)

# ───── أدوات التوكين ─────
def generate_token(email, salt):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    return s.dumps(email, salt=salt)

def verify_token(token, salt, expires_sec=3600):
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = s.loads(token, salt=salt, max_age=expires_sec)
    except Exception:
        return None
    return email



@auth_bp.route('/activation-sent')
def activation_sent():
    """تعرض رسالة ثابتة تطلب من المستخدم التحقق من بريده."""
    return render_template('public/activation_sent.html')