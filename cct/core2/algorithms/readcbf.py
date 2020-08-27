import numpy as np

from .cbfdecompress import cbfdecompress


def readcbf(filename: str):
    with open(filename, 'rb') as f:
        dim1 = None
        dim2 = None
        while f.readline().strip() != b'--CIF-BINARY-FORMAT-SECTION--':
            pass
        while line := f.readline().strip():
            if line.startswith(b'conversions=') and (line != b"conversions=\"x-CBF_BYTE_OFFSET\""):
                raise RuntimeError('Unsupported CBF compression')
            if line.startswith(b'Content-Transfer-Encoding:') and (line != b"Content-Transfer-Encoding: BINARY"):
                raise RuntimeError('Unsupported content transfer encoding')
            if line.startswith(b'X-Binary-Element-Type:') and (
                    line != b"X-Binary-Element-Type: \"signed 32-bit integer\""):
                raise RuntimeError('Unsupported binary element type')
            if line.startswith(b'X-Binary-Element-Byte-Order:') and (
                    line != b"X-Binary-Element-Byte-Order: LITTLE_ENDIAN"):
                raise RuntimeError('Unsupported binary element byte order')
            if line.startswith(b'X-Binary-Size-Fastest-Dimension:'):
                dim1 = int(line.split()[-1])
            elif line.startswith(b'X-Binary-Size-Second-Dimension:'):
                dim2 = int(line.split()[-1])
    if dim1 is None or dim2 is None:
        raise RuntimeError('Image dimensions not found in file.')
    with open(filename, 'rb') as f:
        data = f.read()
        data = np.frombuffer(data[data.find(b'\x0c\x1a\x04\xd5') + 4:], np.uint8)
        output = np.empty(dim1 * dim2, order='C', dtype=np.double)
        cbfdecompress(data, output)
    return output.reshape(dim2, dim1)
