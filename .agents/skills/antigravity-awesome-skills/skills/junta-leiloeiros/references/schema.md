# Schema de Dados — Leiloeiros das Juntas Comerciais

## Tabela `leiloeiros` (SQLite)

```sql
CREATE TABLE leiloeiros (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    estado           TEXT    NOT NULL,     -- UF: SP, RJ, MG, ...
    junta            TEXT    NOT NULL,     -- nome da junta: JUCESP, JUCERJA, ...
    matricula        TEXT,                 -- número de matrícula (pode ser NULL se não publicado)
    nome             TEXT    NOT NULL,     -- nome completo do leiloeiro
    cpf_cnpj         TEXT,                 -- CPF ou CNPJ (quando disponível)
    situacao         TEXT,                 -- ATIVO | CANCELADO | SUSPENSO | IRREGULAR
    endereco         TEXT,                 -- endereço completo
    municipio        TEXT,                 -- cidade
    telefone         TEXT,                 -- telefone de contato
    email            TEXT,                 -- e-mail
    data_registro    TEXT,                 -- data de registro na junta (ISO 8601 ou texto)
    data_atualizacao TEXT,                 -- última atualização cadastral
    url_fonte        TEXT,                 -- URL de onde o dado foi coletado
    scraped_at       TEXT    NOT NULL,     -- timestamp da coleta (ISO 8601 UTC)
    UNIQUE (estado, matricula) ON CONFLICT REPLACE
);
```

## Campos

| Campo | Tipo | Obrigatório | Valores |
|-------|------|-------------|---------|
| `id` | int | auto | PK auto-incremento |
| `estado` | text | sim | UF 2 letras maiúsculas |
| `junta` | text | sim | Nome da junta ex: JUCESP |
| `matricula` | text | não | Número de matrícula na junta |
| `nome` | text | sim | Nome completo |
| `cpf_cnpj` | text | não | Documento sem formatação preferencial |
| `situacao` | text | não | ATIVO, CANCELADO, SUSPENSO, IRREGULAR |
| `endereco` | text | não | Logradouro completo |
| `municipio` | text | não | Cidade |
| `telefone` | text | não | Formato livre |
| `email` | text | não | E-mail de contato |
| `data_registro` | text | não | Data ISO ou texto da junta |
| `data_atualizacao` | text | não | Data ISO ou texto da junta |
| `url_fonte` | text | não | URL da página coletada |
| `scraped_at` | text | sim | ISO 8601 UTC ex: 2024-03-15T10:30:00+00:00 |

## Normalização de `situacao`

Os textos das juntas são normalizados para valores padrão:

| Texto Original (exemplos) | Valor Normalizado |
|--------------------------|-------------------|
| Ativo, Regular, Habilitado, Regularizado | `ATIVO` |
| Cancelado, Baixado, Extinto | `CANCELADO` |
| Suspenso | `SUSPENSO` |
| Irregular | `IRREGULAR` |
| Qualquer outro | mantido como recebido |

## Formato de Exportação (JSON)

```json
{
  "exported_at": "2024-03-15T10:30:00+00:00",
  "total": 1234,
  "data": [
    {
      "id": 1,
      "estado": "SP",
      "junta": "JUCESP",
      "matricula": "001234",
      "nome": "João da Silva Leiloeiro",
      "cpf_cnpj": null,
      "situacao": "ATIVO",
      "endereco": "Rua das Flores, 100",
      "municipio": "São Paulo",
      "telefone": "(11) 3456-7890",
      "email": "joao@leiloes.com.br",
      "data_registro": "2010-05-20",
      "data_atualizacao": null,
      "url_fonte": "https://www.institucional.jucesp.sp.gov.br/tradutores-leiloeiros.html",
      "scraped_at": "2024-03-15T10:30:00+00:00"
    }
  ]
}
```

## Índices

```sql
CREATE INDEX idx_estado   ON leiloeiros (estado);
CREATE INDEX idx_nome     ON leiloeiros (nome);
CREATE INDEX idx_situacao ON leiloeiros (situacao);
CREATE INDEX idx_scraped  ON leiloeiros (scraped_at);
```
