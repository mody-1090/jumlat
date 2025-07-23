# app/utils/approval.py
from app.models import Voucher, VoucherBatch, db

def approve_voucher(voucher: Voucher):
    voucher.status = "awaiting_payment"

    # 1) إنشاء أو ربط الدفعة
    if voucher.batch_id is None:
        batch = (
            VoucherBatch.query
            .filter_by(factory_id=voucher.factory_id,
                       product=voucher.product,
                       status="under_review")
            .first()
        )
        if batch is None:
            batch = VoucherBatch(
                factory_id=voucher.factory_id,
                product=voucher.product,
                status="under_review"
            )
            db.session.add(batch)
            db.session.flush()

        voucher.batch_id = batch.id

    # 2) ترقية الدفعة إن اكتملت
    batch = voucher.batch
    if batch and all(x.status == "awaiting_payment" for x in batch.vouchers):
        batch.status = "awaiting_payment"
