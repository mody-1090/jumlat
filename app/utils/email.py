# utils/email.py
from datetime import datetime                    # ← جديد
from flask import render_template, current_app
from flask_mail import Message
from app.extensions import mail


def send_email(to, subject, template, **context):
    """
    يرسل رسالة بريد HTML مع نسخة نصية بديلة.
    - template: مسار قالب Jinja2 (HTML)
    - **context: المتغيرات الممرَّرة إلى القالب
    """
    # ✨ أضف now() إلى السياق إذا لم يُمرَّر
    context.setdefault('now', datetime.utcnow)    # ← السطر المطلوب

    # 1) تجهيز HTML و Plain
    html_body = render_template(template, **context)

    # إذا وُجد قالب .txt موازي
    text_template = template.replace('.html', '.txt')
    try:
        current_app.jinja_env.get_source(current_app.jinja_env, text_template)
        text_body = render_template(text_template, **context)
    except Exception:
        text_body = None

    # 2) إنشاء الرسالة
    msg = Message(
        subject    = subject,
        recipients = [to],
        sender     = current_app.config.get('MAIL_DEFAULT_SENDER', 'no-reply@jumlat.com'),
        html       = html_body,
        body       = text_body or 'يرجى استخدام عميل بريد يدعم HTML'
    )

    # 3) الإرسال
    mail.send(msg)
