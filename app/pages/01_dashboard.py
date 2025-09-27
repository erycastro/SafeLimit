import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt

st.set_page_config(page_title="Dashboard", page_icon="📊", layout="wide")

# --- Carregar dados (funciona só com base_sintetica.csv) ---
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]  # .../safe-limit
csv_path = ROOT / "data" / "base_sintetica.csv"
if not csv_path.exists():
    st.error("Arquivo data/base_sintetica.csv não encontrado.")
    st.stop()

df = pd.read_csv(csv_path)

# normaliza nome de atraso
if "atraso_30d" in df.columns and "atraso30d" not in df.columns:
    df = df.rename(columns={"atraso_30d": "atraso30d"})

# checa se já tem colunas prontas; se não tiver, calcula pd_pred com o modelo salvo
need_features = ['utilizacao','consistencia_6m','ticket_medio_deposito','renda_mensal','atraso30d','limite_atual']
missing_feat = [c for c in need_features if c not in df.columns]
if missing_feat:
    st.error(f"Faltam colunas básicas no CSV: {missing_feat}")
    st.stop()

def ensure_pd_pred(df):
    if 'pd_pred' in df.columns:
        return df
    # tentar carregar o modelo salvo e criar pd_pred
    from joblib import load
    model_path = ROOT / "models" / "safelimit_pd_calibrated_sigmoid.joblib"
    if not model_path.exists():
        st.error("Faltam pd_pred no CSV e o modelo salvo não foi encontrado em models/. "
                 "Abra o notebook 02_modelo_pd.ipynb, salve o modelo e rode a política.")
        st.stop()
    model = load(model_path)
    X = df[need_features]
    df = df.copy()
    df['pd_pred'] = model.predict_proba(X)[:, 1]
    return df

df = ensure_pd_pred(df)

# --- Sidebar: parâmetros "what-if" ---
st.sidebar.header("Parâmetros da política")
alpha = st.sidebar.slider("α (agressividade do aumento)", 1.0, 8.0, 5.0, 0.5)
cut_D = st.sidebar.slider("Corte do bucket D (PD ≥)", 0.06, 0.15, 0.10, 0.01, help="Clientes com PD acima disso não recebem aumento.")
cap_renda = st.sidebar.slider("Cap por renda (máx. % da renda)", 0.3, 0.8, 0.5, 0.05)
cap_mult  = st.sidebar.slider("Cap multiplicador (novo limite ≤ N × atual)", 1.2, 3.0, 2.0, 0.1)

# --- Reaplicar política com parâmetros atuais (sem mudar pd_pred) ---
def bucket(pd_):
    if pd_ < 0.03: return 'A'
    if pd_ < 0.06: return 'B'
    if pd_ < cut_D: return 'C'
    return 'D'

def passa_min_cons(cons_frac, minimo_meses=4):
    return int(round(cons_frac * 6)) >= minimo_meses

def recomendar_limite_row(r):
    b = bucket(r['pd_pred'])
    cons_ok = passa_min_cons(r['consistencia_6m'])
    EPS = 1e-9
    tick_ok = r['ticket_medio_deposito'] + EPS >= 0.05 * r['renda_mensal']
    if (not (cons_ok and tick_ok)) or b == 'D':
        return r['limite_atual'], 0.0, False, b
    base = alpha * r['ticket_medio_deposito']
    aumento_bruto = min(base, cap_renda * r['renda_mensal'])
    fator = {'A':1.0, 'B':0.6, 'C':0.3}[b]
    aumento = aumento_bruto * fator
    aumento = min(aumento, max(0.0, cap_mult * r['limite_atual'] - r['limite_atual']))
    return r['limite_atual'] + aumento, aumento, True, b

calc = df.apply(recomendar_limite_row, axis=1, result_type='expand')
df['novo_limite_viz'], df['aumento_viz'], df['elegivel_viz'], df['bucket_viz'] = calc[0], calc[1], calc[2], calc[3]

# --- Cabeçalho explicativo (acessível) ---
st.markdown("## Dashboard")
st.write(
    "O painel abaixo resume a política atual. **Leitura acessível**: "
    "os gráficos têm rótulos de valor e todo indicador possui texto. "
    "Use Tab/Shift+Tab para navegar; botões e sliders funcionam por teclado."
)

# --- KPIs principais (linha 1) ---
# --- KPIs principais (linha 1) ---
c1, c2 = st.columns(2)

pct_eleg = df['elegivel_viz'].mean()
aum_med  = df.loc[df['elegivel_viz'], 'aumento_viz'].mean()

c1.metric("Elegíveis", f"{pct_eleg*100:.1f}%", help="Proporção de clientes com aumento sugerido.")
c2.metric("Aumento médio (elegíveis)", f"R$ {aum_med:,.2f}")

# --- Guardrail de risco (não mostrar EL, só o selo) ---
LGD = 1.0  # proxy simples; pode trocar p/ 0.8 se quiser
el_pre = (df['pd_pred'] * LGD * df['limite_atual']).mean()
el_pos = (df['pd_pred'] * LGD * df['novo_limite_viz']).mean()
delta_pct = 100 * (el_pos - el_pre) / max(el_pre, 1e-9)

limite = 10.0  # limite de ΔEL aceitável (em %)
if delta_pct <= limite:
    st.info(f"Risco controlado: ΔEL ≈ {delta_pct:.1f}% (≤ {limite:.0f}%).")
else:
    st.warning(f"Atenção: ΔEL ≈ {delta_pct:.1f}% (> {limite:.0f}%). "
               "Ajuste α/corte de PD ou caps para reduzir.")


# --- Distribuição por bucket (com rótulos) ---
st.markdown("### Distribuição por bucket")
st.write("O gráfico abaixo mostra a fração do portfólio em cada bucket.")
bucket_share = (df['bucket_viz'].value_counts(normalize=True).sort_index()*100).reindex(['A','B','C','D']).fillna(0)

fig, ax = plt.subplots(figsize=(6,3))
bars = ax.bar(bucket_share.index, bucket_share.values)
ax.set_ylabel('% do portfólio'); ax.set_ylim(0, max(1, bucket_share.max()*1.2))
for rect, val in zip(bars, bucket_share.values):
    ax.text(rect.get_x()+rect.get_width()/2, rect.get_height()+0.5, f"{val:.1f}%", ha='center', va='bottom')
ax.grid(axis='y', alpha=0.2)
st.pyplot(fig, use_container_width=True)

# --- Elegibilidade por bucket ---
st.markdown("### Elegibilidade por bucket")
eleg_by_b = df.groupby('bucket_viz')['elegivel_viz'].mean().reindex(['A','B','C','D']).fillna(0)*100
fig2, ax2 = plt.subplots(figsize=(6,3))
bars2 = ax2.bar(eleg_by_b.index, eleg_by_b.values)
ax2.set_ylabel('% elegíveis'); ax2.set_ylim(0, 100)
ax2.set_ylim(0, max(100, eleg_by_b.max() + 8))
for rect, val in zip(bars2, eleg_by_b.values):
        y = val + 1
        color = '#0B1F2A'  # texto escuro
        va = 'bottom'
        top = ax2.get_ylim()[1]
        if y > top - 1:
            y = val - 3.5
            color = 'white'
            va = 'top'
        ax2.text(rect.get_x() + rect.get_width()/2, y, f"{val:.1f}%",
            ha='center', va=va, color=color, fontweight='normal')
ax2.grid(axis='y', alpha=0.2)
st.pyplot(fig2, use_container_width=True)

# --- Tabela acessível + download ---
st.markdown("### Tabela")
st.write("Tabela com PD, bucket e recomendação; você pode **ordenar/filtrar** e **baixar CSV**.")
view_cols = ['cliente_id','pd_pred','bucket_viz','elegivel_viz','limite_atual','novo_limite_viz','aumento_viz']
df_view = df[view_cols].copy()
df_view['pd_pred'] = (df_view['pd_pred']*100).round(1).astype(str) + '%'
st.dataframe(df_view.head(50), use_container_width=True)

csv_out = df[view_cols].to_csv(index=False).encode('utf-8')
st.download_button("Baixar CSV (recomendações atuais)", data=csv_out, file_name="safelimit_recomendacoes.csv", mime="text/csv")
