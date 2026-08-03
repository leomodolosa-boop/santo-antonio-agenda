import math
import shutil
import sqlite3
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

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
    tamanho = 400
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

    ESCUDOS_DIR.mkdir(parents=True, exist_ok=True)
    sem_escudo = conn.execute(
        "SELECT id, nome FROM times WHERE is_fixo = 0 AND escudo IS NULL ORDER BY id"
    ).fetchall()
    for time_row in sem_escudo:
        nome_arquivo = f"time_{time_row['id']}.png"
        gerar_escudo_padrao(time_row["nome"], time_row["id"], ESCUDOS_DIR / nome_arquivo)
        conn.execute("UPDATE times SET escudo = ? WHERE id = ?", (nome_arquivo, time_row["id"]))
    conn.commit()

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
