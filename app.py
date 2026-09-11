def processar_ficheiro_importado(ficheiro):
    try:
        nome = ficheiro.name.lower()

        if nome.endswith((".xlsx", ".xls")):
            excel = pd.ExcelFile(ficheiro)
            # Procura especificamente a aba de posições abertas da XTB
            aba_alvo = next(
                (
                    s
                    for s in excel.sheet_names
                    if "open" in s.lower() or "aberta" in s.lower()
                ),
                excel.sheet_names[-1],
            )
            df_raw = pd.read_excel(excel, sheet_name=aba_alvo, header=None)
        else:
            df_raw = pd.read_csv(ficheiro, header=None)

        # Localiza a linha onde começam as colunas da tabela
        header_idx = None
        for idx in range(min(30, len(df_raw))):
            linha = [
                str(v).strip().lower()
                for v in df_raw.iloc[idx].values
                if pd.notnull(v)
            ]
            if "ticker" in linha and (
                "volume" in linha or "open price" in linha
            ):
                header_idx = idx
                break

        if header_idx is None:
            return None, "Estrutura de posições abertas não encontrada."

        df_data = df_raw.iloc[header_idx + 1 :].copy()
        df_data.columns = [
            str(c).strip() for c in df_raw.iloc[header_idx].values
        ]

        # Extrai compras executadas e consolida por Ticker
        df_compras = df_data[df_data["Type"] == "BUY"].copy()
        df_compras["Volume"] = pd.to_numeric(
            df_compras["Volume"], errors="coerce"
        )
        col_preco = next(
            c
            for c in df_compras.columns
            if "open price" in c.lower() or "preço" in c.lower()
        )
        df_compras[col_preco] = pd.to_numeric(
            df_compras[col_preco], errors="coerce"
        )

        df_consolidado = (
            df_compras.groupby("Ticker")
            .apply(
                lambda g: pd.Series(
                    {
                        "Shares": round(float(g["Volume"].sum()), 4),
                        "Cost_Per_Share": round(
                            float(
                                (g["Volume"] * g[col_preco]).sum()
                                / g["Volume"].sum()
                            ),
                            2,
                        ),
                        "Currency": "EUR",
                    }
                )
            )
            .reset_index()
        )

        return df_consolidado, None
    except Exception as e:
        return None, f"Erro ao importar: {str(e)}"
