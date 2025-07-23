from app import create_app, db
from app.models import Voucher, Promoter

app = create_app()

with app.app_context():
    fixed = 0
    vouchers = Voucher.query.filter(Voucher.promoter_id != None).all()

    for v in vouchers:
        # نحاول إيجاد المروج الذي يكون user_id == promoter_id الموجود في السند (المربوط خطأ)
        promoter = Promoter.query.filter_by(user_id=v.promoter_id).first()
        if promoter:
            v.promoter_id = promoter.id
            fixed += 1

    db.session.commit()
    print(f"✅ تم تصحيح {fixed} سند كان مربوطًا بـ User.id بدل Promoter.id.")
