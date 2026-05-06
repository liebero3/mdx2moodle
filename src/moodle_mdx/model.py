from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AnswerModel:
    text_html: str
    fraction: str


@dataclass(slots=True)
class QuestionModel:
    id: str
    qtype: str
    name: str
    question_html: str
    slot: int
    page: int
    defaultmark: str
    penalty: str
    maxmark: str
    single: bool
    shuffleanswers: bool
    answernumbering: str
    answers: list[AnswerModel] = field(default_factory=list)


@dataclass(slots=True)
class MoodleItem:
    id: str
    type: str
    title: str
    attrs: dict[str, Any]
    body: str = ""
    pages: list[dict[str, Any]] = field(default_factory=list)
    questions: list[QuestionModel] = field(default_factory=list)
    files: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class MoodleSection:
    id: str
    index: int
    title: str
    attrs: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    items: list[MoodleItem] = field(default_factory=list)


@dataclass(slots=True)
class CourseModel:
    course: dict[str, Any]
    backup: dict[str, Any]
    sections: list[MoodleSection]
    format_options: dict[str, Any] = field(default_factory=dict)
