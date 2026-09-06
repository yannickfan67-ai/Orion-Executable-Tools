from __future__ import annotations

import time
from dataclasses import dataclass, field
from .format import load_orx
from .assembler import INS

@dataclass
class VMResult:
    exit_code: int = 0
    steps: int = 0
    log: list[str] = field(default_factory=list)

class OrxVM:
    def __init__(self, path, *, trace: bool = False):
        self.header, self.data, self.meta = load_orx(path)
        h = self.header
        self.code = self.data[h.code_offset:h.code_offset+h.code_size]
        self.rodata = self.data[h.rodata_offset:h.rodata_offset+h.rodata_size]
        self.reg = [0] * 8
        self.pc = h.entry
        self.zf = False
        self.trace = trace
        self.result = VMResult()
        self.running = True

    def cstr(self, off: int) -> str:
        if off < 0 or off >= len(self.rodata):
            raise RuntimeError(f"rodata offset out of bounds: {off}")
        end = self.rodata.find(b"\0", off)
        if end < 0: end = len(self.rodata)
        return self.rodata[off:end].decode("utf-8", errors="replace")

    def syscall(self, sid: int, imm: int) -> None:
        if sid == 1:
            msg = self.cstr(imm); self.result.log.append(msg); print(msg)
        elif sid == 2:
            self.result.exit_code = self.reg[0] & 0xFFFFFFFF; self.running = False
        elif sid == 16:
            title = self.cstr(imm) if imm >= 0 else "ORX App"
            self.result.log.append(f"[window] {title} {self.reg[0]}x{self.reg[1]}")
        elif sid == 17:
            self.result.log.append(f"[clear] #{self.reg[0] & 0xFFFFFF:06x}")
        elif sid == 18:
            self.result.log.append(f"[rect] x={self.reg[0]} y={self.reg[1]} w={self.reg[2]} h={self.reg[3]} color=#{self.reg[4] & 0xFFFFFF:06x}")
        elif sid == 19:
            self.result.log.append(f"[text] ({self.reg[0]},{self.reg[1]}) {self.cstr(imm)}")
        elif sid == 20:
            self.result.log.append("[present]")
        elif sid == 21:
            self.reg[0] = 0
        elif sid == 22:
            time.sleep(min(self.reg[0], 1000) / 1000.0)
        else:
            raise RuntimeError(f"unsupported syscall {sid}")

    def run(self, *, max_steps: int = 1_000_000) -> VMResult:
        while self.running:
            if self.result.steps >= max_steps:
                raise RuntimeError("VM step limit exceeded")
            if self.pc < 0 or self.pc + 8 > len(self.code) or self.pc % 8:
                raise RuntimeError(f"PC out of bounds: {self.pc}")
            op, a, b, c, imm = INS.unpack_from(self.code, self.pc)
            here = self.pc
            self.pc += 8
            self.result.steps += 1
            if self.trace: print(f"pc={here:04x} op={op:02x} a={a} b={b} imm={imm} regs={self.reg}")
            if op == 0x00: pass
            elif op == 0x01: self.running = False
            elif op == 0x02: self.reg[a] = imm & 0xFFFFFFFFFFFFFFFF
            elif op == 0x03: self.reg[a] = self.reg[b]
            elif op == 0x04: self.reg[a] = (self.reg[a] + self.reg[b]) & 0xFFFFFFFFFFFFFFFF
            elif op == 0x05: self.reg[a] = (self.reg[a] + imm) & 0xFFFFFFFFFFFFFFFF
            elif op == 0x06: self.reg[a] = (self.reg[a] - self.reg[b]) & 0xFFFFFFFFFFFFFFFF
            elif op == 0x07: self.zf = self.reg[a] == self.reg[b]
            elif op == 0x08: self.pc += imm
            elif op == 0x09:
                if self.zf: self.pc += imm
            elif op == 0x0A:
                if not self.zf: self.pc += imm
            elif op == 0x10: self.syscall(a, imm)
            else: raise RuntimeError(f"unknown opcode 0x{op:02x} at {here:#x}")
        return self.result
