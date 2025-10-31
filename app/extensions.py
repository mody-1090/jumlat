# app/extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail
from flask_login import LoginManager
from flask_wtf import CSRFProtect

db            = SQLAlchemy()
mail          = Mail()
login_manager = LoginManager()
csrf          = CSRFProtect()
