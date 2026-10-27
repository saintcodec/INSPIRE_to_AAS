# INSPIRE_to_AAS

Research project: automatic generation of Asset Administration Shell (AAS v3.1) Submodel Templates from INSPIRE data models, and AAS instances for real objects such as cadastral parcels.

Part of a broader effort on management-level digital twins for land parcels.

## Status

Research prototype. Nothing in this repository is assumed correct until it has been tested and the result documented.

- **Working:** CadastralParcels + AdministrativeUnits → 7 AAS v3.1 Submodel Templates (0 verification errors), plus an example parcel AAS ([E04](experiments/e04_first_generator/)).
- **Working:** Existing Land Use, Land Cover and Soil (14 templates), including soil observations, association classes and national codelist values ([E05](experiments/e05_ecotwin_requests/), used by the EcoTwin project).
- Python API for other projects: `inspire2aas.instance.build_submodel`, `build_feature_collection`, `write_aasx`, `inspire2aas.ids`, `inspire2aas.check_refs`.
- Mapping rules: [docs/mapping_rules.md](docs/mapping_rules.md)
- [first_reaserch.md](first_reaserch.md): initial desk-research notes (LLM-assisted). These are **hypotheses to verify**, not established facts.

## Usage

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
set PYTHONPATH=src

:: 1. templates for one or more INSPIRE application schemas -> output/templates/<name>/
.venv\Scripts\python -m inspire2aas.build CadastralParcels AdministrativeUnits

:: 2. an AAS for one parcel from a values file -> output/instances/<name>/
.venv\Scripts\python -m inspire2aas.instance examples\parcel_example.json

:: 3. automatic tests
.venv\Scripts\python -m pytest tests
```

Required source data (not committed): `data/raw/approved/ea+xmi/` (INSPIRE UML v2025.1), `data/raw/approved/fc/`, and `data/raw/INSPIRE Registry/` (RDF dump). See the experiments for checksums.

## Experiments

Each experiment has its own folder with scripts, results and a log (question, method, findings).

| ID | Topic | Status |
|---|---|---|
| [E01](experiments/e01_source_inventory/) | Inventory of the INSPIRE v2025.1 EA/XMI model; cross-check against the mapping tables | done |
| [E02](experiments/e02_fc_crosscheck/) | Our XMI reader vs ShapeChange's Feature Catalogue | done |
| [E03](experiments/e03_registry_codelists/) | Codelists: UML vs INSPIRE Registry (values, extensibility) | done |
| [E04](experiments/e04_first_generator/) | First generator: CP + AU templates and a parcel AAS | done |
| [E05](experiments/e05_ecotwin_requests/) | EcoTwin requests R1–R6: observations, association classes, national codes, ids | done |
| [E06](experiments/e06_feature_collections/) | EcoTwin request R7: feature collections; AASX file naming and part name | done |
