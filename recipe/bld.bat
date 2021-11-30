REM set MENU_DIR="%PREFIX%"\Menu
REM mkdir "%MENU_DIR%"
REM copy recipe\menu_cpt.json %MENU_DIR%\
REM if errorlevel 1 exit 1
REM copy recipe\cptlogo.ico %MENU_DIR%\
REM copy recipe\cpt2logo.ico %MENU_DIR%\
REM if errorlevel 1 exit 1
"%PYTHON%" setup.py install
if errorlevel 1 exit 1
