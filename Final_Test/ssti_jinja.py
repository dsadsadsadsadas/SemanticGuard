from flask import Flask, request
from jinja2 import Template
app = Flask(__name__)
@app.route('/hello')
def hello():
    name = request.args.get('name', 'World')
    # VULNERABLE: SSTI rendering raw string containing user input
    template = Template(f"Hello {name}!") 
    return template.render()
