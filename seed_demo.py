# seed_demo.py
"""
زرع حسابات تجريبية:
    admin      / admin123       (مدير)
    factory1   / factory123     (مصنع)
    promoter1  / promoter123    (مروّج)

يشغَّل مرّة واحدة:
    $ python seed_demo.py
"""

from app import create_app, db
from app.models import User, Factory, Promoter


def seed_demo_users():
    """ينشئ الحسابات إذا كانت غير موجودة ويتأكد من تفعيلها."""

    # 1) مدير (admin)
    if not User.query.filter_by(username="admin").first():
        admin = User(
            username="admin",
            email="admin@demo.sa",
            phone="0500000001",
            role="admin",
            is_verified=True,
        )
        admin.password = "admin123"
        db.session.add(admin)

    # 2) مصنع + مستخدمه (factory1)
    if not User.query.filter_by(username="factory1").first():
        factory = Factory(
            name="مصنع تجريبي",
            contact_person="أحمد",
            contact_phone="0500000000",
            commission_rate=1.0,
            cr_number="1234567890",
            vat_number="3000000000",
        )
        db.session.add(factory)
        db.session.flush()  # للحصول على factory.id

        factory_user = User(
            username="factory1",
            email="factory1@demo.sa",
            phone="0500000002",
            role="factory",
            factory_id=factory.id,
            is_verified=True,
        )
        factory_user.password = "factory123"
        db.session.add(factory_user)

    # 3) مروّج + Promoter مرتبط (promoter1)
    if not User.query.filter_by(username="promoter1").first():
        promoter_user = User(
            username="promoter1",
            email="promoter1@demo.sa",
            phone="0500000003",
            role="promoter",
            is_verified=True,
        )
        promoter_user.password = "promoter123"
        db.session.add(promoter_user)
        db.session.flush()

        promoter = Promoter(
            name="خالد",
            user_id=promoter_user.id,
            account_holder_name="خالد بن عبدالله",
            bank_name="مصرف الراجحي",
            iban="SA0000000000000000000000",
        )
        db.session.add(promoter)

    db.session.commit()
    print("✅ تمت زراعة الحسابات التجريبية بنجاح.")


if __name__ == "__main__":
    app = create_app()  # يهيّئ الامتدادات
    with app.app_context():     # ← السياق مطلوب لعمليات الـ DB
        seed_demo_users()
