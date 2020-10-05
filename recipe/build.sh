export CFLAGS="${CFLAGS} -I${PREFIX}/include"
$PYTHON setup.py install --single-version-externally-managed --record record.txt

