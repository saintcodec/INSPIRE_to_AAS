# Notice: content that is not ours

The MIT licence in [LICENSE](LICENSE) covers the code and the documentation written for this
project. It does **not** cover the INSPIRE content the code reads and the generated files carry.

## INSPIRE

The files under `output/` and the result tables under `experiments/*/results/` contain names,
definitions and identifiers taken from:

- the **INSPIRE Consolidated UML Model** (Annex I, II, III; implementing-rules version 2025.1), and
- the **INSPIRE Registry** (feature concept dictionary, code lists, application schemas), version
  20260826-0.

Source: INSPIRE, © European Union. https://inspire.ec.europa.eu/

**Changes made:** the definitions are carried over unchanged, except that a text longer than the
limit of the target field is cut and marked with "…"; the model itself is translated into Asset
Administration Shell Submodel Templates and ConceptDescriptions. What is not translated one to one
is listed in each build's `loss_ledger.csv` and `report.md`. Every generated ConceptDescription
names where its definition comes from (`sourceOfDefinition`).

**Licence of that content.** We reuse it under the reuse policy of the European Commission
(Commission Decision 2011/833/EU), which licenses content owned by the EU under
[Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/):
reuse is allowed provided the source is acknowledged and changes are indicated, as done above.

**What we could not confirm (checked 2026-11-14):** neither the INSPIRE Registry page nor the
repository of the INSPIRE application schemas carries a licence statement of its own. CC BY 4.0 is
stated in the legal notice of the European Commission's website and in the copyright notice of the
Publications Office, which hosts the Registry since 1 July 2026. If you reuse the generated files,
check the conditions that apply to you.

The INSPIRE source files themselves (`data/raw/`) are not part of this repository.

## ShapeChange

Experiment E02 compares our reader with the Feature Catalogue produced by ShapeChange. ShapeChange
is not part of this repository.
