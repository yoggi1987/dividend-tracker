import io
import os
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# ---------------------------------------------------------
# Configuração da Página e Moeda Base
# ---------------------------------------------------------
st.set_page_config(
    page_title="Dividend Portfolio Tracker",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

MOEDA_BASE = "€"
CSV_FILE = "portfolio.csv"

MAPA_TICKERS_EUROPA = {
    "FUSD": "FUSD.DE",
    "IDVY": "IDVY.AS",
    "VGWD": "VGWD.DE",
    "VHYL": "VHYL.AS",
    "IQQE": "IQQE.DE",
    "VWCE": "VWCE.DE",
    "QDVE": "QDVE.DE",
    "VUAA": "VUAA.DE",
    "SXR8": "SXR8.DE",
    "IS3N": "IS3N.DE",
    "EUNL": "EUNL.DE",
    "VUSA": "VUSA.AS",
}

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
# Gestão de Ficheiro Local
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
                {
                    "Ticker": "FUSD.DE",
                    "Shares": 1282.0,
                    "Cost_Per_Share": 11.81,
                    "Currency": "EUR",
                },
                {
                    "Ticker": "IDVY.AS",
                    "Shares": 368.04,
                    "Cost_Per_Share": 25.47,
                    "Currency": "EUR",
                },
                {
                    "Ticker": "VICI",
                    "Shares": 7.0,
                    "Cost_Per_Share": 22.01,
                    "Currency": "USD",
                },
            ]
        )
        dados_iniciais.to_csv(CSV_FILE, index=False)
        return dados_iniciais

    df = pd.read_csv(CSV_FILE)
    if "Currency" not in df.columns:
        df["Currency"] = "EUR"
    return df


def guardar_portfolio(df):
    df.to_csv(CSV_FILE, index=False)


# ---------------------------------------------------------
# Câmbio EUR / USD
# ---------------------------------------------------------
@st.cache_data(ttl=600)
def obter_taxa_eur_usd():
    try:
        forex = yf.Ticker("EURUSD=X")
        taxa = forex.fast_info.last_price or 1.16
        return taxa
    except Exception:
        return 1.16


# ---------------------------------------------------------
# Motor de Leitura de Extratos (CSV & Excel / XTB / Trading 212)
# ---------------------------------------------------------
def normalizar_ticker_xtb(ticker_raw):
    t = str(ticker_raw).strip().upper()
    if t.endswith(".US"):
        return t[:-3]  # Remove .US (ex: VICI.US -> VICI)
    if t.endswith(".NL"):
        return t.replace(".NL", ".AS")
    return MAPA_TICKERS_EUROPA.get(t, t)


def processar_ficheiro_importado(ficheiro):
    try:
        nome = ficheiro.name.lower()

        # Leitura de Ficheiro Excel (.xlsx / .xls)
        if nome.endswith((".xlsx", ".xls")):
            excel = pd.ExcelFile(ficheiro)
            df_raw = None

            # Procura abas de posições abertas típicas da XTB
            for sheet in excel.sheet_names:
                s_limpa = sheet.strip().upper()
                if "ABERTA" in s_limpa or "OPEN" in s_limpa or "POSI" in s_limpa:
                    df_raw = pd.read_excel(excel, sheet_name=sheet)
                    break

            if df_raw is None:
                df_raw = pd.read_excel(excel, sheet_name=0)

        else:
            df_raw = pd.read_csv(ficheiro)

        # Limpeza de nomes de colunas
        df_raw.columns = [str(c).strip() for c in df_raw.columns]
        colunas = df_raw.columns.tolist()

        # CASO 1: RELATÓRIO XTB (Aba Posições Abertas)
        col_xtb_ticker = next(
            (c for c in colunas if c.upper() in ["SÍMBOLO", "SIMBOLO", "SYMBOL"]),
            None,
        )
        col_xtb_volume = next(
            (c for c in colunas if c.upper() in ["VOLUME", "QUANTIDADE", "QTD"]),
            None,
        )
        col_xtb_preco = next(
            (
                c
                for c in colunas
                if "PREÇO DE ABERTURA" in c.upper()
                or "OPEN PRICE" in c.upper()
                or "PREÇO MÉDIO" in c.upper()
            ),
            None,
        )

        if col_xtb_ticker and col_xtb_volume and col_xtb_preco:
            linhas = []
            for _, row in df_raw.iterrows():
                t_raw = str(row[col_xtb_ticker]).strip()
                if not t_raw or t_raw.lower() in ["nan", "total"]:
                    continue

                t_final = normalizar_ticker_xtb(t_raw)
                qtd = pd.to_numeric(row[col_xtb_volume], errors="coerce") or 0.0
                preco = pd.to_numeric(row[col_xtb_preco], errors="coerce") or 0.0

                moeda = "USD" if str(t_raw).endswith(".US") else "EUR"

                if qtd > 0:
                    linhas.append(
                        {
                            "Ticker": t_final,
                            "Shares": round(float(qtd), 4),
                            "Cost_Per_Share": round(float(preco), 2),
                            "Currency": moeda,
                        }
                    )

            if linhas:
                df_xtb = pd.DataFrame(linhas)
                # Agrupa se tiver ordens fracionadas do mesmo ativo
                df_xtb_group = (
                    df_xtb.groupby("Ticker")
                    .apply(
                        lambda g: pd.Series(
                            {
                                "Shares": g["Shares"].sum(),
                                "Cost_Per_Share": (
                                    g["Shares"] * g["Cost_Per_Share"]
                                ).sum()
                                / g["Shares"].sum(),
                                "Currency": g["Currency"].iloc[0],
                            }
                        )
                    )
                    .reset_index()
                )
                return df_xtb_group, None

        # CASO 2: EXTRATO TRADING 212
        if "Action" in colunas and (
            "No. of shares" in colunas or "Shares" in colunas
        ):
            col_shares = (
                "No. of shares" if "No. of shares" in colunas else "Shares"
            )
            col_price = (
                "Price / share" if "Price / share" in colunas else "Price"
            )
            col_curr = next(
                (c for c in colunas if "Currency" in c and "Price" in c),
                "Currency (Price / share)",
            )

            carteira_calc = {}
            for _, row in df_raw.iterrows():
                acao = str(row["Action"]).lower()
                ticker_orig = str(row["Ticker"]).strip().upper()
                ticker = MAPA_TICKERS_EUROPA.get(ticker_orig, ticker_orig)
                qtd = float(row[col_shares]) if pd.notnull(row[col_shares]) else 0.0
                preco = (
                    float(row[col_price]) if pd.notnull(row[col_price]) else 0.0
                )
                moeda_op = (
                    str(row[col_curr]).strip().upper()
                    if col_curr in df_raw.columns and pd.notnull(row[col_curr])
                    else "EUR"
                )

                if ticker not in carteira_calc:
                    carteira_calc[ticker] = {
                        "shares": 0.0,
                        "total_invested": 0.0,
                        "currency": moeda_op,
                    }

                pos = carteira_calc[ticker]
                if "buy" in acao:
                    pos["total_invested"] += qtd * preco
                    pos["shares"] += qtd
                    pos["currency"] = moeda_op
                elif "sell" in acao and pos["shares"] > 0:
                    custo_medio = pos["total_invested"] / pos["shares"]
                    pos["shares"] = max(0.0, pos["shares"] - qtd)
                    pos["total_invested"] = pos["shares"] * custo_medio

            linhas = []
            for t, val in carteira_calc.items():
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
                            "Currency": (
                                "USD" if "USD" in val["currency"] else "EUR"
                            ),
                        }
                    )
            return pd.DataFrame(linhas), None

        # CASO 3: MODELO PADRÃO
        t_col = next(
            (c for c in colunas if c.lower() in ["ticker", "symbol", "ativo"]),
            None,
        )
        s_col = next(
            (
                c
                for c in colunas
                if c.lower() in ["shares", "acoes", "ações", "qtd", "quantidade"]
            ),
            None,
        )
        c_col = next(
            (
                c
                for c in colunas
                if c.lower()
                in ["cost_per_share", "cost", "preco_medio", "custo"]
            ),
            None,
        )
        curr_col = next(
            (c for c in colunas if c.lower() in ["currency", "moeda"]), None
        )

        if t_col and s_col and c_col:
            df_res = pd.DataFrame()
            df_res["Ticker"] = (
                df_raw[t_col]
                .astype(str)
                .str.strip()
                .str.upper()
                .apply(normalizar_ticker_xtb)
            )
            df_res["Shares"] = pd.to_numeric(df_raw[s_col], errors="coerce").fillna(0.0)
            df_res["Cost_Per_Share"] = pd.to_numeric(df_raw[c_col], errors="coerce").fillna(0.0)
            df_res["Currency"] = (
                df_raw[curr_col]
                .astype(str)
                .str.upper()
                .apply(lambda c: "USD" if "USD" in c else "EUR")
                if curr_col
                else "EUR"
            )
            return df_res[df_res["Shares"] > 0], None

        return (
            None,
            f"Colunas não reconhecidas. Foram encontradas: {', '.join(colunas[:6])}",
        )

    except Exception as e:
        return None, f"Erro ao processar ficheiro: {str(e)}"


# ---------------------------------------------------------
# Cotações e Dividendos Reais
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

            div_rate = info.get("dividendRate", 0.0) or 0.0
            div_yield = info.get("dividendYield", 0.0) or 0.0

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

            if div_rate > 0 and sum(pagamentos_mes.values()) == 0:
                for m in range(1, 13):
                    pagamentos_mes[m] = div_rate / 12.0

            if div_yield == 0.0 and div_rate > 0 and preco > 0:
                div_yield = div_rate / preco
            elif div_rate == 0.0 and div_yield > 0 and preco > 0:
                div_rate = preco * div_yield

            moeda_ativo = fast_info.currency or info.get("currency", "EUR")
            moeda_ativo = moeda_ativo.upper()
            nome = info.get("shortName", t)

            dados[t] = {
                "Name": nome,
                "Price_Native": preco,
                "Prev_Close_Native": preco_anterior,
                "Day_Change_Pct": variacao_dia_pct,
                "Annual_Div_Native": div_rate,
                "Div_Yield": div_yield,
                "Monthly_Schedule_Native": pagamentos_mes,
                "Currency_Native": moeda_ativo,
            }
        except Exception:
            dados[t] = {
                "Name": t,
                "Price_Native": 0.0,
                "Prev_Close_Native": 0.0,
                "Day_Change_Pct": 0.0,
                "Annual_Div_Native": 0.0,
                "Div_Yield": 0.0,
                "Monthly_Schedule_Native": {m: 0.0 for m in range(1, 13)},
                "Currency_Native": "EUR",
            }
    return dados


# ---------------------------------------------------------
# Sidebar: Gestão de Carteira & Importação
# ---------------------------------------------------------
df_portfolio = carregar_portfolio()
taxa_eur_usd = obter_taxa_eur_usd()

with st.sidebar:
    st.header("⚙️ Gestor de Carteira")
    st.caption(f"💱 Câmbio atual: **1 EUR = {taxa_eur_usd:.4f} USD**")

    # 1. IMPORTAR (XLSX / CSV)
    with st.expander("📥 Importar Relatório (XTB / T212)", expanded=True):
        st.write("Suporta **Excel da XTB (`.xlsx`)** ou **CSV da Trading 212**.")
        uploaded_file = st.file_uploader(
            "Seleciona o ficheiro",
            type=["xlsx", "xls", "csv"],
            key="file_up",
        )
        tipo_import = st.radio(
            "Método de Importação:",
            ["Fundir / Adicionar", "Substituir Carteira"],
            index=0,
        )

        if uploaded_file is not None:
            if st.button("Executar Importação", use_container_width=True):
                df_novo, erro = processar_ficheiro_importado(uploaded_file)
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
                    st.success(f"Carregadas {len(df_novo)} posições!")
                    st.cache_data.clear()
                    st.rerun()

    # 2. EDITAR / CORRIGIR ATIVO
    with st.expander("✏️ Editar / Corrigir Ativo", expanded=False):
        if not df_portfolio.empty:
            ticker_para_editar = st.selectbox(
                "Seleciona a posição:", options=df_portfolio["Ticker"].tolist()
            )
            idx_ativo = df_portfolio[
                df_portfolio["Ticker"] == ticker_para_editar
            ].index[0]
            linha_atual = df_portfolio.loc[idx_ativo]

            novo_nome_ticker = (
                st.text_input("Ticker", value=str(linha_atual["Ticker"]))
                .strip()
                .upper()
            )
            novas_shares_edit = st.number_input(
                "N.º de Ações",
                min_value=0.0001,
                value=float(linha_atual["Shares"]),
                step=1.0,
            )
            novo_custo_edit = st.number_input(
                "Preço Médio de Compra",
                min_value=0.01,
                value=float(linha_atual["Cost_Per_Share"]),
                step=0.1,
            )
            moeda_edit = st.selectbox(
                "Moeda do Preço Médio",
                options=["EUR", "USD"],
                index=0
                if str(linha_atual.get("Currency", "EUR")) == "EUR"
                else 1,
            )

            if st.button("Atualizar Posição", use_container_width=True):
                df_portfolio.at[idx_ativo, "Ticker"] = novo_nome_ticker
                df_portfolio.at[idx_ativo, "Shares"] = novas_shares_edit
                df_portfolio.at[idx_ativo, "Cost_Per_Share"] = novo_custo_edit
                df_portfolio.at[idx_ativo, "Currency"] = moeda_edit
                guardar_portfolio(df_portfolio)
                st.success(f"{novo_nome_ticker} atualizado!")
                st.cache_data.clear()
                st.rerun()

    # 3. ADICIONAR NOVO ATIVO MANUALMENTE
    with st.expander("➕ Adicionar Novo Ativo", expanded=False):
        novo_ticker = (
            st.text_input("Ticker (ex: AAPL, O, VGWD.DE)")
            .strip()
            .upper()
        )
        novas_shares = st.number_input(
            "N.º de Ações / Unidades",
            min_value=0.0001,
            value=10.0,
            step=1.0,
            key="add_shares",
        )
        moeda_compra = st.selectbox(
            "Moeda do Preço de Compra",
            options=["EUR (€)", "USD ($)"],
            index=0,
            key="add_moeda",
        )
        novo_custo = st.number_input(
            "Preço Médio de Compra",
            min_value=0.01,
            value=50.0,
            step=0.5,
            key="add_custo",
        )

        if st.button("Guardar Ativo", use_container_width=True):
            if novo_ticker:
                t_ajustado = MAPA_TICKERS_EUROPA.get(novo_ticker, novo_ticker)
                if t_ajustado in df_portfolio["Ticker"].values:
                    st.warning("O ativo já se encontra registado.")
                else:
                    moeda_registo = "USD" if "USD" in moeda_compra else "EUR"
                    nova_linha = pd.DataFrame(
                        [
                            {
                                "Ticker": t_ajustado,
                                "Shares": novas_shares,
                                "Cost_Per_Share": novo_custo,
                                "Currency": moeda_registo,
                            }
                        ]
                    )
                    df_portfolio = pd.concat(
                        [df_portfolio, nova_linha], ignore_index=True
                    )
                    guardar_portfolio(df_portfolio)
                    st.success(f"{t_ajustado} adicionado!")
                    st.cache_data.clear()
                    st.rerun()

    # 4. REMOVER ATIVO
    with st.expander("🗑️ Remover Ativo", expanded=False):
        if not df_portfolio.empty:
            ticker_remover = st.selectbox(
                "Seleciona para eliminar",
                options=df_portfolio["Ticker"].tolist(),
                key="del_sel",
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
# Processamento e Consolidação dos Dados em EUR
# ---------------------------------------------------------
tickers_lista = df_portfolio["Ticker"].tolist()
market_data = obter_dados_mercado(tickers_lista)

dados_processados = []
distribuicao_mensal_eur = {m: 0.0 for m in range(1, 13)}

for _, row in df_portfolio.iterrows():
    t = row["Ticker"]
    shares = float(row["Shares"])
    cost_input = float(row["Cost_Per_Share"])
    currency_input = row.get("Currency", "EUR")

    m_info = market_data.get(t, {})
    curr_price_native = m_info.get("Price_Native", 0.0)
    prev_close_native = m_info.get(
        "Prev_Close_Native", curr_price_native
    )
    day_pct = m_info.get("Day_Change_Pct", 0.0)
    annual_div_native = m_info.get("Annual_Div_Native", 0.0)
    div_yield = m_info.get("Div_Yield", 0.0) * 100
    native_currency = m_info.get("Currency_Native", "EUR")
    monthly_sched_native = m_info.get("Monthly_Schedule_Native", {})

    fator_conversao_eur = (
        (1.0 / taxa_eur_usd) if native_currency == "USD" else 1.0
    )

    price_eur = curr_price_native * fator_conversao_eur
    prev_close_eur = prev_close_native * fator_conversao_eur
    cost_eur = (
        (cost_input / taxa_eur_usd)
        if currency_input == "USD"
        else cost_input
    )

    invested_eur = shares * cost_eur
    mkt_value_eur = shares * price_eur
    unrealized_gl_eur = mkt_value_eur - invested_eur
    total_return_pct = (
        (unrealized_gl_eur / invested_eur) * 100 if invested_eur > 0 else 0.0
    )
    day_gl_eur = (
        shares * (price_eur - prev_close_eur) if price_eur > 0 else 0.0
    )

    annual_dividend_eur = shares * (annual_div_native * fator_conversao_eur)
    yoc = (
        (annual_dividend_eur / invested_eur) * 100 if invested_eur > 0 else 0.0
    )

    for m in range(1, 13):
        distribuicao_mensal_eur[m] += (
            monthly_sched_native.get(m, 0.0)
            * fator_conversao_eur
            * shares
        )

    dados_processados.append(
        {
            "Ticker": t,
            "Moeda": native_currency,
            "Shares": shares,
            "Preço Original": f"{curr_price_native:,.2f} {'$' if native_currency=='USD' else '€'}",
            "Preço (€)": price_eur,
            "Custo Médio (€)": cost_eur,
            "Investido (€)": invested_eur,
            "Valor Mercado (€)": mkt_value_eur,
            "Variação Dia %": day_pct,
            "Ganho Dia (€)": day_gl_eur,
            "Retorno Total (€)": unrealized_gl_eur,
            "Retorno Total %": total_return_pct,
            "Dividendo Anual (€)": annual_dividend_eur,
            "Dividend Yield %": div_yield,
            "Yield on Cost %": yoc,
        }
    )

df_view = pd.DataFrame(dados_processados)

total_invested = (
    df_view["Investido (€)"].sum() if not df_view.empty else 0.0
)
total_mkt_value = (
    df_view["Valor Mercado (€)"].sum() if not df_view.empty else 0.0
)
total_unrealized_gl = total_mkt_value - total_invested
total_return_overall_pct = (
    (total_unrealized_gl / total_invested) * 100 if total_invested > 0 else 0.0
)
total_day_gl = (
    df_view["Ganho Dia (€)"].sum() if not df_view.empty else 0.0
)
total_annual_dividend = (
    df_view["Dividendo Anual (€)"].sum() if not df_view.empty else 0.0
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
    df_view["Peso %"] = (df_view["Valor Mercado (€)"] / total_mkt_value) * 100
else:
    df_view["Peso %"] = 0.0

# ---------------------------------------------------------
# Layout Principal
# ---------------------------------------------------------
st.title("💼 Dividend Portfolio Tracker (Consolidado em €)")

m1, m2, m3, m4, m5 = st.columns(5)
m1.metric(
    label="Valor de Mercado",
    value=f"{total_mkt_value:,.2f} {MOEDA_BASE}",
    delta=f"{total_day_gl:+,.2f} {MOEDA_BASE} hoje",
)
m2.metric(
    label="Total Investido",
    value=f"{total_invested:,.2f} {MOEDA_BASE}",
)
m3.metric(
    label="Retorno Total (G/L)",
    value=f"{total_unrealized_gl:+,.2f} {MOEDA_BASE}",
    delta=f"{total_return_overall_pct:+.2f}%",
)
m4.metric(
    label="Dividendos Anuais",
    value=f"{total_annual_dividend:,.2f} {MOEDA_BASE}",
    delta=f"{total_annual_dividend/12:,.2f} {MOEDA_BASE}/mês",
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
                    "Moeda",
                    "Shares",
                    "Preço Original",
                    "Custo Médio (€)",
                    "Valor Mercado (€)",
                    "Peso %",
                    "Variação Dia %",
                    "Ganho Dia (€)",
                    "Retorno Total (€)",
                    "Retorno Total %",
                    "Yield on Cost %",
                ]
            ].copy()

            st.dataframe(
                df_display.style.format(
                    {
                        "Shares": "{:,.2f}",
                        "Custo Médio (€)": "{:,.2f} €",
                        "Valor Mercado (€)": "{:,.2f} €",
                        "Peso %": "{:.2f}%",
                        "Variação Dia %": "{:+.2f}%",
                        "Ganho Dia (€)": "{:+,.2f} €",
                        "Retorno Total (€)": "{:+,.2f} €",
                        "Retorno Total %": "{:+.2f}%",
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
                        "Variação Dia %",
                        "Ganho Dia (€)",
                        "Retorno Total (€)",
                        "Retorno Total %",
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
                values="Valor Mercado (€)",
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
    st.subheader("Análise dos Proventos Passivos (em €)")
    c1, c2 = st.columns([2, 1])

    with c1:
        if not df_view.empty and total_annual_dividend > 0:
            fig_bar = px.bar(
                df_view.sort_values(
                    by="Dividendo Anual (€)", ascending=False
                ),
                x="Ticker",
                y="Dividendo Anual (€)",
                text_auto=".2f",
                title="Projeção de Renda Anual por Ativo (€)",
                color="Dividendo Anual (€)",
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
            f"• **Rendimento Médio Mensal:** `{total_annual_dividend / 12:,.2f} {MOEDA_BASE}`"
        )
        st.write(
            f"• **Rendimento Médio Diário:** `{total_annual_dividend / 365:,.2f} {MOEDA_BASE}`"
        )
        maior_pagador = (
            df_view.loc[df_view["Dividendo Anual (€)"].idxmax()]["Ticker"]
            if not df_view.empty and total_annual_dividend > 0
            else "N/A"
        )
        st.write(f"• **Maior Pagador:** `{maior_pagador}`")
        st.write(f"• **Dividend Yield da Carteira:** `{portfolio_yield:.2f}%`")
        st.write(f"• **Yield on Cost (YoC):** `{portfolio_yoc:.2f}%`")

    st.markdown("---")
    st.subheader("Calendário de Pagamentos (Meses Reais em €)")
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
    valores_mes = [distribuicao_mensal_eur[m] for m in range(1, 13)]

    fig_months = go.Figure(
        data=[
            go.Bar(
                x=meses,
                y=valores_mes,
                text=[
                    f"{v:,.2f} {MOEDA_BASE}" if v > 0 else ""
                    for v in valores_mes
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
        yaxis_title=f"Rendimento ({MOEDA_BASE})",
    )
    st.plotly_chart(fig_months, use_container_width=True)

# TAB 3: Snowball Simulator
with tab_forecast:
    st.subheader("Simulador Snowball & Compounding (DRIP em €)")
    col_inputs, col_graph = st.columns([1, 2])

    with col_inputs:
        anos = st.slider("Horizonte Temporal (Anos)", 5, 30, 20, 1)
        aporte_mensal = st.number_input(
            f"Aporte Mensal Adicional ({MOEDA_BASE})",
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
                name=f"Valor do Portfólio ({MOEDA_BASE})",
                line=dict(color="#58a6ff", width=3),
                fill="tozeroy",
            )
        )
        fig_sim.add_trace(
            go.Scatter(
                x=anos_lista,
                y=proj_dividendos,
                name=f"Dividendo Anual ({MOEDA_BASE})",
                line=dict(color="#00e676", width=2),
                yaxis="y2",
            )
        )

        fig_sim.update_layout(
            title="Efeito Bola de Neve (Património vs Rendimento Passivo)",
            yaxis=dict(title=f"Valor Total ({MOEDA_BASE})"),
            yaxis2=dict(
                title=f"Dividendo Anual ({MOEDA_BASE})",
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
            f"💡 Em **{anos} anos**, o teu portfólio está projetado para atingir **{proj_valor[-1]:,.2f} {MOEDA_BASE}**, "
            f"gerando um rendimento anual em dividendos de **{proj_dividendos[-1]:,.2f} {MOEDA_BASE}** "
            f"(~**{proj_dividendos[-1]/12:,.2f} {MOEDA_BASE} por mês**)."
        )
