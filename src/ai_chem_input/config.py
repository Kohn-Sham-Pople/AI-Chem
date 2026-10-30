"""A small strict JSON Schema subset, shared with the published schemas."""
import json
import re
from pathlib import Path
from .errors import require, InputError
from .paths import read_small

ID = r'^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$'
HASH = r'^[0-9a-f]{64}$'


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(ID, value), 'SCHEMA', 'id', 2)
    return value


def _pairs(pairs):
    d = {}
    for k, v in pairs:
        require(k not in d, 'JSON_DUPLICATE', exit_code=2)
        d[k] = v
    return d


def loads(data):
    try:
        return json.loads(data, object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(InputError('JSON_NONFINITE', exit_code=2)))
    except (ValueError, UnicodeError):
        raise InputError('JSON_SYNTAX', exit_code=2) from None


def load(path):
    return loads(read_small(path))


def validate(value, schema, field='$'):
    if 'anyOf' in schema:
        for option in schema['anyOf']:
            try:
                validate(value, option, field)
                return value
            except InputError:
                pass
        raise InputError('SCHEMA', field, 2)
    types = {'object': dict, 'array': list, 'string': str, 'integer': int,
             'boolean': bool, 'null': type(None)}
    if 'type' in schema:
        require(type(value) is types[schema['type']], 'SCHEMA', field, 2)
    if 'const' in schema:
        require(type(value) is type(schema['const']) and value == schema['const'], 'SCHEMA', field, 2)
    if 'enum' in schema:
        require(value in schema['enum'], 'SCHEMA', field, 2)
    if isinstance(value, dict):
        props = schema.get('properties', {})
        require(set(schema.get('required', ())) <= set(value), 'SCHEMA', field, 2)
        additional = schema.get('additionalProperties', True)
        if additional is False:
            require(set(value) <= set(props), 'SCHEMA', field, 2)
        for k, v in value.items():
            child = props.get(k, additional if isinstance(additional, dict) else {})
            validate(v, child, field + '.' + k)
    elif isinstance(value, list):
        require(len(value) >= schema.get('minItems', 0) and len(value) <= schema.get('maxItems', 1000000), 'SCHEMA', field, 2)
        for i, item in enumerate(value):
            validate(item, schema.get('items', {}), field + '[' + str(i) + ']')
    elif isinstance(value, str):
        require(not any(x in value for x in ('<', '>', '\x00', '\n', '\r', 'PLACEHOLDER')), 'SCHEMA', field, 2)
        require(len(value) >= schema.get('minLength', 0), 'SCHEMA', field, 2)
        if schema.get('format')=='canonical-decimal':
            require(value!='-0','SCHEMA',field,2)
        if 'pattern' in schema:
            require(re.fullmatch(schema['pattern'], value) is not None, 'SCHEMA', field, 2)
    elif type(value) is int:
        require(value >= schema.get('minimum', -2**63) and value <= schema.get('maximum', 2**63), 'SCHEMA', field, 2)
    return value


def schema_for(kind):
    # Schemas ship inside the package as well as in the repository catalog.
    return loads((Path(__file__).parent / 'schemas' / (kind + '.json')).read_bytes())


def checked(value, kind):
    return validate(value, schema_for(kind))
