"""Tests for the message processor orchestrator."""

from __future__ import annotations

import uuid
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
from code_messaging_bridge.services.claude.schemas import ClaudeResult
from code_messaging_bridge.services.processor import MessageProcessor


@pytest.fixture
def sync_session() -> Session:
    """Create a sync SQLite session for processor tests."""
    engine = create_engine("sqlite://", echo=False)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def conversation(sync_session: Session) -> Conversation:
    """Create a test conversation."""
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
    """Create mock settings for processor tests."""
    settings = MagicMock()
    settings.claude_cli_path = "claude"
    settings.claude_max_turns = 10
    settings.twilio_account_sid = "ACtest"
    settings.twilio_auth_token = "test_token"
    settings.twilio_whatsapp_number = "+14155551234"
    return settings


@patch("code_messaging_bridge.services.processor.ClaudeCodeRunner")
@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
@patch("code_messaging_bridge.services.processor.MessageProcessor._send_whatsapp_response")
def test_process_message_success(
    mock_send: MagicMock,
    _mock_subprocess: MagicMock,
    mock_runner_cls: MagicMock,
    sync_session: Session,
    conversation: Conversation,
    mock_settings: MagicMock,
) -> None:
    """Should invoke Claude, store outbound message, and send response."""
    mock_runner = MagicMock()
    mock_runner.invoke.return_value = ClaudeResult(
        success=True,
        output="Here is the answer.",
        session_id="sess-new-123",
        cost_usd=0.05,
        num_turns=3,
    )
    mock_runner_cls.return_value = mock_runner

    processor = MessageProcessor(sync_session, mock_settings)
    processor.process_message(
        conversation_id=conversation.id,
        content="What files are here?",
        platform_user_id="whatsapp:+1234567890",
    )
    sync_session.commit()

    # Verify Claude was called
    mock_runner.invoke.assert_called_once()
    invocation = mock_runner.invoke.call_args[0][0]
    assert invocation.prompt == "What files are here?"
    assert invocation.working_directory == "/tmp/project"

    # Verify session ID was updated
    sync_session.refresh(conversation)
    assert conversation.claude_session_id == "sess-new-123"

    # Verify outbound message was stored
    messages = sync_session.execute(
        select(Message).where(Message.conversation_id == conversation.id)
    ).scalars().all()
    assert len(messages) == 1
    assert messages[0].direction == MessageDirection.OUTBOUND
    assert messages[0].content == "Here is the answer."
    assert messages[0].status == MessageStatus.SENT

    # Verify WhatsApp send was called
    mock_send.assert_called_once_with("whatsapp:+1234567890", "Here is the answer.")


@patch("code_messaging_bridge.services.processor.ClaudeCodeRunner")
@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
@patch("code_messaging_bridge.services.processor.MessageProcessor._send_whatsapp_response")
def test_process_message_claude_error(
    mock_send: MagicMock,
    _mock_subprocess: MagicMock,
    mock_runner_cls: MagicMock,
    sync_session: Session,
    conversation: Conversation,
    mock_settings: MagicMock,
) -> None:
    """Should send error message when Claude fails."""
    mock_runner = MagicMock()
    mock_runner.invoke.return_value = ClaudeResult(
        success=False,
        output="",
        error_message="CLI timed out",
    )
    mock_runner_cls.return_value = mock_runner

    processor = MessageProcessor(sync_session, mock_settings)
    processor.process_message(
        conversation_id=conversation.id,
        content="Do something",
        platform_user_id="whatsapp:+1234567890",
    )
    sync_session.commit()

    # Verify error message was sent
    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][1]
    assert "error" in sent_text.lower()
    assert "CLI timed out" in sent_text

    # Verify outbound message was stored with error text
    messages = sync_session.execute(
        select(Message).where(Message.conversation_id == conversation.id)
    ).scalars().all()
    assert len(messages) == 1
    assert "error" in messages[0].content.lower()


@patch("code_messaging_bridge.services.processor.ClaudeCodeRunner")
@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
@patch("code_messaging_bridge.services.processor.MessageProcessor._send_whatsapp_response")
def test_process_message_resumes_session(
    mock_send: MagicMock,
    _mock_subprocess: MagicMock,
    mock_runner_cls: MagicMock,
    sync_session: Session,
    conversation: Conversation,
    mock_settings: MagicMock,
) -> None:
    """Should pass existing session_id to Claude for conversation continuity."""
    conversation.claude_session_id = "existing-session-abc"
    sync_session.commit()

    mock_runner = MagicMock()
    mock_runner.invoke.return_value = ClaudeResult(
        success=True,
        output="Follow-up answer.",
        session_id="existing-session-abc",
    )
    mock_runner_cls.return_value = mock_runner

    processor = MessageProcessor(sync_session, mock_settings)
    processor.process_message(
        conversation_id=conversation.id,
        content="Follow-up question",
        platform_user_id="whatsapp:+1234567890",
    )

    invocation = mock_runner.invoke.call_args[0][0]
    assert invocation.session_id == "existing-session-abc"


@patch("code_messaging_bridge.services.processor.ClaudeCodeRunner")
@patch("code_messaging_bridge.services.claude.runner.subprocess.run")
@patch("code_messaging_bridge.services.processor.MessageProcessor._send_whatsapp_response")
def test_process_message_missing_conversation(
    mock_send: MagicMock,
    _mock_subprocess: MagicMock,
    mock_runner_cls: MagicMock,
    sync_session: Session,
    mock_settings: MagicMock,
) -> None:
    """Should handle missing conversation gracefully."""
    mock_runner_cls.return_value = MagicMock()

    processor = MessageProcessor(sync_session, mock_settings)
    processor.process_message(
        conversation_id=uuid.uuid4(),
        content="Hello",
        platform_user_id="whatsapp:+1234567890",
    )

    # Should not crash, and should not send anything
    mock_send.assert_not_called()
