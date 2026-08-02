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
