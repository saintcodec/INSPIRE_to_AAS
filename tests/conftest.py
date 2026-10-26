import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from inspire2aas import build, registry, xmi_reader  # noqa: E402


@pytest.fixture(scope="session")
def model():
    return xmi_reader.read()


@pytest.fixture(scope="session")
def reg():
    return registry.read()


@pytest.fixture(scope="session")
def cp_au_templates():
    assert build.main(["CadastralParcels", "AdministrativeUnits"]) == 0
    return build.config.OUTPUT_DIR / "templates" / "cp_au" / "cp_au_templates.json"
