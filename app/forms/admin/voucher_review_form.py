# forms/admin/voucher_review_form.py
from flask_wtf import FlaskForm
from wtforms import HiddenField, StringField
from wtforms.validators import DataRequired

class VoucherReviewForm(FlaskForm):
    voucher_id = HiddenField(validators=[DataRequired()])
    action = HiddenField(validators=[DataRequired()])
    reason = StringField("سبب الرفض")
