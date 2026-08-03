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
> deploys. Para não perder os dados dos times e jogos cadastrados, considere
> um disco pago (Render Disks) ou faça backup periódico do arquivo
> `agenda_futebol.db`.

## Login e permissões

O calendário, histórico e lista de times são públicos (qualquer um com o link
vê). Agendar, editar, confirmar/cancelar jogos e gerenciar times/usuários
exige login com perfil **master**.

No primeiro acesso (quando ainda não existe nenhum usuário), o app leva
automaticamente para a criação da conta master. Sessões duram 90 dias.

Defina a variável de ambiente `SECRET_KEY` no Render (Settings → Environment)
com um valor aleatório e fixo — sem isso, o app usa uma chave padrão de
desenvolvimento, e qualquer redeploy pode invalidar as sessões já logadas.
