"""E01b - Cross-check mapping tables (xls) against the XMI for selected schemas.

For each concrete «featureType»/«dataType» in the schema, build the flattened property
set from the XMI (own + inherited attributes + navigable association roles) and compare
name / multiplicity / voidable with the 'SelectedObjects' + 'ComplexTypes' sheets.

Usage:  python compare_mapping.py  -> writes results/mapping_vs_xmi_<schema>.csv
"""
from collections import Counter
from pathlib import Path
import csv
import re

import xlrd

from xmi_load import load, NS, XMI_ID, XMI_IDREF, XMI_TYPE, ROOT
from inventory import stereotypes

MAP_DIR = ROOT / "data/raw/approved/mapping"
OUT = Path(__file__).parent / "results"
CASES = {
    "AdministrativeUnits": "AdministrativeUnitsMappingTable.xls",
    "CadastralParcels": "CadastralParcelsMappingTable.xls",
    "Soil": "SoilMappingTable.xls",
    "LandCoverVector": "LandCoverMappingTable.xls",
    "Existing Land Use": "LandUseMappingTable.xls",
}


def norm_name(s):
    return re.sub(r"\s+", "", s.split(" - ")[0]).lower()


def norm_mult(s):
    s = str(s).strip()
    if s in ("1.0", "1"):
        return "1"
    return s.replace("...", "..")


def mult(lo, hi):
    lo = "0" if lo is None else lo
    hi = "1" if hi is None else hi
    hi = "*" if hi in ("-1", "*") else hi
    return lo if lo == hi else f"{lo}..{hi}"


def xmi_model():
    root, _ = load()
    model = root.find(f"{{{NS['uml']}}}Model")
    ext = root.find(f"{{{NS['xmi']}}}Extension")
    ea = {e.get(XMI_IDREF): e for e in ext.find("elements")}
    byid = {e.get(XMI_ID): e for e in model.iter() if e.get(XMI_ID)}
    # voidable association ends, from EA connectors: (class id, role name)
    void_roles = set()
    for cn in ext.find("connectors"):
        for end, other in (("target", "source"), ("source", "target")):
            e, o = cn.find(end), cn.find(other)
            if e is None or o is None:
                continue
            role = e.find("role")
            if role is not None and role.get("name") and "voidable" in stereotypes(e):
                void_roles.add((o.get(XMI_IDREF), role.get("name")))
    return model, ea, byid, void_roles


def flattened(cls, ea, byid, void_roles, seen=None):
    """name -> (multiplicity, voidable, origin class) incl. inherited, subclass wins."""
    seen = seen or set()
    out = {}
    for g in cls.findall("generalization"):
        sup = byid.get(g.get("general"))
        if sup is not None and sup.get(XMI_ID) not in seen:
            seen.add(sup.get(XMI_ID))
            out.update(flattened(sup, ea, byid, void_roles, seen))
    e = ea.get(cls.get(XMI_ID))
    ea_void = set()
    if e is not None and e.find("attributes") is not None:
        ea_void = {a.get("name") for a in e.find("attributes") if "voidable" in stereotypes(a)}
    for a in cls.findall("ownedAttribute"):
        if not a.get("name"):
            continue
        lo = a.find("lowerValue")
        hi = a.find("upperValue")
        is_role = bool(a.get("association"))
        v = (cls.get(XMI_ID), a.get("name")) in void_roles if is_role else a.get("name") in ea_void
        out[a.get("name")] = (mult(lo.get("value") if lo is not None else None,
                                   hi.get("value") if hi is not None else None),
                              v, cls.get("name"), "role" if is_role else "attr")
    return out


def read_xls(path):
    """{normalised type name: {normalised prop: (raw name, mult, voidable col)}}"""
    book = xlrd.open_workbook(path)
    res = {}
    for sh in book.sheets():
        if sh.name.lower().startswith("codelist"):
            continue
        cur = None
        for r in range(2, sh.nrows):
            row = sh.row_values(r)
            if str(row[0]).strip():
                cur = norm_name(str(row[0]).split("\n")[0])
                res.setdefault(cur, {})
            if cur and str(row[2]).strip() and str(row[4]).strip():
                res[cur][norm_name(str(row[2]))] = (str(row[2]).strip(), norm_mult(row[5]), str(row[6]).strip())
    return res


def main():
    model, ea, byid, void_roles = xmi_model()
    OUT.mkdir(exist_ok=True)
    for schema, xls in CASES.items():
        pkg = next(p for p in model.iter("packagedElement")
                   if p.get(XMI_TYPE) == "uml:Package" and p.get("name") == schema)
        tab = read_xls(MAP_DIR / xls)
        rows, stat = [], Counter()
        for c in pkg.iter("packagedElement"):
            e = ea.get(c.get(XMI_ID))
            st = stereotypes(e) if e is not None else []
            if not st or st[0] not in ("featuretype", "datatype"):
                continue
            if e.find("properties").get("isAbstract") == "true":
                continue
            flat = flattened(c, ea, byid, void_roles)
            t = tab.get(norm_name(c.get("name")))
            if t is None:
                stat["type missing in xls"] += 1
                rows.append(dict(type=c.get("name"), prop="*", status="TYPE_MISSING_IN_XLS"))
                continue
            for name, (m, v, origin, kind) in flat.items():
                x = t.get(norm_name(name))
                if x is None:
                    status = "MISSING_IN_XLS"
                else:
                    xm, xv = x[1], x[2].lower() == "voidable"
                    status = "OK" if (xm == m and xv == v) else \
                        ("MULT_DIFF" if xm != m and xv == v else "VOID_DIFF" if xm == m else "MULT+VOID_DIFF")
                stat[f"{kind}:{status}"] += 1
                rows.append(dict(type=c.get("name"), prop=name, kind=kind, origin=origin, xmi_mult=m,
                                 xmi_voidable=v, xls_name=x[0] if x else "", xls_mult=x[1] if x else "",
                                 xls_voidcol=x[2] if x else "", status=status))
            for k, x in t.items():
                if k not in {norm_name(n) for n in flat}:
                    stat["EXTRA_IN_XLS"] += 1
                    rows.append(dict(type=c.get("name"), prop=x[0], xls_mult=x[1], xls_voidcol=x[2], status="EXTRA_IN_XLS"))
        fn = OUT / f"mapping_vs_xmi_{schema.replace(' ', '_')}.csv"
        keys = ["type", "prop", "kind", "origin", "xmi_mult", "xmi_voidable", "xls_name", "xls_mult", "xls_voidcol", "status"]
        with open(fn, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)
        print(f"{schema:22s}", dict(stat))


if __name__ == "__main__":
    main()
