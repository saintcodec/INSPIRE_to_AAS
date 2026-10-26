"""Read the INSPIRE EA XMI 2.1 export into the intermediate model.

Implements the reader rules established in experiments E01-E02:
- tolerant cp1252 decoding (E01 F1)
- stereotypes from the EA extension incl. the `xrefs` string (E01 F3/F4)
- tag values without the `#NOTES#` suffix (E01 F5)
- skip EA Boundary/Text pseudo-classes (E01 F10)
- type references by id, else by (unique) name (E01 F11)
- attributes only if listed by EA (E02 R1), names trimmed (R2),
  category from first known stereotype (R3), duplicate schema names (R4),
  role navigability from EA style, Non-Navigable excluded (R5)
- duplicate / clashing roles logged, not silently merged (E02 G6/G7)
"""
from collections import Counter, defaultdict
import re

from lxml import etree

from . import config
from .model import Cls, Doc, Model, Prop, Schema

NS_XMI = "http://schema.omg.org/spec/XMI/2.1"
NS_UML = "http://schema.omg.org/spec/UML/2.1"
XMI_ID = f"{{{NS_XMI}}}id"
XMI_IDREF = f"{{{NS_XMI}}}idref"
XMI_TYPE = f"{{{NS_XMI}}}type"
STEREO_RE = re.compile(r"@STEREO;Name=([^;]+);")


def load_xml(path=config.XMI_PATH):
    text = path.read_bytes().decode("cp1252", errors="replace")
    text = re.sub(r"^<\?xml[^>]*\?>", "", text, count=1)
    return etree.fromstring(text, etree.XMLParser(huge_tree=True))


def stereotypes(node):
    found = []
    x = node.find("xrefs")
    if x is not None and x.get("value"):
        found += STEREO_RE.findall(x.get("value"))
    for tag in ("properties", "stereotype", "role"):
        s = node.find(tag)
        if s is not None and s.get("stereotype") and s.get("stereotype") not in found:
            found.insert(0, s.get("stereotype"))
    return [s.strip().lower() for s in found]


def tags(node):
    t = node.find("tags")
    return {} if t is None else {(x.get("name") or "").strip(): (x.get("value") or "").split("#NOTES#")[0].strip()
                                 for x in t.findall("tag")}


def parse_doc(text):
    """Split EA documentation into the INSPIRE '-- Name --' / '-- Definition --' / '-- Description --' blocks."""
    text = (text or "").replace("\r", "")
    parts = re.split(r"--\s*(Name|Definition|Description)\s*--", text)
    d = Doc()
    if len(parts) == 1:
        d.definition = text.strip()
        return d
    for key, body in zip(parts[1::2], parts[2::2]):
        setattr(d, key.lower(), body.strip())
    return d


def read(path=config.XMI_PATH) -> Model:
    root = load_xml(path)
    model = root.find(f"{{{NS_UML}}}Model")
    ext = root.find(f"{{{NS_XMI}}}Extension")
    ea = {e.get(XMI_IDREF): e for e in ext.find("elements")}
    issues = []

    # ---------------- packages and application schemas
    parent, pkg_name = {}, {}
    for p in model.iter("packagedElement"):
        if p.get(XMI_TYPE) == "uml:Package":
            pkg_name[p.get(XMI_ID)] = p.get("name")
            for c in p:
                if c.tag == "packagedElement":
                    parent[c.get(XMI_ID)] = p.get(XMI_ID)
    schemas, schema_of_pkg, seen = {}, {}, Counter()
    for pid, name in pkg_name.items():
        e = ea.get(pid)
        if e is not None and "applicationschema" in stereotypes(e):
            name = name.strip()
            seen[name] += 1
            if seen[name] > 1:
                name = f"{name} ({seen[name]})"
            schemas[name] = Schema(name=name, version=tags(e).get("version", ""))
            schema_of_pkg[pid] = name

    def schema_of(eid):
        p = parent.get(eid)
        while p is not None and p not in schema_of_pkg:
            p = parent.get(p)
        return schema_of_pkg.get(p)

    # ---------------- classes
    classes = {}
    for c in model.iter("packagedElement"):
        ty = c.get(XMI_TYPE)
        if ty not in ("uml:Class", "uml:AssociationClass", "uml:Enumeration", "uml:DataType",
                      "uml:PrimitiveType", "uml:Interface"):
            continue
        e = ea.get(c.get(XMI_ID))
        props_el = e.find("properties") if e is not None else None
        if props_el is not None and props_el.get("sType") in ("Boundary", "Text", "Note"):
            continue
        st = stereotypes(e) if e is not None else []
        cat = next((config.CLASS_STEREOTYPES[s] for s in st if s in config.CLASS_STEREOTYPES), None)
        if cat is None:
            cat = {"uml:Enumeration": "enumeration", "uml:PrimitiveType": "primitive",
                   "uml:DataType": "dataType"}.get(ty, "type")  # E02 G5: unstereotyped -> object type
        if st and st[0] not in config.CLASS_STEREOTYPES and cat != "type":
            issues.append(dict(kind="odd-first-stereotype", cls=c.get("name"), detail=st))
        cl = Cls(id=c.get(XMI_ID), name=(c.get("name") or "").strip(), category=cat,
                 abstract=(props_el is not None and props_el.get("isAbstract") == "true") or c.get("isAbstract") == "true",
                 schema=schema_of(c.get(XMI_ID)),
                 supertypes=[g.get("general") for g in c.findall("generalization") if g.get("general")],
                 tags=tags(e) if e is not None else {},
                 doc=parse_doc(props_el.get("documentation") if props_el is not None else ""))
        if e is not None and e.find("constraints") is not None:
            cl.constraints = [(k.get("name"), k.get("notes") or k.get("description") or "") for k in e.find("constraints")]
        cl._uml = c   # keep for attribute pass
        cl._ea = e
        classes[cl.id] = cl

    names = defaultdict(list)
    for cl in classes.values():
        names[cl.name].append(cl)

    def resolve(ref, context_schema):
        """-> (type_name, type_id)"""
        if not ref:
            return "", None
        if ref in classes:
            return classes[ref].name, ref
        name = ref.split("_", 1)[1] if ref.startswith(("EAJava_", "EAnone_")) else ref
        name = name.strip()
        cands = names.get(name, [])
        if not cands:
            return name, None
        pick = next((c for c in cands if c.schema == context_schema), None) or \
            next((c for c in cands if c.schema is not None), None) or cands[0]
        if len(cands) > 1:
            issues.append(dict(kind="ambiguous-type-name", cls=name, detail=f"{len(cands)} candidates"))
        return pick.name, pick.id

    # ---------------- attributes and codelist values
    for cl in classes.values():
        e = cl._ea
        ea_attrs = {}
        if e is not None and e.find("attributes") is not None:
            ea_attrs = {a.get("name"): a for a in e.find("attributes")}
        for a in cl._uml.findall("ownedAttribute"):
            raw = a.get("name")
            if a.get("association") or not raw or raw not in ea_attrs:
                continue
            ea_a = ea_attrs[raw]
            name = raw.strip()
            if cl.category in ("codeList", "enumeration"):
                cl.values.append(name)
                continue
            lo = a.find("lowerValue")
            hi = a.find("upperValue")
            lo = lo.get("value") if lo is not None else "1"
            hi = hi.get("value") if hi is not None else "1"
            hi = "*" if hi in ("-1", "*") else hi
            st = stereotypes(ea_a)
            t = a.find("type")
            tname, tid = resolve(t.get(XMI_IDREF) if t is not None else None, cl.schema)
            if not tname:
                p = ea_a.find("properties")
                tname = (p.get("type") or "").strip() if p is not None else ""
                if tname:
                    tname, tid = resolve(tname, cl.schema)
            if not tname:
                issues.append(dict(kind="attribute-without-type", cls=cl.name, detail=name))
            doc_el = ea_a.find("documentation")
            cl.props.append(Prop(name=name, kind="attr", lower=lo, upper=hi, type_name=tname, type_id=tid,
                                 voidable="voidable" in st, lifecycle="lifecycleinfo" in st,
                                 ordered=a.get("isOrdered") == "true",
                                 doc=parse_doc(doc_el.get("value") if doc_el is not None else ""),
                                 owner_id=cl.id))
        for lit in cl._uml.findall("ownedLiteral"):
            if lit.get("name"):
                cl.values.append(lit.get("name").strip())

    # ---------------- association roles (EA connectors)
    seen_roles = set()
    for cn in ext.find("connectors"):
        pr = cn.find("properties")
        if pr is None or pr.get("ea_type") not in ("Association", "Aggregation"):
            continue
        for end, other in (("source", "target"), ("target", "source")):
            en, ot = cn.find(end), cn.find(other)
            role = en.find("role")
            if role is None or not (role.get("name") or "").strip():
                continue
            owner = classes.get(ot.get(XMI_IDREF))
            target = classes.get(en.get(XMI_IDREF))
            if owner is None:
                continue
            style = (en.find("style").get("value") or "") if en.find("style") is not None else ""
            if "Navigable=Non-Navigable" in style:
                continue
            name = role.get("name").strip()
            key = (owner.id, name, target.id if target else None)
            if key in seen_roles:
                issues.append(dict(kind="duplicate-association", cls=owner.name, detail=name))
                continue
            seen_roles.add(key)
            if any(p.name == name for p in owner.props):
                issues.append(dict(kind="property-name-clash", cls=owner.name,
                                   detail=f"{name} -> {target.name if target else '?'} (kept first)"))
                continue
            m = (en.find("type").get("multiplicity") or "1") if en.find("type") is not None else "1"
            lo, _, hi = m.partition("..")
            hi = hi or lo
            if m.strip() == "*":
                lo, hi = "0", "*"
            st = stereotypes(en)
            doc_el = en.find("documentation")
            xp = cn.find("extendedProperties")
            assoc_cls = xp.get("associationclass") if xp is not None else None
            owner.props.append(Prop(name=name, kind="role", lower=lo.strip(), upper=hi.strip(),
                                    assoc_class_id=assoc_cls if assoc_cls in classes else None,
                                    type_name=target.name if target else en.find("model").get("name"),
                                    type_id=target.id if target else None,
                                    voidable="voidable" in st,
                                    ordered=(en.find("modifiers") is not None and en.find("modifiers").get("isOrdered") == "true"),
                                    doc=parse_doc(doc_el.get("value") if doc_el is not None else ""),
                                    owner_id=owner.id))

    for cl in classes.values():
        del cl._uml, cl._ea
    return Model(schemas=schemas, classes=classes, issues=issues)


def flatten(model: Model, cls: Cls):
    """All properties of a class incl. inherited ones (root first; a subclass redefinition wins)."""
    out, order = {}, []
    seen = set()

    def walk(c):
        if c.id in seen:
            return
        seen.add(c.id)
        for sid in c.supertypes:
            if sid in model.classes:
                walk(model.classes[sid])
        for p in c.props:
            if p.name not in out:
                order.append(p.name)
            out[p.name] = p
    walk(cls)
    return [out[n] for n in order]
