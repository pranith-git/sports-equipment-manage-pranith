from flask import Flask, current_app, jsonify

from inventory_service.database import ServiceError, initialize_database
from inventory_service.routes import inventory_api


app = Flask(__name__)
app.register_blueprint(inventory_api)
initialize_database()


@app.errorhandler(ServiceError)
def handle_service_error(error):
    return jsonify(error=error.message), error.status_code


@app.errorhandler(500)
def handle_internal_error(error):
    current_app.logger.error("Unhandled inventory service error: %s", error)
    return jsonify(error="Internal inventory service error."), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002, debug=False)
