import calendar
import functools
import os
import re
import sqlite3
from datetime import date, datetime, time as hora_tipo, timedelta
from pathlib import Path

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from flask_wtf import CSRFProtect
from PIL import Image, ImageOps
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from db import (
    ErroIntegridade,
    TIME_FIXO,
    USANDO_POSTGRES,
    gerar_escudo_padrao,
    gerar_icones_pwa,
    get_conn,
    init_db,
    salvar_cor_escudo,
    salvar_escudo_blob,
    salvar_foto_jogador_blob,
)


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
csrf = CSRFProtect(app)

# Código secreto exigido para criar a conta master pela primeira vez.
# Defina SETUP_TOKEN no ambiente (Render → Environment) com um valor só seu.
SETUP_TOKEN = os.environ.get("SETUP_TOKEN", "trocar-este-codigo-no-render")

APP_VERSION = "3.6.0"

ESCUDOS_DIR = Path(__file__).parent / "static" / "escudos"
ESCUDOS_DIR.mkdir(parents=True, exist_ok=True)
JOGADORES_DIR = Path(__file__).parent / "static" / "jogadores"
JOGADORES_DIR.mkdir(parents=True, exist_ok=True)
EXTENSOES_PERMITIDAS = {"png", "jpg", "jpeg", "webp"}
POSICOES_JOGADOR = ["Goleiro", "Zagueiro", "Lateral", "Volante", "Meio-campo", "Atacante"]

init_db()


def get_db():
    """Uma única conexão por requisição — abrir uma nova por consulta é caro
    demais com o Postgres remoto (cada conexão custa uma rodada extra de
    handshake pela rede, e uma página chega a fazer 5-6 consultas)."""
    if "db" not in g:
        g.db = get_conn()
    return g.db


@app.teardown_appcontext
def fechar_db(exception=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def usuario_logado():
    if "usuario_id" not in session:
        return None
    if "usuario_atual" not in g:
        conn = get_db()
        g.usuario_atual = conn.execute(
            "SELECT id, nome, usuario, perfil FROM usuarios WHERE id = ?", (session["usuario_id"],)
        ).fetchone()
    return g.usuario_atual


def master_obrigatorio(funcao):
    @functools.wraps(funcao)
    def envolvida(*args, **kwargs):
        usuario = usuario_logado()
        if not usuario or usuario["perfil"] != "master":
            flash("Você precisa entrar como administrador para fazer isso.")
            return redirect(url_for("login", proximo=request.full_path))
        return funcao(*args, **kwargs)
    return envolvida


@app.template_filter("hex_para_rgb")
def hex_para_rgb(cor_hex):
    """'#1f6feb' -> '31,111,235', pra usar em rgba(var(--x), alfa) no CSS."""
    if not cor_hex:
        return None
    h = cor_hex.lstrip("#")
    return ",".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


@app.context_processor
def injetar_contexto_global():
    conn = get_db()
    usuario = usuario_logado()
    row_escudo = conn.execute(
        "SELECT escudo, escudo_cor, campo_mapa_url FROM times WHERE is_fixo = 1"
    ).fetchone()
    return {
        "usuario_logado": usuario,
        "eh_master": bool(usuario and usuario["perfil"] == "master"),
        "escudo_fixo": row_escudo["escudo"] if row_escudo else None,
        "escudo_fixo_cor": row_escudo["escudo_cor"] if row_escudo else None,
        "campo_mapa_url_fixo": row_escudo["campo_mapa_url"] if row_escudo else None,
        "app_version": APP_VERSION,
    }


@app.route("/configurar-master", methods=["GET", "POST"])
def configurar_master():
    conn = get_db()
    if conn.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone():
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
            session.clear()
            session.permanent = True
            session["usuario_id"] = usuario_criado["id"]
            return redirect(url_for("index"))

    return render_template("configurar_master.html", erro=erro)


@app.route("/login", methods=["GET", "POST"])
def login():
    conn = get_db()
    if not conn.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone():
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
            destino = request.form.get("proximo") or url_for("index")
            return redirect(destino)
        erro = "Usuário ou senha inválidos."

    return render_template("login.html", erro=erro, proximo=request.args.get("proximo", ""))


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/usuarios", methods=["GET", "POST"])
@master_obrigatorio
def usuarios():
    conn = get_db()
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
            except (sqlite3.IntegrityError, ErroIntegridade):
                erro = "Já existe um usuário com esse login."

    lista = conn.execute("SELECT * FROM usuarios ORDER BY nome").fetchall()
    return render_template("usuarios.html", usuarios=lista, erro=erro)


@app.route("/usuarios/<int:usuario_id>/excluir", methods=["POST"])
@master_obrigatorio
def usuarios_excluir(usuario_id):
    if usuario_id == session.get("usuario_id"):
        flash("Você não pode excluir seu próprio usuário enquanto estiver logado com ele.")
        return redirect(url_for("usuarios"))
    conn = get_db()
    conn.execute("DELETE FROM usuarios WHERE id = ?", (usuario_id,))
    conn.commit()
    return redirect(url_for("usuarios"))


def _abrir_imagem_upload(arquivo):
    if not arquivo or not arquivo.filename:
        return None
    ext = arquivo.filename.rsplit(".", 1)[-1].lower() if "." in arquivo.filename else ""
    if ext not in EXTENSOES_PERMITIDAS:
        flash("Formato de imagem não suportado. Envie um arquivo PNG, JPG ou WEBP.")
        return None
    try:
        return ImageOps.exif_transpose(Image.open(arquivo.stream)).convert("RGBA")
    except Exception:
        flash("Não foi possível abrir essa imagem. Tente outro arquivo.")
        return None


def salvar_escudo(arquivo, time_id, conn):
    imagem = _abrir_imagem_upload(arquivo)
    if imagem is None:
        return None
    nome_arquivo = secure_filename(f"time_{time_id}.png")
    caminho = ESCUDOS_DIR / nome_arquivo
    imagem.save(caminho, "PNG")
    salvar_escudo_blob(conn, time_id, caminho)
    salvar_cor_escudo(conn, time_id, caminho)
    conn.commit()
    return nome_arquivo


def salvar_foto_jogador(arquivo, jogador_id, conn):
    imagem = _abrir_imagem_upload(arquivo)
    if imagem is None:
        return None
    nome_arquivo = secure_filename(f"jogador_{jogador_id}.png")
    caminho = JOGADORES_DIR / nome_arquivo
    imagem.save(caminho, "PNG")
    salvar_foto_jogador_blob(conn, jogador_id, caminho)
    conn.commit()
    return nome_arquivo

MESES_PT = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

# Depois desse horário no dia do jogo, ele passa a contar como "encerrado"
# (aguardando resultado) mesmo sem virar o dia — calculado na hora, sem
# depender de nenhum agendador/cron rodando no horário certo.
HORA_ENCERRAMENTO_JOGO = hora_tipo(18, 30)


def jogo_aguardando_resultado(data_jogo_str, status, resultado_lancado):
    if status == "cancelado" or resultado_lancado:
        return False
    data_jogo = date.fromisoformat(data_jogo_str)
    agora = datetime.now()
    if data_jogo < agora.date():
        return True
    return data_jogo == agora.date() and agora.time() >= HORA_ENCERRAMENTO_JOGO


app.jinja_env.globals["jogo_aguardando_resultado"] = jogo_aguardando_resultado


def jogo_ao_vivo(data_jogo_str, hora_str, status, resultado_lancado):
    """Estimativa simples: considera "ao vivo" da hora marcada até 2h depois,
    já que não guardamos horário de término da partida."""
    if status != "confirmado" or resultado_lancado or not hora_str:
        return False
    data_jogo = date.fromisoformat(data_jogo_str)
    agora = datetime.now()
    if data_jogo != agora.date():
        return False
    h, m = hora_str.split(":")
    inicio = datetime.combine(data_jogo, hora_tipo(int(h), int(m)))
    fim = inicio + timedelta(hours=2)
    return inicio <= agora <= fim


app.jinja_env.globals["jogo_ao_vivo"] = jogo_ao_vivo


def sabados_do_mes(ano, mes):
    cal = calendar.Calendar()
    return [
        d for d in cal.itermonthdates(ano, mes)
        if d.month == mes and d.weekday() == 5  # sábado
    ]


def buscar_proximo_jogo():
    conn = get_db()
    agora = datetime.now()
    # Depois das 18:30, o jogo de hoje já é considerado encerrado e some
    # do "próximo jogo" — passa a mostrar o de fato próximo.
    if agora.time() >= HORA_ENCERRAMENTO_JOGO:
        data_minima = (agora.date() + timedelta(days=1)).isoformat()
    else:
        data_minima = agora.date().isoformat()
    jogo = conn.execute(
        """
        SELECT jogos.*, times.nome AS adversario_nome, times.escudo AS adversario_escudo, times.escudo_cor AS adversario_cor
        FROM jogos JOIN times ON times.id = jogos.adversario_id
        WHERE jogos.data >= ? AND jogos.status != 'cancelado'
        ORDER BY jogos.data ASC
        LIMIT 1
        """,
        (data_minima,),
    ).fetchone()
    return jogo


def calcular_aproveitamento():
    conn = get_db()
    linhas = conn.execute(
        """
        SELECT placar_santo, placar_adversario FROM jogos
        WHERE placar_santo IS NOT NULL AND placar_adversario IS NOT NULL
        """
    ).fetchall()

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
    conn = get_db()
    hoje = date.today()
    dias_ate_sabado = (5 - hoje.weekday()) % 7
    candidato = hoje + timedelta(days=dias_ate_sabado)
    # Uma única consulta trazendo todas as datas futuras já ocupadas, em vez
    # de uma consulta por semana até achar uma livre.
    datas_ocupadas = {
        row["data"] for row in conn.execute(
            "SELECT data FROM jogos WHERE data >= ?", (candidato.isoformat(),)
        ).fetchall()
    }
    while candidato.isoformat() in datas_ocupadas:
        candidato += timedelta(days=7)
    return candidato


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
    conn = get_db()
    sabados = sabados_do_mes(ano, mes)

    # Uma única consulta pra todos os sábados do mês, em vez de uma por
    # sábado — cada ida-e-volta ao Postgres remoto custa ~200-300ms.
    jogos_por_data = {}
    if sabados:
        marcadores = ", ".join(["?"] * len(sabados))
        linhas = conn.execute(
            f"""
            SELECT jogos.*, times.nome AS adversario_nome, times.escudo AS adversario_escudo, times.escudo_cor AS adversario_cor
            FROM jogos JOIN times ON times.id = jogos.adversario_id
            WHERE jogos.data IN ({marcadores})
            """,
            tuple(d.isoformat() for d in sabados),
        ).fetchall()
        jogos_por_data = {linha["data"]: linha for linha in linhas}

    jogos_com_resultado = [
        linha["id"] for linha in jogos_por_data.values() if linha["placar_santo"] is not None
    ]
    artilheiros_por_jogo = {}
    if jogos_com_resultado:
        marcadores_gols = ", ".join(["?"] * len(jogos_com_resultado))
        linhas_gols = conn.execute(
            f"""
            SELECT gols.jogo_id, gols.quantidade, jogadores.nome_completo, jogadores.apelido
            FROM gols JOIN jogadores ON jogadores.id = gols.jogador_id
            WHERE gols.jogo_id IN ({marcadores_gols})
            ORDER BY gols.quantidade DESC
            """,
            tuple(jogos_com_resultado),
        ).fetchall()
        for linha in linhas_gols:
            artilheiros_por_jogo.setdefault(linha["jogo_id"], []).append(
                {"nome": linha["apelido"] or linha["nome_completo"], "quantidade": linha["quantidade"]}
            )

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
        artilheiros_por_jogo=artilheiros_por_jogo,
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
        ano_atual=date.today().year,
    )


@app.route("/jogo/novo", methods=["GET", "POST"])
@master_obrigatorio
def jogo_novo():
    conn = get_db()
    data_str = request.values.get("data") or proximo_sabado_sem_jogo().isoformat()

    if request.method == "POST":
        adversario_id = request.form.get("adversario_id")
        mandante = request.form.get("mandante", "casa")
        hora = request.form.get("hora", "").strip()
        local = request.form.get("local", "").strip()
        local_mapa_url = request.form.get("local_mapa_url", "").strip()
        observacao = request.form.get("observacao", "").strip()
        nova_data = request.form.get("data", "")

        erro = None
        if not adversario_id:
            erro = "Selecione o adversário."
        elif not nova_data or date.fromisoformat(nova_data).weekday() != 5:
            erro = "A data precisa ser um sábado."
        else:
            try:
                conn.execute(
                    """
                    INSERT INTO jogos (data, hora, adversario_id, mandante, local, local_mapa_url, status, observacao)
                    VALUES (?, ?, ?, ?, ?, ?, 'pendente', ?)
                    """,
                    (nova_data, hora, adversario_id, mandante, local, local_mapa_url or None, observacao),
                )
                conn.commit()
            except (sqlite3.IntegrityError, ErroIntegridade):
                erro = "Já existe um jogo agendado para essa data."

        if not erro:
            d = date.fromisoformat(nova_data)
            return redirect(url_for("calendario", ano=d.year, mes=d.month))

        adversarios = conn.execute(
            "SELECT * FROM times WHERE is_fixo = 0 ORDER BY nome"
        ).fetchall()
        template = "jogo_form_conteudo.html" if request.form.get("modal") == "1" else "jogo_form.html"
        return render_template(
            template,
            jogo=None,
            data_str=nova_data or data_str,
            adversarios=adversarios,
            time_fixo=TIME_FIXO,
            erro=erro,
        )

    adversarios = conn.execute(
        "SELECT * FROM times WHERE is_fixo = 0 ORDER BY nome"
    ).fetchall()
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
    conn = get_db()

    jogo_existente = conn.execute("SELECT * FROM jogos WHERE id = ?", (jogo_id,)).fetchone()
    if not jogo_existente:
        abort(404)

    if request.method == "POST":
        if "excluir" in request.form:
            conn.execute("DELETE FROM jogos WHERE id = ?", (jogo_id,))
            conn.commit()
            d = date.fromisoformat(jogo_existente["data"])
            return redirect(url_for("calendario", ano=d.year, mes=d.month))

        adversario_id = request.form["adversario_id"]
        mandante = request.form.get("mandante", "casa")
        nova_data = request.form["data"]
        hora = request.form.get("hora", "").strip()
        local = request.form.get("local", "").strip()
        local_mapa_url = request.form.get("local_mapa_url", "").strip()
        observacao = request.form.get("observacao", "").strip()
        status = request.form.get("status", "confirmado")
        placar_santo = request.form.get("placar_santo") or None
        placar_adversario = request.form.get("placar_adversario") or None
        resultado_lancado = 1 if (placar_santo is not None and placar_adversario is not None) else 0

        erro = None
        if date.fromisoformat(nova_data).weekday() != 5:
            erro = "A data precisa ser um sábado."
        else:
            try:
                conn.execute(
                    """
                    UPDATE jogos
                    SET adversario_id = ?, mandante = ?, data = ?, hora = ?, local = ?, local_mapa_url = ?,
                        observacao = ?, status = ?, placar_santo = ?, placar_adversario = ?, resultado_lancado = ?
                    WHERE id = ?
                    """,
                    (adversario_id, mandante, nova_data, hora, local, local_mapa_url or None, observacao, status,
                     placar_santo, placar_adversario, resultado_lancado, jogo_id),
                )
                # Substitui os artilheiros do jogo por completo — mais simples
                # e seguro do que tentar casar linhas antigas com as novas.
                conn.execute("DELETE FROM gols WHERE jogo_id = ?", (jogo_id,))
                jogadores_gol = request.form.getlist("gol_jogador")
                quantidades_gol = request.form.getlist("gol_qtd")
                for jogador_id_str, quantidade_str in zip(jogadores_gol, quantidades_gol):
                    if not jogador_id_str or not quantidade_str:
                        continue
                    quantidade = int(quantidade_str)
                    if quantidade > 0:
                        conn.execute(
                            "INSERT INTO gols (jogo_id, jogador_id, quantidade) VALUES (?, ?, ?)",
                            (jogo_id, int(jogador_id_str), quantidade),
                        )
                conn.commit()
            except (sqlite3.IntegrityError, ErroIntegridade):
                erro = "Já existe um jogo agendado para essa data."

        if erro:
            adversarios = conn.execute(
                "SELECT * FROM times WHERE is_fixo = 0 ORDER BY nome"
            ).fetchall()
            jogadores_ativos = conn.execute(
                "SELECT id, nome_completo, apelido FROM jogadores WHERE status = 'ativo' ORDER BY nome_completo"
            ).fetchall()
            jogo_atual = dict(request.form)
            jogo_atual["id"] = jogo_id
            jogo_atual["adversario_id"] = int(adversario_id)
            template = "jogo_form_conteudo.html" if request.form.get("modal") == "1" else "jogo_form.html"
            return render_template(
                template,
                jogo=jogo_atual,
                data_str=nova_data,
                adversarios=adversarios,
                jogadores_ativos=jogadores_ativos,
                artilheiros=[],
                time_fixo=TIME_FIXO,
                erro=erro,
            )

        d = date.fromisoformat(nova_data)
        return redirect(url_for("calendario", ano=d.year, mes=d.month))

    adversarios = conn.execute(
        "SELECT * FROM times WHERE is_fixo = 0 ORDER BY nome"
    ).fetchall()
    jogadores_ativos = conn.execute(
        "SELECT id, nome_completo, apelido FROM jogadores WHERE status = 'ativo' ORDER BY nome_completo"
    ).fetchall()
    artilheiros = conn.execute(
        "SELECT jogador_id, quantidade FROM gols WHERE jogo_id = ?", (jogo_id,)
    ).fetchall()
    template = "jogo_form_conteudo.html" if request.args.get("modal") == "1" else "jogo_form.html"
    return render_template(
        template,
        jogo=jogo_existente,
        data_str=jogo_existente["data"],
        adversarios=adversarios,
        jogadores_ativos=jogadores_ativos,
        artilheiros=artilheiros,
        time_fixo=TIME_FIXO,
    )


def _mudar_status_jogo(jogo_id, novo_status):
    conn = get_db()
    jogo = conn.execute("SELECT data FROM jogos WHERE id = ?", (jogo_id,)).fetchone()
    if not jogo:
        abort(404)
    conn.execute("UPDATE jogos SET status = ? WHERE id = ?", (novo_status, jogo_id))
    conn.commit()
    d = date.fromisoformat(jogo["data"])
    return redirect(url_for("calendario", ano=d.year, mes=d.month))


@app.route("/jogo/<int:jogo_id>/confirmar", methods=["POST"])
@master_obrigatorio
def jogo_confirmar(jogo_id):
    return _mudar_status_jogo(jogo_id, "confirmado")


@app.route("/jogo/<int:jogo_id>/cancelar", methods=["POST"])
@master_obrigatorio
def jogo_cancelar(jogo_id):
    return _mudar_status_jogo(jogo_id, "cancelado")


@app.route("/jogo/<int:jogo_id>/reabrir", methods=["POST"])
@master_obrigatorio
def jogo_reabrir(jogo_id):
    return _mudar_status_jogo(jogo_id, "pendente")


@app.route("/historico")
def historico():
    conn = get_db()
    agora = datetime.now()
    # Depois das 18:30 de sábado, o jogo do dia já entra no histórico
    # (aguardando resultado) sem precisar esperar virar o dia.
    if agora.time() >= HORA_ENCERRAMENTO_JOGO:
        data_limite = agora.date().isoformat()
        operador = "<="
    else:
        data_limite = agora.date().isoformat()
        operador = "<"
    jogos = conn.execute(
        f"""
        SELECT jogos.*, times.nome AS adversario_nome, times.escudo AS adversario_escudo, times.escudo_cor AS adversario_cor
        FROM jogos JOIN times ON times.id = jogos.adversario_id
        WHERE jogos.data {operador} ?
        ORDER BY jogos.data DESC
        """,
        (data_limite,),
    ).fetchall()
    return render_template("historico.html", jogos=jogos, time_fixo=TIME_FIXO)


@app.route("/artilharia")
def artilharia():
    conn = get_db()
    ano_atual = date.today().year
    # Ranking só da temporada corrente — vira o ano, os gols do ano anterior
    # somem do ranking sozinhos (sem precisar apagar nada, é só o filtro de
    # data do jogo). O histórico de cada temporada continua acessível no
    # banco, só não entra na conta da temporada atual.
    ranking = conn.execute(
        """
        SELECT jogadores.id, jogadores.nome_completo, jogadores.apelido, jogadores.foto,
               COALESCE(SUM(gols.quantidade), 0) AS total_gols,
               COUNT(DISTINCT gols.jogo_id) AS jogos_marcou
        FROM jogadores
        JOIN gols ON gols.jogador_id = jogadores.id
        JOIN jogos ON jogos.id = gols.jogo_id
        WHERE jogadores.conta_estatisticas = 1 AND jogos.data LIKE ?
        GROUP BY jogadores.id, jogadores.nome_completo, jogadores.apelido, jogadores.foto
        ORDER BY total_gols DESC, jogadores.nome_completo ASC
        """,
        (f"{ano_atual}-%",),
    ).fetchall()
    top_artilheiros = [
        {
            "nome": row["apelido"] or row["nome_completo"],
            "gols": row["total_gols"],
            "jogos": row["jogos_marcou"],
            "foto": url_for("static", filename="jogadores/" + row["foto"]) if row["foto"] else "",
        }
        for row in ranking[:5]
    ]
    return render_template(
        "artilharia.html",
        ranking=ranking,
        time_fixo=TIME_FIXO,
        ano_atual=ano_atual,
        top_artilheiros=top_artilheiros,
    )


@app.route("/times", methods=["GET", "POST"])
def times():
    conn = get_db()
    if request.method == "POST":
        usuario = usuario_logado()
        if not usuario or usuario["perfil"] != "master":
            flash("Você precisa entrar como administrador para fazer isso.")
            return redirect(url_for("login", proximo=request.full_path))
        nome = request.form.get("nome", "").strip()
        cidade = request.form.get("cidade", "").strip()
        contato = request.form.get("contato", "").strip()
        nome_campo = request.form.get("nome_campo", "").strip()
        endereco = request.form.get("endereco", "").strip()
        if nome:
            novo_id = None
            if USANDO_POSTGRES:
                cursor = conn.execute(
                    """
                    INSERT INTO times (nome, cidade, contato, nome_campo, endereco)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (nome) DO NOTHING
                    RETURNING id
                    """,
                    (nome, cidade, contato, nome_campo, endereco),
                )
                conn.commit()
                row_id = cursor.fetchone()
                if row_id:
                    novo_id = row_id["id"]
            else:
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
            if novo_id:
                escudo = salvar_escudo(request.files.get("escudo"), novo_id, conn)
                if escudo:
                    conn.execute("UPDATE times SET escudo = ? WHERE id = ?", (escudo, novo_id))
                    conn.commit()

    lista = conn.execute("SELECT * FROM times ORDER BY is_fixo DESC, nome").fetchall()
    return render_template("times.html", times=lista)


@app.route("/times/<int:time_id>/editar", methods=["GET", "POST"])
@master_obrigatorio
def times_editar(time_id):
    conn = get_db()

    if not conn.execute("SELECT 1 FROM times WHERE id = ?", (time_id,)).fetchone():
        abort(404)

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        cidade = request.form.get("cidade", "").strip()
        contato = request.form.get("contato", "").strip()
        nome_campo = request.form.get("nome_campo", "").strip()
        endereco = request.form.get("endereco", "").strip()
        cep = request.form.get("cep", "").strip()
        campo_mapa_url = request.form.get("campo_mapa_url", "").strip()

        if not nome:
            flash("O nome do time não pode ficar em branco.")
            time_row = conn.execute("SELECT * FROM times WHERE id = ?", (time_id,)).fetchone()
            return render_template("time_form.html", time=time_row)

        try:
            conn.execute(
                """
                UPDATE times SET nome = ?, cidade = ?, contato = ?, nome_campo = ?, endereco = ?, cep = ?, campo_mapa_url = ?
                WHERE id = ?
                """,
                (nome, cidade, contato, nome_campo, endereco, cep or None, campo_mapa_url or None, time_id),
            )
            conn.commit()
        except (sqlite3.IntegrityError, ErroIntegridade):
            flash(f'Já existe um time chamado "{nome}".')
            time_row = conn.execute("SELECT * FROM times WHERE id = ?", (time_id,)).fetchone()
            return render_template("time_form.html", time=time_row)

        escudo = salvar_escudo(request.files.get("escudo"), time_id, conn)
        if escudo:
            conn.execute("UPDATE times SET escudo = ? WHERE id = ?", (escudo, time_id))
            conn.commit()
            time_row = conn.execute("SELECT is_fixo FROM times WHERE id = ?", (time_id,)).fetchone()
            if time_row and time_row["is_fixo"]:
                gerar_icones_pwa(ESCUDOS_DIR / escudo)
        return redirect(url_for("times"))

    time_row = conn.execute("SELECT * FROM times WHERE id = ?", (time_id,)).fetchone()
    return render_template("time_form.html", time=time_row)


@app.route("/times/<int:time_id>/excluir", methods=["POST"])
@master_obrigatorio
def times_excluir(time_id):
    conn = get_db()
    time_row = conn.execute("SELECT is_fixo, nome FROM times WHERE id = ?", (time_id,)).fetchone()
    if not time_row:
        abort(404)

    if time_row["is_fixo"]:
        flash("Não é possível excluir o time fixo.")
    else:
        em_uso = conn.execute(
            "SELECT 1 FROM jogos WHERE adversario_id = ? LIMIT 1", (time_id,)
        ).fetchone()
        if em_uso:
            flash(f'"{time_row["nome"]}" tem jogos cadastrados e não pode ser excluído.')
        else:
            conn.execute("DELETE FROM times WHERE id = ?", (time_id,))
            conn.commit()
    return redirect(url_for("times"))


@app.route("/jogadores", methods=["GET", "POST"])
def jogadores():
    conn = get_db()
    if request.method == "POST":
        usuario = usuario_logado()
        if not usuario or usuario["perfil"] != "master":
            flash("Você precisa entrar como administrador para fazer isso.")
            return redirect(url_for("login", proximo=request.full_path))
        nome_completo = request.form.get("nome_completo", "").strip()
        apelido = request.form.get("apelido", "").strip()
        posicao = request.form.get("posicao", "").strip()
        numero_camisa = request.form.get("numero_camisa", "").strip()
        if nome_completo:
            sql_insert = """
                INSERT INTO jogadores (nome_completo, apelido, posicao, numero_camisa, status, data_cadastro)
                VALUES (?, ?, ?, ?, 'ativo', ?)
            """
            parametros = (nome_completo, apelido or None, posicao or None, numero_camisa or None, date.today().isoformat())
            if USANDO_POSTGRES:
                cursor = conn.execute(sql_insert + " RETURNING id", parametros)
                conn.commit()
                novo_id = cursor.fetchone()["id"]
            else:
                cursor = conn.execute(sql_insert, parametros)
                conn.commit()
                novo_id = cursor.lastrowid
            foto = salvar_foto_jogador(request.files.get("foto"), novo_id, conn)
            if foto:
                conn.execute("UPDATE jogadores SET foto = ? WHERE id = ?", (foto, novo_id))
                conn.commit()

    lista = conn.execute("SELECT * FROM jogadores ORDER BY status ASC, nome_completo").fetchall()
    return render_template("jogadores.html", jogadores=lista, posicoes=POSICOES_JOGADOR)


@app.route("/jogadores/<int:jogador_id>/editar", methods=["GET", "POST"])
@master_obrigatorio
def jogadores_editar(jogador_id):
    conn = get_db()
    jogador_row = conn.execute("SELECT * FROM jogadores WHERE id = ?", (jogador_id,)).fetchone()
    if not jogador_row:
        abort(404)

    if request.method == "POST":
        nome_completo = request.form.get("nome_completo", "").strip()
        apelido = request.form.get("apelido", "").strip()
        posicao = request.form.get("posicao", "").strip()
        numero_camisa = request.form.get("numero_camisa", "").strip()
        status = request.form.get("status", "ativo")
        conn.execute(
            """
            UPDATE jogadores SET nome_completo = ?, apelido = ?, posicao = ?, numero_camisa = ?, status = ?
            WHERE id = ?
            """,
            (nome_completo, apelido or None, posicao or None, numero_camisa or None, status, jogador_id),
        )
        conn.commit()
        foto = salvar_foto_jogador(request.files.get("foto"), jogador_id, conn)
        if foto:
            conn.execute("UPDATE jogadores SET foto = ? WHERE id = ?", (foto, jogador_id))
            conn.commit()
        return redirect(url_for("jogadores"))

    return render_template("jogador_form.html", jogador=jogador_row, posicoes=POSICOES_JOGADOR)


@app.route("/jogadores/<int:jogador_id>/excluir", methods=["POST"])
@master_obrigatorio
def jogadores_excluir(jogador_id):
    conn = get_db()
    jogador_row = conn.execute("SELECT nome_completo FROM jogadores WHERE id = ?", (jogador_id,)).fetchone()
    if not jogador_row:
        abort(404)
    em_uso = conn.execute("SELECT 1 FROM gols WHERE jogador_id = ? LIMIT 1", (jogador_id,)).fetchone()
    if em_uso:
        flash(f'"{jogador_row["nome_completo"]}" tem gols registrados e não pode ser excluído — marque como inativo em vez disso.')
    else:
        conn.execute("DELETE FROM jogadores WHERE id = ?", (jogador_id,))
        conn.commit()
    return redirect(url_for("jogadores"))


@app.errorhandler(404)
def erro_404(e):
    return render_template(
        "erro.html",
        codigo=404,
        titulo="Página não encontrada",
        mensagem="O link que você seguiu não existe ou o jogo/time já foi removido.",
    ), 404


@app.errorhandler(500)
def erro_500(e):
    return render_template(
        "erro.html",
        codigo=500,
        titulo="Algo deu errado",
        mensagem="Tivemos um problema inesperado. Tente novamente em instantes.",
    ), 500


if __name__ == "__main__":
    app.run(debug=True)
