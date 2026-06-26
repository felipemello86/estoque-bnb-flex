from flask import Flask, render_template, request, jsonify
from database import init_db, get_db, get_config, set_config, fetchall, fetchone, execute
from whatsapp import enviar_alerta_estoque, testar_conexao
import logging
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'bnbflex2024secretkey'

# Cria as tabelas ao iniciar (funciona com gunicorn e direto)
init_db()


# ─── Páginas ──────────────────────────────────────────────────────────────────

@app.route('/')
def dashboard():
    conn = get_db()
    total_produtos = fetchone(conn, 'SELECT COUNT(*) as n FROM produtos')['n']
    em_alerta = fetchone(conn, 'SELECT COUNT(*) as n FROM produtos WHERE quantidade <= estoque_minimo')['n']
    movimentos_hoje = fetchone(conn, "SELECT COUNT(*) as n FROM movimentos WHERE DATE(criado_em) = CURRENT_DATE")['n']
    ultimos_movimentos = fetchall(conn, '''
        SELECT m.*, p.nome as produto_nome, p.unidade
        FROM movimentos m
        JOIN produtos p ON p.id = m.produto_id
        ORDER BY m.criado_em DESC LIMIT 10
    ''')
    alertas = fetchall(conn, 'SELECT * FROM produtos WHERE quantidade <= estoque_minimo ORDER BY nome')
    conn.close()

    return render_template('index.html',
        total_produtos=total_produtos,
        em_alerta=em_alerta,
        movimentos_hoje=movimentos_hoje,
        ultimos_movimentos=ultimos_movimentos,
        alertas=alertas,
        empresa=get_config('empresa_nome') or 'Bnb Flex'
    )


@app.route('/produtos')
def produtos():
    conn = get_db()
    rows = fetchall(conn, 'SELECT * FROM produtos ORDER BY nome')
    categorias = fetchall(conn, 'SELECT DISTINCT categoria FROM produtos ORDER BY categoria')
    conn.close()
    return render_template('produtos.html',
        produtos=rows,
        categorias=[r['categoria'] for r in categorias],
        empresa=get_config('empresa_nome') or 'Bnb Flex'
    )


@app.route('/movimentos')
def movimentos():
    conn = get_db()
    prods = fetchall(conn, 'SELECT id, nome, unidade FROM produtos ORDER BY nome')
    conn.close()
    return render_template('movimentos.html',
        produtos=prods,
        empresa=get_config('empresa_nome') or 'Bnb Flex'
    )


@app.route('/relatorio')
def relatorio():
    conn = get_db()
    prods = fetchall(conn, 'SELECT id, nome FROM produtos ORDER BY nome')
    conn.close()
    return render_template('relatorio.html',
        produtos=prods,
        empresa=get_config('empresa_nome') or 'Bnb Flex'
    )


@app.route('/configuracoes')
def configuracoes():
    cfg = {
        'whatsapp_url': get_config('whatsapp_url') or '',
        'whatsapp_apikey': get_config('whatsapp_apikey') or '',
        'whatsapp_instance': get_config('whatsapp_instance') or '',
        'gestora_telefone': get_config('gestora_telefone') or '',
        'empresa_nome': get_config('empresa_nome') or 'Bnb Flex',
    }
    return render_template('configuracoes.html', cfg=cfg,
        empresa=get_config('empresa_nome') or 'Bnb Flex')


# ─── API Produtos ──────────────────────────────────────────────────────────────

@app.route('/api/produtos', methods=['GET'])
def api_get_produtos():
    conn = get_db()
    categoria = request.args.get('categoria', '')
    busca = request.args.get('busca', '')
    alerta = request.args.get('alerta', '')

    query = 'SELECT * FROM produtos WHERE TRUE'
    params = []
    if categoria:
        query += ' AND categoria = %s'
        params.append(categoria)
    if busca:
        query += ' AND nome ILIKE %s'
        params.append(f'%{busca}%')
    if alerta == '1':
        query += ' AND quantidade <= estoque_minimo'
    query += ' ORDER BY nome'

    rows = fetchall(conn, query, params)
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/api/produtos', methods=['POST'])
def api_criar_produto():
    data = request.json
    conn = get_db()
    try:
        row = fetchone(conn, '''
            INSERT INTO produtos (nome, categoria, unidade, fornecedor, custo, quantidade, estoque_minimo)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        ''', (
            data['nome'], data['categoria'], data.get('unidade', 'un'),
            data.get('fornecedor', ''), float(data.get('custo', 0)),
            float(data.get('quantidade', 0)), float(data.get('estoque_minimo', 0))
        ))
        produto_id = row['id']

        qtd = float(data.get('quantidade', 0))
        if qtd > 0:
            execute(conn, '''
                INSERT INTO movimentos (produto_id, tipo, quantidade, observacao, usuario)
                VALUES (%s, 'entrada', %s, 'Estoque inicial', 'Sistema')
            ''', (produto_id, qtd))

        conn.close()
        return jsonify({'ok': True, 'id': produto_id}), 201
    except Exception as e:
        conn.close()
        return jsonify({'ok': False, 'erro': str(e)}), 400


@app.route('/api/produtos/<int:pid>', methods=['GET'])
def api_get_produto(pid):
    conn = get_db()
    row = fetchone(conn, 'SELECT * FROM produtos WHERE id = %s', (pid,))
    conn.close()
    if not row:
        return jsonify({'ok': False, 'erro': 'Não encontrado'}), 404
    return jsonify(dict(row))


@app.route('/api/produtos/<int:pid>', methods=['PUT'])
def api_atualizar_produto(pid):
    data = request.json
    conn = get_db()
    try:
        execute(conn, '''
            UPDATE produtos
            SET nome=%s, categoria=%s, unidade=%s, fornecedor=%s, custo=%s, estoque_minimo=%s
            WHERE id=%s
        ''', (
            data['nome'], data['categoria'], data.get('unidade', 'un'),
            data.get('fornecedor', ''), float(data.get('custo', 0)),
            float(data.get('estoque_minimo', 0)), pid
        ))
        conn.close()
        return jsonify({'ok': True})
    except Exception as e:
        conn.close()
        return jsonify({'ok': False, 'erro': str(e)}), 400


@app.route('/api/produtos/<int:pid>', methods=['DELETE'])
def api_deletar_produto(pid):
    conn = get_db()
    execute(conn, 'DELETE FROM produtos WHERE id = %s', (pid,))
    conn.close()
    return jsonify({'ok': True})


# ─── API Movimentos ────────────────────────────────────────────────────────────

@app.route('/api/movimentos', methods=['GET'])
def api_get_movimentos():
    conn = get_db()
    produto_id = request.args.get('produto_id', '')
    tipo = request.args.get('tipo', '')
    data_ini = request.args.get('data_ini', '')
    data_fim = request.args.get('data_fim', '')
    limit = int(request.args.get('limit', 50))

    query = '''
        SELECT m.*, p.nome as produto_nome, p.unidade
        FROM movimentos m
        JOIN produtos p ON p.id = m.produto_id
        WHERE TRUE
    '''
    params = []
    if produto_id:
        query += ' AND m.produto_id = %s'
        params.append(produto_id)
    if tipo:
        query += ' AND m.tipo = %s'
        params.append(tipo)
    if data_ini:
        query += ' AND DATE(m.criado_em) >= %s'
        params.append(data_ini)
    if data_fim:
        query += ' AND DATE(m.criado_em) <= %s'
        params.append(data_fim)
    query += ' ORDER BY m.criado_em DESC LIMIT %s'
    params.append(limit)

    rows = fetchall(conn, query, params)
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        if d.get('criado_em'):
            d['criado_em'] = str(d['criado_em'])
        result.append(d)
    return jsonify(result)


@app.route('/api/movimentos', methods=['POST'])
def api_registrar_movimento():
    data = request.json
    produto_id = int(data['produto_id'])
    tipo = data['tipo']
    quantidade = float(data['quantidade'])
    observacao = data.get('observacao', '')
    usuario = data.get('usuario', 'Usuário')

    if quantidade <= 0:
        return jsonify({'ok': False, 'erro': 'Quantidade deve ser maior que zero'}), 400

    conn = get_db()
    produto = fetchone(conn, 'SELECT * FROM produtos WHERE id = %s', (produto_id,))
    if not produto:
        conn.close()
        return jsonify({'ok': False, 'erro': 'Produto não encontrado'}), 404

    nova_qtd = produto['quantidade']
    if tipo == 'entrada':
        nova_qtd += quantidade
    elif tipo == 'saida':
        if quantidade > produto['quantidade']:
            conn.close()
            return jsonify({'ok': False, 'erro': 'Quantidade insuficiente em estoque'}), 400
        nova_qtd -= quantidade

    execute(conn, '''
        INSERT INTO movimentos (produto_id, tipo, quantidade, observacao, usuario)
        VALUES (%s, %s, %s, %s, %s)
    ''', (produto_id, tipo, quantidade, observacao, usuario))

    execute(conn, 'UPDATE produtos SET quantidade = %s WHERE id = %s', (nova_qtd, produto_id))
    conn.close()

    em_alerta = nova_qtd <= produto['estoque_minimo']

    if em_alerta:
        def enviar_bg():
            try:
                enviar_alerta_estoque(
                    produto['nome'], nova_qtd,
                    produto['estoque_minimo'], produto['unidade']
                )
            except Exception as e:
                logger.error(f"Erro ao enviar alerta: {e}")
        threading.Thread(target=enviar_bg, daemon=True).start()

    return jsonify({
        'ok': True,
        'quantidade_atual': nova_qtd,
        'em_alerta': em_alerta,
        'alerta_whatsapp': em_alerta
    })


# ─── API Categorias ────────────────────────────────────────────────────────────

@app.route('/api/categorias')
def api_categorias():
    conn = get_db()
    rows = fetchall(conn, 'SELECT DISTINCT categoria FROM produtos ORDER BY categoria')
    conn.close()
    return jsonify([r['categoria'] for r in rows])


# ─── API Relatório ─────────────────────────────────────────────────────────────

@app.route('/api/relatorio/resumo')
def api_relatorio_resumo():
    conn = get_db()
    data_ini = request.args.get('data_ini', '')
    data_fim = request.args.get('data_fim', '')

    params_mov = []
    filtro_data = ''
    if data_ini:
        filtro_data += ' AND DATE(m.criado_em) >= %s'
        params_mov.append(data_ini)
    if data_fim:
        filtro_data += ' AND DATE(m.criado_em) <= %s'
        params_mov.append(data_fim)

    entradas = fetchone(conn,
        f"SELECT COALESCE(SUM(quantidade), 0) as total FROM movimentos m WHERE tipo='entrada'{filtro_data}",
        params_mov)['total']

    saidas = fetchone(conn,
        f"SELECT COALESCE(SUM(quantidade), 0) as total FROM movimentos m WHERE tipo='saida'{filtro_data}",
        params_mov)['total']

    por_produto = fetchall(conn, f'''
        SELECT p.nome, p.unidade,
            COALESCE(SUM(CASE WHEN m.tipo='entrada' THEN m.quantidade ELSE 0 END), 0) as entradas,
            COALESCE(SUM(CASE WHEN m.tipo='saida' THEN m.quantidade ELSE 0 END), 0) as saidas
        FROM produtos p
        LEFT JOIN movimentos m ON m.produto_id = p.id {filtro_data}
        GROUP BY p.id, p.nome, p.unidade ORDER BY p.nome
    ''', params_mov)

    alertas = fetchall(conn,
        'SELECT nome, quantidade, estoque_minimo, unidade FROM produtos WHERE quantidade <= estoque_minimo')

    conn.close()
    return jsonify({
        'total_entradas': float(entradas),
        'total_saidas': float(saidas),
        'por_produto': [dict(r) for r in por_produto],
        'alertas': [dict(r) for r in alertas]
    })


# ─── API Configurações ─────────────────────────────────────────────────────────

@app.route('/api/configuracoes', methods=['POST'])
def api_salvar_config():
    data = request.json
    logger.info(f"Salvando configurações: {list(data.keys())}")
    campos = ['whatsapp_url', 'whatsapp_apikey', 'whatsapp_instance', 'gestora_telefone', 'empresa_nome']
    for campo in campos:
        if campo in data:
            set_config(campo, data[campo])
            logger.info(f"set_config({campo}) = '{data[campo][:10]}...' " if data[campo] else f"set_config({campo}) = ''")
    # Verifica o que foi salvo
    url = get_config('whatsapp_url')
    apikey = get_config('whatsapp_apikey')
    instance = get_config('whatsapp_instance')
    logger.info(f"Após salvar — url={bool(url)}, apikey={bool(apikey)}, instance={bool(instance)}")
    return jsonify({'ok': True})


@app.route('/api/whatsapp/teste', methods=['POST'])
def api_testar_whatsapp():
    url = get_config('whatsapp_url')
    apikey = get_config('whatsapp_apikey')
    instance = get_config('whatsapp_instance')
    logger.info(f"Teste WPP — url={repr(url)}, apikey={repr(apikey)}, instance={repr(instance)}")
    ok, estado = testar_conexao()
    # Traduz estados para mensagens amigáveis
    mensagens = {
        'open': 'Conectado',
        'connecting': 'Reconectando... aguarde 1 min e teste novamente',
        'close': 'Desconectado',
        'unknown': 'Estado desconhecido',
        'Configurações incompletas': 'Configurações incompletas',
    }
    estado_msg = mensagens.get(estado, estado)
    return jsonify({'ok': ok, 'estado': estado_msg})


@app.route('/api/whatsapp/enviar_teste', methods=['POST'])
def api_enviar_teste_whatsapp():
    """Envia uma mensagem de teste real para o telefone da gestora."""
    enviado = enviar_alerta_estoque(
        produto_nome='TESTE',
        quantidade_atual=0,
        estoque_minimo=1,
        unidade='un'
    )
    return jsonify({'ok': enviado, 'mensagem': 'Mensagem enviada!' if enviado else 'Falha ao enviar'})


# ──────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    import os
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
