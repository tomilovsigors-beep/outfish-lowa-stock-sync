from datetime import datetime, timedelta, timezone
from flask import jsonify, request

CREATE_CASE = """
mutation CreateCase($metaobject: MetaobjectCreateInput!) {
  metaobjectCreate(metaobject: $metaobject) {
    metaobject { id handle }
    userErrors { field message }
  }
}
"""

def add_recovery_routes(app, shop_factory):
    @app.route("/recovery/request", methods=["POST", "OPTIONS"])
    def recovery_request():
        if request.method == "OPTIONS":
            response = app.make_response(("", 204))
        else:
            data = request.get_json(silent=True) or {}
            email = str(data.get("email", "")).strip().lower()
            request_id = str(data.get("request_id", "")).strip()
            product_id = str(data.get("product_id", "")).strip()
            variant_id = str(data.get("variant_id", "")).strip()
            if not email or "@" not in email or not request_id or not product_id or not variant_id:
                response = app.make_response((jsonify({"error":"invalid"}), 400))
            else:
                now = datetime.now(timezone.utc)
                fields = [
                    {"key":"request_id","value":request_id},
                    {"key":"case_type","value":"price_alert"},
                    {"key":"source","value":"storefront"},
                    {"key":"status","value":"pending"},
                    {"key":"email","value":email},
                    {"key":"product_id","value":product_id},
                    {"key":"variant_id","value":variant_id},
                    {"key":"product_title","value":str(data.get("product_title",""))},
                    {"key":"variant_title","value":str(data.get("variant_title",""))},
                    {"key":"locale","value":str(data.get("locale","lv"))},
                    {"key":"requested_at","value":now.isoformat()},
                    {"key":"process_after","value":(now+timedelta(hours=24)).isoformat()},
                    {"key":"consent_at_request","value":"true" if data.get("marketing_consent") else "false"},
                ]
                result = shop_factory().gql(CREATE_CASE, {
                    "metaobject": {
                        "type":"outfish_recovery_case",
                        "fields":fields
                    }
                })["metaobjectCreate"]
                if result.get("userErrors"):
                    response = app.make_response((jsonify({"error":"shopify","details":result["userErrors"]}),409))
                else:
                    response = app.make_response((jsonify({"ok":True,"id":result["metaobject"]["id"]}),201))
        origin=request.headers.get("Origin","")
        if origin in ("https://outfish.lv","https://www.outfish.lv"):
            response.headers["Access-Control-Allow-Origin"]=origin
            response.headers["Vary"]="Origin"
        response.headers["Access-Control-Allow-Headers"]="Content-Type"
        response.headers["Access-Control-Allow-Methods"]="POST, OPTIONS"
        return response
