from __future__ import annotations

import ast
import re
import struct
from dataclasses import dataclass

INS = struct.Struct("<BBBBi")
REG_RE = re.compile(r"r([0-7])$", re.I)

OP = {
    "nop": 0x00,
    "halt": 0x01,
    "movi": 0x02,
    "mov": 0x03,
    "add": 0x04,
    "addi": 0x05,
    "sub": 0x06,
    "cmp": 0x07,
    "jmp": 0x08,
    "jz": 0x09,
    "jnz": 0x0A,
    "syscall": 0x10,
}

SYSCALL = {
    "log": 1,
    "exit": 2,
    "window": 16,
    "clear": 17,
    "rect": 18,
    "text": 19,
    "present": 20,
    "event": 21,
    "sleep": 22,
}

@dataclass
class Assembly:
    code: bytes
    rodata: bytes
    entry: int
    symbols: dict[str, int]


def _reg(token: str) -> int:
    m = REG_RE.fullmatch(token.strip())
    if not m:
        raise ValueError(f"expected register r0..r7, got {token!r}")
    return int(m.group(1))


def _int(token: str) -> int:
    return int(token.strip(), 0)


def _strip_comment(line: str) -> str:
    out = []
    quote = None
    escaped = False
    for ch in line:
        if escaped:
            out.append(ch); escaped = False; continue
        if ch == "\\":
            out.append(ch); escaped = True; continue
        if quote:
            out.append(ch)
            if ch == quote: quote = None
            continue
        if ch in "\"'": quote = ch; out.append(ch); continue
        if ch in ";#": break
        out.append(ch)
    return "".join(out).strip()


def assemble(source: str) -> Assembly:
    lines = [_strip_comment(x) for x in source.splitlines()]
    lines = [x for x in lines if x]
    section = "code"
    code_pc = 0
    ro_pc = 0
    code_labels: dict[str, int] = {}
    ro_labels: dict[str, int] = {}
    entry_label = "main"

    for line in lines:
        low = line.lower()
        if low.startswith(".section "):
            section = low.split(None, 1)[1]
            if section not in ("code", "rodata"):
                raise ValueError(f"unknown section {section}")
            continue
        if low.startswith(".entry "):
            entry_label = line.split(None, 1)[1].strip()
            continue
        if line.endswith(":"):
            name = line[:-1].strip()
            target = code_labels if section == "code" else ro_labels
            if name in target:
                raise ValueError(f"duplicate label {name}")
            target[name] = code_pc if section == "code" else ro_pc
            continue
        if section == "code":
            code_pc += 8
        else:
            if low.startswith(".string "):
                value = ast.literal_eval(line.split(None, 1)[1])
                ro_pc += len(value.encode("utf-8")) + 1
            elif low.startswith(".bytes "):
                vals = [int(x.strip(), 0) & 0xFF for x in line.split(None, 1)[1].split(",")]
                ro_pc += len(vals)
            elif low.startswith(".align "):
                a = _int(line.split(None, 1)[1])
                ro_pc = (ro_pc + a - 1) & ~(a - 1)
            else:
                raise ValueError(f"invalid rodata directive: {line}")

    if entry_label not in code_labels:
        raise ValueError(f"entry label {entry_label!r} not found")

    code = bytearray()
    rodata = bytearray()
    section = "code"
    pc = 0
    for line in lines:
        low = line.lower()
        if low.startswith(".section "):
            section = low.split(None, 1)[1]; continue
        if low.startswith(".entry ") or line.endswith(":"):
            continue
        if section == "rodata":
            if low.startswith(".string "):
                value = ast.literal_eval(line.split(None, 1)[1])
                rodata += value.encode("utf-8") + b"\0"
            elif low.startswith(".bytes "):
                rodata += bytes(int(x.strip(), 0) & 0xFF for x in line.split(None, 1)[1].split(","))
            elif low.startswith(".align "):
                a = _int(line.split(None, 1)[1])
                while len(rodata) % a: rodata.append(0)
            continue

        parts = line.replace(",", " ").split()
        name = parts[0].lower()
        args = parts[1:]
        if name not in OP:
            raise ValueError(f"unknown opcode {name}")
        op = OP[name]; a = b = c = 0; imm = 0
        if name in ("nop", "halt"):
            if args: raise ValueError(f"{name} takes no operands")
        elif name == "movi":
            if len(args) != 2: raise ValueError("movi reg, imm")
            a, imm = _reg(args[0]), _int(args[1])
        elif name in ("mov", "add", "sub", "cmp"):
            if len(args) != 2: raise ValueError(f"{name} reg, reg")
            a, b = _reg(args[0]), _reg(args[1])
        elif name == "addi":
            if len(args) != 2: raise ValueError("addi reg, imm")
            a, imm = _reg(args[0]), _int(args[1])
        elif name in ("jmp", "jz", "jnz"):
            if len(args) != 1 or args[0] not in code_labels:
                raise ValueError(f"{name} requires a code label")
            target = code_labels[args[0]]
            imm = target - (pc + 8)
        elif name == "syscall":
            if not args or args[0].lower() not in SYSCALL:
                raise ValueError("unknown syscall")
            a = SYSCALL[args[0].lower()]
            if len(args) > 1:
                ref = args[1]
                if ref.startswith("@"):
                    label = ref[1:]
                    if label not in ro_labels: raise ValueError(f"unknown rodata label {label}")
                    imm = ro_labels[label]
                else:
                    imm = _int(ref)
            if len(args) > 2: raise ValueError("syscall name [, imm-or-@rodata]")
        code += INS.pack(op, a, b, c, imm)
        pc += 8

    symbols = {**{f"code:{k}": v for k, v in code_labels.items()}, **{f"ro:{k}": v for k, v in ro_labels.items()}}
    return Assembly(bytes(code), bytes(rodata), code_labels[entry_label], symbols)
