@echo off
chcp 65001 >nul
echo ======================================
echo   Sistema de Estoque — Bnb Flex
echo ======================================

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo ERRO: Python nao encontrado. Instale em https://python.org
    pause
    exit /b 1
)

if not exist "venv\" (
    echo Criando ambiente virtual...
    python -m venv venv
)

call venv\Scripts\activate

echo Instalando dependencias...
pip install -r requirements.txt -q

echo.
echo Iniciando servidor...
echo.
echo   Acesse: http://localhost:5000
echo.
echo Pressione Ctrl+C para parar.
echo --------------------------------------

python app.py
pause
