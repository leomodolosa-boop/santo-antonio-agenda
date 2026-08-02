import calendar
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from db import TIME_FIXO, get_conn, init_db

app = Flask(__name__)

ESCUDOS_DIR = Path(__file__).parent / "static" / "escudos"
ESCUDOS_DIR.mkdir(parents=True, exist_ok=True)
EXTENSOES_PERMITIDAS = {"png"}

init_db()


def salvar_escudo(arquivo, time_id):
    if not arquivo or not arquivo.filename:
        return None
    ext = arquivo.filename.rsplit(".", 1)[-1].lower() if "." in arquivo.filename else ""
    if ext not in EXTENSOES_PERMITIDAS:
        return None
    nome_arquivo = secure_filename(f"time_{time_id}.png")
    arquivo.save(ESCUDOS_DIR / nome_arquivo)
    return nome_arquivo


@app.context_processor
def injetar_escudo_fixo():
    conn = get_conn()
    row = conn.execute("SELECT escudo FROM times WHERE is_fixo = 1").fetchone()
    conn.close()
    return {"escudo_fixo": row["escudo"] if row else None}

MESES_PT = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


def sabados_do_mes(ano, mes):
    cal = calendar.Calendar()
    return [
        d for d in cal.itermonthdates(ano, mes)
        if d.month == mes and d.weekday() == 5  # sábado
    ]


def proximo_sabado_sem_jogo():
    conn = get_conn()
    hoje = date.today()
    dias_ate_sabado = (5 - hoje.weekday()) % 7
    candidato = hoje + timedelta(days=dias_ate_sabado)
    while True:
        jogo = conn.execute(
            "SELECT id FROM jogos WHERE data = ?", (candidato.isoformat(),)
        ).fetchone()
        if not jogo:
            conn.close()
            return candidato
        candidato += timedelta(days=7)


@app.route("/")
def index():
    hoje = date.today()
    return redirect(url_for("calendario", ano=hoje.year, mes=hoje.month))


@app.route("/calendario/<int:ano>/<int:mes>")
def calendario(ano, mes):
    conn = get_conn()
    sabados = sabados_do_mes(ano, mes)

    jogos_por_data = {}
    for d in sabados:
        row = conn.execute(
            """
            SELECT jogos.*, times.nome AS adversario_nome, times.escudo AS adversario_escudo
            FROM jogos JOIN times ON times.id = jogos.adversario_id
            WHERE jogos.data = ?
            """,
            (d.isoformat(),),
        ).fetchone()
        if row:
            jogos_por_data[d.isoformat()] = row
    conn.close()

    prev_mes = mes - 1 if mes > 1 else 12
    prev_ano = ano if mes > 1 else ano - 1
    next_mes = mes + 1 if mes < 12 else 1
    next_ano = ano if mes < 12 else ano + 1

    return render_template(
        "calendario.html",
        ano=ano,
        mes=mes,
        nome_mes=MESES_PT[mes],
        sabados=sabados,
        jogos_por_data=jogos_por_data,
        prev_ano=prev_ano,
        prev_mes=prev_mes,
        next_ano=next_ano,
        next_mes=next_mes,
        hoje=date.today().isoformat(),
        time_fixo=TIME_FIXO,
        proximo_sabado_livre=proximo_sabado_sem_jogo().isoformat(),
    )


@app.route("/jogo/novo", methods=["GET", "POST"])
def jogo_novo():
    conn = get_conn()
    data_str = request.values.get("data") or proximo_sabado_sem_jogo().isoformat()

    if request.method == "POST":
        adversario_id = request.form["adversario_id"]
        hora = request.form.get("hora", "").strip()
        local = request.form.get("local", "").strip()
        observacao = request.form.get("observacao", "").strip()
        conn.execute(
            """
            INSERT INTO jogos (data, hora, adversario_id, local, status, observacao)
            VALUES (?, ?, ?, ?, 'pendente', ?)
            """,
            (request.form["data"], hora, adversario_id, local, observacao),
        )
        conn.commit()
        d = date.fromisoformat(request.form["data"])
        conn.close()
        return redirect(url_for("calendario", ano=d.year, mes=d.month))

    adversarios = conn.execute(
        "SELECT * FROM times WHERE is_fixo = 0 ORDER BY nome"
    ).fetchall()
    conn.close()
    return render_template(
        "jogo_form.html",
        jogo=None,
        data_str=data_str,
        adversarios=adversarios,
        time_fixo=TIME_FIXO,
    )


@app.route("/jogo/<int:jogo_id>/editar", methods=["GET", "POST"])
def jogo_editar(jogo_id):
    conn = get_conn()

    if request.method == "POST":
        if "excluir" in request.form:
            jogo = conn.execute("SELECT data FROM jogos WHERE id = ?", (jogo_id,)).fetchone()
            conn.execute("DELETE FROM jogos WHERE id = ?", (jogo_id,))
            conn.commit()
            d = date.fromisoformat(jogo["data"])
            conn.close()
            return redirect(url_for("calendario", ano=d.year, mes=d.month))

        adversario_id = request.form["adversario_id"]
        nova_data = request.form["data"]
        hora = request.form.get("hora", "").strip()
        local = request.form.get("local", "").strip()
        observacao = request.form.get("observacao", "").strip()
        status = request.form.get("status", "confirmado")
        placar_santo = request.form.get("placar_santo") or None
        placar_adversario = request.form.get("placar_adversario") or None

        erro = None
        if date.fromisoformat(nova_data).weekday() != 5:
            erro = "A data precisa ser um sábado."
        else:
            try:
                conn.execute(
                    """
                    UPDATE jogos
                    SET adversario_id = ?, data = ?, hora = ?, local = ?, observacao = ?, status = ?,
                        placar_santo = ?, placar_adversario = ?
                    WHERE id = ?
                    """,
                    (adversario_id, nova_data, hora, local, observacao, status,
                     placar_santo, placar_adversario, jogo_id),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                erro = "Já existe um jogo agendado para essa data."

        if erro:
            adversarios = conn.execute(
                "SELECT * FROM times WHERE is_fixo = 0 ORDER BY nome"
            ).fetchall()
            jogo_atual = dict(request.form)
            jogo_atual["id"] = jogo_id
            jogo_atual["adversario_id"] = int(adversario_id)
            conn.close()
            return render_template(
                "jogo_form.html",
                jogo=jogo_atual,
                data_str=nova_data,
                adversarios=adversarios,
                time_fixo=TIME_FIXO,
                erro=erro,
            )

        d = date.fromisoformat(nova_data)
        conn.close()
        return redirect(url_for("calendario", ano=d.year, mes=d.month))

    jogo = conn.execute("SELECT * FROM jogos WHERE id = ?", (jogo_id,)).fetchone()
    adversarios = conn.execute(
        "SELECT * FROM times WHERE is_fixo = 0 ORDER BY nome"
    ).fetchall()
    conn.close()
    return render_template(
        "jogo_form.html",
        jogo=jogo,
        data_str=jogo["data"],
        adversarios=adversarios,
        time_fixo=TIME_FIXO,
    )


@app.route("/jogo/<int:jogo_id>/confirmar", methods=["POST"])
def jogo_confirmar(jogo_id):
    conn = get_conn()
    jogo = conn.execute("SELECT data FROM jogos WHERE id = ?", (jogo_id,)).fetchone()
    conn.execute("UPDATE jogos SET status = 'confirmado' WHERE id = ?", (jogo_id,))
    conn.commit()
    conn.close()
    d = date.fromisoformat(jogo["data"])
    return redirect(url_for("calendario", ano=d.year, mes=d.month))


@app.route("/jogo/<int:jogo_id>/cancelar", methods=["POST"])
def jogo_cancelar(jogo_id):
    conn = get_conn()
    jogo = conn.execute("SELECT data FROM jogos WHERE id = ?", (jogo_id,)).fetchone()
    conn.execute("UPDATE jogos SET status = 'cancelado' WHERE id = ?", (jogo_id,))
    conn.commit()
    conn.close()
    d = date.fromisoformat(jogo["data"])
    return redirect(url_for("calendario", ano=d.year, mes=d.month))


@app.route("/jogo/<int:jogo_id>/reabrir", methods=["POST"])
def jogo_reabrir(jogo_id):
    conn = get_conn()
    jogo = conn.execute("SELECT data FROM jogos WHERE id = ?", (jogo_id,)).fetchone()
    conn.execute("UPDATE jogos SET status = 'pendente' WHERE id = ?", (jogo_id,))
    conn.commit()
    conn.close()
    d = date.fromisoformat(jogo["data"])
    return redirect(url_for("calendario", ano=d.year, mes=d.month))


@app.route("/historico")
def historico():
    conn = get_conn()
    jogos = conn.execute(
        """
        SELECT jogos.*, times.nome AS adversario_nome, times.escudo AS adversario_escudo
        FROM jogos JOIN times ON times.id = jogos.adversario_id
        WHERE jogos.data < ?
        ORDER BY jogos.data DESC
        """,
        (date.today().isoformat(),),
    ).fetchall()
    conn.close()
    return render_template("historico.html", jogos=jogos, time_fixo=TIME_FIXO)


@app.route("/times", methods=["GET", "POST"])
def times():
    conn = get_conn()
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        cidade = request.form.get("cidade", "").strip()
        contato = request.form.get("contato", "").strip()
        nome_campo = request.form.get("nome_campo", "").strip()
        endereco = request.form.get("endereco", "").strip()
        if nome:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO times (nome, cidade, contato, nome_campo, endereco)
                VALUES (?, ?, ?, ?, ?)
                """,
                (nome, cidade, contato, nome_campo, endereco),
            )
            conn.commit()
            if cursor.rowcount:
                novo_id = cursor.lastrowid
                escudo = salvar_escudo(request.files.get("escudo"), novo_id)
                if escudo:
                    conn.execute("UPDATE times SET escudo = ? WHERE id = ?", (escudo, novo_id))
                    conn.commit()

    lista = conn.execute("SELECT * FROM times ORDER BY is_fixo DESC, nome").fetchall()
    conn.close()
    return render_template("times.html", times=lista)


@app.route("/times/<int:time_id>/editar", methods=["GET", "POST"])
def times_editar(time_id):
    conn = get_conn()

    if request.method == "POST":
        cidade = request.form.get("cidade", "").strip()
        contato = request.form.get("contato", "").strip()
        nome_campo = request.form.get("nome_campo", "").strip()
        endereco = request.form.get("endereco", "").strip()
        conn.execute(
            """
            UPDATE times SET cidade = ?, contato = ?, nome_campo = ?, endereco = ?
            WHERE id = ?
            """,
            (cidade, contato, nome_campo, endereco, time_id),
        )
        conn.commit()
        escudo = salvar_escudo(request.files.get("escudo"), time_id)
        if escudo:
            conn.execute("UPDATE times SET escudo = ? WHERE id = ?", (escudo, time_id))
            conn.commit()
        conn.close()
        return redirect(url_for("times"))

    time_row = conn.execute("SELECT * FROM times WHERE id = ?", (time_id,)).fetchone()
    conn.close()
    return render_template("time_form.html", time=time_row)


@app.route("/times/<int:time_id>/excluir", methods=["POST"])
def times_excluir(time_id):
    conn = get_conn()
    time_row = conn.execute("SELECT is_fixo FROM times WHERE id = ?", (time_id,)).fetchone()
    if time_row and not time_row["is_fixo"]:
        em_uso = conn.execute(
            "SELECT 1 FROM jogos WHERE adversario_id = ? LIMIT 1", (time_id,)
        ).fetchone()
        if not em_uso:
            conn.execute("DELETE FROM times WHERE id = ?", (time_id,))
            conn.commit()
    conn.close()
    return redirect(url_for("times"))


if __name__ == "__main__":
    app.run(debug=True)
