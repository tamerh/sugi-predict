#!/usr/bin/env python3
"""
Modify config file for snapshot isolation.

Updates base_dir and project_root in a YAML config file to point
to the snapshot directory structure.

Usage:
    python modify_snapshot_config.py <config_file> <snapshot_root> <code_dir>

Example:
    python modify_snapshot_config.py config/config.yaml /path/to/snapshot /path/to/snapshot/code
"""

import sys
from pathlib import Path


def modify_with_ruamel(config_path: Path, snapshot_root: str, code_dir: str) -> bool:
    """Modify config using ruamel.yaml (preserves comments and formatting)."""
    try:
        from ruamel.yaml import YAML

        yaml = YAML()
        yaml.preserve_quotes = True
        yaml.width = 4096  # Prevent line wrapping

        with open(config_path, 'r') as f:
            config = yaml.load(f)

        # Update base_dir and project_root
        config['base_dir'] = snapshot_root
        config['project_root'] = code_dir

        with open(config_path, 'w') as f:
            yaml.dump(config, f)

        print(f"    Updated {config_path.name} (comments preserved)")
        return True

    except ImportError:
        return False
    except Exception as e:
        print(f"    Warning: ruamel.yaml failed for {config_path.name}: {e}", file=sys.stderr)
        return False


def modify_with_pyyaml(config_path: Path, snapshot_root: str, code_dir: str) -> bool:
    """Modify config using PyYAML (loses comments)."""
    try:
        import yaml

        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Update base_dir and project_root
        config['base_dir'] = snapshot_root
        config['project_root'] = code_dir

        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        print(f"    Updated {config_path.name} (no comments)")
        return True

    except Exception as e:
        print(f"    Error: PyYAML failed for {config_path.name}: {e}", file=sys.stderr)
        return False


def main():
    if len(sys.argv) != 4:
        print("Usage: modify_snapshot_config.py <config_file> <snapshot_root> <code_dir>",
              file=sys.stderr)
        sys.exit(1)

    config_path = Path(sys.argv[1])
    snapshot_root = sys.argv[2]
    code_dir = sys.argv[3]

    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    # Try ruamel.yaml first, fall back to PyYAML
    if modify_with_ruamel(config_path, snapshot_root, code_dir):
        sys.exit(0)

    if modify_with_pyyaml(config_path, snapshot_root, code_dir):
        sys.exit(0)

    print(f"Error: Failed to modify {config_path}", file=sys.stderr)
    sys.exit(1)


if __name__ == '__main__':
    main()
