from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SubmitImageRequest(_message.Message):
    __slots__ = ("image", "min_confidence", "classes")
    IMAGE_FIELD_NUMBER: _ClassVar[int]
    MIN_CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    CLASSES_FIELD_NUMBER: _ClassVar[int]
    image: bytes
    min_confidence: float
    classes: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, image: _Optional[bytes] = ..., min_confidence: _Optional[float] = ..., classes: _Optional[_Iterable[str]] = ...) -> None: ...

class SubmitImageResponse(_message.Message):
    __slots__ = ("job_id",)
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    def __init__(self, job_id: _Optional[str] = ...) -> None: ...

class GetResultRequest(_message.Message):
    __slots__ = ("job_id",)
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    def __init__(self, job_id: _Optional[str] = ...) -> None: ...

class GetResultResponse(_message.Message):
    __slots__ = ("status", "detections", "annotated_image", "error")
    class Status(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = ()
        PENDING: _ClassVar[GetResultResponse.Status]
        DONE: _ClassVar[GetResultResponse.Status]
        FAILED: _ClassVar[GetResultResponse.Status]
    PENDING: GetResultResponse.Status
    DONE: GetResultResponse.Status
    FAILED: GetResultResponse.Status
    STATUS_FIELD_NUMBER: _ClassVar[int]
    DETECTIONS_FIELD_NUMBER: _ClassVar[int]
    ANNOTATED_IMAGE_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    status: GetResultResponse.Status
    detections: _containers.RepeatedCompositeFieldContainer[Detection]
    annotated_image: bytes
    error: str
    def __init__(self, status: _Optional[_Union[GetResultResponse.Status, str]] = ..., detections: _Optional[_Iterable[_Union[Detection, _Mapping]]] = ..., annotated_image: _Optional[bytes] = ..., error: _Optional[str] = ...) -> None: ...

class Detection(_message.Message):
    __slots__ = ("label", "confidence", "x1", "y1", "x2", "y2")
    LABEL_FIELD_NUMBER: _ClassVar[int]
    CONFIDENCE_FIELD_NUMBER: _ClassVar[int]
    X1_FIELD_NUMBER: _ClassVar[int]
    Y1_FIELD_NUMBER: _ClassVar[int]
    X2_FIELD_NUMBER: _ClassVar[int]
    Y2_FIELD_NUMBER: _ClassVar[int]
    label: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int
    def __init__(self, label: _Optional[str] = ..., confidence: _Optional[float] = ..., x1: _Optional[int] = ..., y1: _Optional[int] = ..., x2: _Optional[int] = ..., y2: _Optional[int] = ...) -> None: ...
