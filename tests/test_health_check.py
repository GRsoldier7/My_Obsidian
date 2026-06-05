"""Tests for scripts/health_check.py"""
import pytest
import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
from health_check import (
    check_minio, check_n8n, check_vault_files, check_brain_dumps,
    check_n8n_execution_backlog, check_n8n_disk_errors, HealthResult,
)


def _backlog_response(n):
    """Mock a single-page n8n executions API response with n items."""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"data": [{} for _ in range(n)], "nextCursor": None}
    return resp


def test_backlog_skipped_without_api_key():
    with patch("health_check.N8N_API_KEY", ""):
        r = check_n8n_execution_backlog()
    assert r.status == "pass"
    assert "Skipped" in r.message


def test_backlog_pass_under_warn():
    with patch("health_check.N8N_API_KEY", "k"), \
         patch("health_check.requests.get", return_value=_backlog_response(175)):
        r = check_n8n_execution_backlog()
    assert r.status == "pass"
    assert r.details["retained"] == 175


def test_backlog_warn_at_threshold():
    with patch("health_check.N8N_API_KEY", "k"), \
         patch("health_check.requests.get", return_value=_backlog_response(1200)):
        r = check_n8n_execution_backlog()
    assert r.status == "warn"
    assert "EXECUTIONS_DATA_PRUNE" in r.message


def test_backlog_fail_at_threshold():
    with patch("health_check.N8N_API_KEY", "k"), \
         patch("health_check.requests.get", return_value=_backlog_response(2500)):
        r = check_n8n_execution_backlog()
    assert r.status == "fail"


def test_backlog_warn_on_api_error():
    with patch("health_check.N8N_API_KEY", "k"), \
         patch("health_check.requests.get", side_effect=Exception("boom")):
        r = check_n8n_execution_backlog()
    assert r.status == "warn"


# --- disk-error (ENOSPC) canary ---------------------------------------------

def _resp(json_obj):
    m = MagicMock()
    m.raise_for_status.return_value = None
    m.json.return_value = json_obj
    return m


def _iso(hours_ago):
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _disk_seq(started_iso, message):
    """Two-stage mock: error-list page, then one execution's detail."""
    list_resp = _resp({"data": [{"id": "1", "startedAt": started_iso,
                                 "workflowId": "4HAStrQY2yZfLKym"}]})
    detail_resp = _resp({"data": {"resultData": {"error": {"message": message}}},
                         "startedAt": started_iso})
    return [list_resp, detail_resp]


def test_disk_errors_skipped_without_api_key():
    with patch("health_check.N8N_API_KEY", ""):
        r = check_n8n_disk_errors()
    assert r.status == "pass"
    assert "Skipped" in r.message


def test_disk_errors_fail_recent_enospc():
    seq = _disk_seq(_iso(1),
                    "ENOSPC: no space left on device, mkdir "
                    "'/home/node/.n8n/binaryData/workflows/4HAStrQY2yZfLKym/executions/9621'")
    with patch("health_check.N8N_API_KEY", "k"), \
         patch("health_check.requests.get", side_effect=seq):
        r = check_n8n_disk_errors()
    assert r.status == "fail"
    assert "ENOSPC" in r.message
    assert "df -h" in r.details["fix"]


def test_disk_errors_warn_old_enospc():
    seq = _disk_seq(_iso(48), "ENOSPC: no space left on device")
    with patch("health_check.N8N_API_KEY", "k"), \
         patch("health_check.requests.get", side_effect=seq):
        r = check_n8n_disk_errors()
    assert r.status == "warn"
    assert r.details["older_count"] == 1


def test_disk_errors_pass_when_error_is_not_disk():
    seq = _disk_seq(_iso(1), "TypeError: cannot read property 'foo' of undefined")
    with patch("health_check.N8N_API_KEY", "k"), \
         patch("health_check.requests.get", side_effect=seq):
        r = check_n8n_disk_errors()
    assert r.status == "pass"


def test_disk_errors_warn_on_api_error():
    with patch("health_check.N8N_API_KEY", "k"), \
         patch("health_check.requests.get", side_effect=Exception("boom")):
        r = check_n8n_disk_errors()
    assert r.status == "warn"


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
