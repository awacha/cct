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
    """Mask/unmask/flip points using the edge crossing algorithm, given the vertices of a polygon

    Starting from each point of the mask matrix, a horizontal line is drawn to the right (along the rows, with
    increasing row numbers). The intersections with this half line and the edges of the polygon is counted: if it is
    even, the point is outside, if odd, inside.

    :param mask: mask matrix
    :type mask: 2D matrix, uint8 dtype
    :param vertices: vertex coordinates. N rows, 2 columns, columns are X (column coordinate) and Y (row coordinate).
    :type vertices: N-by-2 matrix of double dtype
    :param maskmode: masking mode
    :type maskmode: MaskingMode
    :return: the modified matrix (also modified in place!)
    :rtype: 2D matrix, uint8 dtype, the same as `mask`
    """
    cdef:
        Py_ssize_t irow, icol, iedge
        Py_ssize_t crossingnumber = 0
        double t
        double rowmin=INFINITY, colmin=INFINITY, rowmax=-INFINITY, colmax=-INFINITY
        double x0, y0, x1, y1

    # if the polygon is strictly inside the matrix (no vertices outside), we can check a smaller part of the mask, which
    # speeds up things a bit.
    for iedge in range(vertices.shape[0]):
        if vertices[iedge, 1] < rowmin:
            rowmin = vertices[iedge, 1]
        if vertices[iedge, 1] > rowmax:
            rowmax = vertices[iedge, 1]
        if vertices[iedge, 0] < colmin:
            colmin = vertices[iedge, 0]
        if vertices[iedge, 0] > colmax:
            colmax = vertices[iedge, 0]
    if rowmin < 0:
        rowmin = 0
    if rowmax > mask.shape[0]:
        rowmax = mask.shape[0]
    if colmin < 0:
        colmin = 0
    if colmax > mask.shape[1]:
        colmax = mask.shape[1]

    # vertices: 2 columns, x (column) and y (row) coordinates of the vertices
    for irow in range(<int>rowmin, <int>rowmax):
        for icol in range(<int>colmin, <int>colmax):
            crossingnumber = 0
            for iedge in range(0, vertices.shape[0]-1):
                # iedge is the starting point of the vertex, iedge +1 is its ending point.
                # notice that indexing of Numpy arrays is (row, column), therefore (y, x)!
                x0 = vertices[iedge, 0]
                y0 = vertices[iedge, 1]
                x1 = vertices[iedge+1, 0]
                y1 = vertices[iedge+1, 1]
                if y1 == y0:
                    # horizontal edge, disregard this.
                    continue
                # The system of equations of the current edge is (t in [0, 1[):
                #   y = y0 + t * (y1-y0)
                #   x = x0 + t * (x1-x0)
                # substituting y = irow and solving for t, we get the x coordinate of the intersection.

                t = (irow - y0) / (y1-y0)
                if t<0 or t>=1:
                    # intersection outside the line section: before the 1st point (t<0) or after (t>=1)
                    continue
                # if t in [0, 1[, then we are OK in the vertical (row) direction, there IS an intersection between the
                # horizontal line and the edge. Let's see the X coordinate now.
                x = x0 + t * (x1 - x0)
                if x >= icol:
                    # Note that we are working with a HALF LINE, pointing right! If the intersection point with the edge
                    # lies to the right from the current point: this is a true intersection! Otherwise, it would be a
                    # false intersection, with the nonexistent left part of the half line.
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