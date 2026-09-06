import tempfile
import unittest
from pathlib import Path
from orx_sdk.assembler import assemble
from orx_sdk.format import pack_orx, load_orx, permission_mask, FLAG_GUI
from orx_sdk.vm import OrxVM

SRC = r'''
.entry main
.section code
main:
    syscall log, @hello
    halt
.section rodata
hello:
    .string "roundtrip-ok"
'''

class OrxTests(unittest.TestCase):
    def test_roundtrip_and_vm(self):
        asm = assemble(SRC)
        blob = pack_orx(code=asm.code, rodata=asm.rodata, metadata={"name":"test","id":"test"}, entry=asm.entry, permissions=permission_mask(["graphics"]), flags=FLAG_GUI)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/"test.orx"; p.write_bytes(blob)
            h, _, meta = load_orx(p)
            self.assertEqual(h.code_size, 16)
            self.assertEqual(meta["name"], "test")
            vm = OrxVM(p); result = vm.run()
            self.assertIn("roundtrip-ok", result.log)

    def test_crc_rejects_corruption(self):
        asm = assemble(SRC)
        blob = bytearray(pack_orx(code=asm.code, rodata=asm.rodata, metadata={"name":"test"}, entry=asm.entry, permissions=0, flags=FLAG_GUI))
        blob[-1] ^= 1
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/"bad.orx"; p.write_bytes(blob)
            with self.assertRaises(ValueError): load_orx(p)

if __name__ == "__main__": unittest.main()
