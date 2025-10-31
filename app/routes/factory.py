# app/routes/factory.py
from app import cache
from flask import Blueprint, abort, current_app, redirect, render_template, request, flash, url_for
from flask_login import login_required, current_user
from app import db
from app.forms.factory.create_voucher_form import VoucherForm
from app.forms.factory.settings_form import FactorySettingsForm
from app.models import CommissionInvoice, ConfirmedEarning, Order, PayoutStatus, Promoter, Voucher, Factory, Earning, VoucherBatch, Withdrawal
from datetime import datetime
from app.utils.generate_qr import generate_qr_code
from sqlalchemy import and_, func
from sqlalchemy.orm import joinedload

from app.utils.helpers import count_waiting_batches

factory_bp = Blueprint('factory', __name__, url_prefix='/factory')

# ─────────────────────────── Dashboard ────────────────────────────
@factory_bp.route('/dashboard', endpoint='dashboard')


@login_required
def dashboard():
    factory = Factory.query.get_or_404(current_user.factory_id)

    # إحصاءات السندات
    total  = Voucher.query.filter_by(factory_id=factory.id).count()
    new    = Voucher.query.filter_by(factory_id=factory.id, status='new').count()
    active = Voucher.query.filter_by(factory_id=factory.id, status='active').count()
    used   = Voucher.query.filter_by(factory_id=factory.id, status='used').count()

    # المبيعات المنجَزة (إجمالي السعر شامل الضريبة لكل السندات المستخدمة)
    sales_total = db.session.query(
        db.func.coalesce(db.func.sum(Voucher.total_price), 0.0)
    ).filter(
        Voucher.factory_id == factory.id,
        Voucher.status == 'used'
    ).scalar()

    # عمولة المروّجين على هذه السندات
    promoters_commission = db.session.query(
        db.func.coalesce(db.func.sum(Earning.promoter_amount), 0.0)
    ).join(Voucher).filter(
        Voucher.factory_id == factory.id
    ).scalar()

    # صافى ربح المصنع = المبيعات − عمولة المروّجين
    net_profit = round((sales_total or 0) - (promoters_commission or 0), 2)

    return render_template(
        'dashboard_factory/index.html',
        total=total, new=new, active=active, used=used,
        sales_total=round(sales_total or 0, 2),
        promoters_commission=round(promoters_commission or 0, 2),
        net_profit=net_profit
    )


# ───────────────────── إصدار سندات جديدة ──────────────────────────
@factory_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_vouchers():
    form    = VoucherForm()
    factory = Factory.query.get_or_404(current_user.factory_id)

    if form.validate_on_submit():
        product        = form.product.data.strip()
        quantity       = form.quantity.data
        count          = form.count.data
        commission_per = form.commission_per.data
        price_per_unit = form.price_per_unit.data
        vat_rate       = form.vat_rate.data
        city           = form.city.data  # ← جديد

        # ❶ إنشاء دفعة جديدة
        batch = VoucherBatch(
            factory_id = factory.id,
            product    = product,
            status     = 'awaiting_payment'
        )
        db.session.add(batch)
        db.session.flush()  # نحصل على batch.id فقط

        # ❷ تجهيز السندات دفعة واحدة بدون flush متكرر
        from uuid import uuid4

        vouchers = []
        vat_multiplier = (1 + vat_rate)
        total_price    = (price_per_unit * quantity) * vat_multiplier
        factory_comm   = commission_per * quantity

        for _ in range(count):
            v = Voucher(
                code               = str(uuid4())[:12].upper(),  # كود فريد وسريع
                product            = product,
                quantity           = quantity,
                price_per_unit     = price_per_unit,
                vat_rate           = vat_rate,
                total_price        = total_price,
                factory_commission = factory_comm,
                factory_id         = factory.id,
                batch_id           = batch.id,
                city               = city
            )
            vouchers.append(v)

        # ❸ إضافة جميع السندات دفعة واحدة (Bulk)
        db.session.bulk_save_objects(vouchers)
        db.session.commit()

        flash(f'✔ تم إصدار {len(vouchers)} سندًا في دفعة واحدة (Batch ID: {batch.id})', 'success')
        return redirect(url_for('factory.create_vouchers'))

    return render_template(
        "dashboard_factory/create_vouchers.html",
        form=form,
        created=[],
        active_tab="issue",
        waiting_batches=count_waiting_batches()
    )






@factory_bp.route('/commission-payments', methods=['GET'])
@login_required
def commission_payments():
    # ------------------------------------------------------
    # ➊ اجلب جميع الدُفعات (VoucherBatch) الخاصة بالمصنع الحالي
    #    والتي ما زالت تتعلق بالدفع (بانتظار – مرفوض – قيد المراجعة)
    # ------------------------------------------------------
    batches = (
        VoucherBatch.query
        .filter_by(factory_id=current_user.factory_id)
        .filter(VoucherBatch.status.in_([
            "awaiting_payment",
            "payment_rejected",
            "payment_under_review"
            
        ]))
        .order_by(VoucherBatch.created_at.desc())
        .all()
    )

    # ------------------------------------------------------
    # ➋ حضّر قائمة مبسَّطة ليستعملها القالب بسهولة
    #    كل عنصر ديكت يحوي معلومات الدفعة
    # ------------------------------------------------------
    batch_groups = []
    for b in batches:
        batch_groups.append({
            "id":               b.id,
            "product":          b.product,
            "voucher_count":    len(b.vouchers),
            "total_quantity":   b.total_quantity(),          # من الدالة التى كتبناها فى المودل
            "total_commission": b.total_commission(),        # (rate_per_unit=1.0 افتراضيًا)
            "status":           b.status
        })

    # ------------------------------------------------------
    # ➌ أعِد القالب ومرّر ثلاث متغيّرات:
    #    groups           → القائمة المبسَّطة ليعرضها الجدول
    #    active_tab       → يضبط التبويب البرّاق Nav-Tabs
    #    waiting_batches  → عدد الدفعات التى تنتظر الدفع (لشارة Badge)
    # ------------------------------------------------------
    return render_template(
        "dashboard_factory/commission_payments.html",
        groups=batch_groups,
        active_tab="payments",
        waiting_batches=count_waiting_batches()
    )


















# routes/factory_bp.py
# routes/factory_bp.py
@factory_bp.route('/commission-payments/<int:batch_id>/upload', methods=['GET', 'POST'])
@login_required
def upload_batch_proof(batch_id):
    batch = (VoucherBatch.query
             .filter_by(id=batch_id, factory_id=current_user.factory_id)
             .first_or_404())

    if request.method == 'POST':
        account_name = (request.form.get('account_name') or '').strip()
        if not account_name:
            flash("الرجاء إدخال اسم الحساب البنكي.", "warning")
            return redirect(request.referrer or url_for('factory.commission_payments'))

        if batch.status not in ['awaiting_payment', 'payment_rejected']:
            flash("⚠️ لا يمكن رفع إثبات لهذه الدفعة في وضعها الحالي.", "warning")
            return redirect(url_for('factory.commission_payments'))

        try:
            # تحديث جماعي سريع فقط لمن حالته ليست الهدف
            updated = (db.session.query(Voucher)
                       .filter(Voucher.batch_id == batch.id,
                               Voucher.status != 'payment_under_review')
                       .update({"status": "payment_under_review"},
                               synchronize_session=False))

            batch.account_name = account_name
            batch.status = 'payment_under_review'

            db.session.commit()
            flash(f"✔ تم رفع بيانات التحويل، وتم تحديث {updated} سندًا.", "success")
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("upload_batch_proof failed: %s", e)
            flash("حدث خطأ أثناء معالجة الدفعة. جرّب لاحقًا.", "danger")

        return redirect(url_for('factory.commission_payments'))

    if batch.status not in ['awaiting_payment', 'payment_rejected']:
        flash("⚠️ لا يمكن رفع إثبات لهذه الدفعة في وضعها الحالي.", "warning")
        return redirect(url_for('factory.commission_payments'))

    return render_template('dashboard_factory/upload_batch_proof.html',
                           batch=batch, active_tab='payments')

# ───────────────────── إعدادات المصنع ─────────────────────────────
@factory_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    factory = Factory.query.get_or_404(current_user.factory_id)
    form = FactorySettingsForm(obj=factory)        # يملأ القيم الحالية

    if form.validate_on_submit():
        form.populate_obj(factory)                 # ينقل القيم إلى الكائن
        db.session.commit()
        flash("✅ تم تحديث بيانات المصنع بنجاح", "success")
        return redirect(url_for('factory.settings'))

    return render_template(
        "dashboard_factory/settings.html",
        form=form
    )


# ───────────────────── تتبع السندات ───────────────────────────────
@factory_bp.route('/track-vouchers')
@login_required
def track_vouchers():
    factory   = Factory.query.get(current_user.factory_id)
    vouchers  = Voucher.query.filter_by(factory_id=factory.id).all()
    return render_template('dashboard_factory/track_vouchers.html', vouchers=vouchers)

@factory_bp.route("/orders", endpoint="orders")
@login_required
def orders():
    factory = Factory.query.get_or_404(current_user.factory_id)

    orders = (
        Order.query
        .options(
            joinedload(Order.voucher),
            joinedload(Order.promoter).joinedload(Promoter.user)
        )
        .join(Voucher)
        .filter(Voucher.factory_id == factory.id)
        .order_by(Order.created_at.desc())
        .all()
    )

    # تقسيم حسب الحالة
    new_orders         = [o for o in orders if o.status == 'new']
    in_progress_orders = [o for o in orders if o.status == 'in_progress']
    done_orders        = [o for o in orders if o.status == 'done']

    return render_template("dashboard_factory/orders.html",
                           new_orders=new_orders,
                           in_progress_orders=in_progress_orders,
                           done_orders=done_orders)



# ───────────────────── الفواتير (PDF) ─────────────────────────────
@factory_bp.route('/invoices')
@login_required
def invoices():
    factory   = Factory.query.get(current_user.factory_id)
    vouchers  = Voucher.query.filter_by(factory_id=factory.id, status='used').all()
    return render_template('dashboard_factory/invoices.html', vouchers=vouchers)



@factory_bp.route('/withdrawals')
@login_required
def withdrawals_list():
    factory_id = current_user.factory_id
    withdrawals = (Withdrawal.query
                   .join(Promoter)
                   .join(Voucher, Voucher.promoter_id == Promoter.id)
                   .filter(Voucher.factory_id == factory_id)
                   .order_by(Withdrawal.created_at.desc())
                   .all())
    return render_template('dashboard_factory/withdrawals.html',
                           withdrawals=withdrawals)

@factory_bp.route('/withdrawals/<int:wid>', methods=['POST'])
@login_required
def decide_withdrawal(wid):
    w = Withdrawal.query.get_or_404(wid)
    factory_id = current_user.factory_id
    # تحقُّق أن السحب يخص هذا المصنع
    any_voucher = (Voucher.query
                   .join(Order)
                   .filter(Order.promoter_id == w.promoter_id,
                           Voucher.factory_id == factory_id).first())
    if not any_voucher:
        abort(403)

    decision = request.form.get('decision')
    note     = request.form.get('note') or None
    if decision == 'approve':
        w.status = 'approved'
        flash('تمت الموافقة على السحب.', 'success')
    else:
        w.status = 'rejected'
        w.factory_note = note
        flash('تم رفض السحب.', 'danger')
    db.session.commit()
    return redirect(url_for('factory.withdrawals_list'))



@factory_bp.route("/orders/<int:order_id>/status", methods=["POST"], endpoint="update_order_status")
@login_required
def update_order_status(order_id):
    """يغيّر حالة طلب يخصّ هذا المصنع، وإذا كانت 'done' يتم إنشاء ربح قابل للسحب"""
    order = Order.query.get_or_404(order_id)
    factory = Factory.query.get_or_404(current_user.factory_id)

    # التأكد أن الطلب تابع لهذا المصنع
    if order.voucher.factory_id != factory.id:
        flash("❌ لا يمكنك تعديل طلب لا يخصّ مصنعك.", "danger")
        return redirect(url_for("factory.orders"))

    # الحالة الجديدة
    new_status = request.form.get("status")
    if new_status not in {"new", "in_progress", "done"}:
        flash("⚠️ حالة غير صالحة.", "warning")
        return redirect(url_for("factory.orders"))

    # تحديث الحالة
    order.status = new_status
    db.session.commit()

    # إذا كانت الحالة "done"، نضيف ربح قابل للسحب
    if new_status == "done":
        # تفادي التكرار
        exists = ConfirmedEarning.query.filter_by(order_id=order.id).first()
        if not exists:
            earning = Earning.query.filter_by(
                voucher_id=order.voucher_id,
                promoter_id=order.promoter_id
            ).first()

            if earning:
                confirmed = ConfirmedEarning(
                    promoter_id=order.promoter_id,
                    order_id=order.id,
                    voucher_id=order.voucher_id,
                    amount=earning.promoter_amount
                )
                db.session.add(confirmed)
                db.session.commit()

    flash("✅ تم تحديث حالة الطلب بنجاح.", "success")
    return redirect(url_for("factory.orders"))

from itertools import groupby
from operator import attrgetter
from sqlalchemy.orm import load_only

LIMIT = 20  # ★ حد العرض المبدئي لكل منتج

@factory_bp.route('/my-vouchers')
def vouchers_list():
    factory_id = current_user.factory_id

    # نجلب فقط الأعمدة اللازمة + ترتيب يخدم التجميع
    q = (
        Voucher.query
        .filter_by(factory_id=factory_id)
        .options(load_only(
            Voucher.id,
            Voucher.product,
            Voucher.code,
            Voucher.quantity,
            Voucher.status,
            Voucher.admin_note,
            Voucher.created_at
        ))
        .order_by(Voucher.product.asc(), Voucher.created_at.desc())
    )
    vouchers = q.all()

    # تجميع في البايثون (أسرع من Jinja groupby)
    groups = []
    for product, items_iter in groupby(vouchers, key=attrgetter('product')):
        items = list(items_iter)
        initial_rows = items[:LIMIT]                  # ★ أول دفعة
        remaining     = max(0, len(items) - LIMIT)    # ★ المتبقي

        groups.append({
            'product': product,
            'count': len(items),
            'total_qty': sum((v.quantity or 0) for v in items),
            'rows': initial_rows,                     # ★ الصفوف المعروضة مبدئيًا
            'remaining': remaining,                   # ★ عدد المتبقي
        })

    return render_template(
        'dashboard_factory/vouchers_list.html',
        groups=groups,
        LIMIT=LIMIT                                   # ★ نمرر الحد للقالب
    )


# ★ راوت التحميل الكسول: يُرجع دفعة صفوف TR إضافية لمنتج معيّن
@factory_bp.route('/my-vouchers/more')
def vouchers_list_more():
    factory_id = current_user.factory_id
    product = request.args.get('product', type=str)
    offset  = request.args.get('offset',  type=int, default=0)
    if not product:
        abort(400, description="product is required")

    q = (
        Voucher.query
        .filter_by(factory_id=factory_id, product=product)
        .options(load_only(
            Voucher.id,
            Voucher.product,
            Voucher.code,
            Voucher.quantity,
            Voucher.status,
            Voucher.admin_note,
            Voucher.created_at
        ))
        .order_by(Voucher.created_at.desc())
    )

    # نجيب الدفعة التالية فقط
    rows = q.slice(offset, offset + LIMIT).all()
    # نرندر صفوف <tr> فقط من خلال قالب جزئي
    return render_template('dashboard_factory/_voucher_rows.html', rows=rows)

@factory_bp.route('/voucher/<int:voucher_id>/upload-proof', methods=['GET', 'POST'])
def upload_payment_proof(voucher_id):
    voucher = Voucher.query.get_or_404(voucher_id)

    # التحقق أن المستخدم يملك السند
    if voucher.factory_id != current_user.factory_id:
        flash("ليس لديك صلاحية على هذا السند.", "danger")
        return redirect(url_for('factory.vouchers_list'))

    if request.method == 'POST':
        proof_url = request.form.get('proof')  # اختياري
        account_name = request.form.get('account_name')  # جديد

        # تخزين البيانات
        voucher.payment_proof_url = proof_url
        voucher.payment_account_name = account_name  # ✅ نضيف هذا السطر
        voucher.status = 'payment_under_review'

        db.session.commit()
        flash("تم تأكيد الدفع بنجاح. بانتظار مراجعة الإدارة.", "success")
        return redirect(url_for('factory.vouchers_list'))

    return render_template('dashboard_factory/upload_payment_proof.html', voucher=voucher)



@factory_bp.route("/orders/<int:order_id>/transfer", methods=["POST"], endpoint="transfer_commission")
def transfer_commission(order_id):
    order = Order.query.get_or_404(order_id)

    if order.status != "done":
        flash("لا يمكن تحويل العمولة إلا بعد اكتمال الطلب.", "warning")
        return redirect(url_for("factory.bond_orders"))

    if not order.promoter:
        flash("هذا الطلب لا يملك مروجًا.", "danger")
        return redirect(url_for("factory.bond_orders"))

    # تحقق من عدم تكرار التحويل
    existing = ConfirmedEarning.query.filter_by(order_id=order.id).first()
    if existing:
        flash("تم تحويل العمولة مسبقًا.", "info")
        return redirect(url_for("factory.bond_orders"))

    # احسب العمولة = الكمية × نسبة المصنع
    commission = order.quantity * order.voucher.factory.commission_rate

    earning = ConfirmedEarning(
        promoter_id = order.promoter_id,
        voucher_id  = order.voucher_id,
        order_id    = order.id,
        amount      = commission
    )

    db.session.add(earning)
    db.session.commit()

    flash(f"✅ تم تحويل عمولة ({commission:.2f} ريال) للمروج.", "success")
    return redirect(url_for("factory.bond_orders"))



# ────────── عرض حالة العمولات للمروجين ──────────
@factory_bp.route("/orders/promoters", endpoint="orders_promoters")
@login_required
def orders_promoters():
    factory_id = current_user.factory_id

    # ─────────── أولاً: المستحقات الجديدة (بدون payout_id) ───────────
    sub_pending = (
        db.session.query(
            Promoter,
            func.coalesce(func.sum(ConfirmedEarning.amount), 0.0).label("total_amount"),
            PayoutStatus
        )
        .join(ConfirmedEarning, ConfirmedEarning.promoter_id == Promoter.id)
        .join(Order, ConfirmedEarning.order_id == Order.id)
        .join(Voucher, Order.voucher_id == Voucher.id)
        .outerjoin(PayoutStatus, and_(
            PayoutStatus.factory_id == factory_id,
            PayoutStatus.promoter_id == Promoter.id
        ))
        .filter(
            Voucher.factory_id == factory_id,
            Order.status == 'done',
            ConfirmedEarning.payout_id == None  # لم يتم تحويلها بعد
        )
        .group_by(Promoter.id, PayoutStatus.id)
        .all()
    )

    # ─────────── ثانياً: العمولات المرتبطة بتحويل (payout_id موجود) ───────────
    sub_grouped = (
        db.session.query(
            PayoutStatus,
            Promoter,
            func.coalesce(func.sum(ConfirmedEarning.amount), 0.0).label("total_amount")
        )
        .join(Promoter, Promoter.id == PayoutStatus.promoter_id)
        .join(ConfirmedEarning, and_(
            ConfirmedEarning.payout_id == PayoutStatus.id,
            ConfirmedEarning.promoter_id == Promoter.id
        ))
        .join(Order, ConfirmedEarning.order_id == Order.id)
        .join(Voucher, Order.voucher_id == Voucher.id)
        .filter(
            Voucher.factory_id == factory_id,
            Order.status == 'done'
        )
        .group_by(PayoutStatus.id, Promoter.id)
        .all()
    )

    # ─────────── تقسيم البيانات حسب الحالة ───────────
    pending = []
    transferring = []
    transferred = []

    # المستحق الجديد (payout_id = None)
    for promoter, total_amount, payout in sub_pending:
        if not payout:
            payout = PayoutStatus(factory_id=factory_id, promoter_id=promoter.id, status='pending')
            db.session.add(payout)
            db.session.commit()

        pending.append({
            'promoter': promoter,
            'total_amount': total_amount,
            'payout': payout
        })

    # المرتبطة بـ payout_id
    for payout, promoter, total_amount in sub_grouped:
        data = {
            'promoter': promoter,
            'total_amount': total_amount,
            'payout': payout
        }

        if payout.status == 'transferring':
            transferring.append(data)
        elif payout.status == 'transferred':
            transferred.append(data)

    return render_template(
        "dashboard_factory/orders_promoters.html",
        pending=pending,
        transferring=transferring,
        transferred=transferred
    )


    
@factory_bp.route("/orders/promoters/<int:promoter_id>/update_status", methods=["POST"])
@login_required
def update_payout_status(promoter_id):
    factory_id = current_user.factory_id
    status = request.form.get("status")

    if status not in ['pending', 'transferring', 'transferred']:
        flash("⚠️ حالة غير صالحة.", "warning")
        return redirect(url_for("factory.orders_promoters"))

    payout = (
        PayoutStatus.query
        .filter_by(factory_id=factory_id, promoter_id=promoter_id)
        .order_by(PayoutStatus.id.desc())
        .first()
    )

    if not payout:
        payout = PayoutStatus(factory_id=factory_id, promoter_id=promoter_id, status=status)
        db.session.add(payout)
        db.session.commit()
    else:
        # ⚠️ إذا كانت الحالة الجديدة "جاري التحويل"، أنشئ سجل جديد واربط العمولات
        if status == "transferring" and payout.status != "transferring":
            # إنشاء سجل جديد
            new_payout = PayoutStatus(factory_id=factory_id, promoter_id=promoter_id, status="transferring")
            db.session.add(new_payout)
            db.session.flush()  # نحصل على ID بدون commit

            # ربط العمولات التي لم تُربط بأي تحويل
            confirmed = ConfirmedEarning.query.join(Order).join(Voucher).filter(
                ConfirmedEarning.promoter_id == promoter_id,
                ConfirmedEarning.payout_id == None,
                Order.status == 'done',
                Voucher.factory_id == factory_id
            ).all()

            for row in confirmed:
                row.payout_id = new_payout.id

            db.session.commit()
            flash("✅ تم إنشاء تحويل جديد وربط العمولات به.", "success")
            return redirect(url_for("factory.orders_promoters"))

        # في الحالات الأخرى، نحدّث الحالة فقط
        payout.status = status
        db.session.commit()
        flash("✅ تم تحديث حالة التحويل.", "success")
        return redirect(url_for("factory.orders_promoters"))


# ── صفحة فواتيري ─────────────────────
@factory_bp.route("/commission-invoices")
@login_required
def factory_commission_invoices():
    invoices = (
        CommissionInvoice.query
        .join(Voucher)
        .filter(Voucher.factory_id == current_user.factory_id)
        .order_by(CommissionInvoice.created_at.desc())
        .all()
    )
    return render_template("dashboard_factory/commission_invoices.html", invoices=invoices)



@factory_bp.route('/orders/print')
@login_required
def print_orders():
    status = request.args.get('status', 'new')
    orders = Order.query.filter_by(status=status).all()
    return render_template('dashboard_factory/orders_print.html', orders=orders)




# app/routes/factory.py
@factory_bp.route('/print-transfers', endpoint='print_transfers')
@login_required
def print_transfers():
    factory_id = current_user.factory_id

    transfers = (
        db.session.query(
            Promoter,
            func.coalesce(func.sum(ConfirmedEarning.amount), 0.0).label("total_amount"),
            PayoutStatus
        )
        .join(PayoutStatus, PayoutStatus.promoter_id == Promoter.id)
        .join(ConfirmedEarning,
              and_(ConfirmedEarning.payout_id == PayoutStatus.id,
                   ConfirmedEarning.promoter_id == Promoter.id))
        .join(Order, ConfirmedEarning.order_id == Order.id)
        .join(Voucher, Order.voucher_id == Voucher.id)
        .filter(
            Voucher.factory_id == factory_id,
            Order.status == 'done',
            PayoutStatus.status == 'transferring'      # ← هنا التغيير
        )
        .group_by(Promoter.id, PayoutStatus.id)
        .all()
    )

    return render_template('dashboard_factory/print_transfers.html',
                           transfers=transfers)
