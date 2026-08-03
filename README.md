# Agenda Santo Antônio do Oriente

App de agenda de jogos de futebol amador (Flask + SQLite).

## Rodar localmente

```bash
pip install -r requirements.txt
python app.py
```

Acesse `http://localhost:5000`.

## Deploy no Render

Este repositório já inclui `render.yaml`. No Render, use **New +  Blueprint**
e aponte para este repositório — ele detecta a configuração automaticamente.

> **Atenção:** no plano gratuito do Render o disco não é persistente entre
> deploys — sem um banco externo (veja abaixo), os dados e escudos são
> apagados a cada atualização.

## Banco de dados persistente (recomendado)

Por padrão o app usa um arquivo SQLite local, que some a cada redeploy no
plano gratuito do Render. Para os dados sobreviverem, defina a variável de
ambiente `DATABASE_URL` (Render → Settings → Environment) com a connection
string de um Postgres gratuito (ex: [Neon](https://neon.tech) ou
[Supabase](https://supabase.com), usando o "Session pooler" caso o host de
conexão direta use IPv6). Com `DATABASE_URL` definida, o app passa a usar
Postgres automaticamente — inclusive guardando os escudos dentro do próprio
banco, então nem as imagens se perdem em um redeploy. Sem essa variável, o
app continua funcionando normalmente com SQLite local (bom para rodar na
sua máquina).

## Login e permissões

O calendário, histórico e lista de times são públicos (qualquer um com o link
vê). Agendar, editar, confirmar/cancelar jogos e gerenciar times/usuários
exige login com perfil **master**.

No primeiro acesso (quando ainda não existe nenhum usuário), o app leva
automaticamente para a criação da conta master. Sessões duram 90 dias.

Defina a variável de ambiente `SECRET_KEY` no Render (Settings → Environment)
com um valor aleatório e fixo — sem isso, o app usa uma chave padrão de
desenvolvimento, e qualquer redeploy pode invalidar as sessões já logadas.
