from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ServerHealth(_message.Message):
    __slots__ = ("url", "sessions", "max_sessions")
    URL_FIELD_NUMBER: _ClassVar[int]
    SESSIONS_FIELD_NUMBER: _ClassVar[int]
    MAX_SESSIONS_FIELD_NUMBER: _ClassVar[int]
    url: str
    sessions: int
    max_sessions: int
    def __init__(self, url: _Optional[str] = ..., sessions: _Optional[int] = ..., max_sessions: _Optional[int] = ...) -> None: ...

class GetServerHealthResponse(_message.Message):
    __slots__ = ("server_health", "last_updated")
    SERVER_HEALTH_FIELD_NUMBER: _ClassVar[int]
    LAST_UPDATED_FIELD_NUMBER: _ClassVar[int]
    server_health: ServerHealth
    last_updated: float
    def __init__(self, server_health: _Optional[_Union[ServerHealth, _Mapping]] = ..., last_updated: _Optional[float] = ...) -> None: ...
