"""
invoice_pdf.py • إنشاء PDF عربي منسّق (سند توريد / فاتورة طلب) مع رفع مباشر إلى S3
"""
import os, qrcode, arabic_reshaper
from io                     import BytesIO
from bidi.algorithm         import get_display
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen        import canvas
from reportlab.pdfbase       import pdfmetrics, ttfonts
from reportlab.platypus      import Table, TableStyle
from reportlab.lib           import colors
from flask                   import current_app
from werkzeug.datastructures import FileStorage

# أداة رفع إلى S3
from app.utils.s3_upload import upload_file_to_s3

# ───────── إعداد الخط العربي ─────────
AR_FONT_CANDIDATES = [
    ("Cairo", "Cairo-Regular.ttf"),
    ("Amiri", "Amiri-Regular.ttf"),
]

def _register_arabic_font():
    for name, file_ in AR_FONT_CANDIDATES:
        if name in pdfmetrics.getRegisteredFontNames():
            return name
        fp = os.path.join(current_app.root_path, "static", "fonts", file_)
        if os.path.exists(fp):
            pdfmetrics.registerFont(ttfonts.TTFont(name, fp))
            return name
    raise RuntimeError("⚠️ لم يُعثر على خط عربي في static/fonts")

def ar(txt: str) -> str:
    return get_display(arabic_reshaper.reshape(str(txt)))

# ───────── عناصر المظهر ─────────
MARGIN = 70   # ≈ 25 mm
def _draw_header(c, w, h, font):
    c.setFillColor("#ffffff"); c.rect(0, h-70, w, 70, fill=1, stroke=0)
    logo = os.path.join(current_app.root_path, "static", "images", "logo.png")
    c.drawImage(logo, w-140, h-62, width=110, height=45, mask='auto')
    c.setFont(font, 20); c.setFillColor(colors.black)
    c.drawString(MARGIN, h-50, ar("منصّة جُملة – سند توريد"))

def _draw_footer(c, w, font):
    c.setStrokeColor('#2575fc'); c.setLineWidth(0.5)
    c.line(MARGIN, 60, w-MARGIN, 60)
    c.setFont(font, 9); c.setFillColor(colors.black)
    c.drawRightString(w-MARGIN, 45,
        ar("للاستفسار: 0564849904  •  support@jumlat.com  •  jumlat.com"))

def _draw_table(c, data, y, font):
    usable_w = A4[0] - 2*MARGIN
    tbl = Table(data, colWidths=[160, usable_w-160])
    tbl.setStyle(TableStyle([
        ('FONTNAME',(0,0),(-1,-1),font), ('FONTSIZE',(0,0),(-1,-1),12),
        ('ALIGN',(0,0),(-1,-1),'RIGHT'), ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('INNERGRID',(0,0),(-1,-1),0.4,colors.grey),
        ('BOX',(0,0),(-1,-1),0.4,colors.grey),
        ('LEFTPADDING',(0,0),(-1,-1),6),  ('RIGHTPADDING',(0,0),(-1,-1),6),
        ('TOPPADDING',(0,0),(-1,-1),4),   ('BOTTOMPADDING',(0,0),(-1,-1),4),
    ]))
    tbl.wrapOn(c, 0, 0); tbl.drawOn(c, MARGIN, y)

# ───────── ① توليد الملف في الذاكرة ─────────
def generate_invoice_pdf_bytes(voucher, order=None):
    """
    تُنشئ PDF (BytesIO) وتُرجِع (stream, filename)
    """
    font  = _register_arabic_font()
    buf   = BytesIO()
    kind  = "invoice" if order else "activation"
    fname = f"{kind}_{voucher.code}.pdf"

    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    _draw_header(c, w, h, font)

    # نص أحمر رئيسي
    c.setFont(font, 16); c.setFillColor(colors.red)
    c.drawCentredString(w/2, h-90, ar(f"الطلبات في {voucher.city}"))
    c.setFillColor(colors.black)

    # جدول البيانات
    unit_price  = voucher.price_per_unit
    vat_amount  = unit_price * voucher.quantity * voucher.vat_rate
    total_price = voucher.total_price
    rows = [
        [ar("رقم السند"),             voucher.code],
        [ar("المنتج"),                ar(voucher.product)],
        [ar("الكمية"),                voucher.quantity],
        [ar("سعر الوحدة"),            f"{unit_price:.2f} ر.س"],
        [ar("قيمة الضريبة"),          f"{vat_amount:.2f} ر.س"],
        [ar("الإجمالي شامل الضريبة"),  f"{total_price:.2f} ر.س"],
    ]
    if order:
        rows += [[ar("اسم العميل"),  ar(order.customer_name)],
                 [ar("جوال العميل"), order.customer_phone]]
    _draw_table(c, rows, h-195, font)

    # تعليمات
    ins = [
      "يُستخدَم هذا السند لمرة واحدة فقط ولا يحتاج لدفعات مسبقة.",
      "جميع الطلبات تُشحن بنظام الدفع عند الاستلام (COD).",
      "لتفعيل السند: امسح رمز QR، أو اضغط عليه إذا كان الملف رقميًّا.",
    ]
    c.setFont(font, 10); y = h-195 - 28 - len(rows)*18
    for line in ins:
        c.drawString(MARGIN, y, ar(line)); y -= 14

    # رمز QR
    base_url = current_app.config.get("BASE_URL", "").rstrip("/")
    qr_url   = f"{base_url}/voucher/order/{voucher.code}"
    qr_img   = qrcode.make(qr_url)
    c.drawInlineImage(qr_img, MARGIN, 110, width=100, height=100)
    c.linkURL(qr_url, (MARGIN,110,MARGIN+100,210), relative=0)
    c.setFont(font, 9); c.drawString(MARGIN, 96, ar("امسح أو انقر لإتمام الطلب"))

    _draw_footer(c, w, font)
    c.showPage(); c.save()

    buf.seek(0)
    return buf, fname

# ───────── ② توليد + رفع إلى S3 ─────────
def create_invoice_pdf(voucher, order=None):
    """
    تُنشئ الملف في الذاكرة ثم ترفعه مباشرةً إلى S3.
    تُرجِع رابط الـ PDF (سحابي).
    """
    pdf_buf, filename = generate_invoice_pdf_bytes(voucher, order)
    wrapped = FileStorage(stream=pdf_buf, filename=filename)
    return upload_file_to_s3(wrapped, folder="pdfs")
