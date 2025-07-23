# app/forms/reset_password_form.py
from flask_wtf import FlaskForm
from wtforms import PasswordField, SubmitField
from wtforms.validators import DataRequired, EqualTo, Length

class ResetPasswordForm(FlaskForm):
    password = PasswordField('كلمة المرور الجديدة', validators=[
        DataRequired(), Length(min=6)
    ])
    password_confirm = PasswordField('تأكيد كلمة المرور', validators=[
        DataRequired(), EqualTo('password', message='كلمة المرور غير متطابقة')
    ])
    submit = SubmitField('حفظ')
