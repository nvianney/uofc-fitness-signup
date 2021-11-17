@echo off
SET FILE=win_uofc_fitness.exe

IF EXIST dist/%FILE% DEL dist/%FILE%
pyinstaller package.spec --onefile --key "f9A*8723FAoipw(" --name %FILE%

@echo off
SET FILE=
