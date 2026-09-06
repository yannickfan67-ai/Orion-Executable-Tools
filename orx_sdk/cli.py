from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
import tomllib

from .assembler import assemble
from .format import FLAG_CONSOLE, FLAG_GUI, load_orx, pack_orx, permission_mask, permission_names
from .vm import OrxVM


def cmd_new(args):
    root = Path(args.directory or args.name.lower().replace(" ", "-"))
    root.mkdir(parents=True, exist_ok=False)
    app_id = "dev.orion." + "".join(c.lower() if c.isalnum() else "." for c in args.name).strip(".").replace("..", ".")
    (root / "app.toml").write_text(
        f'name = "{args.name}"\nid = "{app_id}"\nversion = "0.1.0"\nabi = 1\nsource = "main.oasm"\ntype = "gui"\npermissions = ["graphics", "input"]\n',
        encoding="utf-8"
    )
    (root / "main.oasm").write_text(
        '.entry main\n.section code\nmain:\n    movi r0, 640\n    movi r1, 400\n    syscall window, @title\n    movi r0, 0x152238\n    syscall clear\n    movi r0, 32\n    movi r1, 42\n    syscall text, @hello\n    syscall present\n    halt\n\n.section rodata\ntitle:\n    .string "' + args.name + '"\nhello:\n    .string "Hello from an ORX app."\n',
        encoding="utf-8"
    )
    print(f"Created ORX project: {root}")


def build_project(root: Path, out: Path | None = None) -> Path:
    manifest_path = root / "app.toml"
    cfg = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
    source = root / cfg.get("source", "main.oasm")
    asm = assemble(source.read_text(encoding="utf-8"))
    app_type = cfg.get("type", "gui")
    flags = FLAG_GUI if app_type == "gui" else FLAG_CONSOLE
    perms = permission_mask(list(cfg.get("permissions", [])))
    icon = b""
    if cfg.get("icon"):
        icon = (root / cfg["icon"]).read_bytes()
    meta = {
        "name": cfg["name"], "id": cfg["id"], "version": cfg.get("version", "0.1.0"),
        "abi": int(cfg.get("abi", 1)), "type": app_type,
        "permissions": list(cfg.get("permissions", [])),
        "source": source.name,
    }
    blob = pack_orx(
        code=asm.code, rodata=asm.rodata, metadata=meta, entry=asm.entry,
        permissions=perms, flags=flags, icon=icon,
        stack_size=int(cfg.get("stack_size", 64 * 1024)),
        heap_size=int(cfg.get("heap_size", 256 * 1024)),
    )
    if out is None:
        build_dir = root / "build"; build_dir.mkdir(exist_ok=True)
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in cfg["name"])
        out = build_dir / f"{safe}.orx"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    return out


def cmd_build(args):
    out = build_project(Path(args.project), Path(args.output) if args.output else None)
    h, _, meta = load_orx(out)
    print(f"Built {out} ({h.file_size} bytes, code={h.code_size}, rodata={h.rodata_size})")
    print(f"App: {meta.get('name')}  id={meta.get('id')}")


def cmd_inspect(args):
    h, _, meta = load_orx(args.file)
    print(json.dumps({
        "format": f"ORX v{h.format_version}", "abi": h.abi_version, "machine": "orion-vm64",
        "file_size": h.file_size, "entry": h.entry,
        "code": {"offset": h.code_offset, "size": h.code_size},
        "rodata": {"offset": h.rodata_offset, "size": h.rodata_size},
        "metadata": meta, "permissions": permission_names(h.permissions),
        "stack_size": h.stack_size, "heap_size": h.heap_size,
        "crc32": f"{h.payload_crc32:08x}",
    }, indent=2, ensure_ascii=False))


def cmd_run(args):
    vm = OrxVM(args.file, trace=args.trace)
    result = vm.run(max_steps=args.max_steps)
    print(f"ORX exited with code {result.exit_code} after {result.steps} steps")


def cmd_check(args):
    h, _, meta = load_orx(args.file)
    print(f"OK: {args.file}: ORX v{h.format_version}, ABI {h.abi_version}, {meta.get('name', 'unnamed')}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="orx", description="Orion Executable Tools")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new", help="create a new ORX application project")
    s.add_argument("name"); s.add_argument("directory", nargs="?"); s.set_defaults(func=cmd_new)
    s = sub.add_parser("build", help="assemble and package an ORX application")
    s.add_argument("project", nargs="?", default="."); s.add_argument("-o", "--output"); s.set_defaults(func=cmd_build)
    s = sub.add_parser("inspect", help="show ORX header and metadata")
    s.add_argument("file"); s.set_defaults(func=cmd_inspect)
    s = sub.add_parser("check", help="validate an ORX file")
    s.add_argument("file"); s.set_defaults(func=cmd_check)
    s = sub.add_parser("run", help="run an ORX file in the host reference VM")
    s.add_argument("file"); s.add_argument("--trace", action="store_true"); s.add_argument("--max-steps", type=int, default=1_000_000); s.set_defaults(func=cmd_run)
    args = p.parse_args(argv)
    try:
        return args.func(args) or 0
    except Exception as exc:
        print(f"orx: error: {exc}", file=sys.stderr)
        return 1
