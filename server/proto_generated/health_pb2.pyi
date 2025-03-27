from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ServerHealth(_message.Message):
    __slots__ = ["host", "max_sessions", "port", "sessions"]
    HOST_FIELD_NUMBER: _ClassVar[int]
    MAX_SESSIONS_FIELD_NUMBER: _ClassVar[int]
    PORT_FIELD_NUMBER: _ClassVar[int]
    SESSIONS_FIELD_NUMBER: _ClassVar[int]
    host: str
    max_sessions: int
    port: int
    sessions: int
    def __init__(self, host: _Optional[str] = ..., port: _Optional[int] = ..., sessions: _Optional[int] = ..., max_sessions: _Optional[int] = ...) -> None: ...
