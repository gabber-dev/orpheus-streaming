from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

AUDIOTYPE_PCM16LE: AudioType
DESCRIPTOR: _descriptor.FileDescriptor

class AudioData(_message.Message):
    __slots__ = ["audio", "audio_type", "channel_count", "sample_rate", "session"]
    AUDIO_FIELD_NUMBER: _ClassVar[int]
    AUDIO_TYPE_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_COUNT_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    SESSION_FIELD_NUMBER: _ClassVar[int]
    audio: str
    audio_type: AudioType
    channel_count: int
    sample_rate: int
    session: str
    def __init__(self, session: _Optional[str] = ..., audio: _Optional[str] = ..., sample_rate: _Optional[int] = ..., audio_type: _Optional[_Union[AudioType, str]] = ..., channel_count: _Optional[int] = ...) -> None: ...

class Eos(_message.Message):
    __slots__ = ["session"]
    SESSION_FIELD_NUMBER: _ClassVar[int]
    session: str
    def __init__(self, session: _Optional[str] = ...) -> None: ...

class Error(_message.Message):
    __slots__ = ["message", "session"]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    SESSION_FIELD_NUMBER: _ClassVar[int]
    message: str
    session: str
    def __init__(self, session: _Optional[str] = ..., message: _Optional[str] = ...) -> None: ...

class Finished(_message.Message):
    __slots__ = ["session"]
    SESSION_FIELD_NUMBER: _ClassVar[int]
    session: str
    def __init__(self, session: _Optional[str] = ...) -> None: ...

class PushText(_message.Message):
    __slots__ = ["session", "text"]
    SESSION_FIELD_NUMBER: _ClassVar[int]
    TEXT_FIELD_NUMBER: _ClassVar[int]
    session: str
    text: str
    def __init__(self, session: _Optional[str] = ..., text: _Optional[str] = ...) -> None: ...

class ReceiveMessage(_message.Message):
    __slots__ = ["audio_data", "error", "finished"]
    AUDIO_DATA_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    FINISHED_FIELD_NUMBER: _ClassVar[int]
    audio_data: AudioData
    error: Error
    finished: Finished
    def __init__(self, audio_data: _Optional[_Union[AudioData, _Mapping]] = ..., finished: _Optional[_Union[Finished, _Mapping]] = ..., error: _Optional[_Union[Error, _Mapping]] = ...) -> None: ...

class SendMessage(_message.Message):
    __slots__ = ["eos", "push_text", "start_session"]
    EOS_FIELD_NUMBER: _ClassVar[int]
    PUSH_TEXT_FIELD_NUMBER: _ClassVar[int]
    START_SESSION_FIELD_NUMBER: _ClassVar[int]
    eos: Eos
    push_text: PushText
    start_session: StartSession
    def __init__(self, start_session: _Optional[_Union[StartSession, _Mapping]] = ..., push_text: _Optional[_Union[PushText, _Mapping]] = ..., eos: _Optional[_Union[Eos, _Mapping]] = ...) -> None: ...

class StartSession(_message.Message):
    __slots__ = ["id", "voice"]
    ID_FIELD_NUMBER: _ClassVar[int]
    VOICE_FIELD_NUMBER: _ClassVar[int]
    id: str
    voice: str
    def __init__(self, voice: _Optional[str] = ..., id: _Optional[str] = ...) -> None: ...

class AudioType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = []
