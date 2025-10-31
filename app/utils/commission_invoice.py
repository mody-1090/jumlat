"""
Commission‑Invoice PDF generator | app/utils/commission_invoice_pdf.py
فاتورة عمولة ضريبية – رفع مباشر إلى S3
"""
import os, uuid, qrcode, arabic_reshaper, io
from decimal   import Decimal, ROUND_HALF_UP
from datetime  import datetime
from bidi.algorithm import get_display
from reportlab.pdfgen      import canvas
from reportlab.pdfbase     import pdfmetrics, ttfonts
from reportlab.lib.pagesizes import A4
from reportlab.platypus    import Table, TableStyle
from reportlab.lib         import colors
from reportlab.lib.utils   import ImageReader          # ← لرسم الـ QR
from flask                 import current_app
from werkzeug.datastructures import FileStorage

from app.utils.s3_upload import upload_file_to_s3


# ───────── أدوات عربية ─────────
def _register_font() -> str:
    fp = os.path.join(current_app.root_path, "static", "fonts", "Amiri-Regular.ttf")
    if "Amiri" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(ttfonts.TTFont("Amiri", fp))
    return "Amiri"

def ar(txt: str) -> str:
    return get_display(arabic_reshaper.reshape(str(txt)))

# ───────── الدالة الرئيسة ─────────
def create_commission_invoice(voucher):
    font = _register_font()
    W, H = A4
    M    = 65                   # الهامش

    # ─── بيانات ثابتة ───
    SELLER_NAME = "شركة محمد محمد حسن محمد الحربي لتجارة الجملة والتجزئة"
    SELLER_CR   = "109193632"
    SELLER_VAT  = "312854007700003"

    buyer       = voucher.factory
    BUYER_NAME  = buyer.name
    BUYER_CR    = buyer.cr_number or "—"
    BUYER_VAT   = buyer.vat_number or "—"

    qty         = voucher.quantity or 0
    gross_total = Decimal(qty) * Decimal("1.00")
    vat_value   = (gross_total * Decimal("15")/Decimal("115")).quantize(Decimal("0.01"), ROUND_HALF_UP)
    net_value   = (gross_total - vat_value).quantize(Decimal("0.01"))

    # اسم الملف المؤقت
    fname     = f"tax_invoice_{voucher.code}_{uuid.uuid4().hex[:6]}.pdf"
    tmp_dir   = os.path.join(current_app.root_path, "tmp_invoices")
    os.makedirs(tmp_dir, exist_ok=True)
    full_path = os.path.join(tmp_dir, fname)

    c = canvas.Canvas(full_path, pagesize=A4)

    # ═════════ 1) الترويسة ═════════
    header_clr = colors.HexColor("#2575fc")
    c.setFillColor(header_clr); c.rect(0, H-85, W, 85, fill=1, stroke=0)
    c.setFont(font, 22); c.setFillColor(colors.white)
    c.drawRightString(W-M, H-50, ar("فاتورة ضريبية"))
    c.setFont(font, 10)
    c.drawRightString(W-M, H-68, ar(datetime.utcnow().strftime("التاريخ: %Y-%m-%d  %H:%M")))
    c.drawString(M, H-68, ar(f"رقم السند: {voucher.code}"))

    logo = os.path.join(current_app.root_path, "static", "images", "company_logo.png")
    if os.path.exists(logo):
        c.drawImage(logo, M, H-78, width=90, height=45, mask="auto")

    # أداة صندوق RTL
    def box(title, l1, l2, y_top):
        h = 70; w = W-2*M
        c.rect(M, y_top-h, w, h, stroke=1, fill=0)
        c.setFont(font, 12); c.drawRightString(W-M-10, y_top-16, ar(title))
        c.setFont(font, 11)
        c.drawRightString(W-M-10, y_top-36, ar(l1))
        c.drawRightString(W-M-10, y_top-54, ar(l2))
        return y_top-h-12

    y = H-110
    y = box("معلومات البائع",
            f"اسم البائع: {SELLER_NAME}",
            f"سجل تجاري: {SELLER_CR}    •    الرقم الضريبي: {SELLER_VAT}", y)
    y = box("معلومات المشتري",
            f"اسم المشتري: {BUYER_NAME}",
            f"سجل تجاري: {BUYER_CR}    •    الرقم الضريبي: {BUYER_VAT}", y)

    # ═════════ 2) جدول الرسوم ═════════
    table_y = y - 110
    tbl_data = [
        [ar("الوصف"), ar("الكمية"), ar("سعر الوحدة"),
         ar("الصافي"), ar("ضريبة 15%"), ar("الإجمالي")],
        [ar("رسوم إصدار سند"), qty, "1.00",
         f"{net_value}", f"{vat_value}", f"{gross_total}"]
    ]
    # الأبعاد = 430pt داخل الهوامش (≤ W‑2M ≈ 465pt)
    col_w = [115, 55, 65, 75, 60, 60]
    tbl = Table(tbl_data, colWidths=col_w, rowHeights=[25,25])
    tbl.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), font),
        ('FONTSIZE', (0,0), (-1,-1), 11),
        ('ALIGN',    (0,0), (-1,-1), 'CENTER'),
        ('BACKGROUND',(0,0),(-1,0), colors.HexColor("#E8E8E8")),
        ('GRID', (0,0), (-1,-1), 0.4, colors.grey),
    ]))
    tbl.wrapOn(c, 0, 0); tbl.drawOn(c, M, table_y)

    # ═════════ 3) رمز QR (إصلاح) ═════════
    qr_url = f"{current_app.config.get('BASE_URL','').rstrip('/')}/voucher/{voucher.code}"
    qr_img = qrcode.make(qr_url)
    buf    = io.BytesIO()
    qr_img.save(buf, format="PNG"); buf.seek(0)

    c.drawImage(
        ImageReader(buf),           # يجنب AttributeError / OSError
        M, 120,
        width=95, height=95
    )
    c.setFont(font, 8)
    c.drawRightString(M + 95, 110, ar("امسح للتحقق من الفاتورة"))

    # ═════════ 4) الملخّص ═════════
    c.setFont(font, 11)
    c.drawRightString(W-M, 100, ar(f"صافي العمولة: {net_value} ر.س"))
    c.drawRightString(W-M, 80, ar(f"ضريبة القيمة المضافة (15%): {vat_value} ر.س"))
    c.setFont(font, 12)
    c.drawRightString(W-M, 58, ar(f"الإجمالي المستحق: {gross_total} ر.س"))
    c.setFont(font, 10)
    c.drawString(M, 58, ar(f"الحساب المحوَّل منه: {voucher.payment_account_name or '—'}"))

    # ═════════ 5) التذييل ═════════
    c.setStrokeColor(header_clr); c.setLineWidth(0.4)
    c.line(M, 40, W-M, 40)
    c.setFont(font, 9); c.setFillColor(colors.grey)
    c.drawCentredString(W/2, 28, ar("فاتورة صادرة آليًا بواسطة منصة جُملة – jumla.sa"))

    c.showPage(); c.save()

    # ═════════ رفع إلى S3 ═════════
    try:
        with open(full_path, "rb") as f:
            pdf_url = upload_file_to_s3(FileStorage(stream=f, filename=fname), folder="invoices")
    finally:
        if os.path.exists(full_path):
            os.remove(full_path)

    return pdf_url
