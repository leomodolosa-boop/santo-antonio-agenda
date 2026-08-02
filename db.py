import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "agenda_futebol.db"

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

# (data, nome_adversario, local, observacao) — agenda pré-definida da temporada 2026.
# status sempre nasce 'pendente'; INSERT OR IGNORE preserva edições já feitas pelo usuário.
JOGOS_INICIAIS = [
    ("2026-08-01", "São Roque", LOCAL_CASA, ""),
    ("2026-08-08", "Amigos do Esporte", LOCAL_CASA, ""),
    ("2026-08-15", "São José", "", ""),
    ("2026-08-22", "Pizzol", "", "Mandante a confirmar"),
    ("2026-08-29", "São João", "", ""),
    ("2026-09-05", "Fazenda Estado", LOCAL_CASA, ""),
    ("2026-09-12", "Perim FC - Garrafão", LOCAL_CASA, ""),
    ("2026-09-19", "Bacia", LOCAL_CASA, ""),
    ("2026-10-03", "União FC", "Santa Luzia", ""),
    ("2026-10-10", "Mata Fria", LOCAL_CASA, ""),
    ("2026-10-31", "Corumbá", LOCAL_CASA, ""),
    ("2026-11-07", "Amigos do Esporte", "", ""),
    ("2026-11-28", "São José", LOCAL_CASA, ""),
    ("2026-12-05", "Rancho Dantas", "", ""),
]


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
            local TEXT,
            status TEXT NOT NULL DEFAULT 'confirmado',
            placar_santo INTEGER,
            placar_adversario INTEGER,
            observacao TEXT
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

    ids_times = {row["nome"]: row["id"] for row in conn.execute("SELECT id, nome FROM times")}
    for data, nome_adversario, local, observacao in JOGOS_INICIAIS:
        adversario_id = ids_times.get(nome_adversario)
        if not adversario_id:
            continue
        conn.execute(
            """
            INSERT OR IGNORE INTO jogos (data, adversario_id, local, status, observacao)
            VALUES (?, ?, ?, 'pendente', ?)
            """,
            (data, adversario_id, local, observacao),
        )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Banco inicializado em {DB_PATH}")
