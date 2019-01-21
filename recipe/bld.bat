set MENU_DIR="%PREFIX%"\Menu
mkdir "%MENU_DIR%"
copy recipe\menu_cpt.json %MENU_DIR%\
if errorlevel 1 exit 1
copy recipe\cptlogo.ico %MENU_DIR%\
if errorlevel 1 exit 1
"%PYTHON%" setup.py install
if errorlevel 1 exit 1
