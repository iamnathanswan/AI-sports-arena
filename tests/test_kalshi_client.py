"""Pin the exact request shape create_order sends, so a regression here is
caught by CI rather than discovered live. Kalshi retired the legacy
POST /portfolio/orders endpoint (410 deprecated_v1_order_endpoint) in favor
of a V2 bid/ask book at POST /portfolio/events/orders."""

from arena.kalshi.client import KalshiClient


def make_client():
    return KalshiClient(env="demo", api_key_id="key-id", private_key_pem="unused-in-this-test")


def capture_request(client, monkeypatch):
    captured = {}

    def fake_request(method, endpoint, params=None, json_body=None, auth_required=False):
        captured.update(
            method=method, endpoint=endpoint, json_body=json_body, auth_required=auth_required
        )
        return {"order": {"order_id": "kalshi-order-1", "client_order_id": json_body["client_order_id"]}}

    monkeypatch.setattr(client, "_request", fake_request)
    return captured


class TestCreateOrderV2Migration:
    def test_hits_v2_endpoint_not_the_deprecated_v1_path(self, monkeypatch):
        client = make_client()
        captured = capture_request(client, monkeypatch)
        client.create_order(ticker="T1", side="yes", count=10, limit_price_cents=55)
        assert captured["method"] == "POST"
        assert captured["endpoint"] == "/portfolio/events/orders"
        assert captured["auth_required"] is True

    def test_yes_side_maps_to_bid(self, monkeypatch):
        client = make_client()
        captured = capture_request(client, monkeypatch)
        client.create_order(ticker="T1", side="yes", count=10, limit_price_cents=55)
        body = captured["json_body"]
        assert body["side"] == "bid"
        assert body["price"] == "0.5500"
        assert "yes_price" not in body and "no_price" not in body and "type" not in body

    def test_count_is_sent_as_a_string_not_a_number(self, monkeypatch):
        # V2 400s with "cannot unmarshal number into Go struct field
        # CreateOrderV2Request.count of type string" if count is a JSON int.
        client = make_client()
        captured = capture_request(client, monkeypatch)
        client.create_order(ticker="T1", side="yes", count=10, limit_price_cents=55)
        body = captured["json_body"]
        assert body["count"] == "10"
        assert isinstance(body["count"], str)

    def test_no_side_maps_to_ask(self, monkeypatch):
        client = make_client()
        captured = capture_request(client, monkeypatch)
        client.create_order(ticker="T1", side="no", count=4, limit_price_cents=30)
        body = captured["json_body"]
        assert body["side"] == "ask"
        assert body["price"] == "0.3000"

    def test_expiration_uses_renamed_field(self, monkeypatch):
        client = make_client()
        captured = capture_request(client, monkeypatch)
        client.create_order(ticker="T1", side="yes", count=1, limit_price_cents=50, expiration_ts=1751904000)
        body = captured["json_body"]
        assert body["time_in_force"] == "good_till_canceled"
        assert body["expiration_time"] == 1751904000
        assert "expiration_ts" not in body

    def test_no_expiration_omits_expiration_time(self, monkeypatch):
        client = make_client()
        captured = capture_request(client, monkeypatch)
        client.create_order(ticker="T1", side="yes", count=1, limit_price_cents=50)
        assert "expiration_time" not in captured["json_body"]

    def test_required_v2_fields_present(self, monkeypatch):
        client = make_client()
        captured = capture_request(client, monkeypatch)
        client.create_order(ticker="T1", side="yes", count=1, limit_price_cents=50)
        body = captured["json_body"]
        assert body["ticker"] == "T1"
        assert body["client_order_id"]
        assert body["count"] == "1"
        assert body["self_trade_prevention_type"] == "taker_at_cross"

    def test_result_extracted_from_response(self, monkeypatch):
        client = make_client()
        capture_request(client, monkeypatch)
        result = client.create_order(ticker="T1", side="yes", count=1, limit_price_cents=50)
        assert result["order_id"] == "kalshi-order-1"
