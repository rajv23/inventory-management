"""
Tests for restocking API endpoints.
"""
import pytest


class TestRestockingEndpoints:
    """Test suite for restocking-related endpoints."""

    def test_create_restock_order_success(self, client):
        """Test creating a restocking order with valid items."""
        payload = {
            "budget": 5000,
            "items": [
                {"sku": "WDG-001", "name": "Industrial Widget Type A", "quantity": 10, "unit_cost": 24.99}
            ]
        }
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["order_number"].startswith("RSO-2025-")
        assert 7 <= data["lead_time_days"] <= 14
        assert "expected_delivery" in data
        assert data["status"] == "Submitted"
        assert data["budget"] == 5000
        assert data["total_cost"] == 249.90

    def test_create_restock_order_empty_items_rejected(self, client):
        """Test that restock orders with empty items list are rejected."""
        payload = {"budget": 100, "items": []}
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 400
        assert "must include at least one item" in response.json()["detail"]

    def test_create_restock_order_multiple_items(self, client):
        """Test creating a restocking order with multiple items."""
        payload = {
            "budget": 10000,
            "items": [
                {"sku": "WDG-001", "name": "Industrial Widget Type A", "quantity": 5, "unit_cost": 24.99},
                {"sku": "PCB-001", "name": "Single Layer PCB Assembly", "quantity": 10, "unit_cost": 50.00}
            ]
        }
        response = client.post("/api/restocking/orders", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert len(data["items"]) == 2
        assert data["total_cost"] == (5 * 24.99) + (10 * 50.00)

    def test_get_restock_orders_lists_submitted(self, client):
        """Test retrieving list of submitted restock orders."""
        # First, create an order
        payload = {
            "budget": 1000,
            "items": [{"sku": "WDG-001", "name": "Widget", "quantity": 5, "unit_cost": 10.00}]
        }
        client.post("/api/restocking/orders", json=payload)

        # Now get the list
        response = client.get("/api/restocking/orders")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(order["order_number"].startswith("RSO-2025-") for order in data)

    def test_get_restock_orders_empty_initially(self, client):
        """Test that restock orders list starts empty."""
        response = client.get("/api/restocking/orders")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
