from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetServerHealthResponse(_message.Message):
    __slots__ = ["last_updated", "server_health"]
    LAST_UPDATED_FIELD_NUMBER: _ClassVar[int]
    SERVER_HEALTH_FIELD_NUMBER: _ClassVar[int]
    last_updated: float
    server_health: ServerHealth
    def __init__(self, server_health: _Optional[_Union[ServerHealth, _Mapping]] = ..., last_updated: _Optional[float] = ...) -> None: ...

class ServerHealth(_message.Message):
    __slots__ = ["max_sessions", "sessions", "url"]
    MAX_SESSIONS_FIELD_NUMBER: _ClassVar[int]
    SESSIONS_FIELD_NUMBER: _ClassVar[int]
    URL_FIELD_NUMBER: _ClassVar[int]
    max_sessions: int
    sessions: int
    url: str
    def __init__(self, url: _Optional[str] = ..., sessions: _Optional[int] = ..., max_sessions: _Optional[int] = ...) -> None: ...
