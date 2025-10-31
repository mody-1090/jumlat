"""
commission_invoice_pdf.py • إنشاء PDF لدفعة عمولات سندات (رفع مباشر إلى S3)
"""
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
import os, qrcode, arabic_reshaper, uuid, io
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics, ttfonts
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader      # ← مهم لرسم الصورة
from flask import current_app
from werkzeug.datastructures import FileStorage

from app.utils.s3_upload import upload_file_to_s3


# ───────── إعداد الخط العربي ─────────
AR_FONT_CANDIDATES = [("Cairo", "Cairo-Regular.ttf"), ("Amiri", "Amiri-Regular.ttf")]
def _register_arabic_font():
    for name, file_ in AR_FONT_CANDIDATES:
        if name in pdfmetrics.getRegisteredFontNames():
            return name
        fp = os.path.join(current_app.root_path, "static", "fonts", file_)
        if os.path.exists(fp):
            pdfmetrics.registerFont(ttfonts.TTFont(name, fp))
            return name
    raise RuntimeError("⚠️ خط عربي غير موجود في static/fonts")

def ar(text: str) -> str:
    return get_display(arabic_reshaper.reshape(str(text)))

# ───────── ثوابت شكلية ─────────
MARGIN = 70

def _draw_header(c, w, h, font):
    c.setFillColor("#ffffff")
    c.rect(0, h-70, w, 70, fill=1, stroke=0)
    logo = os.path.join(current_app.root_path, "static", "images", "logo.png")
    if os.path.exists(logo):
        c.drawImage(logo, w-140, h-62, width=110, height=45, mask='auto')
    c.setFont(font, 20); c.setFillColor(colors.white)
    c.drawString(MARGIN, h-50, ar("منصّة جُملة – فاتورة عمولة"))

def _draw_footer(c, w, font):
    c.setStrokeColor('#2575fc'); c.setLineWidth(0.5)
    c.line(MARGIN, 60, w-MARGIN, 60)
    c.setFont(font, 9)
    c.drawRightString(
        w-MARGIN, 45,
        ar("للاستفسار: -0564849904  •  support@jumlat.com  •  jumlat.com –فاتورة صادرة آليًا بواسطة منصة جُملة –")
    )

def _draw_table(c, data, y, font, col1=160):
    usable_w = A4[0] - 2*MARGIN
    tbl = Table(data, colWidths=[col1, usable_w-col1])
    tbl.setStyle(TableStyle([
        ('FONTNAME',  (0,0), (-1,-1), font),
        ('FONTSIZE',  (0,0), (-1,-1), 11),
        ('ALIGN',     (0,0), (-1,-1), 'RIGHT'),
        ('VALIGN',    (0,0), (-1,-1), 'MIDDLE'),
        ('INNERGRID', (0,0), (-1,-1), .4, colors.grey),
        ('BOX',       (0,0), (-1,-1), .4, colors.grey),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING',(0,0), (-1,-1), 6),
        ('TOPPADDING',  (0,0), (-1,-1), 4),
        ('BOTTOMPADDING',(0,0), (-1,-1), 4),
    ]))
    tbl.wrapOn(c, 0, 0); tbl.drawOn(c, MARGIN, y)

# ───────── الدالة الرئيسة ─────────
def create_batch_commission_invoice(batch, total_amount: float):
    """
    تُنشئ PDF فاتورة ضريبية جماعية وترفعها إلى S3.
    تُرجِع (رابط PDF على S3, رقم الفاتورة).
    """
    font = _register_arabic_font()
    W, H = A4

    # ─── بيانات ثابتة ───
    SELLER_NAME = "شركة محمد حسن محمد الحربي لتجارة الجملة والتجزئة"
    SELLER_CR   = "109193632"
    SELLER_VAT  = "312854007700003"

    buyer       = batch.vouchers[0].factory
    BUYER_NAME  = buyer.name
    BUYER_CR    = buyer.cr_number or "—"
    BUYER_VAT   = buyer.vat_number or "—"

    gross_total = Decimal(str(total_amount)).quantize(Decimal("0.01"))
    vat_value   = (gross_total * Decimal("15")/Decimal("115")).quantize(Decimal("0.01"), ROUND_HALF_UP)
    net_value   = (gross_total - vat_value).quantize(Decimal("0.01"))
    qty         = batch.total_quantity()

    invoice_number = f"BATCH-{batch.id}-{uuid.uuid4().hex[:6].upper()}"

    # ملف مؤقت
    fname = f"tax_invoice_batch_{batch.id}_{uuid.uuid4().hex[:6]}.pdf"
    tmp_dir = os.path.join(current_app.root_path, "tmp_invoices")
    os.makedirs(tmp_dir, exist_ok=True)
    full_path = os.path.join(tmp_dir, fname)

    c = canvas.Canvas(full_path, pagesize=A4)

    # 1) الترويسة
    header_clr = colors.HexColor("#ffffff")
    c.setFillColor(header_clr); c.rect(0, H-85, W, 85, fill=1, stroke=0)
    logo = os.path.join(current_app.root_path, "static", "images", "logo.png")
    if os.path.exists(logo):
        c.drawImage(logo, MARGIN, H-78, width=90, height=45, mask="auto")
    c.setFont(font, 22); c.setFillColor(colors.black)
    c.drawRightString(W-MARGIN, H-50, ar("فاتورة ضريبية – رسوم سندات"))
    c.setFont(font, 10)
    c.drawRightString(W-MARGIN, H-68, ar(datetime.utcnow().strftime("التاريخ: %Y-%m-%d  %H:%M")))
    c.drawString(MARGIN, H-90, ar(f"رقم : {batch.id}"))

    # بيانات الصناديق
    def box(title, l1, l2, y_top):
        h_box, w_box = 70, W-2*MARGIN
        c.rect(MARGIN, y_top-h_box, w_box, h_box, stroke=1, fill=0)
        c.setFont(font, 12); c.setFillColor(colors.black)
        c.drawRightString(W-MARGIN-10, y_top-16, ar(title))
        c.setFont(font, 11)
        c.drawRightString(W-MARGIN-10, y_top-36, ar(l1))
        c.drawRightString(W-MARGIN-10, y_top-54, ar(l2))
        return y_top-h_box-12

    y = H-110
    y = box("معلومات البائع",
            f"اسم البائع: {SELLER_NAME}",
            f"سجل تجاري: {SELLER_CR}    •    الرقم الضريبي: {SELLER_VAT}", y)
    y = box("معلومات المشتري",
            f"اسم المشتري: {BUYER_NAME}",
            f"سجل تجاري: {BUYER_CR}    •    الرقم الضريبي: {BUYER_VAT}", y)

    # جدول الرسوم
    # ═════════ 3) جدول الرسوم الضريبية ═════════
    table_y = y - 110

    tbl_data = [
        [ar("الوصف"), ar("الوحدات"), ar("سعر الوحدة"),
         ar("الصافي"), ar("ضريبة 15%"), ar("الإجمالي")],

        [ar("رسوم إصدار سندات"), qty, "1.00",
         f"{net_value}", f"{vat_value}", f"{gross_total}"]
    ]

    # مجموع الأعمدة أدناه = 430pt < 455pt (المساحة داخل الهوامش)
    col_widths = [115, 55, 65, 75, 60, 60]

    tbl = Table(tbl_data, colWidths=col_widths, rowHeights=[25, 25])
    tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font),
        ('FONTSIZE', (0, 0), (-1, -1), 11),

        ('ALIGN',    (0, 0), (-1, -1), 'CENTER'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#E8E8E8")),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.grey),
    ]))

    tbl.wrapOn(c, 0, 0)
    tbl.drawOn(c, MARGIN, table_y)

    # ═════════ 4) رمز QR (تم التعديل) ═════════
    qr_url  = "https://jumlat.com"          # لاحقًا يمكن استبداله بالرابط النهائي
    qr_img  = qrcode.make(qr_url)           # كائن PIL
    buf     = io.BytesIO()
    qr_img.save(buf, format="PNG")
    buf.seek(0)
    c.drawImage(
        ImageReader(buf),                   # يجنب خطأ .format
        W - MARGIN - 100, 180,
        width=100, height=100
    )
    c.setFont(font, 8)
    c.drawCentredString(W - MARGIN - 50, 168, ar("امسح للتحقق من الفاتورة"))

    # الملخص
    summary_y = 150
    c.setFont(font, 11)
    c.drawRightString(W - MARGIN, summary_y, ar(f"صافي العمولة: {net_value} ر.س"))
    c.drawRightString(W - MARGIN, summary_y - 18, ar(f"ضريبة القيمة المضافة (15%): {vat_value} ر.س"))
    c.setFont(font, 12)
    c.drawRightString(W - MARGIN, summary_y - 36, ar(f"الإجمالي المستحق: {gross_total} ر.س"))
    c.setFont(font, 10)
    c.drawString(MARGIN, summary_y - 36, ar(f"الحساب المحوَّل منه: {batch.account_name or '—'}"))

    _draw_footer(c, W, font)
    c.showPage(); c.save()

    # رفع إلى S3
    with open(full_path, "rb") as f:
        pdf_url = upload_file_to_s3(FileStorage(stream=f, filename=fname), folder="invoices")
    if os.path.exists(full_path):
        os.remove(full_path)

    return pdf_url, invoice_number
