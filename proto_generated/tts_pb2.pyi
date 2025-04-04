from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AudioType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    AUDIOTYPE_PCM16LE: _ClassVar[AudioType]
AUDIOTYPE_PCM16LE: AudioType

class SendMessage(_message.Message):
    __slots__ = ("session", "start_session", "push_text", "eos")
    SESSION_FIELD_NUMBER: _ClassVar[int]
    START_SESSION_FIELD_NUMBER: _ClassVar[int]
    PUSH_TEXT_FIELD_NUMBER: _ClassVar[int]
    EOS_FIELD_NUMBER: _ClassVar[int]
    session: str
    start_session: StartSession
    push_text: PushText
    eos: Eos
    def __init__(self, session: _Optional[str] = ..., start_session: _Optional[_Union[StartSession, _Mapping]] = ..., push_text: _Optional[_Union[PushText, _Mapping]] = ..., eos: _Optional[_Union[Eos, _Mapping]] = ...) -> None: ...

class ReceiveMessage(_message.Message):
    __slots__ = ("session", "audio_data", "finished", "error")
    SESSION_FIELD_NUMBER: _ClassVar[int]
    AUDIO_DATA_FIELD_NUMBER: _ClassVar[int]
    FINISHED_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    session: str
    audio_data: AudioData
    finished: Finished
    error: Error
    def __init__(self, session: _Optional[str] = ..., audio_data: _Optional[_Union[AudioData, _Mapping]] = ..., finished: _Optional[_Union[Finished, _Mapping]] = ..., error: _Optional[_Union[Error, _Mapping]] = ...) -> None: ...

class StartSession(_message.Message):
    __slots__ = ("voice",)
    VOICE_FIELD_NUMBER: _ClassVar[int]
    voice: str
    def __init__(self, voice: _Optional[str] = ...) -> None: ...

class PushText(_message.Message):
    __slots__ = ("text",)
    TEXT_FIELD_NUMBER: _ClassVar[int]
    text: str
    def __init__(self, text: _Optional[str] = ...) -> None: ...

class Eos(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AudioData(_message.Message):
    __slots__ = ("audio", "sample_rate", "audio_type", "channel_count")
    AUDIO_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_RATE_FIELD_NUMBER: _ClassVar[int]
    AUDIO_TYPE_FIELD_NUMBER: _ClassVar[int]
    CHANNEL_COUNT_FIELD_NUMBER: _ClassVar[int]
    audio: bytes
    sample_rate: int
    audio_type: AudioType
    channel_count: int
    def __init__(self, audio: _Optional[bytes] = ..., sample_rate: _Optional[int] = ..., audio_type: _Optional[_Union[AudioType, str]] = ..., channel_count: _Optional[int] = ...) -> None: ...

class Finished(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class Error(_message.Message):
    __slots__ = ("session", "message")
    SESSION_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    session: str
    message: str
    def __init__(self, session: _Optional[str] = ..., message: _Optional[str] = ...) -> None: ...
