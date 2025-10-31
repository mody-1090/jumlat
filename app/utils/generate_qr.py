import io
import qrcode
import os
from flask import current_app

from app.utils.s3_upload import upload_file_to_s3

def generate_qr_code(code: str) -> str:
    """
    توليد صورة QR للـ code ورفعها إلى S3.
    تُعيد رابط S3 الكامل (URL).
    """
    # إنشاء صورة QR
    img = qrcode.make(code)

    # تحويل الصورة إلى ملف مؤقت داخل الذاكرة
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    buffer.name = f"{code}.png"  # مهم لاستخراج الاسم في s3_utils

    # رفع إلى S3 داخل مجلد "qr"
    qr_url = upload_file_to_s3(buffer, folder="qr")

    return qr_url
