# API Server (CONTEXT DRIFT: Using Flask)
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/api/users', methods=['POST'])
def create_user():
    data = request.json
    return jsonify({"status": "created"})

if __name__ == '__main__':
    app.run(debug=True)
