from flask import Flask
from routes.lsl import lsl_blueprint
from routes.device import device_blueprint
import asyncio
from helper.api_helper import get_devices

app = Flask(__name__)

# Register the blueprints (routes)
app.register_blueprint(lsl_blueprint, url_prefix='/api/lsl')
app.register_blueprint(device_blueprint, url_prefix='/api/device')

@app.route('/', methods=['GET'])
def home():
    return {"message": "Backend is running"}

if __name__ == '__main__':
    # Perform initial device check before starting the app
    # asyncio.run(get_devices())
    app.run(debug=True, port=5000)