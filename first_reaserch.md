# INSPIRE UML → AAS v3 Submodel Templates: Feasibility and Implementation Strategy

Automatically converting all INSPIRE application schemas into AAS v3 Submodel Templates is feasible, provided three things hold. The converter must read the UML model (the EA project or XMI from INSPIRE-MIF/uml-models, ideally via ShapeChange's model loader), not the XSDs. It needs explicit, configurable rules for inheritance flattening, association classes, voidability and codelists, because the AAS has no native equivalent for these. And geometry and coverages have to be treated as opaque payloads (GeoJSON Blobs or external references), not as modelled structure. Nothing is lost silently if every lossy step is recorded as a Qualifier or Extension and reported in a coverage metric. The real risk is semantic drift, not structural impossibility.

## TL;DR
- **Feasible, model-driven, with recorded losses.** The approved INSPIRE UML model is published officially and versioned twice a year. Its latest release is v2025.1 (31 January 2025), covering about 75 application schemas. It is the only artifact that keeps stereotypes, voidable flags, tagged values, association classes and OCL constraints. The XSDs measurably drop information, which makes them a fallback only. Use ShapeChange (Java) to load the EA model and export it to SCXML, then run a Python (aas-core3.1 / BaSyx) transformation that emits AAS Submodel Templates and IEC 61360 ConceptDescriptions.
- **Main incompatibilities and how to resolve them.**
  - Inheritance → flatten into every concrete leaf type and keep the lineage in semanticIds.
  - Association classes (e.g. Soil `DerivedProfilePresenceInSoilBody`) → AnnotatedRelationshipElement, or an SMC inside a list.
  - Voidable/nilReason → a Qualifier convention.
  - Codelists → ConceptDescriptions whose valueList entries carry valueIds that are EU-Vocabularies-resolvable `inspire.ec.europa.eu/codelist/...` URIs.
  - Cycles and by-reference links → ReferenceElements, not containment.
  - Geometry → RFC 7946 GeoJSON. It must be WGS 84 (equivalent to urn:ogc:def:crs:OGC::CRS84, RFC 7946 §4), so ETRS89/UTM (EPSG:25832) geometry needs either reprojection or a deliberately non-RFC "crs" profile.
- **No direct prior art found, but reusable building blocks exist.** I found no published INSPIRE→AAS or ISO 19109→AAS converter. The building blocks are ShapeChange (flattener, modular Target API), the INSPIRE model-transformation-rules repository, the INSPIRE RDF vocabularies, Eclipse ESMF's SAMM→AAS generator (as a design reference), aas-core verification, and IDTA SMTs such as Asset Location (IDTA 02045), Digital Nameplate (02006) and Contact Information (02002). Start with SO, ELU, LCV, AU and CP, and pin AAS v3.1.x for tooling compatibility even though v3.2 is published.

---

## 1. Source inventory: what was actually inspected

**What was inspected and what was not.** The table separates what I opened (web-rendered official artifacts and release notes) from what is documented only. I could not download and unzip `EAXMI.zip` from this environment: GitHub tree and zip URLs were blocked. So the XMI version, the file layout and the presence of EA-specific tags inside the XMI are **not verified**, and they should be your first hands-on check (Phase 0 below).

### 1.1 Candidate sources

| Source | Format | Status / versioning | Verified facts | Machine-readability for a converter |
|---|---|---|---|---|
| **INSPIRE-MIF/uml-models** (GitHub) | EA project (EAP) + XMI exports in `approved/ea+xmi/EAXMI.zip` and `draft/ea+xmi/EAXMI.zip`; HTML view; Feature Catalogue\[1\] | **Approved** = only IR (Implementing Rules) models for Annex I+II+III. **Draft** = IR + TG-extended models, "to be used with caution".\[1\]\[2\] Releases: r4618 (08/05/2014), v2022.2, v2023.1, v2023.2, v2024.1, **v2025.1 (31/01/2025, latest)**\[3\] | *Verified (release notes):* v2022.2 "made available EA project used to derive v4 of GML schemas" and changed SO `soilDerivedObjectObservation` from 1 to [1..*]. v2024.1 "Converted enumerations into codelists" (#130), aligned the CP UML structure (#50) and added an association to LandCoverUnit (#131). v2025.1 changed AM `specializedZoneType` to 0..*\[3\] | **Best source.** Full UML semantics: stereotypes, tagged values, voidable, association classes, constraints. EAP needs EA, or ShapeChange's EA loader, which uses EA's Java API on Windows. XMI is tool-neutral but EA dialect (see 1.3) |
| **INSPIRE Knowledge Base "INSPIRE data models"** | Links to FC, HTML, Mapping Tables, EA/XMI, schema repo\[4\] | The Approved distribution is maintained. The Draft distribution "is not maintained, and all data models contained therein might be not aligned with the official versions"\[4\] | *Verified (page text)* | Index only; it points back to the GitHub artifacts |
| **Feature Catalogue (approved)** `inspire-mif.github.io/uml-models/approved/fc/` | Generated HTML (ShapeChange-style FC) | Dated 31/01/2025. "each application schema is versioned separately"\[5\] | *Verified (fetched):* lists Voidable, Multiplicity, value type (with "(code list)", "(data type)" or "(spatial object type)" kind), definitions and tagged values (e.g. `obligation = IR`) per property\[5\] | Good **validation oracle**, since it is generated from the same EA model. Poor primary input: HTML scraping, no stable IDs |
| **XSD repository** `inspire.ec.europa.eu/schemas` (official) + GitHub mirror INSPIRE-MIF/application-schemas | GML 3.2 application schemas (ShapeChange-generated) | Official location "is, and will remain, https://inspire.ec.europa.eu/schemas". \[6\] Releases by 31 Jan and 31 Jul,\[7\] plus hotfixes.\[7\] Semantic versioning: major = breaking, minor = backward-compatible, bugfix\[7\] | *Verified:* v2024.1 moved BaseTypes to 4.0 (removed `VerticalPositionValue`) and AU, US-common and others to 5.0, cascading major bumps. SO 4.0.2 added the missing OM_Observation associations.\[8\] Older snapshots are kept in dated folders (e.g. `/schemas/2021.1/`)\[7\] | **Lossy.** See 1.3 |
| **Codelists: INSPIRE Registry → EU Vocabularies** | SKOS/RDF and ISO 19135 views (historically `.rdf`, `.json`, `.xml` per register) | The Registry moved into EU Vocabularies on 1 July 2026; migration completed 16 September 2026.\[9\] "Existing identifiers and links under inspire.ec.europa.eu continue to resolve, and API access works as before"\[10\] | *Verified (official pages):* separate registers exist for code lists, enumerations, **extensibility**, application schemas, feature concepts and more.\[11\] *Not verified:* whether `.json`/`.rdf` content negotiation still behaves identically after the migration (subagent probes timed out or returned HTTP 429) | **Use as semantic anchor** (valueId/semanticId URIs). Cache a snapshot; do not depend on it at build time |
| **INSPIRE RDF vocabularies** (inspire-eu-rdf/inspire-rdf-vocabularies; ARE3NA RDF guidelines) | Turtle/OWL generated with ShapeChange | Repository describes them as "**draft** RDF vocabularies for (selected) INSPIRE spatial object types"\[12\] | *Verified (README):* only selected themes. The guidelines require "an application schema shall be converted into a single OWL ontology"\[13\] | Useful for **semanticId alignment** (e.g. locn, GeoSPARQL). Unsuitable as primary input: incomplete and draft |
| **INSPIRE-MIF/model-transformation-rules** | Documented generic rules (from MIWP Action 2017.2)\[14\] | Encoding-agnostic simplification rules (flattening etc.)\[14\] | *Verified (README)* | Directly reusable **as the specification of the flattening rule set** |

### 1.2 Inventory statistics (what could be quantified)

*Verified from the approved Feature Catalogue (31/01/2025):* about **75 application schemas** in the table of contents (hand count, ±2). Specialised Observations sub-packages (Gridded, Point, Trajectory/Profile) are not counted, and several schemas (Base Types 2, Land Use Nomenclature, LandCoverNomenclature, Observable Properties, Energy Resources Base) define no spatial object types.

| Theme / schema (first test set) | Spatial object types (verified from FC TOC) | Notable constructs (verified unless marked) |
|---|---|---|
| **Soil (SO)** | 12: DerivedSoilProfile, ObservedSoilProfile, ProfileElement, SoilBody, SoilDerivedObject, SoilHorizon, SoilLayer, SoilPlot, SoilProfile, SoilSite, SoilThemeCoverage, SoilThemeDescriptiveCoverage\[5\] | Association class **DerivedProfilePresenceInSoilBody**: "Interval that defines the minimum and maximum percentage of the area of the soil body represented by a specific derived soil profile". The role `isDescribedBy` is voidable, [1..*].\[15\] Abstract SoilProfile and ProfileElement; coverages; OM_Observation links (fixed in XSD 4.0.2) |
| **Existing Land Use (ELU)** | 2 (ExistingLandUseDataSet, ExistingLandUseObject). Gridded Land Use and Sampled Land Use are separate schemas\[5\] | Dataset→member aggregation; HILUCS codelist plus specificLandUse |
| **LandCoverVector (LCV)** | 2 (LandCoverDataset, LandCoverUnit). LandCoverRaster (LandCoverGridCoverage) and LandCoverNomenclature are separate\[5\] | Association to LandCoverUnit added in v2024.1.\[3\] The time-stamped LandCoverObservation data type is *from TG, not verified in FC* |
| **AdministrativeUnits (AU) v5.0** | 3 (AdministrativeBoundary, AdministrativeUnit, Condominium)\[5\] | 1 data type (ResidenceOfAuthority). Codelists: LegalStatusValue, TechnicalStatusValue, AdministrativeHierarchyLevel (1stOrder–6thOrder), CountryCode. No unions or enumerations. All association roles are voidable; `administeredBy` is derived. 3 OCL constraints (`AdmininstrativeUnitHighestLevel` [sic], `AdministrativeUnitLowestLevel`, `CondominiumsAtCountryLevel`). Self-associations upperLevelUnit/lowerLevelUnit form a **graph**\[5\] |
| **CadastralParcels (CP)** | 4 (BasicPropertyUnit, CadastralBoundary, CadastralParcel, CadastralZoning)\[5\] | UML restructured in v2024.1\[3\] |
| **Base Types / Activity Complex example** | ActivityComplex (supertype of EnvironmentalManagementFacility, Holding, ProductionFacility)\[5\] | `beginLifespanVersion` voidable [1]; `geometry: GM_Object`; `PT_FreeText` descriptions; `ThematicIdentifier`; `obligation = IR` tag on codelist attributes\[5\] |

**Not quantified (left for automated Phase 0):** total counts of data types, unions, enumerations, codelists and abstract classes, plus maximum inheritance depth and association-class count across all ~75 schemas. These must come from parsing the XMI/SCXML, not from HTML. Make the inventory script the first deliverable; it doubles as the converter's parser test. The FC confirms that union types exist (e.g. `AreaOfResponsibilityType`, `ServiceLocationType` in Governmental Services).\[5\] Note that v2024.1 converted most enumerations to codelists, so enumeration counts in older literature are out of date.\[16\]

### 1.3 Why XSD is not the primary input (verified evidence)

- **Information demonstrably lost in XSD.**
  - INSPIRE-MIF/application-schemas issue #41: in MineralResources, `sourceReference: DocumentCitation[1..*]` survives in the XSD "only mentioned in the appinfo tag". The XSD instead gets an xlink property, although a «dataType» cannot be referenced.\[17\]
  - Issue #83: `UtilityNetwork.authorityRole: RelatedParty` (a data type) is encoded as `gml:ReferenceType`.\[18\]
  - These are UML→XSD encoding artefacts that a converter would inherit.
- **Constraints and codelist rules are not in XSD.** The TGs themselves note: "Not all constraints defined in the application schemas can be mapped to XML", and codelist-value obligations "cannot be mapped to the XML schema".\[19\]
- **Voidable and association classes are mangled in XSD.** Voidable becomes `nillable` plus `nilReason`. Association classes are flattened into intermediate property types. Stereotypes and tagged values (extensibility, `obligation`) are absent or only in `appinfo`. *(Documentation-based, consistent with the INSPIRE GML encoding rule.)*
- **Even mature XSD tooling struggles.** In the Safe Software FME Community thread "FME Schema from XSD for INSPIRE not complete?", the diagnosis was that the v5 ProtectedSite schemas moved legalFoundationDate and legalFoundationDocument into the DesignationType element of siteDesignation, which FME maps "as an xml fragment", hiding the embedded child elements.
- **EA XMI caveats (documented by ShapeChange).** When exporting XMI 1.x, "EA uses 0..* as the default multiplicity for association ends where the multiplicity has not been defined", and it encodes unspecified-navigability associations as source→target. ShapeChange also notes its XMI 1.0 loader "is not up-to-date" and recommends EA or SCXML input.\[20\]

---

## 2. Construct-by-construct mapping INSPIRE/ISO → AAS v3

AAS references: IDTA-01001 Part 1. v3.2 is published (Release 26-01) and v3.3 is "in progress".\[21\]\[22\] The IEC 61360 data specification (IDTA-01003-a) is v3.1.1.

| INSPIRE / ISO construct | Recommended AAS representation | Information loss / notes |
|---|---|---|
| «applicationSchema» (e.g. `so` 4.0) | One **namespace + version** for the generated SMT set. Set `AdministrativeInformation.version/revision` from the schema version | Lossless if the schema URI and version go into the semanticId (e.g. `http://inspire.ec.europa.eu/applicationschema/so`) |
| «featureType» (concrete) | One **Submodel Template** per concrete feature type (`kind=Template`). Instances become Submodels; see §5 for granularity | Feature identity semantics → `Submodel.id` + `semanticId` |
| «featureType» abstract / inheritance | **Flatten** inherited properties into each concrete subtype. Record the lineage with `supplementalSemanticIds` pointing to each supertype CD | AAS SMTs have no inheritance. Polymorphic slots (property typed by an abstract class) need a choice construct (see «union») |
| «dataType» | **SubmodelElementCollection** with its own CD | Lossless. Reuse the same CD everywhere the data type occurs |
| «union» | SMC with all alternatives as optional children + Qualifier `SMT/Cardinality=ZeroToOne` on each + a custom constraint qualifier "exactly one of" | **Loss of the XOR constraint** in the metamodel. Enforce it in the validator |
| «enumeration» (few remain after v2024.1) | Property `xs:string` + CD with IEC 61360 **valueList** (value + valueId) | Lossless for closed lists |
| «codeList» | Property `xs:string` (or `valueId` usage) whose CD references the codelist URI. Embed the valueList only for `extensibility=none`. Store the extensibility (none/narrower/open/any) in a CD Extension | AAS valueList is closed by nature. **Open/any lists cannot be closed** → no embedded valueList, validate against the snapshot plus national extensions |
| «voidable» | Element stays optional in the SMT. In the instance: omit, or include with Qualifier `inspire:nilReason` = `unknown`/`unpopulated`/`withheld` | No null-with-reason in AAS. The Qualifier convention must be documented in the SMT |
| «lifeCycleInfo» (begin/endLifespanVersion) | Properties `xs:dateTime` (keep), optionally mirrored to `AdministrativeInformation.createdAt/updatedAt` (new in v3.2) | v3.2 timestamps are "business values", not object-version history.\[23\] **Do not replace** INSPIRE lifespan |
| «leaf» / «type» / «estimatedType» | Structural. «type» from ISO is treated like «dataType» | — |
| Multiplicity [1] / [0..1] / [0..*] / [1..*] | Qualifier `SMT/Cardinality` = One / ZeroToOne / ZeroToMany / OneToMany. For upper bound >1, wrap in **SubmodelElementList** | List items lose idShort (AASd-120).\[24\] The FC "ordered" property → `orderRelevant` |
| Composition / inline association to «dataType» | Nested SMC or list | Lossless |
| Association to «featureType» (by-reference / xlink) | **ReferenceElement** (ModelReference to target Submodel), or ExternalReference to the inspireId URI if the target lives outside the AAS | Bidirectional roles: emit only the navigable/owning end, mark the inverse as derived |
| Association class (e.g. DerivedProfilePresenceInSoilBody) | **SubmodelElementList of AnnotatedRelationshipElement** (first = source, second = target, annotations = class attributes such as `derivedProfilePercentageRange` as Range). Alternative: list of SMC {ReferenceElement + attributes} | AnnotatedRelationshipElement annotations must be DataElements → **RangeType maps to Range**. Complex association-class attributes force the SMC alternative |
| Recursion / cycles (WRBSoilNameType qualifiers/`over`, ProfileElement `isPartOf`, AU upper/lowerLevelUnit, network topology) | Break at feature boundaries with ReferenceElements. For data-type recursion, unroll to a configurable depth N, then emit a ReferenceElement or Blob | AAS is a containment tree; the v3.2 recursion depth guidance is minimum 32.\[25\] **Unbounded recursion cannot be templated** |
| CharacterString / Boolean / Integer / Real / Number / Date / DateTime / URI | `xs:string` / `xs:boolean` / `xs:integer` (or `xs:long`) / `xs:double` / `xs:decimal` / `xs:date` / `xs:dateTime` / `xs:anyURI` | Number → `xs:decimal` (or `xs:double`) is a choice; record it in the CD |
| Measure / Length / Area (value + uom) | Property `xs:double` + CD dataType `REAL_MEASURE` + `unit`/`unitId` | **AASc-3a-009** requires a unit if a *_MEASURE type is used.\[26\] INSPIRE often leaves the uom to the instance → use a generic CD without MEASURE or with a uom Qualifier |
| LocalisedCharacterString / PT_FreeText / GeographicalName spelling | **MultiLanguageProperty** | GeographicalName is a rich data type (script, pronunciation, nameStatus) → an SMC whose spelling text is an MLP |
| RangeType (upper/lower/uom) | **Range** with valueType + uom Qualifier or CD unit | v3.1+ no longer treats a missing min/max as ±∞,\[25\] so document the semantics |
| Identifier (namespace/localId/versionId) | SMC `inspireId` {namespace, localId, versionId} **and** `Submodel.id` = `{namespace}/{localId}` URI. The asset itself gets a `specificAssetId` with name `inspireId` | versionId vs AAS versioning: keep both. AAS `version`/`revision` are numeric in v3.2\[23\] and cannot hold arbitrary versionId strings |
| validFrom / validTo | Properties `xs:dateTime` | — |
| GM_Point / GM_Curve / GM_Surface / GM_MultiSurface / GM_Object | **Blob** `contentType=application/geo+json` (user decision). semanticId on the Blob = INSPIRE property CD; Qualifier records the declared ISO type | GeoJSON (RFC 7946) lacks arcs/clothoids, solids, TIN, rings with curves, and non-WGS84 CRS. See inconsistency I-9 |
| Coverages (ISO 19123/GMLCOV: SoilThemeCoverage, ElevationGridCoverage, LandCoverGridCoverage, Orthoimagery) | **File** (GeoTIFF/COG/netCDF) or ExternalReference to OGC API Coverages/WCS, plus an SMC with coverage metadata (domainExtent, rangeType description) | Templating of the range set is out of scope; point to external data |
| OM_Observation (ISO 19156) | Dedicated SMC `Observation` {phenomenonTime, resultTime, procedure ref, observedProperty URI, featureOfInterest ref, result}. Time-series results → reuse **IDTA Time Series Data** SMT | SO, EF, Specialised Observations. Parameter codelists need national extension (as found in your manual test) |
| CI_Citation / CI_ResponsibleParty / RelatedParty / Contact / EX_Extent / TM_Period | CI_* and RelatedParty → reuse IDTA **Contact Information (02002)**; DocumentCitation → SMC + File; TM_Period → SMC {begin, end} | ISO 19115 is huge → profile only the attributes INSPIRE actually uses |
| OCL constraints | ConceptDescription Extension (text) + validator rules | AAS has no constraint language. Rules must be hand-written or translated per constraint |

---

## 3. Catalogue of inconsistencies

| # | Issue | Concrete examples | Severity | Resolution options (trade-offs) |
|---|---|---|---|---|
| I-1 | **No inheritance in SMTs** | ActivityComplex → ProductionFacility/Holding; SoilProfile → Observed/DerivedSoilProfile; ProfileElement → SoilLayer/SoilHorizon; TransportLink hierarchy | High | (a) Flatten into leaves (recommended; follow model-transformation-rules). (b) "Base SMT + specialised SMT" composition via two Submodels, which loses atomicity. (c) Keep abstract classes as SMTs, with `supplementalSemanticIds` for typing |
| I-2 | **Polymorphic slots** (property typed by an abstract class or GM_Object) | `ActivityComplex.geometry: GM_Object`; ProfileElement members | Medium | Choice SMC (union pattern) or a Qualifier `inspire:concreteType` on the instance |
| I-3 | **Association classes** | `DerivedProfilePresenceInSoilBody` (SoilBody↔DerivedSoilProfile with percentage range) | Medium | AnnotatedRelationshipElement list (clean, if annotations are DataElements) vs SMC with ReferenceElement + attributes (general) |
| I-4 | **Graphs and cycles** | AU upperLevelUnit/lowerLevelUnit; Soil `isDerivedFrom`; network link/node topology; WRB `over` qualifiers | High (network themes), Medium (SO/AU) | ReferenceElements at feature boundaries. Unroll data-type recursion to depth N. Emit only the owning direction and mark the inverse as derived |
| I-5 | **Voidable/nilReason** | AU: all association roles and legal/technicalStatus; ActivityComplex `beginLifespanVersion` [1] voidable\[5\] | Medium | Qualifier `inspire:nilReason` (recommended). Alternatives: sibling Property `<name>_nilReason` (verbose), or Extension (less visible to SMT tools) |
| I-6 | **Open codelists vs closed valueList** | HILUCSValue + `specificLandUse` (national); LandCoverClassValue (dataset-defined nomenclature); SO/OM parameter codelists | High for LC/SO | Never embed valueList for narrower/open/any. Bind the codelist URI as CD semanticId. Validate against the snapshot + a national-extension register (e.g. ATKIS OBJART, BK50 Bodenarten, LB-NRW classes) |
| I-7 | **idShort constraints** | AASd-002: ≥2 characters, letters/digits/hyphen/underscore, starting with a letter, no trailing hyphen. AASd-022: unique per namespace.\[23\]\[27\] Single-character INSPIRE names (e.g. `Id` in Permission is fine; potential collisions after flattening such as two `name` attributes from different supertypes) | Low–Medium | Deterministic name mangling with a collision suffix. Original name kept in `displayName` and CD `preferredName` |
| I-8 | **SubmodelElementList homogeneity** | Lists of polymorphic members (e.g. ProfileElement = SoilLayer or SoilHorizon); AASd-107/108/109 require a single element type, value type and semanticId\[24\] | Medium | Split into one list per concrete type, or a list of SMC with a common semanticId of the abstract type + concreteType Qualifier |
| I-9 | **Geometry / GeoJSON** | GM_Curve with arcs (CP boundaries), 3D (Buildings3D), TIN (ElevationTIN), GM_Solid; ETRS89/EPSG:25832 source CRS | High (fidelity), Low (for green-space 2D polygons) | RFC 7946 (August 2016) mandates a WGS 84 lon/lat CRS equivalent to urn:ogc:def:crs:OGC::CRS84 (§4), and its Appendix B states that the "crs" member of the 2008 spec "is no longer used". Options: (a) reproject to CRS84 in the Blob and store the original-CRS geometry as a second Blob/File (`application/gml+xml`, or GeoJSON with "crs" flagged as non-RFC). (b) Densify arcs with a recorded tolerance. (c) Reject solids/TIN → File reference. For PostGIS ingest, (a) gives lossless round-trip |
| I-10 | **Measures without fixed unit** | `InputOutputAmount.amount: Measure`; soil parameters | Medium | CD without *_MEASURE + uom Qualifier, or pinned UCUM unit per national profile (avoids AASc-3a-009 violation, as seen in ESMF issue #1053)\[26\] |
| I-11 | **Coverages** | SoilThemeCoverage, ElevationGridCoverage, LandCoverGridCoverage | Medium | File/External reference + metadata SMC. No element-level modelling |
| I-12 | **Versioning semantics** | inspireId.versionId (string), lifespan, schema major versions (BaseTypes 3.3→4.0 cascade)\[8\] | Medium | Keep INSPIRE versioning as Properties. Map the schema version to SMT `AdministrativeInformation`. Generate new SMT ids on major schema bumps |
| I-13 | **OCL constraints** | AU `CondominiumsAtCountryLevel`, `AdministrativeUnitLowestLevel`\[5\] | Low | Text in CD Extension + hand-coded validator rules |

---

## 4. Prior art and tooling

- **INSPIRE/ISO 19109 → AAS.** My searches turned up no published converter or IDTA working group covering INSPIRE, GML application schemas or CityGML. Treat this as "not found", not as proven absent. The nearest AAS work in infrastructure is application-level, e.g. Cavalieri & Gambadoro's AAS-based digital twin of a water supply system (Sensors 24(5):1360, 2024), whose authors state that AAS use for water supply systems "is not present in the current literature", and 3D visualisation linking AAS to geometry (Springer). The IDTA content hub lists an IFC-linking use case ("Link IfcSensor, IfcActuator…to type and instance AAS"), which shows BIM↔AAS work by reference, not by model conversion.\[28\]
- **Model-to-AAS generators (design references).**
  - Eclipse ESMF `esmf-aspect-model-aas-generator` (SAMM→AAS): mature, and its bug tracker shows typical pitfalls: issue #1053 reports REAL_MEASURE / INTEGER_MEASURE ConceptDescriptions generated without a unit, flagged by aas-core3.1-typescript 1.0.1 as an AASc-3a-009 violation.
  - *Model-driven realization of IDTA submodel specifications* (arXiv 2406.14470): generates Java APIs from SMT specs.\[29\]
  - DTDL→AAS (Sensors 2023, 23(18):7742, which shows that "a generic mapping between DTDL and AAS can be applied for transformation") and OWL↔AAS mappings (RML/RDFex, hsu-aut/CSS-AAS-OWL).
  - aas-core-works `aas-smt-codegen`: transpiles SMTs.\[30\]
- **ShapeChange (interactive instruments).**
  - Loads EA models via the EA Java API, SCXML, or (outdated) XMI 1.0.\[31\]
  - Transformations include Profiler, Naming modifier and the powerful **Flattener** (inheritance flattening, type flattening, measure flattening, multiple-geometry handling).\[32\]\[33\]
  - Targets: XSD, Schematron, JSON Schema, RDF/OWL/SKOS, SQL DDL, ArcGIS, FC, Model Export (SCXML).\[33\]\[34\]\[35\]\[36\]
  - Architecture: "modular, allowing for the specification of additional input formats, transformations or targets by implementing the underlying interfaces".\[31\] An **AAS target is a natural extension point**.
- **hale»studio (wetransform).** Instance transformation into INSPIRE GML. Relevant later for mapping ATKIS/LB/BK50 *instances*, not for schema conversion. *(Not inspected in detail.)*
- **AAS SDKs.**
  - aas-core3.0 / **aas-core3.1** (Python, C#, TS, Go, C++; generated from formal meta-models, with verification).\[37\]
  - Eclipse BaSyx Python SDK: the PyPI release documents metamodel v3.0.1, and a development branch shows v3.1.2. It includes a compliance tool.\[38\]\[39\]
  - AAS4J (Java).
  - A third-party 2026 blog states that no released BaSyx build claims v3.2 support.\[22\] This is unverified secondary content, but consistent with the SDK READMEs.
- **Reusable IDTA SMTs.**
  - **IDTA 02045-1-0 Data Model for Asset Location** (July 2024; includes CoordinateSystems lists, omlox mapping).\[40\] It targets indoor/industrial positioning, so use it as an optional *point* location, not for parcels.
  - **Digital Nameplate 02006-3-0** (AddressInformation drop-in).\[41\]
  - **Contact Information 02002** (for RelatedParty/CI_ResponsibleParty).\[42\]
  - **Time Series Data** (for OM results).
  - Hierarchical Structures (for AU hierarchy or green-space part-of trees).
  - Handover Documentation (for DocumentCitation/legal documents).

---

## 5. Recommended architecture and implementation plan

### 5.1 Input decision
Use the **approved EA model** as the single source of truth. Load it with **ShapeChange** and export to **SCXML** (ShapeChange Model Export) once per INSPIRE release. Then process SCXML in your own pipeline.

Justification:
- SCXML preserves stereotypes, tagged values, voidable flags, association classes, constraints and documentation in a documented XML format.
- It avoids EA-XMI dialect issues (default multiplicities, navigability).\[20\]
- It decouples development from the Windows/EA dependency.

Fallback: parse XMI directly with lxml, resolving `xmi:idref` and EA `TaggedValue` extensions. Use the FC HTML only as a **regression oracle**, comparing per-property voidable, multiplicity and value type.

### 5.2 Pipeline
1. **Ingest:** SCXML (or XMI) → **intermediate model (IM)**: Package, Class(stereotype, abstract, supertypes), Property(type, multiplicity, voidable, ordered, isNavigable, assocClass), Constraint, TaggedValues, Documentation (`-- Name --`/`-- Definition --`/`-- Description --` blocks parsed separately).
2. **Resolve external types** via a curated **ISO type map** (ISO 19103/19107/19108/19115/19123/19156 → AAS pattern). This is a hand-maintained YAML file, versioned.
3. **Rule engine (configurable YAML profiles):**
   - inheritance flattening
   - union pattern
   - association handling (containment vs reference vs AnnotatedRelationship)
   - recursion depth
   - voidable policy
   - codelist policy (by extensibility)
   - idShort mangling
   - list vs collection
   - geometry policy (CRS84 + original-CRS Blob)
4. **National extension layer:** a separate profile that adds (a) codelist extensions (ATKIS OBJART/Funktion, LB-NRW classes, BK50 parameters) as additional CDs whose `isCaseOf` / `supplementalSemanticId` points to the INSPIRE value, (b) additional Properties in a namespaced SMC `nationalExtension` (e.g. `de-nw`), and (c) profiling, i.e. dropping unused optional properties. It must never edit the INSPIRE-derived SMT in place.
5. **Emit:** AAS Environment (Submodels kind=Template + ConceptDescriptions) as JSON/XML/AASX via aas-core3.1-python (or BaSyx for AASX packaging).
6. **Validate:** aas-core verification (all AASd/AASc constraints), BaSyx compliance tool, an AASX Package Explorer smoke test, plus custom checks (union XOR, OCL ports, codelist membership).\[43\]\[44\]
7. **Report:** per-schema **loss ledger**, i.e. every UML construct with mapping status {lossless, recorded-lossy, dropped}. Its coverage metric is your scientific contribution.

### 5.3 ConceptDescriptions and semanticIds
- One CD per class, property and codelist value, using IEC 61360 `preferredName` (UML name + FC "-- Name --"), `definition` (FC definition; multilingual where the Feature Concept Dictionary provides it), `dataType`, `unit`, and `valueList` (closed lists only).
- **CD ids and semanticIds:** use registry URIs where they exist:
  - `http://inspire.ec.europa.eu/applicationschema/<prefix>`
  - `http://inspire.ec.europa.eu/featureconcept/<Name>`
  - `http://inspire.ec.europa.eu/codelist/<List>/<value>`
  - These are guaranteed to keep resolving after the EU Vocabularies migration.\[10\]\[45\]
- For properties, which have no official URI, mint a deterministic URI under your own namespace that embeds the schema version, e.g. `https://<your-domain>/inspire/so/4.0/SoilBody/soilBodyLabel`. Add a `supplementalSemanticId` to the INSPIRE RDF vocabulary term where one exists.

### 5.4 Granularity
- **One SMT per concrete feature type** (flattened), grouped by application schema, e.g. `SO-SoilBody`, `SO-DerivedSoilProfile`, `ELU-ExistingLandUseObject`, `LCV-LandCoverUnit`, `AU-AdministrativeUnit`, `CP-CadastralParcel`.
- One SMT per schema would create huge templates and break SubmodelElementList homogeneity.
- **Feature instances = Submodel instances**, id = inspireId URI.
- **Green-space AAS** (asset = Grünanlage, `globalAssetId` = your stable URI, `specificAssetIds` = ATKIS object id + inspireId) holds:
  - its own identity Submodel (Nameplate-like) with the geometry Blob
  - **references** to the ELU, LCV, SO and AU (and CP) Submodels that describe it
  - An ELU object usually corresponds 1:1 to a green space. LC units, soil bodies, AUs and parcels are shared, n:m objects.
- **Shared objects** (an AU or SoilBody covering many green spaces) live as Submodels in their **own AAS** (asset = the administrative unit / soil body), which the green-space AAS references via ReferenceElement or a RelationshipElement with an overlap-share annotation. This avoids duplication and maps cleanly to PostGIS tables per feature type.

### 5.5 Tech stack
- **Python 3.11+**:
  - `lxml` (SCXML/XMI)
  - `pydantic` (IM)
  - **aas-core3.1-python** (types + verification)
  - `basyx-python-sdk` (AASX I/O, compliance tool)
  - `pyproj` + `shapely` (CRS84 reprojection, densification)
  - `rdflib` (codelist SKOS snapshots)
  - `pytest` + `hypothesis`
- **Java** only for the ShapeChange step (CLI configuration, no custom code initially). Write a native ShapeChange AAS Target later if upstream contribution is desired.
- **AAS version:** generate **v3.1.x** now, since the SDKs and BaSyx are aligned there. Keep the version-specific semantic URIs (`admin-shell.io/aas/3/1/...` vs `/3/2/`) in one adapter so the v3.2 switch (createdAt/updatedAt, AssetKind Batch, numeric version) is a configuration flag.

### 5.6 Testing
- **Golden tests:** per-property comparison of IM vs Feature Catalogue (voidable, multiplicity, type).
- **Round-trip:** IM → SMT → reconstructed IM, diff limited to the loss ledger.
- **Instance tests:** INSPIRE GML samples (e.g. NRW SO/AU/CP download services) → AAS instances → PostGIS → GML again via hale or a simple writer; compare geometries within tolerance.
- **Theme-by-theme CI:** all ~75 schemas must emit verifiable AAS. Track the coverage metric per release.

### 5.7 Phased plan
| Phase | Scope | Exit criterion |
|---|---|---|
| 0 (1–2 wks) | Download `approved/ea+xmi/EAXMI.zip` (v2025.1), record the XMI version and files, run ShapeChange → SCXML, build the inventory script (counts of all construct types per schema) | Verified statistics table for all schemas; resolves the open items of §1 |
| 1 | IM + rules for AU and CP (simple: hierarchy graph, codelists, voidable, CP geometry with possible arcs) | Verified SMTs + CDs; loss ledger |
| 2 | ELU + LCV (open codelists, HILUCS + specificLandUse, LandCoverObservation time series, dataset aggregation) | National extension profile `de-nw` for ATKIS/LB codes |
| 3 | SO (association class, abstract ProfileElement, OM_Observation, coverages, WRB recursion) | Reproduces your manual SoilBody test automatically; BK50 parameter extension |
| 4 | Green-space AAS composition + PostGIS client ingest | End-to-end demo NRW |
| 5 | All Annex themes (networks, coverages, EF, GE) | Coverage metric published per theme |

---

## 6. Open questions and risks

- **Unverified artifact details (highest priority).** The XMI version, EA tag names (e.g. `extensibility`, `vocabulary`, `codeList`), per-schema file layout, and full counts of unions, enumerations, codelists and association classes. All are resolvable in Phase 0.
- **INSPIRE governance in transition.**
  - Registry → EU Vocabularies (1 July 2026; completed 16 September 2026). Geoportal retired 1 July 2026 in favour of data.europa.eu.\[9\]\[46\]
  - URIs are promised stable,\[10\] but API behaviour (`.json`/`.rdf` suffixes) should be monitored. Cache codelist snapshots with a date.
  - The UML and schema maintenance cadence is twice-yearly. The latest UML release found is v2025.1,\[3\]\[7\] so check whether 2025.2/2026.x releases exist before freezing.\[8\]
- **Breaking schema changes.** The v2024.1 enumeration→codelist conversion caused major bumps (BaseTypes 4.0, AU 5.0).\[8\]\[16\] SMT ids must embed the schema version, and regeneration must be one command.
- **Draft vs approved.** TG-extended models (e.g. extended PF, AF, US) are "not maintained" and may diverge,\[4\] so only support them behind a flag.
- **AAS version churn.** v3.0 → v3.1 → v3.2 (2026), v3.3 in progress. v3.1 relaxed idShort (hyphen allowed) and deprecated `category`.\[25\] v3.2 adds timestamps and makes version/revision numeric.\[23\]\[47\] Ecosystem support lags (BaSyx).\[22\]
- **GeoJSON policy conflict.** RFC-compliant CRS84 vs the national ETRS89/UTM32 requirement.\[48\]\[49\] Decide explicitly, and document it in the SMT, before generating instances.
- **Semantic ownership.** Minting property URIs under your own domain makes you a de facto maintainer. Consider proposing them to the INSPIRE MIG/MIF, or to IDTA as an "External" SMT registration.\[28\]

## Sources

1. [GitHub - INSPIRE-MIF/uml-models: Community for the discussion of change proposals to the INSPIRE UML models.](https://github.com/INSPIRE-MIF/uml-models)
2. [INSPIRE UML models](https://inspire-mif.github.io/uml-models/)
3. [Releases · INSPIRE-MIF/uml-models](https://github.com/INSPIRE-MIF/uml-models/releases)
4. [INSPIRE data models - INSPIRE Knowledge Base - European Commission](https://knowledge-base.inspire.ec.europa.eu/tools/inspire-data-models_en)
5. [Feature Catalogue'INSPIRE application schemas'](https://inspire-mif.github.io/uml-models/approved/fc/)
6. [GitHub - INSPIRE-MIF/application-schemas: Community for the discussion of change proposals to the INSPIRE XML schemas. · GitHub](https://github.com/INSPIRE-MIF/application-schemas)
7. [application-schemas/governance-release-process/process.md at main · INSPIRE-MIF/application-schemas](https://github.com/INSPIRE-MIF/application-schemas/blob/main/governance-release-process/process.md)
8. [Releases · INSPIRE-MIF/application-schemas](https://github.com/INSPIRE-MIF/application-schemas/releases)
9. [News - EU Vocabularies - Publications Office of the EU](https://op.europa.eu/en/web/eu-vocabularies/news)
10. [INSPIRE Registry - EU Vocabularies - Publications Office of the EU](https://inspire.ec.europa.eu/registry/)
11. [INSPIRE Registry - EU Vocabularies - Publications Office of the EU](https://op.europa.eu/en/web/eu-vocabularies/inspire-registry)
12. [GitHub - inspire-eu-rdf/inspire-rdf-vocabularies: RDF Vocabularies for INSPIRE application schemas · GitHub](https://github.com/inspire-eu-rdf/inspire-rdf-vocabularies)
13. [Guidelines for the RDF encoding of spatial data](https://inspire-eu-rdf.github.io/inspire-rdf-guidelines/)
14. [GitHub - INSPIRE-MIF/model-transformation-rules: Repository including generic INSPIRE model transformation rules, to be used for deriving specific encodings for INSPIRE data.](https://github.com/INSPIRE-MIF/model-transformation-rules)
15. [Feature Catalogue 'INSPIRE application schemas'](https://inspire-mif.github.io/uml-models/draft/fc/)
16. [INSPIRE Schema Updates - wetransform](https://wetransform.to/news-and-events/inspire-schema-updates/)
17. [MineralResources sourceReference problem · Issue #41 · INSPIRE-MIF/application-schemas](https://github.com/INSPIRE-MIF/application-schemas/issues/41)
18. [US\_UtilityNetwork\_authorityRole RelatedParty type to reference inline · Issue #83 · INSPIRE-MIF/application-schemas](https://github.com/INSPIRE-MIF/application-schemas/issues/83)
19. [Scope](https://inspire-mif.github.io/technical-guidelines/data/ad/dataspecification_ad.html)
20. [XMI 1.0 models](https://shapechange.github.io/ShapeChange/3.1.0/application%20schemas/XMI_1.0_models.html)
21. [Part 1: Metamodel (IDTA-01001) - IDTA Specs Documentation](https://industrialdigitaltwin.io/aas-specifications/IDTA-01001/v3.2/index.html)
22. [AAS Metamodel 3.2 (IDTA 26-01): Migration Guide 2026](https://iotdigitaltwinplm.com/aas-metamodel-3-2-idta-release-26-01-migration-2026/)
23. [Common Attributes](https://industrialdigitaltwin.io/aas-specifications/IDTA-01001/v3.2/spec-metamodel/common.html)
24. [Overview of Submodel Element Types :: Asset Administration Shell Documentation](https://zrgt.github.io/aas-specs-antora/IDTA-01001/v3.1/spec-metamodel/submodel-elements.html)
25. [feat: AAS spec/submodel template skills, subagents and v3.2 update by Evaldoes · Pull Request #1 · open-aas/aas-agents](https://github.com/open-aas/aas-agents/pull/1)
26. [\[BUG\] SAMM2AAS: ConceptDescription gets REAL\_MEASURE / INTEGER\_MEASURE without a unit (AASc-3a-009) · Issue #1053 · eclipse-esmf/esmf-sdk](https://github.com/eclipse-esmf/esmf-sdk/issues/1053)
27. [Constraints: Global Invariants - IDTA Specs Documentation](https://industrialdigitaltwin.io/aas-specifications/IDTA-01001/v3.1/spec-metamodel/constraints.html)
28. [IDTA - AAS Submodel Templates](https://industrialdigitaltwin.org/en/content-hub/submodels)
29. [Model-driven realization of IDTA submodel specifications](https://arxiv.org/pdf/2406.14470)
30. [aas-core-works repositories · GitHub](https://github.com/orgs/aas-core-works/repositories)
31. [Packages](https://shapechange.github.io/ShapeChange/3.1.0/get%20started/Packages.html)
32. [ShapeChange/CHANGELOG.md at master · ShapeChange/ShapeChange](https://github.com/ShapeChange/ShapeChange/blob/master/CHANGELOG.md)
33. [ShapeChange](https://www.eurosdr.net/sites/default/files/images/inline/dm_ws_213_shapechange_gco_a_tool_for_model-driven_development_involving_geographic_data.pdf)
34. [Testbed-12 ShapeChange Engineering Report](https://docs.ogc.org/per/16-020.html)
35. [OGC Testbed-17: Model-Driven Standards Engineering Report](https://docs.ogc.org/per/21-035r1.html)
36. [ShapeChange - interactive instruments GmbH](https://www.interactive-instruments.de/en/shapechange/)
37. [aas-core-works · GitHub](https://github.com/aas-core-works)
38. [GitHub - JAB1305/basyx-python-sdk: The Eclipse BaSyx Python SDK, an implementation of the Asset Administration Shell (AAS) for Industry 4.0 systems · GitHub](https://github.com/JAB1305/basyx-python-sdk)
39. [GitHub - eclipse-basyx/basyx-python-sdk: The Eclipse BaSyx Python SDK, an implementation of the Asset Administration Shell (AAS) for Industry 4.0 systems · GitHub](https://github.com/eclipse-basyx/basyx-python-sdk)
40. [IDTA 02045-1-0 Data Model for Asset Location July 2024](https://industrialdigitaltwin.org/wp-content/uploads/2024/07/IDTA-02045-1-0_Submodel_Data-Model-for-Asset-Location.pdf)
41. [S P E C I F I C AT I O N Submodel Template of the Asset Administration Shell](https://industrialdigitaltwin.org/wp-content/uploads/2024/11/IDTA-02006-3-0_Submodel_Digital-Nameplate.pdf)
42. [Downloads - IDTA](https://industrialdigitaltwin.org/en/content-hub/downloads)
43. [basyx-compliance-tool · PyPI](https://pypi.org/project/basyx-compliance-tool/2.2.0/)
44. [Getting Started — aas-core3.1 1.0.0 documentation](https://aas-core31-python.readthedocs.io/en/latest/getting_started/)
45. [INSPIRE registry](https://inspire.ec.europa.eu/codelist/ClassificationMethodUsedValue)
46. [INSPIRE datasets move to the European Data Portal](https://data.europa.eu/en/news-events/news/inspire-datasets-move-european-data-portal)
47. [AAS Metamodel 3.2 (IDTA Release 26-01): What Changes for Digital Twin Teams in 2026](https://iotdigitaltwinplm.com/web-stories/story-aas-metamodel-3-2-idta-release-26-01-migration-2026/)
48. [Spatial Data on the Web Best Practices](https://www.w3.org/2021/sdw/bp/)
49. [GeoJSON FAQ](https://geojason.com/geojson-faq)
