# SafeLimit — aumento de limite responsável via depósitos + PD

**O que é:** O SafeLimit recomenda **aumento de limite de cartão** para clientes que **poupam de forma recorrente**, controlando **risco** com um **modelo de PD** (probabilidade de default) e **regras de política** com travas (“caps”). É um projeto didático com dados **sintéticos**.

---

## Como funciona (em 2 passos)

1) **Modelo (PD)** → estima a chance (%) de inadimplência em 12 meses a partir de:
   - comportamento de depósitos (consistência e ticket),
   - uso do cartão (utilização, atrasos),
   - renda e contexto simples.

2) **Política (regras)** → decide **se aumenta** e **quanto aumenta** o limite usando:
   - **elegibilidade mínima:** consistência ≥ **4 de 6** meses e ticket ≥ **5% da renda**,
   - **buckets de risco (A/B/C/D)** conforme a PD,
   - **caps** por renda (≤50% renda) e por multiplicador (≤2× limite atual),
   - **fator de risco** por bucket (A=1.0; B=0.6; C=0.3; D=0.0).

---

## “Contrato” do projeto (v1.0)

### Objetivo
Recomendar **aumento de limite** condicionado a **depósitos recorrentes**, **sem elevar demais o risco**.

### Métricas de sucesso
- **Modelo:** AUC **≥ 0,70** e **calibração** ok (PD prevista ≈ PD observada por faixas).
- **Negócio:** conceder aumento apenas se **PD < 6%** **e** **consistência ≥ 4/6 meses**, respeitando caps.

### Buckets de risco (faixas de PD)
- **A:** PD < 3%
- **B:** 3–6%
- **C:** 6–10%
- **D:** ≥10% → **sem aumento**

### Elegibilidade mínima
- `consistencia_6m ≥ 0,66` (≥ 4 de 6 meses com depósito)
- `ticket_medio_deposito ≥ 5% da renda_mensal`

### Política de aumento
    base = α × ticket_medio_deposito        (padrão α = 5)
    cap_renda = 50% da renda_mensal
    cap_mult  = 2 × limite_atual
    fator_risco = {A:1.0, B:0.6, C:0.3, D:0.0}

    aumento_bruto = min(base, cap_renda)
    aumento_final = aumento_bruto × fator_risco
    aumento_final limitado para não ultrapassar (cap_mult − limite_atual)

    novo_limite_sugerido = limite_atual + aumento_final (se elegível)

**Exemplo rápido (aplicando a política acima):**  
Renda = R$ 3.000 | Limite atual = R$ 1.200 | Ticket = R$ 300 | Consistência = 6/6 | PD = 2,8% (Bucket A)  
→ base = 5×300 = 1.500 | cap_renda = 1.500 | cap_mult = 2×1.200 = 2.400 | fator A = 1.0  
→ aumento_bruto = min(1.500, 1.500) = 1.500  
→ aumento_final = 1.500 × 1.0 = 1.500, mas **cap_mult** limita o novo limite a **R$ 2.400** (aumento máx. = 1.200).  
→ **novo_limite_sugerido = R$ 2.400**.

### Saídas por cliente
- `novo_limite_sugerido` (R$)
- `PD` (0–100%)
- `bucket` (A/B/C/D)
- `elegível` (sim/não)
- `justificativa` (resumo das regras/variáveis/caps que influenciaram)

---

## Dados e dicionário (sintéticos)

**Arquivo esperado:** `data/base_sintetica.csv`

**Colunas mínimas:**
- `cliente_id` (int)
- `renda_mensal` (float, R$)
- `limite_atual` (float, R$)
- `utilizacao` (0–1)
- `consistencia_6m` (0–1) — fração (ex.: 4/6 = 0,66)
- `ticket_medio_deposito` (float, R$)
- `atraso30d` (0/1)
- `default_12m` (0/1) — rótulo para treinar/avaliar PD

**Sanidade sugerida:** `default_12m` entre 4% e 10%; variedade em `limite_atual/renda_mensal`, `utilizacao` e `consistencia_6m`.

---


## Resultados

- **Modelo (baseline):** AUC **0,747** no conjunto de teste.
- **Calibração:** comparação por quantis (**q = 8**) com **erro médio ≈ 2,3 p.p.** (PD prevista ≈ observada).
- **Cortes finais da política:** PD < **6%**, consistência ≥ **4/6**, ticket ≥ **5%** da renda; caps **50% da renda** e **2×** o limite; fatores A/B/C = **1.0 / 0.6 / 0.3**; **D = 0%** elegível.
- **Impacto (sintético):**
  - **41,5%** elegíveis  
  - **Aumento médio** (entre elegíveis): **R$ 609,31**
  - **Buckets** no portfólio: **A 15,6% / B 33,7% / C 24,4% / D 26,3%**
  - **Elegibilidade por bucket:** **A 96% / B 62% / C 22,9% / D 0%**

---

## Estrutura do repositório
    .
    ├─ data/
    │  └─ base_sintetica.csv
    ├─ notebooks/
    │  ├─ 01_eda.ipynb
    │  └─ 02_modelo_pd.ipynb
    ├─ app/
    │  └─ app.py
    ├─ reports/
    │  ├─ metrics.md
    │  └─ policy_tradeoffs.md
    └─ README.md

---

## Quickstart

**Ambiente — libs essenciais (nomes simples para adicionar no env):**  
`python` (3.11), `pandas`, `numpy`, `scikit-learn`, `matplotlib`, `jupyterlab`, `ipykernel`, `streamlit`  

**Como rodar (comandos num bloco único):**
    # EDA/modelagem
    jupyter lab

    # App (placeholder de PD até plugar o modelo)
    streamlit run app/app.py

---

## Glossário (linguagem simples)
- **PD (Probabilidade de Default):** chance do cliente **não pagar** (ex.: PD=5% → ~5 em 100).
- **AUC:** mede o quão bem o modelo **separa bons de ruins** (≥0,70 já é ok no baseline).
- **Calibração:** verifica se a **PD prevista** bate com a **PD observada** nos grupos.
- **Consistência 6m:** fração de meses (nos últimos 6) em que houve depósito (ex.: 4/6=0,66).
- **Ticket médio:** valor médio depositado por mês (últimos 6).
- **Buckets A/B/C/D:** faixas de risco pela PD para facilitar regras.
- **Caps:** travas que limitam aumento (por renda e por multiplicador do limite atual).
- **Elegível:** passou nas regras mínimas e não está no bucket D.

