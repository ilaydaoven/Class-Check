from flask import Flask
from .auth import auth
from .views import views

def create_app():
    app = Flask(__name__)

    # Uygulama yapılandırması buraya eklenebilir

    from .views import views
    from .auth import auth

    # Blueprintler uygulamaya kaydediliyor
    app.register_blueprint(views, url_prefix='/')
    app.register_blueprint(auth, url_prefix='/auth')

    return app