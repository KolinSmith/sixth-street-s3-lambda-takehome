import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda"))
import handler  # noqa: E402  (path must be set before this import)


def _mock_s3_object(body_bytes: bytes):
    mock_body = MagicMock()
    mock_body.read.return_value = body_bytes
    return {"Body": mock_body}


def test_process_file_parses_comma_separated_line(caplog):
    with patch.object(handler, "s3_client") as mock_client:
        mock_client.get_object.return_value = _mock_s3_object(
            b"alice,32,dallas"
        )
        with caplog.at_level("INFO"):
            handler.process_file("test-bucket", "test-key.txt")

    mock_client.get_object.assert_called_once_with(
        Bucket="test-bucket", Key="test-key.txt"
    )
    assert "alice" in caplog.text
    assert "32" in caplog.text
    assert "dallas" in caplog.text


def test_process_file_handles_empty_file(caplog):
    with patch.object(handler, "s3_client") as mock_client:
        mock_client.get_object.return_value = _mock_s3_object(b"")
        with caplog.at_level("ERROR"):
            handler.process_file("test-bucket", "empty-key.txt")

    assert "empty" in caplog.text.lower()


def test_process_file_handles_get_object_failure(caplog):
    with patch.object(handler, "s3_client") as mock_client:
        mock_client.get_object.side_effect = Exception("boom")
        with caplog.at_level("ERROR"):
            handler.process_file("test-bucket", "missing-key.txt")

    assert "failed" in caplog.text.lower()


def test_lambda_handler_processes_each_record():
    event = {
        "Records": [
            {"s3": {"bucket": {"name": "b1"}, "object": {"key": "k1.txt"}}},
            {"s3": {"bucket": {"name": "b2"}, "object": {"key": "k2.txt"}}},
        ]
    }
    with patch.object(handler, "process_file") as mock_process:
        handler.lambda_handler(event, context=None)

    assert mock_process.call_count == 2
    mock_process.assert_any_call("b1", "k1.txt")
    mock_process.assert_any_call("b2", "k2.txt")
