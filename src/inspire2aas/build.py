"""Command line: build AAS Submodel Templates for INSPIRE application schemas.

    python -m inspire2aas.build CadastralParcels AdministrativeUnits

Writes to output/templates/<prefix>/:
    <prefix>_templates.json   AAS environment (Submodel Templates + ConceptDescriptions)
    <prefix>_templates.aasx   same, as AASX package (via BaSyx; also an independent read check)
    loss_ledger.csv           everything that was not translated 1:1
    report.md                 summary (counts, verification result)
"""
from collections import Counter
from datetime import date
import argparse
import csv
import json

import aas_core3_1.jsonization as jsonization
import aas_core3_1.types as T
import aas_core3_1.verification as verification

from . import config, mapper, registry, xmi_reader


def verify(env):
    return [f"{e.path}: {e.cause}" for e in verification.verify(env)]


def write_aasx(json_path, aasx_path):
    """Re-read our JSON with BaSyx (independent parser) and package it as AASX."""
    from basyx.aas.adapter import aasx
    from basyx.aas.adapter.json import read_aas_json_file
    with open(json_path, encoding="utf-8") as fh:
        store = read_aas_json_file(fh, failsafe=False)
    files = aasx.DictSupplementaryFileContainer()
    with aasx.AASXWriter(str(aasx_path)) as w:
        # BaSyx writes XML unless write_json=True, so the part name must end in .xml (EcoTwin defect 2)
        w.write_all_aas_objects("/aasx/data.xml", store, files)
    return len(store)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("schemas", nargs="+", help="UML application schema names, e.g. CadastralParcels")
    ap.add_argument("--name", help="output name (default: Registry prefix of the first schema)")
    a = ap.parse_args(argv)

    model = xmi_reader.read()
    reg = registry.read()
    unknown = [s for s in a.schemas if s not in model.schemas]
    if unknown:
        raise SystemExit(f"unknown schema(s): {unknown}. Known: {sorted(model.schemas)}")
    smts, cds, ledger, codelists = mapper.build(model, reg, set(a.schemas))
    name = a.name or "_".join(reg.schema_prefix.get(s, s) for s in a.schemas)

    shell = T.AssetAdministrationShell(
        id=f"{config.BASE_URI}aas/templates/{name}", id_short=f"INSPIRE_{name}_Templates",
        asset_information=T.AssetInformation(asset_kind=T.AssetKind.TYPE,
                                             global_asset_id=f"{config.BASE_URI}asset/templates/{name}"),
        submodels=[mapper.model_ref_submodel(s.id) for s in smts])
    env = T.Environment(asset_administration_shells=[shell], submodels=smts, concept_descriptions=cds)
    errors = verify(env)

    out = config.OUTPUT_DIR / "templates" / name
    out.mkdir(parents=True, exist_ok=True)
    jpath = out / f"{name}_templates.json"
    jpath.write_text(json.dumps(jsonization.to_jsonable(env), indent=2, ensure_ascii=False), encoding="utf-8")
    (out / f"{name}_codelists.json").write_text(json.dumps(codelists, indent=1, ensure_ascii=False), encoding="utf-8")
    aasx_note = ""
    try:
        n = write_aasx(jpath, out / f"{name}_templates.aasx")
        aasx_note = f"AASX written; BaSyx re-read {n} identifiables without error."
    except Exception as ex:  # report, do not hide
        aasx_note = f"AASX FAILED: {type(ex).__name__}: {ex}"
    with open(out / "loss_ledger.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["schema", "smt", "path", "kind", "detail"])
        w.writeheader()
        w.writerows(ledger)

    kinds = Counter(l["kind"] for l in ledger)
    lines = [f"# Build report: {name}", "",
             f"- date: {date.today()}",
             f"- schemas: {', '.join(f'{s} {model.schemas[s].version}' for s in a.schemas)}",
             f"- INSPIRE UML: {config.XMI_PATH.name}",
             f"- INSPIRE Registry version: {reg.version}",
             f"- Submodel Templates: {len(smts)} ({', '.join(s.id_short for s in smts)})",
             f"- ConceptDescriptions: {len(cds)}",
             f"- aas-core3.1 verification: **{'PASSED (0 errors)' if not errors else f'{len(errors)} ERRORS'}**",
             f"- {aasx_note}", "",
             "## Loss ledger (not translated 1:1)", "", "| kind | count |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in kinds.most_common()]
    if errors:
        lines += ["", "## Verification errors", ""] + [f"- {e}" for e in errors[:200]]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:12]))
    print(f"\nloss ledger: {dict(kinds)}")
    if errors:
        print("\nfirst verification errors:\n  " + "\n  ".join(errors[:25]))
    print(f"\noutput: {out}")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
