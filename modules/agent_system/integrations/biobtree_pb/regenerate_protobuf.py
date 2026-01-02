#!/usr/bin/env python3
"""
Regenerate Python protobuf files from BioBTree proto definitions.

This script regenerates the gRPC/protobuf Python files from the latest
BioBTree proto definitions and fixes import statements for proper package usage.

Usage:
    python regenerate_protobuf.py

    Or from project root:
    python -m modules.agent_system.integrations.biobtree_pb.regenerate_protobuf
"""

import subprocess
import sys
from pathlib import Path


def get_paths():
    """Get source and destination paths."""
    # This script is in: bioyoda/modules/agent_system/integrations/biobtree_pb/
    script_dir = Path(__file__).parent.resolve()

    # bioyoda root (4 levels up)
    bioyoda_root = script_dir.parent.parent.parent.parent

    # Proto source directory (biobtreev2 is a link inside bioyoda)
    proto_src = bioyoda_root / "biobtreev2" / "src" / "pbuf"

    # Output directory (same as script location)
    output_dir = script_dir

    return proto_src, output_dir, bioyoda_root


def regenerate_protobuf():
    """Regenerate protobuf Python files."""
    proto_src, output_dir, bioyoda_root = get_paths()

    # Verify proto source exists
    if not proto_src.exists():
        print(f"ERROR: Proto source directory not found: {proto_src}")
        print(f"Expected biobtreev2/src/pbuf relative to: {bioyoda_root}")
        sys.exit(1)

    # Check for required proto files
    attr_proto = proto_src / "attr.proto"
    app_proto = proto_src / "app.proto"

    if not attr_proto.exists() or not app_proto.exists():
        print(f"ERROR: Proto files not found in {proto_src}")
        print(f"  attr.proto exists: {attr_proto.exists()}")
        print(f"  app.proto exists: {app_proto.exists()}")
        sys.exit(1)

    print(f"Proto source: {proto_src}")
    print(f"Output dir:   {output_dir}")
    print()

    # Run protoc
    print("Generating Python protobuf files...")
    cmd = [
        sys.executable, "-m", "grpc_tools.protoc",
        f"-I{proto_src}",
        f"--python_out={output_dir}",
        f"--grpc_python_out={output_dir}",
        str(attr_proto),
        str(app_proto),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"ERROR: protoc failed:")
        print(result.stderr)
        sys.exit(1)

    print("  Generated: attr_pb2.py, attr_pb2_grpc.py")
    print("  Generated: app_pb2.py, app_pb2_grpc.py")
    print()

    # Fix import statements for package usage
    print("Fixing import statements for package usage...")

    files_to_fix = [
        (output_dir / "app_pb2.py", "import attr_pb2", "from . import attr_pb2"),
        (output_dir / "app_pb2_grpc.py", "import app_pb2", "from . import app_pb2"),
    ]

    for filepath, old_import, new_import in files_to_fix:
        if filepath.exists():
            content = filepath.read_text()
            if old_import in content and new_import not in content:
                content = content.replace(old_import, new_import)
                filepath.write_text(content)
                print(f"  Fixed: {filepath.name}")
            elif new_import in content:
                print(f"  Already fixed: {filepath.name}")
            else:
                print(f"  No change needed: {filepath.name}")

    print()

    # Clear pycache to ensure fresh imports
    pycache = output_dir / "__pycache__"
    if pycache.exists():
        import shutil
        shutil.rmtree(pycache)
        print("Cleared __pycache__")

    # Verify the regenerated files
    print()
    print("Verifying generated files...")
    try:
        # Need to reload if already imported
        import importlib
        if 'attr_pb2' in sys.modules:
            del sys.modules['attr_pb2']
        if 'app_pb2' in sys.modules:
            del sys.modules['app_pb2']

        # Try importing from the output directory
        sys.path.insert(0, str(output_dir))
        import attr_pb2
        import app_pb2
        sys.path.pop(0)

        # Check for key message types
        has_bindingdb = hasattr(attr_pb2, 'BindingdbAttr')
        has_antibody = hasattr(attr_pb2, 'AntibodyAttr')
        has_pubchem = hasattr(attr_pb2, 'PubchemAttr')

        print(f"  BindingdbAttr: {'YES' if has_bindingdb else 'NO'}")
        print(f"  AntibodyAttr:  {'YES' if has_antibody else 'NO'}")
        print(f"  PubchemAttr:   {'YES' if has_pubchem else 'NO'}")

        if has_bindingdb:
            bd = attr_pb2.BindingdbAttr()
            fields = [f.name for f in bd.DESCRIPTOR.fields]
            binding_fields = [f for f in fields if f in ['ki', 'kd', 'ic50', 'ec50']]
            print(f"  BindingDB binding fields: {binding_fields}")

        print()
        print("SUCCESS: Protobuf files regenerated successfully!")

    except ImportError as e:
        print(f"  WARNING: Could not verify imports: {e}")
        print("  Files were generated but verification failed.")
        print("  Try importing manually to check for issues.")


if __name__ == "__main__":
    regenerate_protobuf()
