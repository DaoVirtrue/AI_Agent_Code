"""
Inter-agent communication protocol and message bus.

Defines the AgentMessage format and a CommunicationBus supporting
send, receive, broadcast, and asynchronous message delivery between agents.
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    """Types of messages in the agent communication protocol."""
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    ACK = "ack"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    ESCALATION = "escalation"
    NOTIFICATION = "notification"
    HANDSHAKE = "handshake"
    SHUTDOWN = "shutdown"


class AgentMessage(BaseModel):
    """Standard message format for inter-agent communication.

    Attributes:
        msg_id: Unique message identifier.
        correlation_id: Links request-response pairs.
        msg_type: Type of the message (see MessageType enum).
        sender: Name of the sending agent.
        receiver: Name of the receiving agent (or '*' for broadcast).
        payload: Message content as a dict.
        timestamp: Unix timestamp when the message was created.
        ttl: Time-to-live in seconds (message expires after this).
        priority: Message priority (0=lowest, 10=highest).
    """
    msg_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str | None = None
    msg_type: str = MessageType.REQUEST.value
    sender: str
    receiver: str = "*"
    payload: dict = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
    ttl: float = 300.0
    priority: int = 5

    def is_expired(self) -> bool:
        """Check if the message has expired."""
        return time.time() - self.timestamp > self.ttl

    def create_response(self, payload: dict, msg_type: str = MessageType.RESPONSE.value) -> "AgentMessage":
        """Create a response message linked to this request.

        Args:
            payload: Response content.
            msg_type: Type for the response message.

        Returns:
            A new AgentMessage with correlation_id set.
        """
        return AgentMessage(
            msg_id=str(uuid.uuid4()),
            correlation_id=self.msg_id,
            msg_type=msg_type,
            sender=self.receiver,
            receiver=self.sender,
            payload=payload,
            priority=self.priority,
        )

    def to_dict(self) -> dict:
        """Serialize to a dict for transport."""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMessage":
        """Deserialize from a dict."""
        return cls(**data)


class CommunicationBus:
    """Asynchronous message bus for inter-agent communication.

    Supports:
    - Direct send/receive with timeouts
    - Broadcast to all agents
    - Request-response correlation
    - Priority-based message delivery
    - TTL-based message expiration

    Args:
        max_queue_size: Maximum messages per agent queue (default 1000).
    """

    def __init__(self, max_queue_size: int = 1000):
        self.max_queue_size = max_queue_size
        self._queues: dict[str, asyncio.Queue] = defaultdict(
            lambda: asyncio.Queue(maxsize=max_queue_size)
        )
        self._response_futures: dict[str, asyncio.Future] = {}
        self._message_count: dict[str, int] = defaultdict(int)
        self._started_at = time.time()

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    async def send(self, message: AgentMessage) -> bool:
        """Send a message to a specific receiver.

        Args:
            message: The AgentMessage to send.

        Returns:
            True if the message was queued successfully.

        Raises:
            ValueError: If the message has expired.
        """
        if message.is_expired():
            raise ValueError(f"Message {message.msg_id} has expired.")

        receiver = message.receiver
        queue = self._queues[receiver]

        try:
            queue.put_nowait(message)
        except asyncio.QueueFull:
            # Evict oldest message to make room
            try:
                queue.get_nowait()
                queue.put_nowait(message)
                logger.warning(
                    "Message queue full for '%s', evicted oldest message",
                    receiver,
                )
            except asyncio.QueueFull:
                logger.error("Message queue still full for '%s' after eviction", receiver)
                return False

        self._message_count[receiver] += 1
        logger.debug(
            "Message sent: %s -> %s [%s] (%s)",
            message.sender, message.receiver, message.msg_type, message.msg_id[:8],
        )
        return True

    async def broadcast(self, sender: str, payload: dict, msg_type: str = MessageType.BROADCAST.value) -> int:
        """Broadcast a message to all registered receivers.

        Args:
            sender: The sender agent name.
            payload: Message payload.
            msg_type: Message type.

        Returns:
            Number of agents the message was broadcast to.
        """
        message = AgentMessage(
            sender=sender,
            receiver="*",
            msg_type=msg_type,
            payload=payload,
        )

        sent = 0
        for agent_name in list(self._queues.keys()):
            if agent_name == sender:
                continue
            message.receiver = agent_name
            message.msg_id = str(uuid.uuid4())
            if await self.send(message):
                sent += 1

        return sent

    async def request(self, sender: str, receiver: str, payload: dict, timeout: float = 30.0) -> AgentMessage | None:
        """Send a request and wait for a response.

        Args:
            sender: Sending agent name.
            receiver: Receiving agent name.
            payload: Request payload.
            timeout: Seconds to wait for a response.

        Returns:
            The response AgentMessage, or None on timeout.

        Raises:
            ValueError: If sender or receiver is empty.
        """
        if not sender or not receiver:
            raise ValueError("Sender and receiver are required.")

        message = AgentMessage(
            sender=sender,
            receiver=receiver,
            msg_type=MessageType.REQUEST.value,
            payload=payload,
        )

        # Register a future for the response
        future = asyncio.get_event_loop().create_future()
        self._response_futures[message.msg_id] = future

        try:
            if not await self.send(message):
                self._response_futures.pop(message.msg_id, None)
                return None

            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            logger.warning("Request %s timed out after %.1fs", message.msg_id[:8], timeout)
            self._response_futures.pop(message.msg_id, None)
            return None
        except Exception as e:
            self._response_futures.pop(message.msg_id, None)
            raise

    # ------------------------------------------------------------------
    # Receive
    # ------------------------------------------------------------------

    async def receive(self, receiver: str, timeout: float = 30.0) -> AgentMessage | None:
        """Receive a message for a specific agent.

        Args:
            receiver: The agent name to receive messages for.
            timeout: Maximum seconds to wait.

        Returns:
            The received AgentMessage, or None on timeout.
        """
        queue = self._queues[receiver]

        try:
            message = await asyncio.wait_for(queue.get(), timeout=timeout)

            # Check expiry
            if message.is_expired():
                logger.debug("Discarding expired message: %s", message.msg_id[:8])
                return await self.receive(receiver, timeout)  # Try next

            # Check for response correlation
            if message.correlation_id and message.correlation_id in self._response_futures:
                future = self._response_futures.pop(message.correlation_id)
                if not future.done():
                    future.set_result(message)

            return message

        except asyncio.TimeoutError:
            return None

    async def receive_all(self, receiver: str) -> list[AgentMessage]:
        """Receive all available messages for an agent (non-blocking).

        Args:
            receiver: The agent name.

        Returns:
            List of all queued messages for this agent.
        """
        queue = self._queues[receiver]
        messages = []

        while not queue.empty():
            try:
                message = queue.get_nowait()
                if not message.is_expired():
                    messages.append(message)
            except asyncio.QueueEmpty:
                break

        return messages

    # ------------------------------------------------------------------
    # Send response (convenience)
    # ------------------------------------------------------------------

    async def send_response(self, request_msg: AgentMessage, payload: dict) -> bool:
        """Send a response to a request message.

        Args:
            request_msg: The original request message.
            payload: Response payload.

        Returns:
            True if sent successfully.
        """
        response = request_msg.create_response(payload)
        return await self.send(response)

    async def send_error(self, request_msg: AgentMessage, error: str, details: dict | None = None) -> bool:
        """Send an error response to a request message.

        Args:
            request_msg: The original request message.
            error: Error message string.
            details: Additional error details.

        Returns:
            True if sent successfully.
        """
        response = request_msg.create_response(
            {"error": error, "details": details or {}},
            msg_type=MessageType.ERROR.value,
        )
        return await self.send(response)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def stats(self) -> dict:
        """Return communication bus statistics."""
        return {
            "uptime_seconds": time.time() - self._started_at,
            "registered_receivers": len(self._queues),
            "messages_by_receiver": dict(self._message_count),
            "pending_responses": len(self._response_futures),
        }

    def __repr__(self) -> str:
        return f"CommunicationBus(receivers={len(self._queues)}, messages={sum(self._message_count.values())})"
