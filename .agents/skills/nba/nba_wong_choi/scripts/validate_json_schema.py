#!/usr/bin/env python3
"""
validate_json_schema.py — NBA Wong Choi JSON Schema Validator

Validates extractor and sportsbet JSON files against their schemas.
Used by the orchestrator as a pre-flight check before report generation.

Usage:
  python validate_json_schema.py --extractor path/to/nba_game_data.json
  python validate_json_schema.py --sportsbet path/to/Sportsbet_Odds.json
  python validate_json_schema.py --extractor data.json --sportsbet odds.json
  python validate_json_schema.py --extractor data.json --strict  # fail on warnings too

Exit codes: 0 = pass, 1 = schema violation, 2 = file not found
"""
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
import json
import argparse

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources")

# ─── Lightweight JSON Schema Validator ────────────────────────────────────
# No external dependency (no jsonschema package needed).
# Validates required fields, types, enums, and critical constraints.

def _type_check(value, expected_type):
    """Check if value matches JSON Schema type string."""
    type_map = {
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }
    if isinstance(expected_type, list):
        return any(_type_check(value, t) for t in expected_type)
    py_type = type_map.get(expected_type)
    if py_type is None:
        return True  # unknown type, pass
    return isinstance(value, py_type)


def validate_against_schema(data, schema, path="$"):
    """Validate data against a JSON Schema (Draft-07 subset).
    
    Returns: (errors: list[str], warnings: list[str])
    """
    errors = []
    warnings = []

    # Type check
    expected_type = schema.get("type")
    if expected_type:
        if not _type_check(data, expected_type):
            errors.append(f"{path}: expected type '{expected_type}', got '{type(data).__name__}'")
            return errors, warnings

    # Enum check
    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{path}: value '{data}' not in enum {schema['enum']}")

    # String constraints
    if isinstance(data, str):
        if "minLength" in schema and len(data) < schema["minLength"]:
            errors.append(f"{path}: string length {len(data)} < minLength {schema['minLength']}")
        if "pattern" in schema:
            import re
            if not re.match(schema["pattern"], data):
                warnings.append(f"{path}: '{data}' does not match pattern '{schema['pattern']}'")

    # Number constraints
    if isinstance(data, (int, float)):
        if "minimum" in schema and data < schema["minimum"]:
            errors.append(f"{path}: {data} < minimum {schema['minimum']}")
        if "maximum" in schema and data > schema["maximum"]:
            errors.append(f"{path}: {data} > maximum {schema['maximum']}")
        if "exclusiveMinimum" in schema and data <= schema["exclusiveMinimum"]:
            errors.append(f"{path}: {data} <= exclusiveMinimum {schema['exclusiveMinimum']}")

    # Array constraints
    if isinstance(data, list):
        if "minItems" in schema and len(data) < schema["minItems"]:
            errors.append(f"{path}: array length {len(data)} < minItems {schema['minItems']}")
        if "maxItems" in schema and len(data) > schema["maxItems"]:
            warnings.append(f"{path}: array length {len(data)} > maxItems {schema['maxItems']}")
        if "items" in schema:
            item_schema = schema["items"]
            # Only validate first 5 items to keep it fast
            for i, item in enumerate(data[:5]):
                e, w = validate_against_schema(item, item_schema, f"{path}[{i}]")
                errors.extend(e)
                warnings.extend(w)

    # Object constraints
    if isinstance(data, dict):
        if "minProperties" in schema and len(data) < schema["minProperties"]:
            errors.append(f"{path}: object has {len(data)} properties < minProperties {schema['minProperties']}")

        # Required fields
        for req in schema.get("required", []):
            if req not in data:
                errors.append(f"{path}: missing required field '{req}'")

        # Properties
        for prop_name, prop_schema in schema.get("properties", {}).items():
            if prop_name in data:
                e, w = validate_against_schema(data[prop_name], prop_schema, f"{path}.{prop_name}")
                errors.extend(e)
                warnings.extend(w)

        # patternProperties (for dynamic keys like team abbreviations)
        for pattern, prop_schema in schema.get("patternProperties", {}).items():
            import re
            for key in data:
                if re.match(pattern, key):
                    e, w = validate_against_schema(data[key], prop_schema, f"{path}.{key}")
                    errors.extend(e)
                    warnings.extend(w)

    # $ref (definitions)
    if "$ref" in schema:
        ref_path = schema["$ref"]
        # Only support local #/definitions/ refs
        if ref_path.startswith("#/definitions/"):
            def_name = ref_path.split("/")[-1]
            # We need the root schema for this — handled by caller
            pass

    return errors, warnings


def validate_with_definitions(data, schema):
    """Top-level validator that resolves $ref definitions."""
    definitions = schema.get("definitions", {})
    
    def resolve_refs(s):
        """Recursively resolve $ref in schema."""
        if isinstance(s, dict):
            if "$ref" in s:
                ref = s["$ref"]
                if ref.startswith("#/definitions/"):
                    def_name = ref.split("/")[-1]
                    if def_name in definitions:
                        return resolve_refs(definitions[def_name])
                return s
            return {k: resolve_refs(v) for k, v in s.items()}
        if isinstance(s, list):
            return [resolve_refs(item) for item in s]
        return s
    
    resolved = resolve_refs(schema)
    return validate_against_schema(data, resolved)


def load_and_validate(json_path, schema_name):
    """Load a JSON file and validate against named schema.
    
    Returns: dict with 'passed', 'errors', 'warnings', 'file'
    """
    schema_path = os.path.join(SCHEMA_DIR, schema_name)
    
    if not os.path.exists(json_path):
        return {
            "passed": False,
            "errors": [f"File not found: {json_path}"],
            "warnings": [],
            "file": json_path
        }
    
    if not os.path.exists(schema_path):
        return {
            "passed": True,
            "errors": [],
            "warnings": [f"Schema not found: {schema_path} — skipping validation"],
            "file": json_path
        }
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return {
            "passed": False,
            "errors": [f"Invalid JSON: {e}"],
            "warnings": [],
            "file": json_path
        }
    
    try:
        with open(schema_path, 'r', encoding='utf-8') as f:
            schema = json.load(f)
    except json.JSONDecodeError as e:
        return {
            "passed": True,
            "errors": [],
            "warnings": [f"Invalid schema JSON: {e}"],
            "file": json_path
        }
    
    errors, warnings = validate_with_definitions(data, schema)
    
    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "file": json_path
    }


def print_report(result, label=""):
    """Print validation report."""
    fname = os.path.basename(result["file"])
    status = "✅ PASS" if result["passed"] else "❌ FAIL"
    
    print(f"\n{'='*60}")
    print(f"📋 JSON Schema Validation — {label or fname}")
    print(f"   Status: {status}")
    print(f"   Errors: {len(result['errors'])}, Warnings: {len(result['warnings'])}")
    
    for e in result["errors"][:10]:
        print(f"   ❌ {e}")
    for w in result["warnings"][:5]:
        print(f"   ⚠️ {w}")
    
    if len(result["errors"]) > 10:
        print(f"   ... and {len(result['errors']) - 10} more errors")
    
    print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(
        description="NBA Wong Choi JSON Schema Validator — "
                    "validates extractor and sportsbet JSON files"
    )
    parser.add_argument("--extractor", help="Path to nba_extractor output JSON")
    parser.add_argument("--sportsbet", help="Path to Sportsbet odds JSON")
    parser.add_argument("--strict", action="store_true",
                        help="Treat warnings as errors (exit 1 if any warnings)")
    args = parser.parse_args()
    
    if not args.extractor and not args.sportsbet:
        parser.print_help()
        sys.exit(2)
    
    any_failed = False
    any_warned = False
    
    if args.extractor:
        result = load_and_validate(args.extractor, "extractor_schema.json")
        print_report(result, "Extractor JSON")
        if not result["passed"]:
            any_failed = True
        if result["warnings"]:
            any_warned = True
    
    if args.sportsbet:
        result = load_and_validate(args.sportsbet, "sportsbet_schema.json")
        print_report(result, "Sportsbet JSON")
        if not result["passed"]:
            any_failed = True
        if result["warnings"]:
            any_warned = True
    
    if any_failed:
        print("\n🚨 SCHEMA VALIDATION FAILED — JSON 數據不符合 schema 要求")
        sys.exit(1)
    elif any_warned and args.strict:
        print("\n⚠️ SCHEMA VALIDATION: WARNINGS (strict mode)")
        sys.exit(1)
    else:
        print("\n✅ SCHEMA VALIDATION PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
