"""Identifiers of generated AAS objects - one place, used by the builder and importable by callers (R5).

An INSPIRE object is identified by its inspireId (namespace + localId). The key used in AAS ids is
    <namespace without scheme>/<localId>
with every character outside [A-Za-z0-9-._~/] percent-encoded (in the localId also "/").
Percent-encoding is reversible, so two different inspireIds never get the same key
(e.g. "L5106_>Q531" -> "L5106_%3EQ531", "L5106_<Q531" -> "L5106_%3CQ531").
"""
import re
from urllib.parse import quote

from . import config


def object_key(namespace: str, local_id: str) -> str:
    ns = re.sub(r"^[A-Za-z][A-Za-z0-9+.\-]*://", "", str(namespace)).strip("/")
    return f"{quote(ns, safe='/-._~')}/{quote(str(local_id), safe='-._~')}"


def template_prefix(template_id: str) -> str:
    """'…/smt/so/4.0.2/SoilBody' -> 'so'"""
    return template_id.split("/smt/", 1)[1].split("/", 1)[0]


def submodel_id(prefix: str, template: str, namespace: str, local_id: str) -> str:
    """Id of the Submodel instance of `template` for one INSPIRE object."""
    return f"{config.BASE_URI}sm/{prefix}/{template}/{object_key(namespace, local_id)}"


def aas_id(prefix: str, namespace: str, local_id: str) -> str:
    return f"{config.BASE_URI}aas/{prefix}/{object_key(namespace, local_id)}"


def asset_id(prefix: str, namespace: str, local_id: str) -> str:
    return f"{config.BASE_URI}asset/{prefix}/{object_key(namespace, local_id)}"
