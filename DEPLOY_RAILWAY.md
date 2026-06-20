# Checklist de deploy — Railway (Festejo Financeiro)

Use este roteiro **antes** de cada deploy em produção. Objetivo: subir só o código novo e **manter os dados do volume** (nunca os dados locais antigos).

---

## 1. Antes do push (na sua máquina)

- [ ] **Não rode** `atualizar_bootstrap.bat` antes deste deploy (evita gravar dados locais antigos no Git).
- [ ] Confirme que `data/` **não** vai no commit:
  ```bash
  git status
  ```
  A pasta `data/` deve aparecer ignorada ou ausente. Se `data/festejo.db` aparecer como staged, **pare** e não faça commit.
- [ ] Revise o que será enviado (só código + templates + static):
  ```bash
  git diff --stat
  ```
- [ ] Commit e push para a branch que o Railway usa (ex.: `main`).

**Lembrete:** `data/` está no `.gitignore` — banco, uploads e NF-e locais **nunca sobem** pelo Git.

---

## 2. Painel Railway — Volume

Railway → seu **projeto** → serviço **web** → aba **Volumes**

- [ ] Existe um volume criado e **montado** no serviço da aplicação.
- [ ] Mount path costuma ser algo como `/data` (anote o caminho exato).
- [ ] O volume **não** foi apagado nem recriado para este deploy.

Railway → serviço → **Variables**

- [ ] Existe `DATA_DIR` apontando para o mount do volume (ex.: `/data`), **ou** o Railway injeta `RAILWAY_VOLUME_MOUNT_PATH` automaticamente ao montar o volume.
- [ ] Não há variável apontando para pasta temporária do container (dados se perderiam a cada deploy).

Ordem de prioridade no código (`app/database.py`):

1. `DATA_DIR` (variável manual)
2. `RAILWAY_VOLUME_MOUNT_PATH` (automático com volume)
3. `data/` local (só desenvolvimento)

---

## 3. Painel Railway — Deploy

Railway → serviço → **Settings** / **Deploy**

- [ ] **Start command** (ou `railway.toml`):
  ```text
  python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
  ```
- [ ] **Health check:** path `/` (já configurado em `railway.toml`).
- [ ] Deploy disparado (automático após push ou manual).

---

## 4. Durante / após o deploy

Railway → serviço → **Deployments** → deploy atual → **View logs**

- [ ] Build concluiu sem erro.
- [ ] App subiu (`Application startup complete` ou similar).
- [ ] **Não** deve aparecer log `Bootstrap: copiando dados iniciais` se o volume já tinha banco (isso indicaria volume vazio ou mount errado).

---

## 5. Testes em produção (URL pública)

Abra a URL do Railway e confira:

- [ ] **Painel** carrega com totais **iguais** aos que o cliente tinha antes (caixa, despesas, lucro).
- [ ] **Caixa / Despesas / Rifa / Leilão** — lançamentos antigos ainda visíveis.
- [ ] Menu lateral: **Patrocínios** e **Investimentos** aparecem (telas novas).
- [ ] Patrocínios e Investimentos podem estar vazios — normal se o cliente ainda não cadastrou.
- [ ] **Infográfico** abre sem erro.
- [ ] (Opcional) Cadastre um teste em Patrocínios, recarregue a página e confirme que **persistiu** (prova de que o volume está gravando).

---

## 6. O que este deploy faz no banco (sem apagar dados)

Na subida, o app executa `create_all`, que **só cria tabelas novas** se não existirem:

- `patrocinio_movimentos`
- `investimentos`

Tabelas e registros antigos **não são alterados nem removidos**.

O `bootstrap_data/` do repositório **só é usado** se não existir `festejo.db` no volume. Com volume já populado, **não sobrescreve** produção.

---

## 7. Nunca faça em produção

| Ação | Risco |
|------|--------|
| Apagar ou recriar o volume | Perda total dos dados do cliente |
| Rodar `atualizar_bootstrap.bat` + commit antes do deploy | Grava snapshot local antigo no Git (não apaga produção, mas confunde) |
| Commitar arquivos de `data/` | Dados locais antigos no repositório |
| Deploy sem volume montado | Cada restart usa banco vazio/temporário |

---

## 8. Backup recomendado (opcional, antes do deploy)

Se tiver acesso ao volume ou CLI Railway:

1. Baixe/copie `festejo.db` do volume para um arquivo datado (ex.: `festejo_backup_2025-06-20.db`).
2. Guarde fora do repositório.

---

## 9. Rollback se algo der errado

1. Railway → **Deployments** → deployment **anterior** (que funcionava) → **Redeploy**.
2. Os dados continuam no volume; só volta a versão do código.
3. Se o problema for só layout/bug visual, corrija localmente e faça novo push.

---

## Resumo em uma linha

**Push só código → volume montado → bootstrap não roda → dados do cliente intactos → tabelas novas criadas automaticamente.**
