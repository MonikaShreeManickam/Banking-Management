from flask import Flask, render_template

from customer import customer
from admin import admin
from loan import loan
from customer_api import customer_api

app = Flask(__name__)

# Secret Key
app.secret_key = "banking_secret_key"

@app.route("/")
def home():
    return render_template("home.html")

# Register Blueprints
app.register_blueprint(customer)
app.register_blueprint(admin)
app.register_blueprint(loan)
app.register_blueprint(customer_api)

# -------------------------
# Main Program
# -------------------------
if __name__ == "__main__":
    app.run(debug=True)