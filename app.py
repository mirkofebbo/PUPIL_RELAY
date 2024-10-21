from flask import Flask
from routes.lsl import lsl_blueprint

app = Flask(__name__)

# Register the blueprints (routes)
app.register_blueprint(lsl_blueprint, url_prefix='/api/lsl')

@app.route('/', methods=['GET'])
def home():
    return {"message": "Backend is running"}

if __name__ == '__main__':
    app.run(debug=True, port=5000)