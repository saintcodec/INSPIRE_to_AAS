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
import io
import json
import re
import sys
from pathlib import Path

import aas_core3_1.jsonization as jsonization
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
            e["value"] = str(value)
            return e
        if mt == "Range":
            if not isinstance(value, dict) or not set(value) <= {"min", "max"} or not value:
                raise InstanceError(f"{path}: a range is {{'min': ..., 'max': ...}}")
            for k in ("min", "max"):
                if k in value:
                    e[k] = str(value[k])
            return e
        if mt == "MultiLanguageProperty":
            texts = value if isinstance(value, dict) else {"en": value}
            e["value"] = [{"language": k, "text": v} for k, v in texts.items()]
            return e
        if mt == "File":
            if isinstance(value, dict) and "file" in value:
                src = (self.base_dir / value["file"]).resolve()
                data, name = src.read_bytes(), src.name
            else:
                data = json.dumps(value, ensure_ascii=False).encode("utf-8")
                name = f"{path.replace('/', '_')}.geojson"
            aasx_path = f"/aasx/files/{name}"
            self.files[aasx_path] = data
            e["value"] = aasx_path
            return e
        if mt == "ReferenceElement":
            e["value"] = self.reference(value, path)
            return e
        raise InstanceError(f"{path}: element type {mt} not supported")


def _verify(env):
    return [f"{e.path}: {e.cause}" for e in verification.verify(jsonization.environment_from_jsonable(env))]


def build_submodel(templates, template, values, base_dir=".", codelist_namespaces=None, codelists=None):
    """One Submodel instance + the ConceptDescriptions it uses (R6). Does not create a shell."""
    t = templates if isinstance(templates, Templates) else Templates(templates, codelists)
    tmpl = t.template(template)
    known = {e["idShort"] for e in tmpl["submodelElements"]}
    unknown = set(values) - known
    if unknown:
        raise InstanceError(f"unknown fields {sorted(unknown)}; template has {sorted(known)}")
    iid = values.get("inspireId")
    if not isinstance(iid, dict) or not {"namespace", "localId"} <= set(iid):
        raise InstanceError("inspireId {namespace, localId} is required to identify the object")
    f = Filler(t, base_dir, codelist_namespaces)
    elems = [f.fill(e, values.get(e["idShort"]), e["idShort"]) for e in tmpl["submodelElements"]]
    sm = {k: v for k, v in tmpl.items() if k not in ("submodelElements", "kind", "administration")}
    sm.update(id=ids.submodel_id(ids.template_prefix(tmpl["id"]), template, iid["namespace"], iid["localId"]),
              kind="Instance", submodelElements=[e for e in elems if e is not None],
              administration={"version": tmpl["administration"]["version"],
                              "revision": tmpl["administration"]["revision"], "templateId": tmpl["id"]})
    f.used_cds.add(tmpl["semanticId"]["keys"][0]["value"])
    cds = [c for c in t.env.get("conceptDescriptions", []) if c["id"] in f.used_cds]
    errors = _verify({"submodels": [sm], "conceptDescriptions": cds})
    return SubmodelResult(sm, cds, f.files, f.warnings, errors)


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


def write_aasx(env, files, aasx_path):
    from basyx.aas.adapter import aasx
    from basyx.aas.adapter.json import read_aas_json_file
    store = read_aas_json_file(io.StringIO(json.dumps(env)), failsafe=False)
    fc = aasx.DictSupplementaryFileContainer()
    for p, data in files.items():
        fc.add_file(p, io.BytesIO(data), "application/geo+json")
    with aasx.AASXWriter(str(aasx_path)) as w:
        # write_all_aas_objects: write_aas() would drop ConceptDescriptions referenced via ExternalReference (E04 B3)
        w.write_all_aas_objects("/aasx/data.json", store, fc)


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
