"""Report dangling references across a set of AAS environment files (R5).

    python -m inspire2aas.check_refs output/instances/*/*.json

A ModelReference to a Submodel (in a ReferenceElement or in a shell's submodel list) is dangling
if no file of the set contains a Submodel with that id. ExternalReferences are not checked.
"""
import glob
import json
import sys


def _walk(elems, path):
    for e in elems or []:
        p = f"{path}/{e.get('idShort', '[]')}"
        if e.get("modelType") == "ReferenceElement" and isinstance(e.get("value"), dict):
            yield p, e["value"]
        if isinstance(e.get("value"), list):
            yield from _walk([x for x in e["value"] if isinstance(x, dict) and "modelType" in x], p)


def dangling_references(envs):
    """envs: {name: environment dict} -> list of (file, path, missing submodel id)"""
    known = {sm["id"] for env in envs.values() for sm in env.get("submodels", [])}
    out = []
    for name, env in envs.items():
        refs = []
        for sh in env.get("assetAdministrationShells", []):
            refs += [(f"{sh['idShort']}/submodels", r) for r in sh.get("submodels", [])]
        for sm in env.get("submodels", []):
            refs += list(_walk(sm.get("submodelElements"), sm.get("idShort", "")))
        for path, ref in refs:
            keys = ref.get("keys", [])
            if ref.get("type") == "ModelReference" and keys and keys[0]["type"] == "Submodel" and keys[0]["value"] not in known:
                out.append((name, path, keys[0]["value"]))
    return out


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    files = sorted({f for a in argv for f in glob.glob(a)})
    if not files:
        raise SystemExit(__doc__)
    envs = {f: json.load(open(f, encoding="utf-8")) for f in files}
    d = dangling_references(envs)
    print(f"{len(files)} files, {sum(len(e.get('submodels', [])) for e in envs.values())} submodels, "
          f"{len(d)} dangling references")
    for f, p, target in d:
        print(f"  {f}: {p} -> {target}")
    return 1 if d else 0


if __name__ == "__main__":
    raise SystemExit(main())
