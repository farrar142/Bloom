from bloom import Application
from bloom.web.asgi import ASGIApplication

app = Application()
asgi = ASGIApplication(application=app, debug=True)
