@echo off
chcp 65001 >nul
echo.
echo  =========================================
echo   EDUCATOR — Configuracao Inicial
echo  =========================================
echo.
echo  Instalando o navegador Chromium...
echo  Aguarde, pode demorar alguns minutos.
echo  (Esta etapa so e necessaria uma vez.)
echo.
educator.exe --install-browser
if %ERRORLEVEL% neq 0 (
    echo.
    echo  [ERRO] Falha na instalacao do navegador.
    echo  Tente executar este arquivo novamente.
    pause
    exit /b 1
)
echo.
echo  =========================================
echo   Tudo pronto!
echo   Execute educator.exe para comecar.
echo  =========================================
echo.
pause
