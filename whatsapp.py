import requests
from database import get_config
import logging

logger = logging.getLogger(__name__)


def enviar_alerta_estoque(produto_nome, quantidade_atual, estoque_minimo, unidade):
    """Envia alerta via WhatsApp quando produto atinge estoque mínimo."""
    url = get_config('whatsapp_url')
    apikey = get_config('whatsapp_apikey')
    instance = get_config('whatsapp_instance')
    telefone = get_config('gestora_telefone')
    empresa = get_config('empresa_nome') or 'Bnb Flex'

    if not all([url, apikey, instance, telefone]):
        logger.warning('WhatsApp não configurado. Alerta não enviado.')
        return False

    # Normaliza telefone (apenas dígitos) e adiciona sufixo WhatsApp
    telefone = ''.join(filter(str.isdigit, telefone))
    numero_wpp = f"{telefone}@s.whatsapp.net"

    mensagem = (
        f"⚠️ *ALERTA DE ESTOQUE - {empresa}*\n\n"
        f"O produto *{produto_nome}* atingiu o nível mínimo de estoque!\n\n"
        f"📦 Quantidade atual: *{quantidade_atual} {unidade}*\n"
        f"🚨 Estoque mínimo: *{estoque_minimo} {unidade}*\n\n"
        f"Por favor, providencie a reposição."
    )

    endpoint = f"{url.rstrip('/')}/message/sendText/{instance}"

    payload = {
        "number": numero_wpp,
        "text": mensagem
    }

    headers = {
        "Content-Type": "application/json",
        "apikey": apikey
    }

    try:
        logger.info(f"Enviando alerta para {telefone} via {endpoint}")
        response = requests.post(endpoint, json=payload, headers=headers, timeout=30)
        logger.info(f"Resposta Evolution API: {response.status_code} — {response.text[:300]}")
        response.raise_for_status()
        logger.info(f"Alerta WhatsApp enviado para {telefone}: {produto_nome}")
        return True
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro ao enviar WhatsApp: {e}")
        return False


def testar_conexao():
    """Testa a conexão com a Evolution API."""
    url = get_config('whatsapp_url')
    apikey = get_config('whatsapp_apikey')
    instance = get_config('whatsapp_instance')

    if not all([url, apikey, instance]):
        return False, "Configurações incompletas"

    endpoint = f"{url.rstrip('/')}/instance/connectionState/{instance}"
    headers = {"apikey": apikey}

    try:
        response = requests.get(endpoint, headers=headers, timeout=10)
        logger.info(f"Evolution API status {response.status_code}: {response.text[:200]}")
        data = response.json()
        state = data.get('instance', {}).get('state', 'unknown')
        connected = state == 'open'
        return connected, state
    except Exception as e:
        logger.error(f"Erro ao testar conexão: {e}")
        return False, str(e)
