set MENU_DIR="%PREFIX%"\Menu
mkdir "%MENU_DIR%"
copy menu_cpt.json %MENU_DIR%\
if errorlevel 1 exit 1
copy cptlogo.png %MENU_DIR%\
if errorlevel 1 exit 1
"%PYTHON%" setup.py install
if errorlevel 1 exit 1
