"""
tests/conftest.py
Shared pytest fixtures for ObsidianHomeOrchestrator tests.

Provides:
- moto-mocked MinIO (S3) with a pre-populated obsidian-vault bucket
- OpenRouter / OpenAI client mock
- Sample brain dump content fixtures
"""
import json
import os
import sys
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.client import Config

# Ensure tools/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

BUCKET = "obsidian-vault"
MINIO_ENDPOINT = "http://localhost:9000"  # used by moto as fake endpoint


# ── Environment ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Set required env vars for all tests — prevents reading real .env."""
    monkeypatch.setenv("MINIO_ENDPOINT", MINIO_ENDPOINT)
    monkeypatch.setenv("MINIO_ACCESS_KEY", "test-access-key")
    monkeypatch.setenv("MINIO_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("MINIO_BUCKET", BUCKET)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test-key")


# ── Mocked MinIO (S3) ────────────────────────────────────────────────────────

@pytest.fixture
def mock_s3(aws_credentials):
    """Moto-mocked S3 client with obsidian-vault bucket pre-created."""
    try:
        from moto import mock_s3 as moto_mock_s3
    except ImportError:
        pytest.skip("moto not installed — skipping S3 mock tests")

    with moto_mock_s3():
        client = boto3.client(
            "s3",
            region_name="us-east-1",
            aws_access_key_id="test-access-key",
            aws_secret_access_key="test-secret-key",
        )
        client.create_bucket(Bucket=BUCKET)
        yield client


@pytest.fixture
def aws_credentials(monkeypatch):
    """Stub AWS credentials so boto3 doesn't look for real ones."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-access-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-secret-key")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")


@pytest.fixture
def s3_with_brain_dump(mock_s3):
    """S3 fixture with a sample brain dump already uploaded."""
    content = SAMPLE_BRAIN_DUMP
    mock_s3.put_object(
        Bucket=BUCKET,
        Key="00_Inbox/brain-dumps/BrainDump — Personal.md",
        Body=content.encode("utf-8"),
    )
    yield mock_s3


# ── OpenRouter mock ──────────────────────────────────────────────────────────

def make_openrouter_response(text: str):
    """Build a mock OpenAI chat completion response."""
    choice = MagicMock()
    choice.message.content = text
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.fixture
def mock_openrouter_success():
    """OpenRouter client that returns a valid task list on first try."""
    client = MagicMock()
    client.chat.completions.create.return_value = make_openrouter_response(
        "- [ ] Call Dr. Smith about hip MRI [area:: health] [priority:: A]\n"
        "- [ ] Research CrossFit gyms near home [area:: health] [priority:: B]"
    )
    return client


@pytest.fixture
def mock_openrouter_first_fails():
    """OpenRouter client where first model fails, second succeeds."""
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        Exception("Rate limit exceeded"),
        make_openrouter_response(
            "- [ ] Buy groceries before Sunday [area:: personal] [priority:: B]"
        ),
    ]
    return client


@pytest.fixture
def mock_openrouter_all_fail():
    """OpenRouter client where all models fail."""
    client = MagicMock()
    client.chat.completions.create.side_effect = Exception("Rate limit exceeded")
    return client


@pytest.fixture
def mock_openrouter_none_response():
    """OpenRouter client that returns NONE (no tasks found)."""
    client = MagicMock()
    client.chat.completions.create.return_value = make_openrouter_response("NONE")
    return client


# ── Sample content fixtures ──────────────────────────────────────────────────

SAMPLE_BRAIN_DUMP = """---
domain: Personal
area: personal
last_processed:
status: empty
---

## ⚡ Quick Notes
Some quick thoughts here

## ✅ To Do's
- Buy milk and groceries before Sunday
- Call Dr. Smith about hip MRI results [priority:: A]
- Research CrossFit gyms near home for 3x/week routine

## 💡 Ideas & Possibilities
New app idea: a habit tracker that integrates with Obsidian using natural language input

## 🔁 Recurring / Rhythms
Weekly gym sessions need to become a firm habit — 3x minimum
"""

SAMPLE_BRAIN_DUMP_EMPTY = """---
domain: Personal
area: personal
last_processed:
status: empty
---

## ⚡ Quick Notes
> **How to use:** Add any quick notes here

## ✅ To Do's
*Add tasks here*

## 💡 Ideas & Possibilities
=this.ideas
"""

SAMPLE_BRAIN_DUMP_TASKS_ONLY = """---
domain: Work
area: work
---

## ✅ To Do's
- [ ] Deliver Union project final report [priority:: A]
- [ ] Schedule exit conversation with manager
- Review Q2 performance metrics
"""

SAMPLE_BRAIN_DUMP_ARTICLES = """---
domain: Personal
area: personal
---

## 📰 Articles & Resources to Follow Up On
- https://example.com/article-1 — interesting AI research
- Check out https://example.com/article-2 about biohacking
"""
