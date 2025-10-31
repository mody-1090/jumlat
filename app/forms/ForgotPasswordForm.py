# app/forms/forgot_password_form.py
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length

class ForgotPasswordForm(FlaskForm):
    email  = StringField('البريد الإلكتروني', validators=[
        DataRequired(), Email(), Length(max=120)
    ])
    submit = SubmitField('إرسال الرابط')
