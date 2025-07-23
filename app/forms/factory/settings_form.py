from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Optional, Length

class FactorySettingsForm(FlaskForm):
    name            = StringField("اسم المصنع",       validators=[DataRequired(), Length(max=120)])
    contact_person  = StringField("اسم الشخص المسؤول", validators=[Optional(), Length(max=100)])
    contact_phone   = StringField("رقم التواصل",       validators=[Optional(), Length(max=20)])
    cr_number       = StringField("السجل التجاري",     validators=[Optional(), Length(max=30)])
    vat_number      = StringField("الرقم الضريبي",     validators=[Optional(), Length(max=30)])

    submit          = SubmitField("💾 حفظ التعديلات")
