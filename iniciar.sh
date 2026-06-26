#!/bin/bash
# Script de inicialização — Estoque Bnb Flex

cd "$(dirname "$0")"

echo "======================================"
echo "  Sistema de Estoque — Bnb Flex"
echo "======================================"

# Verifica Python
if ! command -v python3 &> /dev/null; then
    echo "ERRO: Python 3 não encontrado. Instale em https://python.org"
    exit 1
fi

# Instala dependências com pip3
echo "Instalando dependências..."
if command -v pip3 &> /dev/null; then
    pip3 install flask requests -q
elif python3 -m pip --version &> /dev/null; then
    python3 -m pip install flask requests -q
else
    echo "ERRO: pip não encontrado. Execute: python3 -m ensurepip --upgrade"
    exit 1
fi

# Obtém IP da rede local (Mac)
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "localhost")

echo ""
echo "Iniciando servidor..."
echo ""
echo "  Acesse localmente:  http://localhost:8080"
echo "  Acesse na rede:     http://$LOCAL_IP:8080"
echo ""
echo "Pressione Ctrl+C para parar."
echo "--------------------------------------"

python3 app.py
