# cython: cdivision=True, wraparound=False, boundscheck=False, language_level=3, embedsignature=True
"""Various functions for determining which pixels of a mask matrix are selected and which are not.

Note that the coordinate of the center of mask element row=irow, col=icol is (x=icol, y=irow), the top left of the
pixel is (x=icol-0.5, y=irow-0.5), the bottom right is (x=icol+0.5, y=irow+0.5), the (x=0,y=0) point being at top left.
"""

from numpy cimport uint8_t
from libc.math cimport fmin, fmax, INFINITY, ceil, floor

cpdef enum MaskingMode:
    mm_mask = 0
    mm_unmask = 1
    mm_flip = 2



def maskCircle(uint8_t[:,:] mask, double centerrow, double centercol, double radius, MaskingMode maskmode):
    cdef:
        Py_ssize_t irow, icol
        double radius2 = radius*radius, r2

    for irow in range(<int>fmax(0, centerrow - radius-1), <int>fmin(mask.shape[0], centerrow + radius+1)):
        for icol in range(<int>fmax(0, centercol - radius - 1), <int>fmin(mask.shape[1], centercol + radius + 1)):
            r2 = (irow-centerrow) * (irow - centerrow) + (icol - centercol) * (icol - centercol)
            if r2 <= radius2:
                if maskmode == mm_mask:
                    mask[irow, icol] = 0
                elif maskmode == mm_unmask:
                    mask[irow, icol] = 1
                else:
                    mask[irow, icol] = mask[irow, icol] == 0
    return mask

def maskRectangle(uint8_t[:,:] mask, double rowmin, colmin, double rowmax, double colmax, MaskingMode maskmode):
    cdef:
        Py_ssize_t irow, icol

    for irow in range(<int>ceil(fmax(0, rowmin+0.5)), <int>ceil(fmin(mask.shape[0], rowmax-0.5))):
        for icol in range(<int>ceil(fmax(0, colmin+0.5)), <int>ceil(fmin(mask.shape[1], colmax-0.5))):
            if maskmode == mm_mask:
                mask[irow, icol] = 0
            elif maskmode == mm_unmask:
                mask[irow, icol] = 1
            else:
                mask[irow, icol] = mask[irow, icol] == 0
    return mask

def maskPolygon(uint8_t[:,:] mask, double [:, :] vertices, MaskingMode maskmode):
    # use the edge crossing algorithm
    cdef:
        Py_ssize_t irow, icol, iedge
        Py_ssize_t crossingnumber = 0
        double t
        double rowmin=INFINITY, colmin=INFINITY, rowmax=-INFINITY, colmax=-INFINITY

    for iedge in range(vertices.shape[0]):
        if vertices[iedge, 0] < rowmin:
            rowmin = vertices[iedge, 0]
        if vertices[iedge, 0] > rowmax:
            rowmax = vertices[iedge, 0]
        if vertices[iedge, 1] < colmin:
            colmin = vertices[iedge, 1]
        if vertices[iedge, 1] > colmax:
            colmax = vertices[iedge, 1]

    # vertices: 2 columns, x (column) and y (row) coordinates of the vertices
    for irow in range(<int>fmax(0, rowmin), <int>fmin(rowmax, mask.shape[0])):
        for icol in range(<int>fmax(0, colmin), <int>fmin(colmax, mask.shape[1])):
            crossingnumber = 0
            for iedge in range(0, vertices.shape[0]-1):
                # iedge is the starting point of the vertex, iedge +1 is its ending point.
                if vertices[iedge, 1] == vertices[iedge+1, 1]:
                    # horizontal edge, disregard this.
                    continue
                t = (irow - vertices[iedge, 1]) / (vertices[iedge+1, 1] - vertices[iedge, 1])
                # if tau in [0, 1[ parametrizes the line section from vertices[iedge, :] to vertices[iedge + 1, :],
                # then tau=t marks the intersection point with the horizontal ray from [x=icol, y=irow].
                if t<0 or t>=1:
                    # intersection outside the line section
                    continue
                if vertices[iedge, 0] + t * (vertices[iedge + 1, 0] - vertices[iedge, 0]) >= icol:
                    # the intersection point lies to the right from the current point: intersection!
                    crossingnumber += 1
            if crossingnumber % 2:
                # odd number of crossing: internal point
                if maskmode == mm_unmask:
                    mask[irow, icol] = 1
                elif maskmode == mm_mask:
                    mask[irow, icol] = 0
                else:
                    # flip
                    mask[irow, icol] = mask[irow, icol] == 0
    return mask