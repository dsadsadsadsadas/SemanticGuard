from flask import Flask, request, render_template_string
app = Flask(__name__)
@app.route('/hello')
def hello():
    name = request.args.get('name', 'World')
    # SAFE: Passing variables as context rather than string formatting
    return render_template_string("Hello {{ name }}!", name=name)
