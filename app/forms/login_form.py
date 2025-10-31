# forms/login_form.py
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length

class LoginForm(FlaskForm):
    email = StringField('البريد الإلكتروني', validators=[
        DataRequired(), Length(max=120)
    ])
    password = PasswordField('كلمة المرور', validators=[
        DataRequired(), Length(min=6)
    ])
    submit = SubmitField('دخول')
