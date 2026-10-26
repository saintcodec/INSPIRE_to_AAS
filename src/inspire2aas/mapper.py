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
    codelists: dict = field(default_factory=dict)   # scheme URI -> registry CodeList used by the templates
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
        if not (definition_en or "").strip():   # AASc-3a-008: English definition is mandatory (R4)
            definition_en = pref_en or cd_id.rsplit("/", 1)[-1]
            self.log(path, "definition-missing", f"{cd_id}: no definition in the source; name used instead")
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
        self.codelists[cl.uri] = cl
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
            semantic_id=ext_ref(self.prop_cd(p, path)), semantic_id_list_element=inner.semantic_id,
            value_type_list_element=value_type, order_relevant=p.ordered,
            qualifiers=quals, value=[inner], **common)

    def inner(self, p: Prop, path, depth, stack):
        """-> (sme without idShort, AASSubmodelElements, value type for lists)"""
        tname = p.type_name
        cls = self.model.classes.get(p.type_id) if p.type_id else None
        E = T.AASSubmodelElements
        # 0a. role with an association class -> collection {reference + class attributes} (R2)
        if p.assoc_class_id:
            return self.association_item(p, path, depth, stack), E.SUBMODEL_ELEMENT_COLLECTION, None
        # 0b. ISO 19156 observation -> observation collection that carries the value (R1)
        if cls is not None and cls.name == "OM_Observation":
            return self.observation(p, cls, path), E.SUBMODEL_ELEMENT_COLLECTION, None
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
                self.log(path, "datatype-recursion-cut",
                         f"{cls.name} at depth {depth} ({'cycle' if cls.id in stack else 'depth limit'}) -> xs:string placeholder")
                sid = ext_ref(self.prop_cd(p, path, "STRING"))
                return T.Property(value_type=T.DataTypeDefXSD.STRING, semantic_id=sid), E.PROPERTY, T.DataTypeDefXSD.STRING
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

    # ------------------------------------------------------------------ association classes (R2)
    def association_item(self, p: Prop, path, depth, stack):
        """Association class -> SMC {reference to the target, attributes of the association class}."""
        acls = self.model.classes[p.assoc_class_id]
        target = self.model.classes.get(p.type_id) if p.type_id else None
        ref_name = (target.name[0].lower() + target.name[1:]) if target else "target"
        fc = self.reg.featureconcepts.get(target.name) if target else None
        ref_cd = self.cd(f"{self.ns(acls)}/{ref_name}", ref_name,
                         f"Reference to the {target.name if target else 'target'} at the other end of the "
                         f"association class {acls.name}.", path)
        ref = T.ReferenceElement(
            id_short=self.id_short(ref_name, f"{path}/{ref_name}"), semantic_id=ext_ref(ref_cd),
            qualifiers=[self._card("One"),
                        T.Qualifier(config.Q_TARGET, T.DataTypeDefXSD.STRING, kind=T.QualifierKind.TEMPLATE_QUALIFIER,
                                    value=fc.uri if fc else (target.name if target else "?"))])
        children = [ref] + [self.element(ap, f"{path}/{ap.name}", depth + 1, stack) for ap in flatten(self.model, acls)]
        self.prop_cd(p, path)   # the role itself keeps its CD (used by the surrounding list)
        self.log(path, "association-class-as-collection",
                 f"{acls.name}: role '{p.name}' -> collection {{{ref_name} (reference), "
                 f"{', '.join(ap.name for ap in flatten(self.model, acls))}}}")
        return T.SubmodelElementCollection(semantic_id=ext_ref(self.class_cd(acls, path)), value=children)

    # ------------------------------------------------------------------ observations (R1)
    def _card(self, value):
        return T.Qualifier(config.Q_CARDINALITY, T.DataTypeDefXSD.STRING, kind=T.QualifierKind.TEMPLATE_QUALIFIER, value=value)

    def _leaf(self, sme, id_short, card, owner: Cls, pref, definition, path, data_type=None, quals=()):
        cd_id = self.cd(f"{self.ns(owner)}/{id_short}", pref, definition, f"{path}/{id_short}", data_type)
        sme.id_short, sme.semantic_id = id_short, ext_ref(cd_id)
        sme.qualifiers = [self._card(card)] + list(quals)
        return sme

    def observed_property_codelist(self, owner: Cls):
        """The parameter codelist for observations of `owner`, read from its OCL constraints
        ('observedProperty … oclIsKindOf(<CodeList>)'), searching supertypes too."""
        seen, todo = set(), [owner]
        while todo:
            c = todo.pop(0)
            if c.id in seen:
                continue
            seen.add(c.id)
            for _, ocl in c.constraints:
                m = re.search(r"observedProperty\s*-(?:&gt;|>)\s*oclIsKindOf\(\s*(\w+)\s*\)", ocl or "")
                if m:
                    return next((k for k in self.model.classes.values()
                                 if k.name == m.group(1) and k.category in ("codeList", "enumeration")), None)
            todo += [self.model.classes[s] for s in c.supertypes if s in self.model.classes]
        return None

    def observation(self, p: Prop, om: Cls, path):
        """OM_Observation (ISO 19156) -> collection that stores the observed value.

        observedProperty, result (number | text | range, exactly one), uom, phenomenonTime,
        resultTime, procedure (reference), parameter (list of NamedValue)."""
        owner = self.model.classes[p.owner_id]
        S, D = T.DataTypeDefXSD.STRING, T.DataTypeDefXSD.DOUBLE
        union_q = T.Qualifier(config.Q_UNION, S, kind=T.QualifierKind.TEMPLATE_QUALIFIER,
                              value="exactly one child element shall be given")
        cl = self.observed_property_codelist(owner)
        op = T.Property(value_type=S)
        if cl is not None:
            cl_id, _ = self.codelist_cd(cl, path)
            op.supplemental_semantic_ids = [ext_ref(cl_id)]
            op_def = (f"The property that is observed, a value of the code list {cl.name} "
                      f"(constraint of {owner.name}).")
        else:
            op_def = "The property that is observed."
            self.log(path, "observation-property-codelist-unknown", f"{owner.name}: no OCL constraint names a code list")
        children = [
            self._leaf(op, "observedProperty", "One", om, "observed property", op_def, path, "STRING"),
            self._leaf(T.SubmodelElementCollection(value=[
                self._leaf(T.Property(value_type=D), "number", "ZeroToOne", om, "numeric result",
                           "Result of the observation as a number.", f"{path}/result", None),
                self._leaf(T.Property(value_type=S), "text", "ZeroToOne", om, "text result",
                           "Result of the observation as a character string (e.g. a class code).", f"{path}/result", "STRING"),
                self._leaf(T.Range(value_type=D), "range", "ZeroToOne", om, "range result",
                           "Result of the observation as a range (INSPIRE RangeType: lowerValue, upperValue).",
                           f"{path}/result", None),
            ]), "result", "One", om, "result",
                "Result of the observation. INSPIRE Soil allows Number, CharacterString or RangeType; exactly one is given.",
                path, quals=[union_q]),
            self._leaf(T.Property(value_type=S), "uom", "ZeroToOne", om, "unit of measure",
                       "Unit of measure of a numeric or range result (UCUM code recommended).", path, "STRING"),
            self._leaf(T.Property(value_type=T.DataTypeDefXSD.DATE_TIME), "phenomenonTime", "One", om, "phenomenon time",
                       "Time at which the observed property applies to the feature of interest.", path, "TIMESTAMP"),
            self._leaf(T.Property(value_type=T.DataTypeDefXSD.DATE_TIME), "resultTime", "One", om, "result time",
                       "Time at which the result became available.", path, "TIMESTAMP"),
        ]
        proc_fc = self.reg.featureconcepts.get("Process")
        children.append(self._leaf(
            T.ReferenceElement(), "procedure", "One", om, "procedure",
            "Process used to generate the result (INSPIRE Process, e.g. a method document).", path,
            quals=[T.Qualifier(config.Q_TARGET, S, kind=T.QualifierKind.TEMPLATE_QUALIFIER,
                               value=proc_fc.uri if proc_fc else "Process")]))
        nv = T.SubmodelElementCollection(value=[
            self._leaf(T.Property(value_type=S), "name", "One", om, "parameter name", "Name of the parameter.",
                       f"{path}/parameter", "STRING"),
            self._leaf(T.Property(value_type=S), "value", "One", om, "parameter value",
                       "Value of the parameter (written as text).", f"{path}/parameter", "STRING"),
            self._leaf(T.Property(value_type=S), "uom", "ZeroToOne", om, "parameter unit of measure",
                       "Unit of measure of the parameter value (UCUM code recommended).", f"{path}/parameter", "STRING")])
        nv_cd = self.cd(f"{self.ns(om)}/parameterItem", "named value",
                        "A parameter of the observation, e.g. the reference depth (ISO 19156 NamedValue).", path)
        nv.semantic_id = ext_ref(nv_cd)
        par_cd = self.cd(f"{self.ns(om)}/parameter", "parameter",
                         "Parameters of the observation event, e.g. the depth a value refers to.", path)
        children.append(T.SubmodelElementList(
            type_value_list_element=T.AASSubmodelElements.SUBMODEL_ELEMENT_COLLECTION, id_short="parameter",
            semantic_id=ext_ref(par_cd), semantic_id_list_element=ext_ref(nv_cd), order_relevant=False,
            qualifiers=[self._card("ZeroToMany")], value=[nv]))
        self.log(path, "observation-profile",
                 "OM_Observation -> collection {observedProperty, result(number|text|range), uom, phenomenonTime, "
                 "resultTime, procedure, parameter[]}; featureOfInterest omitted (OCL: = the object itself); "
                 "resultQuality, validTime, metadata, relatedObservation omitted; TM_Object simplified to dateTime; "
                 "NamedValue.value stored as text")
        return T.SubmodelElementCollection(semantic_id=ext_ref(self.prop_cd(p, path)),
                                           supplemental_semantic_ids=[ext_ref(self.class_cd(om, path))],
                                           value=children)

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


def codelist_sidecar(b: "Builder"):
    """Registry codes of every codelist the templates use (valid values only), for the instance builder:
    it must know which codes exist in INSPIRE, also for open lists (R3)."""
    out = {}
    for uri, cl in sorted(b.codelists.items()):
        valid = {k: v for k, v in cl.values.items() if v.status == "valid"}
        parents = {v.broader for v in valid.values() if v.broader}
        out[uri] = dict(
            extensibility=cl.extensibility, registryVersion=b.reg.version,
            values={code: dict(uri=v.uri, broader=v.broader.rsplit("/", 1)[-1] if v.broader else None,
                               hasNarrower=v.uri in parents, label=v.labels.get("en", ""))
                    for code, v in sorted(valid.items())})
    return out


def build(model: Model, reg: Registry, schemas):
    """Build Submodel Templates for all concrete feature types of the given application schemas.
    -> (templates, concept descriptions, loss ledger, codelist sidecar)"""
    b = Builder(model, reg)
    smts = []
    for cls in sorted(model.classes.values(), key=lambda c: (c.schema or "", c.name)):
        if cls.schema in schemas and cls.category == "featureType" and not cls.abstract:
            smts.append(b.smt(cls))
    return smts, list(b.cds.values()), b.ledger, codelist_sidecar(b)
