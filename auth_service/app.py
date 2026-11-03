from flask import Flask, jsonify

from auth_service.database import initialize_database
from auth_service.routes import auth_api


app = Flask(__name__)
app.register_blueprint(auth_api)
app.add_url_rule(
    "/api/health",
    endpoint="health",
    view_func=lambda: jsonify(service="authentication", status="ok"),
)
initialize_database()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=False)
