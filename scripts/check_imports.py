import importlib
import pkgutil
import sys

import src


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

failures = []

for module in pkgutil.walk_packages(src.__path__, prefix="src."):
    try:
        importlib.import_module(module.name)
        print(f"OK {module.name}")
    except Exception as e:
        print(f"ERR {module.name}")
        print(f"   {type(e).__name__}: {e}")
        failures.append(module.name)

print()
print(f"Failed: {len(failures)}")
