"""Intermediate model: a tool-neutral picture of the INSPIRE UML model."""
from dataclasses import dataclass, field


@dataclass
class Doc:
    name: str = ""         # "-- Name --" block (human readable name)
    definition: str = ""   # "-- Definition --" block
    description: str = ""  # "-- Description --" block


@dataclass
class Prop:
    name: str
    kind: str              # "attr" | "role"
    lower: str
    upper: str             # "1", "*", "2", ...
    type_name: str
    type_id: str | None    # id of the resolved class, None if external/unresolved
    voidable: bool = False
    lifecycle: bool = False
    ordered: bool = False
    doc: Doc = field(default_factory=Doc)
    owner_id: str = ""     # class that defines the property (relevant after flattening)


@dataclass
class Cls:
    id: str
    name: str
    category: str          # featureType | dataType | union | codeList | enumeration | type | primitive | other
    abstract: bool
    schema: str | None     # application schema name, None for ISO / foundation outside schemas
    supertypes: list = field(default_factory=list)   # class ids
    props: list = field(default_factory=list)        # own properties (Prop)
    values: list = field(default_factory=list)       # codelist values held in the UML
    constraints: list = field(default_factory=list)  # (name, OCL text)
    tags: dict = field(default_factory=dict)
    doc: Doc = field(default_factory=Doc)


@dataclass
class Schema:
    name: str
    version: str
    prefix: str = ""       # Registry short name, e.g. "cp"


@dataclass
class Model:
    schemas: dict          # name -> Schema
    classes: dict          # id -> Cls
    issues: list           # reader-level anomalies (dicts)

    def by_name(self, schema, name):
        return next(c for c in self.classes.values() if c.schema == schema and c.name == name)
