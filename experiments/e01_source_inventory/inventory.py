"""E01 - Inventory of the INSPIRE consolidated EA XMI (v2025.1, approved / IR only).

Counts UML constructs per «applicationSchema» package, using the EA extension
(`xmi:Extension/elements|connectors`) because stereotypes and tagged values are
NOT exported as standard UML profile applications in this file.

Usage:  python inventory.py   -> writes results/*.csv and prints a summary
"""
from collections import Counter, defaultdict
from pathlib import Path
import csv
import re

from xmi_load import load, NS, XMI_ID, XMI_IDREF, XMI_TYPE

OUT = Path(__file__).parent / "results"
STEREO_RE = re.compile(r"@STEREO;Name=([^;]+);")


def stereotypes(node):
    """All stereotypes of an EA extension node: <stereotype> shows only the first,
    the complete list is only in the xrefs string."""
    found = []
    x = node.find("xrefs")
    if x is not None and x.get("value"):
        found += STEREO_RE.findall(x.get("value"))
    for tag in ("properties", "stereotype"):
        s = node.find(tag)
        if s is not None and s.get("stereotype") and s.get("stereotype") not in found:
            found.insert(0, s.get("stereotype"))
    return [s.lower() for s in found]


def tags(node):
    t = node.find("tags")
    # EA appends the tag's notes to the value as "value#NOTES#notes..."
    return {} if t is None else {x.get("name"): (x.get("value") or "").split("#NOTES#")[0]
                                 for x in t.findall("tag")}


def main():
    root, replacements = load()
    model = root.find(f"{{{NS['uml']}}}Model")
    ext = root.find(f"{{{NS['xmi']}}}Extension")
    ea_el = {e.get(XMI_IDREF): e for e in ext.find("elements")}

    # --- package tree and application schemas
    parent, pkg_name = {}, {}
    for p in model.iter("packagedElement"):
        if p.get(XMI_TYPE) == "uml:Package":
            pkg_name[p.get(XMI_ID)] = p.get("name")
            for c in p:
                if c.tag == "packagedElement":
                    parent[c.get(XMI_ID)] = p.get(XMI_ID)

    def path(pid):
        out = []
        while pid in pkg_name:
            out.append(pkg_name[pid])
            pid = parent.get(pid)
        return "/".join(reversed(out))

    app_schemas = {}
    for pid in pkg_name:
        e = ea_el.get(pid)
        if e is not None and "applicationschema" in stereotypes(e):
            t = tags(e)
            app_schemas[pid] = dict(name=pkg_name[pid], path=path(pid),
                                    version=t.get("version", ""), xmlns=t.get("xmlns", ""),
                                    targetNamespace=t.get("targetNamespace", ""))

    def schema_of(eid):
        p = parent.get(eid)
        while p is not None:
            if p in app_schemas:
                return p
            p = parent.get(p)
        return None

    # --- classes
    rows = []
    stats = defaultdict(Counter)
    class_stereo, attr_stereo, tagnames, cls_tag_names = Counter(), Counter(), Counter(), Counter()
    unresolved_types = Counter()
    all_ids = {e.get(XMI_ID) for e in model.iter() if e.get(XMI_ID)}
    for c in model.iter("packagedElement"):
        ty = c.get(XMI_TYPE)
        if ty not in ("uml:Class", "uml:Enumeration", "uml:AssociationClass", "uml:Interface", "uml:DataType"):
            continue
        sid = schema_of(c.get(XMI_ID))
        e = ea_el.get(c.get(XMI_ID))
        st = stereotypes(e) if e is not None else []
        t = tags(e) if e is not None else {}
        for s in st:
            class_stereo[s] += 1
        if sid is None:
            continue
        cls_tag_names.update(t.keys())
        props = e.find("properties") if e is not None else None
        abstract = props is not None and props.get("isAbstract") == "true"
        s = stats[sid]
        key = st[0] if st else f"<none:{ty}>"
        s[f"cls:{key}"] += 1
        if ty == "uml:AssociationClass":
            s["associationClass"] += 1
        if abstract:
            s["abstract"] += 1
        if "codelist" in st:
            s[f"codelist.extensibility={t.get('extensibility', '<missing>')}"] += 1
        s["generalizations"] += len(c.findall("generalization"))
        cons = e.find("constraints") if e is not None else None
        n_cons = 0 if cons is None else len(cons)
        s["constraints"] += n_cons
        n_attr = n_void = 0
        for a in c.findall("ownedAttribute"):
            if a.get("association"):
                continue  # navigable association ends owned by class; counted via connectors
            n_attr += 1
            tref = a.find("type")
            if tref is not None and tref.get(XMI_IDREF) and tref.get(XMI_IDREF) not in all_ids:
                unresolved_types[tref.get(XMI_IDREF)] += 1
                s["attr.type_unresolved"] += 1
        ea_attrs = e.find("attributes") if e is not None else None
        if ea_attrs is not None:
            for ea in ea_attrs:
                ast = stereotypes(ea)
                attr_stereo.update(ast)
                tagnames.update(tags(ea).keys())
                if "voidable" in ast:
                    n_void += 1
        s["attributes"] += n_attr
        s["attr.voidable"] += n_void
        if not c.get("name"):
            s["cls.unnamed"] += 1
        rows.append(dict(schema=app_schemas[sid]["name"], cls=c.get("name") or "", umltype=ty,
                         stereotypes="|".join(st), abstract=abstract, attributes=n_attr,
                         voidable_attrs=n_void, constraints=n_cons,
                         extensibility=t.get("extensibility", ""), vocabulary=t.get("vocabulary", "")))

    # --- associations (EA connectors) per schema of source
    conn_stereo = Counter()
    for cn in ext.find("connectors"):
        src = cn.find("source")
        sid = schema_of(src.get(XMI_IDREF)) if src is not None else None
        ct = cn.find("properties").get("ea_type") if cn.find("properties") is not None else None
        if sid is not None:
            stats[sid][f"conn:{ct}"] += 1
            for end in (cn.find("source"), cn.find("target")):
                if end is not None and "voidable" in stereotypes(end):
                    stats[sid]["assocEnd.voidable"] += 1
                    conn_stereo["voidable"] += 1

    OUT.mkdir(exist_ok=True)
    with open(OUT / "classes.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["schema"], r["cls"])))
    keys = sorted({k for s in stats.values() for k in s})
    with open(OUT / "schemas.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["schema", "version", "path", "targetNamespace"] + keys)
        for sid, meta in sorted(app_schemas.items(), key=lambda kv: kv[1]["path"]):
            w.writerow([meta["name"], meta["version"], meta["path"], meta["targetNamespace"]] + [stats[sid][k] for k in keys])

    total = Counter()
    for s in stats.values():
        total.update(s)
    print(f"cp1252 replacement chars: {replacements}")
    print(f"application schemas: {len(app_schemas)}")
    print("TOTAL over application schemas:")
    for k in keys:
        print(f"  {k:45s} {total[k]}")
    print("class stereotypes (whole model):", class_stereo.most_common())
    print("attribute stereotypes (whole model):", attr_stereo.most_common())
    print("attribute tag names (whole model):", tagnames.most_common(25))
    print("class tag names (app schemas):", cls_tag_names.most_common(40))
    print("unresolved attr type refs (top 15):", unresolved_types.most_common(15))
    print("distinct unresolved attr type refs:", len(unresolved_types))


if __name__ == "__main__":
    main()
