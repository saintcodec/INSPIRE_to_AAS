"""Create AAS *instances* from generated Submodel Templates + values.

Command line (one object -> one AAS with one submodel, JSON + AASX):

    python -m inspire2aas.instance examples/parcel_example.json

Python API (R6) - one submodel + the ConceptDescriptions it uses, to compose your own shells:

    from inspire2aas.instance import build_submodel
    r = build_submodel("output/templates/x/x_templates.json", "SoilBody", values, base_dir=".")
    r.submodel, r.concept_descriptions, r.files, r.warnings, r.errors

Spec file:
{
  "templates": "output/templates/cp_au/cp_au_templates.json",
  "template": "CadastralParcel",
  "codelistNamespaces": {"LandUseClassificationValue": "https://example.org/codes/"},   # optional
  "values": { <idShort>: <value>, ... }
}
Values:
- simple value; MultiLanguageProperty {"de": "...", "en": "..."}; Range {"min": a, "max": b}
- list: [v, v, ...]; collection: {child: value, ...}
- File: {"file": "relative/path.geojson"} or an inline GeoJSON object
- voidable without value: {"nilReason": "unknown" | "unpopulated" | "withheld"}
- reference: "<submodel id>" | {"template": "...", "inspireId": {"namespace": ..., "localId": ...}} | {"uri": "..."}
- codelist value: "code" | {"code": "...", "uri": "...", "broader": "<INSPIRE parent code>"}
Codelist rules (R3):
- code in the INSPIRE Registry -> valueId = Registry URI
- code not in the Registry: closed list -> error; otherwise valueId = given "uri" (or codelistNamespaces + code),
  never an INSPIRE URI; without a URI -> no valueId + warning
- narrower lists: a national value should name its INSPIRE parent ("broader"); it is stored as qualifier
  INSPIRE/broaderValue. Using a structuring INSPIRE value that has narrower values -> warning
"""
import copy
from dataclasses import dataclass, field
import hashlib
import io
import json
import re
import sys
from pathlib import Path

import aas_core3_1.jsonization as jsonization
import aas_core3_1.types as aas_types
import aas_core3_1.verification as verification

from . import config, ids

NIL_REASONS = {"unknown", "unpopulated", "withheld", "other:unpopulated"}


class InstanceError(Exception):
    pass


def ext_ref(uri):
    return {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": uri}]}


def model_ref(sm_id):
    return {"type": "ModelReference", "keys": [{"type": "Submodel", "value": sm_id}]}


@dataclass
class SubmodelResult:
    submodel: dict
    concept_descriptions: list
    files: dict = field(default_factory=dict)      # path inside the AASX -> bytes
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)      # aas-core3.1 verification of submodel + CDs


class Templates:
    """A built template set: the AAS environment + its codelist sidecar."""

    def __init__(self, path_or_env, codelists=None):
        if isinstance(path_or_env, dict):
            self.env, self.path = path_or_env, None
        else:
            self.path = Path(path_or_env)
            if not self.path.is_absolute() and not self.path.exists():
                self.path = config.ROOT / self.path
            self.env = json.loads(self.path.read_text(encoding="utf-8"))
        if codelists is None and self.path is not None:
            side = self.path.with_name(self.path.name.replace("_templates.json", "_codelists.json"))
            codelists = json.loads(side.read_text(encoding="utf-8")) if side.exists() else {}
        self.codelists = codelists or {}
        self.by_short = {s["idShort"]: s for s in self.env["submodels"]}
        self.cds = {c["id"]: c for c in self.env.get("conceptDescriptions", [])}

    def template(self, name):
        if name not in self.by_short:
            raise InstanceError(f"template {name} not found; available: {sorted(self.by_short)}")
        return self.by_short[name]


class Filler:
    def __init__(self, templates: Templates, base_dir, codelist_ns=None):
        self.t = templates
        self.base_dir = Path(base_dir)
        self.codelist_ns = codelist_ns or {}
        self.warnings, self.files, self.used_cds = [], {}, set()
        self.file_dir = "object"   # per-object folder inside the AASX (set by fill_feature)
        self.path_root = ""        # path prefix of the current object (e.g. "SoilBodies[3]/")

    def file_path(self, path, suffix):
        """Unique AASX part name: /aasx/files/<object folder>/<element path><suffix>."""
        local = path[len(self.path_root):] if path.startswith(self.path_root) else path
        name = re.sub(r"[^A-Za-z0-9._-]", "_", local).strip("_") or "file"
        p = f"/aasx/files/{self.file_dir}/{name}{suffix}"
        if p in self.files:
            raise InstanceError(f"{path}: file name {p} is already used in this package")
        return p

    @staticmethod
    def typed(value, value_type, path):
        """Check a value against its xsd type now, so the error names the field (not a verifier path)."""
        s = str(value)
        if not verification.value_consistent_with_xsd_type(s, aas_types.DataTypeDefXSD(value_type)):
            hint = " (xs:dateTime needs a time and zone, e.g. 2023-07-09T00:00:00Z)" if value_type == "xs:dateTime" else ""
            raise InstanceError(f"{path}: '{s}' is not a valid {value_type}{hint}")
        return s

    @staticmethod
    def quals(e):
        return {q["type"]: q.get("value") for q in e.get("qualifiers", [])}

    def strip_template(self, e):
        e.pop("qualifiers", None)
        for k in ("semanticId", "semanticIdListElement"):
            if k in e:
                self.used_cds.add(e[k]["keys"][0]["value"])
        for r in e.get("supplementalSemanticIds", []):
            self.used_cds.add(r["keys"][0]["value"])

    def value_list(self, e):
        cd = self.t.cds.get(e.get("semanticId", {}).get("keys", [{}])[0].get("value"))
        if not cd:
            return None
        vl = cd["embeddedDataSpecifications"][0]["dataSpecificationContent"].get("valueList")
        return {p["value"]: p["valueId"]["keys"][0]["value"] for p in vl["valueReferencePairs"]} if vl else None

    # -------------------------------------------------------------- codelists (R3)
    def codelist_value(self, e, value, path):
        if isinstance(value, dict):
            unknown = set(value) - {"code", "uri", "broader"}
            if unknown or "code" not in value:
                raise InstanceError(f"{path}: codelist value must be a code or {{code, uri?, broader?}}")
            code, uri, broader = str(value["code"]), value.get("uri"), value.get("broader")
        else:
            code, uri, broader = str(value), None, None
        e["value"] = code
        closed = self.value_list(e)
        scheme = e["supplementalSemanticIds"][0]["keys"][0]["value"] if e.get("supplementalSemanticIds") else None
        cl = self.t.codelists.get(scheme) if scheme else None
        known = (cl or {}).get("values", {})
        if closed is not None and code not in closed:
            raise InstanceError(f"{path}: '{code}' is not in the closed codelist {sorted(closed)}")
        if code in known:
            if uri and uri != known[code]["uri"]:
                raise InstanceError(f"{path}: '{code}' is an INSPIRE value with URI {known[code]['uri']}, not {uri}")
            e["valueId"] = ext_ref(known[code]["uri"])
            if cl.get("extensibility") == "narrower" and known[code].get("hasNarrower"):
                self.warnings.append(f"{path}: '{code}' is a structuring value with narrower values in "
                                     f"{scheme.rsplit('/', 1)[-1]}; a narrower value is expected")
            return e
        if closed is not None:   # closed list from CD but code also checked above
            e["valueId"] = ext_ref(closed[code])
            return e
        # national / provider value: never an INSPIRE URI
        list_name = scheme.rsplit("/", 1)[-1] if scheme else ""
        if not uri:
            base = self.codelist_ns.get(scheme) or self.codelist_ns.get(list_name)
            uri = f"{base}{code}" if base else None
        if uri and uri.startswith(config.INSPIRE):
            raise InstanceError(f"{path}: '{code}' is not in the INSPIRE Registry ({list_name}); "
                                f"an INSPIRE URI would claim otherwise: {uri}")
        if uri:
            e["valueId"] = ext_ref(uri)
        else:
            self.warnings.append(f"{path}: national code '{code}' in {list_name or 'codelist'} has no URI -> no valueId")
        if cl and cl.get("extensibility") == "narrower":
            if not broader:
                self.warnings.append(f"{path}: '{code}' is not an INSPIRE value of the narrower list {list_name}; "
                                     f"it should name its INSPIRE parent ('broader')")
            else:
                parent = known.get(str(broader)) or next((v for v in known.values() if v["uri"] == broader), None)
                if parent is None:
                    raise InstanceError(f"{path}: broader '{broader}' is not a value of {list_name}")
                e["qualifiers"] = [{"type": "INSPIRE/broaderValue", "valueType": "xs:anyURI", "kind": "ValueQualifier",
                                    "value": parent["uri"], "valueId": ext_ref(parent["uri"])}]
        elif broader:
            raise InstanceError(f"{path}: 'broader' is only meaningful for narrower lists")
        return e

    # -------------------------------------------------------------- references (R5)
    def reference(self, value, path):
        if isinstance(value, str):
            return model_ref(value)
        if isinstance(value, dict) and set(value) == {"uri"}:
            return ext_ref(value["uri"])
        if isinstance(value, dict) and set(value) == {"template", "inspireId"}:
            tmpl = self.t.template(value["template"])
            iid = value["inspireId"]
            return model_ref(ids.submodel_id(ids.template_prefix(tmpl["id"]), value["template"],
                                             iid["namespace"], iid["localId"]))
        raise InstanceError(f"{path}: reference must be a submodel id, {{uri}} or {{template, inspireId}}")

    # -------------------------------------------------------------- generic fill
    def fill(self, e, value, path):
        """Fill one template element (dict) with value. Returns the instance element or None (omitted)."""
        q = self.quals(e)
        card = q.get(config.Q_CARDINALITY, "ZeroToOne")
        voidable = q.get(config.Q_VOIDABLE) == "true"
        e = copy.deepcopy(e)
        self.strip_template(e)
        if value is None:
            if card in ("One", "OneToMany"):
                if voidable:
                    self.warnings.append(f"{path}: mandatory voidable element not given -> nilReason 'unpopulated'")
                    value = {"nilReason": "unpopulated"}
                else:
                    raise InstanceError(f"{path}: mandatory element missing")
            else:
                return None
        if isinstance(value, dict) and set(value) == {"nilReason"}:
            if not voidable:
                raise InstanceError(f"{path}: nilReason given but element is not voidable")
            if value["nilReason"] not in NIL_REASONS:
                raise InstanceError(f"{path}: nilReason must be one of {sorted(NIL_REASONS)}")
            e["qualifiers"] = [{"type": "INSPIRE/nilReason", "valueType": "xs:string", "kind": "ValueQualifier",
                                "value": value["nilReason"]}]
            if e["modelType"] in ("SubmodelElementList", "SubmodelElementCollection"):
                e.pop("value", None)
            return e
        mt = e["modelType"]
        if mt == "SubmodelElementList":
            items = value if isinstance(value, list) else [value]
            if not items:   # AAS: a list value must be absent or have >= 1 item
                if card == "OneToMany":
                    raise InstanceError(f"{path}: at least one value required")
                return None
            tmpl = e["value"][0]
            e["value"] = []
            for i, v in enumerate(items):
                item = self.fill(dict(tmpl, qualifiers=[{"type": config.Q_CARDINALITY, "valueType": "xs:string",
                                                         "kind": "TemplateQualifier", "value": "One"}]), v, f"{path}[{i}]")
                item.pop("idShort", None)
                e["value"].append(item)
            return e
        if mt == "SubmodelElementCollection":
            known = [c["idShort"] for c in e.get("value", [])]
            if not isinstance(value, dict):
                raise InstanceError(f"{path}: expected an object with {known}")
            unknown = set(value) - set(known)
            if unknown:
                raise InstanceError(f"{path}: unknown fields {sorted(unknown)}; allowed {sorted(known)}")
            if q.get(config.Q_UNION) and len(value) != 1:
                raise InstanceError(f"{path}: exactly one of {sorted(known)} must be given")
            children = [self.fill(c, value.get(c["idShort"]), f"{path}/{c['idShort']}") for c in e.get("value", [])]
            e["value"] = [c for c in children if c is not None]
            return e
        if mt == "Property":
            if e.get("supplementalSemanticIds") or self.value_list(e) is not None:
                return self.codelist_value(e, value, path)
            if isinstance(value, dict):
                raise InstanceError(f"{path}: expected a simple value, got {value}")
            if e["valueType"] == "xs:boolean":
                value = str(bool(value)).lower() if isinstance(value, bool) else str(value).lower()
            e["value"] = self.typed(value, e["valueType"], path)
            return e
        if mt == "Range":
            if not isinstance(value, dict) or not set(value) <= {"min", "max"} or not value:
                raise InstanceError(f"{path}: a range is {{'min': ..., 'max': ...}}")
            for k in ("min", "max"):
                if k in value:
                    e[k] = self.typed(value[k], e["valueType"], f"{path}/{k}")
            return e
        if mt == "MultiLanguageProperty":
            texts = value if isinstance(value, dict) else {"en": value}
            e["value"] = [{"language": k, "text": v} for k, v in texts.items()]
            return e
        if mt == "File":
            if isinstance(value, dict) and "file" in value:
                src = (self.base_dir / value["file"]).resolve()
                data, suffix = src.read_bytes(), src.suffix or ".bin"
            else:
                data, suffix = json.dumps(value, ensure_ascii=False).encode("utf-8"), ".geojson"
            aasx_path = self.file_path(path, suffix)   # unique per object and element (EcoTwin defect 1)
            self.files[aasx_path] = data
            e["value"] = aasx_path
            return e
        if mt == "ReferenceElement":
            e["value"] = self.reference(value, path)
            return e
        raise InstanceError(f"{path}: element type {mt} not supported")


def _verify(env):
    return [f"{e.path}: {e.cause}" for e in verification.verify(jsonization.environment_from_jsonable(env))]


def file_dir(namespace, local_id):
    """Folder for one object's files in an AASX: readable part of the inspireId + short hash
    of the full object key, so different objects never share a folder."""
    key = ids.object_key(namespace, local_id)
    readable = re.sub(r"[^A-Za-z0-9._-]", "_", str(local_id))[:60].strip("_") or "object"
    return f"{readable}_{hashlib.sha1(key.encode('utf-8')).hexdigest()[:8]}"


def fill_feature(f: Filler, tmpl, values, prefix=""):
    """Fill all elements of one feature from its template; the same rules for a single feature
    (build_submodel) and for an item of a collection (build_feature_collection)."""
    where = prefix.rstrip("/") or "values"
    if not isinstance(values, dict):
        raise InstanceError(f"{where}: expected an object with the template's fields")
    known = {e["idShort"] for e in tmpl["submodelElements"]}
    unknown = set(values) - known
    if unknown:
        raise InstanceError(f"{where}: unknown fields {sorted(unknown)}; template has {sorted(known)}")
    iid = values.get("inspireId")
    if not isinstance(iid, dict) or not {"namespace", "localId"} <= set(iid):
        raise InstanceError(f"{where}: inspireId {{namespace, localId}} is required to identify the object")
    f.file_dir, f.path_root = file_dir(iid["namespace"], iid["localId"]), prefix
    elems = [f.fill(e, values.get(e["idShort"]), f"{prefix}{e['idShort']}") for e in tmpl["submodelElements"]]
    f.used_cds.add(tmpl["semanticId"]["keys"][0]["value"])
    return [e for e in elems if e is not None], iid


def _result(t, f, sm):
    cds = [c for c in t.env.get("conceptDescriptions", []) if c["id"] in f.used_cds]
    return SubmodelResult(sm, cds, f.files, f.warnings, _verify({"submodels": [sm], "conceptDescriptions": cds}))


def build_submodel(templates, template, values, base_dir=".", codelist_namespaces=None, codelists=None):
    """One Submodel instance + the ConceptDescriptions it uses (R6). Does not create a shell."""
    t = templates if isinstance(templates, Templates) else Templates(templates, codelists)
    tmpl = t.template(template)
    f = Filler(t, base_dir, codelist_namespaces)
    elems, iid = fill_feature(f, tmpl, values)
    sm = {k: v for k, v in tmpl.items() if k not in ("submodelElements", "kind", "administration")}
    sm.update(id=ids.submodel_id(ids.template_prefix(tmpl["id"]), template, iid["namespace"], iid["localId"]),
              kind="Instance", submodelElements=elems,
              administration={"version": tmpl["administration"]["version"],
                              "revision": tmpl["administration"]["revision"], "templateId": tmpl["id"]})
    return _result(t, f, sm)


def build_feature_collection(templates, template, values_list, submodel_id, id_short, semantic_id=None,
                             list_name="features", base_dir=".", codelist_namespaces=None, codelists=None):
    """Several features of one type as items of one Submodel (R7).

    Submodel (id, idShort, semanticId from the caller)
    └── <list_name>  SubmodelElementList of SMC, semanticIdListElement = the feature concept
        └── [i]      SMC without idShort, semanticId = the feature concept,
                     supplementalSemanticId = the Submodel Template the item follows,
                     children = the template's elements, filled with every rule of build_submodel.
    Errors name the item, e.g. "SoilBodies[3]/beginLifespanVersion: …"."""
    t = templates if isinstance(templates, Templates) else Templates(templates, codelists)
    tmpl = t.template(template)
    if not isinstance(values_list, list) or not values_list:
        raise InstanceError(f"{list_name}: a non-empty list of features is required")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*[A-Za-z0-9_]", list_name) or \
            not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*[A-Za-z0-9_]", id_short):
        raise InstanceError("id_short and list_name must be valid idShorts (letters, digits, '_'; >= 2 characters)")
    concept = tmpl["semanticId"]
    f = Filler(t, base_dir, codelist_namespaces)
    items, seen = [], {}
    for i, values in enumerate(values_list):
        iid = values.get("inspireId") if isinstance(values, dict) else None
        if isinstance(iid, dict) and {"namespace", "localId"} <= set(iid):
            key = ids.object_key(iid["namespace"], iid["localId"])
            if key in seen:
                raise InstanceError(f"{list_name}[{i}]: inspireId is the same as {list_name}[{seen[key]}]")
            seen[key] = i
        elems, _ = fill_feature(f, tmpl, values, f"{list_name}[{i}]/")
        items.append({"modelType": "SubmodelElementCollection", "semanticId": concept,
                      "supplementalSemanticIds": [ext_ref(tmpl["id"])], "value": elems})
    feature_list = {"modelType": "SubmodelElementList", "idShort": list_name, "orderRelevant": False,
                    "typeValueListElement": "SubmodelElementCollection", "semanticIdListElement": concept,
                    "value": items}
    sm = {"modelType": "Submodel", "id": submodel_id, "idShort": id_short, "kind": "Instance",
          "submodelElements": [feature_list]}
    if semantic_id:
        sm["semanticId"] = ext_ref(semantic_id)
    return _result(t, f, sm)


def build_instance(spec_path):
    """Spec file -> AAS environment with one shell and one submodel (command line use)."""
    spec_path = Path(spec_path)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    vals = spec["values"]
    r = build_submodel(spec["templates"], spec["template"], vals, spec_path.parent, spec.get("codelistNamespaces"))
    prefix = ids.template_prefix(r.submodel["administration"]["templateId"])
    ns_, local = vals["inspireId"]["namespace"], vals["inspireId"]["localId"]
    specific = [{"name": "inspireId", "value": f"{ns_}/{local}"}]
    if isinstance(vals.get("nationalCadastralReference"), str):
        specific.append({"name": "nationalCadastralReference", "value": vals["nationalCadastralReference"]})
    short = re.sub(r"[^A-Za-z0-9_]", "_", f"{spec['template']}_{local}")
    shell = {"modelType": "AssetAdministrationShell", "id": ids.aas_id(prefix, ns_, local), "idShort": short,
             "assetInformation": {"assetKind": "Instance", "globalAssetId": ids.asset_id(prefix, ns_, local),
                                  "specificAssetIds": specific},
             "submodels": [model_ref(r.submodel["id"])]}
    env = {"assetAdministrationShells": [shell], "submodels": [r.submodel], "conceptDescriptions": r.concept_descriptions}
    return env, r, _verify(env), short


CONTENT_TYPES = {".geojson": "application/geo+json", ".json": "application/json", ".xml": "application/xml",
                 ".gml": "application/gml+xml", ".pdf": "application/pdf", ".png": "image/png",
                 ".jpg": "image/jpeg", ".tif": "image/tiff", ".tiff": "image/tiff"}


def write_aasx(env, files, aasx_path):
    """Package an AAS environment (dict) + supplementary files (AASX path -> bytes) as AASX.
    The environment part is XML and is named /aasx/data.xml (EcoTwin defect 2: it was called data.json)."""
    from basyx.aas.adapter import aasx
    from basyx.aas.adapter.json import read_aas_json_file
    store = read_aas_json_file(io.StringIO(json.dumps(env)), failsafe=False)
    fc = aasx.DictSupplementaryFileContainer()
    for p, data in files.items():
        fc.add_file(p, io.BytesIO(data), CONTENT_TYPES.get(Path(p).suffix.lower(), "application/octet-stream"))
    with aasx.AASXWriter(str(aasx_path)) as w:
        # write_all_aas_objects: write_aas() would drop ConceptDescriptions referenced via ExternalReference (E04 B3)
        # BaSyx writes XML unless write_json=True, so the part name must end in .xml
        w.write_all_aas_objects("/aasx/data.xml", store, fc)


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)
    try:
        env, r, errors, name = build_instance(argv[0])
    except InstanceError as ex:
        raise SystemExit(f"INPUT ERROR: {ex}")
    out = config.OUTPUT_DIR / "instances" / name
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.json").write_text(json.dumps(env, indent=2, ensure_ascii=False), encoding="utf-8")
    write_aasx(env, r.files, out / f"{name}.aasx")
    print(f"AAS instance: {name}")
    print(f"  submodel id: {r.submodel['id']}")
    print(f"  elements filled: {len(r.submodel['submodelElements'])}, embedded files: {list(r.files)}")
    print(f"  aas-core3.1 verification: {'PASSED (0 errors)' if not errors else errors}")
    for w_ in r.warnings:
        print(f"  WARNING {w_}")
    print(f"  output: {out}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
