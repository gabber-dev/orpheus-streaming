from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ServerHealth(_message.Message):
    __slots__ = ["internal_connection_port", "internal_connection_url", "max_sessions", "sessions"]
    INTERNAL_CONNECTION_PORT_FIELD_NUMBER: _ClassVar[int]
    INTERNAL_CONNECTION_URL_FIELD_NUMBER: _ClassVar[int]
    MAX_SESSIONS_FIELD_NUMBER: _ClassVar[int]
    SESSIONS_FIELD_NUMBER: _ClassVar[int]
    internal_connection_port: int
    internal_connection_url: str
    max_sessions: int
    sessions: int
    def __init__(self, internal_connection_url: _Optional[str] = ..., internal_connection_port: _Optional[int] = ..., sessions: _Optional[int] = ..., max_sessions: _Optional[int] = ...) -> None: ...
