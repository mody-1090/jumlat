# app/routes/public.py
import os
from flask import (
    Blueprint, render_template, redirect, url_for,
    flash, request, send_from_directory, current_app
)
from flask_login import current_user, login_required
from app import db
from app.models import Promoter, Voucher, Order, Earning, OrderPayment
from app.utils.invoice_pdf import create_invoice_pdf

public_bp = Blueprint('public', __name__, template_folder='templates/public')

# ───────────────────── الصفحات العامة ──────────────────────
@public_bp.route('/')
def index():
    vouchers = Voucher.query.filter_by(status='approved_for_market').all()
    return render_template(
        'public/index.html',
        latest_articles=[],
        vouchers=vouchers
    )


@public_bp.route('/about')
def about():
    return render_template('public/about.html')

@public_bp.route('/contact')
def contact():
    return render_template('public/contact.html')

# ───────────────────── سوق السندات (NEW) ───────────────────
@public_bp.route('/market')
@login_required
def market():
    vouchers = Voucher.query.filter_by(status='approved_for_market').all()
    return render_template('public/market.html', vouchers=vouchers)

# ─────────── التفعيل الثاني: إنشاء الطلب النهائى للجمهور ───────────
@public_bp.route('/voucher/order/<code>', methods=['GET', 'POST'])
def confirm_order(code):
    voucher = Voucher.query.filter_by(code=code).first_or_404()

    # إذا كان السند مُستخدَمًا بالفعل ➜ وجِّه لصفحة التتبّع
    if voucher.status == 'used':
        order = Order.query.filter_by(voucher_id=voucher.id).first()
        if order:
            return redirect(url_for('public.order_status', token=order.tracking_token))

        flash('لم يُعثر على طلب مرتبط بهذا السند.', 'warning')
        return redirect(url_for('public.market'))

    if voucher.status != 'active':
        flash('هذا السند غير مفعّل أو تم استخدامه.', 'warning')
        return redirect(url_for('public.market'))

    if request.method == 'POST':
        # === تجميع البيانات من النموذج =================================
        cust_name      = request.form.get('customer_name', '').strip()
        cust_phone     = request.form.get('customer_phone', '').strip()
        shop_name      = request.form.get('shop_name', '').strip()

        address_detail = request.form.get('address_detail', '').strip()
        maps_link      = request.form.get('maps_link', '').strip()

        cr_number      = request.form.get('cr_number', '').strip()
        vat_number     = request.form.get('vat_number', '').strip()
        preferred_time = request.form.get('preferred_time', '').strip()
        notes          = request.form.get('notes', '').strip()

        # ملف الإيصال
        receipt_file = request.files.get('payment_receipt')

        # === التحقق من الحقول الإلزامية ================================
        if not cust_name or not cust_phone or not shop_name:
            flash('❌ يجب إدخال الاسم والجوال واسم المحل.', 'danger')
            return redirect(url_for('public.confirm_order', code=code))

        if not address_detail and not maps_link:
            flash('❌ يرجى إدخال العنوان التفصيلي أو رابط Google Maps.', 'danger')
            return redirect(url_for('public.confirm_order', code=code))

        if not cr_number or not vat_number or not preferred_time:
            flash('❌ جميع الحقول المطلوبة يجب تعبئتها.', 'danger')
            return redirect(url_for('public.confirm_order', code=code))

        if not receipt_file or not receipt_file.filename:
            flash('❌ يجب رفع إيصال التحويل.', 'danger')
            return redirect(url_for('public.confirm_order', code=code))

        try:
            # === رفع الإيصال إلى Firebase ==============================
            # بدّل اسم الدالة التالية إلى اسم دالتك الفعلي
            receipt_url = upload_to_firebase(receipt_file)

            if not receipt_url:
                flash('❌ تعذر رفع إيصال التحويل.', 'danger')
                return redirect(url_for('public.confirm_order', code=code))

            # === إنشاء سجل الطلب وربط المروّج =========================
            order = Order(
                voucher_id     = voucher.id,
                promoter_id    = voucher.promoter_id,
                quantity       = voucher.quantity,
                customer_name  = cust_name,
                customer_phone = cust_phone,
                shop_name      = shop_name,
                city           = 'الرياض',
                address_detail = address_detail or None,
                maps_link      = maps_link or None,
                cr_number      = cr_number,
                vat_number     = vat_number,
                preferred_time = preferred_time,
                notes          = notes,
                status         = 'new'
            )
            db.session.add(order)
            db.session.flush()   # مهم للحصول على order.id

            # === إنشاء سجل الدفع ======================================
            payment = OrderPayment(
                order_id        = order.id,
                payment_method  = 'bank_transfer',
                receipt_url     = receipt_url,
                status          = 'uploaded'
            )
            db.session.add(payment)

            # === تحديث السند إلى USED ================================
            voucher.status = 'used'

            # === تسجيل عمولة المروّج (سجل تتبعي) =====================
            db.session.add(Earning(
                voucher_id      = voucher.id,
                promoter_id     = voucher.promoter_id,
                promoter_amount = voucher.factory_commission,
                factory_amount  = 0.0
            ))

            db.session.commit()

            # === إضافة رابط التتبّع العام ============================
            track_url = url_for('public.order_status', token=order.tracking_token, _external=True)
            flash('✅ تم تسجيل الطلب ورفع الإيصال بنجاح.', 'success')
            flash(f'رابط متابعة الطلب: {track_url}', 'info')

            return redirect(track_url)

        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Error while creating order with payment receipt")
            flash('❌ حدث خطأ أثناء تسجيل الطلب أو رفع الإيصال.', 'danger')
            return redirect(url_for('public.confirm_order', code=code))

    return render_template('public/confirm_order.html', voucher=voucher)

# ───────────────────── تحميل / معاينة PDF ───────────────────
@public_bp.route('/voucher/invoice/<code>')
@login_required
def download_invoice(code):
    voucher = Voucher.query.filter_by(code=code).first_or_404()

    if not voucher.invoice_path:
        flash('لم يتم توليد الفاتورة بعد.', 'warning')
        return redirect(url_for('public.voucher_details', code=code))

    pdf_dir  = current_app.config['PDF_FOLDER']
    filename = os.path.basename(voucher.invoice_path)
    return send_from_directory(pdf_dir, filename, as_attachment=True)





@public_bp.route('/voucher/thanks/<code>')
def order_thanks(code):
    voucher = Voucher.query.filter_by(code=code).first_or_404()
    if voucher.status != 'used':
        flash('لم يُنشأ طلب لهذا السند بعد.', 'warning')
        return redirect(url_for('public.market'))
    return render_template('public/order_thanks.html', voucher=voucher)


@public_bp.route('/order/<token>')
def order_status(token):
    order = Order.query.filter_by(tracking_token=token).first_or_404()
    return render_template('public/order_status.html', order=order)



@public_bp.route("/terms")
def terms():
    return render_template("public/terms.html")

@public_bp.route("/privacy")
def privacy():
    return render_template("public/privacy.html")
