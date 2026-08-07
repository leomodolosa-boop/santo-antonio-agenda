import math
import os
import shutil
import sqlite3
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DATABASE_URL = os.environ.get("DATABASE_URL")
USANDO_POSTGRES = bool(DATABASE_URL)

if USANDO_POSTGRES:
    import psycopg2
    import psycopg2.extras


class ErroIntegridade(Exception):
    """Violação de restrição UNIQUE/NOT NULL, unificada entre SQLite e Postgres."""


BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "agenda_futebol.db"
ESCUDOS_DIR = BASE_DIR / "static" / "escudos"
JOGADORES_DIR = BASE_DIR / "static" / "jogadores"
ICONS_DIR = BASE_DIR / "static" / "icons"
BRAND_ESCUDO_OFICIAL = BASE_DIR / "static" / "brand" / "escudo_oficial.png"

TIME_FIXO = "Santo Antônio do Oriente"

TIMES_INICIAIS = [
    "Santo Antônio do Oriente",
    "Ipê",
    "Taquarussu",
    "Bar de Muniqu",
    "São Bento",
    "Alto Rio da Cobra",
    "Expocláudio",
    "Pizzol",
    "São Roque",
    "PSV",
    "Fazenda Estado",
    "Corumbá",
    "União FC",
    "Tropa do Mantém",
    "Campestre",
    "Braço do Sul",
    "Mata Fria",
    "Rancho Dantas",
    "São João",
    "São B Garrafão",
    "São José",
    "Perim FC - Garrafão",
    "Bacia",
    "Amigos do Esporte",
    "Atlético VNI",
]

TIME_FIXO_CIDADE = "Venda Nova do Imigrante"
TIME_FIXO_CAMPO = "Campo do Santo Antônio do Oriente"
TIME_FIXO_ENDERECO = "Comunidade Santo Antônio do Oriente, s/n"

LOCAL_CASA = "Santo Antônio do Oriente - Venda Nova do Imigrante"
HORA_PADRAO = "15:00"

# (data, nome_adversario, mandante, local, observacao) — agenda pré-definida da temporada 2026.
# mandante: 'casa' (Santo Antônio manda) ou 'fora' (adversário manda).
# status sempre nasce 'pendente'; INSERT OR IGNORE preserva edições já feitas pelo usuário.
JOGOS_INICIAIS = [
    ("2026-02-07", "Ipê", "casa", LOCAL_CASA, ""),
    ("2026-02-14", "Taquarussu", "casa", LOCAL_CASA, ""),
    ("2026-02-21", "Bar de Muniqu", "casa", LOCAL_CASA, ""),
    ("2026-02-28", "São Bento", "casa", LOCAL_CASA, ""),
    ("2026-03-07", "Alto Rio da Cobra", "casa", "", "Mandante a confirmar"),
    ("2026-03-14", "Expocláudio", "casa", LOCAL_CASA, ""),
    ("2026-03-21", "Pizzol", "casa", LOCAL_CASA, ""),
    ("2026-03-28", "São Roque", "fora", "", ""),
    ("2026-04-04", "PSV", "casa", LOCAL_CASA, ""),
    ("2026-04-11", "Fazenda Estado", "fora", "", ""),
    ("2026-04-25", "Corumbá", "fora", "", ""),
    ("2026-05-02", "União FC", "casa", LOCAL_CASA, ""),
    ("2026-05-09", "Tropa do Mantém", "casa", LOCAL_CASA, ""),
    ("2026-05-16", "Campestre", "fora", "", ""),
    ("2026-05-30", "Taquarussu", "fora", "", ""),
    ("2026-06-06", "Braço do Sul", "fora", "", ""),
    ("2026-06-13", "Mata Fria", "fora", "", ""),
    ("2026-06-20", "Rancho Dantas", "casa", LOCAL_CASA, ""),
    ("2026-06-27", "São João", "casa", LOCAL_CASA, ""),
    ("2026-07-04", "São B Garrafão", "casa", LOCAL_CASA, ""),
    ("2026-07-11", "Ipê", "fora", "", ""),
    ("2026-07-18", "Atlético VNI", "casa", "", "Mandante a confirmar"),
    ("2026-07-25", "São Bento", "fora", "", ""),
    ("2026-08-01", "São Roque", "casa", LOCAL_CASA, ""),
    ("2026-08-08", "Amigos do Esporte", "casa", LOCAL_CASA, ""),
    ("2026-08-15", "São José", "fora", "", ""),
    ("2026-08-22", "Pizzol", "casa", "", "Mandante a confirmar"),
    ("2026-08-29", "São João", "fora", "", ""),
    ("2026-09-05", "Fazenda Estado", "casa", LOCAL_CASA, ""),
    ("2026-09-12", "Perim FC - Garrafão", "casa", LOCAL_CASA, ""),
    ("2026-09-19", "Bacia", "casa", LOCAL_CASA, ""),
    ("2026-10-03", "União FC", "fora", "Santa Luzia", ""),
    ("2026-10-10", "Mata Fria", "casa", LOCAL_CASA, ""),
    ("2026-10-31", "Corumbá", "casa", LOCAL_CASA, ""),
    ("2026-11-07", "Amigos do Esporte", "fora", "", ""),
    ("2026-11-28", "São José", "casa", LOCAL_CASA, ""),
    ("2026-12-05", "Rancho Dantas", "fora", "", ""),
]


def gerar_icones_pwa(caminho_escudo):
    """Gera os ícones do app (192px/512px): faixas da bandeira (grená/branco/
    verde) como fundo, com o escudo centralizado por cima."""
    try:
        origem = Image.open(caminho_escudo).convert("RGBA")
    except Exception:
        return

    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    for tamanho in (192, 512):
        fundo = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
        faixa = tamanho / 3
        for i, cor in enumerate([(107, 21, 34, 255), (246, 246, 244, 255), (15, 74, 44, 255)]):
            bloco = Image.new("RGBA", (tamanho, int(faixa) + 1), cor)
            fundo.paste(bloco, (0, int(i * faixa)))

        area = int(tamanho * 0.82)
        miniatura = origem.copy()
        miniatura.thumbnail((area, area), Image.LANCZOS)
        x = (tamanho - miniatura.width) // 2
        y = (tamanho - miniatura.height) // 2
        fundo.paste(miniatura, (x, y), miniatura)
        fundo.convert("RGB").save(ICONS_DIR / f"icon-{tamanho}.png")


PALETA_ESCUDOS = [
    (31, 111, 235), (211, 36, 47), (130, 80, 223), (191, 135, 0),
    (9, 105, 218), (17, 99, 41), (138, 99, 210), (149, 56, 0),
    (5, 80, 174), (164, 14, 38), (63, 143, 80), (191, 96, 9),
]
CONECTORES_NOME = {"de", "do", "da", "e", "fc"}


def _fonte_escudo(tamanho):
    try:
        return ImageFont.load_default(size=tamanho)
    except TypeError:
        return ImageFont.load_default()


def _iniciais_time(nome):
    palavras = [p for p in nome.replace("-", " ").split() if p.lower() not in CONECTORES_NOME]
    if not palavras:
        palavras = nome.split()
    if len(palavras) == 1:
        return palavras[0][:2].upper()
    return (palavras[0][0] + palavras[1][0]).upper()


def gerar_escudo_padrao(nome, indice, caminho_saida):
    """Gera um escudo simples e provisório (formato e cor variam por time),
    só pra não ficar sem imagem nenhuma até o usuário subir o escudo real."""
    tamanho = 640
    cor = PALETA_ESCUDOS[indice % len(PALETA_ESCUDOS)]
    estilo = indice % 4
    img = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = tamanho / 2
    r = tamanho * 0.42
    branco = (255, 255, 255, 255)
    preenchimento = cor + (255,)

    if estilo == 0:  # círculo
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=preenchimento, outline=branco, width=8)
    elif estilo == 1:  # escudo
        pontos = [
            (cx - r, cy - r * 0.75), (cx + r, cy - r * 0.75),
            (cx + r, cy + r * 0.25), (cx, cy + r * 1.1), (cx - r, cy + r * 0.25),
        ]
        d.polygon(pontos, fill=preenchimento)
        d.line(pontos + [pontos[0]], fill=branco, width=8, joint="curve")
    elif estilo == 2:  # hexágono
        pontos = [
            (cx + r * math.cos(math.radians(60 * i - 30)), cy + r * math.sin(math.radians(60 * i - 30)))
            for i in range(6)
        ]
        d.polygon(pontos, fill=preenchimento)
        d.line(pontos + [pontos[0]], fill=branco, width=8, joint="curve")
    else:  # quadrado arredondado
        d.rounded_rectangle([cx - r, cy - r, cx + r, cy + r], radius=r * 0.35, fill=preenchimento, outline=branco, width=8)

    iniciais = _iniciais_time(nome)
    fonte = _fonte_escudo(int(tamanho * 0.32))
    caixa = d.textbbox((0, 0), iniciais, font=fonte)
    largura = caixa[2] - caixa[0]
    altura = caixa[3] - caixa[1]
    d.text((cx - largura / 2 - caixa[0], cy - altura / 2 - caixa[1]), iniciais, font=fonte, fill=branco)

    img.save(caminho_saida)


class _CursorPostgres:
    """Deixa o cursor do psycopg2 parecido com o do sqlite3 (rowcount, iteração direta)."""

    def __init__(self, cursor):
        self._cursor = cursor

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)

    @property
    def rowcount(self):
        return self._cursor.rowcount


class _ConexaoPostgres:
    """Faz a conexão psycopg2 aceitar o mesmo padrão de uso do sqlite3.Connection
    usado no resto do app: conn.execute(sql_com_?, params).fetchone()/.fetchall()."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        cursor = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cursor.execute(sql.replace("?", "%s"), params)
        except psycopg2.IntegrityError as e:
            self._conn.rollback()
            raise ErroIntegridade(str(e)) from e
        return _CursorPostgres(cursor)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_conn():
    if USANDO_POSTGRES:
        return _ConexaoPostgres(psycopg2.connect(DATABASE_URL))
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def salvar_escudo_blob(conn, time_id, caminho):
    """No Postgres, guarda o PNG do escudo dentro do banco (bytea) pra sobreviver
    a redeploys, já que o disco do Render é apagado a cada atualização.
    Não dá commit — quem chama decide quando (bulk no init_db faz um commit
    só no final, pra não multiplicar idas-e-voltas de rede)."""
    if not USANDO_POSTGRES:
        return
    dados = Path(caminho).read_bytes()
    conn.execute(
        "UPDATE times SET escudo_dados = ? WHERE id = ?",
        (psycopg2.Binary(dados), time_id),
    )


def salvar_foto_jogador_blob(conn, jogador_id, caminho):
    """Mesma ideia do escudo: guarda a foto do jogador no Postgres (bytea)
    pra sobreviver a redeploys. Também não dá commit sozinha."""
    if not USANDO_POSTGRES:
        return
    dados = Path(caminho).read_bytes()
    conn.execute(
        "UPDATE jogadores SET foto_dados = ? WHERE id = ?",
        (psycopg2.Binary(dados), jogador_id),
    )


def cor_dominante_escudo(caminho):
    """Cor média do escudo (ignorando pixels transparentes), usada como acento
    visual do time nos cards de jogo. Retorna None se não conseguir ler a imagem."""
    try:
        img = Image.open(caminho).convert("RGBA")
    except Exception:
        return None
    img.thumbnail((48, 48))
    r = g = b = total = 0
    for pr, pg, pb, pa in img.getdata():
        if pa < 30:
            continue
        r += pr
        g += pg
        b += pb
        total += 1
    if not total:
        return None
    return "#{:02x}{:02x}{:02x}".format(r // total, g // total, b // total)


def salvar_cor_escudo(conn, time_id, caminho):
    """Também não dá commit — mesma razão das funções acima."""
    cor = cor_dominante_escudo(caminho)
    if cor:
        conn.execute("UPDATE times SET escudo_cor = ? WHERE id = ?", (cor, time_id))
    return cor


def init_db():
    conn = get_conn()

    if USANDO_POSTGRES:
        # Um único round-trip para todo o DDL — cada ida-e-volta ao Postgres
        # remoto custa ~250-300ms, e isso soma rápido no boot do app.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS times (
                id SERIAL PRIMARY KEY,
                nome TEXT UNIQUE NOT NULL,
                cidade TEXT,
                contato TEXT,
                is_fixo INTEGER NOT NULL DEFAULT 0,
                escudo TEXT,
                escudo_dados BYTEA,
                escudo_cor TEXT,
                nome_campo TEXT,
                endereco TEXT,
                cep TEXT,
                campo_mapa_url TEXT
            );
            ALTER TABLE times ADD COLUMN IF NOT EXISTS escudo_cor TEXT;
            ALTER TABLE times ADD COLUMN IF NOT EXISTS cep TEXT;
            ALTER TABLE times ADD COLUMN IF NOT EXISTS campo_mapa_url TEXT;
            CREATE TABLE IF NOT EXISTS jogos (
                id SERIAL PRIMARY KEY,
                data TEXT NOT NULL UNIQUE,
                hora TEXT,
                adversario_id INTEGER NOT NULL REFERENCES times(id),
                mandante TEXT NOT NULL DEFAULT 'casa',
                local TEXT,
                local_mapa_url TEXT,
                status TEXT NOT NULL DEFAULT 'confirmado',
                placar_santo INTEGER,
                placar_adversario INTEGER,
                observacao TEXT,
                resultado_lancado INTEGER NOT NULL DEFAULT 0
            );
            ALTER TABLE jogos ADD COLUMN IF NOT EXISTS local_mapa_url TEXT;
            ALTER TABLE jogos ADD COLUMN IF NOT EXISTS resultado_lancado INTEGER NOT NULL DEFAULT 0;
            CREATE TABLE IF NOT EXISTS usuarios (
                id SERIAL PRIMARY KEY,
                nome TEXT NOT NULL,
                email TEXT,
                usuario TEXT UNIQUE NOT NULL,
                senha_hash TEXT NOT NULL,
                perfil TEXT NOT NULL DEFAULT 'visualizacao',
                perm_jogos INTEGER NOT NULL DEFAULT 1,
                perm_times INTEGER NOT NULL DEFAULT 1,
                perm_jogadores INTEGER NOT NULL DEFAULT 1,
                perm_usuarios INTEGER NOT NULL DEFAULT 1,
                perm_confirmar_jogos INTEGER NOT NULL DEFAULT 1
            );
            ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS perm_jogos INTEGER NOT NULL DEFAULT 1;
            ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS perm_times INTEGER NOT NULL DEFAULT 1;
            ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS perm_jogadores INTEGER NOT NULL DEFAULT 1;
            ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS perm_usuarios INTEGER NOT NULL DEFAULT 1;
            ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS perm_confirmar_jogos INTEGER NOT NULL DEFAULT 1;
            ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS perm_mensalidades INTEGER NOT NULL DEFAULT 0;
            CREATE TABLE IF NOT EXISTS jogadores (
                id SERIAL PRIMARY KEY,
                nome_completo TEXT NOT NULL,
                apelido TEXT,
                posicao TEXT,
                numero_camisa INTEGER,
                status TEXT NOT NULL DEFAULT 'ativo',
                foto TEXT,
                foto_dados BYTEA,
                data_cadastro TEXT NOT NULL,
                conta_estatisticas INTEGER NOT NULL DEFAULT 1,
                participa_mensalidade INTEGER NOT NULL DEFAULT 0
            );
            ALTER TABLE jogadores ADD COLUMN IF NOT EXISTS conta_estatisticas INTEGER NOT NULL DEFAULT 1;
            ALTER TABLE jogadores ADD COLUMN IF NOT EXISTS participa_mensalidade INTEGER NOT NULL DEFAULT 0;
            CREATE TABLE IF NOT EXISTS gols (
                id SERIAL PRIMARY KEY,
                jogo_id INTEGER NOT NULL REFERENCES jogos(id) ON DELETE CASCADE,
                jogador_id INTEGER NOT NULL REFERENCES jogadores(id) ON DELETE CASCADE,
                quantidade INTEGER NOT NULL DEFAULT 1,
                UNIQUE(jogo_id, jogador_id)
            );
            CREATE TABLE IF NOT EXISTS mensalidades (
                id SERIAL PRIMARY KEY,
                jogador_id INTEGER NOT NULL REFERENCES jogadores(id) ON DELETE CASCADE,
                ano INTEGER NOT NULL,
                mes INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'aberto',
                data_pagamento TEXT,
                observacao TEXT,
                valor TEXT,
                UNIQUE(jogador_id, ano, mes)
            );
            ALTER TABLE mensalidades ADD COLUMN IF NOT EXISTS valor TEXT;
            """
        )
    else:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS times (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT UNIQUE NOT NULL,
                cidade TEXT,
                contato TEXT,
                is_fixo INTEGER NOT NULL DEFAULT 0,
                escudo TEXT,
                nome_campo TEXT,
                endereco TEXT,
                cep TEXT,
                campo_mapa_url TEXT
            );

            CREATE TABLE IF NOT EXISTS jogos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL UNIQUE,
                hora TEXT,
                adversario_id INTEGER NOT NULL REFERENCES times(id),
                mandante TEXT NOT NULL DEFAULT 'casa',
                local TEXT,
                local_mapa_url TEXT,
                status TEXT NOT NULL DEFAULT 'confirmado',
                placar_santo INTEGER,
                placar_adversario INTEGER,
                observacao TEXT
            );

            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                email TEXT,
                usuario TEXT UNIQUE NOT NULL,
                senha_hash TEXT NOT NULL,
                perfil TEXT NOT NULL DEFAULT 'visualizacao',
                perm_jogos INTEGER NOT NULL DEFAULT 1,
                perm_times INTEGER NOT NULL DEFAULT 1,
                perm_jogadores INTEGER NOT NULL DEFAULT 1,
                perm_usuarios INTEGER NOT NULL DEFAULT 1,
                perm_confirmar_jogos INTEGER NOT NULL DEFAULT 1,
                perm_mensalidades INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS jogadores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_completo TEXT NOT NULL,
                apelido TEXT,
                posicao TEXT,
                numero_camisa INTEGER,
                status TEXT NOT NULL DEFAULT 'ativo',
                foto TEXT,
                data_cadastro TEXT NOT NULL,
                conta_estatisticas INTEGER NOT NULL DEFAULT 1,
                participa_mensalidade INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS gols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jogo_id INTEGER NOT NULL REFERENCES jogos(id) ON DELETE CASCADE,
                jogador_id INTEGER NOT NULL REFERENCES jogadores(id) ON DELETE CASCADE,
                quantidade INTEGER NOT NULL DEFAULT 1,
                UNIQUE(jogo_id, jogador_id)
            );

            CREATE TABLE IF NOT EXISTS mensalidades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jogador_id INTEGER NOT NULL REFERENCES jogadores(id) ON DELETE CASCADE,
                ano INTEGER NOT NULL,
                mes INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'aberto',
                data_pagamento TEXT,
                observacao TEXT,
                valor TEXT,
                UNIQUE(jogador_id, ano, mes)
            );
            """
        )
        conn.commit()

        colunas = {row["name"] for row in conn.execute("PRAGMA table_info(times)")}
        if "escudo" not in colunas:
            conn.execute("ALTER TABLE times ADD COLUMN escudo TEXT")
        if "nome_campo" not in colunas:
            conn.execute("ALTER TABLE times ADD COLUMN nome_campo TEXT")
        if "endereco" not in colunas:
            conn.execute("ALTER TABLE times ADD COLUMN endereco TEXT")
        if "escudo_cor" not in colunas:
            conn.execute("ALTER TABLE times ADD COLUMN escudo_cor TEXT")
        if "cep" not in colunas:
            conn.execute("ALTER TABLE times ADD COLUMN cep TEXT")
        if "campo_mapa_url" not in colunas:
            conn.execute("ALTER TABLE times ADD COLUMN campo_mapa_url TEXT")
        conn.commit()

        colunas_jogos = {row["name"] for row in conn.execute("PRAGMA table_info(jogos)")}
        if "hora" not in colunas_jogos:
            conn.execute("ALTER TABLE jogos ADD COLUMN hora TEXT")
        if "mandante" not in colunas_jogos:
            conn.execute("ALTER TABLE jogos ADD COLUMN mandante TEXT NOT NULL DEFAULT 'casa'")
        if "local_mapa_url" not in colunas_jogos:
            conn.execute("ALTER TABLE jogos ADD COLUMN local_mapa_url TEXT")
        if "resultado_lancado" not in colunas_jogos:
            conn.execute("ALTER TABLE jogos ADD COLUMN resultado_lancado INTEGER NOT NULL DEFAULT 0")
        conn.commit()

        colunas_jogadores = {row["name"] for row in conn.execute("PRAGMA table_info(jogadores)")}
        if "conta_estatisticas" not in colunas_jogadores:
            conn.execute("ALTER TABLE jogadores ADD COLUMN conta_estatisticas INTEGER NOT NULL DEFAULT 1")
        if "participa_mensalidade" not in colunas_jogadores:
            conn.execute("ALTER TABLE jogadores ADD COLUMN participa_mensalidade INTEGER NOT NULL DEFAULT 0")
        conn.commit()

        colunas_usuarios = {row["name"] for row in conn.execute("PRAGMA table_info(usuarios)")}
        for coluna in ("perm_jogos", "perm_times", "perm_jogadores", "perm_usuarios", "perm_confirmar_jogos"):
            if coluna not in colunas_usuarios:
                conn.execute(f"ALTER TABLE usuarios ADD COLUMN {coluna} INTEGER NOT NULL DEFAULT 1")
        if "perm_mensalidades" not in colunas_usuarios:
            conn.execute("ALTER TABLE usuarios ADD COLUMN perm_mensalidades INTEGER NOT NULL DEFAULT 0")
        conn.commit()

        colunas_mensalidades = {row["name"] for row in conn.execute("PRAGMA table_info(mensalidades)")}
        if "valor" not in colunas_mensalidades:
            conn.execute("ALTER TABLE mensalidades ADD COLUMN valor TEXT")
        conn.commit()

    # Só semeia os times iniciais se a tabela estiver vazia (primeiro boot).
    # Antes isso rodava sempre que faltasse um NOME da lista — o que recriava
    # um time "do zero" toda vez que alguém corrigia o nome dele e o app
    # reiniciava (cada deploy no Render reinicia o processo).
    if not conn.execute("SELECT 1 FROM times LIMIT 1").fetchone():
        for nome in TIMES_INICIAIS:
            conn.execute(
                "INSERT INTO times (nome, is_fixo) VALUES (?, ?)",
                (nome, 1 if nome == TIME_FIXO else 0),
            )

    conn.execute(
        """
        UPDATE times
        SET cidade = COALESCE(cidade, ?), nome_campo = COALESCE(nome_campo, ?), endereco = COALESCE(endereco, ?)
        WHERE is_fixo = 1
        """,
        (TIME_FIXO_CIDADE, TIME_FIXO_CAMPO, TIME_FIXO_ENDERECO),
    )

    ESCUDOS_DIR.mkdir(parents=True, exist_ok=True)

    # Uma única query traz escudo + blob de todo mundo, em vez de uma consulta
    # por time — com 25+ times isso é a diferença entre ~1s e ~15s de boot,
    # o suficiente pra estourar o tempo limite de deploy do Render.
    campo_blob = ", escudo_dados" if USANDO_POSTGRES else ""
    todos_times = conn.execute(
        f"SELECT id, nome, escudo, escudo_cor, is_fixo{campo_blob} FROM times ORDER BY is_fixo DESC, id"
    ).fetchall()

    for time_row in todos_times:
        eh_fixo = bool(time_row["is_fixo"])
        nome_arquivo = time_row["escudo"]
        precisa_cor = not time_row["escudo_cor"]
        blob = time_row["escudo_dados"] if USANDO_POSTGRES else None

        if nome_arquivo:
            caminho = ESCUDOS_DIR / nome_arquivo
            if not caminho.exists():
                if blob is not None:
                    Path(caminho).write_bytes(bytes(blob))
                elif eh_fixo and BRAND_ESCUDO_OFICIAL.exists():
                    shutil.copyfile(BRAND_ESCUDO_OFICIAL, caminho)
                elif not eh_fixo:
                    gerar_escudo_padrao(time_row["nome"], time_row["id"], caminho)
                    salvar_escudo_blob(conn, time_row["id"], caminho)
        elif eh_fixo and BRAND_ESCUDO_OFICIAL.exists():
            nome_arquivo = f"time_{time_row['id']}.png"
            caminho = ESCUDOS_DIR / nome_arquivo
            shutil.copyfile(BRAND_ESCUDO_OFICIAL, caminho)
            conn.execute("UPDATE times SET escudo = ? WHERE id = ?", (nome_arquivo, time_row["id"]))
            salvar_escudo_blob(conn, time_row["id"], caminho)
        elif not eh_fixo:
            nome_arquivo = f"time_{time_row['id']}.png"
            caminho = ESCUDOS_DIR / nome_arquivo
            gerar_escudo_padrao(time_row["nome"], time_row["id"], caminho)
            conn.execute("UPDATE times SET escudo = ? WHERE id = ?", (nome_arquivo, time_row["id"]))
            salvar_escudo_blob(conn, time_row["id"], caminho)
        else:
            caminho = None

        if caminho and caminho.exists():
            if eh_fixo:
                gerar_icones_pwa(caminho)
            if precisa_cor:
                salvar_cor_escudo(conn, time_row["id"], caminho)

    # Restaura (ou gera) as fotos dos jogadores do mesmo jeito que os
    # escudos — mesmo problema do disco efêmero do Render.
    JOGADORES_DIR.mkdir(parents=True, exist_ok=True)
    campo_blob_jogador = ", foto_dados" if USANDO_POSTGRES else ""
    todos_jogadores = conn.execute(
        f"SELECT id, nome_completo, foto{campo_blob_jogador} FROM jogadores ORDER BY id"
    ).fetchall()
    for jogador_row in todos_jogadores:
        nome_arquivo = jogador_row["foto"]
        blob = jogador_row["foto_dados"] if USANDO_POSTGRES else None
        if nome_arquivo:
            caminho = JOGADORES_DIR / nome_arquivo
            if not caminho.exists():
                if blob is not None:
                    Path(caminho).write_bytes(bytes(blob))
                else:
                    gerar_escudo_padrao(jogador_row["nome_completo"], jogador_row["id"], caminho)
                    salvar_foto_jogador_blob(conn, jogador_row["id"], caminho)
        else:
            nome_arquivo = f"jogador_{jogador_row['id']}.png"
            caminho = JOGADORES_DIR / nome_arquivo
            gerar_escudo_padrao(jogador_row["nome_completo"], jogador_row["id"], caminho)
            conn.execute("UPDATE jogadores SET foto = ? WHERE id = ?", (nome_arquivo, jogador_row["id"]))
            salvar_foto_jogador_blob(conn, jogador_row["id"], caminho)

    ids_times = {row["nome"]: row["id"] for row in todos_times}
    linhas = [
        (data, HORA_PADRAO, ids_times[nome_adversario], mandante, local, observacao)
        for data, nome_adversario, mandante, local, observacao in JOGOS_INICIAIS
        if nome_adversario in ids_times
    ]
    if linhas:
        # Uma única query com todas as linhas, em vez de uma por jogo — com o
        # Postgres remoto, cada ida-e-volta de rede custa ~250-300ms, e são
        # dezenas de jogos pré-cadastrados na temporada.
        if USANDO_POSTGRES:
            marcadores = ", ".join(["(?, ?, ?, ?, ?, 'pendente', ?)"] * len(linhas))
            sql = f"""
                INSERT INTO jogos (data, hora, adversario_id, mandante, local, status, observacao)
                VALUES {marcadores}
                ON CONFLICT (data) DO NOTHING
            """
            parametros = tuple(valor for linha in linhas for valor in linha)
            conn.execute(sql, parametros)
        else:
            marcadores = ", ".join(["(?, ?, ?, ?, ?, 'pendente', ?)"] * len(linhas))
            sql = f"""
                INSERT OR IGNORE INTO jogos (data, hora, adversario_id, mandante, local, status, observacao)
                VALUES {marcadores}
            """
            parametros = tuple(valor for linha in linhas for valor in linha)
            conn.execute(sql, parametros)

    conn.execute("UPDATE jogos SET hora = ? WHERE hora IS NULL OR hora = ''", (HORA_PADRAO,))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Banco inicializado em {DB_PATH}")
