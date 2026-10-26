"""Map the intermediate model to AAS v3.1 Submodel Templates (aas-core3.1 objects).

Mapping rules v0 (see docs/mapping_rules.md):
  concrete «featureType"     -> Submodel (kind=Template), inherited properties flattened in
  primitive (CharacterString…) -> Property with xsd value type
  LocalisedCharacterString / PT_FreeText -> MultiLanguageProperty
  GM_* geometry               -> File, contentType application/geo+json
  «codeList» / «enumeration»  -> Property xs:string + ConceptDescription with Registry values
  «dataType» / «union» / «type» (INSPIRE) -> SubmodelElementCollection (recursive, depth-limited)
  «featureType» as value type -> ReferenceElement
  multiplicity upper > 1      -> SubmodelElementList around the element
  multiplicity, voidable, lifeCycleInfo, union, geometry type -> Qualifiers
Everything that is not translated 1:1 is written to the loss ledger.
"""
from dataclasses import dataclass, field
import re

import aas_core3_1.types as T

from . import config
from .model import Cls, Model, Prop
from .registry import Registry
from .xmi_reader import flatten

IEC61360_SPEC = "https://admin-shell.io/DataSpecificationTemplates/DataSpecificationIec61360/3/0"
UML_TO_REG_EXT = {"none": "none", "narrower": "narrower", "any": "open", "open": "open"}  # E03 C1

MAX_NAME, MAX_TEXT, MAX_PREF = 128, 1023, 255


def ext_ref(uri):
    return T.Reference(T.ReferenceTypes.EXTERNAL_REFERENCE, [T.Key(T.KeyTypes.GLOBAL_REFERENCE, uri)])


def model_ref_submodel(sm_id):
    return T.Reference(T.ReferenceTypes.MODEL_REFERENCE, [T.Key(T.KeyTypes.SUBMODEL, sm_id)])


@dataclass
class Builder:
    model: Model
    reg: Registry
    cds: dict = field(default_factory=dict)      # id -> ConceptDescription
    ledger: list = field(default_factory=list)
    _ctx: dict = field(default_factory=dict)

    # ------------------------------------------------------------------ helpers
    def log(self, path, kind, detail):
        row = dict(schema=self._ctx.get("schema", ""), smt=self._ctx.get("smt", ""),
                   path=path, kind=kind, detail=detail)
        if row not in self.ledger:
            self.ledger.append(row)

    def prefix(self, schema):
        return self.reg.schema_prefix.get(schema) or re.sub(r"[^a-z0-9]", "", schema.lower())

    def version(self, schema):
        return self.model.schemas[schema].version if schema in self.model.schemas else ""

    def ns(self, cls: Cls):
        s = cls.schema or "external"
        return f"{config.BASE_URI}cd/{self.prefix(s)}/{self.version(s) or '0'}/{cls.name}"

    def text(self, s, limit, path, what):
        s = re.sub(r"\s+", " ", s or "").strip()
        if len(s) > limit:
            self.log(path, "text-truncated", f"{what}: {len(s)} > {limit} characters")
            s = s[: limit - 1] + "…"
        return s

    def id_short(self, name, path):
        s = re.sub(r"[^A-Za-z0-9_]", "_", name)
        if not re.match(r"[A-Za-z]", s):
            s = "x" + s
        if len(s) < 2:  # AAS 3.1 idShort pattern requires >= 2 characters
            s = s + "_"
        if s != name:
            self.log(path, "idShort-renamed", f"{name!r} -> {s!r}")
        return s

    # ------------------------------------------------------------------ concept descriptions
    def cd(self, cd_id, pref_en, definition_en, path, data_type=None, pref_de="", def_de="",
           value_list=None, note="", short=""):
        if cd_id in self.cds:
            return cd_id
        pref = [T.LangStringPreferredNameTypeIEC61360("en", self.text(pref_en, MAX_PREF, path, "preferredName") or "n/a")]
        if pref_de:
            pref.append(T.LangStringPreferredNameTypeIEC61360("de", self.text(pref_de, MAX_PREF, path, "preferredName@de")))
        definition = None
        if definition_en or def_de:
            definition = []
            if definition_en:
                definition.append(T.LangStringDefinitionTypeIEC61360("en", self.text(definition_en, MAX_TEXT, path, "definition")))
            if def_de:
                definition.append(T.LangStringDefinitionTypeIEC61360("de", self.text(def_de, MAX_TEXT, path, "definition@de")))
        content = T.DataSpecificationIEC61360(
            preferred_name=pref, definition=definition,
            data_type=T.DataTypeIEC61360(data_type) if data_type else None,
            value_list=value_list)
        self.cds[cd_id] = T.ConceptDescription(
            id=cd_id,
            id_short=self.id_short(short or cd_id.rstrip("/").rsplit("/", 1)[-1], path + "#cd"),
            description=[T.LangStringTextType("en", self.text(note, MAX_TEXT, path, "cd note"))] if note else None,
            embedded_data_specifications=[T.EmbeddedDataSpecification(ext_ref(IEC61360_SPEC), content)])
        return cd_id

    def class_cd(self, cls: Cls, path):
        fc = self.reg.featureconcepts.get(cls.name) if cls.category == "featureType" else None
        cd_id = fc.uri if fc else self.ns(cls)
        return self.cd(cd_id, (fc.labels.get("en") if fc else "") or cls.doc.name or cls.name,
                       cls.doc.definition or (fc.definitions.get("en", "") if fc else ""), path,
                       pref_de=fc.labels.get("de", "") if fc else "",
                       def_de=fc.definitions.get("de", "") if fc else "")

    def codelist_cd(self, cls: Cls, path):
        """CD for a codelist; Registry is authoritative (decision 2026-10-26)."""
        cl = self.reg.codelist(cls.name, cls.tags.get("vocabulary", ""))
        path = f"codelist:{cls.name}"  # log codelist findings once per list, not per use
        uml_ext = (cls.tags.get("extensibility") or cls.tags.get("extensiblity") or cls.tags.get("extensibilty") or "").strip()
        if cl is None:
            self.log(path, "codelist-not-in-registry", cls.name)
            return self.cd(self.ns(cls), cls.doc.name or cls.name, cls.doc.definition, path,
                           note=f"INSPIRE codelist {cls.name}; not found in the INSPIRE Registry "
                                f"(UML extensibility: {uml_ext or 'missing'})."), None
        reg_ext = cl.extensibility
        if not uml_ext:
            self.log(path, "codelist-extensibility-missing-in-uml", f"{cls.name}: Registry says {reg_ext}")
        elif UML_TO_REG_EXT.get(uml_ext) != reg_ext and not (UML_TO_REG_EXT.get(uml_ext) == "open" and reg_ext == "any"):
            self.log(path, "codelist-extensibility-conflict",
                     f"{cls.name}: UML '{uml_ext}' vs Registry '{reg_ext}' -> Registry used")
        valid = {k: v for k, v in cl.values.items() if v.status == "valid"}
        vl = None
        if reg_ext == "none" and valid:
            vl = T.ValueList([T.ValueReferencePair(code, ext_ref(v.uri)) for code, v in sorted(valid.items())])
        note = (f"INSPIRE codelist {cl.uri} (Registry version {self.reg.version}); extensibility '{reg_ext}' "
                f"({'closed list' if reg_ext == 'none' else 'values may be extended by data providers'}); "
                f"{len(valid)} valid values.")
        return self.cd(cl.uri, cl.labels.get("en") or cls.name, cl.definitions.get("en", ""), path,
                       data_type="STRING", pref_de=cl.labels.get("de", ""), def_de=cl.definitions.get("de", ""),
                       value_list=vl, note=note), vl

    def prop_cd(self, p: Prop, path, data_type=None, value_list=None):
        owner = self.model.classes[p.owner_id]
        return self.cd(f"{self.ns(owner)}/{p.name}", p.doc.name or p.name, p.doc.definition, path,
                       data_type=data_type, value_list=value_list)

    # ------------------------------------------------------------------ elements
    @staticmethod
    def cardinality(lo, hi):
        many = hi == "*" or (hi.isdigit() and int(hi) > 1)
        if lo == "0":
            return "ZeroToMany" if many else "ZeroToOne"
        return "OneToMany" if many else "One"

    def qualifiers(self, p: Prop, path, union_member=False):
        lo, hi = ("0", p.upper) if union_member else (p.lower, p.upper)
        card = self.cardinality(lo, hi)
        if hi not in ("1", "*") or lo not in ("0", "1"):
            self.log(path, "multiplicity-approximated", f"[{lo}..{hi}] -> {card}")
        q = [T.Qualifier(config.Q_CARDINALITY, T.DataTypeDefXSD.STRING, kind=T.QualifierKind.TEMPLATE_QUALIFIER, value=card)]
        if p.voidable:
            q.append(T.Qualifier(config.Q_VOIDABLE, T.DataTypeDefXSD.BOOLEAN, kind=T.QualifierKind.TEMPLATE_QUALIFIER, value="true"))
        if p.lifecycle:
            q.append(T.Qualifier(config.Q_LIFECYCLE, T.DataTypeDefXSD.BOOLEAN, kind=T.QualifierKind.TEMPLATE_QUALIFIER, value="true"))
        return q

    def element(self, p: Prop, path, depth=0, stack=(), union_member=False):
        """Return the SME for property p (with idShort, qualifiers; wrapped in a list if multi-valued)."""
        inner, list_type, value_type = self.inner(p, path, depth, stack)
        common = dict(display_name=[T.LangStringNameType("en", self.text(p.doc.name or p.name, MAX_NAME, path, "displayName"))],
                      description=[T.LangStringTextType("en", self.text(p.doc.definition, MAX_TEXT, path, "description"))]
                      if p.doc.definition else None)
        quals = self.qualifiers(p, path, union_member)
        many = p.upper == "*" or (p.upper.isdigit() and int(p.upper) > 1)
        if not many:
            inner.id_short = self.id_short(p.name, path)
            inner.qualifiers = (inner.qualifiers or []) + quals
            inner.display_name, inner.description = common["display_name"], common["description"]
            return inner
        return T.SubmodelElementList(
            type_value_list_element=list_type, id_short=self.id_short(p.name, path),
            semantic_id=inner.semantic_id, semantic_id_list_element=inner.semantic_id,
            value_type_list_element=value_type, order_relevant=p.ordered,
            qualifiers=quals, value=[inner], **common)

    def inner(self, p: Prop, path, depth, stack):
        """-> (sme without idShort, AASSubmodelElements, value type for lists)"""
        tname = p.type_name
        cls = self.model.classes.get(p.type_id) if p.type_id else None
        E = T.AASSubmodelElements
        # 1. primitives
        if tname in config.PRIMITIVES:
            kind, xsd = config.PRIMITIVES[tname]
            if kind == "mlp":
                sid = ext_ref(self.prop_cd(p, path, "STRING_TRANSLATABLE"))
                return T.MultiLanguageProperty(semantic_id=sid), E.MULTI_LANGUAGE_PROPERTY, None
            if tname in config.MEASURES:
                self.log(path, "measure-unit-not-fixed", f"{tname}: value as xs:double, unit of measure left to the instance")
            vt = T.DataTypeDefXSD(xsd)
            sid = ext_ref(self.prop_cd(p, path, config.XSD_TO_IEC.get(xsd)))
            return T.Property(value_type=vt, semantic_id=sid), E.PROPERTY, vt
        # 2. geometry
        if tname.startswith(("GM_", "TP_")):
            sid = ext_ref(self.prop_cd(p, path, "FILE"))
            q = [T.Qualifier(config.Q_GEOMETRY, T.DataTypeDefXSD.STRING, kind=T.QualifierKind.TEMPLATE_QUALIFIER, value=tname)]
            self.log(path, "geometry-as-geojson", f"{tname} -> File {config.GEOMETRY_CONTENT_TYPE}")
            return T.File(content_type=config.GEOMETRY_CONTENT_TYPE, semantic_id=sid, qualifiers=q), E.FILE, None
        # 3. codelists
        if cls is not None and cls.category in ("codeList", "enumeration"):
            cl_id, vl = self.codelist_cd(cls, path)
            sid = ext_ref(self.prop_cd(p, path, "STRING", value_list=vl))
            return (T.Property(value_type=T.DataTypeDefXSD.STRING, semantic_id=sid,
                               supplemental_semantic_ids=[ext_ref(cl_id)]), E.PROPERTY, T.DataTypeDefXSD.STRING)
        # 4. references to other spatial objects
        if cls is not None and cls.category == "featureType":
            target = self.reg.featureconcepts.get(cls.name)
            q = [T.Qualifier(config.Q_TARGET, T.DataTypeDefXSD.STRING, kind=T.QualifierKind.TEMPLATE_QUALIFIER,
                             value=target.uri if target else cls.name)]
            sid = ext_ref(self.prop_cd(p, path))
            return T.ReferenceElement(semantic_id=sid, qualifiers=q), E.REFERENCE_ELEMENT, None
        # 5. structured INSPIRE types -> collection
        if cls is not None and cls.schema is not None and cls.category in ("dataType", "union", "type"):
            if cls.id in stack or depth >= config.DATATYPE_MAX_DEPTH:
                self.log(path, "datatype-recursion-cut", f"{cls.name} at depth {depth} -> xs:string placeholder")
            else:
                children = []
                for cp in flatten(self.model, cls):
                    children.append(self.element(cp, f"{path}/{cp.name}", depth + 1, stack + (cls.id,),
                                                 union_member=cls.category == "union"))
                sid = ext_ref(self.prop_cd(p, path))
                q = None
                if cls.category == "union":
                    q = [T.Qualifier(config.Q_UNION, T.DataTypeDefXSD.STRING, kind=T.QualifierKind.TEMPLATE_QUALIFIER,
                                     value="exactly one child element shall be given")]
                    self.log(path, "union-xor-not-enforced", f"{cls.name}: 'exactly one of' only as qualifier")
                return (T.SubmodelElementCollection(semantic_id=sid, supplemental_semantic_ids=[ext_ref(self.class_cd(cls, path))],
                                                    qualifiers=q, value=children or None),
                        E.SUBMODEL_ELEMENT_COLLECTION, None)
        # 6. everything else: external (ISO) or unresolved types -> string placeholder
        reason = "unresolved type" if cls is None else f"external {cls.category} '{cls.name}' (not an INSPIRE schema type)"
        if cls is not None and cls.category == "featureType":
            reason = "feature type"
        self.log(path, "type-placeholder", f"{tname or '<no type>'}: {reason} -> xs:string")
        sid = ext_ref(self.prop_cd(p, path, "STRING"))
        return T.Property(value_type=T.DataTypeDefXSD.STRING, semantic_id=sid), E.PROPERTY, T.DataTypeDefXSD.STRING

    # ------------------------------------------------------------------ submodel templates
    def smt(self, cls: Cls) -> T.Submodel:
        schema = cls.schema
        self._ctx = dict(schema=schema, smt=cls.name)
        ver = self.version(schema)
        parts = (ver.split(".") + ["0"])[:3]
        if len(ver.split(".")) > 2:
            self.log(cls.name, "schema-version-patch-dropped",
                     f"schema version {ver} -> AAS version {parts[0]} revision {parts[1]}")
        fc = self.reg.featureconcepts.get(cls.name)
        sem = self.class_cd(cls, cls.name)
        elems = [self.element(p, f"{cls.name}/{p.name}") for p in flatten(self.model, cls)]
        for k, (name, ocl) in enumerate(cls.constraints):
            self.log(cls.name, "ocl-constraint-not-translated", name)
        display = [T.LangStringNameType("en", self.text((fc.labels.get("en") if fc else "") or cls.name, MAX_NAME, cls.name, "name"))]
        if fc and fc.labels.get("de"):
            display.append(T.LangStringNameType("de", self.text(fc.labels["de"], MAX_NAME, cls.name, "name@de")))
        return T.Submodel(
            id=f"{config.BASE_URI}smt/{self.prefix(schema)}/{ver}/{cls.name}",
            id_short=self.id_short(cls.name, cls.name), kind=T.ModellingKind.TEMPLATE,
            display_name=display,
            description=[T.LangStringTextType("en", self.text(cls.doc.definition, MAX_TEXT, cls.name, "description"))]
            if cls.doc.definition else None,
            administration=T.AdministrativeInformation(version=parts[0], revision=parts[1]),
            semantic_id=ext_ref(sem),
            submodel_elements=elems)


def build(model: Model, reg: Registry, schemas):
    """Build Submodel Templates for all concrete feature types of the given application schemas."""
    b = Builder(model, reg)
    smts = []
    for cls in sorted(model.classes.values(), key=lambda c: (c.schema or "", c.name)):
        if cls.schema in schemas and cls.category == "featureType" and not cls.abstract:
            smts.append(b.smt(cls))
    return smts, list(b.cds.values()), b.ledger
