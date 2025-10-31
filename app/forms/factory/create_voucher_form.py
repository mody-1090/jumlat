from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, FloatField, SubmitField, SelectField
from wtforms.validators import DataRequired, NumberRange

class VoucherForm(FlaskForm):
    # ── اسم المنتج ──────────────────────────────────────────
    product = StringField(
        'اسم المنتج',
        validators=[DataRequired(message='يرجى إدخال اسم المنتج')]
    )

    # ── الكمية لكل سند ─────────────────────────────────────
    quantity = IntegerField(
        'الكمية لكل سند',
        validators=[
            DataRequired(message='الكمية مطلوبة'),
            NumberRange(min=1, message='الكمية يجب أن تكون 1 على الأقل')
        ]
    )

    # ── عدد السندات المراد إصدارها ─────────────────────────
    count = IntegerField(
        'عدد السندات',
        validators=[
            DataRequired(message='عدد السندات مطلوب'),
            NumberRange(min=1, message='العدد يجب أن يكون 1 على الأقل')
        ]
    )

    # ── عمولة المروج على كل وحدة ───────────────────────────
    commission_per = FloatField(
        'عمولة المروج لكل وحدة',
        validators=[
            DataRequired(message='يرجى إدخال قيمة العمولة'),
            NumberRange(min=0, message='العمولة لا يمكن أن تكون سالبة')
        ]
    )

    # ── سعر المصنع للوحدة ──────────────────────────────────
    price_per_unit = FloatField(
        'سعر الوحدة',
        validators=[
            DataRequired(message='يرجى إدخال سعر الوحدة'),
            NumberRange(min=0, message='السعر لا يمكن أن يكون سالبًا')
        ]
    )

    # ── نسبة الضريبة المضافة (ثابتة 15%) ───────────────────
    vat_rate = FloatField(
        'نسبة الضريبة',
        default=00.15,  # كنسبة مئوية
        validators=[
            NumberRange(min=0, message='النسبة لا يمكن أن تكون سالبة')
        ]
    )

    # ── مدينة السند ─────────────────────────────────────────
    city = SelectField(
        'مدينة السند',
        choices=[('الرياض', 'الرياض')],
        default='الرياض',
        validators=[DataRequired()]
    )

    # ── زر الإرسال ──────────────────────────────────────────
    submit = SubmitField('إصدار السندات')
