import tempfile
import unittest
from pathlib import Path

from orx_sdk.format import (
    FLAG_GUI,
    HEADER,
    HEADER_SIZE,
    load_orx,
    pack_orx,
    permission_names,
)


def base_blob():
    return pack_orx(
        code=b'\0' * 16,
        rodata=b'hello',
        metadata={'name': 'validation'},
        entry=0,
        permissions=0,
        flags=FLAG_GUI,
    )


def rewrite_header(blob, mutate):
    data=bytearray(blob)
    values=list(HEADER.unpack_from(data))
    mutate(values)
    data[:HEADER_SIZE]=HEADER.pack(*values)
    return bytes(data)


class FormatValidationTests(unittest.TestCase):
    def assert_rejected(self, blob, text):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'bad.orx'
            path.write_bytes(blob)
            with self.assertRaisesRegex(ValueError,text):
                load_orx(path)

    def test_rejects_overlapping_sections(self):
        blob=rewrite_header(base_blob(),lambda v:v.__setitem__(12,v[8]))
        self.assert_rejected(blob,'overlaps')

    def test_rejects_unknown_permission_bits(self):
        blob=rewrite_header(base_blob(),lambda v:v.__setitem__(6,1<<31))
        self.assert_rejected(blob,'permission bits')
        with self.assertRaisesRegex(ValueError,'permission bits'):
            permission_names(1<<31)

    def test_rejects_unknown_flag_bits(self):
        blob=rewrite_header(base_blob(),lambda v:v.__setitem__(5,1<<31))
        self.assert_rejected(blob,'flag bits')

    def test_rejects_misaligned_section(self):
        blob=rewrite_header(base_blob(),lambda v:v.__setitem__(12,v[12]+1))
        self.assert_rejected(blob,'not 16-byte aligned')

    def test_rejects_invalid_code_size_before_execution(self):
        blob=rewrite_header(base_blob(),lambda v:v.__setitem__(9,10))
        self.assert_rejected(blob,'multiple of 8')

    def test_packer_rejects_unknown_masks(self):
        with self.assertRaisesRegex(ValueError,'permission bits'):
            pack_orx(code=b'\0'*8,rodata=b'',metadata={},entry=0,permissions=1<<31,flags=0)
        with self.assertRaisesRegex(ValueError,'flag bits'):
            pack_orx(code=b'\0'*8,rodata=b'',metadata={},entry=0,permissions=0,flags=1<<31)


if __name__=='__main__':
    unittest.main()
