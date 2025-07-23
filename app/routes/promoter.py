# app/routes/promoter.py
from flask import (
    Blueprint, abort, render_template, redirect,
    url_for, flash, request
)
from flask_login import current_user, login_required
from functools import wraps
from app import db
from app.forms.promoter.profile_form import PromoterProfileForm
from app.models import ConfirmedEarning, Dispute, PayoutStatus, Voucher, Earning, Promoter, Order, Withdrawal
from sqlalchemy.orm import joinedload

promoter_bp = Blueprint(
    "promoter",
    __name__,
    url_prefix="/promoter",
    template_folder="../templates/dashboard_promoter"
)

# ───────── ديكوريتور يتحقق أن المستخدم مروج ─────────
def promoter_only(view_func):
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "promoter":
            flash("ليس لديك صلاحية الوصول إلى هذه الصفحة.", "danger")
            return redirect(url_for("public.index"))
        return view_func(*args, **kwargs)
    return login_required(wrapper)

@promoter_bp.route("/dashboard", endpoint="dashboard")
@promoter_only
def dashboard():
    promoter = current_user.promoter
    if not promoter:
        flash("⚠️ لم يتم ربط حسابك بمروج.", "danger")
        return redirect(url_for("logout"))

    pid = promoter.id

    # ───────── إحصاءات السندات ─────────
    total_vouchers  = Voucher.query.filter_by(promoter_id=pid).count()
    active_vouchers = Voucher.query.filter_by(promoter_id=pid, status="active").count()

    used_vouchers   = (
        db.session.query(Order)
        .join(Voucher)
        .filter(Order.promoter_id == pid, Order.status == "done")
        .count()
    )

    # ───────── إحصاءات الطلبات ─────────
    total_orders = Order.query.filter_by(promoter_id=pid).count()
    pending_orders = Order.query.filter_by(promoter_id=pid).filter(Order.status != "done").count()
    done_orders    = Order.query.filter_by(promoter_id=pid, status="done").count()

    # ───────── الأرباح من جدول Earning ─────────
    potential_sum = (
        db.session.query(db.func.coalesce(db.func.sum(Earning.promoter_amount), 0.0))
        .join(Voucher).join(Order)
        .filter(Earning.promoter_id == pid, Order.status != "done")
        .scalar()
    )

    confirmed_sum = (
        db.session.query(db.func.coalesce(db.func.sum(Earning.promoter_amount), 0.0))
        .join(Voucher).join(Order)
        .filter(Earning.promoter_id == pid, Order.status == "done")
        .scalar()
    )

    # ───────── الأرباح بعد التحويل من ConfirmedEarning ─────────
    converted_sum = (
        db.session.query(db.func.coalesce(db.func.sum(ConfirmedEarning.amount), 0.0))
        .filter(ConfirmedEarning.promoter_id == pid, ConfirmedEarning.payout_id.isnot(None))
        .scalar()
    )

    return render_template(
        "dashboard_promoter/index.html",
        total_vouchers=total_vouchers,
        active_vouchers=active_vouchers,
        used_vouchers=used_vouchers,
        total_orders=total_orders,
        pending_orders=pending_orders,
        done_orders=done_orders,
        potential_sum=round(potential_sum or 0, 2),
        confirmed_sum=round(confirmed_sum or 0, 2),
        converted_sum=round(converted_sum or 0, 2)
    )


# ───────── قائمة “سنداتي” مع تصفية المنتج ─────────
@promoter_bp.route("/vouchers", endpoint="vouchers")
@promoter_only
def my_vouchers():
    promoter = Promoter.query.filter_by(user_id=current_user.id).first_or_404()
    pid = promoter.id

    # جميع المنتجات المتاحة لهذا المروّج (للقائمة المنسدلة)
    products = (
        db.session.query(Voucher.product)
        .filter_by(promoter_id=pid)
        .distinct()
        .order_by(Voucher.product)
        .all()
    )
    products = [p[0] for p in products]          # استخراج القيم فقط

    # قيمة التصفية المختارة من الـ Query-string
    chosen = request.args.get("product", "all")

    base_q = Voucher.query.filter_by(promoter_id=pid)
    if chosen != "all":
        base_q = base_q.filter_by(product=chosen)

    vouchers_all = base_q.order_by(Voucher.created_at.desc()).all()

    # تقسيم إلى مفعَّلة / مستخدمة
    active = [v for v in vouchers_all if v.status == "active"]
    used   = [v for v in vouchers_all if v.status == "used"]

    return render_template(
        "dashboard_promoter/my_vouchers.html",
        products=products,
        chosen=chosen,
        active=active,
        used=used
    )
# ───────── أرباحي ─────────
# routes/promoter.py
@promoter_bp.route("/earnings")
@promoter_only
def earnings():
    # احصل على رقم المروّج الصحيح
    promoter = Promoter.query.filter_by(user_id=current_user.id).first_or_404()
    pid = promoter.id
    # 1) أرباح محتملة
    potential = (
        db.session.query(Earning, Voucher, Order)
        .join(Voucher, Voucher.id == Earning.voucher_id)
        .join(Order, Order.voucher_id == Voucher.id)
        .filter(Earning.promoter_id == pid,
                Order.status != 'done')
        .all()
    )
    # 2) أرباح مؤكدة (لم تُحوّل بعد)
    confirmed = (
        db.session.query(ConfirmedEarning, Order, Voucher)
        .join(Order, Order.id == ConfirmedEarning.order_id)
        .join(Voucher, Voucher.id == ConfirmedEarning.voucher_id)
        .filter(ConfirmedEarning.promoter_id == pid,
                ConfirmedEarning.payout_id.is_(None))
        .all()
    )
    # 3) أرباح قيد التحويل / تم تحويلها
    converted = (
        db.session.query(ConfirmedEarning, Order, Voucher, PayoutStatus)
        .join(Order, Order.id == ConfirmedEarning.order_id)
        .join(Voucher, Voucher.id == ConfirmedEarning.voucher_id)
        .join(PayoutStatus, PayoutStatus.id == ConfirmedEarning.payout_id)
        .filter(ConfirmedEarning.promoter_id == pid)
        .all()
    )

    return render_template(
        "dashboard_promoter/earnings.html",
        potential=potential,
        confirmed=confirmed,
        converted=converted
    )

# ───────── الإعدادات ─────────
@promoter_bp.route("/settings", methods=["GET", "POST"], endpoint="settings")
@promoter_only
def settings():
    form = PromoterProfileForm(obj=current_user.promoter)

    if form.validate_on_submit():
        current_user.promoter.account_holder_name = form.account_holder_name.data.strip()
        current_user.promoter.bank_name = form.bank_name.data.strip()
        current_user.promoter.iban = form.iban.data.strip()
        db.session.commit()
        flash("✅ تم تحديث بيانات الحساب البنكي بنجاح", "success")
        return redirect(url_for("promoter.settings"))

    return render_template("dashboard_promoter/settings.html", form=form)


# إظهار أرباحه القابلة للسحب

from flask_wtf import FlaskForm

class DummyForm(FlaskForm):
    pass

@promoter_bp.route('/withdraw', methods=['GET', 'POST'])
@login_required
def withdraw_request():
    promoter = current_user.promoter
    form = DummyForm()

    # تحقق من وجود طلب سابق قيد المراجعة
    pending = Withdrawal.query.filter_by(promoter_id=promoter.id, status='pending').first()
    if pending:
        flash('لديك طلب سحب قيد المراجعة.', 'warning')
        return redirect(url_for('promoter.vouchers'))

    # جلب الأرباح القابلة للسحب فقط من جدول ConfirmedEarning
    confirmed_earnings = ConfirmedEarning.query.filter_by(promoter_id=promoter.id).all()

    total_done = sum(e.amount for e in confirmed_earnings)
    total_pending = 0.0  # ما فيه أرباح غير مؤكدة في هذا المنطق بعد الآن

    rows = [
        {
            'voucher_code': e.voucher.code if e.voucher else '—',
            'amount': e.amount,
            'status': 'done',
            'withdrawable': True
        }
        for e in confirmed_earnings
    ]

    # حساب المسحوبات السابقة
    total_paid = db.session.query(
        db.func.coalesce(db.func.sum(Withdrawal.amount), 0.0)
    ).filter(
        Withdrawal.promoter_id == promoter.id,
        Withdrawal.status == 'approved'
    ).scalar()

    balance = total_done - total_paid

    if request.method == 'POST' and form.validate_on_submit():
        w = Withdrawal(promoter_id=promoter.id, amount=balance)
        db.session.add(w)
        db.session.commit()
        flash('تم إرسال طلب السحب للمصنع بنجاح.', 'success')
        return redirect(url_for('promoter.vouchers'))

    return render_template(
        'dashboard_promoter/withdraw.html',
        form=form,
        balance=balance,
        total_done=total_done,
        total_pending=total_pending,
        rows=rows
    )



@promoter_bp.route('/withdrawals/<int:wid>/appeal', methods=['GET', 'POST'])
@login_required
def appeal_withdrawal(wid):
    w = Withdrawal.query.get_or_404(wid)
    if w.promoter_id != current_user.promoter.id or w.status != 'rejected':
        abort(403)
    if request.method == 'POST':
        reason = request.form.get('reason', '').strip()
        if not reason:
            flash('يرجى كتابة سبب التظلّم', 'warning'); return redirect(request.url)
        d = Dispute(withdrawal_id=w.id, reason=reason)
        db.session.add(d); db.session.commit()
        flash('تم إرسال التظلّم إلى الإدارة.', 'success')
        return redirect(url_for('promoter.vouchers'))

    return render_template('dashboard_promoter/appeal.html', withdrawal=w)





