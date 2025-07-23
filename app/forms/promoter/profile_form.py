# forms/promoter/profile_form.py

from flask_wtf import FlaskForm
from wtforms import StringField
from wtforms.validators import DataRequired, Length

class PromoterProfileForm(FlaskForm):
    account_holder_name = StringField('الاسم مطابق للحساب البنكي', validators=[DataRequired(), Length(max=100)])
    bank_name = StringField('اسم البنك', validators=[Length(max=100)])
    iban = StringField('رقم الآيبان', validators=[Length(max=24)])
