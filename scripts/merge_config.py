#!/usr/bin/env python3
"""
Merge config.yaml with test_overrides.yaml to create test_config.yaml

This script is used to generate a test configuration by merging the base
configuration with test-specific overrides. It preserves YAML comments
when ruamel.yaml is available.

Usage:
    python merge_config.py
    python merge_config.py --base config/config.yaml --overrides config/test_overrides.yaml --output config/test_config.yaml
"""

import sys
import argparse
from pathlib import Path


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge override dict into base dict, returning the merged result."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def merge_with_ruamel(base_path: Path, overrides_path: Path, output_path: Path) -> bool:
    """Merge configs using ruamel.yaml (preserves comments and formatting)."""
    try:
        from ruamel.yaml import YAML

        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.width = 4096  # Prevent line wrapping
        yaml.default_flow_style = False

        with open(base_path) as f:
            config = yaml.load(f)

        with open(overrides_path) as f:
            overrides = yaml.load(f)

        # ruamel.yaml uses special dict types, need to handle carefully
        def merge_ruamel(base, override):
            for key, value in override.items():
                if key in base and hasattr(base[key], 'items') and hasattr(value, 'items'):
                    merge_ruamel(base[key], value)
                else:
                    base[key] = value
            return base

        merged = merge_ruamel(config, overrides)

        with open(output_path, 'w') as f:
            yaml.dump(merged, f)

        print(f"  Generated {output_path} (comments preserved)")
        return True

    except ImportError:
        return False
    except Exception as e:
        print(f"  Warning: ruamel.yaml failed: {e}", file=sys.stderr)
        return False


def merge_with_pyyaml(base_path: Path, overrides_path: Path, output_path: Path) -> bool:
    """Merge configs using PyYAML (loses comments)."""
    try:
        import yaml

        with open(base_path) as f:
            config = yaml.safe_load(f)

        with open(overrides_path) as f:
            overrides = yaml.safe_load(f)

        merged = deep_merge(config, overrides)

        with open(output_path, 'w') as f:
            yaml.dump(merged, f, default_flow_style=False, sort_keys=False)

        print(f"  Generated {output_path} (no comments)")
        return True

    except Exception as e:
        print(f"  Error: PyYAML failed: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description='Merge YAML configuration files')
    parser.add_argument('--base', default='config/config.yaml',
                        help='Base configuration file')
    parser.add_argument('--overrides', default='config/test_overrides.yaml',
                        help='Override configuration file')
    parser.add_argument('--output', default='config/test_config.yaml',
                        help='Output configuration file')
    args = parser.parse_args()

    base_path = Path(args.base)
    overrides_path = Path(args.overrides)
    output_path = Path(args.output)

    # Check inputs exist
    if not base_path.exists():
        print(f"Error: Base config not found: {base_path}", file=sys.stderr)
        sys.exit(1)

    if not overrides_path.exists():
        print(f"Error: Overrides config not found: {overrides_path}", file=sys.stderr)
        sys.exit(1)

    # Try ruamel.yaml first, fall back to PyYAML
    if merge_with_ruamel(base_path, overrides_path, output_path):
        sys.exit(0)

    print("  Warning: ruamel.yaml not available, using standard yaml", file=sys.stderr)

    if merge_with_pyyaml(base_path, overrides_path, output_path):
        sys.exit(0)

    print("Error: Failed to merge configuration files", file=sys.stderr)
    sys.exit(1)


if __name__ == '__main__':
    main()
