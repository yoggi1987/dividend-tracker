import io
import os
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# ---------------------------------------------------------
# Configuração da Página e Tema
# ---------------------------------------------------------
st.set_page_config(
    page_title="Dividend Portfolio Tracker",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded",
)

MOEDA_BASE = "€"
CSV_FILE = "portfolio.csv"
HIST_FILE = "history_stats.csv"

MAPA_TICKERS_EUROPA = {
    "FUSD": "FUSD.DE",
    "IDVY": "IDVY.AS",
    "VGWD": "VGWD.DE",
    "VGWE": "VGWE.DE",
    "VHYL": "VHYL.AS",
    "IQQE": "IQQE.DE",
    "VWCE": "VWCE.DE",
    "QDVE": "QDVE.DE",
    "VUAA": "VUAA.DE",
    "SXR8": "SXR8.DE",
    "IS3N": "IS3N.DE",
    "EUNL": "EUNL.DE",
    "VUSA": "VUSA.AS",
    "SMH": "SMH.DE",
}

MAPA_PAISES_IRS = {
    "US": "840 - Estados Unidos",
    "IE": "372 - Irlanda",
    "DE": "276 - Alemanha",
    "NL": "528 - Países Baixos",
    "FR": "250 - França",
    "GB": "826 - Reino Unido",
    "JP": "392 - Japão",
    "CN": "156 - China",
    "PT": "620 - Portugal",
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
# Gestão de Estado e Ficheiros Locais
# ---------------------------------------------------------
def carregar_portfolio():
    if not os.path.exists(CSV_FILE):
        dados_iniciais = pd.DataFrame(
            [
                {
                    "Ticker": "VGWD.DE",
                    "Shares": 195.10,
                    "Cost_Per_Share": 77.06,
                    "Currency": "EUR",
                },
                {
                    "Ticker": "IQQE.DE",
                    "Shares": 81.00,
                    "Cost_Per_Share": 58.24,
                    "Currency": "EUR",
                },
                {
                    "Ticker": "FUSD.DE",
                    "Shares": 1282.00,
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
                    "Shares": 7.00,
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


def carregar_stats_historico():
    default_stats = {
        "divs_recebidos": 634.73,
        "ganho_realizado": 1445.11,
        "custos_transacao": 25.39,
        "trocas": 0.00,
        "custos_correntes": 53.95,
        "tir": 14.92,
        "twr": 16.47,
    }
    if os.path.exists(HIST_FILE):
        try:
            df_h = pd.read_csv(HIST_FILE)
            return df_h.iloc[0].to_dict()
        except Exception:
            return default_stats
    return default_stats


def guardar_stats_historico(stats_dict):
    pd.DataFrame([stats_dict]).to_csv(HIST_FILE, index=False)


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
# Motor de Leitura de Extratos (XTB Excel & T212 CSV)
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
        dados_apuramento = {
            "holdings": pd.DataFrame(),
            "closed_trades": [],
            "divs_total": 0.0,
            "realized_pl": 0.0,
            "fees_total": 0.0,
            "tipo_ficheiro": "",
        }

        # CASO 1: RELATÓRIO EXCEL DA XTB (.XLSX)
        if nome.endswith((".xlsx", ".xls")):
            dados_apuramento["tipo_ficheiro"] = "XTB"
            excel = pd.ExcelFile(ficheiro)

            # 1. Posições Abertas (Holdings)
            open_sheet = next(
                (
                    s
                    for s in excel.sheet_names
                    if ("open" in s.lower() or "aberta" in s.lower())
                    and not ("close" in s.lower() or "fech" in s.lower())
                ),
                None,
            )
            if open_sheet:
                df_raw = pd.read_excel(
                    excel, sheet_name=open_sheet, header=None
                )
                h_idx = None
                for i in range(min(30, len(df_raw))):
                    r = [
                        str(v).strip().lower()
                        for v in df_raw.iloc[i].values
                        if pd.notnull(v)
                    ]
                    if "ticker" in r and ("volume" in r or "open price" in r):
                        h_idx = i
                        break
                if h_idx is not None:
                    df_d = df_raw.iloc[h_idx + 1 :].copy()
                    df_d.columns = [
                        str(v).strip() for v in df_raw.iloc[h_idx].values
                    ]

                    c_type = next(
                        (c for c in df_d.columns if c.lower() == "type"), None
                    )
                    c_tick = next(
                        (c for c in df_d.columns if c.lower() == "ticker"),
                        None,
                    )
                    c_vol = next(
                        (c for c in df_d.columns if c.lower() == "volume"),
                        None,
                    )
                    c_prc = next(
                        (
                            c
                            for c in df_d.columns
                            if "open price" in c.lower() or "preço" in c.lower()
                        ),
                        None,
                    )

                    sub = (
                        df_d[
                            df_d[c_type]
                            .astype(str)
                            .str.upper()
                            .str.contains("BUY", na=False)
                        ].copy()
                        if c_type
                        else df_d.copy()
                    )
                    sub[c_vol] = pd.to_numeric(sub[c_vol], errors="coerce")
                    sub[c_prc] = pd.to_numeric(sub[c_prc], errors="coerce")
                    sub = sub.dropna(subset=[c_vol, c_prc])
                    sub = sub[sub[c_vol] > 0]

                    linhas_h = []
                    for _, row in sub.iterrows():
                        raw_t = str(row[c_tick]).strip().upper()
                        t_norm = normalizar_ticker(raw_t)
                        moeda = "USD" if raw_t.endswith(".US") else "EUR"
                        linhas_h.append(
                            {
                                "Ticker": t_norm,
                                "Shares": float(row[c_vol]),
                                "Cost_Per_Share": float(row[c_prc]),
                                "Currency": moeda,
                            }
                        )

                    if linhas_h:
                        df_h = pd.DataFrame(linhas_h)
                        dados_apuramento["holdings"] = (
                            df_h.groupby("Ticker")
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

            # 2. Posições Fechadas (Ganhos Realizados e IRS)
            closed_sheet = next(
                (
                    s
                    for s in excel.sheet_names
                    if "close" in s.lower() or "fech" in s.lower()
                ),
                None,
            )
            if closed_sheet:
                df_raw = pd.read_excel(
                    excel, sheet_name=closed_sheet, header=None
                )
                h_idx = None
                for i in range(min(30, len(df_raw))):
                    r = [
                        str(v).strip().lower()
                        for v in df_raw.iloc[i].values
                        if pd.notnull(v)
                    ]
                    if "ticker" in r and (
                        "profit/loss" in r or "close price" in r
                    ):
                        h_idx = i
                        break
                if h_idx is not None:
                    df_c = df_raw.iloc[h_idx + 1 :].copy()
                    df_c.columns = [
                        str(v).strip() for v in df_raw.iloc[h_idx].values
                    ]
                    for _, row in df_c.iterrows():
                        t = str(row.get("Ticker", "")).strip().upper()
                        if not t or t in ["NAN", "NONE", "TOTAL"]:
                            continue
                        pl = (
                            pd.to_numeric(
                                row.get("Profit/Loss"), errors="coerce"
                            )
                            or 0.0
                        )
                        dados_apuramento["realized_pl"] += pl

                        dt_c = pd.to_datetime(
                            row.get("Close Time (UTC)"), errors="coerce"
                        )
                        p_val = (
                            pd.to_numeric(
                                row.get("Purchase Value"), errors="coerce"
                            )
                            or 0.0
                        )
                        s_val = (
                            pd.to_numeric(
                                row.get("Sale Value"), errors="coerce"
                            )
                            or 0.0
                        )

                        pais = (
                            "620 - Portugal"
                            if t.endswith(".PT")
                            else (
                                "276 - Alemanha"
                                if t.endswith(".DE")
                                else "840 - Estados Unidos"
                            )
                        )
                        quadro = (
                            "Anexo G (Nacional)"
                            if t.endswith(".PT")
                            else "Anexo J - Quadro 9.2A"
                        )

                        dados_apuramento["closed_trades"].append(
                            {
                                "Corretora": "XTB",
                                "Ticker": t,
                                "Nome": str(row.get("Instrument", t)),
                                "País": pais,
                                "Quadro IRS": quadro,
                                "Data Venda": dt_c.strftime("%Y-%m-%d")
                                if pd.notnull(dt_c)
                                else "2026",
                                "Ano/Mês": dt_c.strftime("%Y-%m")
                                if pd.notnull(dt_c)
                                else "2026",
                                "Valor Venda (€)": round(s_val, 2),
                                "Valor Compra (€)": round(p_val, 2),
                                "Mais/Menos-valia (€)": round(pl, 2),
                            }
                        )

            # 3. Dividendos e Custos de Caixa
            cash_sheet = next(
                (
                    s
                    for s in excel.sheet_names
                    if "cash" in s.lower() or "caixa" in s.lower()
                ),
                None,
            )
            if cash_sheet:
                df_raw = pd.read_excel(
                    excel, sheet_name=cash_sheet, header=None
                )
                h_idx = None
                for i in range(min(30, len(df_raw))):
                    r = [
                        str(v).strip().lower()
                        for v in df_raw.iloc[i].values
                        if pd.notnull(v)
                    ]
                    if "type" in r and "amount" in r:
                        h_idx = i
                        break
                if h_idx is not None:
                    df_cash = df_raw.iloc[h_idx + 1 :].copy()
                    df_cash.columns = [
                        str(v).strip() for v in df_raw.iloc[h_idx].values
                    ]
                    df_cash["Amount"] = pd.to_numeric(
                        df_cash["Amount"], errors="coerce"
                    )
                    for _, row in df_cash.iterrows():
                        tp = str(row.get("Type", "")).strip().lower()
                        amt = float(row.get("Amount", 0.0))
                        if "dividend" in tp:
                            dados_apuramento["divs_total"] += amt

            return dados_apuramento, None

        # CASO 2: EXTRATO CSV DA TRADING 212
        else:
            dados_apuramento["tipo_ficheiro"] = "Trading 212"
            df_raw = pd.read_csv(ficheiro)
            df_raw.columns = [str(c).strip() for c in df_raw.columns]

            # Dividendos
            divs = df_raw[
                df_raw["Action"]
                .astype(str)
                .str.contains("Dividend", case=False, na=False)
            ]
            dados_apuramento["divs_total"] = float(
                pd.to_numeric(divs["Total"], errors="coerce").sum()
            )

            # Taxas e custos de conversão
            c_conv = pd.to_numeric(
                df_raw.get("Currency conversion fee", 0.0), errors="coerce"
            ).sum()
            c_ftt = pd.to_numeric(
                df_raw.get("French transaction tax", 0.0), errors="coerce"
            ).sum()
            dados_apuramento["fees_total"] = float(c_conv + c_ftt)

            # Vendas realizadas e IRS Anexo J
            sells = df_raw[
                df_raw["Action"].isin(["Market sell", "Limit sell"])
            ].copy()
            for _, r in sells.iterrows():
                isin = str(r.get("ISIN", ""))
                country_code = isin[:2] if len(isin) >= 2 else "US"
                country_name = MAPA_PAISES_IRS.get(
                    country_code, f"{country_code} - Estrangeiro"
                )

                dt_venda = pd.to_datetime(
                    r.get("Time (UTC)"), errors="coerce"
                )
                val_venda = (
                    float(r.get("Total", 0.0))
                    if r.get("Currency (Total)") == "EUR"
                    else (float(r.get("Total", 0.0)) / 1.08)
                )
                res = (
                    float(r.get("Result", 0.0))
                    if r.get("Currency (Result)") == "EUR"
                    else (float(r.get("Result", 0.0)) / 1.08)
                )
                val_compra = val_venda - res
                dados_apuramento["realized_pl"] += res

                dados_apuramento["closed_trades"].append(
                    {
                        "Corretora": "Trading 212",
                        "Ticker": r.get("Ticker", ""),
                        "Nome": r.get("Name", r.get("Ticker", "")),
                        "País": country_name,
                        "Quadro IRS": "Anexo J - Quadro 9.2A",
                        "Data Venda": dt_venda.strftime("%Y-%m-%d")
                        if pd.notnull(dt_venda)
                        else "2026",
                        "Ano/Mês": dt_venda.strftime("%Y-%m")
                        if pd.notnull(dt_venda)
                        else "2026",
                        "Valor Venda (€)": round(val_venda, 2),
                        "Valor Compra (€)": round(val_compra, 2),
                        "Mais/Menos-valia (€)": round(res, 2),
                    }
                )

            # Posições vivas (Holdings)
            df_sorted = df_raw.sort_values("Time (UTC)", ascending=True)
            carteira_calc = {}
            for _, r in df_sorted.iterrows():
                act = str(r.get("Action", "")).lower()
                if "buy" in act or "sell" in act:
                    raw_t = str(r.get("Ticker", "")).strip().upper()
                    t_norm = normalizar_ticker(raw_t)
                    qtd = (
                        pd.to_numeric(r.get("No. of shares"), errors="coerce")
                        or 0.0
                    )
                    tot = pd.to_numeric(r.get("Total"), errors="coerce") or 0.0
                    moeda_prc = str(
                        r.get("Currency (Price / share)", "EUR")
                    ).upper()

                    if t_norm not in carteira_calc:
                        carteira_calc[t_norm] = {
                            "shares": 0.0,
                            "invested_eur": 0.0,
                            "currency": moeda_prc,
                        }

                    pos = carteira_calc[t_norm]
                    if "buy" in act:
                        pos["invested_eur"] += tot
                        pos["shares"] += qtd
                        pos["currency"] = moeda_prc
                    elif "sell" in act and pos["shares"] > 0:
                        cm = pos["invested_eur"] / pos["shares"]
                        pos["shares"] = max(0.0, pos["shares"] - qtd)
                        pos["invested_eur"] = pos["shares"] * cm

            linhas_t212 = []
            for t, val in carteira_calc.items():
                if val["shares"] > 0.001:
                    pm = val["invested_eur"] / val["shares"]
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
            dados_apuramento["holdings"] = pd.DataFrame(linhas_t212)
            return dados_apuramento, None

    except Exception as e:
        return None, f"Erro no processamento: {str(e)}"


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
            variacao_dia_pct = (
                ((preco - preco_anterior) / preco_anterior) * 100
                if preco and preco_anterior
                else 0.0
            )

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

            moeda_ativo = (
                fast_info.currency or info.get("currency", "EUR")
            ).upper()
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
stats_hist = carregar_stats_historico()
taxa_eur_usd = obter_taxa_eur_usd()

with st.sidebar:
    st.header("⚙️ Gestor de Carteira")
    st.caption(f"💱 Câmbio atual: **1 EUR = {taxa_eur_usd:.4f} USD**")

    # 1. IMPORTAR EXCEL (XTB) OU CSV (TRADING 212)
    with st.expander("📥 Importar Relatório (XTB / T212)", expanded=True):
        st.write("Carrega o **Excel da XTB** ou o **CSV da Trading 212**.")
        uploaded_file = st.file_uploader(
            "Ficheiro", type=["xlsx", "xls", "csv"], key="file_up"
        )
        tipo_import = st.radio(
            "Método de Importação:",
            ["Fundir / Adicionar", "Substituir Carteira"],
            index=0,
        )

        if uploaded_file is not None:
            if st.button("Executar Importação", use_container_width=True):
                res_dados, erro = processar_ficheiro_importado(uploaded_file)
                if erro:
                    st.error(erro)
                elif res_dados is not None:
                    df_novo = res_dados["holdings"]
                    if not df_novo.empty:
                        if tipo_import == "Substituir Carteira":
                            df_portfolio = df_novo
                        else:
                            df_portfolio = (
                                pd.concat([df_portfolio, df_novo])
                                .drop_duplicates(subset=["Ticker"], keep="last")
                                .reset_index(drop=True)
                            )
                        guardar_portfolio(df_portfolio)

                    # Atualiza os dados históricos se existirem no ficheiro
                    if res_dados["realized_pl"] > 0:
                        stats_hist["ganho_realizado"] = round(
                            res_dados["realized_pl"], 2
                        )
                    if res_dados["divs_total"] > 0:
                        stats_hist["divs_recebidos"] = round(
                            res_dados["divs_total"], 2
                        )
                    if res_dados["fees_total"] > 0:
                        stats_hist["custos_transacao"] = round(
                            res_dados["fees_total"], 2
                        )
                    guardar_stats_historico(stats_hist)

                    # Guarda vendas para a aba de IRS
                    if res_dados["closed_trades"]:
                        st.session_state["irs_trades"] = res_dados[
                            "closed_trades"
                        ]

                    st.success(
                        f"Relatório {res_dados['tipo_ficheiro']} processado com sucesso!"
                    )
                    st.cache_data.clear()
                    st.rerun()

    # 2. ADICIONAR / REFORÇAR ATIVO MANUALMENTE
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
            "Moeda da Compra",
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
                        f"Reforço em {t_ajustado}! Novo total: {nova_qtd_total:.2f} ações | Novo PM: {novo_custo_medio:.2f}"
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

    # 3. EDITAR / CORRIGIR ATIVO
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

tab_holdings, tab_desempenho, tab_insights, tab_forecast, tab_irs = st.tabs(
    [
        "📊 Holdings",
        "📈 Desempenho",
        "💰 Dividend Insights",
        "🚀 Snowball Forecast",
        "📑 Fiscal (IRS)",
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

# TAB 2: Desempenho (Estilo getquin / Parqet com HTML Seguro)
with tab_desempenho:
    col_centro, col_vazia = st.columns([1.18, 1.82])

    with col_centro:
        ganho_preco_eur = total_unrealized_gl
        ganho_preco_pct = total_return_overall_pct

        with st.expander(
            "⚙️ Configurar Histórico Realizado e Custos", expanded=False
        ):
            c_divs_rec = st.number_input(
                "Dividendos Já Recebidos (€)",
                min_value=0.0,
                value=float(stats_hist.get("divs_recebidos", 634.73)),
                step=10.0,
            )
            c_ganho_realizado = st.number_input(
                "Ganhos Realizados (Vendas Anteriores) (€)",
                min_value=0.0,
                value=float(stats_hist.get("ganho_realizado", 1445.11)),
                step=50.0,
            )
            c_custos_transacao = st.number_input(
                "Custos de Transação / Comissões (€)",
                min_value=0.0,
                value=float(stats_hist.get("custos_transacao", 25.39)),
                step=1.0,
            )
            c_trocas = st.number_input(
                "Custos de Câmbio / Trocas (€)",
                min_value=0.0,
                value=float(stats_hist.get("trocas", 0.0)),
                step=1.0,
            )
            c_custos_correntes = st.number_input(
                "Custos Correntes (€)",
                min_value=0.0,
                value=float(stats_hist.get("custos_correntes", 53.95)),
                step=5.0,
            )

            if st.button("Guardar Parâmetros", use_container_width=True):
                stats_hist.update(
                    {
                        "divs_recebidos": c_divs_rec,
                        "ganho_realizado": c_ganho_realizado,
                        "custos_transacao": c_custos_transacao,
                        "trocas": c_trocas,
                        "custos_correntes": c_custos_correntes,
                    }
                )
                guardar_stats_historico(stats_hist)
                st.success("Guardado!")
                st.rerun()

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

        tir_irr = float(stats_hist.get("tir", 14.92))
        twr = float(stats_hist.get("twr", 16.47))

        # Renderização HTML sem indentação de código
        card_html = f"""<div style="background-color: #11141a; border: 1px solid #21262d; border-radius: 12px; padding: 22px; color: #ffffff; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 440px;">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
<div>
<span style="font-size: 19px; font-weight: 700;">Desempenho</span>
<span style="background-color: #21262d; color: #8b949e; font-size: 11px; font-weight: 600; padding: 2px 6px; border-radius: 4px; margin-left: 8px; vertical-align: middle;">PREMIUM</span>
</div>
<span style="color: #8b949e; font-size: 13px; cursor: pointer;">Mostrar mais</span>
</div>
<div style="display: flex; justify-content: flex-end; align-items: flex-end; height: 110px; margin: 15px 0 25px 0; padding-right: 25px; position: relative;">
<div style="position: absolute; top: 40px; left: 0; right: 0; border-top: 1px dashed #30363d;"></div>
<div style="display: flex; flex-direction: column; align-items: center; margin-right: 40px; z-index: 1;">
<div style="background-color: #00d084; width: 42px; height: 40px; border-radius: 2px 2px 0 0;"></div>
<div style="background-color: #21262d; width: 42px; height: 30px; border-radius: 0 0 2px 2px; margin-bottom: 8px;"></div>
<span style="color: #8b949e; font-size: 13px; font-weight: 500;">2025</span>
</div>
<div style="display: flex; flex-direction: column; align-items: center; z-index: 1;">
<div style="background-color: #00d084; width: 42px; height: 70px; border-radius: 2px 2px 0 0;"></div>
<div style="background-color: #21262d; width: 42px; height: 45px; border-radius: 0 0 2px 2px; margin-bottom: 8px;"></div>
<span style="color: #8b949e; font-size: 13px; font-weight: 500;">2026</span>
</div>
</div>
<div style="font-size: 16px; font-weight: 700; margin-bottom: 12px;">Capital</div>
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 22px; font-size: 14px;">
<span style="color: #c9d1d9;">Capital investido <span style="font-size: 12px; color: #6b7280;">ⓘ</span></span>
<span style="font-weight: 700; font-size: 15px;">€ {total_invested:,.2f}</span>
</div>
<div style="font-size: 16px; font-weight: 700; margin-bottom: 12px;">Repartição do desempenho</div>
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 14px;">
<span style="color: #c9d1d9;">Ganho de preço <span style="font-size: 12px; color: #6b7280;">ⓘ</span></span>
<div>
<span style="color: #00d084; font-weight: 600; margin-right: 14px;">↗ {ganho_preco_pct:.2f}%</span>
<span style="font-weight: 700;">€ {ganho_preco_eur:,.2f}</span>
</div>
</div>
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 14px;">
<span style="color: #c9d1d9;">Dividendos <span style="font-size: 12px; color: #6b7280;">ⓘ</span></span>
<div>
<span style="color: #00d084; font-weight: 600; margin-right: 14px;">↗ {divs_pct:.2f}%</span>
<span style="font-weight: 700;">€ {c_divs_rec:,.2f}</span>
</div>
</div>
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 22px; font-size: 14px;">
<span style="color: #c9d1d9;">Ganho realizado <span style="font-size: 12px; color: #6b7280;">ⓘ</span></span>
<div>
<span style="color: #00d084; font-weight: 600; margin-right: 14px;">↗ {ganho_real_pct:.2f}%</span>
<span style="font-weight: 700;">€ {c_ganho_realizado:,.2f}</span>
</div>
</div>
<div style="font-size: 16px; font-weight: 700; margin-bottom: 12px;">Custos de transação</div>
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 14px;">
<span style="color: #c9d1d9;">Custos de transação</span>
<span style="font-weight: 700;">-€ {c_custos_transacao:,.2f}</span>
</div>
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-size: 14px;">
<span style="color: #c9d1d9;">Trocas</span>
<span style="font-weight: 700;">€ {c_trocas:,.2f}</span>
</div>
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; font-size: 14px;">
<span style="color: #c9d1d9;">Custos correntes <span style="font-size: 12px; color: #6b7280;">ⓘ</span></span>
<span style="font-weight: 700;">€ {c_custos_correntes:,.2f}</span>
</div>
<hr style="border: 0; border-top: 1px solid #21262d; margin-bottom: 18px;">
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; font-size: 15px;">
<span style="font-weight: 700;">Retorno total</span>
<span style="color: #00d084; font-weight: 700; font-size: 16px;">↗ € {retorno_total_eur:,.2f}</span>
</div>
<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; font-size: 14px;">
<span style="font-weight: 700;">Taxa interna de rendibilidade <span style="font-size: 12px; color: #6b7280;">ⓘ</span></span>
<span style="color: #00d084; font-weight: 700;">↗ {tir_irr:.2f}%</span>
</div>
<div style="display: flex; justify-content: space-between; align-items: center; font-size: 14px;">
<span style="font-weight: 700;">Taxa de retorno real ponderada pelo tempo <span style="font-size: 12px; color: #6b7280;">ⓘ</span></span>
<span style="color: #00d084; font-weight: 700;">↗ {twr:.2f}%</span>
</div>
</div>"""

        clean_render = "".join(line.strip() for line in card_html.splitlines())
        st.markdown(clean_render, unsafe_allow_html=True)

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

# TAB 5: Fiscal (IRS Anexo J & Anexo G)
with tab_irs:
    st.subheader("📑 Apuramento de Mais-Valias para o IRS")
    st.caption(
        "Discriminação automática das vendas executadas para preenchimento do **Anexo J (Quadro 9.2A)** e **Anexo G**."
    )

    lista_vendas = st.session_state.get("irs_trades", [])

    if lista_vendas:
        df_irs = pd.DataFrame(lista_vendas)

        c_vendas, c_lucro = st.columns(2)
        total_vendas_eur = df_irs["Valor Venda (€)"].sum()
        total_pl_irs = df_irs["Mais/Menos-valia (€)"].sum()

        c_vendas.metric("Total Alienado", f"{total_vendas_eur:,.2f} €")
        c_lucro.metric(
            "Saldo de Mais-Valias Líquidas",
            f"{total_pl_irs:+,.2f} €",
            delta=f"{len(df_irs)} operações realizadas",
        )

        st.dataframe(
            df_irs.style.format(
                {
                    "Valor Venda (€)": "{:,.2f} €",
                    "Valor Compra (€)": "{:,.2f} €",
                    "Mais/Menos-valia (€)": "{:+,.2f} €",
                }
            ).map(
                lambda v: (
                    "color: #00e676;"
                    if v > 0
                    else "color: #ff5252;"
                    if v < 0
                    else ""
                ),
                subset=["Mais/Menos-valia (€)"],
            ),
            use_container_width=True,
            height=380,
        )

        csv_irs = df_irs.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Descarregar Tabela para Apoio ao IRS (CSV)",
            data=csv_irs,
            file_name="apuramento_mais_valias_irs.csv",
            mime="text/csv",
        )
    else:
        st.info(
            "Carrega o teu ficheiro da **XTB (`.xlsx`)** ou da **Trading 212 (`.csv`)** na barra lateral para carregar automaticamente o histórico de vendas para o IRS."
        )
