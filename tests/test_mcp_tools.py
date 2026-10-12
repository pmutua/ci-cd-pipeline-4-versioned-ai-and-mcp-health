# test_mcp_tools.py - Deliverable 3 evidence: unit tests against the MCP
# tool functions directly (no protocol, no subprocess), per the capstone's
# own fallback path ("No MCP Inspector: unit-test the tool functions with
# pytest"). Each tool is exercised once with valid input and at least once
# with a deliberately invalid call, proving errors come back as instructive
# JSON data (an "error" key naming the valid options) rather than a raised
# exception the caller can't recover from.

from __future__ import annotations

import json

from mcp_server import logistics_mcp as mcp


def test_check_stock_valid_item() -> None:
    result = json.loads(mcp.check_stock("amoxicillin"))
    assert result["item"] == "amoxicillin"
    assert len(result["stock"]) == 5
    assert {"clinic", "clinic_id", "county", "units", "reorder_needed"} <= result["stock"][0].keys()


def test_check_stock_invalid_item_returns_error_as_data() -> None:
    result = json.loads(mcp.check_stock("bandages"))
    assert "error" in result
    assert "bandages" in result["error"]
    assert "amoxicillin" in result["error"]  # names the valid options


def test_plan_delivery_route_valid_start() -> None:
    result = json.loads(mcp.plan_delivery_route("C01"))
    assert result["route"][0] == "Kisumu Central Clinic"
    assert len(result["route"]) == 5
    assert result["total_km"] > 0


def test_plan_delivery_route_invalid_clinic_returns_error_as_data() -> None:
    result = json.loads(mcp.plan_delivery_route("C99"))
    assert "error" in result
    assert "C99" in result["error"]


def test_get_delivery_eta_valid_pair() -> None:
    result = json.loads(mcp.get_delivery_eta("C01", "C04"))
    assert result["from"] == "Kisumu Central Clinic"
    assert result["to"] == "Homa Bay Lakeside Clinic"
    assert result["km"] > 0
    assert result["eta_minutes"] > 0


def test_get_delivery_eta_invalid_clinic_returns_error_as_data() -> None:
    result = json.loads(mcp.get_delivery_eta("C01", "ZZZ"))
    assert "error" in result


def test_request_reorder_valid() -> None:
    result = json.loads(mcp.request_reorder("C01", "amoxicillin", 50))
    assert result["status"] == "planned"
    assert result["units"] == 50


def test_request_reorder_units_out_of_range_returns_error_as_data() -> None:
    result = json.loads(mcp.request_reorder("C01", "amoxicillin", 9999))
    assert "error" in result
    assert "500" in result["error"]


def test_request_reorder_unknown_item_returns_error_as_data() -> None:
    result = json.loads(mcp.request_reorder("C01", "vitamins", 10))
    assert "error" in result
    assert "vitamins" in result["error"]


def test_request_reorder_unknown_clinic_returns_error_as_data() -> None:
    result = json.loads(mcp.request_reorder("Z99", "amoxicillin", 10))
    assert "error" in result
    assert "Z99" in result["error"]


def test_clinic_directory_resource() -> None:
    result = json.loads(mcp.clinic_directory())
    assert len(result) == 5
    assert {"id", "name", "county"} <= result[0].keys()


def test_every_tool_call_logs_one_line(caplog) -> None:
    import logging

    with caplog.at_level(logging.INFO, logger="logistics_mcp"):
        mcp.check_stock("amoxicillin")
    assert any("tool=check_stock" in r.message for r in caplog.records)
