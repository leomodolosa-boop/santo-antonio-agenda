import shutil
import sqlite3
from pathlib import Path

from PIL import Image

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "agenda_futebol.db"
ESCUDOS_DIR = BASE_DIR / "static" / "escudos"
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


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_conn()
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
            endereco TEXT
        );

        CREATE TABLE IF NOT EXISTS jogos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL UNIQUE,
            hora TEXT,
            adversario_id INTEGER NOT NULL REFERENCES times(id),
            mandante TEXT NOT NULL DEFAULT 'casa',
            local TEXT,
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
            perfil TEXT NOT NULL DEFAULT 'visualizacao'
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
    conn.commit()

    colunas_jogos = {row["name"] for row in conn.execute("PRAGMA table_info(jogos)")}
    if "hora" not in colunas_jogos:
        conn.execute("ALTER TABLE jogos ADD COLUMN hora TEXT")
    if "mandante" not in colunas_jogos:
        conn.execute("ALTER TABLE jogos ADD COLUMN mandante TEXT NOT NULL DEFAULT 'casa'")
    conn.commit()

    existentes = {row["nome"] for row in conn.execute("SELECT nome FROM times")}
    for nome in TIMES_INICIAIS:
        if nome not in existentes:
            conn.execute(
                "INSERT INTO times (nome, is_fixo) VALUES (?, ?)",
                (nome, 1 if nome == TIME_FIXO else 0),
            )
    conn.commit()

    conn.execute(
        """
        UPDATE times
        SET cidade = COALESCE(cidade, ?), nome_campo = COALESCE(nome_campo, ?), endereco = COALESCE(endereco, ?)
        WHERE is_fixo = 1
        """,
        (TIME_FIXO_CIDADE, TIME_FIXO_CAMPO, TIME_FIXO_ENDERECO),
    )
    conn.commit()

    time_fixo_row = conn.execute("SELECT id, escudo FROM times WHERE is_fixo = 1").fetchone()
    if time_fixo_row and not time_fixo_row["escudo"] and BRAND_ESCUDO_OFICIAL.exists():
        ESCUDOS_DIR.mkdir(parents=True, exist_ok=True)
        nome_arquivo = f"time_{time_fixo_row['id']}.png"
        shutil.copyfile(BRAND_ESCUDO_OFICIAL, ESCUDOS_DIR / nome_arquivo)
        conn.execute("UPDATE times SET escudo = ? WHERE id = ?", (nome_arquivo, time_fixo_row["id"]))
        conn.commit()
        gerar_icones_pwa(ESCUDOS_DIR / nome_arquivo)

    ids_times = {row["nome"]: row["id"] for row in conn.execute("SELECT id, nome FROM times")}
    for data, nome_adversario, mandante, local, observacao in JOGOS_INICIAIS:
        adversario_id = ids_times.get(nome_adversario)
        if not adversario_id:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO jogos (data, hora, adversario_id, mandante, local, status, observacao)
            VALUES (?, ?, ?, ?, ?, 'pendente', ?)
            """,
            (data, HORA_PADRAO, adversario_id, mandante, local, observacao),
        )
    conn.commit()

    conn.execute("UPDATE jogos SET hora = ? WHERE hora IS NULL OR hora = ''", (HORA_PADRAO,))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Banco inicializado em {DB_PATH}")
