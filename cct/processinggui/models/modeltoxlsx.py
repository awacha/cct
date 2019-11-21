import openpyxl
from PyQt5 import QtCore

def model2xlsx(filename:str, sheetname:str, model:QtCore.QAbstractItemModel):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheetname
    for row in range(model.rowCount()):
        for col in range(model.columnCount()):
            ws.cell(row+1, col+1, value=model.index(row, col).data(QtCore.Qt.DisplayRole))
    wb.save(filename)
