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
TRADES_FILE = "closed_trades.csv"
DIVS_FILE = "dividends.csv"
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
    "DK": "208 - Dinamarca",
}

MESES_NOMES = [
    "jan",
    "fev",
    "mar",
    "abr",
    "mai",
    "jun",
    "jul",
    "ago",
    "set",
    "out",
    "nov",
    "dez",
]

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


def fragment_auto(run_every=None):
    if hasattr(st, "fragment"):
        return st.fragment(run_every=run_every)
    elif hasattr(st, "experimental_fragment"):
        return st.experimental_fragment(run_every=run_every)
    return lambda f: f


# ---------------------------------------------------------
# Gestão de Ficheiros Locais e Persistência
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


def carregar_vendas_fechadas():
    if os.path.exists(TRADES_FILE):
        try:
            return pd.read_csv(TRADES_FILE)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def guardar_vendas_fechadas(df_novas):
    df_existente = carregar_vendas_fechadas()
    if df_existente.empty:
        df_final = df_novas
    else:
        df_final = pd.concat(
            [df_existente, df_novas], ignore_index=True
        ).drop_duplicates(
            subset=[
                "Corretora",
                "Ticker",
                "Data Venda",
                "Valor Venda (€)",
                "Valor Compra (€)",
            ],
            keep="last",
        )
    df_final.to_csv(TRADES_FILE, index=False)
    return df_final


def carregar_dividendos():
    if os.path.exists(DIVS_FILE):
        try:
            return pd.read_csv(DIVS_FILE)
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()


def guardar_dividendos(df_novos):
    df_existente = carregar_dividendos()
    if df_existente.empty:
        df_final = df_novos
    else:
        df_final = pd.concat(
            [df_existente, df_novos], ignore_index=True
        ).drop_duplicates(
            subset=[
                "Corretora",
                "Ticker",
                "Data",
                "Valor_Bruto",
                "Valor_Liquido",
            ],
            keep="last",
        )
    df_final.to_csv(DIVS_FILE, index=False)
    return df_final


def carregar_stats_historico():
    default_stats = {
        "divs_recebidos": 524.68,
        "ganho_realizado": 1602.89,
        "custos_transacao": 25.39,
        "trocas": 0.00,
        "custos_correntes": 53.95,
        "tir": 14.92,
        "twr": 16.47,
        "dgr_estimado": 7.0,
        "aporte_mensal_estimado": 0.0,
    }
    if os.path.exists(HIST_FILE):
        try:
            df_h = pd.read_csv(HIST_FILE)
            d = df_h.iloc[0].to_dict()
            default_stats.update(d)
            return default_stats
        except Exception:
            return default_stats
    return default_stats


def guardar_stats_historico(stats_dict):
    pd.DataFrame([stats_dict]).to_csv(HIST_FILE, index=False)


# ---------------------------------------------------------
# Câmbio EUR / USD em Tempo Real (TTL = 5s)
# ---------------------------------------------------------
@st.cache_data(ttl=5)
def obter_taxa_eur_usd():
    try:
        forex = yf.Ticker("EURUSD=X")
        taxa = forex.fast_info.last_price or 1.16
        return taxa
    except Exception:
        return 1.16


# ---------------------------------------------------------
# Motor de Leitura e Unificação de Extratos
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
            "dividend_records": [],
            "divs_total_liquido": 0.0,
            "divs_total_bruto": 0.0,
            "realized_pl": 0.0,
            "fees_total": 0.0,
            "tipo_ficheiro": "",
        }

        # 1. XTB (.xlsx)
        if nome.endswith((".xlsx", ".xls")):
            dados_apuramento["tipo_ficheiro"] = "XTB"
            excel = pd.ExcelFile(ficheiro)

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

                    sub_div = df_cash[
                        df_cash["Type"].isin(["Dividend", "Withholding tax"])
                    ].copy()
                    sub_div["Date_Only"] = pd.to_datetime(
                        sub_div["Time"], errors="coerce"
                    ).dt.date

                    for (d, t), grp in sub_div.groupby(["Date_Only", "Ticker"]):
                        g_val = grp[grp["Type"] == "Dividend"]["Amount"].sum()
                        w_val = abs(
                            grp[grp["Type"] == "Withholding tax"]["Amount"].sum()
                        )
                        if g_val > 0:
                            n_val = g_val - w_val
                            dados_apuramento["divs_total_bruto"] += g_val
                            dados_apuramento["divs_total_liquido"] += n_val
                            dados_apuramento["dividend_records"].append(
                                {
                                    "Data": str(d),
                                    "Ano_Mes": str(d)[:7],
                                    "Corretora": "XTB",
                                    "Ticker": str(t),
                                    "Nome": str(t),
                                    "País": "840 - Estados Unidos"
                                    if "US" in str(t)
                                    else "372 - Irlanda",
                                    "Valor_Bruto": round(g_val, 2),
                                    "Retencao_Fonte": round(w_val, 2),
                                    "Valor_Liquido": round(n_val, 2),
                                }
                            )

            return dados_apuramento, None

        # 2. Trading 212 (.csv)
        else:
            dados_apuramento["tipo_ficheiro"] = "Trading 212"
            df_raw = pd.read_csv(ficheiro, encoding="utf-8-sig")
            df_raw.columns = [str(c).strip() for c in df_raw.columns]

            divs = df_raw[
                df_raw["Action"]
                .astype(str)
                .str.contains("Dividend", case=False, na=False)
            ].copy()
            for _, r in divs.iterrows():
                dt = pd.to_datetime(r.get("Time (UTC)"), errors="coerce")
                net = float(r.get("Total", 0.0))
                wht = float(r.get("Withholding tax", 0.0))
                gross = net + wht

                isin = str(r.get("ISIN", ""))
                c_code = isin[:2] if len(isin) >= 2 else "US"
                pais_nome = MAPA_PAISES_IRS.get(
                    c_code, f"{c_code} - Estrangeiro"
                )

                dados_apuramento["divs_total_liquido"] += net
                dados_apuramento["divs_total_bruto"] += gross

                dados_apuramento["dividend_records"].append(
                    {
                        "Data": dt.strftime("%Y-%m-%d")
                        if pd.notnull(dt)
                        else "2026",
                        "Ano_Mes": dt.strftime("%Y-%m")
                        if pd.notnull(dt)
                        else "2026",
                        "Corretora": "Trading 212",
                        "Ticker": str(r.get("Ticker", "")),
                        "Nome": str(r.get("Name", r.get("Ticker", ""))),
                        "País": pais_nome,
                        "Valor_Bruto": round(gross, 2),
                        "Retencao_Fonte": round(wht, 2),
                        "Valor_Liquido": round(net, 2),
                    }
                )

            c_conv = pd.to_numeric(
                df_raw.get("Currency conversion fee", 0.0), errors="coerce"
            ).sum()
            c_ftt = pd.to_numeric(
                df_raw.get("French transaction tax", 0.0), errors="coerce"
            ).sum()
            dados_apuramento["fees_total"] = float(c_conv + c_ftt)

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
# Obtenção de Cotações em Tempo Real (TTL = 5s)
# ---------------------------------------------------------
@st.cache_data(ttl=5)
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
# Sidebar: Gestão de Carteira & Opções
# ---------------------------------------------------------
df_portfolio = carregar_portfolio()
df_vendas_salvas = carregar_vendas_fechadas()
df_divs_salvos = carregar_dividendos()
stats_hist = carregar_stats_historico()

with st.sidebar:
    st.header("⚙️ Gestor de Carteira")

    st.markdown("### ⚡ Cotações em Tempo Real")
    auto_refresh = st.toggle(
        "Atualização Automática",
        value=True,
        help="Atualiza as cotações e métricas a cada 5 segundos em segundo plano.",
    )
    intervalo_segundos = 5
    if auto_refresh:
        intervalo_segundos = st.select_slider(
            "Frequência:",
            options=[5, 10, 15, 30, 60],
            value=5,
            format_func=lambda s: f"{s}s (Direto)" if s == 5 else f"{s}s",
        )
        st.caption(f"🟢 **Modo Direto:** Atualiza a cada **{intervalo_segundos} segundos**.")
    else:
        st.caption("⚪ Pausado: atualização manual.")

    run_interval = intervalo_segundos if auto_refresh else None

    st.markdown("---")

    st.markdown("### 🏛️ Opção Fiscal de Dividendos")
    modo_retencao = st.radio(
        "Visualizar Dividendos:",
        ["Sem Retenção (Líquido)", "Com Retenção (Bruto)"],
        index=0,
        help="Líquido: o valor real creditado na conta.\nBruto: o total antes do imposto retido na fonte.",
    )
    is_bruto = "Bruto" in modo_retencao

    st.markdown("---")

    with st.expander("📥 Importar Relatório (XTB / T212)", expanded=True):
        st.write("Carrega o **Excel da XTB** ou o **CSV da Trading 212**.")
        uploaded_file = st.file_uploader(
            "Ficheiro", type=["xlsx", "xls", "csv"], key="file_up"
        )
        tipo_import = st.radio(
            "Método para Carteira Atual:",
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

                    if res_dados["closed_trades"]:
                        df_novas_vendas = pd.DataFrame(
                            res_dados["closed_trades"]
                        )
                        df_vendas_salvas = guardar_vendas_fechadas(
                            df_novas_vendas
                        )

                    if res_dados["dividend_records"]:
                        df_novos_divs = pd.DataFrame(
                            res_dados["dividend_records"]
                        )
                        df_divs_salvos = guardar_dividendos(df_novos_divs)

                    if not df_divs_salvos.empty:
                        stats_hist["divs_recebidos"] = float(
                            df_divs_salvos["Valor_Liquido"].sum()
                        )
                    if not df_vendas_salvas.empty:
                        stats_hist["ganho_realizado"] = float(
                            df_vendas_salvas["Mais/Menos-valia (€)"].sum()
                        )
                    if res_dados["fees_total"] > 0:
                        stats_hist["custos_transacao"] = round(
                            res_dados["fees_total"], 2
                        )
                    guardar_stats_historico(stats_hist)

                    st.success(
                        f"Relatório {res_dados['tipo_ficheiro']} processado com sucesso!"
                    )
                    st.cache_data.clear()
                    st.rerun()

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
    if st.button("🔄 Forçar Atualização Imediata", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ---------------------------------------------------------
# PAINEL PRINCIPAL
# ---------------------------------------------------------
@fragment_auto(run_every=run_interval)
def render_painel_principal():
    df_port = carregar_portfolio()
    df_vendas = carregar_vendas_fechadas()
    df_divs = carregar_dividendos()
    stats = carregar_stats_historico()
    taxa_eur_usd = obter_taxa_eur_usd()

    tickers_lista = df_port["Ticker"].tolist()
    market_data = obter_dados_mercado(tickers_lista)

    dados_processados = []
    # Dicionário detalhado: mês -> {ticker: valor_eur}
    distribuicao_mensal_detalhada = {m: {} for m in range(1, 13)}
    distribuicao_mensal_eur = {m: 0.0 for m in range(1, 13)}

    for _, row in df_port.iterrows():
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
            (unrealized_gl_eur / invested_eur) * 100
            if invested_eur > 0
            else 0.0
        )
        day_gl_eur = (
            shares * (price_eur - prev_close_eur) if price_eur > 0 else 0.0
        )

        fator_retencao = (
            0.85 if (native_currency == "USD" and not is_bruto) else 1.0
        )
        annual_dividend_eur = (
            shares * (annual_div_native * fator_conversao_eur) * fator_retencao
        )
        yoc = (
            (annual_dividend_eur / invested_eur) * 100
            if invested_eur > 0
            else 0.0
        )

        for m in range(1, 13):
            val_m = (
                monthly_sched_native.get(m, 0.0)
                * fator_conversao_eur
                * shares
                * fator_retencao
            )
            if val_m > 0:
                distribuicao_mensal_detalhada[m][t] = val_m
                distribuicao_mensal_eur[m] += val_m

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
                "Dividend Yield %": div_yield * fator_retencao,
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
        (total_unrealized_gl / total_invested) * 100
        if total_invested > 0
        else 0.0
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
        df_view["Peso %"] = (
            df_view["Valor Mercado (€)"] / total_mkt_value
        ) * 100
    else:
        df_view["Peso %"] = 0.0

    c_title, c_status = st.columns([4, 1])
    with c_title:
        st.title("💼 Dividend Portfolio Tracker (Consolidado em €)")
    with c_status:
        if auto_refresh:
            st.markdown(
                f"<div style='text-align: right; padding-top: 15px;'><span style='color: #00e676; font-size: 13px; font-weight: 600;'>🟢 AO VIVO ({intervalo_segundos}s)</span></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='text-align: right; padding-top: 15px;'><span style='color: #8b949e; font-size: 13px; font-weight: 600;'>⚪ PAUSADO</span></div>",
                unsafe_allow_html=True,
            )

    rotulo_div = (
        "Dividendos Anuais (Brutos)"
        if is_bruto
        else "Dividendos Anuais (Líquidos)"
    )
    rotulo_yield = "Yield Bruto / YoC" if is_bruto else "Yield Líquido / YoC"

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
        label=rotulo_div,
        value=f"{total_annual_dividend:,.2f} {MOEDA_BASE}",
        delta=f"{total_annual_dividend/12:,.2f} {MOEDA_BASE}/mês",
    )
    m5.metric(
        label=rotulo_yield,
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

    # TAB 2: Desempenho
    with tab_desempenho:
        col_centro, col_vazia = st.columns([1.18, 1.82])

        with col_centro:
            ganho_preco_eur = total_unrealized_gl
            ganho_preco_pct = total_return_overall_pct

            if not df_divs.empty:
                divs_valor_card = (
                    float(df_divs["Valor_Bruto"].sum())
                    if is_bruto
                    else float(df_divs["Valor_Liquido"].sum())
                )
            else:
                divs_valor_card = (
                    601.38
                    if is_bruto
                    else float(stats.get("divs_recebidos", 524.68))
                )

            with st.expander(
                "⚙️ Configurar Histórico Realizado e Custos", expanded=False
            ):
                c_divs_rec = st.number_input(
                    "Dividendos Recebidos (€)",
                    min_value=0.0,
                    value=float(divs_valor_card),
                    step=10.0,
                )
                c_ganho_realizado = st.number_input(
                    "Ganhos Realizados (€)",
                    min_value=0.0,
                    value=float(stats.get("ganho_realizado", 1602.89)),
                    step=50.0,
                )
                c_custos_transacao = st.number_input(
                    "Custos de Transação (€)",
                    min_value=0.0,
                    value=float(stats.get("custos_transacao", 25.39)),
                    step=1.0,
                )
                c_trocas = st.number_input(
                    "Custos de Câmbio (€)",
                    min_value=0.0,
                    value=float(stats.get("trocas", 0.0)),
                    step=1.0,
                )
                c_custos_correntes = st.number_input(
                    "Custos Correntes (€)",
                    min_value=0.0,
                    value=float(stats.get("custos_correntes", 53.95)),
                    step=5.0,
                )

                if st.button("Guardar Parâmetros", use_container_width=True):
                    stats.update(
                        {
                            "divs_recebidos": c_divs_rec,
                            "ganho_realizado": c_ganho_realizado,
                            "custos_transacao": c_custos_transacao,
                            "trocas": c_trocas,
                            "custos_correntes": c_custos_correntes,
                        }
                    )
                    guardar_stats_historico(stats)
                    st.success("Guardado com sucesso!")
                    st.rerun()

            divs_pct = (
                (c_divs_rec / total_invested) * 100
                if total_invested > 0
                else 0.0
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

            tir_irr = float(stats.get("tir", 14.92))
            twr = float(stats.get("twr", 16.47))

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
<span style="color: #c9d1d9;">Dividendos {'(Bruto)' if is_bruto else '(Líquido)'} <span style="font-size: 12px; color: #6b7280;">ⓘ</span></span>
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
            st.markdown(
                "".join(line.strip() for line in card_html.splitlines()),
                unsafe_allow_html=True,
            )

    # TAB 3: Dividend Insights (Estilo getquin com Estimativa Futura)
    with tab_insights:
        st.markdown(
            """
            <div style="display: flex; align-items: center; margin-bottom: 15px;">
                <span style="font-size: 20px; font-weight: 700; margin-right: 10px;">Dividendos</span>
                <span style="background-color: #21262d; color: #8b949e; font-size: 11px; font-weight: 600; padding: 2px 7px; border-radius: 4px;">PREMIUM</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander("⚙️ Parâmetros da Estimativa Futura", expanded=False):
            c_dgr_col, c_apt_col = st.columns(2)
            with c_dgr_col:
                taxa_dgr = st.slider(
                    "Crescimento Anual dos Dividendos (% DGR)",
                    0.0,
                    15.0,
                    float(stats.get("dgr_estimado", 7.0)),
                    0.5,
                )
            with c_apt_col:
                aporte_futuro = st.number_input(
                    "Aporte Mensal Estimado Adicional (€)",
                    min_value=0.0,
                    value=float(stats.get("aporte_mensal_estimado", 0.0)),
                    step=100.0,
                )

            if st.button("Guardar Parâmetros de Estimativa", use_container_width=True):
                stats["dgr_estimado"] = taxa_dgr
                stats["aporte_mensal_estimado"] = aporte_futuro
                guardar_stats_historico(stats)
                st.success("Configuração de estimativa guardada!")
                st.rerun()

        # Seletor de Horizonte de Dividendos
        anos_disponiveis = [
            "2025",
            "2026 (Atual)",
            "2027 (Estimativa)",
            "2028 (Estimativa)",
            "Previsão Multi-Anual",
        ]
        ano_selecionado = st.radio(
            "Selecionar Horizonte:",
            anos_disponiveis,
            index=1,
            horizontal=True,
            label_visibility="collapsed",
        )

        # Cálculo do Fator de Crescimento conforme o Ano
        fator_ano = 1.0
        incremento_aportes = 0.0
        is_multi_ano = ano_selecionado == "Previsão Multi-Anual"

        if "2025" in ano_selecionado:
            fator_ano = 0.0  # Histórico sem dados prévios
        elif "2026" in ano_selecionado:
            fator_ano = 1.0
        elif "2027" in ano_selecionado:
            fator_ano = 1.0 + (taxa_dgr / 100.0)
            incremento_aportes = (aporte_futuro * 12) * (portfolio_yield / 100.0)
        elif "2028" in ano_selecionado:
            fator_ano = (1.0 + (taxa_dgr / 100.0)) ** 2
            incremento_aportes = (aporte_futuro * 24) * (portfolio_yield / 100.0)

        # Mapeamento dos dividendos mensais para o ano selecionado
        valores_mes_ano = []
        pagadores_mes_ano = []
        is_mes_estimado = []

        mes_atual = pd.Timestamp.now().month  # 9 (Setembro)

        for m in range(1, 13):
            # Projeção base da carteira com o fator de crescimento do ano
            val_base_m = (distribuicao_mensal_eur[m] * fator_ano) + (
                incremento_aportes / 12.0
            )
            pagadores = list(distribuicao_mensal_detalhada[m].keys())

            if "2026" in ano_selecionado:
                # Em 2026: meses passados com registos reais usam os dados reais dos ficheiros
                if not df_divs.empty and m < mes_atual:
                    divs_m_real = df_divs[
                        df_divs["Data"].str.startswith(f"2026-{m:02d}")
                    ]
                    if not divs_m_real.empty:
                        val_real = (
                            divs_m_real["Valor_Bruto"].sum()
                            if is_bruto
                            else divs_m_real["Valor_Liquido"].sum()
                        )
                        valores_mes_ano.append(val_real)
                        pagadores_mes_ano.append(
                            divs_m_real["Ticker"].unique().tolist()
                        )
                        is_mes_estimado.append(False)
                        continue

                # Meses futuros de 2026
                valores_mes_ano.append(val_base_m)
                pagadores_mes_ano.append(pagadores)
                is_mes_estimado.append(m >= mes_atual)

            elif "2025" in ano_selecionado:
                valores_mes_ano.append(0.0)
                pagadores_mes_ano.append([])
                is_mes_estimado.append(False)
            else:
                # 2027 / 2028: todos os meses são 100% estimados
                valores_mes_ano.append(val_base_m)
                pagadores_mes_ano.append(pagadores)
                is_mes_estimado.append(True)

        total_ano_calculado = sum(valores_mes_ano)
        media_mensal_ano = total_ano_calculado / 12.0

        # 4 Cartões de Topo estilo getquin
        k1, k2, k3, k4 = st.columns(4)
        rotulo_topo = (
            "Total previsto" if "Estimativa" in ano_selecionado else "Total recebido / previsto"
        )
        k1.metric(rotulo_topo, f"€ {total_ano_calculado:,.2f}")
        k2.metric(
            "Rendimento de dividendos (TTM)",
            f"{portfolio_yield * fator_ano:.3f}%",
        )
        k3.metric("YoC (TTM)", f"{portfolio_yoc * fator_ano:.3f}%")
        k4.metric("CAGR Estimado", f"{taxa_dgr:.1f}%")

        st.markdown("<br>", unsafe_allow_html=True)

        if not is_multi_ano:
            # Gráfico Mensal idêntico ao getquin
            fig_meses = go.Figure()

            # Barras reais (sólidas)
            x_real = [
                MESES_NOMES[i]
                for i in range(12)
                if not is_mes_estimado[i] and valores_mes_ano[i] > 0
            ]
            y_real = [
                valores_mes_ano[i]
                for i in range(12)
                if not is_mes_estimado[i] and valores_mes_ano[i] > 0
            ]

            if x_real:
                fig_meses.add_trace(
                    go.Bar(
                        x=x_real,
                        y=y_real,
                        name="Recebido",
                        marker=dict(color="#00d084"),
                        text=[f"€ {v:,.2f}" for v in y_real],
                        textposition="outside",
                    )
                )

            # Barras estimadas (hachuradas com listras diagonais)
            x_est = [
                MESES_NOMES[i]
                for i in range(12)
                if is_mes_estimado[i] and valores_mes_ano[i] > 0
            ]
            y_est = [
                valores_mes_ano[i]
                for i in range(12)
                if is_mes_estimado[i] and valores_mes_ano[i] > 0
            ]

            if x_est:
                fig_meses.add_trace(
                    go.Bar(
                        x=x_est,
                        y=y_est,
                        name="Estimado",
                        marker=dict(
                            color="#9b51e0",
                            pattern=dict(shape="/", fgcolor="#ffffff", size=8),
                        ),
                        text=[f"€ {v:,.2f}" for v in y_est],
                        textposition="outside",
                    )
                )

            # Linha tracejada da média mensal Ø
            if media_mensal_ano > 0:
                fig_meses.add_hline(
                    y=media_mensal_ano,
                    line_dash="dash",
                    line_color="#8b949e",
                    line_width=1.5,
                )

            fig_meses.update_layout(
                title=dict(
                    text=f"<b>Ø € {media_mensal_ano:,.2f}</b> <span style='font-size:12px; color:#8b949e;'>(Média/mês)</span>"
                    f"<span style='float:right;'><b>Σ € {total_ano_calculado:,.2f}</b> <span style='font-size:12px; color:#8b949e;'>(Total Anual)</span></span>",
                    x=0.01,
                    y=0.98,
                    xanchor="left",
                    font=dict(color="#ffffff", size=15),
                ),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#c9d1d9"),
                height=350,
                margin=dict(t=50, b=20, l=10, r=10),
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1,
                ),
                yaxis=dict(
                    showgrid=True,
                    gridcolor="#21262d",
                    zeroline=False,
                    showticklabels=False,
                ),
                xaxis=dict(
                    showgrid=False,
                    tickfont=dict(color="#8b949e", size=13),
                    categoryorder="array",
                    categoryarray=MESES_NOMES,
                ),
            )
            st.plotly_chart(fig_meses, use_container_width=True)

            # Grelha de Ativos Pagadores em baixo do gráfico
            st.markdown("#### 📅 Ativos Pagadores em Cada Mês")
            cols_meses = st.columns(12)
            for idx, c in enumerate(cols_meses):
                with c:
                    m_nome = MESES_NOMES[idx]
                    m_val = valores_mes_ano[idx]
                    m_pags = pagadores_mes_ano[idx]
                    st.markdown(
                        f"<div style='text-align:center;'><b style='color:#8b949e;'>{m_nome}</b><br>"
                        f"<span style='font-size:13px; font-weight:700;'>€ {m_val:,.2f}</span></div>",
                        unsafe_allow_html=True,
                    )
                    if m_pags:
                        for p in m_pags[:3]:
                            p_clean = p.split(".")[0]
                            st.markdown(
                                f"<div style='background-color:#21262d; border-radius:4px; font-size:10px; text-align:center; margin:2px 0; padding:1px;'>{p_clean}</div>",
                                unsafe_allow_html=True,
                            )
                    else:
                        st.markdown(
                            "<div style='color:#484f58; font-size:11px; text-align:center;'>-</div>",
                            unsafe_allow_html=True,
                        )

        else:
            # Visão Multi-Anual: Evolução de 2025 até 2030
            anos_proj = [2025, 2026, 2027, 2028, 2029, 2030]
            valores_multi = []
            for y in anos_proj:
                if y == 2025:
                    valores_multi.append(0.0)
                elif y == 2026:
                    valores_multi.append(total_annual_dividend)
                else:
                    exp = y - 2026
                    cresc = (1.0 + (taxa_dgr / 100.0)) ** exp
                    novos = (aporte_futuro * 12 * exp) * (portfolio_yield / 100.0)
                    valores_multi.append((total_annual_dividend * cresc) + novos)

            fig_multi = go.Figure()
            fig_multi.add_trace(
                go.Bar(
                    x=[str(y) for y in anos_proj],
                    y=valores_multi,
                    text=[f"€ {v:,.2f}" for v in valores_multi],
                    textposition="auto",
                    marker_color=["#21262d", "#00d084", "#58a6ff", "#58a6ff", "#58a6ff", "#58a6ff"],
                )
            )
            fig_multi.update_layout(
                title="<b>Evolução Anual dos Dividendos Passivos (2025 - 2030)</b>",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#c9d1d9"),
                height=350,
                yaxis_title="Total Anual (€)",
            )
            st.plotly_chart(fig_multi, use_container_width=True)

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
            yield_base = (
                portfolio_yield / 100.0 if portfolio_yield > 0 else 0.035
            )
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

    # TAB 5: Fiscal (IRS Anexo J & Anexo G)
    with tab_irs:
        st.subheader("📑 Apuramento Consolidado para IRS (XTB + Trading 212)")
        aba_irs_mv, aba_irs_divs = st.tabs(
            [
                "📈 Mais-Valias (Quadro 9.2A / Anexo G)",
                "💰 Rendimentos de Capitais (Quadro 8 - Dividendos)",
            ]
        )

        with aba_irs_mv:
            if not df_vendas.empty:
                c_v1, c_v2, c_v3 = st.columns(3)
                tot_alienado = df_vendas["Valor Venda (€)"].sum()
                tot_aquisicao = df_vendas["Valor Compra (€)"].sum()
                tot_saldo_mv = df_vendas["Mais/Menos-valia (€)"].sum()

                c_v1.metric("Total Alienado (€)", f"{tot_alienado:,.2f} €")
                c_v2.metric(
                    "Total de Aquisição (€)", f"{tot_aquisicao:,.2f} €"
                )
                c_v3.metric(
                    "Saldo de Mais-Valias Líquidas",
                    f"{tot_saldo_mv:+,.2f} €",
                    delta=f"{len(df_vendas)} operações registadas",
                )

                corretora_filtro = st.selectbox(
                    "Filtrar por Corretora:",
                    ["Todas", "Trading 212", "XTB"],
                    key="filtro_corr",
                )
                df_mostrar_vendas = df_vendas.copy()
                if corretora_filtro != "Todas":
                    df_mostrar_vendas = df_mostrar_vendas[
                        df_mostrar_vendas["Corretora"] == corretora_filtro
                    ]

                st.dataframe(
                    df_mostrar_vendas.sort_values(
                        by="Data Venda", ascending=False
                    ).style.format(
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

                csv_vendas = df_vendas.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Descarregar Tabela de Mais-Valias (CSV)",
                    data=csv_vendas,
                    file_name="mais_valias_irs_anexo_j_g.csv",
                    mime="text/csv",
                )
            else:
                st.info(
                    "Importa os extratos na barra lateral para carregar as mais-valias."
                )

        with aba_irs_divs:
            if not df_divs.empty:
                st.markdown(
                    "#### Discriminação de Dividendos no Estrangeiro (Anexo J - Quadro 8)"
                )
                resumo_pais = (
                    df_divs.groupby("País")[
                        ["Valor_Bruto", "Retencao_Fonte", "Valor_Liquido"]
                    ]
                    .sum()
                    .reset_index()
                )

                st.dataframe(
                    resumo_pais.style.format(
                        {
                            "Valor_Bruto": "{:,.2f} €",
                            "Retencao_Fonte": "{:,.2f} €",
                            "Valor_Liquido": "{:,.2f} €",
                        }
                    ),
                    use_container_width=True,
                )

                csv_divs_irs = df_divs.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "📥 Descarregar Dividendos para IRS (CSV)",
                    data=csv_divs_irs,
                    file_name="dividendos_estrangeiro_anexo_j.csv",
                    mime="text/csv",
                )
            else:
                st.info("Nenhum registo de dividendos disponível para o IRS.")


# Execução do painel dinâmico em streaming
render_painel_principal()
