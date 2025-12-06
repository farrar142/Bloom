from bloom import Application

application = Application("demo-app").auto_scan()

# ASGI 앱 (uvicorn용)
asgi_app = application.asgi
