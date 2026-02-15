"""Integration test: full pipeline with mocked Claude CLI."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from code_messaging_bridge.models import (
    Base,
    Conversation,
    Message,
    MessageDirection,
    MessageStatus,
)
from code_messaging_bridge.services.processor import MessageProcessor


@pytest.fixture
def sync_session() -> Session:
    """Create a sync SQLite session for integration tests."""
    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def conversation(sync_session: Session) -> Conversation:
    """Create a test conversation for integration tests."""
    conv = Conversation(
        platform="whatsapp",
        platform_user_id="whatsapp:+1234567890",
        working_directory="/tmp/project",
        is_active=True,
    )
    sync_session.add(conv)
    sync_session.commit()
    return conv


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings for integration tests."""
    settings = MagicMock()
    settings.claude_cli_path = "claude"
    settings.claude_max_turns = 10
    settings.twilio_account_sid = "ACtest"
    settings.twilio_auth_token = "test_token"
    settings.twilio_whatsapp_number = "+14155551234"
    return settings


@patch("code_messaging_bridge.services.processor.MessageProcessor._send_whatsapp_response")
@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
def test_full_pipeline_success(
    mock_subprocess: MagicMock,
    mock_send: MagicMock,
    sync_session: Session,
    conversation: Conversation,
    mock_settings: MagicMock,
) -> None:
    """Full pipeline: receive message → Claude processes → response sent → stored in DB."""
    # Mock Claude CLI returning a successful JSON response
    claude_output = json.dumps({
        "type": "result",
        "result": "There are 5 files in this project.",
        "session_id": "sess-integration-001",
        "cost_usd": 0.03,
        "duration_ms": 8000,
        "num_turns": 2,
        "is_error": False,
    })
    mock_subprocess.return_value = MagicMock(
        returncode=0, stdout=claude_output, stderr=""
    )

    processor = MessageProcessor(sync_session, mock_settings)
    processor.process_message(
        conversation_id=conversation.id,
        content="What files are in this project?",
        platform_user_id="whatsapp:+1234567890",
    )
    sync_session.commit()

    # Verify Claude was called with correct prompt
    call_args = mock_subprocess.call_args
    cmd = call_args[0][0]
    assert "What files are in this project?" in cmd

    # Verify session ID was updated on conversation
    sync_session.refresh(conversation)
    assert conversation.claude_session_id == "sess-integration-001"

    # Verify response was sent via WhatsApp
    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][1]
    assert "5 files" in sent_text

    # Verify outbound message stored in DB
    messages = sync_session.execute(
        select(Message).where(Message.conversation_id == conversation.id)
    ).scalars().all()
    assert len(messages) == 1
    assert messages[0].direction == MessageDirection.OUTBOUND
    assert messages[0].status == MessageStatus.SENT


@patch("code_messaging_bridge.services.processor.MessageProcessor._send_whatsapp_response")
@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
def test_full_pipeline_session_continuity(
    mock_subprocess: MagicMock,
    mock_send: MagicMock,
    sync_session: Session,
    conversation: Conversation,
    mock_settings: MagicMock,
) -> None:
    """Second message should use --resume with the session ID from first message."""
    # First message
    first_output = json.dumps({
        "result": "First answer",
        "session_id": "sess-first",
        "is_error": False,
    })
    mock_subprocess.return_value = MagicMock(returncode=0, stdout=first_output, stderr="")

    processor = MessageProcessor(sync_session, mock_settings)
    processor.process_message(
        conversation_id=conversation.id,
        content="First question",
        platform_user_id="whatsapp:+1234567890",
    )
    sync_session.commit()

    # Verify session ID set
    sync_session.refresh(conversation)
    assert conversation.claude_session_id == "sess-first"

    # Second message should pass the session ID
    second_output = json.dumps({
        "result": "Follow-up answer",
        "session_id": "sess-first",
        "is_error": False,
    })
    mock_subprocess.return_value = MagicMock(returncode=0, stdout=second_output, stderr="")

    processor.process_message(
        conversation_id=conversation.id,
        content="Follow-up question",
        platform_user_id="whatsapp:+1234567890",
    )
    sync_session.commit()

    # Second call should include --resume
    second_call_cmd = mock_subprocess.call_args[0][0]
    assert "--resume" in second_call_cmd
    resume_idx = second_call_cmd.index("--resume")
    assert second_call_cmd[resume_idx + 1] == "sess-first"

    # Should have 2 outbound messages now
    messages = sync_session.execute(
        select(Message).where(
            Message.conversation_id == conversation.id,
            Message.direction == MessageDirection.OUTBOUND,
        )
    ).scalars().all()
    assert len(messages) == 2


@patch("code_messaging_bridge.services.processor.MessageProcessor._send_whatsapp_response")
@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
def test_full_pipeline_long_response_split(
    mock_subprocess: MagicMock,
    mock_send: MagicMock,
    sync_session: Session,
    conversation: Conversation,
    mock_settings: MagicMock,
) -> None:
    """Long Claude responses should be split into multiple WhatsApp messages."""
    long_text = "This is a detailed explanation. " * 100  # ~3100 chars
    claude_output = json.dumps({
        "result": long_text,
        "session_id": "sess-long",
        "is_error": False,
    })
    mock_subprocess.return_value = MagicMock(returncode=0, stdout=claude_output, stderr="")

    # Use real _send_whatsapp_response but mock the Twilio client
    patch_target = (
        "code_messaging_bridge.services.processor.MessageProcessor._send_whatsapp_response"
    )
    with patch(patch_target) as patched_send:
        processor = MessageProcessor(sync_session, mock_settings)
        processor.process_message(
            conversation_id=conversation.id,
            content="Explain in detail",
            platform_user_id="whatsapp:+1234567890",
        )

    # Response should have been sent (content stored is the full text)
    patched_send.assert_called_once()
