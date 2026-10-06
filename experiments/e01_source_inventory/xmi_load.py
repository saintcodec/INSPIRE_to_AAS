"""Robust loader for the INSPIRE EA XMI 2.1 export.

The file declares encoding="windows-1252" but contains at least one byte (0x90)
that is undefined in cp1252 (Shift-JIS residue in a Note's `status`), which makes
libxml2 abort with a misleading "Growing input buffer" error. We decode leniently
and report how many replacements were made.
"""
from pathlib import Path
import re

from lxml import etree

ROOT = Path(__file__).resolve().parents[2]
XMI_PATH = ROOT / "data/raw/approved/ea+xmi/EAXMI/INSPIRE_Consolidated_UML_Model_ANNEX I-II-III-Only_IR_2025.1.xml"

NS = {
    "xmi": "http://schema.omg.org/spec/XMI/2.1",
    "uml": "http://schema.omg.org/spec/UML/2.1",
}
XMI_ID = f"{{{NS['xmi']}}}id"
XMI_IDREF = f"{{{NS['xmi']}}}idref"
XMI_TYPE = f"{{{NS['xmi']}}}type"


def load(path: Path = XMI_PATH):
    raw = path.read_bytes()
    text = raw.decode("cp1252", errors="replace")
    replacements = text.count("�")
    text = re.sub(r"^<\?xml[^>]*\?>", "", text, count=1)
    root = etree.fromstring(text, etree.XMLParser(huge_tree=True))
    return root, replacements
