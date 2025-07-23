from app import create_app, db
from flask_migrate import Migrate

# إنشاء التطبيق
app = create_app()

# ربط Flask-Migrate
migrate = Migrate(app, db)

# تشغيل التطبيق
if __name__ == '__main__':
    app.run(debug=True)
