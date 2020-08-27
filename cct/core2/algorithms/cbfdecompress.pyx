# cython: cdivision=True, wraparound=False, boundscheck=False, language_level=3, embedsignature=True
cimport numpy as np
ctypedef np.uint8_t uint8_t
ctypedef np.int32_t int32_t
ctypedef np.int8_t int8_t
ctypedef np.int16_t int16_t
ctypedef np.double_t double_t

def cbfdecompress(const uint8_t [:] inarray, double_t[:] outarray):
    """Citation from http://www.bernstein-plus-sons.com/software/CBF/doc/CBFLIB.html#3.3

        The "byte_offset" compression algorithm is the following:

            1. Start with a base pixel value of 0.
            2. Compute the difference delta between the next pixel value and the base pixel value.
            3. If -127 ≤ delta ≤ 127, output delta as one byte, make the current pixel value the base pixel value and
               return to step 2.
            4. Otherwise output -128 (80 hex).
            5. We still have to output delta. If -32767 ≤ delta ≤ 32767, output delta as a little_endian 16-bit
               quantity, make the current pixel value the base pixel value and return to step 2.
            6. Otherwise output -32768 (8000 hex, little_endian, i.e. 00 then 80)
            7. We still have to output delta. If -2147483647 ≤ delta ≤ 2147483647, output delta as a little_endian 32
               bit quantity, make the current pixel value the base pixel value and return to step 2.
            8. Otherwise output -2147483648 (80000000 hex, little_endian, i.e. 00, then 00, then 00, then 80) and then
               output the pixel value as a little-endian 64 bit quantity, make the current pixel value the base pixel
               value and return to step 2.

        The "byte_offset" decompression algorithm is the following:

            1. Start with a base pixel value of 0.
            2. Read the next byte as delta
            3. If -127 ≤ delta ≤ 127, add delta to the base pixel value, make that the new base pixel value, place it on
               the output array and return to step 2.
            4. If delta is 80 hex, read the next two bytes as a little_endian 16-bit number and make that delta.
            5. If -32767 ≤ delta ≤ 32767, add delta to the base pixel value, make that the new base pixel value, place
               it on the output array and return to step 2.
            6. If delta is 8000 hex, read the next 4 bytes as a little_endian 32-bit number and make that delta
            7. If -2147483647 ≤ delta ≤ 2147483647, add delta to the base pixel value, make that the new base pixel
               value, place it on the output array and return to step 2.
            8. If delta is 80000000 hex, read the next 8 bytes as a little_endian 64-bit number and make that delta,
               add delta to the base pixel value, make that the new base pixel value, place it on the output array and
               return to step 2.

    ( end of cite).

    I.e. the special cases:

     (4)        (6)              (8)
    <0x80>|<0x00><0x80>|<0x00><0x00><0x00><0x80>
    """
    cdef:
        Py_ssize_t nbytes = inarray.size, iin = 0, iout = 0, nout = outarray.size
        double lastvalue = 0

    while iin < nbytes:
        if inarray[iin] != 0x80:
            # difference stored on one byte
            outarray[iout] = lastvalue + <int8_t>(inarray[iin])
            iin += 1
        elif not ((inarray[iin+1] == 0x00) and (inarray[iin+2] == 0x80)):
            # difference stored on two bytes
            outarray[iout] = lastvalue + <int16_t>(inarray[iin+1] + 0x100*inarray[iin+2])
            iin += 3
        elif not ((inarray[iin+3] == 0x00)
                  and (inarray[iin+4] == 0x00) and (inarray[iin+5] == 0x00) and (inarray[iin+6] == 0x80)):
            # difference stored on four bytes
            outarray[iout] = lastvalue + <int32_t>(
                inarray[iin+3] + 0x100*inarray[iin+4] + 0x10000*inarray[iin+5] + 0x1000000*inarray[iin+6])
            iin += 7
        else:
            raise ValueError('Cannot load 64-bit data')
        lastvalue=outarray[iout]
        iout +=1
        if iout >= nout:
            break
    if iout != nout:
        raise ValueError('Binary data does not have enough points.')
    return outarray
