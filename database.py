import os
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get('DATABASE_URL')

# Render fornece URLs com "postgres://" — psycopg2 exige "postgresql://"
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)


def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            categoria TEXT NOT NULL,
            unidade TEXT NOT NULL DEFAULT 'un',
            fornecedor TEXT,
            custo REAL DEFAULT 0,
            quantidade REAL NOT NULL DEFAULT 0,
            estoque_minimo REAL NOT NULL DEFAULT 0,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS movimentos (
            id SERIAL PRIMARY KEY,
            produto_id INTEGER NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
            tipo TEXT NOT NULL CHECK(tipo IN ('entrada', 'saida')),
            quantidade REAL NOT NULL,
            observacao TEXT,
            usuario TEXT DEFAULT 'Sistema',
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor TEXT
        )
    ''')

    defaults = [
        ('whatsapp_url', ''),
        ('whatsapp_apikey', ''),
        ('whatsapp_instance', ''),
        ('gestora_telefone', ''),
        ('empresa_nome', 'Bnb Flex'),
    ]
    for chave, valor in defaults:
        c.execute(
            'INSERT INTO configuracoes (chave, valor) VALUES (%s, %s) ON CONFLICT (chave) DO NOTHING',
            (chave, valor)
        )

    conn.commit()
    conn.close()


def fetchall(conn, query, params=()):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        return cur.fetchall()


def fetchone(conn, query, params=()):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        return cur.fetchone()


def execute(conn, query, params=()):
    with conn.cursor() as cur:
        cur.execute(query, params)
    conn.commit()


def get_config(chave):
    conn = get_db()
    row = fetchone(conn, 'SELECT valor FROM configuracoes WHERE chave = %s', (chave,))
    conn.close()
    return row['valor'] if row else None


def set_config(chave, valor):
    conn = get_db()
    execute(conn, 'INSERT INTO configuracoes (chave, valor) VALUES (%s, %s) ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor', (chave, valor))
    conn.close()
