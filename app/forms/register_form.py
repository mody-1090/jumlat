from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, TelField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Optional
from app.models import User


class RegisterForm(FlaskForm):
    # ─── بيانات أساسية ───
    username = StringField('اسم المستخدم', validators=[
        DataRequired(), Length(min=3, max=64)
    ])
    email = StringField('البريد الإلكتروني', validators=[
        DataRequired(), Length(max=120)
    ])
    phone = TelField('رقم الجوال', validators=[
        DataRequired(), Length(min=4, max=20)
    ])

    password = PasswordField('كلمة المرور', validators=[
        DataRequired(), Length(min=6),
        EqualTo('confirm', message='التأكيد غير مطابق')
    ])
    confirm = PasswordField('تأكيد كلمة المرور', validators=[DataRequired()])

    role = SelectField('نوع الحساب', choices=[
        ('factory', 'مصنع'), ('promoter', 'مروج / تاجر جملة')
    ], validators=[DataRequired()])

    # ─── حقول المصنع ─── (ليست مطلوبة مبدئيًا)
    factory_name    = StringField('اسم المصنع',       validators=[Optional(), Length(max=128)])
    factory_contact = StringField('اسم ضابط الاتصال',  validators=[Optional(), Length(max=128)])
    factory_phone   = TelField('جوال ضابط الاتصال',    validators=[Optional(), Length(max=20)])
    cr_number       = StringField('السجل التجاري',     validators=[Optional(), Length(max=30)])
    vat_number      = StringField('الرقم الضريبي',     validators=[Optional(), Length(max=30)])

    # ─── حقول المروّج ───
    account_holder_name = StringField('اسم صاحب الحساب البنكي', validators=[Optional(), Length(max=100)])
    bank_name           = StringField('اسم البنك',               validators=[Optional(), Length(max=100)])
    iban                = StringField('رقم الآيبان',             validators=[Optional(), Length(min=15, max=34)])

    submit = SubmitField('إنشاء الحساب')

    # --- تحقّق التكرار ---
    def validate_username(self, field):
        if User.query.filter_by(username=field.data).first():
            raise ValidationError('اسم المستخدم مسجّل بالفعل.')

    def validate_email(self, field):
        if User.query.filter_by(email=field.data).first():
            raise ValidationError('البريد مسجّل بالفعل.')

    # --- تحقّق ديناميكي بحسب الدور ---
    def validate(self, extra_validators=None):
        rv = super().validate(extra_validators=extra_validators)
        if not rv:
            return False

        if self.role.data == 'factory':
            required = [
                self.factory_name, self.factory_contact, self.factory_phone,
                self.cr_number, self.vat_number
            ]
            for f in required:
                if not f.data:
                    f.errors.append('هذا الحقل مطلوب للمصنع.')
                    return False

        elif self.role.data == 'promoter':
            required = [
                self.account_holder_name, self.bank_name, self.iban
            ]
            for f in required:
                if not f.data:
                    f.errors.append('هذا الحقل مطلوب للمروّج.')
                    return False

        return True
