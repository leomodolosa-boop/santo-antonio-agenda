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
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Banco inicializado em {DB_PATH}")
