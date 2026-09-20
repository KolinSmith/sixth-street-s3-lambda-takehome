import os
import sys
from unittest.mock import patch, MagicMock

# "lambda" is a Python reserved keyword (used for anonymous functions), so a test file can't
# do `from lambda import handler` — that's a syntax error. This sidesteps it: manually add
# the lambda/ folder to Python's import search path (sys.path), then import handler.py as a
# bare top-level module instead of going through the "lambda" package name.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "lambda"))
import handler  # noqa: E402  (path must be set before this import)


# boto3's real get_object() returns a dict where response["Body"] is a stream-like object
# with a .read() method — this builds a fake version with the same shape, so our mock
# behaves close enough to the real S3 response for the code under test to not notice the
# difference.
def _mock_s3_object(body_bytes: bytes):
    mock_body = MagicMock()  # a fake object that accepts any method call/attribute access
    mock_body.read.return_value = body_bytes  # ...but .read() specifically returns this
    return {"Body": mock_body}


# caplog is a built-in pytest fixture (pytest auto-provides it just by naming it as a
# parameter) — it captures anything sent to Python's logging module during the test, so we
# can assert on what got logged without touching real CloudWatch.
def test_process_file_parses_comma_separated_line(caplog):
    # patch.object temporarily replaces handler.s3_client with a fake for the duration of
    # this `with` block only — real boto3/AWS is never touched, and the real s3_client is
    # restored automatically when the block ends.
    with patch.object(handler, "s3_client") as mock_client:
        mock_client.get_object.return_value = _mock_s3_object(
            b"alice,32,dallas"
        )
        with caplog.at_level("INFO"):  # only capture INFO-and-above log messages
            handler.process_file("test-bucket", "test-key.txt")

    # Confirms process_file called get_object with exactly these arguments, exactly once —
    # catches a bug like swapping the bucket/key order.
    mock_client.get_object.assert_called_once_with(
        Bucket="test-bucket", Key="test-key.txt"
    )
    # caplog.text is every captured log message joined into one string — checking each
    # parsed field shows up confirms the comma-split logic actually worked end to end.
    assert "alice" in caplog.text
    assert "32" in caplog.text
    assert "dallas" in caplog.text


def test_process_file_handles_empty_file(caplog):
    with patch.object(handler, "s3_client") as mock_client:
        mock_client.get_object.return_value = _mock_s3_object(b"")
        with caplog.at_level("ERROR"):
            handler.process_file("test-bucket", "empty-key.txt")

    # Proves the empty-file branch in handler.py actually fires and logs something
    # containing "empty" — this is the test that matches what you watched happen live
    # against the real deployment.
    assert "empty" in caplog.text.lower()


def test_process_file_handles_get_object_failure(caplog):
    with patch.object(handler, "s3_client") as mock_client:
        # side_effect makes the mock raise this exception instead of returning a value —
        # simulates S3 erroring out (missing file, permissions, etc.) without needing a
        # real broken S3 call to test against.
        mock_client.get_object.side_effect = Exception("boom")
        with caplog.at_level("ERROR"):
            handler.process_file("test-bucket", "missing-key.txt")

    # Confirms the try/except in process_file catches this and logs an error instead of
    # letting the exception crash the function.
    assert "failed" in caplog.text.lower()


def test_lambda_handler_processes_each_record():
    # A hand-built example of the event shape S3 actually sends a Lambda — one dict per
    # uploaded file, under "Records". Two records here tests that lambda_handler loops over
    # all of them, not just the first.
    event = {
        "Records": [
            {"s3": {"bucket": {"name": "b1"}, "object": {"key": "k1.txt"}}},
            {"s3": {"bucket": {"name": "b2"}, "object": {"key": "k2.txt"}}},
        ]
    }
    # Here we mock out process_file itself (not s3_client) — this test only cares that
    # lambda_handler correctly unpacks the event and calls process_file with the right
    # arguments, not what process_file does internally (that's covered by the tests above).
    with patch.object(handler, "process_file") as mock_process:
        handler.lambda_handler(event, context=None)

    assert mock_process.call_count == 2
    # assert_any_call checks this call happened at some point, regardless of order — since
    # dict/list iteration order for S3 records isn't something we need to depend on.
    mock_process.assert_any_call("b1", "k1.txt")
    mock_process.assert_any_call("b2", "k2.txt")
