import ast, os

errors = []
for root, dirs, files in os.walk("app"):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for f in files:
        if f.endswith(".py"):
            path = os.path.join(root, f)
            try:
                with open(path, encoding="utf-8") as fh:
                    ast.parse(fh.read(), filename=path)
            except SyntaxError as e:
                errors.append(f"{path}: {e}")
for e in errors:
    print("ERROR:", e)
if not errors:
    print("All Python files OK")
