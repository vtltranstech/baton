"""What a diagram says, independent of how it is drawn. The SVG and Mermaid writers both read these."""

from __future__ import annotations

from dataclasses import dataclass, field

# Status of an element in a story: what the reader must look at.
NEW, CHANGED, REMOVED, IMPACTED, TOUCHED, CONTEXT = (
    "new",
    "changed",
    "removed",
    "impacted",
    "touched",
    "context",
)
STATUSES = (NEW, CHANGED, REMOVED, IMPACTED, TOUCHED, CONTEXT)
RANK = {NEW: 0, REMOVED: 1, CHANGED: 2, IMPACTED: 3, TOUCHED: 4, CONTEXT: 5}


def strongest(*statuses: str) -> str:
    present = [s for s in statuses if s]
    return min(present, key=lambda s: RANK[s]) if present else CONTEXT


# -- flow (architecture views and the story's flow with impacts) ------------------------------------------


@dataclass
class Lane:
    id: str
    title: str
    sub: str = ""


@dataclass
class Node:
    id: str
    label: str
    kind: str = "component"  # component | screen | store | queue | file | external | person | job | container
    status: str = CONTEXT
    sub: str = ""  # one short line under the label: stereotype, technology or file:lines
    lane: str = ""


@dataclass
class Link:
    src: str
    dst: str
    label: str = ""
    status: str = CONTEXT
    style: str = "sync"  # sync | async | data
    labels: list[str] = field(default_factory=list)  # every label merged into this link


def merge_label(link: Link, label: str) -> None:
    """Several calls on one arrow: the first two by name, then +n."""
    if not link.labels and link.label:
        link.labels.append(link.label)
    if label and label not in link.labels:
        link.labels.append(label)
    extra = len(link.labels) - 2
    link.label = " / ".join(link.labels[:2]) + (f" +{extra}" if extra > 0 else "")


@dataclass
class Flow:
    title: str
    subtitle: str = ""
    lanes: list[Lane] = field(default_factory=list)
    nodes: list[Node] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)
    caption: str = ""


# -- sequence ----------------------------------------------------------------------------------------------


@dataclass
class Participant:
    id: str
    label: str
    sub: str = ""
    kind: str = "component"  # component | person | screen | store | queue | file | external
    status: str = TOUCHED


@dataclass
class Message:
    src: str
    dst: str
    label: str
    kind: str = "sync"  # sync | async | return | error
    status: str = TOUCHED
    note: str = ""  # shown to the right of the arrow's target, e.g. "-> impacts ledger-service"


@dataclass
class Fragment:
    kind: str  # alt | opt | loop
    label: str
    first: int  # index into messages, inclusive
    last: int


@dataclass
class Sequence:
    title: str
    subtitle: str = ""
    participants: list[Participant] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    fragments: list[Fragment] = field(default_factory=list)
    caption: str = ""


# -- class / data model ------------------------------------------------------------------------------------


@dataclass
class Member:
    text: str
    status: str = ""  # "" | new | changed | removed
    kind: str = "method"  # field | method | key


@dataclass
class Box:
    id: str
    name: str
    stereo: str = ""
    status: str = CONTEXT
    sub: str = ""
    fields: list[Member] = field(default_factory=list)
    methods: list[Member] = field(default_factory=list)
    collapsed: bool = False


@dataclass
class Relation:
    src: str
    dst: str
    kind: str = "uses"  # uses | implements | extends | creates
    label: str = ""
    status: str = CONTEXT


@dataclass
class ClassDiagram:
    title: str
    subtitle: str = ""
    boxes: list[Box] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    entity: bool = False  # draw as a data model: no methods compartment, keys marked
    caption: str = ""


# -- use cases ---------------------------------------------------------------------------------------------


@dataclass
class Actor:
    id: str
    label: str
    kind: str = "person"  # person | system
    side: str = "left"


@dataclass
class UseCase:
    id: str
    label: str
    status: str = TOUCHED
    sub: str = ""


@dataclass
class UseCaseLink:
    src: str  # an actor or a use case
    dst: str  # a use case
    kind: str = "assoc"  # assoc | include | extend


@dataclass
class UseCaseDiagram:
    title: str
    subtitle: str = ""
    system: str = ""
    actors: list[Actor] = field(default_factory=list)
    cases: list[UseCase] = field(default_factory=list)
    links: list[UseCaseLink] = field(default_factory=list)
    caption: str = ""
