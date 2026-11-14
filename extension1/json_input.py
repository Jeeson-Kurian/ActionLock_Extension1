"""Decode evidence without silently choosing between duplicate fields."""
import json


def _unique_fields(pairs):
    obj = dict(pairs)
    if len(obj) != len(pairs):
        raise ValueError("Duplicate JSON field")
    return obj


def load_evidence_json(raw):
    return json.loads(raw, object_pairs_hook=_unique_fields)
