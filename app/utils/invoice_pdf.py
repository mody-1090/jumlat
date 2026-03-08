"""
invoice_pdf.py • إنشاء PDF عربي منسّق (سند توريد / فاتورة طلب) مع رفع مباشر إلى S3
ويُنشئ صفحة ثانية لوصف المنتج وصورته إن وُجدا
"""
import os
import qrcode
import boto3
import arabic_reshaper

from io import BytesIO
from urllib.parse import urlparse
from bidi.algorithm import get_display
from flask import current_app
from werkzeug.datastructures import FileStorage

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics, ttfonts
from reportlab.platypus import Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader

# أداة رفع إلى S3
from app.utils.s3_upload import upload_file_to_s3

# ───────── إعداد S3 / R2 ─────────
AWS_ACCESS_KEY = os.environ.get('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY')
AWS_BUCKET_NAME = os.environ.get('AWS_S3_BUCKET_NAME')
AWS_REGION = os.environ.get('AWS_S3_REGION', 'auto')
S3_ENDPOINT_URL = os.environ.get('S3_ENDPOINT_URL')

s3_client = boto3.client(
    "s3",
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY,
    region_name=AWS_REGION,
    endpoint_url=S3_ENDPOINT_URL,
)

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
MARGIN = 70   # ≈ 25 mm

def _draw_header(c, w, h, font):
    c.setFillColor("#ffffff")
    c.rect(0, h - 70, w, 70, fill=1, stroke=0)

    logo = os.path.join(current_app.root_path, "static", "images", "logo.png")
    if os.path.exists(logo):
        c.drawImage(logo, w - 140, h - 62, width=110, height=45, mask='auto')

    c.setFont(font, 20)
    c.setFillColor(colors.black)
    c.drawString(MARGIN, h - 50, ar("منصّة جُملة – سند توريد"))

def _draw_footer(c, w, font):
    c.setStrokeColor('#2575fc')
    c.setLineWidth(0.5)
    c.line(MARGIN, 60, w - MARGIN, 60)

    c.setFont(font, 9)
    c.setFillColor(colors.black)
    c.drawRightString(
        w - MARGIN,
        45,
        ar("للاستفسار: 0564849904  •  support@jumlat.com  •  jumlat.com")
    )

def _draw_table(c, data, y, font):
    usable_w = A4[0] - 2 * MARGIN
    tbl = Table(data, colWidths=[160, usable_w - 160])
    tbl.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.grey),
        ('BOX', (0, 0), (-1, -1), 0.4, colors.grey),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    tbl.wrapOn(c, 0, 0)
    tbl.drawOn(c, MARGIN, y)

def _wrap_ar_lines(text, max_chars=55):
    """
    تقسيم نص عربي إلى أسطر تقريبية حسب عدد الأحرف
    """
    if not text:
        return []

    words = str(text).split()
    lines = []
    current = ""

    for word in words:
        tentative = f"{current} {word}".strip()
        if len(tentative) <= max_chars:
            current = tentative
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines

def _extract_r2_key_from_url(url):
    """
    يحول الرابط العام إلى object key داخل البكت
    مثال:
    https://xxx.r2.dev/voucher-products/file.jpg
    -> voucher-products/file.jpg
    """
    if not url:
        return None

    parsed = urlparse(url)
    return parsed.path.lstrip("/")

def _download_image_to_reader(url):
    """
    تحميل الصورة مباشرة من R2 / S3 عبر boto3 بدل الرابط العام
    """
    if not url:
        return None

    try:
        object_key = _extract_r2_key_from_url(url)
        if not object_key:
            return None

        obj = s3_client.get_object(Bucket=AWS_BUCKET_NAME, Key=object_key)
        data = obj["Body"].read()

        return ImageReader(BytesIO(data))

    except Exception as e:
        current_app.logger.warning(f"تعذر تحميل صورة المنتج من R2: {e}")
        return None

def _draw_product_details_page(c, voucher, font):
    """
    صفحة ثانية فيها وصف المنتج والصورة
    """
    w, h = A4
    _draw_header(c, w, h, font)

    c.setFillColor(colors.black)
    c.setFont(font, 18)
    c.drawRightString(w - MARGIN, h - 95, ar("تفاصيل المنتج"))

    # بطاقة اسم المنتج
    c.setFillColor(colors.HexColor("#f8f9fa"))
    c.roundRect(MARGIN, h - 155, w - 2 * MARGIN, 42, 8, fill=1, stroke=0)

    c.setFillColor(colors.black)
    c.setFont(font, 13)
    c.drawRightString(w - MARGIN - 12, h - 138, ar(f"اسم المنتج: {voucher.product}"))

    current_y = h - 190

    # وصف المنتج
    if getattr(voucher, "product_description", None):
        c.setFont(font, 14)
        c.setFillColor(colors.HexColor("#2575fc"))
        c.drawRightString(w - MARGIN, current_y, ar("وصف المنتج"))
        current_y -= 24

        c.setFillColor(colors.black)
        c.setFont(font, 11)

        desc_lines = _wrap_ar_lines(voucher.product_description, max_chars=55)

        # خلفية خفيفة للوصف
        desc_box_height = max(70, len(desc_lines) * 16 + 20)
        c.setFillColor(colors.HexColor("#fcfcfc"))
        c.roundRect(
            MARGIN,
            current_y - desc_box_height + 8,
            w - 2 * MARGIN,
            desc_box_height,
            8,
            fill=1,
            stroke=1
        )

        c.setFillColor(colors.black)
        text_y = current_y - 10
        for line in desc_lines:
            c.drawRightString(w - MARGIN - 12, text_y, ar(line))
            text_y -= 16

        current_y -= (desc_box_height + 22)

    # صورة المنتج
    if getattr(voucher, "product_image_url", None):
        c.setFont(font, 14)
        c.setFillColor(colors.HexColor("#2575fc"))
        c.drawRightString(w - MARGIN, current_y, ar("صورة المنتج"))
        current_y -= 22

        img_reader = _download_image_to_reader(voucher.product_image_url)
        if img_reader:
            try:
                img_width = 260
                img_height = 220

                x = (w - img_width) / 2
                y = max(110, current_y - img_height)

                c.drawImage(
                    img_reader,
                    x,
                    y,
                    width=img_width,
                    height=img_height,
                    preserveAspectRatio=True,
                    mask='auto'
                )

                current_y = y - 20
            except Exception as e:
                current_app.logger.warning(f"تعذر رسم صورة المنتج داخل PDF: {e}")
                c.setFillColor(colors.red)
                c.setFont(font, 11)
                c.drawRightString(w - MARGIN, current_y, ar("تعذر عرض صورة المنتج داخل الملف"))
                current_y -= 18
        else:
            c.setFillColor(colors.red)
            c.setFont(font, 11)
            c.drawRightString(w - MARGIN, current_y, ar("تعذر تحميل صورة المنتج من التخزين"))
            current_y -= 18

    _draw_footer(c, w, font)

# ───────── ① توليد الملف في الذاكرة ─────────
def generate_invoice_pdf_bytes(voucher, order=None):
    """
    تُنشئ PDF (BytesIO) وتُرجِع (stream, filename)
    """
    font = _register_arabic_font()
    buf = BytesIO()
    kind = "invoice" if order else "activation"
    fname = f"{kind}_{voucher.code}.pdf"

    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4

    # ───── الصفحة الأولى ─────
    _draw_header(c, w, h, font)

    # نص أحمر رئيسي
    c.setFont(font, 16)
    c.setFillColor(colors.red)
    c.drawCentredString(w / 2, h - 90, ar(f"الطلبات في {voucher.city}"))
    c.setFillColor(colors.black)

    # جدول البيانات
    unit_price = voucher.price_per_unit
    vat_amount = unit_price * voucher.quantity * voucher.vat_rate
    total_price = voucher.total_price

    rows = [
        [ar("رقم السند"), voucher.code],
        [ar("المنتج"), ar(voucher.product)],
        [ar("الكمية"), voucher.quantity],
        [ar("سعر الوحدة"), f"{unit_price:.2f} ر.س"],
        [ar("قيمة الضريبة"), f"{vat_amount:.2f} ر.س"],
        [ar("الإجمالي شامل الضريبة"), f"{total_price:.2f} ر.س"],
    ]

    if order:
        rows += [
            [ar("اسم العميل"), ar(order.customer_name)],
            [ar("جوال العميل"), order.customer_phone]
        ]

    _draw_table(c, rows, h - 195, font)

    # تعليمات
    ins = [
        "يُستخدَم هذا السند لمرة واحدة فقط.",
        "يُرجى مراجعة تفاصيل المنتج قبل تأكيد الطلب.",
        "لإتمام الطلب: امسح رمز QR أو اضغط عليه إذا كان الملف رقميًا.",
    ]

    c.setFont(font, 10)
    y = h - 195 - 28 - len(rows) * 18
    for line in ins:
        c.drawString(MARGIN, y, ar(line))
        y -= 14

    # رمز QR
    base_url = current_app.config.get("BASE_URL", "").rstrip("/")
    qr_url = f"{base_url}/voucher/order/{voucher.code}"
    qr_img = qrcode.make(qr_url)

    c.drawInlineImage(qr_img, MARGIN, 110, width=100, height=100)
    c.linkURL(qr_url, (MARGIN, 110, MARGIN + 100, 210), relative=0)

    c.setFont(font, 9)
    c.drawString(MARGIN, 96, ar("امسح أو انقر لإتمام الطلب"))

    _draw_footer(c, w, font)
    c.showPage()

    # ───── الصفحة الثانية: وصف وصورة المنتج ─────
    has_description = bool(getattr(voucher, "product_description", None))
    has_image = bool(getattr(voucher, "product_image_url", None))

    if has_description or has_image:
        _draw_product_details_page(c, voucher, font)
        c.showPage()

    c.save()
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
