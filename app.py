import io
import os
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# ---------------------------------------------------------
# Configuração da Página e Moeda
# ---------------------------------------------------------
st.set_page_config(
    page_title="Dividend Data Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

MOEDA = "€"
CSV_FILE = "portfolio.csv"

st.markdown(
    """
    <style>
        .main { background-color: #0e1117; }
        .stMetric {
            background-color: #161b22;
            padding: 14px;
            border-radius: 8px;
            border: 1px solid #30363d;
        }
    </style>
""",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# Gestão de Dados Locais (CSV)
# ---------------------------------------------------------
def carregar_portfolio():
    if not os.path.exists(CSV_FILE):
        dados_iniciais = pd.DataFrame(
            [
                {
                    "Ticker": "VGWD.DE",
                    "Shares": 195.0,
                    "Cost_Per_Share": 77.06,
                    "Currency": "EUR",
                },
                {
                    "Ticker": "IQQE.DE",
                    "Shares": 81.0,
                    "Cost_Per_Share": 58.24,
                    "Currency": "EUR",
                },
            ]
        )
        dados_iniciais.to_csv(CSV_FILE, index=False)
        return dados_iniciais
    return pd.read_csv(CSV_FILE)


def guardar_portfolio(df):
    df.to_csv(CSV_FILE, index=False)


# ---------------------------------------------------------
# Processamento de CSV (Trading 212 & Genérico)
# ---------------------------------------------------------
def processar_csv_importado(ficheiro_carregado):
    try:
        df_raw = pd.read_csv(ficheiro_carregado)
        colunas = [c.strip() for c in df_raw.columns]
        df_raw.columns = colunas

        # Formato Trading 212
        if "Action" in colunas and (
            "No. of shares" in colunas or "Shares" in colunas
        ):
            col_shares = (
                "No. of shares" if "No. of shares" in colunas else "Shares"
            )
            col_price = (
                "Price / share" if "Price / share" in colunas else "Price"
            )
            col_ticker = "Ticker"

            carteira_calculada = {}
            if "Time" in colunas:
                df_raw["Time"] = pd.to_datetime(df_raw["Time"], errors="coerce")
                df_raw = df_raw.sort_values("Time", ascending=True)

            for _, row in df_raw.iterrows():
                acao = str(row["Action"]).lower()
                ticker = str(row[col_ticker]).strip().upper()
                qtd = float(row[col_shares]) if pd.notnull(row[col_shares]) else 0.0
                preco = (
                    float(row[col_price]) if pd.notnull(row[col_price]) else 0.0
                )

                if ticker not in carteira_calculada:
                    carteira_calculada[ticker] = {
                        "shares": 0.0,
                        "total_invested": 0.0,
                    }

                pos = carteira_calculada[ticker]
                if "buy" in acao:
                    pos["total_invested"] += qtd * preco
                    pos["shares"] += qtd
                elif "sell" in acao and pos["shares"] > 0:
                    custo_medio = pos["total_invested"] / pos["shares"]
                    pos["shares"] = max(0.0, pos["shares"] - qtd)
                    pos["total_invested"] = pos["shares"] * custo_medio

            linhas = []
            for t, val in carteira_calculada.items():
                if val["shares"] > 0.0001:
                    pm = (
                        val["total_invested"] / val["shares"]
                        if val["shares"] > 0
                        else 0.0
                    )
                    linhas.append(
                        {
                            "Ticker": t,
                            "Shares": round(val["shares"], 4),
                            "Cost_Per_Share": round(pm, 2),
                            "Currency": "EUR",
                        }
                    )
            return pd.DataFrame(linhas), None

        # Formato Padrão (Ticker, Shares, Cost_Per_Share)
        ticker_col = next(
            (c for c in colunas if c.lower() in ["ticker", "symbol", "ativo"]),
            None,
        )
        shares_col = next(
            (
                c
                for c in colunas
                if c.lower() in ["shares", "acoes", "ações", "qtd", "quantidade"]
            ),
            None,
        )
        cost_col = next(
            (
                c
                for c in colunas
                if c.lower()
                in [
                    "cost_per_share",
                    "cost",
                    "preco_medio",
                    "preço médio",
                    "custo",
                ]
            ),
            None,
        )

        if ticker_col and shares_col and cost_col:
            df_res = pd.DataFrame()
            df_res["Ticker"] = df_raw[ticker_col].astype(str).str.strip().str.upper()
            df_res["Shares"] = pd.to_numeric(df_raw[shares_col], errors="coerce").fillna(0.0)
            df_res["Cost_Per_Share"] = pd.to_numeric(df_raw[cost_col], errors="coerce").fillna(0.0)
            df_res["Currency"] = "EUR"
            return df_res[df_res["Shares"] > 0], None

        return (
            None,
            "Formato não reconhecido. Usa: Ticker, Shares, Cost_Per_Share.",
        )
    except Exception as e:
        return None, f"Erro ao processar ficheiro: {str(e)}"


# ---------------------------------------------------------
# Obtenção de Cotações e Dividendos Reais (TTM)
# ---------------------------------------------------------
@st.cache_data(ttl=300)
def obter_dados_mercado(tickers):
    dados = {}
    if not tickers:
        return dados

    for t in tickers:
        try:
            ticker_obj = yf.Ticker(t)
            fast_info = ticker_obj.fast_info
            info = ticker_obj.info

            preco = fast_info.last_price or 0.0
            preco_anterior = fast_info.previous_close or preco

            variacao_dia_pct = 0.0
            if preco and preco_anterior:
                variacao_dia_pct = (
                    (preco - preco_anterior) / preco_anterior
                ) * 100

            # 1. Tentar ler do sumário inicial
            div_rate = info.get("dividendRate", 0.0) or 0.0
            div_yield = info.get("dividendYield", 0.0) or 0.0

            # 2. Fallback robusto para ETFs Europeus (UCITS): histórico real de pagamentos
            pagamentos_mes = {m: 0.0 for m in range(1, 13)}
            try:
                hist_divs = ticker_obj.dividends
                if hist_divs is not None and not hist_divs.empty:
                    h_naive = hist_divs.copy()
                    if h_naive.index.tz is not None:
                        h_naive.index = h_naive.index.tz_localize(None)

                    agora = pd.Timestamp.now()
                    um_ano_atras = agora - pd.Timedelta(days=365)
                    divs_12m = h_naive[h_naive.index >= um_ano_atras]

                    if not divs_12m.empty and divs_12m.sum() > 0:
                        if div_rate == 0.0:
                            div_rate = float(divs_12m.sum())
                        for dt, val in divs_12m.items():
                            pagamentos_mes[dt.month] += float(val)
                    else:
                        ultimas = h_naive.tail(4)
                        if div_rate == 0.0:
                            div_rate = float(ultimas.sum())
                        for dt, val in ultimas.items():
                            pagamentos_mes[dt.month] += float(val)
            except Exception:
                pass

            # Distribuir equitativamente caso haja dividendos mas sem registo de datas
            if div_rate > 0 and sum(pagamentos_mes.values()) == 0:
                for m in range(1, 13):
                    pagamentos_mes[m] = div_rate / 12.0

            # Calcular yield se ainda não existir
            if div_yield == 0.0 and div_rate > 0 and preco > 0:
                div_yield = div_rate / preco
            elif div_rate == 0.0 and div_yield > 0 and preco > 0:
                div_rate = preco * div_yield

            moeda = fast_info.currency or info.get("currency", "EUR")
            nome = info.get("shortName", t)

            dados[t] = {
                "Name": nome,
                "Price": preco,
                "Prev_Close": preco_anterior,
                "Day_Change_Pct": variacao_dia_pct,
                "Annual_Div_Per_Share": div_rate,
                "Div_Yield": div_yield,
                "Monthly_Schedule": pagamentos_mes,
                "Currency": moeda,
            }
        except Exception:
            dados[t] = {
                "Name": t,
                "Price": 0.0,
                "Prev_Close": 0.0,
                "Day_Change_Pct": 0.0,
                "Annual_Div_Per_Share": 0.0,
                "Div_Yield": 0.0,
                "Monthly_Schedule": {m: 0.0 for m in range(1, 13)},
                "Currency": "EUR",
            }
    return dados


# ---------------------------------------------------------
# Sidebar: Gestão de Carteira
# ---------------------------------------------------------
df_portfolio = carregar_portfolio()

with st.sidebar:
    st.header("⚙️ Gestor de Carteira")

    with st.expander("📥 Importar Ficheiro CSV", expanded=False):
        st.caption("Suporta extratos da **Trading 212** ou modelo padrão.")
        modelo_csv = "Ticker,Shares,Cost_Per_Share\nVGWD.DE,195.0,77.06\nIQQE.DE,81.0,58.24\nMSFT,10.0,400.0\n"
        st.download_button(
            label="📄 Descarregar Modelo CSV",
            data=modelo_csv,
            file_name="modelo_carteira.csv",
            mime="text/csv",
            use_container_width=True,
        )

        uploaded_file = st.file_uploader("Carregar CSV", type=["csv"])
        tipo_import = st.radio(
            "Método:", ["Substituir Carteira", "Fundir / Adicionar"]
        )

        if uploaded_file is not None:
            if st.button("Executar Importação", use_container_width=True):
                df_novo, erro = processar_csv_importado(uploaded_file)
                if erro:
                    st.error(erro)
                elif df_novo is not None and not df_novo.empty:
                    if tipo_import == "Substituir Carteira":
                        df_portfolio = df_novo
                    else:
                        df_portfolio = (
                            pd.concat([df_portfolio, df_novo])
                            .drop_duplicates(subset=["Ticker"], keep="last")
                            .reset_index(drop=True)
                        )
                    guardar_portfolio(df_portfolio)
                    st.success(f"Carregados {len(df_novo)} ativos!")
                    st.cache_data.clear()
                    st.rerun()

    with st.expander("➕ Adicionar Manualmente", expanded=False):
        novo_ticker = (
            st.text_input("Ticker (ex: VGWD.DE, IQQE.DE, MSFT)")
            .strip()
            .upper()
        )
        novas_shares = st.number_input(
            "N.º de Ações / Unidades", min_value=0.0001, value=10.0, step=1.0
        )
        novo_custo = st.number_input(
            f"Preço Médio de Compra ({MOEDA})",
            min_value=0.01,
            value=50.0,
            step=0.5,
        )

        if st.button("Guardar Ativo", use_container_width=True):
            if novo_ticker:
                if novo_ticker in df_portfolio["Ticker"].values:
                    st.warning("O ativo já se encontra registado.")
                else:
                    nova_linha = pd.DataFrame(
                        [
                            {
                                "Ticker": novo_ticker,
                                "Shares": novas_shares,
                                "Cost_Per_Share": novo_custo,
                                "Currency": "EUR",
                            }
                        ]
                    )
                    df_portfolio = pd.concat(
                        [df_portfolio, nova_linha], ignore_index=True
                    )
                    guardar_portfolio(df_portfolio)
                    st.success(f"{novo_ticker} adicionado!")
                    st.cache_data.clear()
                    st.rerun()

    with st.expander("🗑️ Remover Ativo", expanded=False):
        if not df_portfolio.empty:
            ticker_remover = st.selectbox(
                "Seleciona o Ticker", options=df_portfolio["Ticker"].tolist()
            )
            if st.button(
                "Eliminar da Carteira",
                type="primary",
                use_container_width=True,
            ):
                df_portfolio = df_portfolio[
                    df_portfolio["Ticker"] != ticker_remover
                ].reset_index(drop=True)
                guardar_portfolio(df_portfolio)
                st.success(f"{ticker_remover} removido.")
                st.cache_data.clear()
                st.rerun()

    st.markdown("---")
    if st.button("🔄 Atualizar Cotações", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ---------------------------------------------------------
# Processamento e Consolidação dos Dados
# ---------------------------------------------------------
tickers_lista = df_portfolio["Ticker"].tolist()
market_data = obter_dados_mercado(tickers_lista)

dados_processados = []
distribuicao_mensal = {m: 0.0 for m in range(1, 13)}

for _, row in df_portfolio.iterrows():
    t = row["Ticker"]
    shares = float(row["Shares"])
    cost_price = float(row["Cost_Per_Share"])

    m_info = market_data.get(t, {})
    curr_price = m_info.get("Price", 0.0)
    day_pct = m_info.get("Day_Change_Pct", 0.0)
    annual_div_share = m_info.get("Annual_Div_Per_Share", 0.0)
    div_yield = m_info.get("Div_Yield", 0.0) * 100
    name = m_info.get("Name", t)
    monthly_sched = m_info.get("Monthly_Schedule", {})

    invested = shares * cost_price
    mkt_value = shares * curr_price
    unrealized_gl = mkt_value - invested
    total_return_pct = (
        (unrealized_gl / invested) * 100 if invested > 0 else 0.0
    )
    day_gl = (
        shares * (curr_price - m_info.get("Prev_Close", curr_price))
        if curr_price > 0
        else 0.0
    )

    annual_dividend = shares * annual_div_share
    yoc = (annual_dividend / invested) * 100 if invested > 0 else 0.0

    # Acumular dividendos por mês calendário
    for m in range(1, 13):
        distribuicao_mensal[m] += shares * monthly_sched.get(m, 0.0)

    dados_processados.append(
        {
            "Ticker": t,
            "Nome": name,
            "Shares": shares,
            "Cost/Share": cost_price,
            "Price": curr_price,
            "Invested": invested,
            "Mkt Value": mkt_value,
            "Day Change %": day_pct,
            "Day G/L": day_gl,
            "Unrealized G/L": unrealized_gl,
            "Total Return %": total_return_pct,
            "Annual Dividend": annual_dividend,
            "Dividend Yield %": div_yield,
            "Yield on Cost %": yoc,
        }
    )

df_view = pd.DataFrame(dados_processados)

total_invested = df_view["Invested"].sum() if not df_view.empty else 0.0
total_mkt_value = df_view["Mkt Value"].sum() if not df_view.empty else 0.0
total_unrealized_gl = total_mkt_value - total_invested
total_return_overall_pct = (
    (total_unrealized_gl / total_invested) * 100 if total_invested > 0 else 0.0
)
total_day_gl = df_view["Day G/L"].sum() if not df_view.empty else 0.0
total_annual_dividend = (
    df_view["Annual Dividend"].sum() if not df_view.empty else 0.0
)
portfolio_yield = (
    (total_annual_dividend / total_mkt_value) * 100
    if total_mkt_value > 0
    else 0.0
)
portfolio_yoc = (
    (total_annual_dividend / total_invested) * 100
    if total_invested > 0
    else 0.0
)

if total_mkt_value > 0:
    df_view["Weight %"] = (df_view["Mkt Value"] / total_mkt_value) * 100
else:
    df_view["Weight %"] = 0.0

# ---------------------------------------------------------
# Layout Principal
# ---------------------------------------------------------
st.title("💼 Dividend Portfolio Tracker")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric(
    label="Valor de Mercado",
    value=f"{total_mkt_value:,.2f} {MOEDA}",
    delta=f"{total_day_gl:+,.2f} {MOEDA} hoje",
)
m2.metric(
    label="Total Investido",
    value=f"{total_invested:,.2f} {MOEDA}",
)
m3.metric(
    label="Retorno Total (G/L)",
    value=f"{total_unrealized_gl:+,.2f} {MOEDA}",
    delta=f"{total_return_overall_pct:+.2f}%",
)
m4.metric(
    label="Dividendos Anuais",
    value=f"{total_annual_dividend:,.2f} {MOEDA}",
    delta=f"{total_annual_dividend/12:,.2f} {MOEDA}/mês",
)
m5.metric(
    label="Yield Médio / YoC",
    value=f"{portfolio_yield:.2f}%",
    delta=f"{portfolio_yoc:.2f}% YoC",
)

st.markdown("<br>", unsafe_allow_html=True)

tab_holdings, tab_insights, tab_forecast = st.tabs(
    ["📊 Holdings", "💰 Dividend Insights", "🚀 Snowball Forecast"]
)

# TAB 1: Holdings
with tab_holdings:
    st.subheader("Posições da Carteira")
    col_tabela, col_pizza = st.columns([3, 1])

    with col_tabela:
        if not df_view.empty:
            df_display = df_view[
                [
                    "Ticker",
                    "Shares",
                    "Price",
                    "Cost/Share",
                    "Mkt Value",
                    "Weight %",
                    "Day Change %",
                    "Day G/L",
                    "Unrealized G/L",
                    "Total Return %",
                    "Yield on Cost %",
                ]
            ].copy()

            st.dataframe(
                df_display.style.format(
                    {
                        "Shares": "{:,.2f}",
                        "Price": "{:,.2f} " + MOEDA,
                        "Cost/Share": "{:,.2f} " + MOEDA,
                        "Mkt Value": "{:,.2f} " + MOEDA,
                        "Weight %": "{:.2f}%",
                        "Day Change %": "{:+.2f}%",
                        "Day G/L": "{:+,.2f} " + MOEDA,
                        "Unrealized G/L": "{:+,.2f} " + MOEDA,
                        "Total Return %": "{:+.2f}%",
                        "Yield on Cost %": "{:.2f}%",
                    }
                ).map(
                    lambda v: (
                        "color: #00e676;"
                        if v > 0
                        else "color: #ff5252;"
                        if v < 0
                        else ""
                    ),
                    subset=[
                        "Day Change %",
                        "Day G/L",
                        "Unrealized G/L",
                        "Total Return %",
                    ],
                ),
                use_container_width=True,
                height=350,
            )
        else:
            st.info("A carteira está vazia.")

    with col_pizza:
        if not df_view.empty and total_mkt_value > 0:
            fig_pie = px.pie(
                df_view,
                values="Mkt Value",
                names="Ticker",
                hole=0.5,
                title="Distribuição (%)",
                color_discrete_sequence=px.colors.qualitative.Dark24,
            )
            fig_pie.update_layout(
                margin=dict(t=30, b=10, l=10, r=10),
                showlegend=False,
                height=320,
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#c9d1d9"),
            )
            fig_pie.update_traces(
                textposition="inside", textinfo="percent+label"
            )
            st.plotly_chart(fig_pie, use_container_width=True)

# TAB 2: Dividend Insights
with tab_insights:
    st.subheader("Análise dos Proventos Passivos")
    c1, c2 = st.columns([2, 1])

    with c1:
        if not df_view.empty and total_annual_dividend > 0:
            fig_bar = px.bar(
                df_view.sort_values(by="Annual Dividend", ascending=False),
                x="Ticker",
                y="Annual Dividend",
                text_auto=".2f",
                title=f"Projeção de Renda Anual por Ativo ({MOEDA})",
                color="Annual Dividend",
                color_continuous_scale="Greens",
            )
            fig_bar.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#c9d1d9"),
                height=340,
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("Sem dados de dividendos para exibir.")

    with c2:
        st.markdown("#### Resumo de Distribuição")
        st.write(
            f"• **Rendimento Médio Mensal:** `{total_annual_dividend / 12:,.2f} {MOEDA}`"
        )
        st.write(
            f"• **Rendimento Médio Diário:** `{total_annual_dividend / 365:,.2f} {MOEDA}`"
        )
        maior_pagador = (
            df_view.loc[df_view["Annual Dividend"].idxmax()]["Ticker"]
            if not df_view.empty and total_annual_dividend > 0
            else "N/A"
        )
        st.write(f"• **Maior Pagador:** `{maior_pagador}`")
        st.write(f"• **Dividend Yield da Carteira:** `{portfolio_yield:.2f}%`")
        st.write(f"• **Yield on Cost (YoC):** `{portfolio_yoc:.2f}%`")

    st.markdown("---")
    st.subheader("Calendário de Pagamentos (Meses Reais)")
    meses = [
        "Jan",
        "Fev",
        "Mar",
        "Abr",
        "Mai",
        "Jun",
        "Jul",
        "Ago",
        "Set",
        "Out",
        "Nov",
        "Dez",
    ]
    valores_mes = [distribuicao_mensal[m] for m in range(1, 13)]

    fig_months = go.Figure(
        data=[
            go.Bar(
                x=meses,
                y=valores_mes,
                text=[
                    f"{v:,.2f} {MOEDA}" if v > 0 else "" for v in valores_mes
                ],
                textposition="auto",
                marker_color="#238636",
            )
        ]
    )
    fig_months.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#c9d1d9"),
        height=280,
        margin=dict(t=20, b=20, l=10, r=10),
        yaxis_title=f"Rendimento ({MOEDA})",
    )
    st.plotly_chart(fig_months, use_container_width=True)

# TAB 3: Snowball Simulator
with tab_forecast:
    st.subheader("Simulador Snowball & Compounding (DRIP)")
    col_inputs, col_graph = st.columns([1, 2])

    with col_inputs:
        anos = st.slider("Horizonte Temporal (Anos)", 5, 30, 20, 1)
        aporte_mensal = st.number_input(
            f"Aporte Mensal Adicional ({MOEDA})",
            min_value=0,
            value=1000,
            step=100,
        )
        div_growth_rate = (
            st.slider(
                "Crescimento Anual do Dividendo (%)", 0.0, 15.0, 7.0, 0.5
            )
            / 100.0
        )
        stock_appreciation = (
            st.slider(
                "Valorização de Capital Anual (%)", 0.0, 15.0, 8.0, 0.5
            )
            / 100.0
        )
        reinvestir_div = st.checkbox(
            "Reinvestir Dividendos (DRIP Automático)", value=True
        )

    anos_lista = list(range(0, anos + 1))
    proj_valor = []
    proj_dividendos = []

    curr_val = total_mkt_value if total_mkt_value > 0 else 10000.0
    curr_div = (
        total_annual_dividend
        if total_annual_dividend > 0
        else (curr_val * 0.035)
    )

    for ano in anos_lista:
        proj_valor.append(curr_val)
        proj_dividendos.append(curr_div)

        novos_aportes = aporte_mensal * 12
        ganho_capital = curr_val * stock_appreciation
        drip = curr_div if reinvestir_div else 0.0

        curr_val = curr_val + ganho_capital + novos_aportes + drip
        yield_base = portfolio_yield / 100.0 if portfolio_yield > 0 else 0.035
        curr_div = (curr_div * (1 + div_growth_rate)) + (
            (novos_aportes + drip) * yield_base
        )

    with col_graph:
        fig_sim = go.Figure()
        fig_sim.add_trace(
            go.Scatter(
                x=anos_lista,
                y=proj_valor,
                name=f"Valor do Portfólio ({MOEDA})",
                line=dict(color="#58a6ff", width=3),
                fill="tozeroy",
            )
        )
        fig_sim.add_trace(
            go.Scatter(
                x=anos_lista,
                y=proj_dividendos,
                name=f"Dividendo Anual ({MOEDA})",
                line=dict(color="#00e676", width=2),
                yaxis="y2",
            )
        )

        fig_sim.update_layout(
            title="Efeito Bola de Neve (Património vs Rendimento Passivo)",
            yaxis=dict(title=f"Valor Total ({MOEDA})"),
            yaxis2=dict(
                title=f"Dividendo Anual ({MOEDA})",
                overlaying="y",
                side="right",
            ),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#c9d1d9"),
            legend=dict(x=0.05, y=0.95),
            height=380,
        )
        st.plotly_chart(fig_sim, use_container_width=True)

        st.info(
            f"💡 Em **{anos} anos**, o teu portfólio está projetado para atingir **{proj_valor[-1]:,.2f} {MOEDA}**, "
            f"gerando um rendimento anual em dividendos de **{proj_dividendos[-1]:,.2f} {MOEDA}** "
            f"(~**{proj_dividendos[-1]/12:,.2f} {MOEDA} por mês**)."
        )