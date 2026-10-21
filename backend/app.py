"""PriceHawk backend: the Flask API that the Chrome extension talks to.

Run it with:   python app.py
"""
import logging
from functools import wraps

from flask import Flask, Response, jsonify, request

import config
from database import db
from exceptions import PriceHawkError, ValidationError
from services import export_service, tracker_service
from services.monitor import start_monitor

logger = logging.getLogger(__name__)
app = Flask(__name__)


# ---------- helpers ----------

def handle_errors(view):
    """DECORATOR: wraps a route so any error becomes a clean JSON response.

    Without it, every route would need its own try/except block.
    """
    @wraps(view)
    def wrapper(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except PriceHawkError as error:  # our own errors know their status code
            return jsonify({"error": str(error)}), error.status_code
        except Exception:  # anything unexpected: log details, hide them from the user
            logger.exception("Unexpected error in %s", view.__name__)
            return jsonify({"error": "Internal server error"}), 500
    return wrapper


def get_json_body():
    body = request.get_json(silent=True)  # None if missing or not valid JSON
    if not isinstance(body, dict):
        raise ValidationError("Request body must be a JSON object")
    return body


def get_url_from_body(body):
    url = body.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValidationError("url is required")
    return url


def csv_response(lines, filename):
    return Response(
        lines,  # a generator: Flask streams it line by line
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------- CORS (lets the Chrome extension call this API) ----------

def origin_allowed(origin):
    if config.EXTENSION_ID:
        return origin == f"chrome-extension://{config.EXTENSION_ID}"
    return origin.startswith("chrome-extension://")  # any extension, but no normal websites


@app.after_request
def add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    if origin_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Vary"] = "Origin"
    return response


# ---------- routes ----------

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "demo_mode": config.DEMO_MODE})


@app.route("/api/preview", methods=["POST"])
@handle_errors
def preview():
    """Look up a product's title and price without saving it."""
    return jsonify(tracker_service.preview_product(get_url_from_body(get_json_body())))


@app.route("/api/products", methods=["POST"])
@handle_errors
def add_product():
    body = get_json_body()
    product = tracker_service.track_product(get_url_from_body(body), body.get("target_price"))
    return jsonify(product.to_dict()), 201


@app.route("/api/products", methods=["GET"])
@handle_errors
def list_products():
    products = tracker_service.list_products(request.args.get("sort", "newest"))
    return jsonify({"products": [product.to_dict() for product in products]})


@app.route("/api/products/<int:product_id>", methods=["GET"])
@handle_errors
def get_product(product_id):
    return jsonify(tracker_service.get_product(product_id).to_dict())


@app.route("/api/products/<int:product_id>", methods=["PUT"])
@handle_errors
def update_product(product_id):
    return jsonify(tracker_service.update_product(product_id, get_json_body()).to_dict())


@app.route("/api/products/<int:product_id>", methods=["DELETE"])
@handle_errors
def delete_product(product_id):
    tracker_service.delete_product(product_id)
    return jsonify({"message": "Product deleted"})


@app.route("/api/products/<int:product_id>/check", methods=["POST"])
@handle_errors
def check_now(product_id):
    return jsonify(tracker_service.check_product(product_id).to_dict())


@app.route("/api/products/<int:product_id>/history", methods=["GET"])
@handle_errors
def price_history(product_id):
    return jsonify({"product_id": product_id, "history": tracker_service.get_history(product_id)})


@app.route("/api/products/<int:product_id>/simulate", methods=["POST"])
@handle_errors
def simulate(product_id):
    """DEMO MODE only: fake a new price to show the email alert."""
    body = get_json_body()
    return jsonify(tracker_service.simulate_price(product_id, body.get("price")).to_dict())


@app.route("/api/export/products.csv")
@handle_errors
def export_products():
    return csv_response(export_service.products_csv(), "pricehawk_products.csv")


@app.route("/api/export/history.csv")
@handle_errors
def export_history():
    product_id = request.args.get("product_id", type=int)
    if product_id is not None:
        tracker_service.get_product(product_id)  # 404 now, instead of an empty file
    return csv_response(export_service.history_csv(product_id), "pricehawk_history.csv")


# ---------- start-up ----------

def setup_logging():
    handlers = [logging.StreamHandler()]
    try:
        handlers.append(logging.FileHandler(config.LOG_FILE, encoding="utf-8"))
    except OSError as error:  # e.g. no permission to write the log file
        print(f"Warning: cannot write log file ({error}); logging to console only")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )


if __name__ == "__main__":
    setup_logging()
    db.init_db()
    start_monitor(config.CHECK_INTERVAL_SECONDS)
    # use_reloader=False: the auto-reloader would run this file twice => two monitor threads.
    app.run(host=config.HOST, port=config.PORT, debug=False, use_reloader=False)
