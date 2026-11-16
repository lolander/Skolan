import re

import voluptuous as vol


def string(v):
    if v is None:
        raise vol.Invalid("tomt")
    return str(v)


def slug(v):
    v = string(v)
    if not re.fullmatch(r"[a-z0-9_]+", v):
        raise vol.Invalid("ogiltigt id")
    return v


def entity_id(v):
    v = string(v).lower()
    if not re.fullmatch(r"[a-z0-9_]+\.[a-z0-9_]+", v):
        raise vol.Invalid("ogiltigt entity_id")
    return v


def ensure_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]
