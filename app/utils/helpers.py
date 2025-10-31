from flask_login import current_user
from app.models import VoucherBatch


def count_waiting_batches():
    return VoucherBatch.query.filter(
        VoucherBatch.factory_id == current_user.factory_id,
        VoucherBatch.status.in_(["awaiting_payment", "payment_rejected"])
    ).count()
