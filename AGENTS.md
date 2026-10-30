# Repository Guidelines

## Estrutura e arquitetura

Este projeto monitora proposições legislativas para a ABCS usando Python, PostgreSQL/Supabase, n8n e Power BI. Contexto detalhado, fluxo diário e invariantes de falha parcial estão no `CLAUDE.md`.

- `src/`: clientes das APIs, extração, carregadores e orquestração.
- `sql/`: schemas, seeds e transformações Bronze → Silver → Gold; `api_cache` materializa dados para o schema `api` consumido pelo Power BI.
- `tests/`: testes automatizados e fixtures em `tests/fixtures/`.
- `BI/`: projeto PBIP, modelo semântico, relatório e scripts de design.
- `.github/workflows/`: testes e execução do pipeline; o agendamento fica no n8n.
- `docs/superpowers/`: especificações e planos de evolução.

## Ambiente e comandos

Use Python 3.14, definido em `.python-version`. Na raiz:

```bash
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m compileall -q src tests
.venv/bin/python -m unittest discover -s tests -v
```

Os dois últimos comandos validam sintaxe e executam a suíte usada no CI. Para rodar scripts, entre em `src/`, pois os imports são entre módulos irmãos:

```bash
cd src
../.venv/bin/python check_environment.py  # verifica banco e configuração
../.venv/bin/python pipeline.py           # carga diária completa
../.venv/bin/python pipeline_pautas.py    # atualização de eventos/pautas
```

Configure `src/.env` conforme `src/.env.example`. Cargas escrevem no banco configurado; `setup_db.py` aplica schemas e recria os caches.

## Estilo e convenções

Use quatro espaços em Python, `snake_case` para módulos/funções e `UPPER_SNAKE_CASE` para constantes. Mantenha comentários, logs e documentação em português. Siga o estilo existente; não há formatador ou linter obrigatório configurado. Centralize configurações em `src/config.py` e keywords em `src/keywords.py`.

## Testes e invariantes

Use `unittest` e `unittest.mock`; nomeie arquivos `test_*.py` e métodos `test_*`. Os testes automatizados devem dispensar banco, credenciais e APIs reais. Não há percentual mínimo de cobertura configurado. Cubra regressões de falhas parciais, transações e janelas incrementais. Preserve o isolamento entre casas, as chaves definidas em `config.py` e a paridade das regras Gold/API.

## Commits e pull requests

O histórico usa mensagens curtas e descritivas em português, como `Bronze do Senado só quando o payload muda`, sem prefixo obrigatório. Faça commits focados. Na descrição do PR, explique problema, comportamento resultante, validação e eventuais passos de migração. Relacione issues quando aplicável e inclua capturas para mudanças visuais no painel.

## Segurança

O repositório é público. Nunca versione `.env`, tokens Google, dados locais ou arquivos `.pbix`, `.pbit` e `.abf`, nem material de `divulgacao/`, URLs/refs/chaves do Supabase, links de planilha ou posições institucionais da ABCS. Antes de alterar TMDL, configure o filtro `segredos-pbi` conforme o README; preserve marcadores e execute `tests/test_segredos.py` pela suíte.
