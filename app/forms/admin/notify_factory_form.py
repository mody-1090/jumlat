# forms/admin/notify_factory_form.py
from flask_wtf import FlaskForm
from wtforms import SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired

class NotifyFactoryForm(FlaskForm):
    factory_id = SelectField('اختر المصنع', coerce=int, validators=[DataRequired()])

    message_type = SelectField('نوع التنبيه', choices=[
        ('accepted', 'الموافقة على السندات'),
        ('payment_issued', 'إصدار دفعة'),
        ('custom', 'رسالة مخصصة')
    ], validators=[DataRequired()])

    custom_message = TextAreaField('رسالة مخصصة (اختياري)')

    submit = SubmitField('إرسال التنبيه')
