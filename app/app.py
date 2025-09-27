import streamlit as st
import pandas as pd
import numpy as np
from joblib import load
import os

st.set_page_config(page_title="SafeLimit", page_icon="💳", layout="centered")
st.title("SafeLimit — aumento de limite responsável ")
st.caption("PD (modelo calibrado) + política por buckets, elegibilidade e caps")
st.markdown("""
<style>
[data-testid="stMetricDelta"] { color: #00C2FF !important; }
[data-testid="stMetricDelta"] svg path { fill: #00C2FF !important; }
</style>
""", unsafe_allow_html=True)

# ------------- carregar modelo -------------
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "safelimit_pd_calibrated_sigmoid.joblib")
model = load(MODEL_PATH)

# ------------- política -------------
def bucket(pd_):
    if pd_ < 0.03: return 'A'
    if pd_ < 0.06: return 'B'
    if pd_ < 0.10: return 'C'
    return 'D'

def _passa_min_cons(cons_frac, minimo_meses=4):
    return int(round(cons_frac * 6)) >= minimo_meses

def recomendar_limite(row, alpha=5.0):
    b = row['bucket']
    cons_ok = _passa_min_cons(row['consistencia_6m'], minimo_meses=4)
    tick_ok = row['ticket_medio_deposito'] >= 0.05 * row['renda_mensal']
    eleg_min = cons_ok and tick_ok
    if (not eleg_min) or b == 'D':
        just = []
        if not cons_ok: just.append("consistência < 4/6")
        if not tick_ok: just.append("ticket < 5% renda")
        if b == 'D':    just.append("bucket D (PD ≥ 10%)")
        return row['limite_atual'], 0.0, False, "Sem aumento: " + "; ".join(just)

    base = alpha * row['ticket_medio_deposito']
    cap_renda = 0.5 * row['renda_mensal']
    cap_mult  = 2.0 * row['limite_atual']
    aumento_bruto = min(base, cap_renda)

    fator = {'A':1.0, 'B':0.6, 'C':0.3}[b]
    aumento = aumento_bruto * fator

    aumento_max_por_mult = max(0.0, cap_mult - row['limite_atual'])
    aumento = min(aumento, aumento_max_por_mult)

    novo = row['limite_atual'] + max(0.0, aumento)
    just = f"Aumento: bucket {b}, α={alpha}, base={base:.2f}, caps: renda≤{cap_renda:.2f}, mult≤{cap_mult:.2f}"
    return novo, aumento, True, just

FEATURES = ['utilizacao','consistencia_6m','ticket_medio_deposito','renda_mensal','atraso30d','limite_atual']

tab1, tab2 = st.tabs(["Simular 1 cliente", "Processar CSV"])

with tab1:
    st.subheader("Entrada")
    col1, col2 = st.columns(2)
    with col1:
        renda = st.number_input("Renda mensal (R$)", min_value=0.0, value=3000.0, step=100.0)
        limite = st.number_input("Limite atual (R$)", min_value=0.0, value=1200.0, step=50.0)
        ticket = st.number_input("Ticket médio de depósito (R$)", min_value=0.0, value=300.0, step=10.0)
    with col2:
        utilizacao = st.slider("Utilização do limite (0–1)", 0.0, 1.0, 0.35, 0.01)
        cons_meses = st.slider("Consistência (meses com depósito nos últimos 6)", 0, 6, 4, 1)
        consist = cons_meses / 6
        atraso30d = st.selectbox("Atraso ≥30d recente?", ["Não", "Sim"]) == "Sim"
    alpha = st.slider("α (agressividade do aumento)", 1.0, 8.0, 5.0, 0.5)

    if st.button("Calcular PD e recomendação"):
        x = pd.DataFrame([{
            'utilizacao': utilizacao,
            'consistencia_6m': consist,
            'ticket_medio_deposito': ticket,
            'renda_mensal': renda,
            'atraso30d': int(atraso30d),
            'limite_atual': limite
        }], columns=FEATURES)
        pd_pred = float(model.predict_proba(x)[:,1])
        bkt = bucket(pd_pred)
        x = x.assign(pd_pred=pd_pred, bucket=bkt)
        novo_limite, aumento, elegivel, justificativa = recomendar_limite(
            {**x.iloc[0].to_dict(), 'bucket': bkt}, alpha=alpha
        )

        st.markdown("### Resultado")
        c1, c2, c3 = st.columns(3)
        c1.metric("PD prevista", f"{pd_pred*100:.1f}%")
        c2.metric("Bucket", bkt)
        c3.metric("Elegível", "Sim ✅" if elegivel else "Não ❌")
        st.metric("Novo limite sugerido", f"R$ {novo_limite:,.2f}", delta=f"+ R$ {aumento:,.2f}")
        st.caption(justificativa)

with tab2:
    st.subheader("Upload CSV (colunas mínimas)")
    st.code(", ".join(FEATURES), language="text")
    file = st.file_uploader("Selecione um CSV", type=["csv"])
    alpha_batch = st.slider("α (lote)", 1.0, 8.0, 5.0, 0.5)
    if file:
        df_in = pd.read_csv(file)
        faltando = [c for c in FEATURES if c not in df_in.columns]
        if faltando:
            st.error(f"Faltam colunas: {faltando}")
        else:
            df_in = df_in.copy()
            df_in['pd_pred'] = model.predict_proba(df_in[FEATURES])[:,1]
            df_in['bucket'] = df_in['pd_pred'].apply(bucket)
            res = df_in.apply(lambda r: recomendar_limite(r, alpha=alpha_batch), axis=1, result_type='expand')
            df_in['novo_limite'], df_in['aumento'], df_in['elegivel'], df_in['justificativa'] = res[0], res[1], res[2], res[3]

            st.write("Prévia:")
            st.dataframe(df_in.head(20).assign(pd_pred=lambda d: (d['pd_pred']*100).round(1).astype(str)+'%'))

            csv_out = df_in.to_csv(index=False).encode('utf-8')
            st.download_button("Baixar resultados CSV", data=csv_out, file_name="safelimit_resultados.csv", mime="text/csv")
