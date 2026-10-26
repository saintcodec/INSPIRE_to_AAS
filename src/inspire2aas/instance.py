"""Create an AAS *instance* (e.g. for one cadastral parcel) from a generated Submodel Template + values.

    python -m inspire2aas.instance examples/parcel_example.json

Input JSON (keys are the idShorts of the template):
{
  "templates": "output/templates/cp_au/cp_au_templates.json",
  "template": "CadastralParcel",
  "values": {
    "inspireId": {"namespace": "...", "localId": "..."},
    "label": "...",
    "areaValue": 512.0,
    "geometry": {"file": "parcel.geojson"},        # or an inline GeoJSON object
    "validFrom": {"nilReason": "unknown"},           # voidable property without a value
    "administrativeUnit": "<id of the AdministrativeUnit submodel>",
    "basicPropertyUnit": ["<id>", "<id>"]
  }
}
Rules:
- optional elements without a value are left out
- mandatory (One/OneToMany) elements must be given; if voidable they may be given as {"nilReason": ...}
  (INSPIRE: unknown | unpopulated | withheld); missing mandatory voidable -> nilReason "unpopulated" + warning
- codelist values are given as codes; closed lists are checked, valueId = Registry URI
- template-only qualifiers (SMT/Cardinality, ...) are removed, nilReason is added as a value qualifier
"""
import copy
import json
import re
import sys
from pathlib import Path

import aas_core3_1.jsonization as jsonization
import aas_core3_1.verification as verification

from . import config

NIL_REASONS = {"unknown", "unpopulated", "withheld", "other:unpopulated"}


class InstanceError(Exception):
    pass


def ext_ref(uri):
    return {"type": "ExternalReference", "keys": [{"type": "GlobalReference", "value": uri}]}


def model_ref(sm_id):
    return {"type": "ModelReference", "keys": [{"type": "Submodel", "value": sm_id}]}


class Filler:
    def __init__(self, cds, base_dir):
        self.cds = {c["id"]: c for c in cds}
        self.base_dir = base_dir
        self.warnings = []
        self.files = {}           # aasx path -> bytes
        self.used_cds = set()

    def quals(self, e):
        return {q["type"]: q.get("value") for q in e.get("qualifiers", [])}

    def strip_template(self, e):
        e.pop("qualifiers", None)
        for k in ("semanticId", "semanticIdListElement"):
            if k in e:
                self.used_cds.add(e[k]["keys"][0]["value"])
        for r in e.get("supplementalSemanticIds", []):
            self.used_cds.add(r["keys"][0]["value"])

    def value_list(self, e):
        cd = self.cds.get(e.get("semanticId", {}).get("keys", [{}])[0].get("value"))
        if not cd:
            return None
        content = cd["embeddedDataSpecifications"][0]["dataSpecificationContent"]
        vl = content.get("valueList")
        return {p["value"]: p["valueId"]["keys"][0]["value"] for p in vl["valueReferencePairs"]} if vl else None

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
            if not items and card == "OneToMany":
                raise InstanceError(f"{path}: at least one value required")
            tmpl = e["value"][0]
            e["value"] = []
            for i, v in enumerate(items):
                item = self.fill(dict(tmpl, qualifiers=[{"type": config.Q_CARDINALITY, "valueType": "xs:string",
                                                         "kind": "TemplateQualifier", "value": "One"}]), v, f"{path}[{i}]")
                item.pop("idShort", None)
                e["value"].append(item)
            return e
        if mt == "SubmodelElementCollection":
            if not isinstance(value, dict):
                raise InstanceError(f"{path}: expected an object with {[c['idShort'] for c in e.get('value', [])]}")
            known = {c["idShort"] for c in e.get("value", [])}
            unknown = set(value) - known
            if unknown:
                raise InstanceError(f"{path}: unknown fields {sorted(unknown)}; allowed {sorted(known)}")
            union = q.get(config.Q_UNION)
            if union and len(value) != 1:
                raise InstanceError(f"{path}: union - exactly one of {sorted(known)} must be given")
            children = [self.fill(c, value.get(c["idShort"]), f"{path}/{c['idShort']}") for c in e.get("value", [])]
            e["value"] = [c for c in children if c is not None]
            return e
        if mt == "Property":
            allowed = self.value_list(e)
            if allowed is not None:
                if str(value) not in allowed:
                    raise InstanceError(f"{path}: '{value}' is not in the closed codelist {sorted(allowed)}")
                e["valueId"] = ext_ref(allowed[str(value)])
            elif e.get("supplementalSemanticIds"):     # open codelist: build Registry value URI
                scheme = e["supplementalSemanticIds"][0]["keys"][0]["value"]
                if scheme.startswith(config.INSPIRE) and re.fullmatch(r"[A-Za-z0-9_.\-]+", str(value)):
                    e["valueId"] = ext_ref(f"{scheme}/{value}")
            if e["valueType"] == "xs:boolean":
                value = str(bool(value)).lower() if isinstance(value, bool) else str(value).lower()
            e["value"] = str(value)
            return e
        if mt == "MultiLanguageProperty":
            texts = value if isinstance(value, dict) else {"en": value}
            e["value"] = [{"language": k, "text": v} for k, v in texts.items()]
            return e
        if mt == "File":
            if isinstance(value, dict) and "file" in value:
                src = (self.base_dir / value["file"]).resolve()
                data = src.read_bytes()
                name = src.name
            else:
                data = json.dumps(value, ensure_ascii=False).encode("utf-8")
                name = f"{path.replace('/', '_')}.geojson"
            aasx_path = f"/aasx/files/{name}"
            self.files[aasx_path] = data
            e["value"] = aasx_path
            return e
        if mt == "ReferenceElement":
            e["value"] = model_ref(str(value))
            return e
        raise InstanceError(f"{path}: element type {mt} not supported")


def build_instance(spec_path):
    spec_path = Path(spec_path)
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    tpl_env = json.loads((config.ROOT / spec["templates"]).read_text(encoding="utf-8"))
    tmpl = next((s for s in tpl_env["submodels"] if s["idShort"] == spec["template"]), None)
    if tmpl is None:
        raise InstanceError(f"template {spec['template']} not found in {spec['templates']}")
    vals = spec["values"]
    f = Filler(tpl_env.get("conceptDescriptions", []), spec_path.parent)
    known = {e["idShort"] for e in tmpl["submodelElements"]}
    unknown = set(vals) - known
    if unknown:
        raise InstanceError(f"unknown fields {sorted(unknown)}; template has {sorted(known)}")
    elems = [f.fill(e, vals.get(e["idShort"]), e["idShort"]) for e in tmpl["submodelElements"]]

    ns_, local = vals["inspireId"]["namespace"], vals["inspireId"]["localId"]
    key = re.sub(r"[^A-Za-z0-9_.\-]", "_", f"{re.sub(r'^[a-z]+://', '', ns_).strip('/')}/{local}")
    prefix = tmpl["id"].split("/smt/")[1].split("/")[0]
    sm_id = f"{config.BASE_URI}sm/{prefix}/{spec['template']}/{key}"
    sm = {k: v for k, v in tmpl.items() if k not in ("submodelElements", "kind", "administration")}
    sm.update(id=sm_id, kind="Instance", submodelElements=[e for e in elems if e is not None],
              administration={"version": tmpl["administration"]["version"],
                              "revision": tmpl["administration"]["revision"], "templateId": tmpl["id"]})
    f.used_cds.add(tmpl["semanticId"]["keys"][0]["value"])
    asset_id = f"{config.BASE_URI}asset/{prefix}/{key}"
    specific = [{"name": "inspireId", "value": f"{ns_}/{local}"}]
    if vals.get("nationalCadastralReference"):
        specific.append({"name": "nationalCadastralReference", "value": str(vals["nationalCadastralReference"])})
    short = re.sub(r"[^A-Za-z0-9_]", "_", f"{spec['template']}_{local}")
    shell = {"modelType": "AssetAdministrationShell", "id": f"{config.BASE_URI}aas/{prefix}/{key}", "idShort": short,
             "assetInformation": {"assetKind": "Instance", "globalAssetId": asset_id, "specificAssetIds": specific},
             "submodels": [model_ref(sm_id)]}
    env = {"assetAdministrationShells": [shell], "submodels": [sm],
           "conceptDescriptions": [c for c in tpl_env.get("conceptDescriptions", []) if c["id"] in f.used_cds]}
    env_obj = jsonization.environment_from_jsonable(env)   # raises on structural errors
    errors = [f"{e.path}: {e.cause}" for e in verification.verify(env_obj)]
    return env, f, errors, short


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        raise SystemExit(__doc__)
    try:
        env, f, errors, name = build_instance(argv[0])
    except InstanceError as ex:
        raise SystemExit(f"INPUT ERROR: {ex}")
    out = config.OUTPUT_DIR / "instances" / name
    out.mkdir(parents=True, exist_ok=True)
    jpath = out / f"{name}.json"
    jpath.write_text(json.dumps(env, indent=2, ensure_ascii=False), encoding="utf-8")
    from basyx.aas.adapter import aasx
    from basyx.aas.adapter.json import read_aas_json_file
    with open(jpath, encoding="utf-8") as fh:
        store = read_aas_json_file(fh, failsafe=False)
    files = aasx.DictSupplementaryFileContainer()
    for p, data in f.files.items():
        import io
        files.add_file(p, io.BytesIO(data), "application/geo+json")
    with aasx.AASXWriter(str(out / f"{name}.aasx")) as w:
        # write_all_aas_objects: write_aas() would drop ConceptDescriptions referenced via ExternalReference
        w.write_all_aas_objects("/aasx/data.json", store, files)
    print(f"AAS instance: {name}")
    print(f"  submodel id: {env['submodels'][0]['id']}")
    print(f"  elements filled: {len(env['submodels'][0]['submodelElements'])}, embedded files: {list(f.files)}")
    print(f"  aas-core3.1 verification: {'PASSED (0 errors)' if not errors else errors}")
    for w_ in f.warnings:
        print(f"  WARNING {w_}")
    print(f"  output: {out}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
