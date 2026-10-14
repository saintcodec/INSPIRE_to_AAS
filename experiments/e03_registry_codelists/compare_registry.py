"""E03 - Codelists: UML model (XMI) vs INSPIRE Registry (EU Vocabularies RDF dump).

Matches every «codeList»/«enumeration» of the XMI application schemas with a Registry
concept scheme (by the `vocabulary` tag URI, else by name) and compares:
existence, extensibility (with the vocabulary difference resolved, see README),
values held in the UML vs values in the Registry.
For the 5 test themes it also compares the mapping-table (xls) labels with Registry labels.

Usage:  python compare_registry.py  -> results/*.csv + summary on stdout
"""
from collections import Counter, defaultdict
from pathlib import Path
import csv
import re
import sys

import xlrd
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "e01_source_inventory"))
from xmi_load import load, NS, XMI_ID, XMI_IDREF, XMI_TYPE, ROOT  # noqa: E402
from inventory import stereotypes, tags  # noqa: E402

REG_DIR = ROOT / "data/raw/INSPIRE Registry"
MAP_DIR = ROOT / "data/raw/approved/mapping"
OUT = Path(__file__).parent / "results"
RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
SKOS = "{http://www.w3.org/2004/02/skos/core#}"
REGM = "{http://inspire.ec.europa.eu/registry/model/ontology#}"
OWL = "{http://www.w3.org/2002/07/owl#}"
LANG = "{http://www.w3.org/XML/1998/namespace}lang"
BASE = "http://inspire.ec.europa.eu/codelist/"

# The same words mean different things (see README, finding C1):
#   UML tag  'any'  = extensible at any level      == Registry 'open'
#   Registry 'any'  = empty list, provider defines all values (no UML equivalent)
UML_TO_COMMON = {"none": "closed", "narrower": "narrower", "any": "extensible", "open": "extensible"}
REG_TO_COMMON = {"none": "closed", "narrower": "narrower", "open": "extensible", "any": "empty(extensible)"}

TEST_THEMES = {"AdministrativeUnits": "AdministrativeUnitsMappingTable.xls",
               "CadastralParcels": "CadastralParcelsMappingTable.xls",
               "Soil": "SoilMappingTable.xls",
               "LandCoverVector": "LandCoverMappingTable.xls",
               "Existing Land Use": "LandUseMappingTable.xls"}


def res(el, tag):
    x = el.find(tag)
    return x.get(RDF + "resource") if x is not None else None


def read_registry(fname):
    root = etree.parse(str(REG_DIR / fname), etree.XMLParser(huge_tree=True)).getroot()
    schemes, values = {}, defaultdict(dict)
    version = None
    for d in root:
        uri = d.get(RDF + "about")
        types = {t.get(RDF + "resource").split("#")[-1] for t in d.findall(RDF + "type")}
        en = next((p.text for p in d.findall(SKOS + "prefLabel") if p.get(LANG) == "en"), None)
        status = (res(d, REGM + "status") or "").rsplit("/", 1)[-1]
        if types & {"CodeListConceptScheme", "EnumerationConceptScheme", "AbstractCodelist"} or \
                ("ConceptScheme" in types and "RegisterConceptScheme" not in types):
            ext = res(d, REGM + "extensibility")
            schemes[uri] = dict(label=en, status=status, extensibility=ext.rsplit("/", 1)[-1] if ext else "",
                                abstract="AbstractCodelist" in types,
                                schema=(res(d, REGM + "applicationSchema") or "").rsplit("/", 1)[-1])
            version = version or d.findtext(OWL + "versionInfo")
        elif types & {"CodeListValue", "EnumerationValue", "Concept"}:
            for s in d.findall(SKOS + "inScheme"):
                sch = s.get(RDF + "resource")
                if sch and sch.count("/") > BASE.count("/") - 1 and sch != BASE.rstrip("/"):
                    values[sch][uri.rsplit("/", 1)[-1]] = dict(label=en, status=status,
                                                               broader=res(d, SKOS + "broader"))
    return schemes, values, version


def read_xmi_codelists():
    root, _ = load()
    model = root.find(f"{{{NS['uml']}}}Model")
    ext = root.find(f"{{{NS['xmi']}}}Extension")
    ea = {e.get(XMI_IDREF): e for e in ext.find("elements")}
    parent, pkg_name = {}, {}
    for p in model.iter("packagedElement"):
        if p.get(XMI_TYPE) == "uml:Package":
            pkg_name[p.get(XMI_ID)] = p.get("name")
            for c in p:
                if c.tag == "packagedElement":
                    parent[c.get(XMI_ID)] = p.get(XMI_ID)
    schemas = {pid: n for pid, n in pkg_name.items()
               if ea.get(pid) is not None and "applicationschema" in stereotypes(ea[pid])}

    def schema_of(eid):
        p = parent.get(eid)
        while p is not None and p not in schemas:
            p = parent.get(p)
        return schemas.get(p)

    out = []
    for c in model.iter("packagedElement"):
        e = ea.get(c.get(XMI_ID))
        if e is None:
            continue
        st = stereotypes(e)
        kind = next((s for s in st if s in ("codelist", "code list", "enumeration")), None)
        if kind is None or schema_of(c.get(XMI_ID)) is None:
            continue
        t = tags(e)
        vals = [a.get("name").strip() for a in c.findall("ownedAttribute") if a.get("name")] + \
               [lit.get("name").strip() for lit in c.findall("ownedLiteral") if lit.get("name")]
        # tag names with typos seen in E01 (F6)
        extv = t.get("extensibility") or t.get("extensiblity") or t.get("extensibilty") or ""
        out.append(dict(schema=schema_of(c.get(XMI_ID)), name=(c.get("name") or "").strip(),
                        kind="enumeration" if kind == "enumeration" else "codelist",
                        vocabulary=(t.get("vocabulary") or "").strip(), extensibility=extv.strip(),
                        uml_values=vals))
    return out


def read_xls_labels(xls):
    book = xlrd.open_workbook(str(MAP_DIR / xls))
    sh = next(s for s in book.sheets() if s.name.lower().startswith("codelist"))
    out, cur = {}, None
    for r in range(2, sh.nrows):
        row = sh.row_values(r)
        if str(row[0]).strip():
            cur = re.sub(r"\s+", "", str(row[0]).split("\n")[0])
            out[cur] = []
        if cur and str(row[2]).strip():
            out[cur].append(str(row[2]).strip())
    return out


def squash(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def main():
    cl_s, cl_v, cl_ver = read_registry("inspire-codelist.rdf")
    en_s, en_v, en_ver = read_registry("inspire-enumeration.rdf")
    schemes = {**cl_s, **en_s}
    values = {**cl_v, **en_v}
    xmi = read_xmi_codelists()
    OUT.mkdir(parents=True, exist_ok=True)
    summary = Counter()
    rows, value_rows = [], []
    matched_schemes = set()
    for c in xmi:
        uri = None
        how = ""
        if c["vocabulary"] in schemes:
            uri, how = c["vocabulary"], "vocabulary-tag"
        elif BASE + c["name"] in schemes:
            uri, how = BASE + c["name"], "name"
        elif "http://inspire.ec.europa.eu/enumeration/" + c["name"] in schemes:
            uri, how = "http://inspire.ec.europa.eu/enumeration/" + c["name"], "name"
        if c["vocabulary"] and c["vocabulary"] not in schemes:
            summary["vocabulary tag not a registry scheme"] += 1
        s = schemes.get(uri) if uri else None
        if s:
            matched_schemes.add(uri)
        reg_vals = values.get(uri, {}) if uri else {}
        valid = {k for k, v in reg_vals.items() if v["status"] == "valid"}
        uml_ext = UML_TO_COMMON.get(c["extensibility"], "<missing>" if not c["extensibility"] else c["extensibility"])
        reg_ext = REG_TO_COMMON.get(s["extensibility"], "<missing>") if s else ""
        if not s:
            ext_cmp = "NO_REGISTRY_ENTRY"
        elif uml_ext == "<missing>":
            ext_cmp = "UML_MISSING"
        elif uml_ext == reg_ext or (uml_ext == "extensible" and reg_ext == "empty(extensible)"):
            ext_cmp = "AGREE"
        else:
            ext_cmp = "CONFLICT"
        summary[f"match:{how or 'NONE'}"] += 1
        summary[f"extensibility:{ext_cmp}"] += 1
        uml_set = set(c["uml_values"])
        if c["uml_values"] and s:
            vcmp = "SAME" if uml_set == valid else "DIFF"
            summary[f"uml-values-vs-registry:{vcmp}"] += 1
        else:
            vcmp = "UML_EMPTY" if s else ""
        rows.append(dict(schema=c["schema"], codelist=c["name"], kind=c["kind"], matched_by=how,
                         registry_uri=uri or "", registry_status=s["status"] if s else "",
                         uml_extensibility=c["extensibility"], registry_extensibility=s["extensibility"] if s else "",
                         extensibility_check=ext_cmp, n_uml_values=len(c["uml_values"]),
                         n_registry_values_valid=len(valid), n_registry_values_all=len(reg_vals),
                         values_check=vcmp,
                         uml_only=" | ".join(sorted(uml_set - set(reg_vals))) if s else "",
                         registry_only=" | ".join(sorted(valid - uml_set)) if s and c["uml_values"] else ""))
    unmatched_reg = [u for u in schemes if u not in matched_schemes]
    summary["registry schemes not used by any XMI codelist"] = len(unmatched_reg)

    # mapping-table labels vs registry labels for the test themes
    for schema, xls in TEST_THEMES.items():
        labels = read_xls_labels(xls)
        for c in [c for c in xmi if c["schema"] == schema]:
            uri = c["vocabulary"] if c["vocabulary"] in schemes else BASE + c["name"]
            reg = values.get(uri, {})
            xl = labels.get(c["name"])
            reg_by_label = {squash(v["label"]): k for k, v in reg.items()}
            reg_by_code = {squash(k): k for k in reg}
            for lab in (xl or []):
                code = reg_by_label.get(squash(lab)) or reg_by_code.get(squash(lab))
                st = "MATCH" if code else "NO_MATCH"
                summary[f"xls-label:{st}"] += 1
                value_rows.append(dict(schema=schema, codelist=c["name"], xls_label=lab,
                                       registry_code=code or "", status=st))
            summary["test-theme codelists"] += 1
            summary["test-theme codelists with registry values"] += bool(reg)
            summary["test-theme codelists with xls values"] += bool(xl)

    write(OUT / "codelists_xmi_vs_registry.csv", rows)
    write(OUT / "xls_labels_vs_registry.csv", value_rows)
    write(OUT / "registry_schemes_unused.csv",
          [dict(uri=u, **{k: v for k, v in schemes[u].items()}, n_values=len(values.get(u, {})))
           for u in sorted(unmatched_reg)])
    print(f"registry version: codelist {cl_ver}, enumeration {en_ver}")
    print(f"registry schemes: {len(schemes)} (codelist {len(cl_s)}, enumeration {len(en_s)}); "
          f"values: {sum(len(v) for v in values.values())}")
    print(f"XMI codelists/enumerations in application schemas: {len(xmi)}")
    for k in sorted(summary):
        print(f"  {k:55s} {summary[k]}")


def write(path, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
