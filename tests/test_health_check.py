"""Tests for scripts/health_check.py"""
import pytest
import sys
import os
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from health_check import check_minio, check_n8n, check_vault_files, check_brain_dumps, HealthResult


def test_health_result_structure():
    r = HealthResult(component="test", status="pass", message="ok", details={})
    assert r.component == "test"
    assert r.status == "pass"
    assert r.message == "ok"
    assert r.details == {}


def test_health_result_statuses():
    for status in ("pass", "fail", "warn"):
        r = HealthResult(component="x", status=status, message="m", details={})
        assert r.status == status


# --- check_minio ---

def test_check_minio_pass():
    mock_s3 = MagicMock()
    mock_s3.head_bucket.return_value = {}
    with patch("health_check._s3_client", return_value=mock_s3):
        result = check_minio()
    assert result.status == "pass"
    assert result.component == "minio"


def test_check_minio_fail_client_error():
    mock_s3 = MagicMock()
    mock_s3.head_bucket.side_effect = ClientError(
        {"Error": {"Code": "NoSuchBucket", "Message": ""}}, "HeadBucket"
    )
    with patch("health_check._s3_client", return_value=mock_s3):
        result = check_minio()
    assert result.status == "fail"
    assert "NoSuchBucket" in result.message


def test_check_minio_fail_connection_error():
    with patch("health_check._s3_client", side_effect=Exception("Connection refused")):
        result = check_minio()
    assert result.status == "fail"
    assert "unreachable" in result.message.lower()


# --- check_n8n ---

def test_check_n8n_pass():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    with patch("health_check.requests.get", return_value=mock_resp):
        result = check_n8n()
    assert result.status == "pass"
    assert result.component == "n8n"


def test_check_n8n_fail_non_200():
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    with patch("health_check.requests.get", return_value=mock_resp):
        result = check_n8n()
    assert result.status == "fail"
    assert "503" in result.message


def test_check_n8n_fail_connection_error():
    with patch("health_check.requests.get", side_effect=Exception("timeout")):
        result = check_n8n()
    assert result.status == "fail"
    assert "unreachable" in result.message.lower()


# --- check_vault_files ---

def test_check_vault_files_all_present():
    mock_s3 = MagicMock()
    mock_s3.head_object.return_value = {}
    with patch("health_check._s3_client", return_value=mock_s3):
        result = check_vault_files()
    assert result.status == "pass"
    assert "missing" not in result.details


def test_check_vault_files_some_missing():
    mock_s3 = MagicMock()
    mock_s3.head_object.side_effect = [
        {},  # first file found
        ClientError({"Error": {"Code": "404", "Message": ""}}, "HeadObject"),  # second missing
        {},
        {},
    ]
    with patch("health_check._s3_client", return_value=mock_s3):
        result = check_vault_files()
    assert result.status == "fail"
    assert len(result.details["missing"]) == 1


# --- check_brain_dumps ---

def test_check_brain_dumps_found():
    mock_s3 = MagicMock()
    mock_s3.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "00_Inbox/brain-dumps/BrainDump — Personal.md", "Size": 4721},
            {"Key": "00_Inbox/brain-dumps/BrainDump — Faith.md", "Size": 1267},
        ]
    }
    with patch("health_check._s3_client", return_value=mock_s3):
        result = check_brain_dumps()
    assert result.status == "pass"
    assert result.details["count"] == 2


def test_check_brain_dumps_none_found():
    mock_s3 = MagicMock()
    mock_s3.list_objects_v2.return_value = {"Contents": []}
    with patch("health_check._s3_client", return_value=mock_s3):
        result = check_brain_dumps()
    assert result.status == "warn"
