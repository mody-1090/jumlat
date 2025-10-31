from datetime import datetime
from app import cache
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from sqlalchemy import func, or_, text
from app import db
from app.forms.admin.notify_factory_form import NotifyFactoryForm
from app.forms.admin.voucher_review_form import VoucherReviewForm
from app.models import CommissionInvoice, Factory, Order, Promoter, LogEntry, Report, Dispute, User, Voucher
from app.utils.commission_invoice import create_commission_invoice
from app.utils.commission_invoice_pdf import create_batch_commission_invoice
from app.utils.email import send_email
from sqlalchemy.orm import selectinload
from sqlalchemy import desc
from math import ceil

admin_bp = Blueprint(
    'admin',
    __name__,
    url_prefix='/admin',
    template_folder='../templates/dashboard_admin'
)

def admin_required(func):
    """ديكور بسيط يتأكد أن المستخدم أدمِن."""
    from flask import abort
    def wrapper(*args, **kwargs):
        if getattr(current_user, 'role', None) != 'admin':
            flash('⚠️ لا تملك صلاحية الوصول لصفحة الإدارة.', 'warning')
            return redirect(url_for('public.index'))
        return func(*args, **kwargs)
    return login_required(wrapper)

# ─── لوحة الإدارة الرئيسية ──────────────────────────
@admin_bp.route('/dashboard', endpoint='dashboard')
@cache.cached(timeout=300)   # كاش 5 دقائق

@admin_required
def index():
    stats = {
        'factories': Factory.query.count(),
        'promoters': Promoter.query.count(),
        'vouchers' : Dispute.query.count(),  # مثال
    }
    return render_template('dashboard_admin/index.html', stats=stats)

# ─── سجلات النظام ────────────────────────────────────
@admin_bp.route('/logs', endpoint='logs')
@admin_required
def logs():
    entries = LogEntry.query.order_by(LogEntry.timestamp.desc()).limit(200).all()
    return render_template('dashboard_admin/logs.html', logs=entries)

# ─── إدارة المصانع ────────────────────────────────────
@admin_bp.route('/manage-factories', endpoint='manage_factories')
@admin_required
def manage_factories():
    factories = Factory.query.order_by(Factory.name).all()
    return render_template('dashboard_admin/manage_factories.html', factories=factories)

# ─── إدارة المروجين ───────────────────────────────────


@admin_bp.route('/promoters/<int:id>/edit', methods=['GET', 'POST'], endpoint='edit_promoter')
@admin_required
def edit_promoter(id):
    promoter = Promoter.query.get_or_404(id)
    user = promoter.user

    if request.method == 'POST':
        # الحقول الأساسية
        promoter.name = (request.form.get('name') or promoter.name)

        # احتمال وجود حقول إضافية في Promoter – حدّث المتوفر منها فقط
        for field in ['city', 'iban', 'bank_name', 'balance']:
            if hasattr(promoter, field) and (field in request.form):
                setattr(promoter, field, request.form.get(field) or getattr(promoter, field))

        # حقول المستخدم المرتبطة
        user.email = (request.form.get('email') or user.email)
        user.phone = (request.form.get('phone') or user.phone)

        # حالة التفعيل (checkbox)
        is_verified = request.form.get('is_verified')
        user.is_verified = True if is_verified == 'on' else False

        db.session.commit()
        flash('تم تحديث بيانات المروّج بنجاح', 'success')
        return redirect(url_for('.manage_promoters'))

    return render_template('dashboard_admin/promoter_edit.html', promoter=promoter)

@admin_bp.route('/promoters/<int:id>/delete', methods=['POST'], endpoint='delete_promoter')
@admin_required
def delete_promoter(id):
    promoter = Promoter.query.get_or_404(id)
    user = promoter.user  # إن رغبت بحذف المستخدم المرتبط أيضًا

    db.session.delete(promoter)
    # انتبه: لا تحذف user إذا كان له علاقات أخرى
    # db.session.delete(user)

    db.session.commit()
    flash('تم حذف المروّج', 'success')
    return redirect(url_for('.manage_promoters'))

from collections import defaultdict
from sqlalchemy.orm import joinedload
from sqlalchemy import and_

ACTIVE_STATES = ['active']  # أضف حالات أخرى لو عندك مثل 'delivered' إلخ

@admin_bp.route('/manage-promoters', endpoint='manage_promoters')
@admin_required
def manage_promoters():
    promoters = (
        Promoter.query
        .options(joinedload(Promoter.user))
        .order_by(Promoter.name)
        .all()
    )

    if not promoters:
        return render_template('dashboard_admin/manage_promoters.html',
                               promoters=[],
                               vouchers_by_promoter={})

    promoter_ids = [p.id for p in promoters]

    # ✅ سندات السوق = (له Order) أو (status ضمن ACTIVE_STATES) وبشرط أنها للمروّج
    activated_or_active_vouchers = (
        db.session.query(Voucher)
        .outerjoin(Order, Order.voucher_id == Voucher.id)
        .filter(Voucher.promoter_id.in_(promoter_ids))
        .filter(
            or_(
                Order.id.isnot(None),                # له طلب => مُستخدم من السوق
                Voucher.status.in_(ACTIVE_STATES)    # نشط مع المروّج حتى لو بدون طلب
            )
        )
        .options(
            joinedload(Voucher.factory),
            joinedload(Voucher.order)
        )
        # ترتيب: الأحدث بالطلب ثم الأحدث بالسند
        .order_by(desc(Order.created_at), desc(Voucher.id))
        .all()
    )

    # تجميع حسب المروّج
    vouchers_by_promoter = defaultdict(list)
    for v in activated_or_active_vouchers:
        if v.promoter_id:
            vouchers_by_promoter[v.promoter_id].append(v)

    return render_template(
        'dashboard_admin/manage_promoters.html',
        promoters=promoters,
        vouchers_by_promoter=vouchers_by_promoter
    )


@admin_bp.route('/vouchers/<int:id>', endpoint='view_voucher')
@admin_required
def view_voucher(id):
    v = (
        Voucher.query
        .options(
            joinedload(Voucher.factory),
            joinedload(Voucher.promoter).joinedload(Promoter.user),
            joinedload(Voucher.order),
            joinedload(Voucher.commission_invoice),
            joinedload(Voucher.batch)
        )
        .get_or_404(id)
    )
    return render_template('dashboard_admin/voucher_detail.html', v=v)




@admin_bp.route('/factories/<int:id>', endpoint='view_factory')
@admin_required
def view_factory(id):
    factory = Factory.query.get_or_404(id)
    return render_template('dashboard_admin/factory_detail.html', factory=factory)








# ─── التقارير ────────────────────────────────────────
@admin_bp.route('/reports', endpoint='reports')
@admin_required
def reports():
    data = Report.generate_summary()   # دالة وهمية تولّد بيانات التقرير
    return render_template('dashboard_admin/reports.html', report=data)

# ─── التظلمات ────────────────────────────────────────
@admin_bp.route('/disputes', endpoint='disputes')
@admin_required
def disputes():
    disputes = Dispute.query.order_by(Dispute.created_at.desc()).all()
    return render_template('dashboard_admin/disputes.html', disputes=disputes)

# ─── مراجعة تظلم واحد ────────────────────────────────
@admin_bp.route('/disputes/<int:dispute_id>', methods=['GET','POST'], endpoint='review_dispute')
@admin_required
def review_dispute(dispute_id):
    d = Dispute.query.get_or_404(dispute_id)
    if request.method == 'POST':
        action = request.form.get('action')         # 'approve' أو 'reject'
        note   = request.form.get('admin_note', '').strip()
        d.admin_note = note
        d.status = 'approved' if action=='approve' else 'rejected'
        db.session.commit()
        flash('تم تحديث حالة التظلم بنجاح.', 'success')
        return redirect(url_for('admin.disputes'))
    return render_template('dashboard_admin/review_dispute.html', dispute=d)


@admin_bp.route('/voucher-review', methods=['GET'])
def voucher_review():
    vouchers = Voucher.query.filter_by(status='pending_admin_review').all()
    form = VoucherReviewForm()

    # استعلام إعداد القبول التلقائي
    setting = GlobalSetting.query.filter_by(key="auto_approve_vouchers").first()
    auto_approve_enabled = setting and setting.value == "true"

    return render_template(
        'dashboard_admin/voucher_review.html',
        vouchers=vouchers,
        form=form,
        auto_approve_enabled=auto_approve_enabled  # هذا المهم
    )



# routes/admin_bp.py
from flask import request, redirect, url_for, flash
from flask_login import login_required
from app import db
from app.models import Voucher, VoucherBatch

# routes/admin.py
@admin_bp.route("/voucher-review/action", methods=["POST"])
@login_required
def review_voucher_action():
    """
    يدعم أربع حالات:
      1) action == approve           + voucher_id  → قبول فردي
      2) action == reject            + voucher_id  → رفض فردي
      3) action == approve_bulk      + voucher_ids → قبول مجموعة
      4) action == reject_bulk       + voucher_ids → رفض مجموعة
    """
    # قيم النموذج
    action       = request.form.get("action")              # approve / reject / approve_bulk / reject_bulk
    voucher_id   = request.form.get("voucher_id",  type=int)
    voucher_ids  = request.form.getlist("voucher_ids", type=int)  # قائمة في حالة bulk
    reason       = request.form.get("reason", "").strip()

    # -------------- أداة داخلية لإجراء القبول --------------
    def approve_voucher(v: Voucher):
        v.status = "awaiting_payment"

        # 1) إيجاد/إنشاء دفعة مناسبة
        if v.batch_id is None:
            batch = (
                VoucherBatch.query
                .filter_by(factory_id=v.factory_id,
                           product=v.product,
                           status="under_review")
                .first()
            )
            if batch is None:
                batch = VoucherBatch(
                    factory_id=v.factory_id,
                    product=v.product,
                    status="under_review"
                )
                db.session.add(batch)
                db.session.flush()  # للحصول على batch.id

            v.batch_id = batch.id

        # 2) ترقية حالة الدفعة إن اكتملت
        batch = v.batch
        if batch and all(x.status == "awaiting_payment" for x in batch.vouchers):
            batch.status = "awaiting_payment"

    # -------------- القبول / الرفض الفردي --------------
    if action in ("approve", "reject"):
        if voucher_id is None:
            flash("البيانات ناقصة.", "danger")
            return redirect(url_for("admin.voucher_review"))

        voucher = Voucher.query.get_or_404(voucher_id)

        if action == "approve":
            approve_voucher(voucher)
            flash("✔ تم قبول السند وتحويله إلى مرحلة دفع العمولة.", "success")

        else:  # reject فردي
            voucher.status     = "rejected"
            voucher.admin_note = reason or "لا يوجد سبب"
            flash("✖ تم رفض السند.", "warning")

    # -------------- القبول / الرفض الجماعي --------------
    elif action in ("approve_bulk", "reject_bulk"):
        if not voucher_ids:
            flash("يرجى تحديد سند واحد على الأقل.", "warning")
            return redirect(url_for("admin.voucher_review"))

        count = 0
        for vid in voucher_ids:
            v = Voucher.query.get(vid)
            if not v:
                continue

            if action == "approve_bulk":
                approve_voucher(v)
            else:   # reject_bulk
                v.status     = "rejected"
                v.admin_note = reason or "—"

            count += 1

        flash(
            f"{'✔' if action=='approve_bulk' else '✖'} "
            f"تم {'قبول' if action=='approve_bulk' else 'رفض'} {count} سند.",
            "success" if action == "approve_bulk" else "warning"
        )

    # -------------- خطأ في الأكشن --------------
    else:
        flash("الإجراء غير معروف.", "danger")
        return redirect(url_for("admin.voucher_review"))

    db.session.commit()
    return redirect(url_for("admin.voucher_review"))




@admin_bp.route('/voucher-payment-review', methods=['GET', 'POST'])
def voucher_payment_review():
    if request.method == 'POST':
        # -------- معالجة النموذج --------
        voucher_id = request.form.get('voucher_id', type=int)
        action     = request.form.get('action')
        note       = request.form.get('note')

        voucher = Voucher.query.get_or_404(voucher_id)

        if action == 'approve':
            # ✅ توليد الفاتورة مرة واحدة إذا لم تكن موجودة
            if voucher.commission_invoice is None:
                amount = voucher.quantity * 1.0  # 1 ريال لكل كرتون (ثابت)
                pdf_url = create_commission_invoice(voucher)

                invoice = CommissionInvoice(
                    voucher_id=voucher.id,
                    amount=amount,
                    pdf_url=pdf_url,
                    created_at=datetime.utcnow()  # ← أضفها صراحة لضمان الحفظ
                )
                db.session.add(invoice)

            voucher.status       = 'approved_for_market'
            voucher.payment_note = None
            flash("تم اعتماد الإثبات وإصدار فاتورة العمولة.", "success")

        elif action == 'reject':
            voucher.status       = 'payment_rejected'
            voucher.payment_note = note
            flash("تم رفض الإثبات مع إرسال ملاحظة.", "warning")

        db.session.commit()
        return redirect(url_for('admin.voucher_payment_review'))

    # -------- العرض (GET) --------
    vouchers = Voucher.query.filter_by(status='payment_under_review').all()
    return render_template(
        'dashboard_admin/voucher_payment_review.html',
        vouchers=vouchers
    )




PER_PAGE = 5  # ✅ عدد الفواتير في كل صفحة


# routes/admin_bp.py  أو حيث يوجد all_invoices

@admin_bp.route('/commission-invoices')
@login_required
def all_invoices():
    page = max(int(request.args.get('page', 1) or 1), 1)
    batch_id = request.args.get('batch_id', type=int)

    q = (CommissionInvoice.query
         .options(
             selectinload(CommissionInvoice.voucher)
             .selectinload(Voucher.factory)
         ))

    if batch_id:
        # فلترة بالفاتورة ↠ السند ↠ الدفعة
        q = q.join(CommissionInvoice.voucher).filter(Voucher.batch_id == batch_id)

    # ترتيب ونقل الفارغ لآخر القائمة
    q = q.order_by(desc(CommissionInvoice.created_at).nullslast())

    total = q.count()
    invoices = (q
                .limit(PER_PAGE)
                .offset((page - 1) * PER_PAGE)
                .all())

    # روابط التصفح
    total_pages = max(ceil(total / PER_PAGE), 1)

    return render_template(
        'dashboard_admin/commission_invoices.html',
        invoices=invoices,
        page=page,
        total_pages=total_pages,
        per_page=PER_PAGE,
        total=total,
        batch_id=batch_id  # لإبقاء الفلترة أثناء التنقل
    )


@admin_bp.route('/batch-payment-review', methods=['GET', 'POST'])
@login_required
def batch_payment_review():
    if request.method == 'POST':
        batch_id = int(request.form['batch_id'])
        action   = request.form['action']
        note     = (request.form.get('note') or '').strip()

        # حمّل الدفعة فقط (بدون .vouchers لتجنب تحميل آلاف السجلات)
        batch = VoucherBatch.query.get_or_404(batch_id)

        # أسماء الجداول من الموديلات (تشمل السكيمة لو موجودة)
        v_tbl  = Voucher.__table__.fullname
        ci_tbl = CommissionInvoice.__table__.fullname

        if action == 'approve':
            # 1) إجمالي العمولات من SQL مباشرة (بدون لفّ على batch.vouchers)
            total_commission_value = (
                db.session.query(func.coalesce(func.sum(Voucher.quantity * 1.0), 0.0))
                .filter(Voucher.batch_id == batch.id)
                .scalar()
            ) or 0.0

            # 2) إنشاء فاتورة الدفعة (تأكّد أن الدالة لا تقرأ كل السندات)
            pdf_url, invoice_number = create_batch_commission_invoice(batch, float(total_commission_value))
            batch.invoice_url = pdf_url
            batch.status      = 'approved'

            # 3) تحديث حالة السندات دفعة واحدة
            upd_res = db.session.execute(
                text(f"""
                    UPDATE {v_tbl}
                    SET status = 'approved_for_market'
                    WHERE batch_id = :bid
                      AND status IS DISTINCT FROM 'approved_for_market'
                """),
                {"bid": batch_id}
            )

            # 4) إدراج فواتير العمولات لكل سند يفتقدها — دفعة واحدة
            # يُفضّل وجود UNIQUE(voucher_id) على جدول فواتير العمولات
            db.session.execute(
                text(f"""
                    INSERT INTO {ci_tbl} (voucher_id, amount, pdf_url, invoice_number)
                    SELECT v.id, (v.quantity * 1.0), :pdf, :inv
                    FROM {v_tbl} v
                    WHERE v.batch_id = :bid
                      AND NOT EXISTS (
                          SELECT 1 FROM {ci_tbl} ci WHERE ci.voucher_id = v.id
                      )
                """),
                {"bid": batch_id, "pdf": pdf_url, "inv": invoice_number}
            )

            flash(f"✔ تم اعتماد الدفعة وإصدار الفاتورة. تم تحديث {upd_res.rowcount} سندًا.", "success")

        elif action == 'reject':
            batch.status = 'payment_rejected'
            batch.note   = note

            upd_res = db.session.execute(
                text(f"""
                    UPDATE {v_tbl}
                    SET status = 'payment_rejected'
                    WHERE batch_id = :bid
                      AND status IS DISTINCT FROM 'payment_rejected'
                """),
                {"bid": batch_id}
            )

            flash(f"✖ تم رفض الدفعة. تم تحديث {upd_res.rowcount} سندًا.", "warning")

        db.session.commit()
        return redirect(url_for('admin.batch_payment_review'))

    # -------- GET: لا تحمل دفعات بلا حدود --------
    batches = (VoucherBatch.query
               .filter_by(status='payment_under_review')
               .order_by(VoucherBatch.id.desc())
               .limit(100)  # أو استخدم paginate
               .all())

    return render_template('dashboard_admin/batch_payment_review.html', batches=batches)


@admin_bp.route('/notify-factory', methods=['GET', 'POST'])
def notify_factory():
    form = NotifyFactoryForm()
    form.factory_id.choices = [(f.id, f.name) for f in Factory.query.order_by(Factory.name).all()]
    sent = False

    if form.validate_on_submit():
        factory = Factory.query.get(form.factory_id.data)
        
        # ✅ بدل factory.user → جلب المستخدم المرتبط بهذا المصنع
        user = User.query.filter_by(factory_id=factory.id).first()

        if not user:
            flash("لم يتم العثور على مستخدم مرتبط بهذا المصنع.", "danger")
            return render_template('dashboard_admin/notify_factory.html', form=form, sent=False)

        message_map = {
            'accepted': "تمت الموافقة على سنداتك، يمكنك الآن متابعة الحالات.",
            'payment_issued': "تم إصدار دفعة لك، تفقد حسابك البنكي.",
        }

        message = message_map.get(form.message_type.data, form.custom_message.data)
        send_email(user.email, "تنبيه من منصة جُملة", 'public/email/generic_notification.html',
                   user=user, message=message)

        sent = True

    return render_template('dashboard_admin/notify_factory.html', form=form, sent=sent)







# routes/admin/settings.py (أو ضمن ملف admin_bp)
from flask import request, redirect, url_for, flash
from app.models import GlobalSetting, db

@admin_bp.route("/toggle-auto-approve", methods=["POST"])
def toggle_auto_approve():
    setting = GlobalSetting.query.filter_by(key="auto_approve_vouchers").first()
    if not setting:
        setting = GlobalSetting(key="auto_approve_vouchers", value="true")
        db.session.add(setting)
    else:
        # قلب القيمة
        setting.value = "false" if setting.value == "true" else "true"

    db.session.commit()
    flash("تم تحديث حالة القبول التلقائي.", "success")
    return redirect(url_for("admin.voucher_review"))



# routes/admin/voucher.py
from flask import redirect, url_for, flash
from app.models import GlobalSetting, Voucher, db
from app.utils.approval import approve_voucher
from flask_login import login_required

@admin_bp.route("/auto-approve-now")
@login_required
def auto_approve_now():
    setting = GlobalSetting.query.filter_by(key="auto_approve_vouchers").first()
    if not (setting and setting.value == "true"):
        flash("⚠️ القبول التلقائي غير مفعل.", "warning")
        return redirect(url_for("admin.voucher_review"))

    # يدعم الحالتين تحسّبًا لاختلاف التسميات
    new_vouchers = (
        Voucher.query
        .filter(or_(Voucher.status == "pending_admin_review",
                    Voucher.status == "new"))
        .all()
    )

    if not new_vouchers:
        flash("لا توجد سندات بانتظار القبول.", "info")
        return redirect(url_for("admin.voucher_review"))

    for v in new_vouchers:
        approve_voucher(v)          # نفس المنطق الموحّد

    db.session.commit()
    flash(f"✔ تم قبول {len(new_vouchers)} سند تلقائيًا.", "success")
    return redirect(url_for("admin.voucher_review"))
