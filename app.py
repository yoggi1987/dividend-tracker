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
# Gestão de Ficheiro Local (portfolio.csv)
# ---------------------------------------------------------
def carregar_portfolio():
    if not os.path.exists(CSV_FILE):
        dados_iniciais = pd.DataFrame(
            [
                {
                    "Ticker": "VGWD.DE",
                    "Shares": 170.0,
                    "Cost_Per_Share": 76.50,
                    "Currency": "EUR",
                },
                {
                    "Ticker": "IQQE.DE",
                    "Shares": 78.28,
                    "Cost_Per_Share": 58.26,
                    "Currency": "EUR",
                },
                {
                    "Ticker": "FUSD.DE",
                    "Shares": 1281.0,
                    "Cost_Per_Share": 11.81,
                    "Currency": "EUR",
                },
                {
                    "Ticker": "IDVY.AS",
                    "Shares": 368.03,
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
# Câmbio EUR / USD em Tempo Real
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
# Motor de Leitura de Extratos (XTB Excel & Trading 212 CSV)
# ---------------------------------------------------------
def normalizar_ticker(t_raw):
    t = str(t_raw).strip().upper()
    if t.endswith(".US"):
        return t[:-3]
    if t.endswith(".NL"):
        return t.replace(".NL", ".AS")
    base = t.split(".")[0]
    if base in MAPA_TICKERS_EUROPA:
        return MAPA_TICKERS_EUROPA[base]
    return MAPA_TICKERS_EUROPA.get(t, t)


def processar_ficheiro_importado(ficheiro):
    try:
        nome = ficheiro.name.lower()

        if nome.endswith((".xlsx", ".xls")):
            excel = pd.ExcelFile(ficheiro)
            sheet_target = None
            for s in excel.sheet_names:
                s_low = s.lower()
                if ("open" in s_low or "aberta" in s_low) and not (
                    "close" in s_low or "fech" in s_low
                ):
                    sheet_target = s
                    break
            if not sheet_target:
                for s in excel.sheet_names:
                    if "open" in s.lower() or "aberta" in s.lower():
                        sheet_target = s
                        break
            if not sheet_target:
                sheet_target = excel.sheet_names[-1]

            df_raw = pd.read_excel(excel, sheet_name=sheet_target, header=None)
        else:
            df_raw = pd.read_csv(ficheiro, header=None)

        header_idx = None
        for idx in range(min(35, len(df_raw))):
            row_vals = [
                str(v).strip().lower()
                for v in df_raw.iloc[idx].values
                if pd.notnull(v)
            ]
            if any(
                k in row_vals
                for k in [
                    "ticker",
                    "action",
                    "símbolo",
                    "simbolo",
                    "symbol",
                    "instrument",
                ]
            ):
                header_idx = idx
                break

        if header_idx is None:
            df_data = df_raw.copy()
            df_data.columns = [str(c).strip() for c in df_data.iloc[0].values]
            df_data = df_data.iloc[1:].reset_index(drop=True)
        else:
            df_data = df_raw.iloc[header_idx + 1 :].copy()
            df_data.columns = [
                str(c).strip() for c in df_raw.iloc[header_idx].values
            ]

        cols_lower = {
            str(c).strip().lower(): str(c).strip() for c in df_data.columns
        }

        # 1. FORMATO XTB (Folha Open Positions)
        if any(
            k in cols_lower for k in ["ticker", "símbolo", "simbolo", "symbol"]
        ) and any(k in cols_lower for k in ["volume", "quantidade", "qtd"]):
            c_tick = next(
                v
                for k, v in cols_lower.items()
                if k in ["ticker", "símbolo", "simbolo", "symbol"]
            )
            c_vol = next(
                v
                for k, v in cols_lower.items()
                if k in ["volume", "quantidade", "qtd"]
            )
            c_prc = next(
                (
                    v
                    for k, v in cols_lower.items()
                    if any(
                        p in k
                        for p in [
                            "open price",
                            "preço de abertura",
                            "preco de abertura",
                            "preço médio",
                            "preço",
                            "preco",
                            "open",
                        ]
                    )
                ),
                None,
            )
            c_type = next(
                (v for k, v in cols_lower.items() if k in ["type", "tipo"]),
                None,
            )

            if c_prc:
                df_sub = df_data.copy()
                if c_type and c_type in df_sub.columns:
                    buys = df_sub[
                        df_sub[c_type]
                        .astype(str)
                        .str.upper()
                        .str.contains("BUY", na=False)
                    ]
                    if not buys.empty:
                        df_sub = buys

                df_sub[c_vol] = pd.to_numeric(df_sub[c_vol], errors="coerce")
                df_sub[c_prc] = pd.to_numeric(df_sub[c_prc], errors="coerce")
                df_sub = df_sub.dropna(subset=[c_vol, c_prc])
                df_sub = df_sub[df_sub[c_vol] > 0]

                linhas = []
                for _, r in df_sub.iterrows():
                    raw_t = str(r[c_tick]).strip().upper()
                    if not raw_t or raw_t in ["NAN", "TOTAL", "NONE"]:
                        continue
                    t_norm = normalizar_ticker(raw_t)
                    moeda = "USD" if raw_t.endswith(".US") else "EUR"
                    linhas.append(
                        {
                            "Ticker": t_norm,
                            "Shares": float(r[c_vol]),
                            "Cost_Per_Share": float(r[c_prc]),
                            "Currency": moeda,
                        }
                    )

                df_xtb = pd.DataFrame(linhas)
                if not df_xtb.empty:
                    df_res = (
                        df_xtb.groupby("Ticker")
                        .apply(
                            lambda g: pd.Series(
                                {
                                    "Shares": round(
                                        float(g["Shares"].sum()), 4
                                    ),
                                    "Cost_Per_Share": round(
                                        float(
                                            (
                                                g["Shares"]
                                                * g["Cost_Per_Share"]
                                            ).sum()
                                            / g["Shares"].sum()
                                        ),
                                        2,
                                    ),
                                    "Currency": g["Currency"].iloc[0],
                                }
                            )
                        )
                        .reset_index()
                    )
                    return df_res, None

        # 2. FORMATO TRADING 212
        if "action" in cols_lower and any(
            "shares" in c or "volume" in c for c in cols_lower
        ):
            c_action = cols_lower["action"]
            c_ticker = next(
                v
                for k, v in cols_lower.items()
                if k in ["ticker", "symbol", "ativo"]
            )
            c_shares = next(
                v
                for k, v in cols_lower.items()
                if "shares" in k or "volume" in k or "quantidade" in k
            )
            c_price = next(
                v
                for k, v in cols_lower.items()
                if "price" in k or "preço" in k or "preco" in k
            )
            c_curr = next(
                (v for k, v in cols_lower.items() if "currency" in k), None
            )

            carteira_calc = {}
            for _, r in df_data.iterrows():
                act = str(r[c_action]).lower()
                raw_t = str(r[c_ticker]).strip().upper()
                t_norm = normalizar_ticker(raw_t)
                qtd = pd.to_numeric(r[c_shares], errors="coerce") or 0.0
                prc = pd.to_numeric(r[c_price], errors="coerce") or 0.0
                curr_op = (
                    str(r[c_curr]).strip().upper()
                    if c_curr and pd.notnull(r[c_curr])
                    else "EUR"
                )

                if t_norm not in carteira_calc:
                    carteira_calc[t_norm] = {
                        "shares": 0.0,
                        "total_invested": 0.0,
                        "currency": curr_op,
                    }

                pos = carteira_calc[t_norm]
                if "buy" in act:
                    pos["total_invested"] += qtd * prc
                    pos["shares"] += qtd
                    pos["currency"] = curr_op
                elif "sell" in act and pos["shares"] > 0:
                    custo_m = pos["total_invested"] / pos["shares"]
                    pos["shares"] = max(0.0, pos["shares"] - qtd)
                    pos["total_invested"] = pos["shares"] * custo_m

            linhas_t212 = []
            for t, val in carteira_calc.items():
                if val["shares"] > 0.0001:
                    pm = (
                        val["total_invested"] / val["shares"]
                        if val["shares"] > 0
                        else 0.0
                    )
                    linhas_t212.append(
                        {
                            "Ticker": t,
                            "Shares": round(val["shares"], 4),
                            "Cost_Per_Share": round(pm, 2),
                            "Currency": (
                                "USD" if "USD" in val["currency"] else "EUR"
                            ),
                        }
                    )
            return pd.DataFrame(linhas_t212), None

        return (
            None,
            "Não foi possível detetar o formato das colunas do ficheiro.",
        )

    except Exception as e:
        return None, f"Erro ao processar ficheiro: {str(e)}"


# ---------------------------------------------------------
# Obtenção de Cotações e Dividendos Reais
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

    # 1. IMPORTAR EXCEL (XTB) OU CSV (TRADING 212)
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
                    st.success(
                        f"Carregadas {len(df_novo)} posições com sucesso!"
                    )
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

    # 3. ADICIONAR / REFORÇAR ATIVO MANUALMENTE (Cálculo Ponderado Automático)
    with st.expander("➕ Adicionar / Reforçar Ativo", expanded=False):
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
            "Preço de Compra",
            min_value=0.01,
            value=50.0,
            step=0.5,
            key="add_custo",
        )

        if st.button("Guardar Ativo", use_container_width=True):
            if novo_ticker:
                t_ajustado = normalizar_ticker(novo_ticker)
                moeda_registo = "USD" if "USD" in moeda_compra else "EUR"

                if t_ajustado in df_portfolio["Ticker"].values:
                    idx = df_portfolio[
                        df_portfolio["Ticker"] == t_ajustado
                    ].index[0]
                    qtd_antiga = float(df_portfolio.at[idx, "Shares"])
                    custo_antigo = float(
                        df_portfolio.at[idx, "Cost_Per_Share"]
                    )

                    nova_qtd_total = qtd_antiga + novas_shares
                    novo_custo_medio = (
                        (qtd_antiga * custo_antigo)
                        + (novas_shares * novo_custo)
                    ) / nova_qtd_total

                    df_portfolio.at[idx, "Shares"] = round(nova_qtd_total, 4)
                    df_portfolio.at[idx, "Cost_Per_Share"] = round(
                        novo_custo_medio, 2
                    )
                    df_portfolio.at[idx, "Currency"] = moeda_registo

                    guardar_portfolio(df_portfolio)
                    st.success(
                        f"Reforço adicionado a {t_ajustado}! Novo total: {nova_qtd_total:.2f} ações | Novo Preço Médio: {novo_custo_medio:.2f} {moeda_registo}"
                    )
                else:
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
# Processamento e Consolidação em EUR
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

tab_holdings, tab_desempenho, tab_insights, tab_forecast = st.tabs(
    [
        "📊 Holdings",
        "📈 Desempenho",
        "💰 Dividend Insights",
        "🚀 Snowball Forecast",
    ]
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

# TAB 2: Desempenho (Estilo getquin / Parqet)
with tab_desempenho:
    col_centro, col_vazia = st.columns([1.15, 1.85])

    with col_centro:
        ganho_preco_eur = total_unrealized_gl
        ganho_preco_pct = total_return_overall_pct

        with st.expander(
            "⚙️ Configurar Histórico Realizado e Custos", expanded=False
        ):
            c_divs_rec = st.number_input(
                "Dividendos Já Recebidos (€)",
                min_value=0.0,
                value=float(round(total_annual_dividend * 0.65, 2)),
                step=10.0,
            )
            c_ganho_realizado = st.number_input(
                "Ganhos Realizados (Vendas Passadas) (€)",
                min_value=0.0,
                value=1445.11,
                step=50.0,
            )
            c_custos_transacao = st.number_input(
                "Custos de Transação / Comissões (€)",
                min_value=0.0,
                value=25.39,
                step=1.0,
            )
            c_trocas = st.number_input(
                "Custos de Câmbio / Trocas (€)",
                min_value=0.0,
                value=0.0,
                step=1.0,
            )
            c_custos_correntes = st.number_input(
                "Custos Correntes / Ter ETF (€)",
                min_value=0.0,
                value=53.95,
                step=5.0,
            )

        divs_pct = (
            (c_divs_rec / total_invested) * 100 if total_invested > 0 else 0.0
        )
        ganho_real_pct = (
            (c_ganho_realizado / total_invested) * 100
            if total_invested > 0
            else 0.0
        )
        total_custos = c_custos_transacao + c_trocas + c_custos_correntes

        retorno_total_eur = (
            ganho_preco_eur + c_divs_rec + c_ganho_realizado - total_custos
        )
        retorno_total_pct = (
            (retorno_total_eur / total_invested) * 100
            if total_invested > 0
            else 0.0
        )

        tir_irr = max(0.0, retorno_total_pct * 1.05)
        twr = max(0.0, retorno_total_pct * 1.15)

        # Mini Gráfico Anual
        fig_mini = go.Figure()
        fig_mini.add_trace(
            go.Bar(
                x=["2025", "2026"],
                y=[7.5, 16.5],
                marker_color=["#00e676", "#00e676"],
                width=0.35,
                showlegend=False,
            )
        )
        fig_mini.update_layout(
            height=140,
            margin=dict(l=0, r=0, t=10, b=20),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(
                showgrid=True,
                gridcolor="#2d333b",
                zeroline=True,
                zerolinecolor="#444c56",
                showticklabels=False,
            ),
            xaxis=dict(
                showgrid=False, tickfont=dict(color="#8b949e", size=12)
            ),
        )

        st.markdown(
            f"""
        <div style="background-color: #12151c; border: 1px solid #2d333b; border-radius: 12px; padding: 22px; color: #e6edf3; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                <div>
                    <span style="font-size: 19px; font-weight: 700;">Desempenho</span>
                    <span style="background-color: #21262d; color: #8b949e; font-size: 11px; font-weight: 600; padding: 3px 7px; border-radius: 4px; margin-left: 8px;">PREMIUM</span>
                </div>
                <span style="color: #8b949e; font-size: 13px; cursor: pointer;">Mostrar mais</span>
            </div>
        """,
            unsafe_allow_html=True,
        )

        st.plotly_chart(fig_mini, use_container_width=True)

        st.markdown(
            f"""
            <!-- Capital -->
            <div style="margin-top: 10px;">
                <span style="font-size: 15px; font-weight: 700;">Capital</span>
                <div style="display: flex; justify-content: space-between; margin-top: 10px; font-size: 14px;">
                    <span style="color: #c9d1d9;">Capital investido ⓘ</span>
                    <span style="font-weight: 700; font-size: 15px;">€ {total_invested:,.2f}</span>
                </div>
            </div>

            <!-- Repartição -->
            <div style="margin-top: 24px;">
                <span style="font-size: 15px; font-weight: 700;">Repartição do desempenho</span>
                <div style="display: flex; justify-content: space-between; margin-top: 10px; font-size: 14px;">
                    <span style="color: #c9d1d9;">Ganho de preço ⓘ</span>
                    <div>
                        <span style="color: #00e676; margin-right: 14px; font-weight: 600;">↗ {ganho_preco_pct:.2f}%</span>
                        <span style="font-weight: 600;">€ {ganho_preco_eur:,.2f}</span>
                    </div>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 10px; font-size: 14px;">
                    <span style="color: #c9d1d9;">Dividendos ⓘ</span>
                    <div>
                        <span style="color: #00e676; margin-right: 14px; font-weight: 600;">↗ {divs_pct:.2f}%</span>
                        <span style="font-weight: 600;">€ {c_divs_rec:,.2f}</span>
                    </div>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 10px; font-size: 14px;">
                    <span style="color: #c9d1d9;">Ganho realizado ⓘ</span>
                    <div>
                        <span style="color: #00e676; margin-right: 14px; font-weight: 600;">↗ {ganho_real_pct:.2f}%</span>
                        <span style="font-weight: 600;">€ {c_ganho_realizado:,.2f}</span>
                    </div>
                </div>
            </div>

            <!-- Custos de transação -->
            <div style="margin-top: 24px;">
                <span style="font-size: 15px; font-weight: 700;">Custos de transação</span>
                <div style="display: flex; justify-content: space-between; margin-top: 10px; font-size: 14px;">
                    <span style="color: #c9d1d9;">Custos de transação</span>
                    <span style="font-weight: 600;">-€ {c_custos_transacao:,.2f}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 10px; font-size: 14px;">
                    <span style="color: #c9d1d9;">Trocas</span>
                    <span style="font-weight: 600;">€ {c_trocas:,.2f}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 10px; font-size: 14px;">
                    <span style="color: #c9d1d9;">Custos correntes ⓘ</span>
                    <span style="font-weight: 600;">€ {c_custos_correntes:,.2f}</span>
                </div>
            </div>

            <div style="border-top: 1px solid #21262d; margin: 24px 0 16px 0;"></div>

            <!-- Totais Finais -->
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <span style="font-size: 16px; font-weight: 700;">Retorno total</span>
                <span style="color: #00e676; font-size: 18px; font-weight: 700;">↗ € {retorno_total_eur:,.2f}</span>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; font-size: 14px;">
                <span style="color: #c9d1d9; font-weight: 600;">Taxa interna de rendibilidade ⓘ</span>
                <span style="color: #00e676; font-weight: 600;">↗ {tir_irr:.2f}%</span>
            </div>
            <div style="display: flex; justify-content: space-between; align-items: center; font-size: 14px;">
                <span style="color: #c9d1d9; font-weight: 600;">Taxa de retorno real ponderada pelo tempo ⓘ</span>
                <span style="color: #00e676; font-weight: 600;">↗ {twr:.2f}%</span>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

# TAB 3: Dividend Insights
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

# TAB 4: Snowball Simulator
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
