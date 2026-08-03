import calendar
import functools
import os
import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from db import TIME_FIXO, gerar_icones_pwa, get_conn, init_db


def validar_senha_forte(senha):
    if len(senha) < 8:
        return "A senha precisa ter pelo menos 8 caracteres."
    if not re.search(r"[A-Z]", senha):
        return "A senha precisa ter pelo menos uma letra maiúscula."
    if not re.search(r"[a-z]", senha):
        return "A senha precisa ter pelo menos uma letra minúscula."
    if not re.search(r"[0-9]", senha):
        return "A senha precisa ter pelo menos um número."
    if not re.search(r"[^A-Za-z0-9]", senha):
        return "A senha precisa ter pelo menos um símbolo (ex: @, #, !, %)."
    return None

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chave-local-de-desenvolvimento-trocar-em-producao")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=90)

# Código secreto exigido para criar a conta master pela primeira vez.
# Defina SETUP_TOKEN no ambiente (Render → Environment) com um valor só seu.
SETUP_TOKEN = os.environ.get("SETUP_TOKEN", "trocar-este-codigo-no-render")

ESCUDOS_DIR = Path(__file__).parent / "static" / "escudos"
ESCUDOS_DIR.mkdir(parents=True, exist_ok=True)
EXTENSOES_PERMITIDAS = {"png"}

init_db()


def usuario_logado():
    if "usuario_id" not in session:
        return None
    conn = get_conn()
    usuario = conn.execute(
        "SELECT id, nome, usuario, perfil FROM usuarios WHERE id = ?", (session["usuario_id"],)
    ).fetchone()
    conn.close()
    return usuario


def master_obrigatorio(funcao):
    @functools.wraps(funcao)
    def envolvida(*args, **kwargs):
        usuario = usuario_logado()
        if not usuario or usuario["perfil"] != "master":
            flash("Você precisa entrar como administrador para fazer isso.")
            return redirect(url_for("login", proximo=request.full_path))
        return funcao(*args, **kwargs)
    return envolvida


@app.context_processor
def injetar_usuario():
    conn = get_conn()
    existe_usuario = conn.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone()
    conn.close()
    usuario = usuario_logado()
    return {
        "usuario_logado": usuario,
        "eh_master": bool(usuario and usuario["perfil"] == "master"),
        "existe_usuario_master": bool(existe_usuario),
    }


@app.route("/configurar-master", methods=["GET", "POST"])
def configurar_master():
    conn = get_conn()
    if conn.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone():
        conn.close()
        return redirect(url_for("login"))

    erro = None
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        usuario_login = request.form.get("usuario", "").strip().lower()
        senha = request.form.get("senha", "")
        codigo = request.form.get("codigo", "").strip()
        if not nome or not usuario_login or not senha or not codigo:
            erro = "Preencha todos os campos."
        elif codigo != SETUP_TOKEN:
            erro = "Código de configuração incorreto."
        elif validar_senha_forte(senha):
            erro = validar_senha_forte(senha)
        else:
            conn.execute(
                "INSERT INTO usuarios (nome, usuario, senha_hash, perfil) VALUES (?, ?, ?, 'master')",
                (nome, usuario_login, generate_password_hash(senha)),
            )
            conn.commit()
            usuario_criado = conn.execute(
                "SELECT id FROM usuarios WHERE usuario = ?", (usuario_login,)
            ).fetchone()
            conn.close()
            session.clear()
            session.permanent = True
            session["usuario_id"] = usuario_criado["id"]
            return redirect(url_for("index"))

    conn.close()
    return render_template("configurar_master.html", erro=erro)


@app.route("/login", methods=["GET", "POST"])
def login():
    conn = get_conn()
    if not conn.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone():
        conn.close()
        return redirect(url_for("configurar_master"))

    erro = None
    if request.method == "POST":
        usuario_login = request.form.get("usuario", "").strip().lower()
        senha = request.form.get("senha", "")
        usuario_row = conn.execute(
            "SELECT * FROM usuarios WHERE usuario = ?", (usuario_login,)
        ).fetchone()
        if usuario_row and check_password_hash(usuario_row["senha_hash"], senha):
            session.clear()
            session.permanent = True
            session["usuario_id"] = usuario_row["id"]
            conn.close()
            destino = request.form.get("proximo") or url_for("index")
            return redirect(destino)
        erro = "Usuário ou senha inválidos."

    conn.close()
    return render_template("login.html", erro=erro, proximo=request.args.get("proximo", ""))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/usuarios", methods=["GET", "POST"])
@master_obrigatorio
def usuarios():
    conn = get_conn()
    erro = None
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip()
        usuario_login = request.form.get("usuario", "").strip().lower()
        senha = request.form.get("senha", "")

        if not nome or not usuario_login or not senha:
            erro = "Preencha nome, usuário e senha."
        elif validar_senha_forte(senha):
            erro = validar_senha_forte(senha)
        else:
            try:
                # Toda conta criada aqui recebe acesso completo (master),
                # igual ao do administrador que a criou.
                conn.execute(
                    "INSERT INTO usuarios (nome, email, usuario, senha_hash, perfil) VALUES (?, ?, ?, ?, 'master')",
                    (nome, email, usuario_login, generate_password_hash(senha)),
                )
                conn.commit()
            except sqlite3.IntegrityError:
                erro = "Já existe um usuário com esse login."

    lista = conn.execute("SELECT * FROM usuarios ORDER BY nome").fetchall()
    conn.close()
    return render_template("usuarios.html", usuarios=lista, erro=erro)


@app.route("/usuarios/<int:usuario_id>/excluir", methods=["POST"])
@master_obrigatorio
def usuarios_excluir(usuario_id):
    if usuario_id == session.get("usuario_id"):
        flash("Você não pode excluir seu próprio usuário enquanto estiver logado com ele.")
        return redirect(url_for("usuarios"))
    conn = get_conn()
    conn.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("usuarios"))


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


def buscar_proximo_jogo():
    conn = get_conn()
    hoje = date.today().isoformat()
    jogo = conn.execute(
        """
        SELECT jogos.*, times.nome AS adversario_nome, times.escudo AS adversario_escudo
        FROM jogos JOIN times ON times.id = jogos.adversario_id
        WHERE jogos.data >= ? AND jogos.status != 'cancelado'
        ORDER BY jogos.data ASC
        LIMIT 1
        """,
        (hoje,),
    ).fetchone()
    conn.close()
    return jogo


def calcular_aproveitamento():
    conn = get_conn()
    linhas = conn.execute(
        """
        SELECT placar_santo, placar_adversario FROM jogos
        WHERE placar_santo IS NOT NULL AND placar_adversario IS NOT NULL
        """
    ).fetchall()
    conn.close()

    vitorias = empates = derrotas = 0
    gols_pro = gols_contra = 0
    for linha in linhas:
        gols_pro += linha["placar_santo"]
        gols_contra += linha["placar_adversario"]
        if linha["placar_santo"] > linha["placar_adversario"]:
            vitorias += 1
        elif linha["placar_santo"] == linha["placar_adversario"]:
            empates += 1
        else:
            derrotas += 1

    jogos = vitorias + empates + derrotas
    pontos = vitorias * 3 + empates
    aproveitamento = round((pontos / (jogos * 3)) * 100) if jogos else 0
    return {
        "jogos": jogos,
        "vitorias": vitorias,
        "empates": empates,
        "derrotas": derrotas,
        "aproveitamento": aproveitamento,
        "gols_pro": gols_pro,
        "gols_contra": gols_contra,
        "saldo_gols": gols_pro - gols_contra,
    }


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


@app.route("/sw.js")
def service_worker():
    # Servido na raiz (não em /static/) para o escopo do service worker
    # cobrir o site inteiro, exigência para o app ser instalável.
    return app.send_static_file("sw.js")


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

    proximo_livre = proximo_sabado_sem_jogo()
    proximo_jogo = buscar_proximo_jogo()
    dias_para_proximo_jogo = None
    if proximo_jogo:
        dias_para_proximo_jogo = (date.fromisoformat(proximo_jogo["data"]) - date.today()).days

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
        proximo_sabado_livre=proximo_livre.isoformat(),
        proximo_sabado_livre_br=proximo_livre.strftime("%d/%m/%Y"),
        proximo_jogo=proximo_jogo,
        dias_para_proximo_jogo=dias_para_proximo_jogo,
        stats=calcular_aproveitamento(),
    )


@app.route("/jogo/novo", methods=["GET", "POST"])
@master_obrigatorio
def jogo_novo():
    conn = get_conn()
    data_str = request.values.get("data") or proximo_sabado_sem_jogo().isoformat()

    if request.method == "POST":
        adversario_id = request.form["adversario_id"]
        mandante = request.form.get("mandante", "casa")
        hora = request.form.get("hora", "").strip()
        local = request.form.get("local", "").strip()
        observacao = request.form.get("observacao", "").strip()
        conn.execute(
            """
            INSERT INTO jogos (data, hora, adversario_id, mandante, local, status, observacao)
            VALUES (?, ?, ?, ?, ?, 'pendente', ?)
            """,
            (request.form["data"], hora, adversario_id, mandante, local, observacao),
        )
        conn.commit()
        d = date.fromisoformat(request.form["data"])
        conn.close()
        return redirect(url_for("calendario", ano=d.year, mes=d.month))

    adversarios = conn.execute(
        "SELECT * FROM times WHERE is_fixo = 0 ORDER BY nome"
    ).fetchall()
    conn.close()
    template = "jogo_form_conteudo.html" if request.args.get("modal") == "1" else "jogo_form.html"
    return render_template(
        template,
        jogo=None,
        data_str=data_str,
        adversarios=adversarios,
        time_fixo=TIME_FIXO,
    )


@app.route("/jogo/<int:jogo_id>/editar", methods=["GET", "POST"])
@master_obrigatorio
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
        mandante = request.form.get("mandante", "casa")
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
                    SET adversario_id = ?, mandante = ?, data = ?, hora = ?, local = ?, observacao = ?, status = ?,
                        placar_santo = ?, placar_adversario = ?
                    WHERE id = ?
                    """,
                    (adversario_id, mandante, nova_data, hora, local, observacao, status,
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
            template = "jogo_form_conteudo.html" if request.form.get("modal") == "1" else "jogo_form.html"
            return render_template(
                template,
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
    template = "jogo_form_conteudo.html" if request.args.get("modal") == "1" else "jogo_form.html"
    return render_template(
        template,
        jogo=jogo,
        data_str=jogo["data"],
        adversarios=adversarios,
        time_fixo=TIME_FIXO,
    )


@app.route("/jogo/<int:jogo_id>/confirmar", methods=["POST"])
@master_obrigatorio
def jogo_confirmar(jogo_id):
    conn = get_conn()
    jogo = conn.execute("SELECT data FROM jogos WHERE id = ?", (jogo_id,)).fetchone()
    conn.execute("UPDATE jogos SET status = 'confirmado' WHERE id = ?", (jogo_id,))
    conn.commit()
    conn.close()
    d = date.fromisoformat(jogo["data"])
    return redirect(url_for("calendario", ano=d.year, mes=d.month))


@app.route("/jogo/<int:jogo_id>/cancelar", methods=["POST"])
@master_obrigatorio
def jogo_cancelar(jogo_id):
    conn = get_conn()
    jogo = conn.execute("SELECT data FROM jogos WHERE id = ?", (jogo_id,)).fetchone()
    conn.execute("UPDATE jogos SET status = 'cancelado' WHERE id = ?", (jogo_id,))
    conn.commit()
    conn.close()
    d = date.fromisoformat(jogo["data"])
    return redirect(url_for("calendario", ano=d.year, mes=d.month))


@app.route("/jogo/<int:jogo_id>/reabrir", methods=["POST"])
@master_obrigatorio
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
        usuario = usuario_logado()
        if not usuario or usuario["perfil"] != "master":
            conn.close()
            flash("Você precisa entrar como administrador para fazer isso.")
            return redirect(url_for("login", proximo=request.full_path))
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
@master_obrigatorio
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
            time_row = conn.execute("SELECT is_fixo FROM times WHERE id = ?", (time_id,)).fetchone()
            if time_row and time_row["is_fixo"]:
                gerar_icones_pwa(ESCUDOS_DIR / escudo)
        conn.close()
        return redirect(url_for("times"))

    time_row = conn.execute("SELECT * FROM times WHERE id = ?", (time_id,)).fetchone()
    conn.close()
    return render_template("time_form.html", time=time_row)


@app.route("/times/<int:time_id>/excluir", methods=["POST"])
@master_obrigatorio
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
